#version 330
// Intercept precipitation with source alpha. Cosmetic player-reveal fades,
// color grades and ground material samplers do not participate in this pass.
uniform sampler2D u_texture;
in vec2 v_uv;
out vec4 fragColor;
void main() {
    fragColor = vec4(1.0, 1.0, 1.0, texture(u_texture, v_uv).a);
}
