extends CanvasModulate
## Day/night atmosphere (M2-11) — mood เปลี่ยนตามนาฬิกาจริง 4 ช่วง (design doc §04)
## CanvasModulate tint เฉพาะ office+agents (HUD/Background อยู่ CanvasLayer แยก —
## Background tint แยกผ่าน _bg เพื่อคุมความมืดของฉากหลัง)
## override จาก sidebar: WS event atmosphere.set {mode: dawn|day|golden|night|auto}
## ปรับสี/ช่วงเวลา ได้ที่ MODES/_clock_mode ที่เดียว

const MODES := {
	# canvas = tint โลก office, bg = สีฉากหลัง (ฐานเดิม #070510)
	"dawn":   {"canvas": Color(0.95, 0.88, 0.93), "bg": Color(0.050, 0.030, 0.072)},
	"day":    {"canvas": Color(1.0, 1.0, 1.0),    "bg": Color(0.027, 0.020, 0.059)},
	"golden": {"canvas": Color(1.0, 0.87, 0.70),  "bg": Color(0.055, 0.030, 0.047)},
	"night":  {"canvas": Color(0.60, 0.62, 0.95), "bg": Color(0.014, 0.011, 0.050)},
}
const FADE_SPEED := 1.2     # ความเร็ว lerp เปลี่ยนโหมด (ต่อวินาที)
const CHECK_SEC := 60.0     # auto mode เช็คนาฬิกาทุกกี่วินาที

var current_mode := "day"
var override_mode := ""     # "" = auto ตามนาฬิกา

var _target_canvas := Color.WHITE
var _target_bg := Color(0.027, 0.020, 0.059)

@onready var _bg: ColorRect = get_node("../BackgroundLayer/Background")
@onready var _events: Node = get_node("../EventClient")


func _ready() -> void:
	_events.event_received.connect(_on_event)
	_apply(_clock_mode(), true)  # บูตแล้วตรงเวลาเลย ไม่ fade

	var timer := Timer.new()
	timer.wait_time = CHECK_SEC
	timer.timeout.connect(_tick)
	add_child(timer)
	timer.start()


func _tick() -> void:
	if override_mode.is_empty():
		_apply(_clock_mode())


func _on_event(event: Dictionary) -> void:
	if str(event.get("type", "")) != "atmosphere.set":
		return
	var mode := str((event.get("data", {}) as Dictionary).get("mode", "auto"))
	if mode == "auto":
		override_mode = ""
		_apply(_clock_mode())
	elif MODES.has(mode):
		override_mode = mode
		_apply(mode)


func _clock_mode() -> String:
	var hour: int = Time.get_time_dict_from_system()["hour"]
	if hour >= 22 or hour < 6:
		return "night"    # DEEP NIGHT
	if hour < 12:
		return "dawn"     # DAWN BOOT
	if hour < 18:
		return "day"      # CYBER DAY
	return "golden"       # GOLDEN NEON


func _apply(mode: String, instant := false) -> void:
	current_mode = mode
	_target_canvas = MODES[mode]["canvas"]
	_target_bg = MODES[mode]["bg"]
	if instant:
		color = _target_canvas
		_bg.color = _target_bg


func _process(delta: float) -> void:
	if color.is_equal_approx(_target_canvas) and _bg.color.is_equal_approx(_target_bg):
		return
	color = color.lerp(_target_canvas, delta * FADE_SPEED)
	_bg.color = _bg.color.lerp(_target_bg, delta * FADE_SPEED)
