class_name ConflictGuard
extends RefCounted
## ตรวจ wallpaper app ที่จะวาดทับเรา (M2-14) — เรียกก่อน attach เสมอ
## Wallpaper Engine: pause ได้จริงผ่าน `<exe> -control stop` / resume ด้วย `-control play`
## Lively: ไม่มี CLI ที่นิ่งพอ — แจ้งเตือนอย่างเดียว
## หมายเหตุ: ใช้ OS.execute (blocking) ได้ที่นี่ เพราะเรียกก่อน SetParent
## (gotcha จาก M2-2 เกิดเฉพาะ script ที่ส่ง window message กลับมาหาเรา)

# image name (พิมพ์เล็ก ไม่มี .exe) -> ชื่อ app ที่แสดงให้ user
const KNOWN := {
	"wallpaper32": "Wallpaper Engine",
	"wallpaper64": "Wallpaper Engine",
	"livelywpf": "Lively Wallpaper",
	"lively": "Lively Wallpaper",
}

var found_apps: Array[String] = []   # ชื่อ app ที่เจอ (unique)
var paused_exe := ""                 # path ของ Wallpaper Engine ที่เรา pause ไว้


func check_and_pause() -> Dictionary:
	"""ตรวจ + pause Wallpaper Engine ถ้าเจอ — คืน {found: [...], paused: bool}"""
	found_apps.clear()
	paused_exe = ""
	var out: Array = []
	OS.execute("powershell.exe", [
		"-NoProfile", "-Command",
		"Get-Process wallpaper32,wallpaper64,livelywpf,lively -ErrorAction SilentlyContinue"
		+ " | Select-Object -ExpandProperty Path",
	], out)
	var we_path := ""
	for line in str(out[0] if out.size() > 0 else "").split("\n"):
		var path := line.strip_edges()
		if path.is_empty():
			continue
		var image := path.get_file().get_basename().to_lower()
		if not KNOWN.has(image):
			continue
		var app: String = KNOWN[image]
		if app not in found_apps:
			found_apps.append(app)
		if app == "Wallpaper Engine":
			we_path = path

	if not we_path.is_empty():
		# สั่งตัว exe เดิม — instance ใหม่ส่งคำสั่งให้ตัวที่รันอยู่แล้วจบตัวเอง
		var code := OS.execute(we_path, ["-control", "stop"])
		if code == 0:
			paused_exe = we_path
	return {"found": found_apps.duplicate(), "paused": not paused_exe.is_empty()}


func resume() -> void:
	"""คืนสภาพ Wallpaper Engine ตอนเราออกจาก wallpaper mode"""
	if paused_exe.is_empty():
		return
	# create_process — ตอน shutdown ไม่อยากบล็อก แล้วไม่ต้องรอผล
	OS.create_process(paused_exe, ["-control", "play"])
	paused_exe = ""
