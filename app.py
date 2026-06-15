"""Web backend: serves the SPA, runs chat over a websocket, and proxies manual
control to the MCP server over REST.

Two independent paths to the device:
  - WS /ws/chat  -> the LLM may call MCP tools (clamped server-side)
  - REST /api/*  -> the UI's manual controls and the emergency stop, which never
                    pass through the LLM.
The emergency stop and the configured safe-word both hit MCP ``stop_all`` directly.
"""
from __future__ import annotations

import logging
import os

from fastmcp import Client
from openai import AsyncOpenAI
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect

import config
from llm import run_chat_turn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

openai_client = AsyncOpenAI(
    base_url=config.LMSTUDIO_BASE_URL, api_key=config.LMSTUDIO_API_KEY
)


async def mcp_call(name: str, args: dict | None = None):
    """Open a short-lived MCP client, call one tool, return its structured data."""
    async with Client(config.MCP_URL) as c:
        result = await c.call_tool(name, args or {})
        return result.data


# --- static ----------------------------------------------------------------
async def index(_request: Request) -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


# --- REST control (manual UI; never via the LLM) ---------------------------
async def api_devices(_request: Request) -> JSONResponse:
    return JSONResponse(await mcp_call("list_devices"))


async def api_status(_request: Request) -> JSONResponse:
    return JSONResponse(await mcp_call("get_status"))


async def api_scan(_request: Request) -> JSONResponse:
    return JSONResponse(await mcp_call("scan_devices", {"seconds": 4.0}))


async def api_vibrate(request: Request) -> JSONResponse:
    body = await request.json()
    return JSONResponse(
        await mcp_call(
            "vibrate",
            {
                "device": int(body["device"]),
                "actuator": int(body.get("actuator", 0)),
                "intensity": float(body.get("intensity", 0.5)),
                "duration_ms": body.get("duration_ms"),
            },
        )
    )


async def api_stop(_request: Request) -> JSONResponse:
    return JSONResponse(await mcp_call("stop_all"))


async def api_play(request: Request) -> JSONResponse:
    body = await request.json()
    return JSONResponse(
        await mcp_call(
            "play_pattern",
            {
                "device": int(body["device"]),
                "actuator": int(body.get("actuator", 0)),
                "steps": body.get("steps", []),
                "loop": int(body.get("loop", 0)),
            },
        )
    )


async def api_templates(_request: Request) -> JSONResponse:
    return JSONResponse(await mcp_call("list_pattern_templates"))


async def api_templates_create(request: Request) -> JSONResponse:
    body = await request.json()
    return JSONResponse(
        await mcp_call(
            "add_pattern_template",
            {
                "name": str(body["name"]),
                "steps": body.get("steps", []),
                "loop": int(body.get("loop", 0)),
            },
        )
    )


async def api_templates_delete(request: Request) -> JSONResponse:
    name = request.path_params["name"]
    return JSONResponse(await mcp_call("delete_pattern_template", {"name": name}))


async def api_templates_call(request: Request) -> JSONResponse:
    name = request.path_params["name"]
    body = await request.json()
    return JSONResponse(
        await mcp_call(
            "call_pattern_template",
            {
                "name": name,
                "device": int(body["device"]),
                "actuator": int(body.get("actuator", 0)),
            },
        )
    )


# --- chat websocket --------------------------------------------------------
def _is_safe_word(text: str) -> bool:
    return config.SAFE_WORD in text.lower().split()


async def ws_chat(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")

            if msg_type == "stop" or (
                msg_type == "user" and _is_safe_word(data.get("text", ""))
            ):
                await mcp_call("stop_all")
                await ws.send_json({"type": "stopped"})
                if msg_type == "stop":
                    continue
                # safe-word: acknowledge and skip the LLM entirely
                await ws.send_json(
                    {"type": "assistant",
                     "text": "🛑 Stopped everything. We can pause here."}
                )
                continue

            if msg_type != "user":
                continue

            async def emit(event: dict) -> None:
                await ws.send_json(event)

            # one MCP client for the whole turn (list_tools + tool calls)
            try:
                async with Client(config.MCP_URL) as mcp_client:
                    await run_chat_turn(
                        openai_client=openai_client,
                        model=config.LMSTUDIO_MODEL,
                        mcp_client=mcp_client,
                        system_prompt=data.get("systemPrompt", ""),
                        history=data.get("history", []),
                        user_text=data.get("text", ""),
                        emit=emit,
                    )
            except Exception as e:
                logger.exception("chat turn failed")
                await ws.send_json({"type": "error", "message": str(e)})
    except WebSocketDisconnect:
        pass


routes = [
    Route("/", index),
    Route("/api/devices", api_devices),
    Route("/api/status", api_status),
    Route("/api/scan", api_scan, methods=["POST"]),
    Route("/api/vibrate", api_vibrate, methods=["POST"]),
    Route("/api/stop", api_stop, methods=["POST"]),
    Route("/api/play", api_play, methods=["POST"]),
    Route("/api/templates", api_templates),
    Route("/api/templates", api_templates_create, methods=["POST"]),
    Route("/api/templates/{name}", api_templates_delete, methods=["DELETE"]),
    Route("/api/templates/{name}/call", api_templates_call, methods=["POST"]),
    WebSocketRoute("/ws/chat", ws_chat),
    Mount("/static", app=StaticFiles(directory=STATIC_DIR), name="static"),
]

app = Starlette(routes=routes)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=config.APP_HOST, port=config.APP_PORT)
