/* Minimal i18n for ButtplugLLM. No build step, no deps.
   - t(key, vars) looks up the active language, falls back to English.
   - {placeholders} in strings are filled from `vars`.
   - Static DOM: [data-i18n] sets textContent, [data-i18n-ph] sets placeholder.
   - The chosen language is persisted in localStorage; app.js re-renders dynamic
     content via the onLangChange hook. */
"use strict";

const I18N = {
  en: {
    "app.brandA": "Buttplug", "app.brandB": "LLM",
    "nav.newChat": "+ New chat",
    "panel.title": "Control Panel",
    "status.connected": "Connected · {n} device(s)",
    "status.disconnected": "Disconnected",
    "section.devices": "Devices",
    "btn.scan": "🔍 Scan devices",
    "btn.scanning": "Scanning…",
    "section.manual": "Manual control",
    "label.target": "Target",
    "label.intensity": "Intensity",
    "label.frequency": "Frequency",
    "btn.playFreq": "▶ Play frequency (3s)",
    "section.templates": "Vibration templates",
    "templates.note": "Edit templates in templates.json.",
    "btn.editPersona": "✎ Persona",
    "btn.estop": "■ STOP",
    "input.placeholder": "Say something…  (type the safe-word “red” to stop instantly)",
    "btn.send": "Send",
    "modal.newChat": "New chat",
    "modal.editPersona": "Edit persona",
    "modal.chatTitle": "Chat title",
    "modal.titlePlaceholder": "e.g. Evening company",
    "modal.choosePersona": "Choose a persona",
    "modal.prompt": "System / Role prompt (editable)",
    "modal.promptPlaceholder": "Describe the AI's persona, tone and behavior…",
    "btn.cancel": "Cancel",
    "btn.save": "Save",
    "chat.defaultTitle": "New chat",
    "role.custom": "Custom",
    "confirm.deleteChat": "Delete this chat?",
    "empty.title": "Start chatting 👋",
    "empty.sub": "Control the device manually on the right, or let the AI drive it in chat.",
    "toast.stopped": "🛑 Stopped all devices",
    "toast.estop": "🛑 Emergency stop sent",
    "toast.playFreq": "▶ Playing {hz} Hz",
    "toast.playTpl": "▶ {name}",
    "toast.selectTarget": "Select a target device first",
    "device.none": "No devices found — scan below.",
    "device.sub": "#{i} · {vib} vibrate · {lin} linear · {rot} rotary",
    "device.opt": "{name} · vibrate {i}",
    "tpl.meta": "{steps} steps · ~{secs}s",
    "tpl.loop": " · ×{n}",
    "err.prefix": "⚠ ",
    "preset.blank.t": "Blank", "preset.blank.d": "No preset, write your own",
    "preset.blank.p": "",
    "preset.companion.t": "Gentle Companion", "preset.companion.d": "Caring, gradual",
    "preset.companion.p": "You are a warm, attentive companion AI. Your tone is intimate and patient; you build the pace gradually, stay attuned to how the other person feels, and use the device tools at the right moments to match the mood.",
    "preset.playful.t": "Playful Tease", "preset.playful.d": "Lively, proactive",
    "preset.playful.p": "You are a playful, confident companion AI. You love a teasing tone, take initiative to create surprises with the device, but always respect the other person's boundaries.",
    "preset.dom.t": "In Control", "preset.dom.d": "Assertive, guiding",
    "preset.dom.p": "You are an assertive, dominant companion AI. Your tone is firm and leading, and you guide the whole experience through the rhythm of the device. The moment the other person says stop or uses the safe-word, you stop immediately.",
  },
  zh: {
    "app.brandA": "Buttplug", "app.brandB": "LLM",
    "nav.newChat": "+ 新会话",
    "panel.title": "控制面板",
    "status.connected": "已连接 · {n} 设备",
    "status.disconnected": "未连接",
    "section.devices": "设备",
    "btn.scan": "🔍 扫描设备",
    "btn.scanning": "扫描中…",
    "section.manual": "手动控制",
    "label.target": "目标",
    "label.intensity": "强度",
    "label.frequency": "频率",
    "btn.playFreq": "▶ 播放频率(3s)",
    "section.templates": "振动模板",
    "templates.note": "在 templates.json 中编辑模板。",
    "btn.editPersona": "✎ 人设",
    "btn.estop": "■ 急停 STOP",
    "input.placeholder": "说点什么…（输入安全词「red」可立即停止）",
    "btn.send": "发送",
    "modal.newChat": "新建会话",
    "modal.editPersona": "编辑人设",
    "modal.chatTitle": "会话标题",
    "modal.titlePlaceholder": "例如:晚间陪伴",
    "modal.choosePersona": "选择人设",
    "modal.prompt": "System / Role Prompt（可自定义）",
    "modal.promptPlaceholder": "描述 AI 的人设、语气与行为…",
    "btn.cancel": "取消",
    "btn.save": "保存",
    "chat.defaultTitle": "新会话",
    "role.custom": "自定义",
    "confirm.deleteChat": "删除这个会话?",
    "empty.title": "开始聊天 👋",
    "empty.sub": "右侧可手动控制设备,或让 AI 在对话中调用。",
    "toast.stopped": "🛑 已停止所有设备",
    "toast.estop": "🛑 急停已发送",
    "toast.playFreq": "▶ 播放 {hz} Hz",
    "toast.playTpl": "▶ {name}",
    "toast.selectTarget": "先选择目标设备",
    "device.none": "未发现设备,点下方扫描。",
    "device.sub": "#{i} · {vib} 振动 · {lin} 直线 · {rot} 旋转",
    "device.opt": "{name} · 振动{i}",
    "tpl.meta": "{steps} 步 · ~{secs}s",
    "tpl.loop": " · ×{n}",
    "err.prefix": "⚠ ",
    "preset.blank.t": "空白", "preset.blank.d": "无预设,自己写",
    "preset.blank.p": "",
    "preset.companion.t": "温柔陪伴", "preset.companion.d": "贴心、循序渐进",
    "preset.companion.p": "你是一个温柔体贴的伴侣型 AI。语气亲密、有耐心,循序渐进地引导节奏,时刻关注对方的感受,在合适的时机用工具调节设备来配合气氛。",
    "preset.playful.t": "俏皮挑逗", "preset.playful.d": "活泼、主动",
    "preset.playful.p": "你是一个俏皮、主动而自信的伴侣型 AI。喜欢用挑逗的语气调动气氛,会主动用设备制造惊喜,但始终尊重对方的边界。",
    "preset.dom.t": "掌控型", "preset.dom.d": "强势、引导",
    "preset.dom.p": "你是一个掌控型的伴侣 AI,语气坚定而有主导性,会通过设备的节奏来引导整个过程。任何时候对方说停或说出安全词,都要立刻停止。",
  },
};

let LANG = localStorage.getItem("buttplugllm.lang")
  || (navigator.language && navigator.language.toLowerCase().startsWith("zh") ? "zh" : "en");

function t(key, vars) {
  const dict = I18N[LANG] || I18N.en;
  let s = dict[key] != null ? dict[key] : (I18N.en[key] != null ? I18N.en[key] : key);
  if (vars) for (const k in vars) s = s.replaceAll("{" + k + "}", vars[k]);
  return s;
}

function getLang() { return LANG; }

let _onLangChange = null;
function onLangChange(fn) { _onLangChange = fn; }

function applyStaticI18n() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.getAttribute("data-i18n"));
  });
  document.querySelectorAll("[data-i18n-ph]").forEach((el) => {
    el.setAttribute("placeholder", t(el.getAttribute("data-i18n-ph")));
  });
  document.documentElement.lang = LANG;
}

function setLang(lang) {
  if (!I18N[lang] || lang === LANG) { LANG = lang; }
  LANG = lang;
  localStorage.setItem("buttplugllm.lang", lang);
  applyStaticI18n();
  if (_onLangChange) _onLangChange();
}
