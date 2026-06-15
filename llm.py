"""LM Studio orchestration. Two modes (config.LLM_TOOL_MODE):

  "prompt"  — the model writes inline [[command]] tags in its reply; we parse,
              execute them via MCP, and strip them from the visible text. The
              system prompt + command protocol are folded into the FIRST user
              turn, and no `tools` are sent. This works with any local model,
              including uncensored / Gemma-style ones whose chat template rejects
              the `system` role and has no tool-calling support.
  "native"  — OpenAI function-calling loop (only for models with a tool template).

The web backend owns the MCP client and OpenAI client; this module is stateless
and is handed everything it needs per turn (the frontend stores history).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Awaitable, Callable

from openai import AsyncOpenAI

import config

logger = logging.getLogger("llm")

MAX_TOOL_ROUNDS = 8

SAFETY_SUFFIX = (
    "\n\n[System note] You can control a real connected device. Intensities are "
    "0.0-1.0 and are hard-capped by the server — do not pretend to exceed limits. "
    "Always honor requests to slow down or stop, and stop immediately if the user "
    "asks to stop or seems uncomfortable."
)

# An event sink: the backend forwards these to the websocket.
EventSink = Callable[[dict[str, Any]], Awaitable[None]]


# ===========================================================================
#  Entry point
# ===========================================================================
async def run_chat_turn(
    openai_client: AsyncOpenAI,
    model: str,
    mcp_client: Any,
    system_prompt: str,
    history: list[dict[str, Any]],
    user_text: str,
    emit: EventSink,
) -> str:
    if config.LLM_TOOL_MODE == "native":
        return await _run_native(
            openai_client, model, mcp_client, system_prompt, history, user_text, emit
        )
    return await _run_prompt(
        openai_client, model, mcp_client, system_prompt, history, user_text, emit
    )


# ===========================================================================
#  Prompt mode (default) — inline [[command]] tags
# ===========================================================================
COMMAND_PROTOCOL = """\
[Device control] You can drive the connected device by writing commands inline in \
your reply, each enclosed in DOUBLE SQUARE BRACKETS. These tags are stripped before \
the user sees your message, so weave them in naturally and use them sparingly and \
meaningfully. Commands:
  [[vibrate i=0.6 d=5000]]   set vibration; i = intensity 0.0-1.0, d = duration in \
ms (omit d to keep going until changed/stopped)
  [[pattern name=NAME]]      play a saved vibration pattern by name
  [[stop]]                   stop everything immediately
Intensity is capped by the server. Stop instantly if asked.
{context}"""


def _strip_commands(text: str) -> str:
    text = re.sub(r"\[\[.+?\]\]", "", text, flags=re.S)
    # collapse blank lines left behind
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _parse_kv(rest: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in re.finditer(r"(\w+)\s*=\s*\"?([^\"\s\]]+)\"?", rest):
        out[m.group(1).lower()] = m.group(2)
    return out


def _parse_commands(text: str) -> list[tuple[str, str]]:
    """Return [(verb, rest)] for each [[...]] block, in order."""
    cmds: list[tuple[str, str]] = []
    for m in re.finditer(r"\[\[(.+?)\]\]", text, flags=re.S):
        body = m.group(1).strip()
        parts = body.split(None, 1)
        if not parts:
            continue
        cmds.append((parts[0].lower(), parts[1] if len(parts) > 1 else ""))
    return cmds


async def _device_context(mcp_client: Any) -> tuple[str, int, int]:
    """Build the 'what's available' note for the prompt, plus default target."""
    dev_idx, act_idx = 0, 0
    lines = []
    try:
        devs = (await mcp_client.call_tool("list_devices")).data or []
        if devs:
            dev_idx = devs[0]["index"]
            names = ", ".join(f'#{d["index"]} {d["name"]}' for d in devs)
            lines.append(f"Connected devices: {names}.")
        else:
            lines.append("No device is currently connected.")
    except Exception:
        pass
    try:
        tpls = (await mcp_client.call_tool("list_pattern_templates")).data or []
        if tpls:
            lines.append("Saved patterns: " + ", ".join(t["name"] for t in tpls) + ".")
    except Exception:
        pass
    return ("\n".join(lines), dev_idx, act_idx)


async def _execute_command(
    mcp_client: Any, verb: str, rest: str, dev: int, act: int, emit: EventSink
) -> None:
    try:
        if verb == "stop":
            await emit({"type": "tool", "name": "stop_all", "args": {}})
            await mcp_client.call_tool("stop_all")
            return
        if verb == "vibrate":
            kv = _parse_kv(rest)
            intensity = float(kv.get("i", kv.get("intensity", 0.5)))
            duration = kv.get("d", kv.get("duration", None))
            args = {
                "device": int(kv.get("dev", dev)),
                "actuator": int(kv.get("act", act)),
                "intensity": intensity,
                "duration_ms": int(duration) if duration is not None else None,
            }
            await emit({"type": "tool", "name": "vibrate", "args": args})
            await mcp_client.call_tool("vibrate", args)
            return
        if verb == "pattern":
            name = rest.strip()
            if name.lower().startswith("name="):
                name = name[5:].strip()
            name = name.strip("\"'")
            kv = _parse_kv(rest)
            args = {
                "name": name,
                "device": int(kv.get("dev", dev)),
                "actuator": int(kv.get("act", act)),
            }
            await emit({"type": "tool", "name": "pattern", "args": {"name": name}})
            await mcp_client.call_tool("call_pattern_template", args)
            return
    except Exception as e:
        logger.warning("command '%s %s' failed: %s", verb, rest, e)
        await emit({"type": "tool_result", "name": verb, "result": {"error": str(e)}})


def _fold_into_first_user(
    preamble: str, history: list[dict[str, Any]], user_text: str
) -> list[dict[str, Any]]:
    """Build a user/assistant-only message list with the system preamble folded
    into the first user turn (Gemma-safe: no system role)."""
    msgs = [{"role": m["role"], "content": m.get("content", "")} for m in history]
    msgs.append({"role": "user", "content": user_text})
    out: list[dict[str, Any]] = []
    injected = False
    for m in msgs:
        if not injected and m["role"] == "user":
            out.append({"role": "user", "content": f"{preamble}\n\n---\n\n{m['content']}"})
            injected = True
        else:
            out.append(m)
    if not injected:
        out.insert(0, {"role": "user", "content": preamble})
    return out


def _gemma_prompt(messages: list[dict[str, Any]]) -> str:
    """Render user/assistant messages in Gemma's turn format, so we can hit the
    raw /v1/completions endpoint and skip LM Studio's (broken) chat template.
    llama.cpp adds <bos> itself, so we don't."""
    parts = []
    for m in messages:
        role = "model" if m["role"] == "assistant" else "user"
        parts.append(f"<start_of_turn>{role}\n{m['content']}<end_of_turn>\n")
    parts.append("<start_of_turn>model\n")
    return "".join(parts)


async def _complete(
    openai_client: AsyncOpenAI, model: str, messages: list[dict[str, Any]]
) -> str:
    """Get one completion, either via the chat endpoint (template applied) or the
    raw completions endpoint with a hand-built Gemma prompt (template bypassed)."""
    if config.LLM_PROMPT_FORMAT == "gemma":
        resp = await openai_client.completions.create(
            model=model,
            prompt=_gemma_prompt(messages),
            stop=["<end_of_turn>", "<start_of_turn>"],
            max_tokens=1024,
        )
        return resp.choices[0].text or ""
    resp = await openai_client.chat.completions.create(model=model, messages=messages)
    return resp.choices[0].message.content or ""


async def _run_prompt(
    openai_client: AsyncOpenAI,
    model: str,
    mcp_client: Any,
    system_prompt: str,
    history: list[dict[str, Any]],
    user_text: str,
    emit: EventSink,
) -> str:
    context, dev, act = await _device_context(mcp_client)
    protocol = COMMAND_PROTOCOL.format(context=context)
    preamble = (system_prompt or "").strip() + SAFETY_SUFFIX + "\n\n" + protocol
    messages = _fold_into_first_user(preamble, history, user_text)

    raw = await _complete(openai_client, model, messages)

    for verb, rest in _parse_commands(raw):
        await _execute_command(mcp_client, verb, rest, dev, act, emit)

    text = _strip_commands(raw)
    await emit({"type": "assistant", "text": text})
    return text


# ===========================================================================
#  Native mode — OpenAI function-calling
# ===========================================================================
def mcp_tools_to_openai(tools: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for t in tools:
        schema = getattr(t, "inputSchema", None) or {"type": "object", "properties": {}}
        out.append({
            "type": "function",
            "function": {
                "name": t.name,
                "description": (t.description or "")[:1024],
                "parameters": schema,
            },
        })
    return out


def _assistant_to_message(msg: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
    if msg.tool_calls:
        out["tool_calls"] = [
            {"id": tc.id, "type": "function",
             "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
            for tc in msg.tool_calls
        ]
    return out


async def _run_native(
    openai_client: AsyncOpenAI,
    model: str,
    mcp_client: Any,
    system_prompt: str,
    history: list[dict[str, Any]],
    user_text: str,
    emit: EventSink,
) -> str:
    tools = await mcp_client.list_tools()
    oai_tools = mcp_tools_to_openai(tools)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": (system_prompt or "") + SAFETY_SUFFIX}
    ]
    messages.extend({"role": m["role"], "content": m.get("content", "")} for m in history)
    messages.append({"role": "user", "content": user_text})

    for _round in range(MAX_TOOL_ROUNDS):
        resp = await openai_client.chat.completions.create(
            model=model, messages=messages, tools=oai_tools, tool_choice="auto"
        )
        msg = resp.choices[0].message
        messages.append(_assistant_to_message(msg))

        if not msg.tool_calls:
            text = msg.content or ""
            await emit({"type": "assistant", "text": text})
            return text

        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            await emit({"type": "tool", "name": name, "args": args})
            try:
                data = (await mcp_client.call_tool(name, args)).data
            except Exception as e:
                data = {"error": str(e)}
            await emit({"type": "tool_result", "name": name, "result": data})
            messages.append({
                "role": "tool", "tool_call_id": tc.id,
                "content": json.dumps(data, ensure_ascii=False, default=str),
            })

    resp = await openai_client.chat.completions.create(model=model, messages=messages)
    text = resp.choices[0].message.content or ""
    await emit({"type": "assistant", "text": text})
    return text
