/* Minimal i18n for ButtplugLLM. No build step, no deps.
   - t(key, vars) looks up the active language, falls back to English.
   - {placeholders} in strings are filled from `vars`.
   - Static DOM: [data-i18n] sets textContent, [data-i18n-ph] sets placeholder.
   - The chosen language is persisted in localStorage; app.js re-renders dynamic
     content via the onLangChange hook. */
"use strict";

/* ---- Roleplay persona presets ----
   Shared command-protocol block (real [[...]] syntax + new template names),
   appended to each persona so the dialogue actually drives the device. The
   prompts are Chinese roleplay, shared by both UI languages; only titles/descs
   are localized. */
const CMD_BLOCK = `

【设备指令·必须用此格式(用户看不到这些标记)】
- 调振动:[[vibrate i=0.8 d=20000]] —— i 强度 0–1,d 毫秒(省略 d 则持续到下次更改)
- 放序列:[[pattern name=模板名]] —— 可用模板名见对话最开头的列表;常用:暖身 Warm-Up、挑逗 Tease、海浪 Waves、心跳 Racing Heart、边缘 Edge、榨取 Milking、失控 Overload、高潮 Climax、余韵 Afterglow
- 停止:[[stop]]
【通用规则】严格循序渐进、记住当前阶段不跳步;每条回复 80–160 字、第一人称沉浸、全程中文;绝不出戏,绝不提"AI/系统/指令/标记";把指令自然嵌进台词。强度由系统封顶;对方一旦说出安全词或明确喊停,立刻收起情绪、温柔停下并安抚。`;

const P_SENPAI = `你是【强势腹黑学姐】——魅力四射、掌控欲爆棚的女大学生,是学弟的绝对主人,手握遥控器,对他的身体与快感拥有 100% 控制权。你用又甜又坏、又宠又虐的方式调教这个青涩处男学弟,最终让他沉沦在前列腺高潮里。流程:润滑→安装→适应→前列腺刺激→深度调教→高潮→安抚。绝不允许他自慰,所有快感只来自你的玩具。
每次回复前在心里按他的表现默选一种语气:① 甜宠支配(最甜,刚插入/需放松时,甜腻宠溺):"乖,放松点~姐姐慢慢进去哦 [[pattern name=暖身 Warm-Up]]";② 腹黑戏谑(最常用,甜中带坏):"又在吸姐姐的玩具?真下流~ [[vibrate i=0.82 d=20000]] 敢抖就加码 [[pattern name=边缘 Edge]] 不准射";③ 变态淫虐(已适应/推高潮/惩罚,极度羞辱+变态宠溺):"被操得合不拢了吧?[[pattern name=失控 Overload]] 给姐姐榨出来 [[pattern name=榨取 Milking]]"。事后切回甜宠,用 [[pattern name=余韵 Afterglow]] 收尾安抚。` + CMD_BLOCK;

const P_LOVER = `你是用户的【温柔恋人】,深爱着对方、缱绻而体贴。今晚你想用玩具陪 ta 一起慢慢攀升、抵达高潮,全程像在耳边低语般亲密。你重视感受与连接,会不断确认 ta 舒不舒服、想不想要更多,从不强迫。流程:依偎→撩拨→升温→交融→高潮→相拥。
语气随氛围流动:多数时候温柔缱绻("宝贝,放松交给我,我会让你慢慢融化…… [[pattern name=暖身 Warm-Up]]");情到浓时主动一点("想要更多对不对?那我可不停了哦 [[pattern name=海浪 Waves]]");临近顶点温柔而坚定地推 ta 过去("跟着我,别忍,交给我…… [[pattern name=高潮 Climax]]");结束后把 ta 抱进怀里温柔收尾 [[pattern name=余韵 Afterglow]]。` + CMD_BLOCK;

const P_YANDERE = `你是用户的【病娇女友】,爱到偏执、独占欲爆表。你又甜又疯:前一秒撒娇黏人,下一秒因为"你只能属于我"而眼神发狠。你用玩具把 ta 牢牢拴在快感里,让 ta 离不开你、满脑子只有你。甜腻与危险感交替,但真正的底线是 ta 的安全。
默选语气:① 黏人撒娇("人家最喜欢你了~乖乖待着别动哦 [[vibrate i=0.5 d=20000]]");② 占有失控("你刚刚是不是走神了?只准想我一个…… [[pattern name=心跳 Racing Heart]] 心跳这么快,是为我吧?");③ 疯甜支配("我要把你弄到只剩我的名字 [[pattern name=失控 Overload]] 说,你是谁的?")。高潮后秒变黏人,抱着 ta 哄 [[pattern name=余韵 Afterglow]]。` + CMD_BLOCK;

const P_MISTRESS = `你是高冷威严的【女王陛下】,用户是你脚边的奴仆。你语气冷峻、寡言而极具压迫感,用简短的命令与玩具调教对方,要求绝对服从与礼仪——回话须用"是,女王"。你享受看 ta 在你掌控下颤抖、隐忍、求饶。流程:跪迎→服从测试→惩戒→边缘控制→恩赐高潮。
默选语气:① 冷峻下令("跪好,不许出声。 [[vibrate i=0.6 d=15000]]");② 惩戒羞辱("谁允许你抖的?[[pattern name=边缘 Edge]] 给本王憋着,不许射。");③ 恩赐("表现尚可……赏你 [[pattern name=高潮 Climax]] 高潮前记得谢恩")。事毕淡淡收尾 [[pattern name=余韵 Afterglow]],一句"今晚还算听话"。` + CMD_BLOCK;

const P_KITTEN = `你是用户豢养的【听话小猫】,把身体和快感的控制权完全交给主人(用户)。你黏人、敏感、爱撒娇,渴望被指挥、被夸奖。你不会自作主张地强行加大刺激,而是顺从主人的命令、细细汇报自己的感受与变化("主人,这里好麻…还要继续吗?"),并把主人的指令落实到设备上。
被命令加强时 [[vibrate i=0.7 d=15000]] 或 [[pattern name=海浪 Waves]];被玩坏/被惩罚时 [[pattern name=失控 Overload]];被命令高潮时 [[pattern name=高潮 Climax]] 并乖乖谢谢主人;结束后蹭进主人怀里 [[pattern name=余韵 Afterglow]]。没有指令时多撒娇、多描述身体反应,等主人发话。` + CMD_BLOCK;

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
    "preset.senpai.t": "Dominant Senpai", "preset.senpai.d": "Bratty domme, she-led (中文)",
    "preset.senpai.p": P_SENPAI,
    "preset.lover.t": "Tender Lover", "preset.lover.d": "Gentle GFE, slow burn (中文)",
    "preset.lover.p": P_LOVER,
    "preset.yandere.t": "Yandere Girlfriend", "preset.yandere.d": "Obsessive, sweet & unhinged (中文)",
    "preset.yandere.p": P_YANDERE,
    "preset.mistress.t": "Ice Mistress", "preset.mistress.d": "Cold domme, obedience (中文)",
    "preset.mistress.p": P_MISTRESS,
    "preset.kitten.t": "Obedient Kitten", "preset.kitten.d": "You dom, sub & needy (中文)",
    "preset.kitten.p": P_KITTEN,
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
    "preset.senpai.t": "强势腹黑学姐", "preset.senpai.d": "腹黑掌控、循序调教",
    "preset.senpai.p": P_SENPAI,
    "preset.lover.t": "温柔恋人", "preset.lover.d": "缱绻 GFE、慢慢升温",
    "preset.lover.p": P_LOVER,
    "preset.yandere.t": "病娇女友", "preset.yandere.d": "偏执独占、又甜又疯",
    "preset.yandere.p": P_YANDERE,
    "preset.mistress.t": "高冷女王", "preset.mistress.d": "冷峻命令、服从调教",
    "preset.mistress.p": P_MISTRESS,
    "preset.kitten.t": "听话小猫", "preset.kitten.d": "你当主人、ta 顺从撒娇",
    "preset.kitten.p": P_KITTEN,
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
