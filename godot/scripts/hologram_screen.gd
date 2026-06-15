extends Node2D
class_name HologramScreen
## M3-7 — จอ hologram บน desk: overlay ทับมอนิเตอร์ furniture แล้วสลับอนิเมชันตาม state
## วาง position = cell เดียวกับ desk/agent (y-sort คีย์เท่ากัน) แล้ว offset เฉพาะ "ภาพ"
##   ขึ้นไปที่มอนิเตอร์ (VIS) — ไม่ใช้ position.y offset (จะหลุด y-sort ไปอยู่หลัง desk)
## agent อยู่โต๊ะ (idle/working/thinking) → จอติดเล่นอนิเมชัน · ไม่อยู่ → จอดับ (มืด)
## เพิ่ม state: วาดแถวใน gen_holo_content.py แล้ว map ใน STATE_ROW/FLASH_ROW

const CONTENT_TEX := "res://assets/sprites/fx/holo_content.png"
const COLS := 4
const ROWS := 5
const FPS := 6.0
const VIS := Vector2(0, -21)             # ตำแหน่งจอมอนิเตอร์ใน desk_agent (pixel 32,23 → cell-21)
const HALF := Vector2(10, 6)             # ครึ่งขนาดจอ ~ มอนิเตอร์ furniture (18×10)
const CYAN := Color(0, 0.898, 1.0)
const FLASH_SEC := 1.0

# status → แถว content; ไม่มีใน map = agent ไม่อยู่โต๊ะ → จอดับ
const STATE_ROW := {
	"idle": 0, "working": 1, "thinking": 2,
}
const FLASH_ROW := {"done": 3, "error": 4}

var _content: Sprite2D
var _row: int = 0                        # แถวตาม status ปัจจุบัน (-1 = ดับ)
var _frame: float = 0.0
var _flash_left: float = 0.0
var _flash_row: int = -1


func _ready() -> void:
	_content = Sprite2D.new()
	_content.texture = load(CONTENT_TEX)
	_content.hframes = COLS
	_content.vframes = ROWS
	_content.frame = 0
	_content.position = VIS
	_content.scale = Vector2(0.7, 0.7)   # 24×16 → ~17×11 พอดีมอนิเตอร์
	_content.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	add_child(_content)
	set_state("idle")


func set_state(status: String) -> void:
	_row = STATE_ROW.get(status, -1)
	if _flash_left <= 0.0:
		_content.visible = _row >= 0      # ดับ = ซ่อนเนื้อจอ (เหลือกรอบมืด)
	queue_redraw()


func flash(kind: String) -> void:
	## โชว์ done/error แวบเดียวแล้วกลับ state เดิม (เรียกตอน task.completed/failed)
	if not FLASH_ROW.has(kind):
		return
	_flash_row = FLASH_ROW[kind]
	_flash_left = FLASH_SEC
	_content.visible = true
	queue_redraw()


func _process(delta: float) -> void:
	var row := _row
	if _flash_left > 0.0:
		_flash_left -= delta
		row = _flash_row
		if _flash_left <= 0.0:
			_content.visible = _row >= 0
			queue_redraw()
	elif _row < 0:
		return                            # จอดับ — ไม่ต้องเดินเฟรม
	_frame = fmod(_frame + FPS * delta, float(COLS))
	_content.frame = maxi(0, row) * COLS + int(_frame)


func _draw() -> void:
	# กรอบ cyan + backing + scanline — สว่างเมื่อติด, หรี่ลงเมื่อจอดับ (agent ไม่อยู่โต๊ะ)
	var lit := _row >= 0 or _flash_left > 0.0
	var rect := Rect2(VIS - HALF, HALF * 2.0)
	draw_rect(rect, Color(0, 0.13, 0.18, 0.55) if lit else Color(0, 0.03, 0.05, 0.7), true)
	draw_rect(rect, Color(CYAN, 0.85) if lit else Color(CYAN, 0.22), false, 1.0)
	var y := VIS.y - HALF.y + 1.0
	while y < VIS.y + HALF.y:
		draw_line(Vector2(VIS.x - HALF.x, y), Vector2(VIS.x + HALF.x, y),
			Color(CYAN, 0.12 if lit else 0.04), 1.0)
		y += 2.0
