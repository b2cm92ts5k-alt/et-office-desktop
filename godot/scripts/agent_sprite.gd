extends Node2D
class_name AgentSprite
## Pixel agent character (M3-1) — spritesheet ตาม docs/ART-SPEC.md
## โหลดไฟล์ตาม convention: res://assets/sprites/characters/char_<sprite_key>.png
## เปลี่ยน asset ทีหลัง: วางไฟล์ชื่อเดิม layout เดิมทับได้เลย ไม่ต้องแก้โค้ด
## ถ้า layout เปลี่ยน แก้ค่ากลุ่ม const ด้านล่างที่เดียว

const SHEET_DIR := "res://assets/sprites/characters/"
const SPRITES_URL := "http://localhost:8797/sprites/files/"  # custom sheet จาก daemon (M6-2 v2)
const FRAME_COLS := 6        # 6 คอลัมน์/แถว (จำนวนเฟรมจริงต่อท่าดูที่ ANIM)
const CELL_H := 48           # ความสูงต่อเฟรมคงที่ — แผ่นเต็ม v2 (192x528) มี 11 แถว
const WALK_SPEED := 48.0     # px/วินาที (1.5 tiles/s)

# M6-2b: เล่นอนิเมชัน idle/sit/sleep จาก spritesheet v2 (192x528, 11 แถว)
# row layout ตาม ART-SPEC §3: 0-3 walk · 4-7 idle · 8-9 sit(SE,SW) · 10 sleep
const ROW_WALK := 0
const ROW_IDLE := 4
const ROW_SIT := 8
const ROW_SLEEP := 10
# ต่อท่า: [row ฐาน, จำนวนเฟรม, fps, ต้องมีอย่างน้อยกี่แถวในแผ่น (back-compat)]
const ANIM := {
	"walk":  {"row": ROW_WALK,  "frames": 6, "fps": 8.0, "need": 4},
	"idle":  {"row": ROW_IDLE,  "frames": 4, "fps": 4.0, "need": 8},
	"sit":   {"row": ROW_SIT,   "frames": 4, "fps": 6.0, "need": 10},
	"sleep": {"row": ROW_SLEEP, "frames": 2, "fps": 2.0, "need": 11},
	"stand": {"row": ROW_WALK,  "frames": 1, "fps": 0.0, "need": 4},  # fallback แผ่น 192x192
}

enum Facing { SE = 0, SW = 1, NE = 2, NW = 3 }

const SLEEP_TINT := Color(0.55, 0.55, 0.75)  # ตัวหม่นลงตอนหลับ (M3-5)

signal arrived

var agent_id: String = ""
var agent_name: String = ""
var aura_color: Color = Color("#00e5ff")
var status: String = "idle"

var _sprite: Sprite2D
var _hud: AgentHud
var _aura: NeonAura
var _zzz: Label
var _zzz_t: float = 0.0
var _sleep_visual := false
var _facing: int = Facing.SE
var _anim: String = "stand"
var _anim_frame: float = 0.0
var _total_rows: int = 4         # จำนวนแถวจริงในแผ่น (192x192→4, 192x528→11)
var _path: Array[Vector2i] = []
var _grid_pos: Vector2i = Vector2i.ZERO


func setup(id: String, display_name: String, sprite_key: String, color: Color,
		custom_sprite: String = "") -> void:
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
	_total_rows = maxi(1, _sprite.texture.get_height() / CELL_H)  # 192x192→4, 192x528→11
	_sprite.hframes = FRAME_COLS
	_sprite.vframes = _total_rows
	_sprite.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	# origin ที่เท้า (กึ่งกลางล่าง) — จำเป็นสำหรับ y-sort ตาม ART-SPEC
	_sprite.offset = Vector2(0, -CELL_H / 2.0)
	add_child(_sprite)

	_hud = AgentHud.new()
	add_child(_hud)
	_hud.setup(display_name, color)

	_zzz = Label.new()
	_zzz.text = "Zzz"
	_zzz.add_theme_font_size_override("font_size", 8)
	_zzz.add_theme_color_override("font_color", Color("#4080ff"))
	_zzz.position = Vector2(16, -44)  # ข้างหัว — ไม่ทับ nameplate/pill
	_zzz.visible = false
	add_child(_zzz)

	y_sort_enabled = true
	_update_frame()

	if not custom_sprite.is_empty():
		_fetch_custom_sheet(custom_sprite)  # โหลดทับทีหลัง — ระหว่างรอใช้ตัว default ไปก่อน


func _fetch_custom_sheet(file: String) -> void:
	## spritesheet ที่ user อัพโหลด (M6-2 v2) — daemon validate ขนาดมาแล้ว
	## รองรับ 192x192 (เดิน 4 แถว) และ 192x528 (เต็ม 11 แถว — index แถวเดินตรงกัน)
	var req := HTTPRequest.new()
	add_child(req)
	req.request_completed.connect(func(_r: int, code: int, _h: PackedStringArray,
			body: PackedByteArray) -> void:
		req.queue_free()
		if code != 200:
			return  # โหลดไม่ได้ — อยู่กับตัว default ต่อ
		var img := Image.new()
		if img.load_png_from_buffer(body) != OK:
			return
		_total_rows = maxi(1, img.get_height() / CELL_H)
		_sprite.vframes = _total_rows
		_sprite.texture = ImageTexture.create_from_image(img)
		_sprite.offset = Vector2(0, -CELL_H / 2.0)
		_update_frame())
	req.request(SPRITES_URL + file)


func set_status(new_status: String) -> void:
	status = new_status
	_aura.set_status(new_status)
	_hud.set_status(new_status)
	if status != "sleep":
		_set_sleep_visual(false)


func say(text: String) -> void:
	_hud.say(text)


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
		_zzz.position.y = -44.0 + sin(_zzz_t * 2.0) * 2.0  # Zzz ลอยขึ้นลงเบา ๆ

	if not _path.is_empty():
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
	elif status == "sleep" and not _sleep_visual:
		_set_sleep_visual(true)

	_advance_anim(delta)


func _set_facing_from(diff: Vector2) -> void:
	# dimetric: ขวาล่าง=SE ซ้ายล่าง=SW ขวาบน=NE ซ้ายบน=NW
	if diff.y >= 0:
		_facing = Facing.SE if diff.x >= 0 else Facing.SW
	else:
		_facing = Facing.NE if diff.x >= 0 else Facing.NW


# --- animation state machine (M6-2b) ---------------------------------
# เลือกท่าจาก status/การเดินทุกเฟรม → เล่นวนตาม fps ของท่านั้น
# แผ่น 192x192 (ไม่มีแถว idle/sit/sleep) → fallback "stand" (ยืนนิ่ง walk เฟรม 0)

func _resolve_anim() -> String:
	if not _path.is_empty():
		return "walk"
	var want := "idle"
	if _sleep_visual:
		want = "sleep"
	elif status == "working":
		want = "sit"
	if _total_rows < int(ANIM[want]["need"]):
		return "stand"
	return want


func _advance_anim(delta: float) -> void:
	var anim := _resolve_anim()
	if anim != _anim:
		_anim = anim
		_anim_frame = 0.0
	var info: Dictionary = ANIM[anim]
	_anim_frame = fmod(_anim_frame + float(info["fps"]) * delta, float(info["frames"]))
	_update_frame()


func _anim_row(anim: String) -> int:
	match anim:
		"idle":
			return ROW_IDLE + _facing
		"sit":  # มีเฉพาะ SE/SW — facing ฝั่งขวา(SE/NE)=แถว SE, ฝั่งซ้าย(SW/NW)=แถว SW
			return ROW_SIT + (0 if _facing == Facing.SE or _facing == Facing.NE else 1)
		"sleep":
			return ROW_SLEEP
		_:  # walk / stand
			return ROW_WALK + _facing


func _update_frame() -> void:
	_sprite.frame = _anim_row(_anim) * FRAME_COLS + int(_anim_frame)
