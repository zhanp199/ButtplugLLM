# ButtplugLLM

> **AI roleplay that controls your toys.** Chat with a **local LLM** that plays a
> character and drives intimate hardware in real time through
> [Intiface Central](https://intiface.com/central/) and the
> [Buttplug](https://buttplug.io) protocol — immersive, fully local, privacy-first.

[简体中文 README →](README.zh.md)

> ⚠️ **18+ / NSFW.** This is adult software for private use by consenting adults.
> It runs entirely on your machine and talks only to your local Intiface and LLM —
> nothing is sent to any third party.

```
Browser (chat + control UI · i18n EN/中文 · light/dark)
   │  WS /ws/chat (LLM, streaming)   │  REST /api/* (manual control, e-stop)
   ▼                                 ▼
app.py  ── MCP client ──▶  mcp_server.py  ── buttplug-py ──▶  Intiface Central ──▶ device
   └── OpenAI client ──▶  local LLM (LM Studio / any OpenAI-compatible server)
```

## Features

- **Roleplay chat** with preset personas (dominant senpai, tender lover, yandere,
  cold mistress, obedient sub, plus 女性向/otome male characters) **and a persona
  builder** — fill in fields (names, relationship, scenario, the toy, pacing) and
  it writes the system prompt for you.
- **The LLM controls the device** by emitting inline commands that fire the moment
  they appear mid-reply (token streaming) — vibrate, play a pattern, or stop.
- **Standalone FastMCP server** (`mcp_server.py`) exposing the device + pattern
  tools — reusable by any MCP client (e.g. Claude Desktop).
- **Vibration pattern templates** shared by the LLM and the manual control panel.
- **Works with uncensored / local models** (Gemma, Llama, Qwen, …) — no
  tool-calling support required (see *LLM modes* below).
- **Bilingual UI** (English / 简体中文) and **light/dark themes**.
- **Safety first** — emergency stop, safe-word, intensity cap, deadman watchdog.

## Requirements

- **Python 3.10+**
- **[Intiface Central](https://intiface.com/central/)** running with its server
  started (default `ws://127.0.0.1:12345`). No hardware? Enable a *simulated
  device* in Intiface's device settings to try it out.
- A **local LLM** behind an OpenAI-compatible endpoint — e.g.
  **[LM Studio](https://lmstudio.ai/)** with its local server started (default
  `http://127.0.0.1:1234/v1`) and a model loaded. An *uncensored* model is
  recommended for adult roleplay.

## Setup

```bash
git clone https://github.com/zhanp199/ButtplugLLM.git
cd ButtplugLLM

python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env              # optional — edit ports / safety / model
```

## Run

```bash
python run.py                     # or: ./venv/bin/python run.py
# then open http://127.0.0.1:8080
```

`run.py` starts the MCP server, waits for it, serves the web app, and stops the
MCP process on exit. (Make sure Intiface Central and your LLM server are running
first.)

## LLM modes

Set these in `.env` to match your model:

- `LLM_TOOL_MODE` — **`prompt`** (default) lets the model drive the device by
  writing inline `[[vibrate …]]` / `[[pattern name=…]]` / `[[stop]]` tags; works
  with **any** model, including uncensored ones with no tool-calling. `native`
  uses OpenAI function-calling (only for models with a proper tool template).
- `LLM_PROMPT_FORMAT` — `chat` (default) or **`gemma`**. Use `gemma` for
  Gemma-family / `*-uncensored` GGUFs whose chat template breaks LM Studio's Jinja
  engine (error: *"Cannot call something that is not a function"*); it bypasses
  the template by hand-building the prompt.
- `LLM_STREAMING` — `auto` (default) / `on` / `off`. With streaming, inline
  commands fire the instant they appear mid-reply.

## Safety

Several layers, all independent of the LLM:

- **Emergency stop** button (always visible) → `stop_all`, bypassing the LLM.
- **Safe-word** (`SAFE_WORD`, default `red`): typing it in chat stops everything
  before the message ever reaches the model.
- **Intensity ceiling** (`MAX_INTENSITY`) and **duration cap** (`MAX_DURATION_MS`)
  clamp every command in both the controller and the MCP layer.
- **Watchdog** (`WATCHDOG_TIMEOUT_S`): any actuator left running with no explicit
  duration is force-stopped after the timeout. Losing the Intiface connection
  also clears local state.
- **Replace semantics**: a new command on an actuator reliably cancels and
  replaces the previous one — no orphaned tasks that survive a stop.

## Vibration templates

Templates live in `templates.json` (steps of `intensity` + `duration_ms`, plus a
`loop` count) and are **edited in that file** — both the LLM and the UI play the
same set. The bundled set builds gradually over a minute or more: 暖身 Warm-Up,
挑逗 Tease, 海浪 Waves, 心跳 Racing Heart, 边缘 Edge, 榨取 Milking, 失控 Overload,
高潮 Climax, 余韵 Afterglow. Defaults are seeded from `patterns.py` on first run if
the file is missing.

## Configuration

| Var | Default | Meaning |
|---|---|---|
| `INTIFACE_URL` | `ws://127.0.0.1:12345` | Intiface Central server |
| `LMSTUDIO_BASE_URL` | `http://127.0.0.1:1234/v1` | local LLM OpenAI endpoint |
| `LMSTUDIO_MODEL` | `local-model` | model id reported by the server |
| `LLM_TOOL_MODE` | `prompt` | `prompt` (inline tags) or `native` (function-calling) |
| `LLM_PROMPT_FORMAT` | `chat` | `chat`, or `gemma` to bypass a broken chat template |
| `LLM_STREAMING` | `auto` | `auto` / `on` / `off` |
| `MCP_PORT` / `APP_PORT` | `8765` / `8080` | MCP server / web app ports |
| `MAX_INTENSITY` | `1.0` | hard intensity ceiling (0–1) |
| `MAX_DURATION_MS` | `30000` | per-command / per-step cap |
| `WATCHDOG_TIMEOUT_S` | `15` | deadman timeout for indefinite commands |
| `SAFE_WORD` | `red` | typing this stops everything |

## Project layout

- **`controller.py`** — the only code that touches hardware, and where all safety
  lives (clamping, timed auto-stop, watchdog, replace-old-with-new, `stop_all`).
- **`mcp_server.py`** — standalone FastMCP server with the device + pattern tools.
- **`patterns.py`** — pattern-template model + JSON persistence.
- **`llm.py` / `app.py`** — LLM orchestration and the Starlette web backend.
- **`static/`** — three-pane SPA; state in `localStorage`, strings in
  `static/i18n.js`.

## Using the standalone MCP server with another client

`mcp_server.py` is independent. Point any MCP client at `http://127.0.0.1:8765/mcp`
to get the same device + template tools.

## License

[BSD 3-Clause License](LICENSE).
