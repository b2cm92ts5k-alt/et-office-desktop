class_name Iso
## Isometric (dimetric 2:1) coordinate helpers — M2-5
## grid: Vector2i ตำแหน่งบน office grid | screen: pixel position ใน world space
## สเปคจาก docs/ART-SPEC.md: tile 64x32, sort by (y สกรีน) = grid_x + grid_y

const TILE_W := 64
const TILE_H := 32


static func grid_to_screen(grid: Vector2i) -> Vector2:
	return Vector2(
		(grid.x - grid.y) * (TILE_W / 2.0),
		(grid.x + grid.y) * (TILE_H / 2.0),
	)


static func screen_to_grid(pos: Vector2) -> Vector2i:
	var gx := (pos.x / (TILE_W / 2.0) + pos.y / (TILE_H / 2.0)) / 2.0
	var gy := (pos.y / (TILE_H / 2.0) - pos.x / (TILE_W / 2.0)) / 2.0
	return Vector2i(roundi(gx), roundi(gy))
