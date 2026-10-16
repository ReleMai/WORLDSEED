#version 330
uniform sampler2D u_texture;
uniform float u_opacity;
uniform vec3 u_ambient;
uniform vec2 u_fade_center;
uniform float u_fade_radius;
uniform float u_local_alpha;
uniform vec4 u_sight_edges;
uniform vec2 u_sight_center;
uniform float u_sight_radius;
uniform bool u_ground;
uniform sampler2D u_ground_w;
uniform sampler2D u_ground_e;
uniform sampler2D u_ground_n;
uniform sampler2D u_ground_s;
uniform sampler2D u_ground_nw;
uniform sampler2D u_ground_ne;
uniform sampler2D u_ground_sw;
uniform sampler2D u_ground_se;
uniform vec3 u_ground_world_transform;
uniform vec3 u_ground_colors[9];
uniform vec4 u_ground_widths;
in vec2 v_uv;
in vec2 v_screen;
out vec4 fragColor;

float groundHash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}
float groundNoise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 s = f * f * (3.0 - 2.0 * f);
    return mix(mix(groundHash(i), groundHash(i + vec2(1.0, 0.0)), s.x),
               mix(groundHash(i + vec2(0.0, 1.0)), groundHash(i + vec2(1.0)), s.x), s.y);
}
vec2 mirrorGround(vec2 p) {
    // A triangular wave is continuous even when source artwork itself does
    // not tile. Rotated, unequal scales suppress its original tile strokes.
    return 1.0 - abs(mod(p, 2.0) - 1.0);
}
vec4 groundMaterial(sampler2D image, vec3 palette, vec2 uvA, vec2 uvB, float shade) {
    vec4 detail = mix(texture(image, uvA), texture(image, uvB), .46);
    return vec4(mix(palette, detail.rgb, .32) * shade, detail.a);
}
float groundEdge(float distanceToEdge, float width) {
    if (width <= 0.0) return 0.0;
    return .5 * (1.0 - smoothstep(0.0, width, distanceToEdge));
}
vec4 groundTexel(vec2 world) {
    vec2 cell = fract(world);
    vec2 warp = vec2(groundNoise(world * .13 + 9.2),
                     groundNoise(world * .13 - 13.1)) - .5;
    vec2 p = world + warp * .85;
    mat2 rotateA = mat2(.92106, .38942, -.38942, .92106);
    mat2 rotateB = mat2(.45360, -.89121, .89121, .45360);
    vec2 uvA = mirrorGround(rotateA * p * .173 + vec2(.24, .63));
    vec2 uvB = mirrorGround(rotateB * p * .271 + vec2(.81, .19));
    float broad = groundNoise(world * .21 + warp * .7);
    float fine = groundNoise(world * 1.37 + vec2(4.7, 17.3));
    float grain = groundNoise(world * 23.7 + vec2(31.4, 8.7));
    float shade = .94 + .085 * broad + .025 * fine + .065 * (grain - .5);
    // Adjacent admitted cells use the same world-anchored width modulation.
    // At the boundary each material contributes exactly half, avoiding the
    // unrelated per-tile alpha masks that previously advertised the grid.
    float widthNoise = .82 + .36 * groundNoise(world * .81 + vec2(7.1, 2.4));
    vec4 widths = min(vec4(.5), u_ground_widths * widthNoise);
    bool west = cell.x < .5;
    bool north = cell.y < .5;
    float wx = groundEdge(west ? cell.x : 1.0-cell.x, west ? widths.x : widths.y);
    float wy = groundEdge(north ? cell.y : 1.0-cell.y, north ? widths.z : widths.w);
    vec4 horizontal;
    vec4 vertical;
    vec4 diagonal;
    if (west) horizontal = groundMaterial(u_ground_w, u_ground_colors[1], uvA, uvB, shade);
    else horizontal = groundMaterial(u_ground_e, u_ground_colors[2], uvA, uvB, shade);
    if (north) vertical = groundMaterial(u_ground_n, u_ground_colors[3], uvA, uvB, shade);
    else vertical = groundMaterial(u_ground_s, u_ground_colors[4], uvA, uvB, shade);
    if (north && west) diagonal = groundMaterial(u_ground_nw, u_ground_colors[5], uvA, uvB, shade);
    else if (north) diagonal = groundMaterial(u_ground_ne, u_ground_colors[6], uvA, uvB, shade);
    else if (west) diagonal = groundMaterial(u_ground_sw, u_ground_colors[7], uvA, uvB, shade);
    else diagonal = groundMaterial(u_ground_se, u_ground_colors[8], uvA, uvB, shade);
    vec4 center = groundMaterial(u_texture, u_ground_colors[0], uvA, uvB, shade);
    // Separable bilinear weights give the same four material contributions
    // from either side of an edge and all four sides of a mixed corner.
    // Nine bounded bindings require fewer than GL 3.3's 16 fragment units;
    // only four material functions contribute at any given pixel.
    return mix(mix(center, horizontal, wx), mix(vertical, diagonal, wx), wy);
}
void main() {
    // Source bytes and mesh UVs are both top-first. Ordinary sprites retain
    // their original UV/alpha behavior; only detached ground uses world UVs.
    vec4 texel;
    if (u_ground) {
        vec2 world = u_ground_world_transform.xy + v_screen * u_ground_world_transform.z;
        texel = groundTexel(world);
    } else {
        texel = texture(u_texture, v_uv);
    }
    float opacity = u_opacity;
    if (u_fade_radius > 0.0) {
        float distance_px = distance(v_screen, u_fade_center);
        float blend = smoothstep(u_fade_radius * 0.70, u_fade_radius, distance_px);
        opacity *= mix(u_local_alpha, 1.0, blend);
    }
    // Radial falloff fades ONLY pixels already authorized by circular LOS.
    // It never draws unknown geometry and does not affect frozen map memory.
    if (u_sight_radius > 0.0) {
        float reach = distance(v_screen,u_sight_center);
        opacity *= 1.0-smoothstep(u_sight_radius*0.925,
                                   u_sight_radius*1.075,
                                   reach);
    }
    // Entire attenuation lies INSIDE the presently admitted ground cell.
    // This is never applied to roofs, characters, moving creatures or memory.
    if (u_ground || dot(u_sight_edges,vec4(1.0))>0.0) {
        float west = 1.0 - smoothstep(0.0, 0.44, v_uv.x);
        float east = 1.0 - smoothstep(0.0, 0.44, 1.0-v_uv.x);
        float north = 1.0 - smoothstep(0.0, 0.44, v_uv.y);
        float south = 1.0 - smoothstep(0.0, 0.44, 1.0-v_uv.y);
        opacity *= (1.0-u_sight_edges.x*west)*(1.0-u_sight_edges.y*east)
                 *(1.0-u_sight_edges.z*north)*(1.0-u_sight_edges.w*south);
    }
    fragColor = vec4(texel.rgb * u_ambient, texel.a * opacity);
}
