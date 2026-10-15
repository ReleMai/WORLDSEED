#version 330
in vec2 in_position;
in vec2 in_uv;
uniform vec2 u_viewport;
out vec2 v_uv;
out vec2 v_screen;
void main() {
    v_uv = in_uv;
    v_screen = in_position;
    gl_Position = vec4(2.0 * in_position.x / u_viewport.x - 1.0,
                       1.0 - 2.0 * in_position.y / u_viewport.y, 0.0, 1.0);
}
