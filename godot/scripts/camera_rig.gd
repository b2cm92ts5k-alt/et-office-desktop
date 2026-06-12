extends Camera2D
## Camera rig — จัดให้ office อยู่กึ่งกลางจอเสมอ (คำนวณจากขนาด grid จริง)
## zoom 1.25: office กว้าง 960*1.25 = 1200px บนจอ 1920 → เหลือขอบข้างละ 360px
## พอให้ sidebar (expand 320px) เปิดได้โดยไม่บังตัว office — ปรับที่ camera_zoom ที่เดียว

const WALL_TOP_PX := 80.0  # ยอดผนังเหนือแถว grid บนสุด: offset 32 + ครึ่ง sprite 96/2

@export var camera_zoom := 1.25

@onready var _builder = get_node("../OfficeBuilder")


func _ready() -> void:
	var w: int = _builder.GRID_W
	var h: int = _builder.GRID_H
	var left := Iso.grid_to_screen(Vector2i(0, h - 1)).x - Iso.TILE_W / 2.0
	var right := Iso.grid_to_screen(Vector2i(w - 1, 0)).x + Iso.TILE_W / 2.0
	var bottom := Iso.grid_to_screen(Vector2i(w - 1, h - 1)).y + Iso.TILE_H / 2.0
	position = Vector2((left + right) / 2.0, (-WALL_TOP_PX + bottom) / 2.0)
	zoom = Vector2(camera_zoom, camera_zoom)
