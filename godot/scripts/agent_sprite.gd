extends Node2D
class_name AgentSprite
## Pixel agent character (M3-1) — spritesheet ตาม docs/ART-SPEC.md
## โหลดไฟล์ตาม convention: res://assets/sprites/characters/char_<sprite_key>.png
## เปลี่ยน asset ทีหลัง: วางไฟล์ชื่อเดิม layout เดิมทับได้เลย ไม่ต้องแก้โค้ด
## ถ้า layout เปลี่ยน แก้ค่ากลุ่ม const ด้านล่างที่เดียว

const SHEET_DIR := "res://assets/sprites/characters/"
const FRAME_COLS := 6        # walk 6 เฟรม
const FRAME_ROWS := 4        # ทิศ: SE, SW, NE, NW
const WALK_FPS := 8.0        # ตาม ART-SPEC
const WALK_SPEED := 48.0     # px/วินาที (1.5 tiles/s)

enum Facing { SE = 0, SW = 1, NE = 2, NW = 3 }

const SLEEP_TINT := Color(0.55, 0.55, 0.75)  # ตัวหม่นลงตอนหลับ (M3-5)

signal arrived

var agent_id: String = ""
var agent_name: String = ""
var aura_color: Color = Color("#00e5ff")
var status: String = "idle"

var _sprite: Sprite2D
var _name_label: Label
var _aura: NeonAura
var _zzz: Label
var _zzz_t: float = 0.0
var _sleep_visual := false
var _facing: int = Facing.SE
var _walk_frame: float = 0.0
var _path: Array[Vector2i] = []
var _grid_pos: Vector2i = Vector2i.ZERO


func setup(id: String, display_name: String, sprite_key: String, color: Color) -> void:
	agent_id = id
	agent_name = display_name
	aura_color = color

	# aura ก่อน sprite — child ลำดับแรกวาดอยู่ใต้ตัว
	_aura = NeonAura.new(color)
	add_child(_aura)

	_sprite = Sprite2D.new()
	var path := SHEET_DIR + "char_%s.png" % sprite_key
	if not ResourceLoader.exists(path):
		path = SHEET_DIR + "char_producer.png"  # fallback
	_sprite.texture = load(path)
	_sprite.hframes = FRAME_COLS
	_sprite.vframes = FRAME_ROWS
	_sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	# origin ที่เท้า (กึ่งกลางล่าง) — จำเป็นสำหรับ y-sort ตาม ART-SPEC
	_sprite.offset = Vector2(0, -float(_sprite.texture.get_height()) / FRAME_ROWS / 2.0)
	add_child(_sprite)

	_name_label = Label.new()
	_name_label.text = display_name
	_name_label.add_theme_font_size_override("font_size", 8)
	_name_label.add_theme_color_override("font_color", color)
	_name_label.position = Vector2(-20, -58)
	add_child(_name_label)

	_zzz = Label.new()
	_zzz.text = "Zzz"
	_zzz.add_theme_font_size_override("font_size", 8)
	_zzz.add_theme_color_override("font_color", Color("#4080ff"))
	_zzz.position = Vector2(8, -56)
	_zzz.visible = false
	add_child(_zzz)

	y_sort_enabled = true
	_update_frame()


func set_status(new_status: String) -> void:
	status = new_status
	_aura.set_status(new_status)
	if status != "sleep":
		_set_sleep_visual(false)


func _set_sleep_visual(on: bool) -> void:
	# ใช้ตอนถึง dorm แล้วเท่านั้น — ระหว่างเดินยังตัวสว่างปกติ
	if _sleep_visual == on:
		return
	_sleep_visual = on
	_sprite.modulate = SLEEP_TINT if on else Color.WHITE
	_zzz.visible = on


func place_at(grid: Vector2i) -> void:
	_grid_pos = grid
	position = Iso.grid_to_screen(grid)


func walk_path(path: Array[Vector2i]) -> void:
	# path จาก OfficeNav — ตัด cell แรกถ้าคือตำแหน่งปัจจุบัน
	_path = path.duplicate()
	if not _path.is_empty() and _path[0] == _grid_pos:
		_path.pop_front()


func grid_pos() -> Vector2i:
	return _grid_pos


func is_walking() -> bool:
	return not _path.is_empty()


func _process(delta: float) -> void:
	if _sleep_visual:
		_zzz_t += delta
		_zzz.position.y = -56.0 + sin(_zzz_t * 2.0) * 2.0  # Zzz ลอยขึ้นลงเบา ๆ

	if _path.is_empty():
		if _walk_frame != 0.0:  # หยุดเดิน → เฟรมยืน
			_walk_frame = 0.0
			_update_frame()
		if status == "sleep" and not _sleep_visual:
			_set_sleep_visual(true)
		return

	var target := Iso.grid_to_screen(_path[0])
	var diff := target - position
	var step := WALK_SPEED * delta
	if diff.length() <= step:
		position = target
		_grid_pos = _path.pop_front()
		if _path.is_empty():
			arrived.emit()
	else:
		position += diff.normalized() * step
		_set_facing_from(diff)

	_walk_frame = fmod(_walk_frame + WALK_FPS * delta, float(FRAME_COLS))
	_update_frame()


func _set_facing_from(diff: Vector2) -> void:
	# dimetric: ขวาล่าง=SE ซ้ายล่าง=SW ขวาบน=NE ซ้ายบน=NW
	if diff.y >= 0:
		_facing = Facing.SE if diff.x >= 0 else Facing.SW
	else:
		_facing = Facing.NE if diff.x >= 0 else Facing.NW


func _update_frame() -> void:
	_sprite.frame = _facing * FRAME_COLS + int(_walk_frame)
