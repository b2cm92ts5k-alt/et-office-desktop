extends Node2D
class_name FxFactory
## M3-8 — เล่น pixel FX flipbook (A-5) แบบ one-shot ตาม event แล้ว free ตัวเอง
## FX ทุกตัว: 32×32, 8 เฟรม strip แนวนอน @ 12fps (ตาม ART-SPEC §5)
## วางเป็น child ของ World layer — เรียก play()/play_event() จาก agent_manager
## เพิ่ม FX ใหม่: วางไฟล์ fx_<name>.png (8 เฟรม) ใน assets/sprites/fx/ แล้ว map ใน EVENT_FX

const FX_DIR := "res://assets/sprites/fx/"
const FRAMES := 8
const FPS := 12.0
const HEAD_OFFSET := Vector2(0, -56)  # ลอยเหนือหัว agent

# map event type (จาก daemon WS) → ชื่อไฟล์ fx (ไม่มีนามสกุล)
const EVENT_FX := {
	"task.completed": "fx_done",
	"task.failed": "fx_error",
	"proposal.created": "fx_proposal",
	"task.working": "fx_working",
}

var _tex_cache: Dictionary = {}


func play_event(event_type: String, world_pos: Vector2) -> void:
	## เล่น FX ที่ map กับ event (เงียบถ้า event ไม่มี FX)
	if EVENT_FX.has(event_type):
		play(EVENT_FX[event_type], world_pos)


func play(fx_name: String, world_pos: Vector2) -> void:
	var tex := _load(fx_name)
	if tex == null:
		return
	var spr := Sprite2D.new()
	spr.texture = tex
	spr.hframes = FRAMES
	spr.vframes = 1
	spr.frame = 0
	spr.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST
	spr.position = world_pos + HEAD_OFFSET
	spr.z_index = 100  # เหนือ furniture/agent เสมอ
	add_child(spr)
	# tween เดินเฟรม 0..FRAMES-1 ตาม fps แล้วลบ — ไม่ผูก _process รายตัว
	var tw := create_tween()
	tw.tween_method(_set_frame.bind(spr), 0.0, float(FRAMES - 1), float(FRAMES) / FPS)
	tw.tween_callback(spr.queue_free)


func _set_frame(f: float, spr: Sprite2D) -> void:
	if is_instance_valid(spr):
		spr.frame = clampi(int(f), 0, FRAMES - 1)


func _load(fx_name: String) -> Texture2D:
	if _tex_cache.has(fx_name):
		return _tex_cache[fx_name]
	var path := FX_DIR + fx_name + ".png"
	if not ResourceLoader.exists(path):
		return null
	var tex: Texture2D = load(path)
	_tex_cache[fx_name] = tex
	return tex
