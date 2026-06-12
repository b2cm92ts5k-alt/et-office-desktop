shader_type canvas_item;
// CRT overlay (M2-9) — scanline + vignette + rolling band บาง ๆ ทั้งจอ
// แปะบน ColorRect ใน CrtLayer (layer 2 — ทับ world + HUD)
// alpha ตั้งต่ำมาก: เป็น texture ของบรรยากาศ ไม่กวนการอ่าน desktop icon

uniform float line_count = 360.0;
uniform float line_alpha : hint_range(0.0, 0.5) = 0.07;
uniform float vignette_alpha : hint_range(0.0, 0.6) = 0.22;
uniform float roll_alpha : hint_range(0.0, 0.3) = 0.04;
uniform float roll_speed = 0.05;


void fragment() {
	// เส้น scanline แนวนอน
	float scan = line_alpha * (0.5 + 0.5 * sin(UV.y * line_count * TAU));
	// ขอบจอมืดแบบจอ CRT
	float vig = vignette_alpha * smoothstep(0.45, 0.78, distance(UV, vec2(0.5)));
	// แถบสว่าง (ลด darkening) กลิ้งลงจอช้า ๆ
	float roll = roll_alpha * smoothstep(0.8, 1.0, sin((UV.y - TIME * roll_speed) * TAU));
	COLOR = vec4(0.0, 0.0, 0.0, clamp(scan + vig - roll, 0.0, 1.0));
}
