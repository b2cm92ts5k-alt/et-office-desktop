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

@onready var _floor: Node2D = $Floor
@onready var _world: Node2D = $World


func _ready() -> void:
	_build_floor()
	_build_walls()
	_build_zone_labels()
	add_child(NeonSign.new())  # ป้าย ET OFFICE บนผนัง (M2-12) — child ท้ายสุด วาดทับผนัง


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
		_add_wall(_wall_w, Vector2i(0, gy))
	for gx in GRID_W:
		_add_wall(_wall_n, Vector2i(gx, 0))


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
