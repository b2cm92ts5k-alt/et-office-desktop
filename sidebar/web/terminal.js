/* Terminal Chat — หน้าต่างแยก OS-level (M6-4/M6-5)
   คุยกับ daemon ตรง ๆ เหมือน panel หลัก — ลากย้ายผ่าน drag region,
   ปรับขนาดผ่านมุมจับ #grip → ส่ง terminal.resize ผ่าน daemon ให้ host ปรับ window
   (ไม่ใช้ js_api bridge ตาม ADR M4-1) */
"use strict";

const BASE = location.protocol.startsWith("http") ? "" : "http://localhost:8797";
const WS_URL = "ws://" + (location.host || "localhost:8797") + "/ws";
const RECONNECT_MS = 3000;
const FEED_MAX_LINES = 400;
const MIN_W = 300, MIN_H = 220;   // ต้องตรงกับ TERMINAL_MIN ใน host.py

let agents = {};
let ws = null;

/* ---------- feed ---------- */

function feedLine(cls, html) {
  const feed = document.getElementById("feed");
  const div = document.createElement("div");
  div.className = "ln " + cls;
  div.innerHTML = html;
  feed.appendChild(div);
  while (feed.children.length > FEED_MAX_LINES) feed.removeChild(feed.firstChild);
  feed.scrollTop = feed.scrollHeight;
}

async function loadAgents() {
  try {
    const list = await (await fetch(BASE + "/agents")).json();
    agents = {};
    for (const a of list) agents[a.id] = a;
  } catch { /* daemon down — WS reconnect จะโหลดใหม่เอง */ }
}

function nameOf(agentId) {
  return agents[agentId] ? agents[agentId].name : agentId;
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
  } catch {
    feedLine("error", "ส่ง task ไม่ได้ — daemon เปิดอยู่ไหม?");
  }
}

/* QA hook — host.py --qa-task ส่ง query param มาที่หน้าต่างนี้ */
function qaSubmit(text) {
  document.getElementById("task-input").value = text;
  submitTask();
}

function collapseAll() {
  // เส้นเดียวกับปุ่มหุบบน panel หลัก — host หุบทั้งสองหน้าต่างพร้อมกัน (M6-5)
  fetch(BASE + "/event", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type: "sidebar.toggle", data: { expanded: false } }),
  }).catch(() => {});
}

/* ---------- WebSocket ---------- */

let qaFired = false;

function connectWs() {
  ws = new WebSocket(WS_URL);
  ws.onopen = () => {
    document.getElementById("daemon-dot").className = "dot on pywebview-drag-region";
    feedLine("done", "เชื่อมต่อ daemon แล้ว");
    loadAgents().then(() => {
      if (qaFired) return;
      qaFired = true;
      const q = new URLSearchParams(location.search);
      if (q.get("qa_task")) setTimeout(() => qaSubmit(q.get("qa_task")), 1500);
    });
  };
  ws.onclose = () => {
    document.getElementById("daemon-dot").className = "dot off pywebview-drag-region";
    setTimeout(connectWs, RECONNECT_MS);
  };
  ws.onmessage = (m) => {
    let ev;
    try { ev = JSON.parse(m.data); } catch { return; }
    if (ev.replay) return;
    handleEvent(ev);
  };
}

function handleEvent(ev) {
  const d = ev.data || {};
  switch (ev.type) {
    case "agent.created":
    case "agent.deleted":
      loadAgents(); // ชื่อ/model ใน route line ต้องสดเสมอ
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
      feedLine("social", `💡 ข้อเสนอใหม่: <b>${esc(trim(d.title, 150))}</b> — Approve/Reject ใน panel หลัก`);
      break;
    case "permission.request":
      feedLine("route", `🔐 ${esc(d.agent_name || "")} ขอ: ${esc(d.summary)} — ตอบใน panel หลัก`);
      break;
    case "permission.auto":
      feedLine("route", `⚙ ${esc(d.agent_name || "")}: ${esc(d.summary)} (อนุมัติยกชุด)`);
      break;
  }
}

/* ---------- resize grip (M6-4) ---------- */

const grip = document.getElementById("grip");
let rs = null; // resize state

grip.addEventListener("pointerdown", (e) => {
  rs = { sx: e.screenX, sy: e.screenY, w: window.innerWidth, h: window.innerHeight, last: 0 };
  grip.setPointerCapture(e.pointerId);
  e.preventDefault();
});

grip.addEventListener("pointermove", (e) => {
  if (!rs) return;
  const now = Date.now();
  if (now - rs.last < 80) return; // throttle — เดินทางผ่าน daemon ทุกครั้ง
  rs.last = now;
  postResize(e);
});

grip.addEventListener("pointerup", (e) => {
  if (rs) postResize(e); // ขนาดสุดท้ายเป๊ะ ๆ
  rs = null;
});

function postResize(e) {
  const w = Math.max(MIN_W, rs.w + (e.screenX - rs.sx));
  const h = Math.max(MIN_H, rs.h + (e.screenY - rs.sy));
  fetch(BASE + "/event", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ type: "terminal.resize", data: { w, h } }),
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
