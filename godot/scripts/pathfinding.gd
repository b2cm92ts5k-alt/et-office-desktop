class_name OfficeNav
## A* pathfinding บน office grid (M3-2) — ใช้ AStarGrid2D built-in ของ Godot
## grid 18x12 ตรงกับ office_builder — เพิ่ม obstacle ได้ภายหลัง (เฟอร์นิเจอร์ A-3)

var _astar := AStarGrid2D.new()


func _init(grid_w: int, grid_h: int) -> void:
	_astar.region = Rect2i(0, 0, grid_w, grid_h)
	_astar.diagonal_mode = AStarGrid2D.DIAGONAL_MODE_NEVER
	_astar.update()


func set_blocked(cell: Vector2i, blocked: bool) -> void:
	_astar.set_point_solid(cell, blocked)


func find_path(from: Vector2i, to: Vector2i) -> Array[Vector2i]:
	if not _astar.region.has_point(from) or not _astar.region.has_point(to):
		return []
	return _astar.get_id_path(from, to)
