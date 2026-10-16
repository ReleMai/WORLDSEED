"""Retained UI composition over a caller-owned OpenGL world framebuffer.

The surface contains UI only: transparent pixels leave the GPU world visible.
No SDL window, event pump, simulation query, framebuffer readback or clear is
owned here. Ordinary menu rendering may upload the whole UI surface; pointer
damage updates upload only the supplied pygame rectangles. Weather animation
can call ``present_cached`` to reuse the last UI without any CPU upload.
"""
from __future__ import annotations

from itertools import islice
from struct import pack

from .gl_worldspace import GPUBackendUnavailable

MAX_WIDTH = 3840
MAX_HEIGHT = 2160
MAX_DIRTY_RECTS = 256
MAX_UI_TEXTURE_BYTES = MAX_WIDTH * MAX_HEIGHT * 4
_SURFACE_TYPES = {}

_VERTEX = """#version 330
in vec2 in_position;
in vec2 in_uv;
out vec2 v_uv;
void main() {
    gl_Position = vec4(in_position, 0.0, 1.0);
    v_uv = in_uv;
}
"""
_FRAGMENT = """#version 330
uniform sampler2D u_ui;
uniform vec2 u_viewport;
in vec2 v_uv;
out vec4 frag_color;
void main() {
    ivec2 pixel = ivec2(clamp(v_uv * u_viewport,
                             vec2(0.0), u_viewport - vec2(1.0)));
    frag_color = texelFetch(u_ui, pixel, 0);
}
"""
_QUAD = pack('<24f',
    -1., 1., 0., 0., 1., 1., 1., 0., -1., -1., 0., 1.,
    -1., -1., 0., 1., 1., 1., 1., 0., 1., -1., 1., 1.)


def _size(width, height):
    if (type(width) is not int or type(height) is not int
            or not 1 <= width <= MAX_WIDTH or not 1 <= height <= MAX_HEIGHT):
        raise ValueError('UI surface exceeds bounded framebuffer dimensions')
    return width, height


def make_ui_surface(pg, size):
    """Create a real pygame surface with raw-RGBA retained snapshot restores.

    pygame's normal alpha ``copy`` re-enables source blending. Restoring such a
    snapshot cannot erase a panel over a transparent world hole. This subtype
    keeps normal alpha composition on the drawing target, but disables source
    blending on each retained copy. pygame also preserves the subtype in
    ``subsurface`` and ``copy``, so
    existing retained UI code can continue to use its normal snapshot methods.
    pygame is caller-supplied and is never imported at module load time.
    """
    width, height = _size(*size)
    surface_type = _SURFACE_TYPES.get(pg.Surface)
    if surface_type is None:
        class RetainedUISurface(pg.Surface):
            def copy(self):
                result = super().copy()
                result.set_alpha(None)
                return result
        surface_type = _SURFACE_TYPES[pg.Surface] = RetainedUISurface
    surface = surface_type((width, height), pg.SRCALPHA)
    surface.fill((0, 0, 0, 0))
    return surface


class GPUUICompositor:
    """One bounded mutable RGBA texture and one reusable quad, in one context.

    ``draw(surface, rects=None)`` uploads all UI pixels; ``rects`` is a bounded
    iterable of pygame-compatible x/y/width/height rectangles in top-left source
    coordinates. Empty rectangles are ignored. Excess overlapping damage falls
    back to one full upload so upload work remains bounded by a viewport.
    ``present_cached()`` draws the existing texture without uploading anything.
    The caller first renders its world into ``ctx.screen`` and performs the SDL
    display flip after composition. Neither method clears or flips the target.
    """
    def __init__(self, ctx, width, height):
        _size(width, height)
        self.ctx = ctx
        self.width = self.height = 0
        self.texture = self.program = self.vbo = self.vao = None
        self.closed = False
        self.uploads = self.upload_bytes = self.draws = 0
        try:
            self.program = ctx.program(vertex_shader=_VERTEX, fragment_shader=_FRAGMENT)
            self.vbo = ctx.buffer(_QUAD)
            self.vao = ctx.vertex_array(self.program,
                                       [(self.vbo, '2f 2f', 'in_position', 'in_uv')])
            self.resize(width, height)
        except Exception as exc:
            self.close()
            if isinstance(exc, GPUBackendUnavailable):
                raise
            raise GPUBackendUnavailable(f'OpenGL UI initialization failed: {type(exc).__name__}') from exc

    def _open(self):
        if self.closed:
            raise GPUBackendUnavailable('UI compositor is closed')

    def resize(self, width, height):
        """Reallocate only on an actual size change; new pixels are transparent."""
        self._open()
        _size(width, height)
        if (width, height) == (self.width, self.height):
            return
        replacement = None
        try:
            replacement = self.ctx.texture((width, height), 4, bytes(width * height * 4))
            replacement.repeat_x = replacement.repeat_y = False
            self.program['u_viewport'].value = (float(width), float(height))
        except Exception as exc:
            if replacement is not None:
                replacement.release()
            raise GPUBackendUnavailable(f'OpenGL UI resize failed: {type(exc).__name__}') from exc
        previous = self.texture
        self.texture = replacement
        self.width, self.height = width, height
        if previous is not None:
            previous.release()

    def draw(self, surface, rects=None):
        """Upload authorized UI pixels, then blend over the completed world."""
        self._open()
        if surface.get_size() != (self.width, self.height):
            raise ValueError('UI surface must match compositor framebuffer size')
        import pygame as pg
        regions = None
        if rects is not None:
            supplied = tuple(islice(iter(rects), MAX_DIRTY_RECTS + 1))
            if len(supplied) > MAX_DIRTY_RECTS:
                raise ValueError('UI damage exceeds bounded rectangle count')
            bounds = pg.Rect(0, 0, self.width, self.height)
            regions = tuple(rect for item in supplied
                            if (rect := pg.Rect(item).clip(bounds)).width > 0 and rect.height > 0)
            if sum(rect.width * rect.height for rect in regions) > self.width * self.height:
                regions = None
        try:
            if regions is None:
                data = pg.image.tobytes(surface, 'RGBA')
                self.texture.write(data, alignment=1)
                self.uploads += 1
                self.upload_bytes += len(data)
            else:
                for rect in regions:
                    data = pg.image.tobytes(surface.subsurface(rect), 'RGBA')
                    self.texture.write(data, viewport=tuple(rect), alignment=1)
                    self.uploads += 1
                    self.upload_bytes += len(data)
        except Exception as exc:
            raise GPUBackendUnavailable(f'OpenGL UI upload failed: {type(exc).__name__}') from exc
        self.present_cached()

    def present_cached(self):
        """Blend retained pixels without clearing, allocating or uploading."""
        self._open()
        try:
            import moderngl
            self.ctx.screen.use()
            self.ctx.viewport = (0, 0, self.width, self.height)
            self.ctx.scissor = None
            self.ctx.enable_only(moderngl.BLEND)
            self.ctx.blend_func = (moderngl.SRC_ALPHA, moderngl.ONE_MINUS_SRC_ALPHA,
                                   moderngl.ONE, moderngl.ONE_MINUS_SRC_ALPHA)
            self.texture.use(location=0)
            self.program['u_ui'].value = 0
            self.vao.render(vertices=6)
            self.draws += 1
        except Exception as exc:
            raise GPUBackendUnavailable(f'OpenGL UI composition failed: {type(exc).__name__}') from exc

    def close(self):
        if self.closed:
            return
        self.closed = True
        for resource in (self.texture, self.vao, self.vbo, self.program):
            if resource is not None:
                try:
                    resource.release()
                except Exception:
                    pass
        self.texture = self.vao = self.vbo = self.program = None
