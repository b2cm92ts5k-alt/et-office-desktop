extends Node2D
## Main scene boot — เชื่อม event client เข้า HUD (agent choreography มาใน M3)

@onready var _status_label: Label = $HudLayer/DaemonStatus
@onready var _ticker_label: Label = $HudLayer/EventTicker
@onready var _events: Node = $EventClient

var _ticker_lines: Array[String] = []


func _ready() -> void:
	print("[office] ET Office booted — wallpaper_mode=%s" % str(
		$WallpaperManager.wallpaper_mode))
	_events.connected.connect(_on_daemon_connected)
	_events.disconnected.connect(_on_daemon_disconnected)
	_events.event_received.connect(_on_event)
	_status_label.text = "● DAEMON: CONNECTING..."
	_status_label.add_theme_color_override("font_color", Color("#ffe040"))


func _on_daemon_connected() -> void:
	_status_label.text = "● DAEMON: ONLINE"
	_status_label.add_theme_color_override("font_color", Color("#00ff9f"))


func _on_daemon_disconnected() -> void:
	_status_label.text = "● DAEMON: OFFLINE — reconnecting"
	_status_label.add_theme_color_override("font_color", Color("#ff4060"))


func _on_event(event: Dictionary) -> void:
	var type := str(event.get("type", "?"))
	var data: Dictionary = event.get("data", {})
	var line := type
	match type:
		"agent.status":
			line = "%s → %s" % [str(data.get("agent_id", "?")).substr(0, 6),
								str(data.get("status", "?"))]
		"task.routing":
			line = "task → %s" % str(data.get("agent", "?"))
		"task.completed":
			line = "task done ✓"
		"task.failed":
			line = "task failed ✗"
	_ticker_lines.append(line)
	if _ticker_lines.size() > 5:
		_ticker_lines.pop_front()
	_ticker_label.text = "\n".join(_ticker_lines)
