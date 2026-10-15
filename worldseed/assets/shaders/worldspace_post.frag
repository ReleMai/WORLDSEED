#version 330
// One-pass, read-only atmospheric composite of an already-authorized FBO.
// World-aligned field motion makes clouds/rain independent of camera travel.
uniform sampler2D u_scene;
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
float rainStreak(vec2 world) {
    // Narrow slanted streaks; two independently phased cells at different scales.
    vec2 drift=vec2(u_wind.x*20.0,230.0+u_wind.y*30.0)*u_clock;
    vec2 p=(world+drift)/vec2(10.0,38.0);
    vec2 ip=floor(p);
    vec2 fp=fract(p);
    float seed=hash12(ip);
    float x=fract(fp.x + fp.y*(0.22+0.10*u_wind.x));
    float streak=(1.0-smoothstep(0.016,0.10,abs(x-seed))) *
                 smoothstep(0.03,0.17,fp.y) * (1.0-smoothstep(0.70,0.98,fp.y));
    return streak * step(0.47,hash12(ip+19.9));
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
    // Live capture clears its scene target to transparent black. Fog, rain and
    // snow must not paint the unknown/private cells omitted by that capture.
    if (original.a <= 0.001) {
        fragColor=vec4(0.0,0.0,0.0,1.0);
        return;
    }
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
    for (int i=0;i<8;i++) {
        if(i>=u_light_count)break;
        vec4 l=u_light_posrad[i];
        float d=length(topScreen-l.xy)/max(1.0,l.z);
        float attenuation=pow(clamp(1.0-d,0.0,1.0),2.0)*l.w;
        scene += original.rgb * u_light_color[i] * attenuation*(0.65+0.25*night);
    }
    // Broad overlapping fog scales with cloudy humidity, not sprite FOW.
    float fogWave=smoothNoise(world/160.0+vec2(u_clock*.012,-u_clock*.008));
    float fogFine=smoothNoise(world/61.0+vec2(u_clock*.016,0.0));
    float fogOpacity=u_fog*(0.19+0.29*fogWave+0.17*fogFine);
    vec3 mistColor=mix(vec3(.12,.19,.24),vec3(.67,.72,.70),u_sun);
    scene=mix(scene,mistColor,clamp(fogOpacity,0.0,0.68));
    // Precipitation in two depth bands. Weather sprites never become click/LOS
    // targets; their world position moves with wind, not with the player.
    float rain=rainStreak(world)*0.70 + rainStreak(world*1.33+vec2(220.,83.))*0.30;
    scene+=vec3(0.61,0.75,0.85)*rain*u_rain*(0.16+0.12*u_sun);
    float snow=snowFlake(world)*0.75+snowFlake(world*1.7+vec2(120.,37.))*0.25;
    scene+=vec3(0.76,0.85,0.91)*snow*u_snow*(0.23+0.12*u_sun);
    // Fully opaque full-window presentation; HUD ownership remains caller-side.
    fragColor=vec4(clamp(scene,0.0,1.0),1.0);
}
