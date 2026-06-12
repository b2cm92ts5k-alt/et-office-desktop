/* Sidebar app (M4-4/M4-5) — คุยกับ daemon ตรง ๆ: HTTP + WS port 8797
   สี pill ตรงกับ Godot hud.gd — แก้ที่ PILL_COLORS ทั้งสองที่ถ้าเปลี่ยน */
"use strict";

// serve โดย daemon (same-origin) — fallback localhost เผื่อเปิดไฟล์ตรง ๆ ใน browser
const BASE = location.protocol.startsWith("http") ? "" : "http://localhost:8797";
const WS_URL = "ws://" + (location.host || "localhost:8797") + "/ws";
const RECONNECT_MS = 3000;

const PILL_COLORS = {
  idle: "#8a8a9a", working: "#00e5ff", thinking: "#b060f0",
  collab: "#ff4da6", break: "#ff6030", sleep: "#4080ff",
};

let agents = {};        // id -> agent config
let collapsed = false;
let ws = null;

// JS error ใด ๆ โผล่ใน feed — ดีบักได้โดยไม่ต้องเปิด devtools
window.onerror = (msg, src, line) => {
  feedLine("error", `JS: ${esc(msg)} (${esc(String(src).split("/").pop())}:${line})`);
};

/* ---------- agents (M4-4) ---------- */

async function loadAgents() {
  try {
    const res = await fetch(BASE + "/agents");
    const list = await res.json();
    agents = {};
    for (const a of list) agents[a.id] = a;
    renderAgents();
    feedLine("ln", `โหลด ${list.length} agents`);
  } catch (e) {
    feedLine("error", `โหลด agents ไม่ได้: ${esc(e.message || e)}`);
  }
}

function renderAgents() {
  const el = document.getElementById("agent-list");
  el.innerHTML = "";
  for (const a of Object.values(agents)) {
    const card = document.createElement("div");
    card.className = "agent-card";
    card.style.setProperty("--ac", a.color);
    const cloud = a.llm.provider !== "ollama" ? "☁ " : "";
    card.innerHTML =
      `<span class="avatar">${esc(a.avatar)}</span>` +
      `<span class="info"><div class="name">${esc(a.name)}</div>` +
      `<div class="role">${esc(a.role)} · ${cloud}${esc(a.llm.model)}</div></span>` +
      `<span class="pill" id="pill-${a.id}"></span>` +
      `<button class="ghost gear" title="เลือก model" onclick="openModelPicker('${a.id}')">⚙</button>` +
      `<button class="ghost fire" title="ไล่ออก" onclick="openFire('${a.id}')">✖</button>`;
    el.appendChild(card);
    setPill(a.id, a.status);
  }
}

function setPill(agentId, status) {
  const pill = document.getElementById("pill-" + agentId);
  if (!pill) return;
  if (agents[agentId]) agents[agentId].status = status;
  pill.textContent = status.toUpperCase();
  pill.style.background = PILL_COLORS[status] || PILL_COLORS.idle;
}

/* ---------- hire modal (M4-4) ---------- */

function openHire() { document.getElementById("hire-backdrop").classList.remove("hidden"); }
function closeHire(ev) {
  if (ev && ev.target.id !== "hire-backdrop") return; // คลิกในกล่องไม่ปิด
  document.getElementById("hire-backdrop").classList.add("hidden");
}

// สี aura อัตโนมัติ (M6-2 v2 — CEO เอา picker ออก): .md กำหนด color มา = ใช้ตามนั้น
// ไม่งั้นเลือกจาก palette ART-SPEC ตามชื่อ (ชื่อเดิมได้สีเดิมเสมอ)
const AURA_PALETTE = ["#e040fb", "#00e5ff", "#ff4da6", "#00ff9f", "#ffe040", "#ff6030"];

function autoColor(name) {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.codePointAt(0)) >>> 0;
  return AURA_PALETTE[h % AURA_PALETTE.length];
}

async function hireAgent() {
  // มี role .md → parse รอบสุดท้ายก่อน (sync ฟอร์ม + system_prompt ให้ตรงเนื้อหาล่าสุด)
  const mdText = document.getElementById("h-md-text").value.trim();
  if (mdText && !(await parseRoleText())) return; // parse ไม่ผ่าน — สถานะโชว์ใน modal แล้ว
  const name = document.getElementById("h-name").value.trim();
  const role = document.getElementById("h-role").value.trim();
  if (!name || !role) return;
  const payload = {
    name, role,
    avatar: document.getElementById("h-avatar").value.trim() || "🤖",
    color: hireRoleColor || autoColor(name),
    keywords: document.getElementById("h-keywords").value
      .split(",").map(s => s.trim()).filter(Boolean),
    system_prompt: mdText ? hireRolePrompt : "",
    sprite: hireSprite,
  };
  const res = await fetch(BASE + "/agents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (res.ok) {
    feedLine("done", `จ้าง ${name} เข้าทีมแล้ว${mdText ? " (พร้อม role .md)" : ""}`);
    if (mdText) {
      // เก็บ .md เข้าคลัง daemon/roles/ ให้ใช้ซ้ำได้ (M6-2)
      fetch(BASE + "/roles/save", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: name, text: mdText }),
      }).catch(() => {});
    }
    resetRoleBox();
    document.getElementById("hire-backdrop").classList.add("hidden");
    loadAgents();
  } else {
    feedLine("error", `จ้างไม่สำเร็จ (${res.status})`);
  }
}

/* ---------- hire role .md (M6-2/M6-3) ---------- */

let hireRolePrompt = ""; // system_prompt จาก .md ที่ parse ผ่านล่าสุด
let hireRoleColor = "";  // color จาก frontmatter .md (ว่าง = autoColor)
let hireSprite = "";     // ไฟล์ spritesheet ที่อัพโหลดแล้ว (M6-2 v2)

function roleUpload() { document.getElementById("h-md-file").click(); }

function roleEditor() {
  document.getElementById("h-md-text").classList.remove("hidden");
  document.getElementById("h-draft-row").classList.add("hidden");
}

function roleDraftRow() {
  document.getElementById("h-draft-row").classList.remove("hidden");
  document.getElementById("h-md-text").classList.remove("hidden");
}

function roleFileChosen(input) {
  const f = input.files && input.files[0];
  if (!f) return;
  const reader = new FileReader();
  reader.onload = () => {
    const ta = document.getElementById("h-md-text");
    ta.value = String(reader.result);
    ta.classList.remove("hidden");
    parseRoleText();
  };
  reader.readAsText(f);
  input.value = "";
}

async function parseRoleText() {
  // ใช้ POST /roles/upload เดิม (M1-10) — ห่อ text เป็นไฟล์เสมือนผ่าน FormData
  const text = document.getElementById("h-md-text").value.trim();
  const status = document.getElementById("h-role-status");
  if (!text) { hireRolePrompt = ""; status.textContent = ""; return null; }
  const fd = new FormData();
  fd.append("file", new File([text], "editor.md", { type: "text/markdown" }));
  try {
    const res = await fetch(BASE + "/roles/upload", { method: "POST", body: fd });
    if (!res.ok) throw new Error(res.status);
    const p = await res.json();
    if (p.name) document.getElementById("h-name").value = p.name;
    if (p.role) document.getElementById("h-role").value = p.role;
    if (p.keywords.length) document.getElementById("h-keywords").value = p.keywords.join(", ");
    if (p.avatar) document.getElementById("h-avatar").value = p.avatar;
    // เก็บ color เฉพาะตอน .md ระบุเอง — RolePreset default คือ cyan ถ้าใช้ตรง ๆ จะทับมั่ว
    hireRoleColor = /^---[\s\S]*?\bcolor\s*:/.test(text) ? p.color : "";
    hireRolePrompt = p.system_prompt || "";
    status.textContent = `✓ role พร้อม — ${p.name} · ${p.keywords.length} keywords · prompt ${hireRolePrompt.length} ตัวอักษร`;
    status.className = "role-status ok";
    return p;
  } catch {
    hireRolePrompt = "";
    hireRoleColor = "";
    status.textContent = "✗ parse .md ไม่ได้ — เช็ค format / daemon เปิดอยู่ไหม?";
    status.className = "role-status err";
    return null;
  }
}

/* ---------- custom spritesheet (M6-2 v2) ---------- */

function spriteUpload() { document.getElementById("h-sprite-file").click(); }

async function spriteFileChosen(input) {
  const f = input.files && input.files[0];
  input.value = "";
  if (!f) return;
  const status = document.getElementById("h-sprite-status");
  const fd = new FormData();
  fd.append("file", f);
  try {
    const res = await fetch(BASE + "/sprites/upload", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.status);
    hireSprite = data.file;
    const prev = document.getElementById("h-sprite-prev");
    prev.src = BASE + data.url;
    prev.classList.remove("hidden");
    status.textContent = `✓ ใช้ spritesheet ที่อัพโหลด (${esc(f.name)})`;
    status.className = "role-status ok";
  } catch (e) {
    hireSprite = "";
    status.textContent = `✗ ${esc(e.message || "อัพโหลดไม่สำเร็จ")}`;
    status.className = "role-status err";
  }
}

function roleTextTouched() {
  const status = document.getElementById("h-role-status");
  status.textContent = "แก้ไขแล้ว — จะ parse อีกครั้งตอนกด HIRE";
  status.className = "role-status";
}

async function draftRole() {
  const desc = document.getElementById("h-draft-desc").value.trim();
  const btn = document.getElementById("h-draft-btn");
  if (!desc) return;
  btn.disabled = true;
  btn.textContent = "กำลังร่าง…";
  try {
    const res = await fetch(BASE + "/roles/draft", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: desc }),
    });
    if (!res.ok) throw new Error(res.status);
    const data = await res.json();
    const ta = document.getElementById("h-md-text");
    ta.value = data.text;
    ta.classList.remove("hidden");
    await parseRoleText();
  } catch {
    feedLine("error", "AI ร่าง role ไม่สำเร็จ — Ollama/daemon เปิดอยู่ไหม?");
  }
  btn.disabled = false;
  btn.textContent = "ร่าง";
}

function resetRoleBox() {
  document.getElementById("h-md-text").value = "";
  document.getElementById("h-md-text").classList.add("hidden");
  document.getElementById("h-draft-row").classList.add("hidden");
  document.getElementById("h-draft-desc").value = "";
  document.getElementById("h-role-status").textContent = "";
  document.getElementById("h-sprite-status").textContent = "";
  document.getElementById("h-sprite-prev").classList.add("hidden");
  hireRolePrompt = "";
  hireRoleColor = "";
  hireSprite = "";
}

/* ---------- fire agent (M6-1) ---------- */

let fireId = null;

function openFire(agentId) {
  const a = agents[agentId];
  if (!a) return;
  fireId = agentId;
  document.getElementById("f-agent-name").textContent = a.name;
  document.getElementById("fire-backdrop").classList.remove("hidden");
}

function closeFire(ev) {
  if (ev && ev.target.id !== "fire-backdrop") return;
  document.getElementById("fire-backdrop").classList.add("hidden");
  fireId = null;
}

async function confirmFire() {
  if (!fireId) return;
  const name = nameOf(fireId);
  const res = await fetch(BASE + `/agents/${fireId}`, { method: "DELETE" });
  if (res.ok) {
    feedLine("ln", `ไล่ ${esc(name)} ออกจากทีมแล้ว`);
    loadAgents(); // WS agent.deleted refresh ซ้ำอยู่แล้ว — อันนี้กัน WS ช้า
  } else {
    feedLine("error", `ไล่ออกไม่สำเร็จ (${res.status})`);
  }
  document.getElementById("fire-backdrop").classList.add("hidden");
  fireId = null;
}

/* ---------- activity mini feed (M6-4 — terminal เต็มแยกไป terminal.html) ---------- */

const MINI_FEED_LINES = 4;

function feedLine(cls, html) {
  const feed = document.getElementById("mini-feed");
  if (!feed) return;
  const div = document.createElement("div");
  div.className = "ln " + cls;
  div.innerHTML = html;
  feed.appendChild(div);
  while (feed.children.length > MINI_FEED_LINES) feed.removeChild(feed.firstChild);
}

/* ---------- proposals (M4-7) ---------- */

async function loadProposals() {
  try {
    const res = await fetch(BASE + "/proposals?status=pending");
    renderProposals(await res.json());
  } catch { /* daemon down — WS reconnect จะเรียกซ้ำเอง */ }
}

function renderProposals(list) {
  const el = document.getElementById("proposal-list");
  const badge = document.getElementById("prop-count");
  el.innerHTML = "";
  badge.classList.toggle("hidden", list.length === 0);
  badge.textContent = list.length;
  if (list.length === 0) {
    el.innerHTML = '<div class="empty-note">ยังไม่มีข้อเสนอจากทีม</div>';
    return;
  }
  for (const p of list) {
    const names = (p.proposed_by || []).map(nameOf).join(" + ");
    const card = document.createElement("div");
    card.className = "proposal-card";
    card.innerHTML =
      `<div class="p-title">💡 ${esc(p.title)}</div>` +
      (p.detail ? `<div class="p-detail">${esc(trim(p.detail, 280))}</div>` : "") +
      (names ? `<div class="p-by">โดย ${esc(names)}</div>` : "") +
      `<div class="p-actions">` +
      `<button class="neon-btn ok" onclick="respondProposal('${p.id}','approve')">✓ APPROVE</button>` +
      `<button class="ghost no" onclick="respondProposal('${p.id}','reject')">✗ REJECT</button>` +
      `</div>`;
    el.appendChild(card);
  }
}

async function respondProposal(id, action) {
  const res = await fetch(BASE + "/proposals/respond", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ proposal_id: id, action }),
  });
  if (res.ok) {
    feedLine(action === "approve" ? "done" : "ln",
      action === "approve" ? "✓ อนุมัติข้อเสนอ — ทีมเริ่มงานแล้ว" : "ปัดตกข้อเสนอแล้ว");
  } else {
    feedLine("error", `ตอบข้อเสนอไม่สำเร็จ (${res.status})`);
  }
  loadProposals();
}

/* ---------- settings (M4-6) ---------- */

let settingsOpen = false;

function toggleSettings() {
  settingsOpen = !settingsOpen;
  document.getElementById("settings-body").classList.toggle("hidden", !settingsOpen);
  document.getElementById("settings-arrow").textContent = settingsOpen ? "▾" : "▸";
  if (settingsOpen) loadSettings();
  saveUiState();
}

let keyStatus = {};

async function loadSettings() {
  try {
    const vram = await (await fetch(BASE + "/system/vram")).json();
    document.getElementById("vram-info").textContent =
      `VRAM: ${vram.vram_gb} GB → แนะนำ ${vram.recommended.qwen}`;
    keyStatus = await (await fetch(BASE + "/settings/apikey")).json();
    renderKeyStatus();
    const soc = await (await fetch(BASE + "/settings/social")).json();
    document.getElementById("soc-enabled").checked = !!soc.social_enabled;
    document.getElementById("soc-chance").value = soc.social_chance;
    document.getElementById("soc-cooldown").value = Math.round(soc.proposal_cooldown_sec / 60);
    const ws = await (await fetch(BASE + "/settings/workspace")).json();
    document.getElementById("ws-path").value = ws.path;
    renderWsStatus(ws);
  } catch {
    feedLine("error", "โหลด settings ไม่ได้");
  }
}

/* ---------- workspace (M6-6) ---------- */

function renderWsStatus(ws) {
  const el = document.getElementById("ws-status");
  if (!ws.path) {
    el.textContent = "ยังไม่ได้ตั้ง — agent ตอบแชทอย่างเดียว ไม่แตะไฟล์";
  } else {
    el.textContent = ws.valid
      ? "✓ ทีมทำงานในโฟลเดอร์นี้ (ทุก action ขออนุญาตก่อนเสมอ)"
      : "✗ โฟลเดอร์นี้หายไปแล้ว — agent จะใช้ tool ไม่ได้";
  }
}

async function saveWorkspace() {
  const path = document.getElementById("ws-path").value.trim();
  const res = await fetch(BASE + "/settings/workspace", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path }),
  });
  if (res.ok) {
    renderWsStatus(await res.json());
    feedLine("done", path ? `workspace → ${esc(path)}` : "ปิด workspace แล้ว");
  } else {
    const err = await res.json().catch(() => ({}));
    document.getElementById("ws-status").textContent = `✗ ${err.detail || "บันทึกไม่สำเร็จ"}`;
    feedLine("error", esc(err.detail || "ตั้ง workspace ไม่สำเร็จ"));
  }
}

/* ---------- permission dialog (M6-8) ---------- */

let permQueue = [];

async function loadPermissions() {
  try {
    permQueue = await (await fetch(BASE + "/permissions")).json();
    renderPerm();
  } catch { /* daemon down — reconnect แล้วโหลดใหม่ */ }
}

function pushPerm(info) {
  if (!permQueue.some(p => p.request_id === info.request_id)) permQueue.push(info);
  renderPerm();
}

function renderPerm() {
  const bd = document.getElementById("perm-backdrop");
  if (permQueue.length === 0) {
    bd.classList.add("hidden");
    return;
  }
  const p = permQueue[0];
  document.getElementById("perm-agent").textContent =
    `${p.agent_name || p.agent_id} · task ${String(p.task_id).slice(0, 6)}`;
  document.getElementById("perm-summary").textContent = p.summary;
  const detail = document.getElementById("perm-detail");
  detail.textContent = p.detail || "";
  detail.classList.toggle("hidden", !p.detail);
  document.getElementById("perm-queue").textContent =
    permQueue.length > 1 ? `รออีก ${permQueue.length - 1} คำขอ` : "";
  bd.classList.remove("hidden");
}

async function respondPerm(decision) {
  const p = permQueue.shift();
  renderPerm();
  if (!p) return;
  try {
    await fetch(BASE + "/permissions/respond", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ request_id: p.request_id, decision }),
    });
  } catch { /* daemon จะ deny เองตอน timeout */ }
  const labels = { approve: "✓ อนุญาต", deny: "✗ ปฏิเสธ", approve_task: "✓✓ อนุญาตทั้ง task" };
  feedLine(decision === "deny" ? "error" : "done", `${labels[decision]}: ${esc(p.summary)}`);
}

function renderKeyStatus() {
  document.getElementById("key-status").innerHTML =
    ["claude", "gemini", "openai"].map(p => {
      const on = keyStatus[p];
      return `<span class="key-chip ${on ? "on" : ""}">${p}: ${on ? "✓ set" : "—"}</span>`;
    }).join(" ");
}

async function saveKey() {
  const provider = document.getElementById("key-provider").value;
  const key = document.getElementById("key-value").value.trim();
  if (!key) return;
  const res = await fetch(BASE + "/settings/apikey", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider, key }),
  });
  if (res.ok) {
    document.getElementById("key-value").value = "";
    keyStatus[provider] = true;
    renderKeyStatus();
    feedLine("done", `บันทึก ${provider} key แล้ว (เก็บใน .env เครื่องนี้เท่านั้น)`);
  } else {
    feedLine("error", `บันทึก key ไม่สำเร็จ (${res.status})`);
  }
}

async function saveSocial() {
  const payload = {
    social_enabled: document.getElementById("soc-enabled").checked,
    social_chance: parseFloat(document.getElementById("soc-chance").value) || 0,
    proposal_cooldown_sec: (parseFloat(document.getElementById("soc-cooldown").value) || 0) * 60,
  };
  const res = await fetch(BASE + "/settings/social", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  feedLine(res.ok ? "done" : "error",
    res.ok ? "บันทึกค่า social loop แล้ว" : "บันทึกไม่สำเร็จ");
}

/* ---------- atmosphere picker (M4-10) ---------- */

const ATMO_LABELS = { auto: "ตามเวลาจริง", dawn: "🌅 DAWN", day: "☀️ CYBER DAY",
                      golden: "🌆 GOLDEN NEON", night: "🌙 DEEP NIGHT" };

async function setAtmosphere(mode) {
  try {
    await fetch(BASE + "/event", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: "atmosphere.set", data: { mode } }),
    });
    for (const b of document.querySelectorAll("#atmo-row .atmo"))
      b.classList.toggle("on", b.dataset.mode === mode);
    feedLine("ln", `บรรยากาศ wallpaper → ${ATMO_LABELS[mode] || mode}`);
  } catch {
    feedLine("error", "เปลี่ยนบรรยากาศไม่ได้ — daemon เปิดอยู่ไหม?");
  }
}

/* ---------- model picker (M4-6) ---------- */

const DEFAULT_MODELS = {
  ollama: "qwen3:8b", claude: "claude-sonnet-4-6",
  gemini: "gemini-2.0-flash", openai: "gpt-4o",
};
let pickerAgentId = null;

function openModelPicker(agentId) {
  const a = agents[agentId];
  if (!a) return;
  pickerAgentId = agentId;
  document.getElementById("m-agent-name").textContent = a.name;
  document.getElementById("m-provider").value = a.llm.provider;
  document.getElementById("m-model").value = a.llm.model;
  onProviderChange();
  document.getElementById("model-backdrop").classList.remove("hidden");
}

function closeModelPicker(ev) {
  if (ev && ev.target.id !== "model-backdrop") return;
  document.getElementById("model-backdrop").classList.add("hidden");
  pickerAgentId = null;
}

function onProviderChange() {
  const p = document.getElementById("m-provider").value;
  document.getElementById("m-model").value = DEFAULT_MODELS[p] || "";
  // เตือนถ้าเลือก cloud แต่ยังไม่ตั้ง key (status โหลดตอนเปิด settings — โหลดสดถ้ายังไม่มี)
  const warn = document.getElementById("m-key-warn");
  if (p === "ollama") { warn.classList.add("hidden"); return; }
  const show = () => warn.classList.toggle("hidden", !!keyStatus[p]);
  if (Object.keys(keyStatus).length === 0) {
    fetch(BASE + "/settings/apikey").then(r => r.json()).then(s => { keyStatus = s; show(); });
  } else { show(); }
}

async function saveModel() {
  if (!pickerAgentId) return;
  const llm = {
    provider: document.getElementById("m-provider").value,
    model: document.getElementById("m-model").value.trim(),
  };
  const res = await fetch(BASE + `/agents/${pickerAgentId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ llm }),
  });
  if (res.ok) {
    feedLine("done", `เปลี่ยน model เป็น ${esc(llm.provider)}/${esc(llm.model)}`);
    document.getElementById("model-backdrop").classList.add("hidden");
    loadAgents();
  } else {
    feedLine("error", `เปลี่ยน model ไม่สำเร็จ (${res.status})`);
  }
}

/* ---------- WebSocket (realtime) ---------- */

let qaFired = false;
let uiRestored = false;

function runQaHooks() {
  // QA hooks จาก host.py --qa-toggle/--qa-settings (qa_task ย้ายไป terminal.html — M6-4)
  if (qaFired) return;
  qaFired = true;
  const q = new URLSearchParams(location.search);
  if (q.get("qa_toggle")) {
    setTimeout(toggleSidebar, 3000);
    setTimeout(toggleSidebar, 6000);
  }
  if (q.get("qa_settings")) setTimeout(toggleSettings, 1500);
}

function connectWs() {
  ws = new WebSocket(WS_URL);
  ws.onopen = () => {
    setDaemonDot(true);
    feedLine("done", "เชื่อมต่อ daemon แล้ว");
    loadAgents().then(runQaHooks);
    loadProposals();
    loadPermissions(); // คำขอที่ค้างระหว่าง sidebar ปิดอยู่ (M6-8)
    if (!uiRestored) { uiRestored = true; restoreUiState(); }
  };
  ws.onclose = () => {
    setDaemonDot(false);
    setTimeout(connectWs, RECONNECT_MS);
  };
  ws.onmessage = (m) => {
    let ev;
    try { ev = JSON.parse(m.data); } catch { return; }
    if (ev.replay) return;
    handleEvent(ev);
  };
}

function setDaemonDot(on) {
  for (const id of ["daemon-dot", "strip-dot"]) {
    const el = document.getElementById(id);
    el.classList.toggle("on", on);
    el.classList.toggle("off", !on);
  }
}

function nameOf(agentId) {
  return agents[agentId] ? agents[agentId].name : agentId;
}

function handleEvent(ev) {
  const d = ev.data || {};
  switch (ev.type) {
    case "agent.status":
      setPill(d.agent_id, d.status);
      break;
    case "agent.created":
    case "agent.deleted":
      loadAgents();
      break;
    case "task.completed":
      feedLine("done", `✔ <b>${esc(nameOf(d.agent_id))}</b>: ${esc(trim(d.output, 400))}`);
      break;
    case "task.failed":
      feedLine("error", `✘ ${esc(nameOf(d.agent_id))}: ${esc(trim(d.error, 200))}`);
      break;
    case "social.meetup":
      feedLine("social", `☕ ${esc((d.names || []).join(" × "))} จับคู่คุยกัน`);
      break;
    case "social.chat":
      feedLine("social", `💬 ${esc(nameOf(d.agent_id))}: ${esc(trim(d.text, 200))}`);
      break;
    case "proposal.created":
      feedLine("social", `💡 ข้อเสนอใหม่: <b>${esc(trim(d.title, 150))}</b>`);
      loadProposals();
      break;
    case "proposal.approved":   // ตอบจาก client อื่น (API/เครื่องอื่น) ก็ต้อง refresh
    case "proposal.rejected":
      loadProposals();
      break;
    case "permission.request":
      pushPerm(d);
      break;
    case "permission.resolved":
      // ตอบจากที่อื่น/timeout — เอาออกจากคิวถ้ายังค้างอยู่
      permQueue = permQueue.filter(p => p.request_id !== d.request_id);
      renderPerm();
      break;
    case "permission.auto":
      feedLine("route", `⚙ ${esc(d.agent_name || "")}: ${esc(d.summary)} (อนุมัติยกชุด)`);
      break;
    case "qa.ping":
      postQaReport();  // QA gate M4-11 ขอ snapshot สถานะ DOM
      break;
    case "wallpaper.conflict": {
      const apps = (d.apps || []).join(", ");
      feedLine(d.paused ? "ln" : "error", d.paused
        ? `⏸ pause ${esc(apps)} ให้ชั่วคราวแล้ว (คืนให้ตอนปิด ET Office)`
        : `⚠ พบ ${esc(apps)} กำลังวาดทับ wallpaper — ปิดเองก่อนใช้ ET Office`);
      break;
    }
    case "sidebar.toggle": {
      // มาจาก system tray (M4-8) — sync CSS ของหน้าให้ตรงกับขนาดหน้าต่าง
      const expanded = !!(d.expanded ?? true);
      collapsed = !expanded;
      document.body.classList.toggle("collapsed", collapsed);
      saveUiState();
      break;
    }
  }
}

/* ---------- collapse (M4-3) + state persistence (M4-11) ---------- */

function toggleSidebar() {
  collapsed = !collapsed;
  document.body.classList.toggle("collapsed", collapsed);
  saveUiState();
  // แจ้ง host ผ่าน daemon ให้ resize หน้าต่าง (ไม่ใช้ js_api bridge — ดู host.py)
  fetch(BASE + "/event", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type: "sidebar.toggle", data: { expanded: !collapsed } }),
  }).catch(() => {});
}

/* ปิด-เปิดแล้ว state คืนได้ (M4-11) — ต้องรัน pywebview แบบ private_mode=False */

function saveUiState() {
  try {
    localStorage.setItem("et_sidebar_state",
      JSON.stringify({ collapsed, settingsOpen }));
  } catch { /* storage ใช้ไม่ได้ (private mode) — ข้าม */ }
}

function restoreUiState() {
  let st = null;
  try { st = JSON.parse(localStorage.getItem("et_sidebar_state")); } catch {}
  if (!st) return;
  if (st.settingsOpen) toggleSettings();
  if (st.collapsed) {
    collapsed = true;
    document.body.classList.add("collapsed");
    // sync ขนาดหน้าต่างกับ host (รอ WS listener ของ host พร้อมก่อนสักนิด)
    setTimeout(() => fetch(BASE + "/event", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type: "sidebar.toggle", data: { expanded: false } }),
    }).catch(() => {}), 1200);
  }
}

/* ---------- QA self-report (M4-11) ---------- */

function postQaReport() {
  const pills = {};
  for (const id of Object.keys(agents)) {
    const el = document.getElementById("pill-" + id);
    if (el) pills[id] = el.textContent.toLowerCase();
  }
  const snap = {
    agents_rendered: document.querySelectorAll(".agent-card").length,
    proposals_rendered: document.querySelectorAll(".proposal-card").length,
    feed_lines: (document.getElementById("mini-feed") || { children: [] }).children.length,
    collapsed,
    settings_open: settingsOpen,
    vram_text: document.getElementById("vram-info").textContent,
    pills,
  };
  fetch(BASE + "/event", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type: "qa.sidebar", data: snap }),
  }).catch(() => {});
}

/* ---------- utils ---------- */

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g,
    c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function trim(s, n) {
  s = String(s ?? "").replace(/\s+/g, " ").trim();
  return s.length > n ? s.slice(0, n) + "…" : s;
}

connectWs();
