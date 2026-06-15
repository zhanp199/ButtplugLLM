# ButtplugLLM

> **会控制玩具的 AI 角色扮演。** 和一个**本地 LLM** 聊天,它扮演角色、并通过
> [Intiface Central](https://intiface.com/central/) 和
> [Buttplug](https://buttplug.io) 协议实时控制你的亲密设备 —— 沉浸式、完全本地、隐私优先。

[English README →](README.md)

> ⚠️ **18+ / NSFW。** 这是供成年人私下自用的成人软件。全程在本机运行,只与你本地的
> Intiface 和 LLM 通信,不向任何第三方发送数据。

```
浏览器(聊天 + 控制界面 · 中/英 i18n · 明暗主题)
   │  WS /ws/chat (LLM,流式)        │  REST /api/*(手动控制、急停)
   ▼                                ▼
app.py  ── MCP 客户端 ──▶  mcp_server.py  ── buttplug-py ──▶  Intiface Central ──▶ 设备
   └── OpenAI 客户端 ──▶  本地 LLM(LM Studio / 任意 OpenAI 兼容服务)
```

## 功能

- **角色扮演聊天**:内置多套人设(强势腹黑学姐、温柔恋人、病娇、高冷女王、听话小猫,
  以及女性向/otome 男性角色),**外加人设构建器** —— 填字段(名字、关系、场景、玩具、
  节奏)即自动生成 system prompt。
- **LLM 实时控制设备**:模型在回复里内联指令,**说到那一刻**就触发(流式)——
  调振动、播放模式、停止。
- **独立 FastMCP 服务**(`mcp_server.py`):暴露设备 + 模板工具,可被任意 MCP 客户端
  复用(如 Claude Desktop)。
- **振动模式模板**:LLM 与手动控制面板共享同一套。
- **支持 uncensored / 本地模型**(Gemma、Llama、Qwen…),无需模型支持工具调用(见下文
  *LLM 模式*)。
- **中/英双语界面**与**明暗主题**。
- **安全优先**:急停、安全词、强度上限、看门狗。

## 环境要求

- **Python 3.10+**
- **[Intiface Central](https://intiface.com/central/)** 已启动并开启 server(默认
  `ws://127.0.0.1:12345`)。没有真机?在 Intiface 设备设置里启用一个*模拟设备*即可体验。
- 一个挂在 OpenAI 兼容接口后的**本地 LLM** —— 例如
  **[LM Studio](https://lmstudio.ai/)** 启动本地 server(默认
  `http://127.0.0.1:1234/v1`)并加载模型。成人角色扮演建议用 *uncensored* 模型。

## 安装

```bash
git clone https://github.com/zhanp199/ButtplugLLM.git
cd ButtplugLLM

python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env              # 可选 —— 调端口 / 安全 / 模型
```

## 运行

```bash
python run.py                     # 或:./venv/bin/python run.py
# 然后打开 http://127.0.0.1:8080
```

`run.py` 会先拉起 MCP 服务、等其就绪,再启动 Web 应用,退出时自动关闭 MCP 进程。
(请先启动 Intiface Central 和你的 LLM server。)

## LLM 模式

在 `.env` 里按你的模型设置:

- `LLM_TOOL_MODE` —— **`prompt`**(默认)让模型用内联 `[[vibrate …]]` /
  `[[pattern name=…]]` / `[[stop]]` 标记驱动设备,**任何**模型都能用(含无工具调用的
  uncensored 模型);`native` 走 OpenAI 函数调用(仅适用于有工具模板的模型)。
- `LLM_PROMPT_FORMAT` —— `chat`(默认)或 **`gemma`**。Gemma 系 / `*-uncensored`
  GGUF 的 chat 模板会让 LM Studio 的 Jinja 报错(*"Cannot call something that is not
  a function"*),用 `gemma` 可绕开模板、自行拼 prompt。
- `LLM_STREAMING` —— `auto`(默认)/ `on` / `off`。流式下,内联指令在出现的瞬间触发。

## 安全机制(均独立于 LLM)

- **急停按钮**(界面常驻)→ 直接 `stop_all`,不经过 LLM。
- **安全词**(`SAFE_WORD`,默认 `red`):聊天里输入它,会在消息进入模型前就停掉一切。
- **强度上限**(`MAX_INTENSITY`)与**时长上限**(`MAX_DURATION_MS`):控制器与 MCP 两层
  都对每条指令钳制。
- **看门狗**(`WATCHDOG_TIMEOUT_S`):无明确时长、一直开着的执行器超时后强制停止;与
  Intiface 断连也会清空本地状态。
- **替换语义**:对某执行器下新指令会可靠地取消并替换旧指令,不留能在急停后复活的孤儿任务。

## 振动模板

模板保存在 `templates.json`(每步含 `intensity` + `duration_ms`,外加 `loop` 循环
次数),**直接编辑该文件**即可 —— LLM 和 UI 播放同一套。内置的几套都循序渐进、时长 1
分钟以上:暖身 Warm-Up、挑逗 Tease、海浪 Waves、心跳 Racing Heart、边缘 Edge、榨取
Milking、失控 Overload、高潮 Climax、余韵 Afterglow。文件缺失时首次运行会从
`patterns.py` 写入默认值。

## 配置项

| 变量 | 默认值 | 含义 |
|---|---|---|
| `INTIFACE_URL` | `ws://127.0.0.1:12345` | Intiface Central server |
| `LMSTUDIO_BASE_URL` | `http://127.0.0.1:1234/v1` | 本地 LLM OpenAI 接口 |
| `LMSTUDIO_MODEL` | `local-model` | server 上报的模型 id |
| `LLM_TOOL_MODE` | `prompt` | `prompt`(内联标记)或 `native`(函数调用) |
| `LLM_PROMPT_FORMAT` | `chat` | `chat`,或 `gemma` 绕开损坏的 chat 模板 |
| `LLM_STREAMING` | `auto` | `auto` / `on` / `off` |
| `MCP_PORT` / `APP_PORT` | `8765` / `8080` | MCP 服务 / Web 应用端口 |
| `MAX_INTENSITY` | `1.0` | 强度硬上限(0–1) |
| `MAX_DURATION_MS` | `30000` | 单条指令 / 单步上限 |
| `WATCHDOG_TIMEOUT_S` | `15` | 无限时指令的 deadman 超时 |
| `SAFE_WORD` | `red` | 输入即停止一切 |

## 把独立 MCP 服务接到其他客户端

`mcp_server.py` 是独立的。把任意 MCP 客户端指向 `http://127.0.0.1:8765/mcp`,即可获得
同一套设备工具与模板工具。

## 许可证

[BSD 3-Clause License](LICENSE)。
