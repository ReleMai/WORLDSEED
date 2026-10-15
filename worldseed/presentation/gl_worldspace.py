"""WORLDSEED G8-candidate OpenGL sprite renderer; explicit native opt-in only.

The primary pygame Surface renderer remains supported. This module owns no
world, saves, physics, NPC queries, keyboard, mouse or game time. A caller that
owns ONE pygame OPENGL window supplies already-authorized, projected commands.
RGBA textures are immutable by (id, revision), budgeted with LRU eviction.
SDL2 Renderer is NOT a shader backend. No SDL dummy or test-only GL context is
counted as Windows performance validation.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from math import isfinite, floor, ceil
from itertools import groupby
from pathlib import Path
from struct import pack
from typing import Iterable

MAX_COMMANDS = 4096
MAX_CLIPS_PER_COMMAND = 2048
MAX_FRAME_DRAW_GROUPS = 16384
MAX_TEXTURE_EDGE = 4096
DEFAULT_TEXTURE_BUDGET = 128 * 1024 * 1024
MAX_TEXTURE_BUDGET = 256 * 1024 * 1024
MAX_FRAME_VERTICES = 6 * MAX_COMMANDS
SHADER_DIR = Path(__file__).resolve().parents[1] / 'assets' / 'shaders'


class GPUBackendUnavailable(RuntimeError):
    """GPU candidate cannot render safely; caller must retain software path."""


@dataclass(frozen=True, slots=True)
class SpriteCommand:
    """An already-authorized screen-space sprite; clip rects are mandatory.

    RGBA bytes use tightly-packed, straight-alpha, top-first row order.
    Texture identity/revision must change when pixels change. Parent resource
    and hit target are *not* inferred from size or clip; command is draw-only.
    """
    visual_id: str
    texture_id: str
    revision: int
    rgba: bytes
    image_w: int
    image_h: int
    bounds: tuple[float, float, float, float]
    clip_rects: tuple[tuple[float, float, float, float], ...]
    opacity: float = 1.0
    fade_center: tuple[float, float] = (0.0, 0.0)
    fade_radius: float = 0.0
    local_alpha: float = 1.0

    def __post_init__(self):
        if not self.visual_id or not self.texture_id:
            raise ValueError('sprite IDs are mandatory')
        if type(self.revision) is not int or self.revision < 0:
            raise ValueError('invalid sprite material revision')
        if any(type(x) is not int or x < 1 or x > MAX_TEXTURE_EDGE
               for x in (self.image_w, self.image_h)):
            raise ValueError('texture dimensions outside bounded limits')
        if not isinstance(self.rgba, bytes) or len(self.rgba) != self.image_w*self.image_h*4:
            raise ValueError('expected exact RGBA texture bytes')
        if len(self.bounds) != 4 or any(not _finite(x) for x in self.bounds):
            raise ValueError('invalid sprite bounds')
        x0,y0,x1,y1=self.bounds
        if x1<=x0 or y1<=y0:
            raise ValueError('sprite rectangle inverted')
        if not isinstance(self.clip_rects, tuple) or len(self.clip_rects)>MAX_CLIPS_PER_COMMAND:
            raise ValueError('sprite FOW clips must be an immutable bounded tuple')
        for item in self.clip_rects:
            if not isinstance(item, tuple) or len(item)!=4 or any(not _finite(x) for x in item):
                raise ValueError('invalid sight clip rectangle')
        if (not _finite(self.opacity) or not 0<=self.opacity<=1 or
            not _finite(self.fade_radius) or self.fade_radius<0 or
            not _finite(self.local_alpha) or not 0<=self.local_alpha<=1 or
            len(self.fade_center)!=2 or any(not _finite(x) for x in self.fade_center)):
            raise ValueError('invalid material alpha parameters')


def _finite(x):
    return type(x) in (int,float) and isfinite(x)


def pixel_clip(rect, width: int, height: int):
    """Top-left-origin integer clip for a GL bottom-left scissor.

    Intersection is conservative: clip cannot grant pixels outside its source
    rectangle. No memory/remembered-cell fall-through is permitted.
    """
    x0,y0,x1,y1=rect
    x=max(0,ceil(x0)); y=max(0,ceil(y0))
    right=min(width,floor(x1)); bottom=min(height,floor(y1))
    if right<=x or bottom<=y:
        return None
    return (x,height-bottom,right-x,bottom-y)


def vertex_bytes(bounds):
    """Two 2D textured triangles (position xy, UV uv) with top-first UV."""
    x0,y0,x1,y1=bounds
    vertices=((x0,y0,0,0),(x1,y0,1,0),(x0,y1,0,1),
              (x0,y1,0,1),(x1,y0,1,0),(x1,y1,1,1))
    return pack('<24f',*(v for item in vertices for v in item))


class TextureBank:
    """Explicit bounded LRU. A failed upload never leaves a bogus cached entry."""
    def __init__(self,ctx,byte_limit=DEFAULT_TEXTURE_BUDGET):
        if type(byte_limit) is not int or not 4096<=byte_limit<=MAX_TEXTURE_BUDGET:
            raise ValueError('invalid GPU texture cache budget')
        self.ctx=ctx
        self.limit=byte_limit
        self.bytes=0
        self.uploads=0
        self.reuses=0
        self.evictions=0
        self._cache=OrderedDict()

    def texture_for(self,command):
        key=(command.texture_id,command.revision,command.image_w,command.image_h)
        prior=self._cache.get(key)
        if prior is not None:
            self._cache.move_to_end(key)
            self.reuses+=1
            return prior[0]
        size=command.image_w*command.image_h*4
        if size>self.limit:
            raise GPUBackendUnavailable('single GPU sprite exceeds texture limit')
        try:
            texture=self.ctx.texture((command.image_w,command.image_h),4,command.rgba)
            texture.repeat_x=False;texture.repeat_y=False
        except Exception as exc:
            raise GPUBackendUnavailable(f'OpenGL upload failed: {type(exc).__name__}') from exc
        while self.bytes+size>self.limit:
            _,(removed,sz)=self._cache.popitem(last=False)
            try:removed.release()
            finally:self.bytes-=sz;self.evictions+=1
        self._cache[key]=(texture,size)
        self.bytes+=size
        self.uploads+=1
        return texture

    def close(self):
        for tex,_ in self._cache.values():tex.release()
        self._cache.clear();self.bytes=0


@dataclass(frozen=True,slots=True)
class FrameReport:
    sprites: int
    draw_calls: int
    triangles: int
    textures_uploaded: int
    textures_reused: int
    gpu_texture_bytes: int
    scissor_regions: int


class GLWorldspaceRenderer:
    """Shader-capable GPU renderer using caller-owned GL context/window.

    The software renderer's SDL event/window owner must relinquish ownership
    BEFORE constructing a live instance. This class never calls set_mode() or
    flips/swallows events itself. The standalone probe owns that lifecycle.
    """
    def __init__(self,ctx,width,height,*,texture_budget=DEFAULT_TEXTURE_BUDGET,
                 vertex_shader=None,fragment_shader=None):
        if type(width) is not int or type(height) is not int or not 1<=width<=3840 or not 1<=height<=2160:
            raise ValueError('invalid framebuffer dimensions')
        self.ctx=ctx
        self.width=width;self.height=height
        self.bank=TextureBank(ctx,texture_budget)
        self._closed=False
        self.program=None;self.vbo=None;self.vao=None
        try:
            self.program=ctx.program(
                vertex_shader=vertex_shader or (SHADER_DIR/'worldspace_sprite.vert').read_text(),
                fragment_shader=fragment_shader or (SHADER_DIR/'worldspace_sprite.frag').read_text())
            self.vbo=ctx.buffer(reserve=96*max(1,min(64,MAX_COMMANDS)))
            self.vao=ctx.vertex_array(self.program,[(self.vbo,'2f 2f','in_position','in_uv')])
        except Exception as exc:
            self.close()
            raise GPUBackendUnavailable(f'OpenGL shader/VAO failed: {type(exc).__name__}') from exc

    def resize(self,width,height):
        if self._closed:raise GPUBackendUnavailable('renderer is closed')
        if type(width) is not int or type(height) is not int or not 1<=width<=3840 or not 1<=height<=2160:
            raise ValueError('invalid framebuffer resize')
        self.width=width;self.height=height
        # Textures are source art and independent of viewport; no reupload.

    def draw(self,commands:Iterable[SpriteCommand],*,clear=(0.03,0.045,0.04,1),
             ambient=(1.0,1.0,1.0)):
        if self._closed:raise GPUBackendUnavailable('renderer is closed')
        rows=tuple(commands)
        if len(rows)>MAX_COMMANDS or any(not isinstance(c,SpriteCommand) for c in rows):
            raise ValueError('GPU frame exceeds bounded command contract')
        if len(ambient)!=3 or any(not _finite(x) or not 0<=x<=1 for x in ambient):
            raise ValueError('invalid GPU ambient grade')
        # Fail before partial frame on invalid material and huge clip budgets.
        work=[]
        for cmd in rows:
            for rect in cmd.clip_rects:
                clip=pixel_clip(rect,self.width,self.height)
                if clip:
                    work.append((cmd,clip))
                    if len(work)>MAX_FRAME_DRAW_GROUPS:
                        raise ValueError('too many GPU visibility clip operations')
        if len(clear)!=4 or any(not _finite(x) or not 0<=x<=1 for x in clear):
            raise ValueError('invalid framebuffer clear color')
        try:
            self.ctx.screen.use()
            self.ctx.viewport=(0,0,self.width,self.height)
            import moderngl
            self.ctx.enable_only(moderngl.BLEND)
            self.ctx.blend_func=(moderngl.SRC_ALPHA,moderngl.ONE_MINUS_SRC_ALPHA)
            self.ctx.clear(*clear)
            self.program['u_viewport'].value=(self.width,self.height)
            self.program['u_texture'].value=0
            self.program['u_ambient'].value=tuple(ambient)
            rendered=0
            uploads_before=self.bank.uploads
            reuses_before=self.bank.reuses
            def batch_key(row):
                cmd,clip=row
                return (cmd.texture_id,cmd.revision,cmd.image_w,cmd.image_h,
                        clip,cmd.opacity,cmd.fade_center,cmd.fade_radius,cmd.local_alpha)
            for _key, group in groupby(work,key=batch_key):
                values=tuple(group)
                for first in range(0,len(values),64):
                    batch=values[first:first+64]
                    cmd,clip=batch[0]
                    tex=self.bank.texture_for(cmd)
                    tex.use(location=0)
                    self.ctx.scissor=clip
                    self.program['u_opacity'].value=cmd.opacity
                    self.program['u_fade_center'].value=cmd.fade_center
                    self.program['u_fade_radius'].value=cmd.fade_radius
                    self.program['u_local_alpha'].value=cmd.local_alpha
                    data=b''.join(vertex_bytes(sprite.bounds) for sprite,_ in batch)
                    self.vbo.write(data)
                    self.vao.render(vertices=6*len(batch))
                    rendered+=1
            self.ctx.scissor=None
            return FrameReport(len(rows),rendered,len(work)*2,
                               self.bank.uploads-uploads_before,
                               self.bank.reuses-reuses_before,
                               self.bank.bytes,len(work))
        except GPUBackendUnavailable:
            self.ctx.scissor=None
            raise
        except Exception as exc:
            self.ctx.scissor=None
            raise GPUBackendUnavailable(f'OpenGL frame failed: {type(exc).__name__}') from exc

    def close(self):
        if self._closed:return
        self._closed=True
        self.bank.close()
        for item in (self.vao,self.vbo,self.program):
            if item is not None:
                try:item.release()
                except Exception:pass


def commands_from_projected(scene,texture_source):
    """Adapt G1 immutable *authorized* visuals; caller supplies RGBA assets.

    `texture_source(visual)` returns (id, revision, raw_rgba, image_w, image_h)
    or None to omit intentional non-art probe objects. No terrain/world reads.
    No sorting beyond G1 projected order; sprite/interaction IDs stay separate.
    """
    fades={f.cover_instance_id:f for f in scene.cover_fades}
    result=[]
    for visual in scene.visuals:
        if visual.remembered_only:continue
        source=texture_source(visual)
        if source is None:continue
        tid,rev,rgba,w,h=source
        fade=fades.get(visual.instance.instance_id)
        result.append(SpriteCommand(
            visual.instance.instance_id,tid,rev,rgba,w,h,
            visual.screen_bounds,visual.clip_rects,
            fade_center=fade.screen_center if fade else (0,0),
            fade_radius=fade.radius_px if fade else 0,
            local_alpha=fade.local_alpha if fade else 1,
        ))
    return tuple(result)
