"""LM Studio orchestration: bridges MCP tools to OpenAI function-calling and runs
the tool-use loop for one chat turn.

The web backend owns the MCP client and OpenAI client; this module is stateless
and is handed everything it needs per turn (the frontend stores history).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Awaitable, Callable

from openai import AsyncOpenAI

logger = logging.getLogger("llm")

MAX_TOOL_ROUNDS = 8

SAFETY_SUFFIX = (
    "\n\n[System note] You can control a real connected device by calling the "
    "provided tools. Intensities are 0.0-1.0 and are hard-capped by the server — "
    "do not pretend to exceed limits. Always honor the user's requests to slow "
    "down or stop, and call stop_all immediately if they ask you to stop or seem "
    "uncomfortable. Prefer timed commands (duration_ms) or pattern templates over "
    "leaving a device running indefinitely."
)

# An event sink: the backend forwards these to the websocket.
EventSink = Callable[[dict[str, Any]], Awaitable[None]]


def mcp_tools_to_openai(tools: list[Any]) -> list[dict[str, Any]]:
    """Convert MCP tool definitions to OpenAI chat-completions tool schemas."""
    out: list[dict[str, Any]] = []
    for t in tools:
        schema = getattr(t, "inputSchema", None) or {"type": "object", "properties": {}}
        out.append(
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": (t.description or "")[:1024],
                    "parameters": schema,
                },
            }
        )
    return out


def _assistant_to_message(msg: Any) -> dict[str, Any]:
    """Serialize an OpenAI assistant message (incl. tool_calls) for re-sending."""
    out: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
    if msg.tool_calls:
        out["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in msg.tool_calls
        ]
    return out


async def run_chat_turn(
    openai_client: AsyncOpenAI,
    model: str,
    mcp_client: Any,
    system_prompt: str,
    history: list[dict[str, Any]],
    user_text: str,
    emit: EventSink,
) -> str:
    """Run one user turn: call the model, execute any tool calls via MCP, repeat
    until the model produces a final text answer. Emits 'tool' / 'assistant'
    events as it goes. Returns the final assistant text."""
    tools = await mcp_client.list_tools()
    oai_tools = mcp_tools_to_openai(tools)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": (system_prompt or "") + SAFETY_SUFFIX}
    ]
    # history items are {role, content}; tool-call rounds are not persisted client-side
    messages.extend({"role": m["role"], "content": m.get("content", "")} for m in history)
    messages.append({"role": "user", "content": user_text})

    final_text = ""
    for _round in range(MAX_TOOL_ROUNDS):
        resp = await openai_client.chat.completions.create(
            model=model, messages=messages, tools=oai_tools, tool_choice="auto"
        )
        msg = resp.choices[0].message
        messages.append(_assistant_to_message(msg))

        if not msg.tool_calls:
            final_text = msg.content or ""
            await emit({"type": "assistant", "text": final_text})
            return final_text

        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            await emit({"type": "tool", "name": name, "args": args})
            try:
                result = await mcp_client.call_tool(name, args)
                data = result.data
            except Exception as e:  # feed the error back so the model can recover
                data = {"error": str(e)}
            await emit({"type": "tool_result", "name": name, "result": data})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(data, ensure_ascii=False, default=str),
                }
            )

    # Ran out of tool rounds; ask for a closing message without tools.
    resp = await openai_client.chat.completions.create(model=model, messages=messages)
    final_text = resp.choices[0].message.content or ""
    await emit({"type": "assistant", "text": final_text})
    return final_text
