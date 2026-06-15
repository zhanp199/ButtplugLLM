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


def _split_tag(inner: str) -> tuple[str, str]:
    parts = inner.strip().split(None, 1)
    if not parts:
        return ("", "")
    return (parts[0].lower(), parts[1] if len(parts) > 1 else "")


# Single-bracket mode/stage annotations the model sometimes writes instead of a
# real command, e.g. "[切换模式:余韵 Afterglow]" / "[mode: Afterglow]".
_MODE_KW = (r"切换模式到|切换模式|切换到|切换|进入|模式|阶段|状态|"
            r"mode|stage|phase|switch|播放|序列|pattern")


def _tpl_match(name: str, tpl_names: list[str]) -> str | None:
    """Resolve a free-text name to a real template (case-insensitive, either
    direction) so 'Afterglow' or '余韵' map to '余韵 Afterglow'. None if no match."""
    n = (name or "").strip().lower()
    if not n:
        return None
    for tn in tpl_names:
        t = tn.lower()
        if n == t or n in t or t in n:
            return tn
    return None


def _classify(inner: str, double: bool, tpl_names: list[str]) -> tuple:
    """Classify a bracketed group into ('cmd', verb, rest) | ('text', literal) |
    ('drop',). Double brackets are commands; single brackets are commands only
    when they clearly are (a verb, a mode annotation naming a real pattern, or a
    bare pattern name) — otherwise they're ordinary prose and stay visible."""
    s = inner.strip()
    if not s:
        return ("drop",) if double else ("text", "[]")
    verb0 = s.split(None, 1)[0].lower()
    if verb0 in ("vibrate", "pattern", "stop"):
        v, rest = _split_tag(s)
        return ("cmd", v, rest)
    if double:
        tn = _tpl_match(s, tpl_names)          # e.g. [[余韵 Afterglow]]
        return ("cmd", "pattern", "name=" + tn) if tn else ("drop",)
    m = re.match(r"^(?:" + _MODE_KW + r")\s*[:：]?\s*(.+?)\s*$", s, flags=re.I)
    if m:
        cand = re.sub(r"\s*(?:模式|mode)\s*$", "", m.group(1).strip().strip("「」\"'“”"), flags=re.I)
        tn = _tpl_match(cand, tpl_names)
        return ("cmd", "pattern", "name=" + tn) if tn else ("drop",)  # tone mode → strip
    tn = _tpl_match(s, tpl_names)              # bare [余韵 Afterglow]
    if tn:
        return ("cmd", "pattern", "name=" + tn)
    return ("text", "[" + inner + "]")         # ordinary prose


async def _handle_group(
    inner: str, double: bool, tpl_names: list[str], mcp_client, dev, act, emit
) -> str | None:
    """Run a classified bracket group; return visible text to keep, or None."""
    action = _classify(inner, double, tpl_names)
    if action[0] == "cmd":
        await _execute_command(mcp_client, action[1], action[2], dev, act, emit)
        return None
    if action[0] == "text":
        return action[1]
    return None  # drop


async def _device_context(mcp_client: Any) -> tuple[str, int, int, list[str]]:
    """Build the 'what's available' note for the prompt, the default target, and
    the list of saved pattern names (used to tell a real pattern from a tone)."""
    dev_idx, act_idx = 0, 0
    lines: list[str] = []
    tpl_names: list[str] = []
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
        tpl_names = [t["name"] for t in tpls]
        if tpl_names:
            lines.append("Saved patterns: " + ", ".join(tpl_names) + ".")
    except Exception:
        pass
    return ("\n".join(lines), dev_idx, act_idx, tpl_names)


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


# --- streaming: incremental [[command]] detection -------------------------
class _StreamingUnsupported(Exception):
    """Raised before any output is emitted so the caller can fall back."""


_stream_supported: bool | None = None  # None = unknown, set by auto-probe


def _use_streaming() -> bool:
    if config.LLM_STREAMING == "off":
        return False
    if config.LLM_STREAMING == "on":
        return True
    return _stream_supported is not False  # "auto": try unless known-bad


def _stream_process(buffer: str, final: bool) -> tuple[list[tuple], str]:
    """Pull complete events out of the rolling buffer, in order. Returns
    ([("text", s) | ("group", inner, is_double)], remaining_buffer). Anything
    from an unclosed "[" is held back so partial brackets never reach the user;
    classification (command vs prose) happens in _classify."""
    events: list[tuple] = []
    while True:
        i = buffer.find("[")
        if i == -1:
            if buffer:
                events.append(("text", buffer))
            buffer = ""
            break
        if i > 0:
            events.append(("text", buffer[:i]))
            buffer = buffer[i:]
        if len(buffer) < 2 and not final:
            break  # wait: could become "[["
        if buffer.startswith("[["):
            end = buffer.find("]]")
            if end == -1:
                if final:
                    buffer = ""  # drop an unterminated command
                break
            events.append(("group", buffer[2:end], True))
            buffer = buffer[end + 2:]
        else:
            end = buffer.find("]")
            if end == -1:
                if final:
                    events.append(("text", buffer))
                    buffer = ""
                break
            events.append(("group", buffer[1:end], False))
            buffer = buffer[end + 1:]
    return events, buffer


async def _open_stream(openai_client: AsyncOpenAI, model: str, messages):
    if config.LLM_PROMPT_FORMAT == "gemma":
        return await openai_client.completions.create(
            model=model, prompt=_gemma_prompt(messages),
            stop=["<end_of_turn>", "<start_of_turn>"], max_tokens=1024, stream=True,
        )
    return await openai_client.chat.completions.create(
        model=model, messages=messages, stream=True,
    )


def _chunk_text(chunk: Any, is_gemma: bool) -> str:
    try:
        return (chunk.choices[0].text if is_gemma
                else chunk.choices[0].delta.content) or ""
    except (AttributeError, IndexError, TypeError):
        return ""


async def _run_prompt_streaming(
    openai_client, model, mcp_client, messages, dev, act, tpl_names, emit
) -> str:
    global _stream_supported
    is_gemma = config.LLM_PROMPT_FORMAT == "gemma"
    try:
        stream = await _open_stream(openai_client, model, messages)
    except Exception as e:
        raise _StreamingUnsupported(str(e))

    buffer, parts, emitted = "", [], False

    async def handle(events):
        nonlocal emitted
        for ev in events:
            if ev[0] == "text":
                if ev[1]:
                    parts.append(ev[1])
                    await emit({"type": "delta", "text": ev[1]})
                    emitted = True
            else:  # ("group", inner, double)
                vis = await _handle_group(ev[1], ev[2], tpl_names, mcp_client, dev, act, emit)
                if vis:
                    parts.append(vis)
                    await emit({"type": "delta", "text": vis})
                    emitted = True

    try:
        async for chunk in stream:
            piece = _chunk_text(chunk, is_gemma)
            if not piece:
                continue
            _stream_supported = True
            buffer += piece
            events, buffer = _stream_process(buffer, final=False)
            await handle(events)
    except Exception as e:
        if not emitted:
            raise _StreamingUnsupported(str(e))
        logger.warning("stream interrupted after partial output: %s", e)

    events, _ = _stream_process(buffer, final=True)
    await handle(events)

    text = re.sub(r"\n{3,}", "\n\n", "".join(parts)).strip()
    await emit({"type": "assistant_end", "text": text})
    return text


async def _run_prompt(
    openai_client: AsyncOpenAI,
    model: str,
    mcp_client: Any,
    system_prompt: str,
    history: list[dict[str, Any]],
    user_text: str,
    emit: EventSink,
) -> str:
    context, dev, act, tpl_names = await _device_context(mcp_client)
    protocol = COMMAND_PROTOCOL.format(context=context)
    preamble = (system_prompt or "").strip() + SAFETY_SUFFIX + "\n\n" + protocol
    messages = _fold_into_first_user(preamble, history, user_text)

    if _use_streaming():
        try:
            return await _run_prompt_streaming(
                openai_client, model, mcp_client, messages, dev, act, tpl_names, emit
            )
        except _StreamingUnsupported as e:
            global _stream_supported
            _stream_supported = False
            logger.warning("streaming unsupported (%s); using non-streaming", e)

    raw = await _complete(openai_client, model, messages)
    events, _ = _stream_process(raw, final=True)
    parts: list[str] = []
    for ev in events:
        if ev[0] == "text":
            parts.append(ev[1])
        else:
            vis = await _handle_group(ev[1], ev[2], tpl_names, mcp_client, dev, act, emit)
            if vis:
                parts.append(vis)
    text = re.sub(r"\n{3,}", "\n\n", "".join(parts)).strip()
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
