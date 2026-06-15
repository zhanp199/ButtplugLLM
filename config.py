"""Central configuration. Reads from environment / .env, with safe defaults.

Imported by every process (MCP server, web app, run.py) so they agree on ports
and safety limits.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()  # load .env if present; real env vars take precedence


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _i(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# --- Connections ---
INTIFACE_URL = os.environ.get("INTIFACE_URL", "ws://127.0.0.1:12345")

MCP_HOST = os.environ.get("MCP_HOST", "127.0.0.1")
MCP_PORT = _i("MCP_PORT", 8765)
MCP_URL = f"http://{MCP_HOST}:{MCP_PORT}/mcp"

APP_HOST = os.environ.get("APP_HOST", "127.0.0.1")
APP_PORT = _i("APP_PORT", 8080)

# --- LM Studio (OpenAI compatible) ---
LMSTUDIO_BASE_URL = os.environ.get("LMSTUDIO_BASE_URL", "http://127.0.0.1:1234/v1")
LMSTUDIO_MODEL = os.environ.get("LMSTUDIO_MODEL", "local-model")
LMSTUDIO_API_KEY = os.environ.get("LMSTUDIO_API_KEY", "lm-studio")

# --- Safety ---
MAX_INTENSITY = max(0.0, min(1.0, _f("MAX_INTENSITY", 1.0)))
MAX_DURATION_MS = _i("MAX_DURATION_MS", 30_000)
WATCHDOG_TIMEOUT_S = _f("WATCHDOG_TIMEOUT_S", 15.0)
SAFE_WORD = os.environ.get("SAFE_WORD", "red").strip().lower()

# Where pattern templates are persisted (shared by LLM + UI).
TEMPLATES_PATH = os.environ.get(
    "TEMPLATES_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates.json"),
)
