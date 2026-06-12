shader_type canvas_item;
// Reflective floor tiles (M2-9) — พื้นรับแสง neon จาง ๆ + gloss sweep วิ่งช้า ๆ
// ใช้ SCREEN_UV ให้ลายต่อเนื่องข้ามทุก tile (tile แชร์ ShaderMaterial ตัวเดียว)
// zone tint เดิมจาก office_builder ส่งผ่าน modulate (v_modulate) ตามปกติ
// ค่า strength ตั้งต่ำตามกฎ brightness ≤60% ใน ART-SPEC

uniform vec4 neon_a : source_color = vec4(0.88, 0.25, 0.98, 1.0);  // Neon Magenta
uniform vec4 neon_b : source_color = vec4(0.0, 0.90, 1.0, 1.0);    // Cyan
uniform float reflect_strength : hint_range(0.0, 1.0) = 0.14;
uniform float sweep_strength : hint_range(0.0, 1.0) = 0.10;
uniform float sweep_speed = 0.06;

varying vec4 v_modulate;


void vertex() {
	v_modulate = COLOR;
}


void fragment() {
	vec4 tex = texture(TEXTURE, UV);
	// แสง neon นวลจากแถวผนังด้านบนจอ ไล่จางลงด้านล่าง — เหมือนพื้นมันสะท้อนป้าย/ไฟผนัง
	float fall = 1.0 - SCREEN_UV.y;
	vec3 neon = mix(neon_a.rgb, neon_b.rgb, 0.5 + 0.5 * sin(TIME * 0.11 + SCREEN_UV.x * 5.0));
	vec3 ambient = neon * fall * fall * reflect_strength;
	// gloss sweep — แถบเงาวับทแยงกวาดผ่านพื้นช้า ๆ
	float band = sin((SCREEN_UV.x + SCREEN_UV.y * 0.6) * 4.0 - TIME * sweep_speed * TAU);
	float sweep = smoothstep(0.985, 1.0, band) * sweep_strength;
	vec3 rgb = tex.rgb + (ambient + vec3(sweep)) * tex.a;
	COLOR = vec4(rgb, tex.a) * v_modulate;
}
