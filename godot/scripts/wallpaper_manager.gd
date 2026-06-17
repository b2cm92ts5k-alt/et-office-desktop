extends Node
## WorkerW wallpaper embedding (M2-2)
## รัน Godot ด้วย `--wallpaper` (หลัง `--`) → ฝัง window ใต้ desktop icon ผ่าน tools/wallpaper.ps1
## spike M2-1 พิสูจน์แล้วว่า script ทำงานบน Win10/11

var wallpaper_mode: bool = false
var paused_by_fullscreen: bool = false
var _hwnd: int = 0
var _flag_path: String = ""
var _poll_timer: Timer
var _guard := ConflictGuard.new()  # M2-14


func _ready() -> void:
	if OS.get_name() != "Windows":
		return
	var args := PackedStringArray()
	args.append_array(OS.get_cmdline_args())
	args.append_array(OS.get_cmdline_user_args())
	_debug("ready args=%s user_args=%s" % [str(OS.get_cmdline_args()), str(OS.get_cmdline_user_args())])
	if "--qa-conflict" in args:
		_qa_conflict_cycle()
	elif "--wallpaper" in args:
		_embed_as_wallpaper()


func _qa_conflict_cycle() -> void:
	# QA M2-14: ตรวจ → pause → รอ 3 วิ → resume (โหมด window ไม่ attach)
	var info := _guard.check_and_pause()
	_debug("qa-conflict found=%s paused=%s" % [str(info["found"]), str(info["paused"])])
	_notify_conflict(info)
	if info["paused"]:
		await get_tree().create_timer(3.0).timeout
		_guard.resume()
		_debug("qa-conflict resumed")


func _debug(msg: String) -> void:
	# breadcrumb ลงไฟล์ — stdout ของ Godot บน Windows ถูก buffer จนอ่านไม่ได้ระหว่างรัน
	var f := FileAccess.open("user://wm_debug.txt", FileAccess.READ_WRITE if FileAccess.file_exists("user://wm_debug.txt") else FileAccess.WRITE)
	if f:
		f.seek_end()
		f.store_line(msg)
		f.close()


func _embed_as_wallpaper() -> void:
	_debug("embed start")
	# M2-14: pause wallpaper app ที่จะวาดทับ (Wallpaper Engine) ก่อน SetParent
	var conflict := _guard.check_and_pause()
	_debug("conflict found=%s paused=%s" % [str(conflict["found"]), str(conflict["paused"])])
	_notify_conflict(conflict)

	_hwnd = DisplayServer.window_get_native_handle(DisplayServer.WINDOW_HANDLE, 0)
	_debug("hwnd=%d" % _hwnd)

	# M12-1: ย้าย window ไปจอหลักก่อน attach — กันเปิดผิดจอ/เห็น wallpaper หลายจอ
	# (wallpaper.ps1 จะ reinforce อีกชั้นด้วยพิกัด relative-to-WorkerW)
	var ps := DisplayServer.get_primary_screen()
	DisplayServer.window_set_position(DisplayServer.screen_get_position(ps))
	DisplayServer.window_set_size(DisplayServer.screen_get_size(ps))
	_debug("placed on primary screen %d pos=%s size=%s" % [ps,
		str(DisplayServer.screen_get_position(ps)), str(DisplayServer.screen_get_size(ps))])
	var script_path := _wallpaper_script_path()
	_debug("script_path=%s" % script_path)
	if script_path.is_empty():
		push_error("[wallpaper] tools/wallpaper.ps1 not found")
		return

	# ห้ามใช้ OS.execute (blocking) — SetParent ใน script ต้องส่ง message แบบ sync
	# มาที่ window นี้ ถ้า main thread บล็อกอยู่จะ deadlock ทั้งคู่
	var pid := OS.create_process("powershell.exe", [
		"-NoProfile", "-ExecutionPolicy", "Bypass",
		"-File", script_path, "-Attach", str(_hwnd),
	])
	wallpaper_mode = pid > 0
	_debug("attach spawned pid=%d hwnd=%d" % [pid, _hwnd])
	if wallpaper_mode:
		Engine.max_fps = 30  # M2-3: ลด GPU load ใน wallpaper mode
		print("[wallpaper] attach spawned pid=%d hwnd=%d" % [pid, _hwnd])
		_start_fullscreen_watch()
	else:
		push_error("[wallpaper] failed to spawn attach process")


# --- M2-4: pause เมื่อมี fullscreen app ทับ ---

func _start_fullscreen_watch() -> void:
	_flag_path = ProjectSettings.globalize_path("user://fullscreen.flag")
	var watch_script := _wallpaper_script_path().get_base_dir().path_join("fullscreen-watch.ps1")
	OS.create_process("powershell.exe", [
		"-NoProfile", "-ExecutionPolicy", "Bypass",
		"-File", watch_script, "-OutFile", _flag_path,
		"-ParentPid", str(OS.get_process_id()),
	])
	_poll_timer = Timer.new()
	_poll_timer.wait_time = 1.0
	# ต้อง ALWAYS — ไม่งั้นตอน tree paused ตัว timer หยุดด้วยแล้วปลุกตัวเองกลับไม่ได้
	_poll_timer.process_mode = Node.PROCESS_MODE_ALWAYS
	_poll_timer.timeout.connect(_check_fullscreen_flag)
	add_child(_poll_timer)
	_poll_timer.start()


func _check_fullscreen_flag() -> void:
	if not FileAccess.file_exists(_flag_path):
		return
	var covered: bool = FileAccess.get_file_as_string(_flag_path).strip_edges() == "1"
	if covered == paused_by_fullscreen:
		return
	paused_by_fullscreen = covered
	if covered:
		Engine.max_fps = 2          # GPU เกือบ 0 ระหว่างถูกทับ
		get_tree().paused = true
		_debug("paused (fullscreen app detected)")
	else:
		Engine.max_fps = 30
		get_tree().paused = false
		_debug("resumed")


func _wallpaper_script_path() -> String:
	# dev: tools/ เป็น sibling ของ godot/ | exported: โฟลเดอร์ tools/ ข้าง .exe
	var dev := ProjectSettings.globalize_path("res://").path_join(
		"../tools/wallpaper.ps1").simplify_path()
	if FileAccess.file_exists(dev):
		return dev
	var packaged := OS.get_executable_path().get_base_dir().path_join(
		"tools/wallpaper.ps1").simplify_path()
	if FileAccess.file_exists(packaged):
		return packaged
	_debug("script not found — tried: %s | %s" % [dev, packaged])
	return ""


func _notify_conflict(info: Dictionary) -> void:
	# แจ้ง user ผ่าน daemon → sidebar feed + tray toast (เงียบ ๆ ถ้า daemon ยังไม่ขึ้น)
	if (info["found"] as Array).is_empty():
		return
	var req := HTTPRequest.new()
	add_child(req)
	req.request_completed.connect(func(_r, _c, _h, _b): req.queue_free())
	req.request("http://localhost:8797/event",
		["Content-Type: application/json"], HTTPClient.METHOD_POST,
		JSON.stringify({"type": "wallpaper.conflict", "data": {
			"apps": info["found"], "paused": info["paused"],
		}}))


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST and wallpaper_mode:
		_detach()


func _detach() -> void:
	_guard.resume()  # M2-14: คืน Wallpaper Engine ให้ user
	var script_path := _wallpaper_script_path()
	if script_path.is_empty() or _hwnd == 0:
		return
	OS.create_process("powershell.exe", [
		"-NoProfile", "-ExecutionPolicy", "Bypass",
		"-File", script_path, "-Detach", str(_hwnd),
	])
	wallpaper_mode = false
	print("[wallpaper] detach spawned")
