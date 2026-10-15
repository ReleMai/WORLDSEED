"""Windows GPU-first G5/G6: a single OpenGL postprocess for sun, fires, fog, clouds, rain/snow.

Visual ONLY. No weather simulation, light propagation, LOS, stealth, time advance,
world generation, or game persistence. Source colors already represent authorized
world pixels; the shader never asks for terrain beyond current visibility.

The caller owns a single pygame OPENGL context and drives the frame loop. The
original software presentation module is not imported or modified.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import cos, isfinite, pi
from pathlib import Path
from struct import pack

from .gl_worldspace import GPUBackendUnavailable

MAX_LIGHTS = 8
MAX_FRAMEBUFFER_BYTES = 48 * 1024 * 1024
SHADER_DIR = Path(__file__).resolve().parents[1] / 'assets' / 'shaders'


def _finite(value):
    return type(value) in (int, float) and isfinite(value)


def daylight(minute: int) -> float:
    """Continuous and wrap-safe approximation, with a real dusk/dawn gradient."""
    if type(minute) is not int:
        raise ValueError('game minute must be an integer')
    hour = (minute % 1440) / 60.0
    # Solar altitude peaks at noon; below-horizon still leaves moonlight.
    solar = cos((hour - 12.0) * pi / 12.0)
    t = max(0., min(1., (solar + 0.23) / 1.17))
    t = t*t*(3 - 2*t)
    return 0.18 + 0.82*t


@dataclass(frozen=True, slots=True)
class WorldLight:
    """Bounded already-authorized visual light; screen xy, pixel radius."""
    x: float
    y: float
    radius: float
    strength: float
    color: tuple[float, float, float] = (1.0, 0.67, 0.36)

    def __post_init__(self):
        if any(not _finite(v) for v in (self.x,self.y,self.radius,self.strength,*self.color)):
            raise ValueError('light contains non-finite parameters')
        if not 1 <= self.radius <= 2048 or not 0 <= self.strength <= 2:
            raise ValueError('light out of bounded range')
        if len(self.color) != 3 or any(not 0 <= c <= 1. for c in self.color):
            raise ValueError('light color channels outside unit interval')


@dataclass(frozen=True, slots=True)
class AtmosphereFrame:
    """Read-only presentation inputs in world-pixel coordinates."""
    minute: int
    rain: float = 0.0
    snow: float = 0.0
    fog: float = 0.0
    cloud: float = 0.0
    wind_x: float = 0.0
    wind_y: float = 0.0
    elapsed_seconds: float = 0.0
    camera_pixel_x: float = 0.0
    camera_pixel_y: float = 0.0
    lights: tuple[WorldLight, ...] = ()

    def __post_init__(self):
        daylight(self.minute)
        for v in (self.rain,self.snow,self.fog,self.cloud):
            if not _finite(v) or not 0 <= v <= 1:
                raise ValueError('precipitation/cloud/fog values must be 0..1')
        for v in (self.wind_x,self.wind_y):
            if not _finite(v) or abs(v) > 4:
                raise ValueError('weather wind vector must be -4..4')
        if (not _finite(self.elapsed_seconds) or not 0 <= self.elapsed_seconds <= 1e9 or
            not _finite(self.camera_pixel_x) or not _finite(self.camera_pixel_y)):
            raise ValueError('invalid animation clock or world camera offset')
        if not isinstance(self.lights,tuple) or len(self.lights) > MAX_LIGHTS or not all(isinstance(x,WorldLight) for x in self.lights):
            raise ValueError('invalid bounded visual lights')
        if self.rain and self.snow:
            raise ValueError('rain and snow precipitation must be exclusive')


def weather_frame(weather, *, minute, elapsed_seconds, camera_pixel_x=0,
                  camera_pixel_y=0, lights=()):
    """Bridge the existing weather dict to bounded, shader-only parameters."""
    kind = str(weather.get('kind','')).casefold()
    rain = max(0., min(1., float(weather.get('rain',0)) / 100.))
    snow = rain if 'snow' in kind or 'blizzard' in kind else 0.
    if snow:rain = 0.
    return AtmosphereFrame(
        minute=int(minute), rain=rain, snow=snow,
        fog=max(0.,min(1.,float(weather.get('fog',0))/100.)),
        cloud=max(0.,min(1.,float(weather.get('cloud_cover',0))/100.)),
        wind_x=max(-4.,min(4.,float(weather.get('wind_dx',0)))),
        wind_y=max(-4.,min(4.,float(weather.get('wind_dy',0)))),
        elapsed_seconds=float(elapsed_seconds),
        camera_pixel_x=float(camera_pixel_x),camera_pixel_y=float(camera_pixel_y),
        lights=tuple(lights))


class GLAtmospherePass:
    """Zero-CPU-readback, resize-aware framebuffer and weather/light compositor.

    The source GPU scene renders to ``scene_target``. One fullscreen shader
    shades it to the single SDL window. No intermediate pygame Surface, second
    SDL Renderer, or copy to the CPU per frame. Framebuffer is RGBA8 only.
    """
    def __init__(self, ctx, width, height, *, vertex_shader=None,fragment_shader=None):
        self.ctx = ctx
        self.width = self.height = 0
        self.program = self.vbo = self.vao = None
        self.scene_color = self.scene_target = None
        self.closed = False
        try:
            self.program=ctx.program(
                vertex_shader=vertex_shader or (SHADER_DIR/'worldspace_post.vert').read_text(encoding='utf-8'),
                fragment_shader=fragment_shader or (SHADER_DIR/'worldspace_post.frag').read_text(encoding='utf-8'))
            from .gl_worldspace import vertex_bytes
            self.vbo=ctx.buffer(vertex_bytes((0.,0.,1.,1.)))
            self.vao=ctx.vertex_array(self.program,[(self.vbo,'2f 2f','in_position','in_uv')])
            self.resize(width,height)
        except Exception as exc:
            self.close()
            raise GPUBackendUnavailable(f'OpenGL atmosphere initialization failed: {type(exc).__name__}') from exc

    def resize(self,width,height):
        if self.closed:raise GPUBackendUnavailable('atmosphere renderer is closed')
        if type(width) is not int or type(height) is not int or not 1<=width<=3840 or not 1<=height<=2160 or width*height*4>MAX_FRAMEBUFFER_BYTES:
            raise ValueError('unsupported bounded atmosphere target size')
        if (width,height)==(self.width,self.height):return
        texture=target=None
        try:
            texture=self.ctx.texture((width,height),4)
            texture.repeat_x=False;texture.repeat_y=False
            target=self.ctx.framebuffer(color_attachments=[texture])
        except Exception as exc:
            if target is not None:target.release()
            if texture is not None:texture.release()
            raise GPUBackendUnavailable(f'OpenGL atmosphere resize failed: {type(exc).__name__}') from exc
        old_target,old_texture=self.scene_target,self.scene_color
        self.scene_color,self.scene_target=texture,target
        self.width,self.height=width,height
        if old_target is not None:old_target.release()
        if old_texture is not None:old_texture.release()

    def present(self, fx:AtmosphereFrame):
        if self.closed:raise GPUBackendUnavailable('atmosphere renderer is closed')
        if not isinstance(fx,AtmosphereFrame):raise TypeError('AtmosphereFrame required')
        try:
            import moderngl
            self.ctx.screen.use()
            self.ctx.viewport=(0,0,self.width,self.height)
            self.ctx.scissor=None
            self.ctx.disable(moderngl.BLEND)
            self.scene_color.use(location=0)
            self.program['u_scene'].value=0
            self.program['u_viewport'].value=(self.width,self.height)
            self.program['u_world_origin'].value=(fx.camera_pixel_x,fx.camera_pixel_y)
            self.program['u_clock'].value=fx.elapsed_seconds
            self.program['u_sun'].value=daylight(fx.minute)
            self.program['u_rain'].value=fx.rain
            self.program['u_snow'].value=fx.snow
            self.program['u_fog'].value=fx.fog
            self.program['u_cloud'].value=fx.cloud
            self.program['u_wind'].value=(fx.wind_x,fx.wind_y)
            self.program['u_light_count'].value=len(fx.lights)
            padded = (*fx.lights, *((None,)*(MAX_LIGHTS-len(fx.lights))))
            self.program['u_light_posrad'].write(pack('<32f',*(v for row in padded for v in ((row.x,row.y,row.radius,row.strength) if row else (0.,0.,1.,0.)))))
            self.program['u_light_color'].write(pack('<24f',*(v for row in padded for v in (row.color if row else (0.,0.,0.)))))
            self.vao.render(vertices=6)
        except Exception as exc:
            raise GPUBackendUnavailable(f'OpenGL atmosphere present failed: {type(exc).__name__}') from exc

    def close(self):
        if self.closed:return
        self.closed=True
        for object_ in (self.scene_target,self.scene_color,self.vao,self.vbo,self.program):
            if object_ is not None:
                try:object_.release()
                except Exception:pass
        self.scene_target=self.scene_color=None
