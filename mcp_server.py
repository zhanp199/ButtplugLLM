"""Standalone FastMCP server: the device-control surface.

Wraps a single DeviceController and a shared TemplateStore, exposing both device
commands and pattern-template management as MCP tools. Runs as its own process
(HTTP transport) so the web backend connects as an MCP client — and so the same
server can later be mounted in Claude Desktop or any other MCP client.

All tools are async and run on the server's event loop (run_in_thread=False)
because the underlying buttplug connection is bound to that loop.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastmcp import FastMCP
from pydantic import BaseModel, Field

import config
from controller import DeviceController
from patterns import Pattern, Step, TemplateStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_server")

# Shared singletons, initialized in the lifespan.
controller: DeviceController | None = None
store: TemplateStore = TemplateStore(config.TEMPLATES_PATH)


def _ctl() -> DeviceController:
    if controller is None:
        raise RuntimeError("Controller not initialized")
    return controller


@asynccontextmanager
async def lifespan(_server: FastMCP):
    global controller
    controller = DeviceController()
    try:
        await controller.connect()
    except Exception as e:  # keep server up so tools can report the error
        logger.error("Could not connect to Intiface: %s", e)
    try:
        yield
    finally:
        await controller.disconnect()


mcp = FastMCP(
    "LLMToy-Device-Control",
    instructions=(
        "Controls intimate hardware connected through Intiface Central. "
        "Intensities are 0.0-1.0 and are hard-capped server-side. Prefer timed "
        "commands or pattern templates over indefinite ones. Call stop_all to "
        "halt everything immediately."
    ),
    lifespan=lifespan,
)


class StepInput(BaseModel):
    intensity: float = Field(ge=0.0, le=1.0, description="0.0-1.0")
    duration_ms: int = Field(ge=0, description="how long to hold this step, in ms")


# --- device tools ----------------------------------------------------------
@mcp.tool(run_in_thread=False)
async def scan_devices(seconds: float = 4.0) -> list[dict[str, Any]]:
    """Scan for nearby devices for a few seconds, then return the device list."""
    await _ctl().scan(min(15.0, max(1.0, seconds)))
    return _ctl().list_devices()


@mcp.tool(run_in_thread=False)
async def list_devices() -> list[dict[str, Any]]:
    """List currently connected devices and their actuators (no new scan)."""
    return _ctl().list_devices()


@mcp.tool(run_in_thread=False)
async def get_status() -> dict[str, Any]:
    """Connection status, device count, active actuators, and safety limits."""
    return _ctl().status()


@mcp.tool(run_in_thread=False)
async def vibrate(
    device: int,
    actuator: int = 0,
    intensity: float = 0.5,
    duration_ms: int | None = None,
) -> dict[str, Any]:
    """Set a vibrate actuator's intensity (0.0-1.0). If duration_ms is given the
    actuator auto-stops after it; otherwise it runs until changed/stopped (and is
    subject to the safety watchdog). Intensity is clamped to the server ceiling."""
    return await _ctl().vibrate(device, actuator, intensity, duration_ms)


@mcp.tool(run_in_thread=False)
async def linear_move(
    device: int, actuator: int = 0, position: float = 0.5, duration_ms: int = 1000
) -> dict[str, Any]:
    """Move a linear actuator to a position (0.0-1.0) over duration_ms."""
    return await _ctl().linear_move(device, actuator, position, duration_ms)


@mcp.tool(run_in_thread=False)
async def rotate(
    device: int, actuator: int = 0, speed: float = 0.5, clockwise: bool = True
) -> dict[str, Any]:
    """Spin a rotatory actuator at speed (0.0-1.0) in the given direction."""
    return await _ctl().rotate(device, actuator, speed, clockwise)


@mcp.tool(run_in_thread=False)
async def stop_device(device: int) -> dict[str, Any]:
    """Stop all actuators on one device."""
    return await _ctl().stop_device(device)


@mcp.tool(run_in_thread=False)
async def stop_all() -> dict[str, Any]:
    """Emergency stop: halt every actuator on every device immediately."""
    return await _ctl().stop_all()


# --- pattern template tools ------------------------------------------------
@mcp.tool(run_in_thread=False)
async def add_pattern_template(
    name: str, steps: list[StepInput], loop: int = 0
) -> dict[str, Any]:
    """Save a named vibration pattern (a sequence of intensity/duration steps).
    loop is the number of extra repeats (0 = play once). Shared with the UI."""
    pattern = Pattern(
        name=name,
        steps=[Step(s.intensity, s.duration_ms) for s in steps],
        loop=max(0, int(loop)),
    )
    store.add(pattern)
    return {"ok": True, "name": name, "step_count": len(pattern.steps),
            "estimated_ms": pattern.total_ms()}


@mcp.tool(run_in_thread=False)
async def list_pattern_templates() -> list[dict[str, Any]]:
    """List saved vibration pattern templates."""
    return [p.to_dict() | {"estimated_ms": p.total_ms()} for p in store.list()]


@mcp.tool(run_in_thread=False)
async def delete_pattern_template(name: str) -> dict[str, Any]:
    """Delete a saved pattern template by name."""
    return {"ok": store.delete(name), "name": name}


@mcp.tool(run_in_thread=False)
async def call_pattern_template(
    name: str, device: int, actuator: int = 0
) -> dict[str, Any]:
    """Play a saved vibration pattern template on a device's vibrate actuator."""
    pattern = store.get(name)
    if pattern is None:
        raise ValueError(f"No pattern template named {name!r}")
    return await _ctl().run_pattern(device, actuator, pattern)


@mcp.tool(run_in_thread=False)
async def play_pattern(
    device: int, steps: list[StepInput], actuator: int = 0, loop: int = 0
) -> dict[str, Any]:
    """Play an ad-hoc vibration pattern (without saving it as a template)."""
    pattern = Pattern(
        name="ad-hoc",
        steps=[Step(s.intensity, s.duration_ms) for s in steps],
        loop=max(0, int(loop)),
    )
    return await _ctl().run_pattern(device, actuator, pattern)


if __name__ == "__main__":
    logger.info("Starting MCP server on %s:%s", config.MCP_HOST, config.MCP_PORT)
    mcp.run(transport="http", host=config.MCP_HOST, port=config.MCP_PORT)
