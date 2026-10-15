#version 330
uniform sampler2D u_texture;
uniform float u_opacity;
uniform vec3 u_ambient;
uniform vec2 u_fade_center;
uniform float u_fade_radius;
uniform float u_local_alpha;
in vec2 v_uv;
in vec2 v_screen;
out vec4 fragColor;
void main() {
    // Uploaded PNG/pygame rows are top-to-bottom; GL texture rows start bottom.
    vec4 texel = texture(u_texture, vec2(v_uv.x, 1.0 - v_uv.y));
    float opacity = u_opacity;
    if (u_fade_radius > 0.0) {
        float distance_px = distance(v_screen, u_fade_center);
        float blend = smoothstep(u_fade_radius * 0.70, u_fade_radius, distance_px);
        opacity *= mix(u_local_alpha, 1.0, blend);
    }
    fragColor = vec4(texel.rgb * u_ambient, texel.a * opacity);
}
