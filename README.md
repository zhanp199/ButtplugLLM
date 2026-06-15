# ButtplugLLM

> `LLM_Buttplug_Roleplay` — chat with a local LLM that can control intimate
> hardware through [Intiface Central](https://intiface.com/central/) and the
> [Buttplug](https://buttplug.io) protocol. For private use by consenting adults.

[简体中文 README →](README.zh.md)

```
Browser (chat + control UI, i18n: EN / 中文)
   │  WS /ws/chat (LLM)      │  REST /api/* (manual control, e-stop)
   ▼                         ▼
app.py  ── MCP client ──▶  mcp_server.py  ── buttplug-py ──▶  Intiface Central ──▶ device
   └── OpenAI client ──▶  LM Studio (local, OpenAI-compatible)
```

- **`controller.py`** — the only code that touches hardware, and where all safety
  lives: intensity/duration clamping, timed auto-stop, a deadman watchdog,
  reliable replace-old-with-new per actuator, and `stop_all`.
- **`mcp_server.py`** — standalone FastMCP server exposing device + pattern-template
  tools. Reusable by any MCP client (e.g. Claude Desktop).
- **`patterns.py`** — vibration pattern templates (steps + loop) with JSON
  persistence, shared by the LLM and the UI.
- **`llm.py` / `app.py`** — LM Studio orchestration and the Starlette web backend.
- **`static/`** — three-pane SPA (conversations · chat · control panel). State in
  `localStorage`; UI strings in `static/i18n.js` (English / 中文, switchable).

## Prerequisites

1. **Intiface Central** running with its server enabled (default
   `ws://127.0.0.1:12345`). No hardware? Enable a simulated device in Intiface's
   device settings.
2. **LM Studio** running its local server (default `http://127.0.0.1:1234/v1`) with
   a **tool-calling capable** model loaded.

## Setup

```bash
./venv/bin/pip install -r requirements.txt
cp .env.example .env   # optional — edit ports / safety limits
```

## Run

```bash
./venv/bin/python run.py
# then open http://127.0.0.1:8080
```

`run.py` starts the MCP server, waits for it, then serves the web app, and stops
the MCP process on exit.

## Safety

Several layers, independent of the LLM:

- **Emergency stop** button (always visible) → `stop_all`, bypassing the LLM.
- **Safe-word** (`SAFE_WORD`, default `red`): typing it in chat stops everything
  before the message ever reaches the model.
- **Intensity ceiling** (`MAX_INTENSITY`) and **duration cap** (`MAX_DURATION_MS`)
  clamp every command in both the controller and the MCP layer.
- **Watchdog** (`WATCHDOG_TIMEOUT_S`): any actuator left running with no explicit
  duration is force-stopped after the timeout (deadman switch). Dropping the
  Intiface connection also clears local state.
- **Replace semantics**: a new command on an actuator reliably cancels and
  replaces the previous one — no orphaned tasks that survive a stop.

All tunable in `.env` (see `.env.example`).

## Internationalization

The UI ships with English and Simplified Chinese. Switch languages from the
selector at the bottom-left; the choice is saved in `localStorage`. To add a
language, add a dictionary to `I18N` in `static/i18n.js` and an `<option>` to the
selector in `static/index.html`.

## Vibration templates

Templates live in `templates.json` (steps of `intensity` + `duration_ms`, plus a
`loop` count) and are **edited in that file** — both the LLM and the UI play the
same set. The bundled set builds over a minute or more (慢热 / 海浪 / 脉冲律动 /
心跳 / 欲擒故纵 / 颤栗 / 高潮冲刺). Defaults are seeded from `patterns.py` on first
run if the file is missing.

## Configuration

| Var | Default | Meaning |
|---|---|---|
| `INTIFACE_URL` | `ws://127.0.0.1:12345` | Intiface Central server |
| `LMSTUDIO_BASE_URL` | `http://127.0.0.1:1234/v1` | LM Studio OpenAI endpoint |
| `LMSTUDIO_MODEL` | `local-model` | model id reported by LM Studio |
| `MCP_PORT` / `APP_PORT` | `8765` / `8080` | MCP server / web app ports |
| `MAX_INTENSITY` | `1.0` | hard intensity ceiling (0–1) |
| `MAX_DURATION_MS` | `30000` | per-command / per-step cap |
| `WATCHDOG_TIMEOUT_S` | `15` | deadman timeout for indefinite commands |
| `SAFE_WORD` | `red` | typing this stops everything |

## Using the standalone MCP server with another client

`mcp_server.py` is independent. Point any MCP client at `http://127.0.0.1:8765/mcp`
to get the same device + template tools.
