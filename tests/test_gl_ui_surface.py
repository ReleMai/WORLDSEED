"""Retained full-game UI stays independent of the GPU world and its authority."""
from __future__ import annotations

import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from worldseed.presentation.gl_ui_surface import (
    GPUUICompositor, MAX_DIRTY_RECTS, MAX_UI_TEXTURE_BYTES, make_ui_surface,
)
from worldseed.presentation.gl_worldspace import GPUBackendUnavailable


class _Resource:
    def __init__(self):
        self.released = 0
        self.writes = []
        self.renders = 0
    def release(self): self.released += 1
    def write(self, data, **kwargs): self.writes.append((data, kwargs))
    def use(self, **kwargs): pass
    def render(self, **kwargs): self.renders += 1


class _Program(_Resource):
    def __init__(self):
        super().__init__()
        self.uniforms = {}
    def __getitem__(self, key):
        return self.uniforms.setdefault(key, SimpleNamespace(value=None))


class _Context:
    def __init__(self):
        self.resources = []
        self.textures = []
        self.buffers = []
        self.screen = _Resource()
    def program(self, **kwargs):
        resource = _Program(); self.resources.append(resource); return resource
    def buffer(self, data):
        resource = _Resource(); self.resources.append(resource)
        self.buffers.append((resource, data)); return resource
    def vertex_array(self, *args):
        resource = _Resource(); self.resources.append(resource); return resource
    def texture(self, size, components, data):
        resource = _Resource(); self.resources.append(resource)
        self.textures.append((resource, size, data)); return resource
    def enable_only(self, flags): pass
    def clear(self, *args): raise AssertionError('UI must never clear the world')


class RetainedUISurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import pygame
        except ImportError:
            raise unittest.SkipTest('optional pygame dependency unavailable')
        cls.pg = pygame

    def test_full_and_partial_snapshots_restore_transparent_pixels(self):
        pg = self.pg
        surface = make_ui_surface(pg, (8, 6))
        self.assertEqual(tuple(surface.get_at((2, 2))), (0, 0, 0, 0))
        surface.fill((10, 20, 30, 128), (0, 0, 2, 2))
        for snapshot, destination in ((surface.copy(), (0, 0)),
                                      (surface.subsurface((2, 2, 3, 3)).copy(), (2, 2))):
            self.assertIsNone(snapshot.get_alpha())
            surface.fill((255, 0, 0, 255))
            surface.blit(snapshot, destination)
            self.assertEqual(tuple(surface.get_at((3, 3))), (0, 0, 0, 0))
        self.assertIsInstance(surface.subsurface((0, 0, 1, 1)), type(surface))

    def test_font_blits_preserve_opaque_panel_alpha_and_visible_glyphs(self):
        pg = self.pg
        pg.font.init()
        font = pg.font.Font(None, 22)
        glyph = font.render('WORLDSEED', True, (230, 240, 250))
        surface = make_ui_surface(pg, (180, 40))
        surface.fill((20, 30, 40, 255))
        surface.blit(glyph, (4, 4))
        # Disabling alpha on the *drawing target* makes pygame copy each font
        # glyph's zero-alpha background into an otherwise opaque panel. Only
        # retained source copies may disable source blending.
        pixels = [surface.get_at((x, y)) for y in range(40) for x in range(180)]
        self.assertTrue(all(pixel.a == 255 for pixel in pixels))
        self.assertTrue(any(pixel.r > 180 and pixel.g > 180 for pixel in pixels))
        snapshot = surface.copy()
        self.assertIsNone(snapshot.get_alpha())
        surface.fill((0, 0, 0, 0))
        surface.blit(snapshot, (0, 0))
        self.assertEqual(pg.image.tobytes(surface, 'RGBA'), pg.image.tobytes(snapshot, 'RGBA'))

    def test_texture_reuse_partial_uploads_cached_present_and_cleanup(self):
        context = _Context()
        fake_gl = SimpleNamespace(BLEND=1, SRC_ALPHA=2, ONE_MINUS_SRC_ALPHA=3, ONE=4)
        surface = make_ui_surface(self.pg, (8, 6))
        surface.fill((11, 22, 33, 44))
        with patch.dict(sys.modules, {'moderngl': fake_gl}):
            compositor = GPUUICompositor(context, 8, 6)
            self.addCleanup(compositor.close)
            texture = compositor.texture
            compositor.draw(surface)
            self.assertEqual(texture.writes[-1][0], bytes((11, 22, 33, 44)) * 48)
            self.assertEqual(compositor.upload_bytes, 8 * 6 * 4)
            compositor.draw(surface, [(-2, -1, 4, 3), (7, 5, 5, 5), (100, 100, 2, 2)])
            self.assertEqual(texture.writes[-2][1]['viewport'], (0, 0, 2, 2))
            self.assertEqual(texture.writes[-1][1]['viewport'], (7, 5, 1, 1))
            self.assertEqual(compositor.upload_bytes, (48 + 4 + 1) * 4)
            uploads = compositor.uploads
            compositor.present_cached(); compositor.draw(surface, [])
            self.assertEqual(compositor.uploads, uploads)
            self.assertEqual(len(context.textures), 1)
            self.assertEqual(len(context.buffers), 1)
            compositor.resize(8, 6)
            self.assertEqual(len(context.textures), 1)
            compositor.resize(10, 7)
            self.assertEqual(texture.released, 1)
            self.assertEqual(len(context.textures), 2)
            self.assertEqual(len(context.buffers), 1)
            self.assertEqual(context.textures[-1][2], bytes(10 * 7 * 4))
            self.assertEqual(context.viewport, (0, 0, 8, 6))
            self.assertIsNone(context.scissor)
            self.assertEqual(context.blend_func, (2, 3, 4, 3))
            compositor.close(); compositor.close()
            self.assertTrue(all(resource.released == 1 for resource in context.resources))
            with self.assertRaises(GPUBackendUnavailable): compositor.present_cached()

    def test_invalid_and_overlapping_damage_stays_bounded(self):
        context = _Context()
        fake_gl = SimpleNamespace(BLEND=1, SRC_ALPHA=2, ONE_MINUS_SRC_ALPHA=3, ONE=4)
        with patch.dict(sys.modules, {'moderngl': fake_gl}):
            compositor = GPUUICompositor(context, 8, 6)
            self.addCleanup(compositor.close)
            surface = make_ui_surface(self.pg, (8, 6))
            with self.assertRaises(ValueError): compositor.draw(make_ui_surface(self.pg, (7, 6)))
            with self.assertRaises(ValueError):
                compositor.draw(surface, ((0, 0, 1, 1) for _ in range(MAX_DIRTY_RECTS + 1)))
            self.assertEqual(compositor.uploads, 0)
            compositor.draw(surface, [(0, 0, 8, 6), (0, 0, 8, 6)])
            self.assertEqual(compositor.upload_bytes, 8 * 6 * 4)
            self.assertNotIn('viewport', compositor.texture.writes[-1][1])
            for width, height in ((0, 10), (3841, 10), (10, 2161), (True, 10)):
                with self.assertRaises(ValueError): compositor.resize(width, height)
            self.assertEqual(MAX_UI_TEXTURE_BYTES, 3840 * 2160 * 4)

    def test_actual_egl_transparency_orientation_dirty_erase_and_cached_reuse(self):
        try:
            import moderngl
        except ImportError:
            self.skipTest('optional ModernGL dependency unavailable')
        try:
            context = moderngl.create_standalone_context(require=330, backend='egl')
        except Exception as exc:
            self.skipTest(f'optional EGL unavailable: {type(exc).__name__}')
        target = compositor = None
        try:
            from tests.test_gpu_visibility_shader import _OffscreenWindowContext
            width, height = 8, 6
            target = context.simple_framebuffer((width, height), components=4)
            wrapper = _OffscreenWindowContext(context, target)
            compositor = GPUUICompositor(wrapper, width, height)
            surface = make_ui_surface(self.pg, (width, height))
            surface.fill((255, 0, 0, 255), (0, 0, 2, 2))
            surface.fill((255, 255, 255, 128), (6, 4, 2, 2))
            target.use(); target.clear(0, 0, 1, 1)
            compositor.draw(surface)
            def pixel(x, top_y):
                raw = target.read(viewport=(x, height - 1 - top_y, 1, 1), components=4, alignment=1)
                return tuple(raw)
            self.assertEqual(pixel(0, 0), (255, 0, 0, 255))
            self.assertEqual(pixel(3, 3), (0, 0, 255, 255))
            self.assertTrue(all(abs(a - b) <= 1 for a, b in zip(pixel(7, 5), (128, 128, 255, 255))))
            surface.fill((0, 0, 0, 0), (0, 0, 2, 2))
            target.clear(0, 1, 0, 1)
            compositor.draw(surface, [(0, 0, 2, 2)])
            self.assertEqual(pixel(0, 0), (0, 255, 0, 255))
            self.assertTrue(all(abs(a - b) <= 1 for a, b in zip(pixel(7, 5), (128, 255, 128, 255))))
            uploads = compositor.uploads
            target.clear(0, 0, 1, 1)
            compositor.present_cached()
            self.assertEqual(compositor.uploads, uploads)
            self.assertEqual(pixel(0, 0), (0, 0, 255, 255))
            self.assertTrue(all(abs(a - b) <= 1 for a, b in zip(pixel(7, 5), (128, 128, 255, 255))))
        finally:
            if compositor is not None: compositor.close()
            if target is not None: target.release()
            context.release()
