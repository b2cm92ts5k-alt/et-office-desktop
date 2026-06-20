extends Node
## Agent choreography (M3-3/M3-5) — รับ WS events → spawn / เดิน / เปลี่ยน status
## ดึง agent list จาก daemon (GET /agents) เมื่อ connect แล้ว spawn ลง World layer
## M3-5: จอง spot ต่อ zone (กันยืนซ้อนกัน) + night shift — DEEP NIGHT (22:00–05:59
## ตาม design doc §04) agent ที่ idle เดินไปนอน dorm เว้นหนึ่งตัวอยู่เวร
## daemon เป็นเจ้าของ status จริงเสมอ — event ที่เข้ามา override พฤติกรรมกลางคืน

const DAEMON_HTTP := "http://localhost:8797"
const GRID_W := 18
const GRID_H := 12

const NIGHT_START_HOUR := 22  # DEEP NIGHT เริ่ม
const NIGHT_END_HOUR := 6     # เช้า — ปลุกตัวที่หลับโดย night logic
const NIGHT_CHECK_SEC := 60.0

# จุดยืนประจำ zone (grid cells) — ตรงกับ ZONES ใน office_builder.gd
const DESK_SPOTS: Array[Vector2i] = [
	Vector2i(7, 1), Vector2i(9, 1), Vector2i(11, 1),
	Vector2i(7, 3), Vector2i(9, 3), Vector2i(11, 3),
	Vector2i(7, 5), Vector2i(9, 5), Vector2i(11, 5),  # แถวสาม — OPS ขยาย (CEO มิ.ย. 2026)
]
const ZONE_SPOTS := {
	# (11,6) เดิมกลายเป็น OPS หลังขยายโซน — ย้ายเข้า CAFE ใหม่ (y เริ่ม 7)
	# จุดละ 1 ตัวเท่านั้น (ห้ามยืนซ้อน) — เต็มแล้วไม่เด้งสุ่มทับ (ข้อ 2)
	"cafe":    [Vector2i(8, 7), Vector2i(10, 8), Vector2i(9, 10), Vector2i(12, 9)],
	"meeting": [Vector2i(2, 7), Vector2i(4, 8), Vector2i(2, 9), Vector2i(4, 10)],
}
# DORM: เตียงสองชั้น 4 หลัง (ตรง bed_bunk ใน office_builder) — หลังละ 2 ที่ (ล่าง/บน)
# = รับได้สูงสุด 8 ตัว (ข้อ 4). bunk 0=ล่าง 1=บน (บนยกภาพ+z สูงกว่า — ข้อ 3)
const DORM_BEDS: Array[Vector2i] = [
	Vector2i(14, 7), Vector2i(16, 8), Vector2i(14, 9), Vector2i(16, 10),
]
const BUNK_CAP := 2
const NO_SPOT := Vector2i(-1, -1)  # sentinel: zone เต็ม (ไม่มีที่ว่าง)

# CEO ยืนประจำที่โต๊ะตัวเองใน EXEC SUITE เสมอ (3,2) ตรง desk_ceo.png — ไม่ใช่โต๊ะพนักงาน
# (CEO มิ.ย. 2026 ข้อ 5) — กันออกจาก DESK_SPOTS pool + ไม่ roam + ไม่ถูกส่งนอนกลางคืน
const CEO_DESK := Vector2i(3, 2)

# Idle-roam (M13-6) — agent ที่ว่างนาน ๆ สุ่มเดินเล่นตาม aisle แล้วกลับโต๊ะ (ดูมีชีวิต ไม่ยืนนิ่ง)
# cells ช่องทางเดินระหว่างโต๊ะ (โต๊ะอยู่ y=1,3,5 → เดินเล่น y=2,4,6) — nav เดินผ่านได้ ไม่ชนผนัง
const ROAM_CHECK_SEC := 6.0
const ROAM_CHANCE := 0.35
const ROAM_SPOTS: Array[Vector2i] = [
	Vector2i(8, 2), Vector2i(10, 2), Vector2i(12, 2),
	Vector2i(8, 4), Vector2i(10, 4), Vector2i(12, 4),
	Vector2i(6, 6), Vector2i(8, 6), Vector2i(10, 6),
	Vector2i(3, 4), Vector2i(5, 6),
]

# map ชื่อ role (จาก daemon registry) → sprite key (ชื่อไฟล์ char_<key>.png)
const ROLE_SPRITES := {
	"producer": "producer", "project manager": "producer",
	"programmer": "coder", "software": "coder", "engineer": "coder",
	"designer": "designer", "ux": "designer",
	"research": "research", "analyst": "research",
}

var _agents: Dictionary = {}      # agent_id -> AgentSprite
var _screens: Dictionary = {}     # agent_id -> HologramScreen (จอ desk, M3-7)
var _desk_of: Dictionary = {}     # agent_id -> Vector2i
var _desk_taken: Dictionary = {}  # Vector2i -> agent_id (1 โต๊ะ 1 คน — ข้อ 2)
var _spot_of: Dictionary = {}     # agent_id -> Vector2i spot ที่จองใน cafe/meeting
var _spot_owner: Dictionary = {}  # Vector2i -> agent_id (1 จุด 1 คน)
var _bed_of: Dictionary = {}      # agent_id -> {"cell": Vector2i, "bunk": int}
var _bed_occ: Dictionary = {}     # "x,y" -> Array[String] ขนาด BUNK_CAP (index=bunk, ""=ว่าง)
var _auto_slept: Dictionary = {}  # agent_id -> true เมื่อหลับโดย night logic (ไม่ใช่ daemon)
var _ceo_ids: Dictionary = {}     # agent_id -> true สำหรับ CEO (ยืนประจำ 3,2 ไม่ roam/ไม่นอน)
var _nav: OfficeNav
var _http: HTTPRequest
var _fx: FxFactory               # M3-8 — เล่น pixel FX ตาม event

@onready var _world: Node2D = get_node("../OfficeBuilder/World")
@onready var _events: Node = get_node("../EventClient")


func _ready() -> void:
	_nav = OfficeNav.new(GRID_W, GRID_H)
	# cell ที่มีผนังตั้งอยู่ (col 0 / row 0 — ตรงกับ office_builder) เดินทะลุไม่ได้ (M3-12)
	for gy in GRID_H:
		_nav.set_blocked(Vector2i(0, gy), true)
	for gx in GRID_W:
		_nav.set_blocked(Vector2i(gx, 0), true)
	_http = HTTPRequest.new()
	add_child(_http)
	_http.request_completed.connect(_on_agents_fetched)
	_events.connected.connect(_fetch_agents)
	_events.event_received.connect(_on_event)

	_fx = FxFactory.new()        # M3-8 — วางใน World เพื่อใช้พิกัดเดียวกับ agent
	_world.add_child(_fx)

	var night_timer := Timer.new()
	night_timer.wait_time = NIGHT_CHECK_SEC
	night_timer.timeout.connect(_check_night_shift)
	add_child(night_timer)
	night_timer.start()

	# M13-6 — idle-roam: agent ว่างเดินเล่นในห้องเป็นระยะ
	var roam_timer := Timer.new()
	roam_timer.wait_time = ROAM_CHECK_SEC
	roam_timer.timeout.connect(_roam_tick)
	add_child(roam_timer)
	roam_timer.start()


func _fetch_agents() -> void:
	_http.request(DAEMON_HTTP + "/agents")


func _on_agents_fetched(_result: int, code: int, _headers: PackedStringArray,
		body: PackedByteArray) -> void:
	_debug("fetched code=%d bytes=%d" % [code, body.size()])
	if code != 200:
		return
	var data: Variant = JSON.parse_string(body.get_string_from_utf8())
	if typeof(data) != TYPE_ARRAY:
		_debug("parse failed type=%d" % typeof(data))
		return
	for i in (data as Array).size():
		var cfg: Dictionary = data[i]
		_spawn_agent(cfg, i)
	_debug("spawned=%d world_children=%d" % [_agents.size(), _world.get_child_count()])
	print("[agents] spawned %d agents" % _agents.size())
	_check_night_shift()  # boot ตอนกลางคืน → จัด night shift ทันทีไม่ต้องรอ timer


func _debug(msg: String) -> void:
	var f := FileAccess.open("user://am_debug.txt", FileAccess.READ_WRITE if FileAccess.file_exists("user://am_debug.txt") else FileAccess.WRITE)
	if f:
		f.seek_end()
		f.store_line(msg)
		f.close()


func _spawn_agent(cfg: Dictionary, index: int) -> void:
	var id := str(cfg.get("id", ""))
	if id.is_empty() or _agents.has(id):
		return
	var is_ceo: bool = bool(cfg.get("is_ceo", false))
	if is_ceo:
		_ceo_ids[id] = true
	var sprite := AgentSprite.new()
	sprite.setup(id, str(cfg.get("name", "agent")),
		_sprite_key_for(str(cfg.get("role", "")) + " " + str(cfg.get("name", ""))),
		Color(str(cfg.get("color", "#00e5ff"))),
		str(cfg.get("sprite", "")))  # custom spritesheet (M6-2 v2)
	# CEO ยืนโต๊ะตัวเองที่ (3,2) เสมอ ไม่กิน DESK_SPOTS ของพนักงาน (ข้อ 5)
	var desk := CEO_DESK if is_ceo else _claim_desk(id, index)
	_desk_of[id] = desk
	sprite.place_at(desk)
	# จอ hologram ประจำโต๊ะ (M3-7) — position = cell เดียวกับ desk/agent (y-sort คีย์เท่ากัน)
	# เพิ่ม "ก่อน" agent → agent วาดทับจอ (จอ overlay มอนิเตอร์ furniture, ไม่บังตัว/หัว agent)
	# อยู่กับที่แม้ agent เดินไปไหน — agent ไม่อยู่โต๊ะ จอจะดับเอง
	var screen := HologramScreen.new()
	screen.position = Iso.grid_to_screen(desk)
	_world.add_child(screen)
	_screens[id] = screen
	_world.add_child(sprite)
	_agents[id] = sprite
	# status เริ่มต้นจาก registry — เดินไป zone ที่ถูกต้องเลยถ้าไม่ใช่ที่ desk
	_apply_status(id, str(cfg.get("status", "idle")))


func _sprite_key_for(role_text: String) -> String:
	var lower := role_text.to_lower()
	for keyword: String in ROLE_SPRITES:
		if keyword in lower:
			return ROLE_SPRITES[keyword]
	return "producer"


func _on_event(event: Dictionary) -> void:
	var type := str(event.get("type", ""))
	var data: Dictionary = event.get("data", {})
	match type:
		"agent.status":
			_apply_status(str(data.get("agent_id", "")), str(data.get("status", "")))
		"agent.created":
			_spawn_agent(data, _agents.size())
		"task.routing":
			_say(data, "รับงาน: " + str(data.get("message", "")))
		"task.completed":
			_say(data, str(data.get("output", "")))
			_fx_at(str(data.get("agent_id", "")), "fx_done")
			_flash_screen(str(data.get("agent_id", "")), "done")
		"task.failed":
			_say(data, "ล้มเหลว: " + str(data.get("error", "")))
			_fx_at(str(data.get("agent_id", "")), "fx_error")
			_flash_screen(str(data.get("agent_id", "")), "error")
		"social.chat":
			_say(data, str(data.get("text", "")))
		"agent.chat":
			_say(data, str(data.get("text", "")))  # M13-7 — คุยเล่นกับผู้ใช้ โชว์ bubble
		"proposal.created":
			var by: Array = data.get("proposed_by", [])
			if not by.is_empty():
				_say({"agent_id": by[0]}, "💡 เสนอไอเดีย: " + str(data.get("title", "")))
				_fx_at(str(by[0]), "fx_proposal")
		"qa.dump":
			_dump_positions()  # QA gate M3-12 อ่าน snapshot นี้ไปตรวจ
		"agent.deleted":
			var id := str(data.get("agent_id", ""))
			if _agents.has(id):
				_release_rest(id)
				_release_desk(id)
				_desk_of.erase(id)
				_auto_slept.erase(id)
				_ceo_ids.erase(id)
				_agents[id].queue_free()
				_agents.erase(id)
				if _screens.has(id):
					_screens[id].queue_free()
					_screens.erase(id)


func _dump_positions() -> void:
	# snapshot ตำแหน่ง/สถานะทุก agent → user://qa_positions.json (ให้ qa_m3.py ตรวจ)
	var snap := {"ts": Time.get_unix_time_from_system(), "agents": []}
	for id: String in _agents:
		var s: AgentSprite = _agents[id]
		(snap["agents"] as Array).append({
			"id": id, "name": s.agent_name,
			"grid": [s.grid_pos().x, s.grid_pos().y],
			"status": s.status, "walking": s.is_walking(),
		})
	var f := FileAccess.open("user://qa_positions.json", FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(snap))
		f.close()


func _say(data: Dictionary, text: String) -> void:
	var sprite: AgentSprite = _agents.get(str(data.get("agent_id", "")))
	if sprite != null:
		sprite.say(text)


func _fx_at(agent_id: String, fx_name: String) -> void:
	# M3-8 — เล่น FX flipbook เหนือหัว agent ที่ระบุ (เงียบถ้าไม่พบตัว)
	var sprite: AgentSprite = _agents.get(agent_id)
	if sprite != null and _fx != null:
		_fx.play(fx_name, sprite.position)


func _flash_screen(agent_id: String, kind: String) -> void:
	# M3-7 — แฟลช done/error บนจอ desk ของ agent
	if _screens.has(agent_id):
		_screens[agent_id].flash(kind)


func _apply_status(agent_id: String, status: String, from_daemon: bool = true) -> void:
	var sprite: AgentSprite = _agents.get(agent_id)
	if sprite == null:
		return
	if from_daemon:
		_auto_slept.erase(agent_id)  # daemon สั่งมาเอง → ไม่นับเป็นหลับอัตโนมัติแล้ว

	# sleep แต่เตียงเต็ม (8 ตัว) → นอนไม่ได้ ตกกลับเป็น idle (ข้อ 4)
	var bunk: Dictionary = {}
	if status == "sleep":
		bunk = _claim_bunk(agent_id)
		if bunk.is_empty():
			status = "idle"

	sprite.set_status(status)
	if _screens.has(agent_id):
		_screens[agent_id].set_state(status)  # จอ desk สลับอนิเมชันตาม state (M3-7)
	match status:
		"working", "thinking", "idle":
			_release_rest(agent_id)
			sprite.set_bunk(0)
			_walk_to(sprite, _desk_of.get(agent_id, DESK_SPOTS[0]))
		"break":
			_release_bed(agent_id)
			sprite.set_bunk(0)
			_go_zone(sprite, agent_id, "cafe")
		"collab":
			_release_bed(agent_id)
			sprite.set_bunk(0)
			_go_zone(sprite, agent_id, "meeting")
		"sleep":
			_release_spot(agent_id)         # ปล่อยที่ cafe/meeting ถ้าเคยจอง
			sprite.set_bunk(int(bunk["bunk"]))  # ชั้นบน → ยกภาพ + z สูงกว่า (ข้อ 3)
			_walk_to(sprite, bunk["cell"])


func _walk_to(sprite: AgentSprite, dest: Vector2i) -> void:
	if dest == NO_SPOT or sprite.grid_pos() == dest:
		return
	sprite.walk_path(_nav.find_path(sprite.grid_pos(), dest))


func _go_zone(sprite: AgentSprite, agent_id: String, zone: String) -> void:
	# เดินไปจุดว่างใน zone — ถ้าเต็มอยู่ที่เดิม (ไม่ยืนทับ — ข้อ 2)
	var spot := _claim_spot(zone, agent_id)
	if spot != NO_SPOT:
		_walk_to(sprite, spot)


# --- Idle-roam (M13-6) — agent ว่างเดินเล่นในห้องให้ดูมีชีวิต -------------

func _roam_tick() -> void:
	# เฉพาะ agent ที่ idle จริง (ไม่ใช่ working/break/sleep), ไม่ใช่ CEO (ยืนประจำ 3,2),
	# ไม่กำลังเดินอยู่, และกลางวัน (กลางคืนปล่อย night logic จัดการ)
	if _is_night():
		return
	for id: String in _agents:
		if _ceo_ids.has(id):
			continue
		var sprite: AgentSprite = _agents[id]
		if sprite.status != "idle" or sprite.is_walking():
			continue
		if randf() >= ROAM_CHANCE:
			continue
		var home: Vector2i = _desk_of.get(id, DESK_SPOTS[0])
		# อยู่นอกโต๊ะแล้ว → ครึ่งหนึ่งเดินกลับโต๊ะ, ครึ่งหนึ่งเดินเล่นต่อ (ไม่ดริฟต์หายไปไกล)
		if sprite.grid_pos() != home and randf() < 0.5:
			_walk_to(sprite, home)
		else:
			_walk_to(sprite, ROAM_SPOTS.pick_random())


# --- desk (1 โต๊ะ 1 คน — ข้อ 2) ---------------------------------------

func _claim_desk(agent_id: String, index: int) -> Vector2i:
	for d: Vector2i in DESK_SPOTS:
		if not _desk_taken.has(d):
			_desk_taken[d] = agent_id
			return d
	return DESK_SPOTS[index % DESK_SPOTS.size()]  # agent เกินจำนวนโต๊ะ (>9) — ยอมซ้ำ


func _release_desk(agent_id: String) -> void:
	if _desk_of.has(agent_id):
		_desk_taken.erase(_desk_of[agent_id])


# --- cafe / meeting (1 จุด 1 คน) -------------------------------------

func _claim_spot(zone: String, agent_id: String) -> Vector2i:
	# จอง spot ว่างใน zone — เต็มแล้วคืน NO_SPOT (ไม่เด้งสุ่มทับกัน — ข้อ 2)
	if _spot_of.has(agent_id) and _spot_of[agent_id] in (ZONE_SPOTS[zone] as Array):
		return _spot_of[agent_id]  # จองที่ใน zone นี้อยู่แล้ว ใช้ที่เดิม
	_release_spot(agent_id)
	var spots: Array = ZONE_SPOTS[zone]
	var free := spots.filter(func(s: Vector2i) -> bool: return not _spot_owner.has(s))
	if free.is_empty():
		return NO_SPOT
	var spot: Vector2i = free.pick_random()
	_spot_of[agent_id] = spot
	_spot_owner[spot] = agent_id
	return spot


func _release_spot(agent_id: String) -> void:
	if _spot_of.has(agent_id):
		_spot_owner.erase(_spot_of[agent_id])
		_spot_of.erase(agent_id)


# --- dorm: เตียง 2 ชั้น × 4 หลัง = สูงสุด 8 ตัว (ข้อ 3, 4) ------------

func _bed_key(cell: Vector2i) -> String:
	return "%d,%d" % [cell.x, cell.y]


func _claim_bunk(agent_id: String) -> Dictionary:
	# คืน {cell, bunk} ของเตียงว่าง (bunk 0=ล่าง 1=บน) — {} ถ้า dorm เต็มหมด (8 ตัว)
	# spread: เติมเตียง "ล่าง" ให้ครบทุกหลังก่อน แล้วค่อยขึ้น "ชั้นบน" (คนมาทีหลังอยู่บน — ข้อ 3)
	if _bed_of.has(agent_id):
		return _bed_of[agent_id]
	for level in BUNK_CAP:
		for bed: Vector2i in DORM_BEDS:
			var key := _bed_key(bed)
			var occ: Array = _bed_occ.get(key, [])
			if occ.is_empty():
				occ.resize(BUNK_CAP)
				occ.fill("")
			if str(occ[level]) == "":
				occ[level] = agent_id
				_bed_occ[key] = occ
				_bed_of[agent_id] = {"cell": bed, "bunk": level}
				return _bed_of[agent_id]
	return {}


func _release_bed(agent_id: String) -> void:
	if not _bed_of.has(agent_id):
		return
	var info: Dictionary = _bed_of[agent_id]
	var key := _bed_key(info["cell"])
	if _bed_occ.has(key):
		var occ: Array = _bed_occ[key]
		var lv: int = info["bunk"]
		if lv >= 0 and lv < occ.size() and str(occ[lv]) == agent_id:
			occ[lv] = ""
	_bed_of.erase(agent_id)


func _release_rest(agent_id: String) -> void:
	# ออกจากที่พักทุกชนิด (cafe/meeting + เตียง) — เรียกตอนกลับไปทำงาน/ถูกลบ
	_release_spot(agent_id)
	_release_bed(agent_id)


# --- Night shift (M3-5) — DEEP NIGHT ตาม design doc §04 -----------------

func _is_night() -> bool:
	var hour: int = Time.get_time_dict_from_system()["hour"]
	return hour >= NIGHT_START_HOUR or hour < NIGHT_END_HOUR


func _check_night_shift() -> void:
	if _agents.is_empty():
		return
	var ids := _agents.keys()
	ids.sort()
	var night_shift: String = ids[0]  # ลำดับคงที่ → ตัวแรกอยู่เวรดึก ไม่หลับ
	if _is_night():
		for id: String in ids:
			var sprite: AgentSprite = _agents[id]
			# CEO ไม่เข้านอน dorm — ยืนประจำโต๊ะตัวเอง (ข้อ 5)
			if id != night_shift and not _ceo_ids.has(id) and sprite.status == "idle":
				_auto_slept[id] = true
				_apply_status(id, "sleep", false)
	elif not _auto_slept.is_empty():
		for id: String in _auto_slept.keys():
			_apply_status(id, "idle", false)
		_auto_slept.clear()
