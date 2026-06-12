extends Node2D
class_name AgentHud
## Per-agent HUD (M3-6) — nameplate (ชื่อ + status pill) + hologram speech bubble
## bubble texture สลับได้ตาม convention: assets/sprites/fx/bubble_9patch.png (A-6)
## ปรับ layout/สี ได้ที่กลุ่ม const ด้านล่างที่เดียว

const BUBBLE_TEXTURE := "res://assets/sprites/fx/bubble_9patch.png"
const BUBBLE_MARGIN := 8          # 9-patch margin ทุกด้าน
const BUBBLE_WIDTH := 116.0
const BUBBLE_MIN_HEIGHT := 24.0
const BUBBLE_Y := -100.0          # ฐาน bubble เหนือหัว (ก่อน bob)
const BUBBLE_BOB_PX := 2.0        # hologram ลอยขึ้นลง
const SAY_SECONDS := 7.0          # ข้อความ event ค้างกี่วินาที
const SAY_MAX_CHARS := 90
const NAME_Y := -64.0
const PILL_Y := -52.0
const TEXT_DARK := Color("#0a0a14")  # ตัวอักษรบน pill สีสว่าง

# สี pill ต่อ status — โทนเดียวกับ aura/zone (ART-SPEC)
const PILL_COLORS := {
	"idle":     Color("#8a8a9a"),
	"working":  Color("#00e5ff"),
	"thinking": Color("#b060f0"),
	"collab":   Color("#ff4da6"),
	"break":    Color("#ff6030"),
	"sleep":    Color("#4080ff"),
}

var _name_label: Label
var _pill: PanelContainer
var _pill_label: Label
var _pill_style: StyleBoxFlat
var _bubble: NinePatchRect
var _bubble_label: Label
var _thinking := false
var _say_until_ms := 0
var _t := 0.0


func setup(display_name: String, role_color: Color) -> void:
	_name_label = Label.new()
	_name_label.text = display_name
	_name_label.add_theme_font_size_override("font_size", 8)
	_name_label.add_theme_color_override("font_color", role_color)
	_name_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_name_label.custom_minimum_size = Vector2(80, 0)
	_name_label.position = Vector2(-40, NAME_Y)
	add_child(_name_label)

	_pill_style = StyleBoxFlat.new()
	_pill_style.bg_color = PILL_COLORS["idle"]
	_pill_style.set_corner_radius_all(4)
	_pill_style.content_margin_left = 4
	_pill_style.content_margin_right = 4
	_pill_style.content_margin_top = 0
	_pill_style.content_margin_bottom = 1
	_pill = PanelContainer.new()
	_pill.add_theme_stylebox_override("panel", _pill_style)
	_pill_label = Label.new()
	_pill_label.text = "IDLE"
	_pill_label.add_theme_font_size_override("font_size", 7)
	_pill_label.add_theme_color_override("font_color", TEXT_DARK)
	_pill.add_child(_pill_label)
	add_child(_pill)
	_center_pill()

	_bubble = NinePatchRect.new()
	_bubble.texture = load(BUBBLE_TEXTURE)
	_bubble.patch_margin_left = BUBBLE_MARGIN
	_bubble.patch_margin_right = BUBBLE_MARGIN
	_bubble.patch_margin_top = BUBBLE_MARGIN
	_bubble.patch_margin_bottom = BUBBLE_MARGIN
	_bubble.size = Vector2(BUBBLE_WIDTH, BUBBLE_MIN_HEIGHT)
	_bubble.visible = false
	var holo := ShaderMaterial.new()
	holo.shader = preload("res://shaders/hologram.gdshader")  # M2-8 — เฉพาะพื้น bubble, ตัวอักษร (child) ไม่โดน
	_bubble.material = holo
	_bubble_label = Label.new()
	_bubble_label.add_theme_font_size_override("font_size", 8)
	_bubble_label.add_theme_color_override("font_color", Color("#bff4ff"))
	_bubble_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_bubble_label.position = Vector2(6, 4)
	_bubble_label.size = Vector2(BUBBLE_WIDTH - 12, BUBBLE_MIN_HEIGHT - 8)
	_bubble.add_child(_bubble_label)
	add_child(_bubble)


func set_status(status: String) -> void:
	_pill_label.text = status.to_upper()
	_pill_style.bg_color = PILL_COLORS.get(status, PILL_COLORS["idle"])
	_center_pill()
	_thinking = status == "thinking"


func say(text: String, seconds: float = SAY_SECONDS) -> void:
	## โชว์ bubble ข้อความชั่วคราว (event จาก daemon) — ทับ bubble คิดชั่วคราว
	var clean := text.strip_edges().replace("\n", " ")
	if clean.length() > SAY_MAX_CHARS:
		clean = clean.substr(0, SAY_MAX_CHARS) + "…"
	_show_bubble(clean, true)
	_say_until_ms = Time.get_ticks_msec() + int(seconds * 1000.0)


func _process(delta: float) -> void:
	_t += delta
	var saying := Time.get_ticks_msec() < _say_until_ms
	if not saying:
		if _thinking:
			# hologram bubble ลอย + จุดคิดวน 3 จังหวะ (design doc §05 THINKING)
			_show_bubble("คิด" + ".".repeat(1 + int(_t * 2.0) % 3), false)
		elif _bubble.visible:
			_bubble.visible = false
	if _bubble.visible:
		_bubble.position.y = BUBBLE_Y - _bubble.size.y + sin(_t * 2.0) * BUBBLE_BOB_PX
		_bubble.modulate.a = 0.92 + sin(_t * 5.0) * 0.08  # ระยิบแบบ hologram


func _show_bubble(text: String, multiline: bool) -> void:
	_bubble_label.text = text
	var height := BUBBLE_MIN_HEIGHT
	if multiline:
		# คำนวณสูงตามข้อความ (ประมาณบรรทัดละ 12px ที่ font 8)
		var lines := ceili(_bubble_label.get_theme_font("font").get_string_size(
			text, HORIZONTAL_ALIGNMENT_LEFT, -1, 8).x / (BUBBLE_WIDTH - 12.0))
		height = maxf(BUBBLE_MIN_HEIGHT, 10.0 + lines * 12.0)
	_bubble.size = Vector2(BUBBLE_WIDTH, height)
	_bubble_label.size = Vector2(BUBBLE_WIDTH - 12, height - 8)
	_bubble.position = Vector2(-BUBBLE_WIDTH / 2.0, BUBBLE_Y - height)
	_bubble.visible = true


func _center_pill() -> void:
	_pill.reset_size()
	_pill.position = Vector2(-_pill.size.x / 2.0, PILL_Y)
