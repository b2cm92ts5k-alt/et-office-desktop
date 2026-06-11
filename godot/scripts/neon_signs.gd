class_name NeonSign
extends Node2D
## ป้าย neon "ET OFFICE" บนผนังเหนือ office + flicker (M2-12)
## texture สลับได้ตาม convention: assets/sprites/furniture/sign_etoffice.png (160x48)
## glow = sprite ซ้ำแบบ additive — alpha สั่นแบบ noise + ดับวูบนาน ๆ ครั้งเหมือนนีออนจริง

const SIGN_TEXTURE := "res://assets/sprites/furniture/sign_etoffice.png"
const SIGN_GRID := Vector2i(9, 0)       # กึ่งกลางผนังด้านบน (แถว wall ที่ gy=0)
const SIGN_Y_OFFSET := -78.0            # สูงบนผนัง — พ้น nameplate ของ agent โต๊ะกลาง (9,1)
const GLOW_BASE := 0.55                 # ความสว่าง glow ปกติ
const GLOW_NOISE := 0.18                # ช่วงสั่นของ glow
const BLINK_CHANCE := 0.003             # โอกาสดับวูบต่อเฟรม (30fps ≈ ทุก ~11 วิ)
const BLINK_SEC := 0.12

var _base: Sprite2D
var _glow: Sprite2D
var _blink_until := 0.0
var _t := 0.0


func _ready() -> void:
	position = Iso.grid_to_screen(SIGN_GRID) + Vector2(0, SIGN_Y_OFFSET)
	var tex: Texture2D = load(SIGN_TEXTURE)

	_base = Sprite2D.new()
	_base.texture = tex
	_base.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	add_child(_base)

	_glow = Sprite2D.new()
	_glow.texture = tex
	_glow.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	_glow.scale = Vector2(1.04, 1.1)  # ฟุ้งออกนอกขอบนิดเดียว
	var mat := CanvasItemMaterial.new()
	mat.blend_mode = CanvasItemMaterial.BLEND_MODE_ADD
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
	# สั่นแบบสุ่มนุ่ม ๆ — ผสมคลื่นสองความถี่กัน beat ตายตัว
	_glow.modulate.a = GLOW_BASE \
		+ sin(_t * 7.3) * GLOW_NOISE * 0.5 \
		+ sin(_t * 1.7) * GLOW_NOISE * 0.5
