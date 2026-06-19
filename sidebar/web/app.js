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
  if (Object.keys(agents).length === 0) {
    el.innerHTML = '<div class="empty-note">ยังไม่มี agent — กด <b>+ HIRE</b> เพื่อจ้างทีม</div>';
    return;
  }
  for (const a of Object.values(agents)) {
    const card = document.createElement("div");
    card.className = "agent-card";
    card.style.setProperty("--ac", a.color);
    const cloud = a.llm.provider !== "ollama" ? "☁ " : "";
    const crown = a.is_ceo ? '<span class="ceo-tag" title="CEO / ตัวคุณ">👑</span> ' : "";
    // CEO ไล่ออกไม่ได้ (เป็นตัวผู้ใช้เอง) — ซ่อนปุ่ม fire
    const fireBtn = a.is_ceo ? "" :
      `<button class="ghost fire" title="ไล่ออก" onclick="openFire('${a.id}')">✖</button>`;
    if (a.is_ceo) card.classList.add("ceo");
    card.innerHTML =
      `<span class="avatar">${esc(a.avatar)}</span>` +
      `<span class="info"><div class="name">${crown}${esc(a.name)}</div>` +
      `<div class="role">${esc(a.role)} · ${cloud}${esc(a.llm.model)}</div></span>` +
      `<span class="pill" id="pill-${a.id}"></span>` +
      `<button class="ghost gear" title="เลือก model" onclick="openModelPicker('${a.id}')">⚙</button>` +
      fireBtn;
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

async function openHire() {
  document.getElementById("hire-backdrop").classList.remove("hidden");
  const opts = await loadAvailableModels(true);
  const base = opts.find(o => o.recommended) || opts[0];
  fillModelSelect(document.getElementById("h-model"), opts,
    base ? { provider: base.provider, model: base.model } : null);
}
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
  const msel = document.getElementById("h-model");
  if (msel && msel.value) payload.llm = parseModelVal(msel.value);
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

// M11-7 — เปิด/ปิด reviewer (global)
async function saveReviewer() {
  const enabled = document.getElementById("reviewer-enabled").checked;
  try {
    await fetch(BASE + "/settings/reviewer", {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    });
    feedLine("done", enabled ? "เปิด Reviewer แล้ว" : "ปิด Reviewer แล้ว");
  } catch { feedLine("error", "ตั้ง reviewer ไม่สำเร็จ"); }
}

// M12-2 — ปิดระบบทั้งหมด (ยืนยัน 2 คลิกกันกดพลาด — pywebview ไม่พึ่ง confirm())
let _shutdownArmed = false;
async function shutdownSystem() {
  if (!_shutdownArmed) {
    _shutdownArmed = true;
    feedLine("error", "⚠ กดปุ่ม ⏻ อีกครั้งภายใน 4 วิ เพื่อยืนยันปิด ET Office");
    setTimeout(() => { _shutdownArmed = false; }, 4000);
    return;
  }
  _shutdownArmed = false;
  feedLine("route", "⏻ กำลังปิด ET Office (daemon + wallpaper + sidebar)…");
  try { await fetch(BASE + "/system/shutdown", { method: "POST" }); }
  catch { feedLine("error", "ส่งคำสั่งปิดไม่ได้ — daemon เปิดอยู่ไหม?"); }
}

async function loadSettings() {
  try {
    const vram = await (await fetch(BASE + "/system/vram")).json();
    document.getElementById("vram-info").textContent =
      `VRAM: ${vram.vram_gb} GB → แนะนำ ${vram.recommended}`;
    await loadKeys();   // M11-14 — โหลด key list (default .env + store)
    renderGithubStatus(await (await fetch(BASE + "/settings/github")).json());
    const soc = await (await fetch(BASE + "/settings/social")).json();
    document.getElementById("soc-enabled").checked = !!soc.social_enabled;
    document.getElementById("soc-chance").value = soc.social_chance;
    document.getElementById("soc-cooldown").value = Math.round(soc.proposal_cooldown_sec / 60);
    const ws = await (await fetch(BASE + "/settings/workspace")).json();
    document.getElementById("ws-path").value = ws.path;
    renderWsStatus(ws);
    const rev = await (await fetch(BASE + "/settings/reviewer")).json();   // M11-7
    document.getElementById("reviewer-enabled").checked = !!rev.enabled;
    loadModelCatalog();
    loadMcp();
    checkOllama();   // เปิด settings = จังหวะดีเช็ค ollama ซ้ำ (M5-5)
  } catch {
    feedLine("error", "โหลด settings ไม่ได้");
  }
}

/* ---------- MCP servers (M10-4) ---------- */

async function loadMcp() {
  try {
    const d = await (await fetch(BASE + "/mcp/servers")).json();
    renderMcp(d.servers || []);
  } catch { /* daemon down */ }
}

function renderMcp(servers) {
  const el = document.getElementById("mcp-list");
  if (!servers.length) { el.innerHTML = '<span class="empty-note">ยังไม่ได้เชื่อม MCP server</span>'; return; }
  el.innerHTML = servers.map(s =>
    `<div class="mcp-row"><span class="mcp-info"><b>${esc(s.name)}</b> <span class="mcp-stat">${esc(s.status)}</span>` +
    `<div class="mcp-cmd">${esc(s.command)}</div></span>` +
    `<button class="neon-btn sm danger" onclick="removeMcp('${esc(s.name)}')">ลบ</button></div>`
  ).join("");
}

async function addMcp() {
  const name = document.getElementById("mcp-name").value.trim();
  const command = document.getElementById("mcp-cmd").value.trim();
  if (!name || !command) return;
  document.getElementById("mcp-list").textContent = "กำลังเชื่อม…";
  try {
    const res = await fetch(BASE + "/mcp/servers", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, command }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      document.getElementById("mcp-name").value = "";
      document.getElementById("mcp-cmd").value = "";
      renderMcp(data.servers || []);
      feedLine("done", `เพิ่ม MCP server: ${esc(name)}`);
    } else {
      feedLine("error", esc(data.detail || "เพิ่ม MCP ไม่สำเร็จ"));
      loadMcp();
    }
  } catch { feedLine("error", "ติดต่อ daemon ไม่ได้"); }
}

async function removeMcp(name) {
  try {
    const res = await fetch(BASE + "/mcp/servers/" + encodeURIComponent(name), { method: "DELETE" });
    const data = await res.json().catch(() => ({}));
    renderMcp(data.servers || []);
    feedLine("done", `ลบ MCP server: ${esc(name)}`);
  } catch { feedLine("error", "ติดต่อ daemon ไม่ได้"); }
}

/* ---------- local model manager (M7-5) ---------- */

let modelCatalogData = null;
let pendingInstall = null;    // tag ที่รอ user ยืนยันก่อนติดตั้ง (consent inline — เลี่ยง window.confirm ที่ WebView2 มีปัญหา)
let pendingUninstall = null;

const MC_CAT = { coder: "💻 Coder", general: "💬 ทั่วไป", math: "🔢 Math", vision: "👁 Vision", multimodal: "🎬 Multimodal" };
const MC_ORDER = ["coder", "general", "math", "vision", "multimodal"];

function openModelsModal() {
  document.getElementById("models-backdrop").classList.remove("hidden");
  loadModelCatalog();
}

function closeModelsModal(ev) {
  if (ev && ev.target.id !== "models-backdrop") return;
  document.getElementById("models-backdrop").classList.add("hidden");
}

async function loadModelCatalog() {
  try {
    modelCatalogData = await (await fetch(BASE + "/models/catalog")).json();
    renderModelCatalog();
  } catch {
    document.getElementById("model-catalog").innerHTML =
      '<div class="empty-note">โหลดรายชื่อ model ไม่ได้ — Ollama รันอยู่ไหม?</div>';
  }
}

function renderModelMini() {
  const mini = document.getElementById("model-mini-status");
  if (!mini || !modelCatalogData) return;
  const active = modelCatalogData.active_local_model || "qwen3 (default)";
  const busy = modelCatalogData.team_busy
    ? " · ⛔ ทีมกำลังทำงาน สลับไม่ได้ตอนนี้"
    : "";
  mini.textContent = `🟢 local ${active} (agent ที่ตั้ง local ใช้ตัวนี้ทั้งหมด)${busy}`;
}

function renderModelCatalog() {
  const data = modelCatalogData;
  if (!data) return;
  const installing = data.installing;
  const hasApp = data.models.some(m => m.app_installed);
  const busy = !!data.team_busy;
  updateInstallBanner(installing, null, installing ? "กำลังติดตั้ง…" : null);
  const byCat = {};
  for (const m of data.models) (byCat[m.category] = byCat[m.category] || []).push(m);
  let html = "";
  for (const cat of MC_ORDER) {
    if (!byCat[cat]) continue;
    html += `<div class="mc-cat">${MC_CAT[cat] || cat}</div>`;
    for (const m of byCat[cat]) html += modelRow(m, installing, hasApp, busy);
  }
  document.getElementById("model-catalog").innerHTML = html;
  renderModelMini();
}

function modelRow(m, installing, hasApp, busy) {
  const rec = m.recommended ? '<span class="rec-badge">แนะนำ</span>' : "";
  const meta = `<span class="mc-meta">use${m.size_gb}GB · VRAM ต้อง ${m.min_vram_gb}GB</span>`;
  const active = modelCatalogData ? modelCatalogData.active_local_model : "";
  const onOllama = m.installed || m.app_installed;   // pull ไว้แล้ว → สลับได้ทันที (ไม่ต้อง pull)
  const delBtn = m.app_installed
    ? ` <button class="neon-btn sm danger" onclick="askUninstall('${m.tag}')">ลบ</button>` : "";
  let action;
  if (m.tag === installing) {
    action = '<span class="mc-state">กำลังลง…</span>';
  } else if (m.tag === active) {
    // ตัวที่ใช้อยู่ — โชว์ชัดว่า active (เคยขึ้นแค่ "มีอยู่แล้ว" จนงงว่าสลับได้ไหม)
    action = '<span class="mc-state ok">✓ ใช้อยู่</span>' + delBtn;
  } else if (busy) {
    action = '<span class="mc-state lock" title="ทีมกำลังทำงาน — รอว่างก่อนสลับ">⛔ ทีมทำงานอยู่</span>';
  } else if (installing) {
    action = '<button class="neon-btn sm" disabled>รอคิว</button>';
  } else if (pendingUninstall === m.tag) {
    action = `<span class="mc-confirm">กลับไปใช้ qwen3 default? <button class="neon-btn sm danger" onclick="doUninstall('${m.tag}')">ยืนยัน</button> <button class="neon-btn sm" onclick="cancelUninstall()">ไม่</button></span>`;
  } else if (onOllama) {
    // มีบน Ollama แล้วแต่ยังไม่ active → สลับมาใช้ทันทีผ่าน /models/activate (M13-1/2)
    action = `<button class="neon-btn sm" onclick="doActivate('${m.tag}')">สลับมาใช้</button>${delBtn}`;
  } else if (m.locked) {
    action = '<span class="mc-state lock">VRAM ไม่พอ</span>';
  } else if (hasApp) {
    action = '<button class="neon-btn sm" disabled title="ติดตั้งเพิ่มได้ครั้งละ 1 ตัว — ลบตัวที่ลงผ่านแอปก่อน">ติดตั้ง</button>';
  } else if (pendingInstall === m.tag) {
    action = `<span class="mc-confirm">(อย่าสลับตอนทีมทำงาน)? <button class="neon-btn sm" onclick="doInstall('${m.tag}')">ยืนยัน</button> <button class="neon-btn sm" onclick="cancelInstall()">ไม่</button></span>`;
  } else {
    // ยังไม่มีบน Ollama → ติดตั้ง (pull) แล้วสลับมาใช้
    action = `<button class="neon-btn sm" onclick="askInstall('${m.tag}')">ติดตั้ง + ใช้</button>`;
  }
  return `<div class="mc-row ${m.locked ? "locked" : ""}">` +
    `<div class="mc-info"><div class="mc-name">${esc(m.name)} ${rec}</div>` +
    `<div class="mc-desc">${esc(m.desc)}</div>${meta}</div>` +
    `<div class="mc-action">${action}</div></div>`;
}

function askInstall(tag) { pendingInstall = tag; pendingUninstall = null; renderModelCatalog(); }
function cancelInstall() { pendingInstall = null; renderModelCatalog(); }
function askUninstall(tag) { pendingUninstall = tag; pendingInstall = null; renderModelCatalog(); }
function cancelUninstall() { pendingUninstall = null; renderModelCatalog(); }

async function doInstall(tag) {
  pendingInstall = null;
  try {
    const res = await fetch(BASE + "/models/install", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tag }),
    });
    if (res.ok) {
      feedLine("route", `⬇ เริ่มติดตั้ง ${esc(tag)}…`);
      if (modelCatalogData) modelCatalogData.installing = tag;
      updateInstallBanner(tag, 0, "เริ่ม…");
      renderModelCatalog();
    } else {
      const e = await res.json().catch(() => ({}));
      feedLine("error", esc(e.detail || "ติดตั้งไม่สำเร็จ"));
      renderModelCatalog();
    }
  } catch {
    feedLine("error", "ติดต่อ daemon ไม่ได้");
  }
}

async function doActivate(tag) {
  // M13-1/2 — สลับ active local model ไปยังตัวที่มีบน Ollama แล้ว (ไม่ pull ใหม่)
  try {
    const res = await fetch(BASE + "/models/activate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tag }),
    });
    if (res.ok) {
      const j = await res.json().catch(() => ({}));
      if (j.changed === false) feedLine("ln", `${esc(tag)} เป็น model ที่ใช้อยู่แล้ว`);
      // ถ้า changed=true → daemon broadcast model.switched ซึ่ง refresh + แจ้ง feed ให้เอง
    } else {
      const e = await res.json().catch(() => ({}));
      feedLine("error", esc(e.detail || "สลับ model ไม่สำเร็จ"));
    }
    loadModelCatalog();
  } catch {
    feedLine("error", "ติดต่อ daemon ไม่ได้");
  }
}

async function doUninstall(tag) {
  pendingUninstall = null;
  try {
    const res = await fetch(BASE + "/models/uninstall", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tag }),
    });
    if (res.ok) feedLine("done", `🗑 ลบ ${esc(tag)} แล้ว`);
    else {
      const e = await res.json().catch(() => ({}));
      feedLine("error", esc(e.detail || "ลบไม่สำเร็จ"));
    }
    loadModelCatalog();
  } catch {
    feedLine("error", "ติดต่อ daemon ไม่ได้");
  }
}

function updateInstallBanner(tag, percent, status) {
  const b = document.getElementById("model-install-banner");
  if (!b) return;
  if (!tag) { b.classList.add("hidden"); return; }
  b.classList.remove("hidden");
  const pct = (percent != null) ? ` ${percent}%` : "";
  document.getElementById("mib-text").textContent = `กำลังติดตั้ง ${tag} — ${status || ""}${pct}`;
  if (percent != null) document.getElementById("mib-fill").style.width = percent + "%";
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
    ["claude", "gemini", "openai", "grok", "deepseek"].map(p => {
      const on = keyStatus[p];
      return `<span class="key-chip ${on ? "on" : ""}">${p}: ${on ? "✓ set" : "—"}</span>`;
    }).join(" ");
}

// M14 — บัญชี API key เก็บใน account_store (เข้ารหัส DPAPI) — ที่เดียว ผ่าน /accounts (เลิกใช้ legacy keys store)
let cloudKeys = [];
async function loadKeys() {
  try { cloudKeys = (await (await fetch(BASE + "/accounts")).json()).accounts || []; }
  catch { cloudKeys = []; }
  keyStatus = {};
  for (const k of cloudKeys) keyStatus[k.provider] = true;
  renderKeyStatus();
  const box = document.getElementById("keys-list");
  if (box) box.innerHTML = cloudKeys.length
    ? cloudKeys.map(k =>
        `<div class="key-item"><span class="key-chip on">${esc(k.provider)}</span> `
        + `${esc(k.label)} <code>${esc(k.masked)}</code> `
        + `<button class="ghost sm" onclick="deleteKey('${esc(k.id)}')">✕ ลบ</button></div>`).join("")
    : `<div class="dim">ยังไม่มี key</div>`;
}

async function deleteKey(id) {
  try {
    const res = await fetch(BASE + "/accounts/" + encodeURIComponent(id), { method: "DELETE" });
    if (res.ok) { feedLine("ln", "ลบ key แล้ว"); loadKeys(); }
    else feedLine("error", `ลบ key ไม่สำเร็จ (${res.status})`);
  } catch { feedLine("error", "ติดต่อ daemon ไม่ได้"); }
}

async function saveKey() {
  const provider = document.getElementById("key-provider").value;
  const label = document.getElementById("key-label").value.trim();
  const key = document.getElementById("key-value").value.trim();
  if (!key) return;
  feedLine("ln", `กำลังตรวจสอบ key ${provider}…`);
  const res = await fetch(BASE + "/accounts/api-key", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider, label, key, validate: true }),
  });
  const d = await res.json().catch(() => ({}));
  if (res.ok) {
    document.getElementById("key-value").value = "";
    document.getElementById("key-label").value = "";
    const n = (d.models || []).length;
    feedLine("done", `เพิ่ม ${provider} key แล้ว${n ? ` (${n} model พร้อมใช้)` : ""} — เข้ารหัสเก็บในเครื่อง`);
    loadKeys();
  } else {
    feedLine("error", `เพิ่ม key ไม่สำเร็จ: ${d.detail || res.status}`);
  }
}

/* ---------- github (M9-3) ---------- */

function renderGithubStatus(g) {
  const el = document.getElementById("gh-status");
  if (g && g.repo) document.getElementById("gh-repo").value = g.repo;
  const acct = (g && g.set)
    ? `<span class="key-chip on">✓ ${esc(g.login || "?")}</span>`
    : `<span class="key-chip">ยังไม่ได้เชื่อม token</span>`;
  const repo = (g && g.repo)
    ? `<span class="key-chip on">📦 ${esc(g.repo)}</span>`
    : `<span class="key-chip">ยังไม่ได้ตั้ง repo</span>`;
  el.innerHTML = acct + " " + repo;
}

async function saveGithubRepo() {
  const repo = document.getElementById("gh-repo").value.trim();
  if (!repo) return;
  document.getElementById("gh-status").textContent = "กำลังตรวจสอบ repo…";
  try {
    const res = await fetch(BASE + "/settings/github-repo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      renderGithubStatus(await (await fetch(BASE + "/settings/github")).json());
      feedLine("done", `ตั้ง GitHub repo: ${esc(data.repo)}`);
    } else {
      document.getElementById("gh-status").textContent = `✗ ${data.detail || "ตั้ง repo ไม่สำเร็จ"}`;
      feedLine("error", esc(data.detail || "ตั้ง repo ไม่สำเร็จ"));
    }
  } catch {
    feedLine("error", "ติดต่อ daemon ไม่ได้");
  }
}

async function saveGithub() {
  const input = document.getElementById("gh-token");
  const token = input.value.trim();
  if (!token) return;
  document.getElementById("gh-status").textContent = "กำลังตรวจสอบ token…";
  try {
    const res = await fetch(BASE + "/settings/github", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      input.value = "";
      renderGithubStatus(await (await fetch(BASE + "/settings/github")).json());
      feedLine("done", `เชื่อม GitHub แล้ว: ${esc(data.login)} (token เก็บใน .env เครื่องนี้)`);
    } else {
      document.getElementById("gh-status").textContent = `✗ ${data.detail || "เชื่อมไม่สำเร็จ"}`;
      feedLine("error", esc(data.detail || "เชื่อม GitHub ไม่สำเร็จ"));
    }
  } catch {
    feedLine("error", "ติดต่อ daemon ไม่ได้");
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

/* ---------- available models (M7-6/M7-8) — local 1 ตัว (active) + cloud ทุกตัวที่มี key (เลือกต่าง provider ต่อ agent ได้) ---------- */

let availableModels = null;

async function loadAvailableModels(force) {
  if (availableModels && !force) return availableModels;
  try {
    availableModels = (await (await fetch(BASE + "/models/available")).json()).options || [];
  } catch {
    availableModels = [{ provider: "ollama", model: "qwen3:8b", label: "qwen3:8b (local)", recommended: true }];
  }
  return availableModels;
}

function fillModelSelect(sel, opts, current) {
  sel.innerHTML = "";
  let matched = false;
  const curAcc = (current && current.account_id) || "";
  for (const o of opts) {
    const op = document.createElement("option");
    op.value = o.provider + "|" + o.model + "|" + (o.account_id || "");  // M14-9 — พา account_id
    op.textContent = o.label;
    if (current && current.provider === o.provider && current.model === o.model
        && curAcc === (o.account_id || "")) { op.selected = true; matched = true; }
    sel.appendChild(op);
  }
  if (current && current.model && !matched) {
    // model ปัจจุบันไม่อยู่ในลิสต์ (เช่น cloud ที่บัญชี/key ถูกลบ) — ค้าง option ไว้ไม่ให้ค่าหาย
    const op = document.createElement("option");
    op.value = current.provider + "|" + current.model + "|" + curAcc;
    op.textContent = (current.provider !== "ollama" ? "☁ " : "") + current.provider + "/" + current.model + " (ปัจจุบัน)";
    op.selected = true;
    sel.appendChild(op);
  }
}

function parseModelVal(v) {
  const p = String(v).split("|");   // provider|model|account_id (account_id optional, M14-9)
  return { provider: p[0] || "", model: p[1] || "", account_id: p[2] || "" };
}

/* ---------- onboarding / CEO (M8) ---------- */

async function checkOnboarding() {
  try {
    const o = await (await fetch(BASE + "/settings/onboarding")).json();
    if (!o.onboarded) openOnboard();
  } catch { /* daemon down — reconnect แล้วเช็คใหม่ */ }
}

async function openOnboard() {
  const opts = await loadAvailableModels(true);
  const base = opts.find(o => o.recommended) || opts[0];
  fillModelSelect(document.getElementById("ceo-model"), opts,
    base ? { provider: base.provider, model: base.model } : null);
  document.getElementById("onboard-backdrop").classList.remove("hidden");
}

async function createCeo() {
  const name = document.getElementById("ceo-name").value.trim();
  const role = document.getElementById("ceo-role").value.trim();
  const status = document.getElementById("ceo-status");
  if (!name || !role) { status.textContent = "ใส่ชื่อและหน้าที่ก่อน"; return; }
  const payload = {
    name, role,
    avatar: document.getElementById("ceo-avatar").value.trim() || "👑",
    color: "#ffe040",   // gold = CEO
    is_ceo: true,
  };
  const msel = document.getElementById("ceo-model");
  if (msel && msel.value) payload.llm = parseModelVal(msel.value);
  status.textContent = "กำลังสร้าง…";
  try {
    const res = await fetch(BASE + "/agents", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) { status.textContent = `สร้างไม่สำเร็จ (${res.status})`; return; }
    await fetch(BASE + "/settings/onboarding", { method: "POST" }).catch(() => {});
    document.getElementById("onboard-backdrop").classList.add("hidden");
    feedLine("done", `ยินดีต้อนรับ ${esc(name)}! 👑 เข้าออฟฟิศแล้ว`);
    loadAgents();
  } catch {
    status.textContent = "ติดต่อ daemon ไม่ได้";
  }
}

/* ---------- model picker (M4-6 / M7-6) ---------- */

let pickerAgentId = null;

async function openModelPicker(agentId) {
  const a = agents[agentId];
  if (!a) return;
  pickerAgentId = agentId;
  document.getElementById("m-agent-name").textContent = a.name;
  fillModelSelect(document.getElementById("m-model"), await loadAvailableModels(true), a.llm);
  loadSpecialistBanner(a);   // M11-9 — โชว์ banner แนะนำ cloud เมื่อมี key
  document.getElementById("m-thinking").checked = !!a.thinking_mode;   // M11-8
  await loadToolChecklist(a.allowed_tools || []);                       // M11-3
  document.getElementById("model-backdrop").classList.remove("hidden");
}

// M11-3 — สร้าง checklist ของ tool ในโมดัล (ติ๊กตาม allowed_tools; ว่าง = ไม่ติ๊กเลย = ทุก tool)
let _toolList = null;
async function loadToolChecklist(allowed) {
  const box = document.getElementById("m-tools");
  if (!box) return;
  if (!_toolList) {
    try { _toolList = (await (await fetch(BASE + "/tools")).json()).tools || []; }
    catch { _toolList = []; }
  }
  const set = new Set(allowed);
  box.innerHTML = _toolList.map(t =>
    `<label class="inline tool-item" title="${esc(t.desc)}">`
    + `<input type="checkbox" value="${esc(t.name)}"${set.has(t.name) ? " checked" : ""}> ${esc(t.name)}</label>`
  ).join("");
}

// M11-9 (§5.2) — banner opt-in: แนะนำ cloud specialist ตาม role เมื่อมี key (CEO กดใช้เอง ไม่บังคับ)
async function loadSpecialistBanner(a) {
  const box = document.getElementById("m-specialist");
  if (!box) return;
  box.classList.add("hidden");
  box.innerHTML = "";
  try {
    const q = new URLSearchParams({ role: a.role || "", keywords: (a.keywords || []).join(",") });
    const d = await (await fetch(BASE + "/settings/specialist?" + q)).json();
    if (!d.suggestion || !d.key_available) return;  // ไม่มี key → ไม่รบกวน, ใช้ local ต่อ
    const s = d.suggestion;
    box.innerHTML = `💡 <b>${esc(a.role)}</b> แนะนำใช้ <b>${esc(s.provider)}/${esc(s.model)}</b> — `
      + `${esc(s.reason)} <button class="neon-btn" id="m-spec-apply">ใช้เลย</button>`;
    box.classList.remove("hidden");
    document.getElementById("m-spec-apply").onclick = () => {
      const sel = document.getElementById("m-model");
      const val = s.provider + "|" + s.model;
      if (![...sel.options].some(o => o.value === val)) {
        const op = document.createElement("option");
        op.value = val; op.textContent = "☁ " + s.provider + "/" + s.model + " (แนะนำ)";
        sel.appendChild(op);
      }
      sel.value = val;
    };
  } catch { /* daemon ล่ม → ไม่โชว์ banner เฉย ๆ */ }
}

function closeModelPicker(ev) {
  if (ev && ev.target.id !== "model-backdrop") return;
  document.getElementById("model-backdrop").classList.add("hidden");
  pickerAgentId = null;
}

async function saveModel() {
  if (!pickerAgentId) return;
  const llm = parseModelVal(document.getElementById("m-model").value);
  const thinking_mode = document.getElementById("m-thinking").checked;            // M11-8
  const allowed_tools = [...document.querySelectorAll("#m-tools input:checked")]   // M11-3
    .map(c => c.value);
  // account_id ผูกมากับ model dropdown แล้ว (M14-9) — ไม่ต้องมี key dropdown แยก
  const res = await fetch(BASE + `/agents/${pickerAgentId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ llm, thinking_mode, allowed_tools }),
  });
  if (res.ok) {
    const toolNote = allowed_tools.length ? `, ${allowed_tools.length} tool` : "";
    feedLine("done", `บันทึก ${esc(llm.provider)}/${esc(llm.model)}${thinking_mode ? " /think" : ""}${toolNote}`);
    document.getElementById("model-backdrop").classList.add("hidden");
    loadAgents();
  } else {
    feedLine("error", `เปลี่ยน model ไม่สำเร็จ (${res.status})`);
  }
}

/* ---------- system status: connecting / daemon down / ollama (M5-5) ---------- */

function showOverlay(state, title, msg) {
  const ov = document.getElementById("sys-overlay");
  if (!ov) return;
  if (state === "ok") { ov.classList.add("hidden"); return; }
  ov.classList.toggle("down", state === "down");
  document.getElementById("sys-title").textContent = title;
  document.getElementById("sys-msg").innerHTML = msg || "";
  ov.classList.remove("hidden");
}

// /health บอก ollama_ok — เปิด/ปิด banner เตือน (local model ใช้ไม่ได้)
async function checkOllama() {
  try {
    const h = await (await fetch(BASE + "/health")).json();
    document.getElementById("ollama-warn").classList.toggle("hidden", h.ollama_ok !== false);
  } catch { /* daemon down — sys-overlay จัดการแล้ว */ }
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
    showOverlay("ok");
    checkOllama();      // เตือนถ้า Ollama ยังไม่ขึ้น (M5-5)
    feedLine("done", "เชื่อมต่อ daemon แล้ว");
    loadAgents().then(runQaHooks);
    loadProposals();
    loadPermissions(); // คำขอที่ค้างระหว่าง sidebar ปิดอยู่ (M6-8)
    if (!uiRestored) { uiRestored = true; restoreUiState(); }
    checkOnboarding(); // first run → wizard สร้าง CEO (M8)
  };
  ws.onclose = () => {
    setDaemonDot(false);
    showOverlay("down", "DAEMON ไม่ทำงาน",
      "เชื่อมต่อ daemon (port 8797) ไม่ได้<br>" +
      "เปิด <b>ET-Office.exe</b> (หรือรัน launcher) ทิ้งไว้<br>" +
      "กำลังลองเชื่อมใหม่อัตโนมัติ…");
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

/* ---------- observability (M11-5, §4.2) ---------- */
// สะสมสถิติต่อ agent ในเซสชัน — ดูได้ทาง window.etAgentStats() (ฐานของ dashboard รอบหน้า)
const agentStats = {};

function recordStats(d) {
  if (!d || !d.agent_id) return;
  const s = agentStats[d.agent_id] || (agentStats[d.agent_id] = {
    name: nameOf(d.agent_id), tasks: 0, latency_ms: 0, tokens_in: 0, tokens_out: 0, cache_hits: 0 });
  s.name = nameOf(d.agent_id);
  s.tasks += 1;
  s.latency_ms += d.latency_ms || 0;
  s.tokens_in += d.tokens_in || 0;
  s.tokens_out += d.tokens_out || 0;
  s.cache_hits += d.cache_hits || 0;
}
window.etAgentStats = () => agentStats;  // เรียกใน console ดูสถิติต่อ agent

// chip metric เล็ก ๆ ต่อท้ายบรรทัด feed: model · เวลา · ↑in↓out · ⚡cache
function fmtMetrics(d) {
  if (!d || !d.model) return "";
  const ms = d.latency_ms || 0;
  const dur = ms >= 1000 ? (ms / 1000).toFixed(1) + "s" : ms + "ms";
  const tok = (d.tokens_in || d.tokens_out)
    ? ` · ↑${d.tokens_in || 0}↓${d.tokens_out || 0}` : "";
  const cache = d.cache_hits ? ` · ⚡${d.cache_hits}` : "";
  return ` <span style="opacity:.55;font-size:.85em">[${esc(d.model)} · ${dur}${tok}${cache}]</span>`;
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
      recordStats(d);
      feedLine("done", `✔ <b>${esc(nameOf(d.agent_id))}</b>: ${esc(trim(d.output, 400))}${fmtMetrics(d)}`);
      break;
    case "task.failed":
      recordStats(d);
      feedLine("error", `✘ ${esc(nameOf(d.agent_id))}: ${esc(trim(d.error, 200))}${fmtMetrics(d)}`);
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
    case "proposal.completed":  // M13-4 — เดิมไม่มี handler → approve แล้วเงียบ (tray toast มาจาก host.py)
      feedLine("done", `✔ ข้อเสนอเสร็จ — <b>${esc(nameOf(d.agent_id))}</b>: ${esc(trim(d.title, 120))}`);
      if (d.output) feedLine("ln", esc(trim(d.output, 400)));
      loadProposals();
      break;
    case "proposal.failed":     // M13-4
      feedLine("error", `✘ ข้อเสนอล้มเหลว: ${esc(trim(d.title, 100))} — ${esc(trim(d.error, 160))}`);
      loadProposals();
      break;
    case "agent.chat":          // M13-7 — agent ตอบคุยเล่น (มาจากที่อื่น/escalate)
      feedLine("social", `💬 ${esc(nameOf(d.agent_id))}: ${esc(trim(d.text, 200))}`);
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
    case "model.install.progress":
      updateInstallBanner(d.tag, d.percent ?? null, d.status || "");
      break;
    case "model.install.done":
      updateInstallBanner(null);
      feedLine("done", `✔ ติดตั้ง ${esc(d.tag)} เสร็จ — agent ที่ใช้ local สลับมาที่ ${esc(d.tag)} แล้ว (เลิกใช้ ${esc(d.prev || "qwen3 default")} · agent ที่ใช้ cloud API ไม่เปลี่ยน)`);
      feedLine("ln", "↻ แนะนำ restart ET Office 1 ครั้งให้ model ใหม่โหลดสะอาด — และอย่าสลับ model ระหว่างทีมกำลังทำงานจริง");
      checkOllama();   // ลง model แรกแล้ว → เคลียร์ banner เตือนถ้า ollama พร้อม (M5-5)
      if (settingsOpen) loadModelCatalog();
      break;
    case "model.install.error":
      updateInstallBanner(null);
      feedLine("error", `✘ ติดตั้ง ${esc(d.tag)} ล้มเหลว: ${esc(d.error || "")}`);
      if (settingsOpen) loadModelCatalog();
      break;
    case "model.uninstall.done":
      feedLine("done", `🗑 ลบ ${esc(d.tag)} แล้ว — agent ที่ใช้ local กลับไปใช้ ${esc(d.active || "qwen3 default")}`);
      if (settingsOpen) loadModelCatalog();
      break;
    case "model.switched":   // M13-1 — สลับ active local model (ไม่ pull ใหม่)
      feedLine("done", `🔄 สลับ local model → <b>${esc(d.tag)}</b> แล้ว (เลิกใช้ ${esc(d.prev || "qwen3 default")} · agent ที่ใช้ cloud API ไม่เปลี่ยน)`);
      feedLine("ln", "agent ที่ตั้ง local ทุกตัวจะใช้ model ใหม่ในงานถัดไปทันที — ไม่ต้อง restart");
      if (settingsOpen) loadModelCatalog();
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

showOverlay("connecting", "กำลังเชื่อมต่อ…", "กำลังเชื่อมกับ daemon (port 8797)");
connectWs();
