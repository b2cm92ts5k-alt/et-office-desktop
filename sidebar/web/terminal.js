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
let attached = [];   // ไฟล์ที่ลากใส่ รอแนบ task ถัดไป (M9-2)

/* ---------- drag & drop ไฟล์ (M9-2) ---------- */

let dragDepth = 0;

function initDrop() {
  const hint = document.getElementById("drop-hint");
  window.addEventListener("dragover", (e) => { e.preventDefault(); });
  window.addEventListener("dragenter", (e) => {
    if (![...(e.dataTransfer?.types || [])].includes("Files")) return;
    e.preventDefault();
    dragDepth++;
    hint.classList.add("on");
  });
  window.addEventListener("dragleave", (e) => {
    e.preventDefault();
    if (--dragDepth <= 0) { dragDepth = 0; hint.classList.remove("on"); }
  });
  window.addEventListener("drop", async (e) => {
    e.preventDefault();
    dragDepth = 0;
    hint.classList.remove("on");
    const files = [...(e.dataTransfer?.files || [])];
    for (const f of files) await uploadDropped(f);
  });
}

function pickFiles() { document.getElementById("file-input").click(); }

async function filesPicked(input) {
  const files = [...(input.files || [])];
  for (const f of files) await uploadDropped(f);
  input.value = "";   // reset เผื่อเลือกไฟล์เดิมซ้ำ
}

async function uploadDropped(file) {
  const fd = new FormData();
  fd.append("file", file);
  feedLine("ln", `📎 กำลังแนบ ${esc(file.name)}…`);
  try {
    const res = await fetch(BASE + "/files/drop", { method: "POST", body: fd });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      attached.push({ name: data.name, rel: data.rel });
      renderAttached();
      feedLine("done", `📎 แนบ ${esc(data.name)} แล้ว — พิมพ์สั่งทีมให้ดูไฟล์ได้เลย`);
    } else {
      feedLine("error", `แนบไม่ได้: ${esc(data.detail || "workspace ยังไม่ได้ตั้งใน Settings?")}`);
    }
  } catch {
    feedLine("error", "แนบไฟล์ไม่ได้ — daemon เปิดอยู่ไหม?");
  }
}

function renderAttached() {
  const box = document.getElementById("attached");
  if (!attached.length) { box.classList.add("hidden"); box.innerHTML = ""; return; }
  box.classList.remove("hidden");
  box.innerHTML = attached.map((a, i) =>
    `<span class="att-chip">📎 ${esc(a.name)} <button onclick="removeAttached(${i})" title="เอาออก">✕</button></span>`
  ).join("");
}

function removeAttached(i) {
  attached.splice(i, 1);
  renderAttached();
}

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
  // แนบ path ไฟล์ที่ลากใส่เข้า context ให้ agent อ่านต่อ (อยู่ใน workspace แล้ว)
  const note = attached.length
    ? `[ไฟล์แนบใน workspace: ${attached.map(a => a.rel).join(", ")}]\n`
    : "";
  const sent = note + msg;
  feedLine("user", `&gt; ${esc(msg)}` + (attached.length ? ` <span class="att-inline">📎${attached.length}</span>` : ""));
  attached = [];
  renderAttached();
  try {
    const res = await fetch(BASE + "/task", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: sent }),
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

initDrop();
connectWs();
