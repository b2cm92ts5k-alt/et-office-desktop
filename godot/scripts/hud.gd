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
const SAY_SECONDS := 7.0          # ข้อความ event ค้างกี่วินาที (ใช้เมื่อไม่คิดเวลาตามความยาว)
const SAY_MAX_CHARS := 140        # M22-1 — ขยายจาก 90 (bubble โตตามข้อความอยู่แล้ว)
const NAME_Y := -64.0
const PILL_Y := -52.0
const TEXT_DARK := Color("#0a0a14")  # ตัวอักษรบน pill สีสว่าง

# M22-1 — bubble/emote engine: emote ไอคอนเร็ว ๆ + typing indicator + หาง bubble + เวลาตามความยาว
const EMOTE_Y := -84.0            # emote ลอยเหนือ pill (ใต้ speech bubble) — ไม่ทับ nameplate
const EMOTE_SECONDS := 1.8        # emote ค้างกี่วินาที (สั้นกว่าข้อความ — เบา)
const EMOTE_POP_SEC := 0.18       # เด้งโต 0→เต็ม ตอนโผล่
const EMOTE_FADE_MS := 400.0      # จางหายช่วงท้าย
const TYPING_MS := 550            # โชว์ ". . ." ก่อนข้อความจริงโผล่ (เหมือนกำลังพิมพ์)
const SAY_MIN_SEC := 3.0          # เวลา bubble ขั้นต่ำ/สูงสุด (คิดตามความยาวข้อความ)
const SAY_MAX_SEC := 9.0
const SAY_SEC_PER_CHAR := 0.05
const TAIL_COLOR := Color("#0c2230", 0.85)  # หางชี้หัว agent — โทนเข้มเข้ากับพื้น bubble

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
var _tail: Polygon2D            # M22-1 — หางชี้หัว agent ที่พูด
var _emote: Label              # M22-1 — emote ไอคอนเร็ว (💡❓😅🔥👍💤 ฯลฯ)
var _thinking := false
var _say_until_ms := 0
var _say_text := ""            # ข้อความจริงที่จะโผล่หลัง typing
var _typing_until_ms := 0      # โชว์ ". . ." จนถึงเวลานี้ แล้วค่อยเผยข้อความ
var _say_revealed := false
var _emote_until_ms := 0
var _emote_t := 0.0
var _t := 0.0


func setup(display_name: String, role_color: Color) -> void:
	_name_label = Label.new()
	_name_label.text = display_name
	_name_label.add_theme_font_size_override("font_size", 8)
	# กันชื่อกลืนพื้นมืด: ดึงสีให้สว่างพอเสมอ (รักษาโทน) + outline ดำรอบตัวอักษร
	_name_label.add_theme_color_override("font_color", _readable(role_color))
	_name_label.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.9))
	_name_label.add_theme_constant_override("outline_size", 4)
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
	# M22-1 — หาง (tail) ชี้ลงหาหัว agent; child ของ bubble (เลื่อนตาม) แต่ไม่กิน hologram shader ของ parent
	_tail = Polygon2D.new()
	_tail.color = TAIL_COLOR
	_bubble.add_child(_tail)
	add_child(_bubble)

	# M22-1 — emote ไอคอนเร็ว: Label ลอยเหนือหัว เด้งโผล่แล้วจางหาย (ใช้ของที่มี = emoji/ข้อความ)
	_emote = Label.new()
	_emote.add_theme_font_size_override("font_size", 16)
	_emote.add_theme_color_override("font_color", Color("#ffffff"))
	_emote.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.9))
	_emote.add_theme_constant_override("outline_size", 4)
	_emote.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_emote.custom_minimum_size = Vector2(40, 0)
	_emote.position = Vector2(-20, EMOTE_Y)
	_emote.pivot_offset = Vector2(20, 10)   # เด้งจากจุดกึ่งกลาง
	_emote.visible = false
	add_child(_emote)


func set_status(status: String) -> void:
	_pill_label.text = status.to_upper()
	_pill_style.bg_color = PILL_COLORS.get(status, PILL_COLORS["idle"])
	_center_pill()
	_thinking = status == "thinking"


func say(text: String, seconds: float = -1.0) -> void:
	## โชว์ bubble ข้อความ (event จาก daemon) — M22-1: typing indicator ก่อน + เวลาตามความยาว
	var clean := text.strip_edges().replace("\n", " ")
	if clean.length() > SAY_MAX_CHARS:
		clean = clean.substr(0, SAY_MAX_CHARS) + "…"
	# เวลาแสดงผล: ถ้าไม่ระบุ → คิดตามความยาว (ข้อความสั้นหายเร็ว ยาวค้างนาน) คุมด้วย MIN/MAX
	var dur := seconds
	if dur < 0.0:
		dur = clampf(SAY_MIN_SEC + clean.length() * SAY_SEC_PER_CHAR, SAY_MIN_SEC, SAY_MAX_SEC)
	var now := Time.get_ticks_msec()
	_say_text = clean
	_say_revealed = false
	_typing_until_ms = now + TYPING_MS                       # โชว์ ". . ." ก่อน
	_say_until_ms = now + TYPING_MS + int(dur * 1000.0)


func emote(icon: String, seconds: float = EMOTE_SECONDS) -> void:
	## M22-1 — emote ไอคอนเร็ว ๆ เหนือหัว (เบากว่าข้อความเต็ม) ตอบเหตุการณ์/อารมณ์
	if _emote == null or icon.is_empty():
		return
	_emote.text = icon
	_emote.scale = Vector2.ONE
	_emote.modulate.a = 1.0
	_emote.visible = true
	_emote_t = 0.0
	_emote_until_ms = Time.get_ticks_msec() + int(seconds * 1000.0)


func _process(delta: float) -> void:
	_t += delta
	var now := Time.get_ticks_msec()
	var saying := now < _say_until_ms
	if saying:
		if now < _typing_until_ms:
			# typing indicator — ". . ." วน 3 จังหวะ (ดูเหมือนกำลังพิมพ์ก่อนข้อความโผล่)
			_show_bubble(". ".repeat(1 + int(_t * 4.0) % 3).strip_edges(), false)
			_say_revealed = false
		elif not _say_revealed:
			_show_bubble(_say_text, true)   # เผยข้อความจริง (เรนเดอร์ครั้งเดียว)
			_say_revealed = true
	elif _thinking:
		# hologram bubble ลอย + จุดคิดวน 3 จังหวะ (design doc §05 THINKING)
		_show_bubble("คิด" + ".".repeat(1 + int(_t * 2.0) % 3), false)
	elif _bubble.visible:
		_bubble.visible = false
	if _bubble.visible:
		_bubble.position.y = BUBBLE_Y - _bubble.size.y + sin(_t * 2.0) * BUBBLE_BOB_PX
		_bubble.modulate.a = 0.92 + sin(_t * 5.0) * 0.08  # ระยิบแบบ hologram

	# M22-1 — emote: เด้งโต→เต็ม ตอนโผล่, ลอยขึ้นเบา ๆ, จางหายช่วงท้าย
	if _emote != null and _emote.visible:
		_emote_t += delta
		var remain := _emote_until_ms - now
		if remain <= 0:
			_emote.visible = false
		else:
			var pop := 0.5 + 0.5 * minf(_emote_t / EMOTE_POP_SEC, 1.0)
			_emote.scale = Vector2(pop, pop)
			_emote.position.y = EMOTE_Y - _emote_t * 6.0
			_emote.modulate.a = clampf(remain / EMOTE_FADE_MS, 0.0, 1.0)


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
	# หางชี้ลงกึ่งกลางล่าง bubble → หาหัว agent (พิกัด local ของ bubble)
	var cx := BUBBLE_WIDTH / 2.0
	_tail.polygon = PackedVector2Array([
		Vector2(cx - 5.0, height - 1.0), Vector2(cx + 5.0, height - 1.0), Vector2(cx, height + 7.0)])
	_bubble.visible = true


func _center_pill() -> void:
	_pill.reset_size()
	_pill.position = Vector2(-_pill.size.x / 2.0, PILL_Y)


func _readable(c: Color) -> Color:
	# บังคับชื่อให้อ่านออกบนพื้นมืดเสมอ — ดันค่า value (HSV) ขึ้นถ้าเข้มเกิน, คงโทนสีเดิม
	# สีเกือบดำ/เทาเข้ม → กลายเป็นเทาสว่าง (s ต่ำ v สูง) ไม่ใช่สีทึบมองไม่เห็น
	var v: float = maxf(c.v, 0.82)
	return Color.from_hsv(c.h, c.s, v, 1.0)
