"""GPU alpha compositor contracts and real WORLDSEED atmosphere parity."""
from __future__ import annotations

import importlib.util
import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from worldseed.presentation.gpu_layers import (
    MAX_GPU_LAYER_BYTES, GPUCompositionUnavailable, RenderLayer,
    SDL2GpuLayerCompositor, _checked_layers,
)


class SurfaceStub:
    def __init__(self, width=16, height=16):
        self.size = (width, height)
        self.blit = Mock()
    def get_size(self): return self.size
    def get_width(self): return self.size[0]
    def get_height(self): return self.size[1]
    def copy(self): return SurfaceStub(*self.size)


class TextureStub:
    instances = []
    @classmethod
    def from_surface(cls, renderer, source):
        instance = SimpleNamespace(blend_mode=None, draw=Mock(), source=source)
        cls.instances.append(instance)
        return instance


class GPULayersContractTests(unittest.TestCase):
    def setUp(self):
        TextureStub.instances.clear()
        self.renderer = SimpleNamespace(draw_color=None, clear=Mock(), present=Mock())
        self.pg = SimpleNamespace(BLENDMODE_BLEND=1)

    def compositor(self, max_cache_bytes=4096):
        return SDL2GpuLayerCompositor(self.renderer, self.pg, TextureStub,
                                    max_cache_bytes=max_cache_bytes)

    def test_immutable_cache_reuse_and_dynamic_layer_uploads(self):
        gpu = self.compositor()
        base = SurfaceStub()
        fog = SurfaceStub()
        rain = SurfaceStub()
        layers = (RenderLayer("fog", fog, "fixed"), RenderLayer("rain", rain))
        gpu.compose(base, layers, base_key="scene", present=True)
        self.assertEqual((gpu.uploads, gpu.reuses), (3, 0))
        self.assertEqual(self.renderer.present.call_count, 1)
        self.assertEqual(gpu.cache_bytes, 2048)
        gpu.compose(base, layers, base_key="scene")
        self.assertEqual((gpu.uploads, gpu.reuses), (4, 2))
        self.assertEqual([t.blend_mode for t in TextureStub.instances], [1]*4)
        self.assertEqual(self.renderer.present.call_count, 1)
        self.assertEqual(gpu.cache_bytes, 2048)

    def test_same_key_different_surface_never_reuses_stale_pixels(self):
        gpu = self.compositor(max_cache_bytes=2048)
        first, next_frame = SurfaceStub(), SurfaceStub()
        base = SurfaceStub()
        gpu.compose(base, [RenderLayer("fog", first, "same")], base_key="base")
        gpu.compose(base, [RenderLayer("fog", next_frame, "same")], base_key="base")
        self.assertEqual((gpu.uploads, gpu.reuses), (3, 1))
        self.assertEqual(gpu.cache_bytes, 2048)
        self.assertIs(gpu._cache[("fog", "same")][0], next_frame)

    def test_cache_eviction_and_close_do_not_retain_surfaces(self):
        gpu = self.compositor(max_cache_bytes=1024)
        gpu.compose(SurfaceStub(), [RenderLayer("fog", SurfaceStub(), "one")],
                    base_key="first")
        self.assertLessEqual(gpu.cache_bytes, 1024)
        self.assertGreaterEqual(gpu.evictions, 1)
        gpu.invalidate()
        self.assertEqual(gpu.cache_bytes, 0)
        self.assertEqual(len(gpu._cache), 0)
        gpu.close()
        with self.assertRaises(GPUCompositionUnavailable):
            gpu.compose(SurfaceStub(), [])

    def test_bad_layers_and_native_failures_never_report_success(self):
        gpu = self.compositor()
        with self.assertRaises(ValueError):
            gpu.compose(SurfaceStub(), [RenderLayer("small", SurfaceStub(8,8))])
        with self.assertRaises(ValueError):
            gpu.compose(SurfaceStub(), [RenderLayer("bad", SurfaceStub(), [])])
        with self.assertRaises(ValueError):
            gpu.compose(SurfaceStub(), [RenderLayer("rain", SurfaceStub())]*17)
        huge = SurfaceStub(3840,2160)
        with self.assertRaises(GPUCompositionUnavailable):
            gpu.compose(huge, [RenderLayer(str(i), huge) for i in range(6)])
        class Broken:
            @staticmethod
            def from_surface(*args):
                raise RuntimeError("driver lost")
        gpu.texture_type = Broken
        with self.assertRaisesRegex(GPUCompositionUnavailable, "RuntimeError"):
            gpu.compose(SurfaceStub(), [], base_key="scene")
        self.assertEqual(gpu.cache_bytes, 0)

    def test_invalid_cache_budget_rejected(self):
        for val in (0, True, MAX_GPU_LAYER_BYTES+1):
            with self.assertRaises(ValueError):
                self.compositor(max_cache_bytes=val)


@unittest.skipUnless(importlib.util.find_spec("pygame"), "requires pygame-ce")
class GPUAtmosphereParityTests(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
        os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

    def test_real_scene_weather_layers_preserve_exact_software_pixels(self):
        from tools.gpu_layer_compositing_probe import capture_layered_frames
        import pygame as pg
        frames, record = capture_layered_frames("forest", 640, 480, 28, 1, 0,
                                                headless=True)
        self.assertTrue(record["software_parity"])
        self.assertEqual(record["source"]["camera_step_cells"], [1, 0])
        self.assertTrue(record["source"]["authority_unchanged"])
        self.assertEqual(len(frames), 2)
        self.assertIn("rain", record["effect_names"][0])
        self.assertIn("fog", record["effect_names"][0])
        self.assertIn("clouds", record["effect_names"][0])
        self.assertTrue(all(base.get_size() == (640,480)
                            for base, _, _ in frames))
        self.assertNotEqual(record["expected_sha256"][0],
                            record["expected_sha256"][1])

    def test_layer_order_matches_original_effect_stack_and_is_lazy(self):
        from worldseed.presentation.atmosphere import EffectStack, EffectFrame, WeatherSample
        import pygame as pg
        stack = EffectStack()
        count = []
        def layer(tag, rgb):
            def render(frame):
                count.append(tag)
                surface = pg.Surface((12,12), pg.SRCALPHA)
                surface.fill((*rgb,120))
                return (surface,)
            return render
        stack.register("last", 20, layer("last", (200,10,0)), lambda _: True)
        stack.register("first", 10, layer("first", (0,10,200)), lambda _: False)
        sample = EffectFrame(b'seed',12,12,0,0,1,0,720,WeatherSample())
        source = pg.Surface((12,12))
        source.fill((20,30,40))
        from worldseed.presentation.gpu_layers import compose_software
        layers = tuple(RenderLayer(name, surf)
                       for name, surf in stack.iter_layers(sample))
        self.assertEqual(count, ["first", "last"])
        expected = source.copy()
        stack.draw(expected, pg.Rect(0,0,12,12), sample)
        got = compose_software(source, layers)
        self.assertEqual(pg.image.tobytes(expected, "RGB"),
                         pg.image.tobytes(got, "RGB"))
        self.assertEqual(count, ["first","last","first","last"])


if __name__ == "__main__":
    unittest.main()
