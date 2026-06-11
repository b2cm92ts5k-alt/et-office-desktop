extends Node2D
class_name NeonAura
## Neon aura ring ใต้ตัว agent (M3-4) — Godot วาดเอง ไม่ฝังใน sprite (กฎจาก ART-SPEC)
## สีมาจาก role color ของ agent (daemon registry) — intensity ตาม status:
## IDLE=หรี่นิ่ง, WORKING=pulse เร็ว, THINKING=breathe ช้า, COLLAB=flash, BREAK=นวล, SLEEP=เกือบดับ
## ปรับจูนทั้งหมดได้ที่กลุ่ม const ด้านล่างที่เดียว

const RADIUS := 17.0      # รัศมีวง (px) ก่อนบีบแนวตั้งตาม perspective dimetric
const SQUASH := 0.5       # บีบแกน y เป็นวงรี 2:1 ให้แนบพื้น iso
const RING_WIDTH := 2.0
const GLOW_ALPHA := 0.30  # ความเข้ม fill กลางวงเทียบกับเส้น ring

# โหมดต่อ status: base=สว่างต่ำสุด, amp=ช่วงแกว่ง, hz=ความเร็วคลื่น, flash=กระพริบตัดฉับ
const MODES := {
	"idle":     {"base": 0.22, "amp": 0.00, "hz": 0.0, "flash": false},
	"working":  {"base": 0.45, "amp": 0.45, "hz": 3.0, "flash": false},
	"thinking": {"base": 0.30, "amp": 0.25, "hz": 0.5, "flash": false},
	"collab":   {"base": 0.15, "amp": 0.75, "hz": 2.5, "flash": true},
	"break":    {"base": 0.30, "amp": 0.10, "hz": 0.3, "flash": false},
	"sleep":    {"base": 0.07, "amp": 0.00, "hz": 0.0, "flash": false},
}

var color: Color = Color("#00e5ff")

var _mode: Dictionary = MODES["idle"]
var _t := 0.0
var _alpha: float = MODES["idle"]["base"]


func _init(aura_color: Color) -> void:
	color = aura_color
	# additive blend ให้แสงซ้อนกับพื้นแบบ neon ไม่ทึบทับ tile
	var mat := CanvasItemMaterial.new()
	mat.blend_mode = CanvasItemMaterial.BLEND_MODE_ADD
	material = mat


func set_status(status: String) -> void:
	_mode = MODES.get(status, MODES["idle"])


func _process(delta: float) -> void:
	_t += delta
	var a: float = _mode["base"]
	var amp: float = _mode["amp"]
	if amp > 0.0:
		var wave := sin(_t * TAU * float(_mode["hz"]))
		if _mode["flash"]:
			wave = signf(wave)  # คลื่นเหลี่ยม = เปิด/ปิดตัดฉับ
		a += amp * (wave * 0.5 + 0.5)
	if not is_equal_approx(a, _alpha):
		_alpha = a
		queue_redraw()


func _draw() -> void:
	draw_set_transform(Vector2.ZERO, 0.0, Vector2(1.0, SQUASH))
	var c := color
	c.a = _alpha * GLOW_ALPHA
	draw_circle(Vector2.ZERO, RADIUS, c)
	c.a = _alpha
	draw_arc(Vector2.ZERO, RADIUS, 0.0, TAU, 36, c, RING_WIDTH)
