shader_type canvas_item;
render_mode blend_add;
// Neon outer-glow (M2-8) — ฟุ้งรอบ texture ด้วย alpha blur 5x5 จุด
// ใช้กับ sprite glow ของ NeonSign — flicker คุมผ่าน modulate.a จากสคริปต์ตามเดิม
// (gl_compatibility ไม่มี 2D glow ใน Environment — ต้องทำใน shader เอง)

uniform vec4 glow_color : source_color = vec4(0.88, 0.25, 0.98, 1.0);
uniform float spread : hint_range(1.0, 24.0) = 8.0;     // รัศมีฟุ้ง (texel)
uniform float intensity : hint_range(0.0, 3.0) = 1.1;

varying vec4 v_modulate;


void vertex() {
	v_modulate = COLOR;
}


void fragment() {
	vec4 tex = texture(TEXTURE, UV);
	float halo = 0.0;
	for (int x = -2; x <= 2; x++) {
		for (int y = -2; y <= 2; y++) {
			vec2 off = vec2(float(x), float(y)) * TEXTURE_PIXEL_SIZE * spread * 0.5;
			halo += texture(TEXTURE, UV + off).a;
		}
	}
	halo /= 25.0;
	// แกนตัวอักษรคงสีเดิม ขอบฟุ้งออกเป็นสี glow
	vec3 rgb = mix(glow_color.rgb, tex.rgb, tex.a);
	float a = clamp(max(tex.a, halo * intensity), 0.0, 1.0);
	COLOR = vec4(rgb, a) * v_modulate;
}
