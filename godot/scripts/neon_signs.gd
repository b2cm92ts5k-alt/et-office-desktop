class_name NeonSign
extends Node2D
## ป้าย neon "ET OFFICE" บนผนังเหนือ office + flicker (M2-12)
## texture สลับได้ตาม convention: assets/sprites/furniture/sign_etoffice.png (160x48)
## glow = sprite ซ้ำแบบ additive — alpha สั่นแบบ noise + ดับวูบนาน ๆ ครั้งเหมือนนีออนจริง

const SIGN_TEXTURE := "res://assets/sprites/furniture/sign_etoffice.png"
# ป้ายอยู่บนผนัง N (gy=0, ด้านขวา) — sprite เอียง isometric ลาดลงขวาแนบระนาบกำแพงนี้
# (CEO ไกด์ มิ.ย.2026 — ย้ายจากผนัง W มาขวาตามกรอบชมพู)
const SIGN_GRID := Vector2i(9, 0)      # cell บนแนวผนัง N → sort key เท่าผนังช่วงนั้น
const SIGN_RAISE := -120.0               # ยกป้ายขึ้นเหนือสันกำแพง (อยู่ "ข้างบนกำแพง")
const SIGN_X_OFFSET := 0.0              # กึ่งกลางหน้าผนัง N
const GLOW_BASE := 0.55                 # ความสว่าง glow ปกติ
const GLOW_NOISE := 0.18                # ช่วงสั่นของ glow
const BLINK_CHANCE := 0.003             # โอกาสดับวูบต่อเฟรม (30fps ≈ ทุก ~11 วิ)
const BLINK_SEC := 0.12

const BUSY_BOOST := 0.30        # M22-4 — glow สว่างขึ้นเมื่อทีมยุ่ง (office คึกคัก)

var _base: Sprite2D
var _glow: Sprite2D
var _blink_until := 0.0
var _t := 0.0
var _busy := 0.0                # M22-4 — ระดับความยุ่งของทีม 0..1 (agent_manager อัปเดต)


func set_busy(level: float) -> void:
	# M22-4 — ambient office life: ทีมยุ่ง = ป้ายนีออนสว่าง+สั่นถี่ขึ้น (ออฟฟิศดูคึกคัก)
	_busy = clampf(level, 0.0, 1.0)


func _ready() -> void:
	add_to_group("neon_sign")   # M22-4 — ให้ agent_manager หา (ไม่ผูก path ตรง)
	# node.position = ground line ของผนัง W ที่ cell นี้ → y-sort วาดป้ายในเลเยอร์เดียว
	# กับผนัง (อยู่หน้าผนังช่วงบน) ส่วนตัวป้ายยกขึ้นเหนือกำแพงด้วย offset ของ sprite
	y_sort_enabled = true
	position = Iso.grid_to_screen(SIGN_GRID)
	var banner := Vector2(SIGN_X_OFFSET, SIGN_RAISE)
	var tex: Texture2D = load(SIGN_TEXTURE)

	_base = Sprite2D.new()
	_base.texture = tex
	_base.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	_base.position = banner
	add_child(_base)

	_glow = Sprite2D.new()
	_glow.texture = tex
	_glow.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	_glow.position = banner
	_glow.scale = Vector2(1.04, 1.1)  # ฟุ้งออกนอกขอบนิดเดียว
	var mat := ShaderMaterial.new()
	mat.shader = preload("res://shaders/neon_glow.gdshader")  # M2-8 — blend_add ในตัว shader
	_glow.material = mat
	add_child(_glow)


func _process(delta: float) -> void:
	_t += delta
	if randf() < BLINK_CHANCE:
		_blink_until = _t + BLINK_SEC
	if _t < _blink_until:  # นีออนดับวูบ
		_glow.modulate.a = 0.05
		_base.modulate.a = 0.45
		return
	_base.modulate.a = 1.0
	# สั่นแบบสุ่มนุ่ม ๆ — ผสมคลื่นสองความถี่กัน beat ตายตัว · ยุ่ง = สว่าง+ถี่ขึ้น (M22-4)
	var fast := 7.3 + _busy * 4.0
	_glow.modulate.a = GLOW_BASE + _busy * BUSY_BOOST \
		+ sin(_t * fast) * GLOW_NOISE * 0.5 \
		+ sin(_t * 1.7) * GLOW_NOISE * 0.5
