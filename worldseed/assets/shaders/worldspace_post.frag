#version 330
// One-pass, read-only atmospheric composite of an already-authorized FBO.
// World-aligned field motion makes clouds/rain independent of camera travel.
uniform sampler2D u_scene;
uniform sampler2D u_cover;
uniform bool u_cover_enabled;
uniform vec2 u_viewport;
uniform vec2 u_world_origin;
uniform float u_clock;
uniform float u_sun;
uniform float u_rain;
uniform float u_snow;
uniform float u_fog;
uniform float u_cloud;
uniform vec2 u_wind;
uniform int u_light_count;
uniform vec4 u_light_posrad[8];
uniform vec3 u_light_color[8];
in vec2 v_uv;
out vec4 fragColor;

float hash12(vec2 v) { return fract(sin(dot(v,vec2(127.1,311.7))) * 43758.5453123); }
float smoothNoise(vec2 v) {
    vec2 i=floor(v), f=fract(v);
    f=f*f*(3.0-2.0*f);
    return mix(mix(hash12(i),hash12(i+vec2(1,0)),f.x),
               mix(hash12(i+vec2(0,1)),hash12(i+vec2(1,1)),f.x),f.y);
}
float cloudField(vec2 position) {
    vec2 uv=position/320.0;
    float c=smoothNoise(uv)*0.55 + smoothNoise(uv*2.03+17.3)*0.3
           + smoothNoise(uv*4.13+31.4)*0.15;
    return smoothstep(0.28,0.76,c);
}
float rainStreak(vec2 world, vec2 spacing, float speed, float depth) {
    // Analytic particles, not scrolling stripe textures. Back-tracing position
    // gives each falling drop a stable world-cell identity. In top-origin world
    // pixels positive Y is DOWN; adding a clock drift made the old rain rise.
    // Shearing by velocity aligns the tapered tail with the wind trajectory.
    float fall=max(120.0,speed+u_wind.y*14.0);
    float lean=(u_wind.x*30.0+5.0)/fall;
    vec2 p=vec2(world.x-world.y*lean,world.y-fall*u_clock);
    vec2 cell=floor(p/spacing), local=p-cell*spacing;
    vec2 key=cell+vec2(71.3,39.7)*depth;
    float identity=hash12(key);
    // Keep the entire short tail inside its cell: no clipped segment snapping
    // when a particle crosses a queried cell boundary, and no neighbor search.
    vec2 center=spacing*vec2(mix(.12,.88,identity),
                             mix(.35,.75,hash12(key+17.1)));
    float lengthPx=mix(8.0,23.0,hash12(key+49.3))*depth;
    float along=local.y-center.y;
    float progress=clamp((along+lengthPx)/lengthPx,0.0,1.0);
    float widthPx=mix(.55,1.05,hash12(key+91.4))*depth;
    // Derivatives belong to continuous coordinates. Taking fwidth(local.x)
    // across a wrapped cell edge creates camera-dependent bright grid seams.
    float aa=max(.45,fwidth(p.x)*.5);
    float across=1.0-smoothstep(widthPx*.25,widthPx+aa,
                               abs(local.x-center.x));
    float tail=smoothstep(-lengthPx,-lengthPx*.40,along) *
               (1.0-smoothstep(-.7,1.0,along));
    float taper=mix(.35,1.0,progress);
    float population=step(hash12(key+113.8),.10+.70*u_rain);
    return across*tail*taper*population*mix(.45,1.0,hash12(key+159.2));
}
float snowFlake(vec2 world) {
    vec2 drift=vec2(-u_wind.x*8.0,26.0+u_wind.y*4.0)*u_clock;
    vec2 p=(world+drift)/vec2(17.0,23.0);
    vec2 cell=floor(p), q=fract(p);
    vec2 center=vec2(hash12(cell+7.1),hash12(cell+31.8));
    return (1.0-smoothstep(0.04,0.17,distance(q,center)))*step(0.55,hash12(cell+41.3));
}
void main() {
    vec2 topScreen = vec2(v_uv.x, 1.0-v_uv.y) * u_viewport;
    vec2 world=topScreen+u_world_origin;
    vec4 original=texture(u_scene,vec2(v_uv.x,v_uv.y));
    // Remembered commands blend RGB but preserve transparent classification
    // alpha. Unknown samples have both RGB and alpha zero, so they stay black.
    // Stacked remembered props stay memory regardless of their layer count.
    // Legacy single-ground .1764 also fits this fallback classification.
    // Freeze memory instead of lighting/animating it. Do NOT test alpha<1: antialiased current
    // canopies also reduce destination alpha under standard sprite blending.
    if (original.a < 0.25) {
        fragColor=vec4(original.rgb,1.0);
        return;
    }
    // Cover can attenuate precipitation only after the existing current-sight
    // classification. It cannot light memory or introduce unknown pixels.
    float exposure = u_cover_enabled ? 1.0-texture(u_cover,v_uv).r : 1.0;
    float night=1.0-u_sun;
    // Twilight desaturation and moon blue are light grades, not a world-state query.
    vec3 nightGrade=vec3(0.38,0.48,0.72);
    vec3 sunGrade=vec3(1.02,0.98,0.94);
    vec3 grade=mix(nightGrade,sunGrade,u_sun);
    // Moving, smooth cloud penumbrae across the land; no camera-locked circles.
    vec2 cloudDrift=vec2(u_wind.x+0.25,u_wind.y+0.06)*u_clock*10.0;
    float cloud=cloudField(world-cloudDrift);
    float cloudShadow=u_cloud*cloud*(0.06+0.20*u_sun);
    vec3 scene=original.rgb*grade*(1.0-cloudShadow);
    // Each emissive light is evaluated in PIXELS and can brighten only an
    // existing scene pixel; shadows, NPC admission and roofs stay external.
    vec3 rainLight=vec3(0.0);
    for (int i=0;i<8;i++) {
        if(i>=u_light_count)break;
        vec4 l=u_light_posrad[i];
        float d=length(topScreen-l.xy)/max(1.0,l.z);
        float attenuation=pow(clamp(1.0-d,0.0,1.0),2.0)*l.w;
        scene += original.rgb * u_light_color[i] * attenuation*(0.65+0.25*night);
        rainLight += u_light_color[i]*attenuation*.16;
    }
    // Broad overlapping fog scales with cloudy humidity, not sprite FOW.
    float fogWave=smoothNoise(world/160.0+vec2(u_clock*.012,-u_clock*.008));
    float fogFine=smoothNoise(world/61.0+vec2(u_clock*.016,0.0));
    float fogOpacity=u_fog*(0.19+0.29*fogWave+0.17*fogFine);
    vec3 mistColor=mix(vec3(.12,.19,.24),vec3(.67,.72,.70),u_sun);
    scene=mix(scene,mistColor,clamp(fogOpacity,0.0,0.68));
    // Three sparse depth bands vary spacing, fall speed, width and exposure.
    // Independent non-integral spacing breaks the old 10x38-pixel stripe grid.
    // No simulation RNG, extra particles/buffers, readback or world queries.
    if (u_rain>0.0) {
        float rain=rainStreak(world,vec2(17.,61.),255.,.75)*.45
                  +rainStreak(world+vec2(137.,61.),vec2(17.,71.),350.,1.0)*.70
                  +rainStreak(world+vec2(53.,193.),vec2(25.,109.),470.,1.4)*.85;
        vec3 rainColor=vec3(.60,.70,.76)*(.08+.18*u_sun)+rainLight;
        scene+=rainColor*rain*u_rain*exposure;
    }
    float snow=snowFlake(world)*0.75+snowFlake(world*1.7+vec2(120.,37.))*0.25;
    scene+=vec3(0.76,0.85,0.91)*snow*u_snow*(0.23+0.12*u_sun)*exposure;
    // Fully opaque full-window presentation; HUD ownership remains caller-side.
    fragColor=vec4(clamp(scene,0.0,1.0),1.0);
}
