extends Node
## Agent choreography (M3-3) — รับ WS events → spawn / เดิน / เปลี่ยน status
## ดึง agent list จาก daemon (GET /agents) เมื่อ connect แล้ว spawn ลง World layer

const DAEMON_HTTP := "http://localhost:8797"
const GRID_W := 18
const GRID_H := 12

# จุดยืนประจำ zone (grid cells) — ตรงกับ ZONES ใน office_builder.gd
const DESK_SPOTS: Array[Vector2i] = [
	Vector2i(7, 1), Vector2i(9, 1), Vector2i(11, 1),
	Vector2i(7, 3), Vector2i(9, 3), Vector2i(11, 3),
]
const ZONE_SPOTS := {
	"cafe":    [Vector2i(8, 7), Vector2i(10, 8), Vector2i(9, 10)],
	"meeting": [Vector2i(2, 7), Vector2i(4, 8), Vector2i(2, 9), Vector2i(4, 10)],
	"dorm":    [Vector2i(14, 7), Vector2i(16, 8), Vector2i(14, 9)],
}

# map ชื่อ role (จาก daemon registry) → sprite key (ชื่อไฟล์ char_<key>.png)
const ROLE_SPRITES := {
	"producer": "producer", "project manager": "producer",
	"programmer": "coder", "software": "coder", "engineer": "coder",
	"designer": "designer", "ux": "designer",
	"research": "research", "analyst": "research",
}

var _agents: Dictionary = {}      # agent_id -> AgentSprite
var _desk_of: Dictionary = {}     # agent_id -> Vector2i
var _nav: OfficeNav
var _http: HTTPRequest

@onready var _world: Node2D = get_node("../OfficeBuilder/World")
@onready var _events: Node = get_node("../EventClient")


func _ready() -> void:
	_nav = OfficeNav.new(GRID_W, GRID_H)
	_http = HTTPRequest.new()
	add_child(_http)
	_http.request_completed.connect(_on_agents_fetched)
	_events.connected.connect(_fetch_agents)
	_events.event_received.connect(_on_event)


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
	var sprite := AgentSprite.new()
	sprite.setup(id, str(cfg.get("name", "agent")),
		_sprite_key_for(str(cfg.get("role", "")) + " " + str(cfg.get("name", ""))),
		Color(str(cfg.get("color", "#00e5ff"))))
	var desk := DESK_SPOTS[index % DESK_SPOTS.size()]
	_desk_of[id] = desk
	sprite.place_at(desk)
	_world.add_child(sprite)
	_agents[id] = sprite


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
		"agent.deleted":
			var id := str(data.get("agent_id", ""))
			if _agents.has(id):
				_agents[id].queue_free()
				_agents.erase(id)


func _apply_status(agent_id: String, status: String) -> void:
	var sprite: AgentSprite = _agents.get(agent_id)
	if sprite == null:
		return
	match status:
		"working", "thinking", "idle":
			_walk_to(sprite, _desk_of.get(agent_id, DESK_SPOTS[0]))
		"break":
			_walk_to(sprite, _random_spot("cafe"))
		"collab":
			_walk_to(sprite, _random_spot("meeting"))
		"sleep":
			_walk_to(sprite, _random_spot("dorm"))


func _walk_to(sprite: AgentSprite, dest: Vector2i) -> void:
	if sprite.grid_pos() == dest:
		return
	sprite.walk_path(_nav.find_path(sprite.grid_pos(), dest))


func _random_spot(zone: String) -> Vector2i:
	var spots: Array = ZONE_SPOTS[zone]
	return spots[randi() % spots.size()]
