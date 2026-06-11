/* Sidebar app (M4-4/M4-5) — คุยกับ daemon ตรง ๆ: HTTP + WS port 8797
   สี pill ตรงกับ Godot hud.gd — แก้ที่ PILL_COLORS ทั้งสองที่ถ้าเปลี่ยน */
"use strict";

// serve โดย daemon (same-origin) — fallback localhost เผื่อเปิดไฟล์ตรง ๆ ใน browser
const BASE = location.protocol.startsWith("http") ? "" : "http://localhost:8797";
const WS_URL = "ws://" + (location.host || "localhost:8797") + "/ws";
const RECONNECT_MS = 3000;
const FEED_MAX_LINES = 200;

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
    card.innerHTML =
      `<span class="avatar">${esc(a.avatar)}</span>` +
      `<span class="info"><div class="name">${esc(a.name)}</div>` +
      `<div class="role">${esc(a.role)} · ${esc(a.llm.model)}</div></span>` +
      `<span class="pill" id="pill-${a.id}"></span>`;
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

async function hireAgent() {
  const name = document.getElementById("h-name").value.trim();
  const role = document.getElementById("h-role").value.trim();
  if (!name || !role) return;
  const payload = {
    name, role,
    avatar: document.getElementById("h-avatar").value.trim() || "🤖",
    color: document.getElementById("h-color").value,
    keywords: document.getElementById("h-keywords").value
      .split(",").map(s => s.trim()).filter(Boolean),
  };
  const res = await fetch(BASE + "/agents", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (res.ok) {
    feedLine("done", `จ้าง ${name} เข้าทีมแล้ว`);
    document.getElementById("hire-backdrop").classList.add("hidden");
    loadAgents();
  } else {
    feedLine("error", `จ้างไม่สำเร็จ (${res.status})`);
  }
}

/* ---------- terminal (M4-5) ---------- */

function feedLine(cls, html) {
  const feed = document.getElementById("feed");
  const div = document.createElement("div");
  div.className = "ln " + cls;
  div.innerHTML = html;
  feed.appendChild(div);
  while (feed.children.length > FEED_MAX_LINES) feed.removeChild(feed.firstChild);
  feed.scrollTop = feed.scrollHeight;
}

async function submitTask() {
  const input = document.getElementById("task-input");
  const msg = input.value.trim();
  if (!msg) return;
  input.value = "";
  feedLine("user", `&gt; ${esc(msg)}`);
  try {
    const res = await fetch(BASE + "/task", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: msg }),
    });
    const data = await res.json();
    const cfg = Object.values(agents).find(a => a.name === data.agent);
    const model = cfg ? cfg.llm.model : "?";
    feedLine("route", `→ มอบงานให้ <b>${esc(data.agent)}</b> (${esc(model)})`);
  } catch (e) {
    feedLine("error", "ส่ง task ไม่ได้ — daemon เปิดอยู่ไหม?");
  }
}

/* QA hook — host.py --qa-task เรียกผ่าน evaluate_js เพื่อทดสอบ path จริง */
function qaSubmit(text) {
  document.getElementById("task-input").value = text;
  submitTask();
}

/* ---------- WebSocket (realtime) ---------- */

let qaFired = false;

function runQaHooks() {
  // QA hooks จาก host.py --qa-task / --qa-toggle (ส่งมาทาง query param)
  if (qaFired) return;
  qaFired = true;
  const q = new URLSearchParams(location.search);
  if (q.get("qa_task")) setTimeout(() => qaSubmit(q.get("qa_task")), 1500);
  if (q.get("qa_toggle")) {
    setTimeout(toggleSidebar, 3000);
    setTimeout(toggleSidebar, 6000);
  }
}

function connectWs() {
  ws = new WebSocket(WS_URL);
  ws.onopen = () => {
    setDaemonDot(true);
    feedLine("done", "เชื่อมต่อ daemon แล้ว");
    loadAgents().then(runQaHooks);
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
      break;
  }
}

/* ---------- collapse (M4-3) ---------- */

function toggleSidebar() {
  collapsed = !collapsed;
  document.body.classList.toggle("collapsed", collapsed);
  // แจ้ง host ผ่าน daemon ให้ resize หน้าต่าง (ไม่ใช้ js_api bridge — ดู host.py)
  fetch(BASE + "/event", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type: "sidebar.toggle", data: { expanded: !collapsed } }),
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
