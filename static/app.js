/* ButtplugLLM frontend. Multi-chat state in localStorage; chat over WS; manual
   control + templates over REST. All user-facing strings go through t() (see
   i18n.js); dynamic content re-renders on language change. Backend is stateless —
   each turn we send the active chat's system prompt + history. */
"use strict";

const $ = (id) => document.getElementById(id);
const LS_CHATS = "buttplugllm.chats";
const LS_ACTIVE = "buttplugllm.active";

const PRESET_KEYS = ["blank", "builder",
  "senpai", "lover", "yandere", "mistress", "kitten",
  "ceo", "puppy", "aloof", "yanboy", "knight"];
const DEFAULT_PRESET = "senpai";
function presetObj(key) {
  return { key, title: t(`preset.${key}.t`), desc: t(`preset.${key}.d`), prompt: t(`preset.${key}.p`) };
}
function presets() { return PRESET_KEYS.map(presetObj); }

let state = { chats: [], active: null };
let ws = null;
let devices = [];
let intensityTimer = null;
let editingExisting = false;
let selectedPreset = DEFAULT_PRESET;

/* ---------- persistence ---------- */
function load() {
  try { state.chats = JSON.parse(localStorage.getItem(LS_CHATS)) || []; } catch { state.chats = []; }
  state.active = localStorage.getItem(LS_ACTIVE);
  if (!state.chats.length) {
    const c = newChatObj(t("chat.defaultTitle"), t(`preset.${DEFAULT_PRESET}.p`), t(`preset.${DEFAULT_PRESET}.t`));
    state.chats.push(c); state.active = c.id;
  }
  if (!state.chats.find((c) => c.id === state.active)) state.active = state.chats[0].id;
  save();
}
function save() {
  localStorage.setItem(LS_CHATS, JSON.stringify(state.chats));
  localStorage.setItem(LS_ACTIVE, state.active);
}
function uid() { return Date.now().toString(36) + Math.random().toString(36).slice(2, 7); }
function newChatObj(title, prompt, role) {
  return { id: uid(), title, role: role || t("role.custom"), systemPrompt: prompt || "", messages: [] };
}
function activeChat() { return state.chats.find((c) => c.id === state.active); }

/* ---------- chat list ---------- */
function renderChatList() {
  const el = $("chatList"); el.innerHTML = "";
  state.chats.forEach((c) => {
    const div = document.createElement("div");
    div.className = "chat-item" + (c.id === state.active ? " active" : "");
    div.innerHTML = `<div class="title">${escapeHtml(c.title)}<div class="role">${escapeHtml(c.role || "")}</div></div><span class="x">×</span>`;
    div.querySelector(".title").onclick = () => { state.active = c.id; save(); renderAll(); };
    div.querySelector(".x").onclick = (e) => { e.stopPropagation(); deleteChat(c.id); };
    el.appendChild(div);
  });
}
function deleteChat(id) {
  if (!confirm(t("confirm.deleteChat"))) return;
  state.chats = state.chats.filter((c) => c.id !== id);
  if (!state.chats.length) { const c = newChatObj(t("chat.defaultTitle"), "", t("role.custom")); state.chats.push(c); }
  if (state.active === id) state.active = state.chats[0].id;
  save(); renderAll();
}

/* ---------- messages ---------- */
function renderMessages() {
  const el = $("messages"); el.innerHTML = "";
  const c = activeChat();
  if (!c.messages.length) {
    el.innerHTML = `<div class="empty"><h2>${escapeHtml(t("empty.title"))}</h2><p>${escapeHtml(t("empty.sub"))}</p></div>`;
    return;
  }
  c.messages.forEach((m) => addMsgDom(m.role, m.content));
  el.scrollTop = el.scrollHeight;
}
function addMsgDom(role, text) {
  const d = document.createElement("div");
  d.className = "msg " + role;
  d.textContent = text;
  $("messages").appendChild(d);
  $("messages").scrollTop = $("messages").scrollHeight;
  return d;
}
function addToolChip(name, args) {
  const d = document.createElement("div");
  d.className = "toolchip";
  d.innerHTML = `⚙ <b>${escapeHtml(name)}</b> ${escapeHtml(JSON.stringify(args))}`;
  const thk = $("thinkingDom");
  $("messages").insertBefore(d, thk || null);
  $("messages").scrollTop = $("messages").scrollHeight;
}
let thinkingDom = null;
function showThinking() {
  hideThinking();
  const d = document.createElement("div");
  d.className = "thinking"; d.id = "thinkingDom";
  d.innerHTML = `<span class="d"></span><span class="d"></span><span class="d"></span>`;
  $("messages").appendChild(d);
  thinkingDom = d;
  $("messages").scrollTop = $("messages").scrollHeight;
}
function hideThinking() { if (thinkingDom) { thinkingDom.remove(); thinkingDom = null; } }

function renderHeader() {
  const c = activeChat();
  $("chatTitle").textContent = c.title;
  $("chatRole").textContent = c.role || "";
}
function renderAll() { renderChatList(); renderHeader(); renderMessages(); }

/* ---------- websocket chat ---------- */
function connectWs() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws/chat`);
  ws.onmessage = (ev) => {
    const e = JSON.parse(ev.data);
    if (e.type === "assistant") {
      hideThinking();
      const c = activeChat();
      c.messages.push({ role: "assistant", content: e.text }); save();
      addMsgDom("assistant", e.text);
    } else if (e.type === "tool") {
      addToolChip(e.name, e.args);
    } else if (e.type === "error") {
      hideThinking();
      addMsgDom("error", t("err.prefix") + e.message);
    } else if (e.type === "stopped") {
      toast(t("toast.stopped"));
    }
  };
  ws.onclose = () => setTimeout(connectWs, 1500);
}
function sendMessage() {
  const text = $("input").value.trim();
  if (!text) return;
  const c = activeChat();
  const history = c.messages.map((m) => ({ role: m.role, content: m.content }));
  c.messages.push({ role: "user", content: text }); save();
  addMsgDom("user", text);
  $("input").value = ""; autoGrow();
  if (text.toLowerCase().split(/\s+/).includes("red")) {
    ws.send(JSON.stringify({ type: "user", text }));  // safe-word path
    return;
  }
  showThinking();
  ws.send(JSON.stringify({ type: "user", systemPrompt: c.systemPrompt, history, text }));
}
function emergencyStop() {
  if (ws && ws.readyState === 1) ws.send(JSON.stringify({ type: "stop" }));
  fetch("/api/stop", { method: "POST" }).catch(() => {});
  setIntensitySlider(0);
  toast(t("toast.estop"));
}

/* ---------- devices / control (REST) ---------- */
async function refreshDevices() {
  try {
    devices = await (await fetch("/api/devices")).json();
    const st = await (await fetch("/api/status")).json();
    setStatus(st.connected, st.device_count);
  } catch { setStatus(false, 0); devices = []; }
  renderDevices();
}
function setStatus(on, count) {
  $("statusPill").className = "status-pill" + (on ? " on" : "");
  $("statusText").textContent = on ? t("status.connected", { n: count }) : t("status.disconnected");
}
function renderDevices() {
  const el = $("devices"); el.innerHTML = "";
  const sel = $("targetSelect"); sel.innerHTML = "";
  if (!devices.length) { el.innerHTML = `<div class="device sub">${escapeHtml(t("device.none"))}</div>`; }
  devices.forEach((d) => {
    const div = document.createElement("div");
    div.className = "device";
    const vib = (d.vibrate_actuators || []).length;
    const sub = t("device.sub", { i: d.index, vib, lin: (d.linear_actuators || []).length, rot: (d.rotatory_actuators || []).length });
    div.innerHTML = `<div class="nm">${escapeHtml(d.name)}</div><div class="sub">${escapeHtml(sub)}</div>`;
    el.appendChild(div);
    (d.vibrate_actuators || []).forEach((a) => {
      const opt = document.createElement("option");
      opt.value = `${d.index}:${a.index}`;
      opt.textContent = t("device.opt", { name: d.name, i: a.index });
      sel.appendChild(opt);
    });
  });
}
function currentTarget() {
  const v = $("targetSelect").value;
  if (!v) return null;
  const [device, actuator] = v.split(":").map(Number);
  return { device, actuator };
}
function manualVibrate(intensity) {
  const tgt = currentTarget(); if (!tgt) return;
  fetch("/api/vibrate", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ device: tgt.device, actuator: tgt.actuator, intensity }),
  }).catch(() => {});
}
function setIntensitySlider(pct) {
  $("intensity").value = pct; $("intVal").textContent = pct + "%";
}
function freqHz() { return $("frequency").value / 10; }
function pulseSteps(freq, intensity, totalMs, duty = 0.5) {
  freq = Math.max(0.1, Math.min(20, freq));
  const period = 1000 / freq;
  const on = Math.max(1, Math.round(period * duty));
  const off = Math.max(1, Math.round(period * (1 - duty)));
  const cycles = Math.max(1, Math.round(totalMs / (on + off)));
  const steps = [];
  for (let i = 0; i < cycles; i++) {
    steps.push({ intensity, duration_ms: on });
    steps.push({ intensity: 0, duration_ms: off });
  }
  return steps;
}
function playFrequency() {
  const tgt = currentTarget(); if (!tgt) { toast(t("toast.selectTarget")); return; }
  const intensity = ($("intensity").value / 100) || 0.8;
  const steps = pulseSteps(freqHz(), intensity, 3000);
  fetch("/api/play", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ device: tgt.device, actuator: tgt.actuator, steps }),
  }).then(() => toast(t("toast.playFreq", { hz: freqHz().toFixed(1) }))).catch(() => {});
}

/* ---------- templates ---------- */
async function refreshTemplates() {
  let tpls = [];
  try { tpls = await (await fetch("/api/templates")).json(); } catch {}
  const el = $("templates"); el.innerHTML = "";
  tpls.forEach((tp) => {
    const div = document.createElement("div");
    div.className = "tpl";
    const secs = (tp.estimated_ms / 1000).toFixed(1);
    let meta = t("tpl.meta", { steps: tp.steps.length, secs });
    if (tp.loop) meta += t("tpl.loop", { n: tp.loop + 1 });
    div.innerHTML = `<div class="nm">${escapeHtml(tp.name)}<small>${escapeHtml(meta)}</small></div>`;
    const play = document.createElement("button"); play.className = "btn sm"; play.textContent = "▶";
    play.onclick = () => playTemplate(tp.name);
    div.appendChild(play);
    el.appendChild(div);
  });
}
function playTemplate(name) {
  const tgt = currentTarget(); if (!tgt) { toast(t("toast.selectTarget")); return; }
  fetch(`/api/templates/${encodeURIComponent(name)}/call`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ device: tgt.device, actuator: tgt.actuator }),
  }).then(() => toast(t("toast.playTpl", { name }))).catch(() => {});
}

/* ---------- chat modal ---------- */
function openChatModal(edit) {
  editingExisting = edit;
  $("modalTitle").textContent = edit ? t("modal.editPersona") : t("modal.newChat");
  const c = edit ? activeChat() : null;
  $("mTitle").value = c ? c.title : "";
  $("mPrompt").value = c ? c.systemPrompt : t(`preset.${DEFAULT_PRESET}.p`);
  selectedPreset = edit ? "blank" : DEFAULT_PRESET;
  renderPresets();
  updateBuilderVisibility();
  $("chatModal").classList.add("show");
}
function renderPresets() {
  const el = $("presetGrid"); el.innerHTML = "";
  presets().forEach((p) => {
    const b = document.createElement("button");
    b.className = "preset" + (p.key === selectedPreset ? " active" : "");
    b.innerHTML = `<div class="pt">${escapeHtml(p.title)}</div><div class="pd">${escapeHtml(p.desc)}</div>`;
    b.onclick = () => {
      selectedPreset = p.key;
      if (p.key === "blank") $("mPrompt").value = "";
      else if (p.key !== "builder") $("mPrompt").value = p.prompt;
      updateBuilderVisibility();
      renderPresets();
    };
    el.appendChild(b);
  });
}
function updateBuilderVisibility() {
  $("builderFields").style.display = selectedPreset === "builder" ? "block" : "none";
}
function fval(id) { const e = $(id); return e ? e.value.trim() : ""; }
function buildPromptFromFields() {
  const en = typeof getLang === "function" && getLang() === "en";
  const aiName = fval("f_aiName"), myName = fval("f_myName"), persona = fval("f_aiPersona");
  const rel = fval("f_rel"), scene = fval("f_scene"), role = fval("f_role"), toy = fval("f_toy");
  const pace = fval("f_pace"), limits = fval("f_limits");
  const ageSuffix = en ? " y/o" : "岁";
  const joiner = en ? ", " : "、";
  const myParts = [fval("f_myGender"), fval("f_myAge") && fval("f_myAge") + ageSuffix, fval("f_myJob")].filter(Boolean).join(joiner);
  const aiParts = [fval("f_aiGender"), fval("f_aiAge") && fval("f_aiAge") + ageSuffix, fval("f_aiJob")].filter(Boolean).join(joiner);
  const L = [];
  if (en) {
    L.push(`You will play "${aiName || "them"}" in a first-person, fully immersive adult roleplay with me.`);
    L.push("\n[Characters]");
    L.push(`- Me: ${myName || "me"}${myParts ? " (" + myParts + ")" : ""}.`);
    L.push(`- You: ${aiName || "you"}${aiParts ? " (" + aiParts + ")" : ""}${persona ? ", personality/tone: " + persona : ""}.`);
    if (rel) L.push(`- Our relationship: ${rel}.`);
    if (scene) L.push(`\n[Scene] ${scene}`);
    if (role) L.push(`\n[Character notes] ${role}`);
    L.push(toy
      ? `\n[Device] On/in me: ${toy}. You can control it live via commands to drive the scene.`
      : `\n[Device] You can control the toy on me live via commands to drive the scene.`);
    if (pace) L.push(`[Pacing] ${pace}.`);
    if (limits) L.push(`[Avoid] ${limits}.`);
    return L.join("\n") + (typeof CMD_BLOCK_EN !== "undefined" ? CMD_BLOCK_EN : "");
  }
  L.push(`你将扮演【${aiName || "对方"}】,与我进行第一人称、沉浸式的成人角色扮演。`);
  L.push("\n【人物】");
  L.push(`- 我:${myName || "我"}${myParts ? "(" + myParts + ")" : ""}。`);
  L.push(`- 你:${aiName || "你"}${aiParts ? "(" + aiParts + ")" : ""}${persona ? ",性格/语气:" + persona : ""}。`);
  if (rel) L.push(`- 我们的关系:${rel}。`);
  if (scene) L.push(`\n【场景】${scene}`);
  if (role) L.push(`\n【角色设定】${role}`);
  L.push(toy
    ? `\n【设备】我身上/体内有:${toy}。你可以通过指令实时控制它,用快感推动剧情。`
    : `\n【设备】你可以通过指令实时控制我身上的玩具,用快感推动剧情。`);
  if (pace) L.push(`【节奏偏好】${pace}。`);
  if (limits) L.push(`【请避免】${limits}。`);
  return L.join("\n") + (typeof CMD_BLOCK !== "undefined" ? CMD_BLOCK : "");
}
function saveChatModal() {
  if (selectedPreset === "builder" && !$("mPrompt").value.trim()) {
    $("mPrompt").value = buildPromptFromFields();
  }
  let title = $("mTitle").value.trim();
  if (!title) title = (selectedPreset === "builder" && (fval("f_aiName") || fval("f_rel"))) || t("chat.defaultTitle");
  const prompt = $("mPrompt").value;
  const role = selectedPreset === "builder"
    ? (fval("f_aiName") || fval("f_rel") || t("role.custom"))
    : (presets().find((p) => p.key === selectedPreset)?.title || t("role.custom"));
  if (editingExisting) {
    const c = activeChat(); c.title = title; c.systemPrompt = prompt; c.role = role;
  } else {
    const c = newChatObj(title, prompt, role);
    state.chats.unshift(c); state.active = c.id;
  }
  save(); renderAll();
  $("chatModal").classList.remove("show");
}

/* ---------- utils ---------- */
function escapeHtml(s) { return String(s).replace(/[&<>"']/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m])); }
let toastTimer = null;
function toast(msg) {
  const el = $("toast"); el.textContent = msg; el.classList.add("show");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove("show"), 2200);
}
function autoGrow() { const i = $("input"); i.style.height = "auto"; i.style.height = Math.min(140, i.scrollHeight) + "px"; }
function applyTheme(theme) {
  document.body.dataset.theme = theme;
  localStorage.setItem("buttplugllm.theme", theme);
  $("themeBtn").textContent = theme === "light" ? "☀️" : "🌙";
}

/* ---------- wire up ---------- */
function init() {
  applyStaticI18n();
  load(); renderAll(); connectWs(); refreshDevices(); refreshTemplates();

  $("langSel").value = getLang();
  $("langSel").onchange = () => setLang($("langSel").value);
  onLangChange(() => {
    renderAll(); refreshDevices(); refreshTemplates();
    if ($("chatModal").classList.contains("show")) {
      $("modalTitle").textContent = editingExisting ? t("modal.editPersona") : t("modal.newChat");
      renderPresets();
    }
  });

  $("newChatBtn").onclick = () => openChatModal(false);
  $("editPromptBtn").onclick = () => openChatModal(true);
  $("estopBtn").onclick = emergencyStop;
  $("sendBtn").onclick = sendMessage;
  $("input").addEventListener("input", autoGrow);
  $("input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });

  $("scanBtn").onclick = async () => {
    $("scanBtn").textContent = t("btn.scanning"); $("scanBtn").disabled = true;
    try { await fetch("/api/scan", { method: "POST" }); } catch {}
    await refreshDevices();
    $("scanBtn").textContent = t("btn.scan"); $("scanBtn").disabled = false;
  };
  $("intensity").addEventListener("input", () => {
    const pct = +$("intensity").value; $("intVal").textContent = pct + "%";
    clearTimeout(intensityTimer);
    intensityTimer = setTimeout(() => manualVibrate(pct / 100), 100);
  });
  $("frequency").addEventListener("input", () => { $("freqVal").textContent = freqHz().toFixed(1) + " Hz"; });
  $("playFreqBtn").onclick = playFrequency;

  $("mCancel").onclick = () => $("chatModal").classList.remove("show");
  $("mClose").onclick = () => $("chatModal").classList.remove("show");
  $("mSave").onclick = saveChatModal;
  $("genPromptBtn").onclick = () => { $("mPrompt").value = buildPromptFromFields(); };

  applyTheme(localStorage.getItem("buttplugllm.theme") || "dark");
  $("themeBtn").onclick = () =>
    applyTheme(document.body.dataset.theme === "light" ? "dark" : "light");

  setInterval(refreshDevices, 8000);
}
document.addEventListener("DOMContentLoaded", init);
