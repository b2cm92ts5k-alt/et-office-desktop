extends Node2D
## Main scene boot (placeholder จนกว่า isometric office จะมาใน M2-5..M2-7)


func _ready() -> void:
	print("[office] ET Office booted — wallpaper_mode=%s" % str(
		$WallpaperManager.wallpaper_mode))
