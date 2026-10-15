#version 330
in vec2 in_position;
in vec2 in_uv;
uniform vec2 u_viewport;
uniform float u_time;
uniform float u_sway_px;
out vec2 v_uv;
out vec2 v_screen;
void main() {
    v_uv = in_uv;
    v_screen = in_position;
    // Sway only the canopy top. The solid ground foot never moves.
    float topWeight = pow(1.0 - in_uv.y, 2.0);
    vec2 shifted = in_position + vec2(u_sway_px * topWeight * sin(u_time * 1.13 + in_position.x * 0.007), 0.0);
    gl_Position = vec4(2.0 * shifted.x / u_viewport.x - 1.0,
                       1.0 - 2.0 * shifted.y / u_viewport.y, 0.0, 1.0);
}
