extends Node2D
## Office floor builder — M2-7 (ใช้ placeholder tiles จาก A-2)
## สร้าง floor 20x14 + ผนัง + 6 zones (tint ตามสีประจำ zone จาก ART-SPEC)
## โครงสร้าง: $Floor (ไม่ y-sort — พื้นเรียบ), $World (y_sort_enabled — ผนัง/เฟอร์นิเจอร์/agent)

# 18x12 → world กว้าง 960px — camera_rig.gd zoom 1.25 = 1200px บนจอ 1920
# เหลือขอบข้างละ 360px ให้ sidebar/panel เปิดได้ไม่บังตัว office
const GRID_W := 18
const GRID_H := 12

# zone: name, สี neon (จาก ART-SPEC), พื้นที่ grid Rect2i(x, y, w, h)
const ZONES := [
	{"name": "EXEC SUITE",  "color": Color("#ffe040"), "rect": Rect2i(0, 0, 6, 5)},
	# OPS ขยายลง 2 แถว (CEO มิ.ย. 2026) — รับโต๊ะแถวสาม y=5, CAFE ขยับลงไป y=7
	{"name": "OPS FLOOR",   "color": Color("#00e5ff"), "rect": Rect2i(6, 0, 7, 7)},
	{"name": "SERVER",      "color": Color("#b060f0"), "rect": Rect2i(13, 0, 5, 5)},
	{"name": "MEETING",     "color": Color("#ff4da6"), "rect": Rect2i(0, 5, 6, 7)},
	{"name": "CAFE",        "color": Color("#ff6030"), "rect": Rect2i(6, 7, 7, 5)},
	{"name": "DORM",        "color": Color("#4080ff"), "rect": Rect2i(13, 5, 5, 7)},
]
const ZONE_TINT := 0.16  # ผสมสี zone ลงพื้นแบบจาง — คุม brightness ≤60%

const FLOOR_SHADER := preload("res://shaders/floor_reflect.gdshader")  # M2-9

var _tile_a: Texture2D = preload("res://assets/sprites/furniture/tile_floor_a.png")
var _tile_b: Texture2D = preload("res://assets/sprites/furniture/tile_floor_b.png")
var _floor_mat: ShaderMaterial  # แชร์ตัวเดียวทุก tile — effect ต่อเนื่องผ่าน SCREEN_UV
var _wall_n: Texture2D = preload("res://assets/sprites/furniture/wall_n.png")
var _wall_w: Texture2D = preload("res://assets/sprites/furniture/wall_w.png")

# เฟอร์นิเจอร์/props (A-3) — วางตาม zone ให้ "ถูกที่และเหมาะสม"
# base ของทุกชิ้นแตะ ground line (gts ของ cell) = เท้า agent → y-sort ตรงกัน
# โต๊ะ OPS วางตรง DESK_SPOTS / เตียงตรง dorm spots (agent_manager.gd) → agent นั่ง/นอนทับพอดี
const FURN_DIR := "res://assets/sprites/furniture/"
const FURNITURE := [
	# EXEC SUITE (0,0,6,5) — โต๊ะ CEO โทนทอง + เก้าอี้ + ต้นไม้ประดับ
	{"f": "desk_ceo.png",         "c": Vector2i(3, 2)},   # ยาว 2 บล็อค คลุม 3,2 3,3
	{"f": "chair_ceo.png",        "c": Vector2i(2, 2)},   # ยาว 2 บล็อค คลุม 2,2 2,3
	{"f": "plant_a.png",          "c": Vector2i(1, 4)},
	{"f": "plant_b.png",          "c": Vector2i(5, 1)},
	# OPS FLOOR (6,0,7,7) — โต๊ะทำงานตรงจุดที่ agent นั่ง (DESK_SPOTS)
	{"f": "desk_agent.png",       "c": Vector2i(7, 1)},
	{"f": "desk_agent.png",       "c": Vector2i(9, 1)},
	{"f": "desk_agent.png",       "c": Vector2i(11, 1)},
	{"f": "desk_agent.png",       "c": Vector2i(7, 3)},
	{"f": "desk_agent.png",       "c": Vector2i(9, 3)},
	{"f": "desk_agent.png",       "c": Vector2i(11, 3)},
	{"f": "desk_agent.png",       "c": Vector2i(7, 5)},
	{"f": "desk_agent.png",       "c": Vector2i(9, 5)},
	{"f": "desk_agent.png",       "c": Vector2i(11, 5)},
	# SERVER (13,0,5,5) — แร็คเรียงชิดผนังหลัง
	{"f": "rack_server.png",      "c": Vector2i(14, 1)},
	{"f": "rack_server.png",      "c": Vector2i(16, 1)},
	{"f": "rack_server.png",      "c": Vector2i(15, 3)},
	# MEETING (0,5,6,7) — โต๊ะยาว 3 บล็อค (agent ล้อม) + whiteboard hologram แนบผนัง W (ยกขึ้นกำแพง)
	{"f": "table_meeting.png",    "c": Vector2i(3, 8), "fc": Vector2(72, 55)},  # คลุม 3,7 3,8 3,9
	{"f": "board_whiteboard.png", "c": Vector2i(0, 8), "fc": Vector2(30, 40), "r": 40.0},
	{"f": "plant_a.png",          "c": Vector2i(1, 11)},
	# CAFE (6,7,7,5) — โซฟายาว 3 บล็อค + โซฟาเล็ก ×2 + เครื่องกาแฟ + ต้นไม้
	{"f": "machine_coffee.png",   "c": Vector2i(6, 7)},
	{"f": "sofa_long.png",        "c": Vector2i(9, 8), "fc": Vector2(70, 58)},  # คลุม 8,8 9,8 10,8
	{"f": "sofa_small.png",       "c": Vector2i(7, 9), "fc": Vector2(36, 32)},
	{"f": "sofa_small.png",       "c": Vector2i(11, 9), "fc": Vector2(36, 32)},
	{"f": "plant_b.png",          "c": Vector2i(12, 11)},
	# DORM (13,5,5,7) — เตียงสองชั้นตรงจุดนอน (dorm spots) → agent หลับบนเตียง
	{"f": "bed_bunk.png",         "c": Vector2i(14, 7)},
	{"f": "bed_bunk.png",         "c": Vector2i(16, 8)},
	{"f": "bed_bunk.png",         "c": Vector2i(14, 9)},
	{"f": "bed_bunk.png",         "c": Vector2i(16, 10)},
	{"f": "plant_a.png",          "c": Vector2i(17, 6)},
]

# footprint base-center (px) ต่อชนิด sprite → จัดให้ "ฐานแตะพื้น" ตรง cell (ไม่ลอย)
# ค่ามาจาก base ของ box()/slab() ใน gen_furniture.py = (cx, by - bh/2)
# board_whiteboard ไม่อยู่ที่นี่ — เป็นของแขวนผนัง (ใช้ cell + raise แทน)
const FC := {
	"desk_agent.png": Vector2(32, 44),
	# CEO desk/chair ยาว 2 บล็อค (แกน +y) → fc = กลางฐาน "tile หลัง" (gy แรก) → c=cell หลัง คลุม c..c+(0,1)
	"desk_ceo.png": Vector2(80, 56), "chair_ceo.png": Vector2(76, 52),
	"chair.png": Vector2(16, 30), "machine_coffee.png": Vector2(16, 38),
	"rack_server.png": Vector2(24, 82), "bed_bunk.png": Vector2(32, 60),
	"plant_a.png": Vector2(16, 40), "plant_b.png": Vector2(16, 40),
	"table_meeting.png": Vector2(72, 55), "sofa_long.png": Vector2(70, 58),
	"sofa_small.png": Vector2(36, 32),
}

@onready var _floor: Node2D = $Floor
@onready var _world: Node2D = $World


func _ready() -> void:
	_build_floor()
	_build_walls()
	_build_furniture()
	_build_zone_labels()
	if "--grid" in OS.get_cmdline_user_args():
		_build_grid_labels()   # ดีบัก: โชว์เลข (gx,gy) ทุก tile — รัน dev-godot.cmd --grid
	# ป้าย ET OFFICE — เข้า World layer เดียวกับผนัง (y-sort) วางบนผนัง N (ขวา) เหนือกำแพง (มิ.ย.2026)
	_world.add_child(NeonSign.new())


func _build_grid_labels() -> void:
	# โชว์พิกัด (gx,gy) กลางทุก tile ไว้หา cell ที่จะใส่ใน FURNITURE / SIGN_GRID
	for gy in GRID_H:
		for gx in GRID_W:
			var l := Label.new()
			l.text = "%d,%d" % [gx, gy]
			l.add_theme_font_size_override("font_size", 7)
			l.add_theme_color_override("font_color", Color(1, 1, 1, 0.55))
			l.position = Iso.grid_to_screen(Vector2i(gx, gy)) - Vector2(9, 4)
			_floor.add_child(l)


func _build_floor() -> void:
	_floor_mat = ShaderMaterial.new()
	_floor_mat.shader = FLOOR_SHADER
	for gy in GRID_H:
		for gx in GRID_W:
			var s := Sprite2D.new()
			s.texture = _tile_a if (gx + gy) % 2 == 0 else _tile_b
			s.position = Iso.grid_to_screen(Vector2i(gx, gy))
			s.modulate = _zone_tint(Vector2i(gx, gy))
			s.material = _floor_mat
			_floor.add_child(s)


func _zone_tint(grid: Vector2i) -> Color:
	for z in ZONES:
		if (z["rect"] as Rect2i).has_point(grid):
			return Color(1, 1, 1).lerp(z["color"], ZONE_TINT)
	return Color(1, 1, 1)


func _build_walls() -> void:
	# ผนังด้านหลังสองระนาบ (ขอบบนซ้าย gx=0 และขอบบนขวา gy=0)
	for gy in GRID_H:
		_add_wall(_wall_n, Vector2i(0, gy))
	for gx in GRID_W:
		_add_wall(_wall_w, Vector2i(gx, 0))


func _build_furniture() -> void:
	for item: Dictionary in FURNITURE:
		var tex: Texture2D = load(FURN_DIR + str(item["f"]))
		if tex == null:
			push_warning("furniture missing: " + str(item["f"]))
			continue
		var s := Sprite2D.new()
		s.texture = tex
		s.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
		# sort key = position.y = ground line ของ cell (เท่ากับเท้า agent ที่ place_at)
		# offset ดันรูปขึ้นครึ่งสูง → ฐาน sprite แตะพื้น tile พอดี (y-sort ตรง)
		# "r" = ยกเพิ่ม (ของแขวนผนัง เช่น whiteboard) — sort key คงที่ ภาพลอยขึ้น
		var raise: float = item.get("r", 0.0)
		s.position = Iso.grid_to_screen(item["c"] as Vector2i)
		# "fc" = footprint base-center (px ใน sprite) → จัดให้จุดนี้ตรงกลาง cell "c" เป๊ะ
		#        (ของยาวหลาย tile: c = cell กลางของช่วงที่คลุม) — sort key = ground line ของ c
		# ไม่มี fc = ของ 1 tile แบบเดิม (ฐานแตะพื้น จัดกลางแนวนอน)
		var fcv: Variant = item.get("fc", FC.get(str(item["f"])))
		if fcv != null:
			var fc: Vector2 = fcv
			s.offset = Vector2(tex.get_width() / 2.0 - fc.x,
				tex.get_height() / 2.0 - fc.y - raise)
		else:
			s.offset = Vector2(0, -tex.get_height() / 2.0 - raise)
		s.y_sort_enabled = true
		_world.add_child(s)


func _add_wall(tex: Texture2D, grid: Vector2i) -> void:
	var s := Sprite2D.new()
	s.texture = tex
	# wall sprite สูง 96 — origin อยู่กลางภาพ ดังนั้น offset ขึ้น (96-32)/2
	s.position = Iso.grid_to_screen(grid) - Vector2(0, (96 - 32) / 2.0)
	s.y_sort_enabled = true
	_world.add_child(s)


func _build_zone_labels() -> void:
	for z in ZONES:
		var rect := z["rect"] as Rect2i
		var center := Vector2i(rect.position + rect.size / 2)
		var label := Label.new()
		label.text = z["name"]
		label.add_theme_color_override("font_color", z["color"])
		label.add_theme_font_size_override("font_size", 10)
		label.position = Iso.grid_to_screen(center) - Vector2(24, 6)
		label.modulate.a = 0.65
		_floor.add_child(label)
