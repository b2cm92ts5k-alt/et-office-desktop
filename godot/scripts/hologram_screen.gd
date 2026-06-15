extends Node2D
class_name HologramScreen
## M3-7 — จอ hologram บน desk: เนื้อจอ (holo_content) สลับอนิเมชันตาม state ของ agent
## content = Sprite2D 4 คอลัมน์ × 5 แถว (state) · กรอบ cyan + scanline วาดเองใน _draw()
##   (เลี่ยง NinePatchRect/TextureRect ใน Node2D)
## ใช้: set_state(status) เมื่อ status เปลี่ยน, flash("done"/"error") ตอนงานจบ/ล้มเหลว
## เพิ่ม state: วาดแถวใหม่ใน gen_holo_content.py แล้ว map ใน STATE_ROW/FLASH_ROW

const CONTENT_TEX := "res://assets/sprites/fx/holo_content.png"
const COLS := 4
const ROWS := 5
const FPS := 6.0
const HALF := Vector2(13, 9)            # ครึ่งขนาดจอ (เนื้อ 24×16 + ขอบ 1px)
const CYAN := Color(0, 0.898, 1.0)
const FLASH_SEC := 1.0

# status → แถว content; ไม่มีใน map = agent ไม่อยู่โต๊ะ → ซ่อนจอ
const STATE_ROW := {
	"idle": 0, "working": 1, "thinking": 2,
}
const FLASH_ROW := {"done": 3, "error": 4}

var _content: Sprite2D
var _row: int = 0                       # แถวตาม status ปัจจุบัน (-1 = ซ่อน)
var _frame: float = 0.0
var _flash_left: float = 0.0
var _flash_row: int = -1


func _ready() -> void:
	_content = Sprite2D.new()
	_content.texture = load(CONTENT_TEX)
	_content.hframes = COLS
	_content.vframes = ROWS
	_content.frame = 0
	_content.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	add_child(_content)
	z_index = 50                        # เหนือ desk furniture, ใต้ FX (100)
	set_state("idle")


func set_state(status: String) -> void:
	_row = STATE_ROW.get(status, -1)
	visible = _row >= 0 or _flash_left > 0.0
	queue_redraw()


func flash(kind: String) -> void:
	## โชว์ done/error แวบเดียวแล้วกลับ state เดิม (เรียกตอน task.completed/failed)
	if not FLASH_ROW.has(kind):
		return
	_flash_row = FLASH_ROW[kind]
	_flash_left = FLASH_SEC
	visible = true
	queue_redraw()


func _process(delta: float) -> void:
	if not visible:
		return
	var row := _row
	if _flash_left > 0.0:
		_flash_left -= delta
		row = _flash_row
		if _flash_left <= 0.0:
			visible = _row >= 0
	elif _row < 0:
		return
	_frame = fmod(_frame + FPS * delta, float(COLS))
	_content.frame = maxi(0, row) * COLS + int(_frame)


func _draw() -> void:
	# backing โปร่งเข้ม + กรอบ cyan + scanline จาง
	var rect := Rect2(-HALF, HALF * 2.0)
	draw_rect(rect, Color(0, 0.15, 0.2, 0.55), true)
	draw_rect(rect, Color(CYAN, 0.9), false, 1.0)
	var y := -HALF.y + 1.0
	while y < HALF.y:
		draw_line(Vector2(-HALF.x, y), Vector2(HALF.x, y), Color(CYAN, 0.12), 1.0)
		y += 2.0
