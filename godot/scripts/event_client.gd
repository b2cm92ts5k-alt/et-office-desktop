extends Node
## WebSocket client → daemon (M2-10)
## ต่อ ws://localhost:8797/ws — daemon จะ replay journal 100 events ล่าสุดให้เอง
## ตอน connect (event มี "replay": true) แล้ว stream realtime ต่อ
## หลุดเมื่อไหร่ retry อัตโนมัติทุก RECONNECT_DELAY วินาที

signal event_received(event: Dictionary)
signal replay_event(event: Dictionary)
signal connected
signal disconnected

const DAEMON_WS_URL := "ws://localhost:8797/ws"
const RECONNECT_DELAY := 3.0

var _socket := WebSocketPeer.new()
var _state := "disconnected"  # disconnected / connecting / connected
var _retry_timer: Timer


func _ready() -> void:
	# รับ event ต่อแม้ tree pause (fullscreen pause) — จะได้ไม่พลาด state จาก daemon
	process_mode = Node.PROCESS_MODE_ALWAYS
	_retry_timer = Timer.new()
	_retry_timer.one_shot = true
	_retry_timer.wait_time = RECONNECT_DELAY
	_retry_timer.process_mode = Node.PROCESS_MODE_ALWAYS
	_retry_timer.timeout.connect(_connect_to_daemon)
	add_child(_retry_timer)
	_connect_to_daemon()


func _connect_to_daemon() -> void:
	var err := _socket.connect_to_url(DAEMON_WS_URL)
	if err != OK:
		_schedule_retry()
		return
	_state = "connecting"


func _process(_delta: float) -> void:
	if _state == "disconnected":
		return
	_socket.poll()
	match _socket.get_ready_state():
		WebSocketPeer.STATE_OPEN:
			if _state != "connected":
				_state = "connected"
				print("[ws] connected to daemon")
				connected.emit()
			while _socket.get_available_packet_count() > 0:
				_handle_packet(_socket.get_packet().get_string_from_utf8())
		WebSocketPeer.STATE_CLOSED:
			if _state == "connected":
				print("[ws] connection lost — retrying in %.0fs" % RECONNECT_DELAY)
				disconnected.emit()
			_schedule_retry()


func _handle_packet(text: String) -> void:
	var data: Variant = JSON.parse_string(text)
	if typeof(data) != TYPE_DICTIONARY:
		return
	var event := data as Dictionary
	if event.get("replay", false):
		replay_event.emit(event)
	else:
		event_received.emit(event)


func _schedule_retry() -> void:
	_state = "disconnected"
	_socket = WebSocketPeer.new()  # ตัวเก่า reuse ไม่ได้หลัง close
	if _retry_timer.is_stopped():
		_retry_timer.start()


func is_daemon_connected() -> bool:
	return _state == "connected"
