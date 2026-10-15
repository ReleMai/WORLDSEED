"""Bounded experimental SDL2 GPU layer composition for WORLDSEED.

The live pygame Surface backend remains authoritative until input, resize,
alpha parity and hardware performance are validated. The GPU compositor never
reads simulation state and never silently treats a failed GPU operation as a
success. An independent software compositor is available for pixel baselines.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Hashable

MAX_GPU_LAYER_BYTES = 192 * 1024 * 1024
MAX_GPU_LAYERS = 16


class GPUCompositionUnavailable(RuntimeError):
    """The experimental compositor cannot safely present this frame."""


@dataclass(frozen=True)
class RenderLayer:
    name: str
    surface: Any
    # A cache_key promises an unchanged surface. Mutable/animated layers
    # should use None; never infer immutability from the surface dimensions.
    cache_key: Hashable | None = None


def _checked_layers(base, layers):
    rows = tuple(layers)
    if len(rows) > MAX_GPU_LAYERS:
        raise ValueError("GPU layer count exceeds bounded budget")
    dims = base.get_size()
    if dims[0] <= 0 or dims[1] <= 0:
        raise ValueError("GPU canvas must have positive dimensions")
    for row in rows:
        if not isinstance(row, RenderLayer) or not isinstance(row.name, str) or not row.name:
            raise TypeError("Expected a named RenderLayer")
        if row.surface.get_size() != dims:
            raise ValueError("GPU layers must match the canvas viewport")
        if row.cache_key is not None:
            try:
                hash(row.cache_key)
            except TypeError:
                raise ValueError("GPU cache keys must be hashable") from None
    # Memory bound applies even if all textures are dynamic and uncached.
    required = (1 + len(rows)) * dims[0] * dims[1] * 4
    if required > MAX_GPU_LAYER_BYTES:
        raise GPUCompositionUnavailable("GPU layer frame exceeds 192 MiB")
    return rows


def compose_software(base, layers):
    """Exact pygame Surface alpha-blit reference; does not modify base."""
    rows = _checked_layers(base, layers)
    result = base.copy()
    for row in rows:
        result.blit(row.surface, (0, 0))
    return result


class SDL2GpuLayerCompositor:
    """Explicit GPU upload and alpha composition on a standalone SDL renderer.

    Do not construct using the production pygame.display window. The window
    boundary must be replaced atomically when the engine graduates to GPU.
    """

    def __init__(self, renderer, pygame_module, texture_type, *,
                 max_cache_bytes=MAX_GPU_LAYER_BYTES):
        if type(max_cache_bytes) is not int or not 1024 <= max_cache_bytes <= MAX_GPU_LAYER_BYTES:
            raise ValueError("GPU cache budget must be 1 KiB to 192 MiB")
        self.renderer = renderer
        self.pg = pygame_module
        self.texture_type = texture_type
        self.max_cache_bytes = max_cache_bytes
        self.cache_bytes = 0
        # Cache both the immutable source reference and matching SDL texture.
        # Holding source references prevents id recycling from reusing a texture.
        self._cache: OrderedDict[Hashable, tuple[Any, Any, int]] = OrderedDict()
        self.uploads = 0
        self.reuses = 0
        self.evictions = 0
        self.closed = False

    def invalidate(self):
        """Release stale GPU textures on viewport resize/context reset."""
        self._cache.clear()
        self.cache_bytes = 0

    def close(self):
        self.invalidate()
        self.closed = True

    def _texture(self, layer: RenderLayer):
        key = (layer.name, layer.cache_key) if layer.cache_key is not None else None
        if key is not None and key in self._cache:
            surface, texture, nbytes = self._cache[key]
            if surface is layer.surface:
                self._cache.move_to_end(key)
                self.reuses += 1
                return texture
            # The caller re-used a key for a different image. Never show the
            # old pixels, even if they have the exact same dimensions.
            self._cache.pop(key)
            self.cache_bytes -= nbytes
        texture = self.texture_type.from_surface(self.renderer, layer.surface)
        texture.blend_mode = self.pg.BLENDMODE_BLEND
        self.uploads += 1
        size = layer.surface.get_width() * layer.surface.get_height() * 4
        if key is not None and size <= self.max_cache_bytes:
            while self._cache and self.cache_bytes + size > self.max_cache_bytes:
                self._cache.popitem(last=False)
                self.cache_bytes = sum(row[2] for row in self._cache.values())
                self.evictions += 1
            self._cache[key] = (layer.surface, texture, size)
            self.cache_bytes += size
        return texture

    def compose(self, base, layers, *, base_key=None, present=False):
        if self.closed:
            raise GPUCompositionUnavailable("GPU compositor has been closed")
        rows = _checked_layers(base, layers)
        # Transparent passes are explicitly composited over an opaque base.
        # Do not apply screen-space postprocessing to the UI in this prototype.
        try:
            self.renderer.draw_color = (0, 0, 0, 255)
            self.renderer.clear()
            for row in (RenderLayer("base", base, base_key), *rows):
                texture = self._texture(row)
                texture.draw()
            if present:
                self.renderer.present()
        except Exception as exc:
            # This isolated backend must fail explicitly. Production callers
            # are responsible for their existing software fallback.
            self.invalidate()
            raise GPUCompositionUnavailable(
                "SDL2 layer composition failed: " + type(exc).__name__
            ) from exc
        return {"layers": 1 + len(rows), "uploads": self.uploads,
                "cache_reuses": self.reuses, "cache_bytes": self.cache_bytes}
