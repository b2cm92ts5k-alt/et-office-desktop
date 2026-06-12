shader_type canvas_item;
// Hologram (M2-8) — scanline เลื่อนขึ้น + flicker สุ่ม + ขอบ RGB แยกเล็กน้อย
// ใช้กับ speech bubble (hud.gd) — จอ desk ใช้ซ้ำได้ใน M3-7
// สี hologram หลักตาม ART-SPEC: Cyan #00E5FF

uniform vec4 tint : source_color = vec4(0.0, 0.9, 1.0, 1.0);
uniform float tint_mix : hint_range(0.0, 1.0) = 0.30;
uniform float line_count : hint_range(8.0, 200.0) = 48.0;
uniform float scroll_speed = 6.0;
uniform float rgb_shift_px : hint_range(0.0, 3.0) = 0.7;
uniform float flicker_amount : hint_range(0.0, 0.5) = 0.10;

varying vec4 v_modulate;


void vertex() {
	v_modulate = COLOR;
}


float hash(float n) {
	return fract(sin(n) * 43758.5453);
}


void fragment() {
	vec2 shift = vec2(rgb_shift_px, 0.0) * TEXTURE_PIXEL_SIZE;
	vec4 tex = texture(TEXTURE, UV);
	tex.r = texture(TEXTURE, UV - shift).r;
	tex.b = texture(TEXTURE, UV + shift).b;
	float scan = 0.82 + 0.18 * sin(UV.y * line_count * TAU - TIME * scroll_speed);
	float flick = 1.0 - flicker_amount * hash(floor(TIME * 24.0));
	vec3 rgb = mix(tex.rgb, tint.rgb, tint_mix) * scan * flick;
	COLOR = vec4(rgb, tex.a * (0.78 + 0.22 * scan) * flick) * v_modulate;
}
