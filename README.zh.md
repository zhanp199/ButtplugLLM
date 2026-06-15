# ButtplugLLM

> `LLM_Buttplug_Roleplay` —— 和一个**本地 LLM** 聊天,让它通过
> [Intiface Central](https://intiface.com/central/) 和
> [Buttplug](https://buttplug.io) 协议控制亲密设备。供成年人私下自用。

[English README →](README.md)

```
浏览器(聊天 + 控制界面,i18n:中文 / English)
   │  WS /ws/chat (LLM)        │  REST /api/*(手动控制、急停)
   ▼                           ▼
app.py  ── MCP 客户端 ──▶  mcp_server.py  ── buttplug-py ──▶  Intiface Central ──▶ 设备
   └── OpenAI 客户端 ──▶  LM Studio(本地,OpenAI 兼容接口)
```

## 模块一览

- **`controller.py`** —— 唯一直接操作硬件的代码,也是所有安全逻辑所在:强度/时长
  钳制、定时自动停、看门狗(deadman)、按执行器可靠的「旧停新替」、以及 `stop_all`。
- **`mcp_server.py`** —— 独立的 FastMCP 服务,暴露设备工具和振动模板工具。可被任何
  MCP 客户端复用(例如 Claude Desktop)。
- **`patterns.py`** —— 振动模式模板(steps + loop)及 JSON 持久化,LLM 和 UI 共享同
  一份。
- **`llm.py` / `app.py`** —— LM Studio 编排,以及 Starlette 后端。
- **`static/`** —— 三栏单页应用(会话 · 聊天 · 控制面板)。状态存在 `localStorage`;
  界面文案集中在 `static/i18n.js`(中文 / English,可切换)。

## 前置条件

1. **Intiface Central** 已运行且开启了 server(默认 `ws://127.0.0.1:12345`)。没有
   真机?在 Intiface 的设备设置里启用一个模拟设备即可。
2. **LM Studio** 已启动本地 server(默认 `http://127.0.0.1:1234/v1`),并加载一个
   **支持 function calling(工具调用)** 的模型。

## 安装

```bash
./venv/bin/pip install -r requirements.txt
cp .env.example .env   # 可选 —— 调整端口 / 安全上限
```

## 运行

```bash
./venv/bin/python run.py
# 然后打开 http://127.0.0.1:8080
```

`run.py` 会先拉起 MCP 服务、等它就绪,再启动 Web 应用;退出时自动关闭 MCP 进程。

## 安全机制(均独立于 LLM)

- **急停按钮**(界面常驻)→ 直接 `stop_all`,不经过 LLM。
- **安全词**(`SAFE_WORD`,默认 `red`):在聊天里输入它,会在消息进入模型之前就停掉
  一切。
- **强度上限**(`MAX_INTENSITY`)与**时长上限**(`MAX_DURATION_MS`):在控制器和 MCP
  两层都对每条指令做钳制。
- **看门狗**(`WATCHDOG_TIMEOUT_S`):任何没有明确时长、一直开着的执行器,超时后会被
  强制停止(deadman)。与 Intiface 断连也会清空本地状态。
- **替换语义**:对某个执行器下新指令时,会可靠地取消并替换旧指令 —— 不会留下能在
  急停后「复活」的孤儿任务。

以上都可在 `.env` 中调整(见 `.env.example`)。

## 国际化(i18n)

界面内置中文与英文。在左下角的选择器切换语言,选择会保存在 `localStorage`。要新增
语言:在 `static/i18n.js` 的 `I18N` 里加一份词典,并在 `static/index.html` 的选择器
里加一个 `<option>` 即可。

## 振动模板

模板保存在 `templates.json`(每步含 `intensity` + `duration_ms`,外加一个 `loop`
循环次数),**直接编辑该文件**即可 —— LLM 和 UI 播放的是同一套。内置的几套都设计成
时长 1 分钟以上、循序渐进:慢热 / 海浪 / 脉冲律动 / 心跳 / 欲擒故纵 / 颤栗 / 高潮冲刺。
若该文件缺失,首次运行会从 `patterns.py` 写入默认值。

## 配置项

| 变量 | 默认值 | 含义 |
|---|---|---|
| `INTIFACE_URL` | `ws://127.0.0.1:12345` | Intiface Central server |
| `LMSTUDIO_BASE_URL` | `http://127.0.0.1:1234/v1` | LM Studio OpenAI 接口 |
| `LMSTUDIO_MODEL` | `local-model` | LM Studio 上报的模型 id |
| `MCP_PORT` / `APP_PORT` | `8765` / `8080` | MCP 服务 / Web 应用端口 |
| `MAX_INTENSITY` | `1.0` | 强度硬上限(0–1) |
| `MAX_DURATION_MS` | `30000` | 单条指令 / 单步上限 |
| `WATCHDOG_TIMEOUT_S` | `15` | 无限时指令的 deadman 超时 |
| `SAFE_WORD` | `red` | 输入即停止一切 |

## 把独立 MCP 服务接到其他客户端

`mcp_server.py` 是独立的。把任意 MCP 客户端指向 `http://127.0.0.1:8765/mcp`,即可
获得同一套设备工具与模板工具。
