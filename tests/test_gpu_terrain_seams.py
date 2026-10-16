"""Fractional camera edges cover authorized sample centers without grid gaps.

The optional EGL checks exercise repository shaders, not native Windows GPU
acceptance. Solid source colors isolate raster clipping from authored textures.
"""
from __future__ import annotations

import unittest

from worldseed.presentation.gl_worldspace import (
    GLWorldspaceRenderer, SpriteCommand, pixel_clip,
)
from worldseed.presentation.gpu_scene_bridge import cell_bounds, prepare_gpu_frame
from worldseed.presentation.worldspace import WorldCamera, WorldFoot


COLOR = b'\x4c\x81\x36\xff'


class FractionalClipContracts(unittest.TestCase):
    def test_adjacent_fractional_clips_partition_authorized_pixel_centers(self):
        edges = (1.2, 7.6, 15.3, 22.8)
        counts = [0] * 25
        for left, right in zip(edges, edges[1:]):
            clip = pixel_clip((left, 0., right, 1.), 25, 1)
            self.assertIsNotNone(clip)
            for x in range(clip[0], clip[0] + clip[2]):
                counts[x] += 1
        expected = [int(edges[0] <= x + .5 < edges[-1]) for x in range(25)]
        self.assertEqual(counts, expected)

    def test_subpixel_clip_only_admits_a_sample_inside_the_source(self):
        self.assertEqual(pixel_clip((2.2, 3.2, 2.8, 3.8), 8, 8), (2, 4, 1, 1))
        self.assertIsNone(pixel_clip((2.6, 3.2, 2.9, 3.8), 8, 8))


class FractionalRasterContracts(unittest.TestCase):
    def setUp(self):
        try:
            import moderngl
        except ImportError:
            self.skipTest('optional ModernGL dependency unavailable')
        try:
            self.context = moderngl.create_standalone_context(require=330, backend='egl')
        except Exception as exc:
            self.skipTest('optional EGL driver unavailable: ' + type(exc).__name__)
        self.addCleanup(self.context.release)
        self.width, self.height = 67, 53
        self.texture = self.context.texture((self.width, self.height), 4)
        self.addCleanup(self.texture.release)
        self.target = self.context.framebuffer(color_attachments=[self.texture])
        self.addCleanup(self.target.release)
        self.renderer = GLWorldspaceRenderer(self.context, self.width, self.height,
                                             texture_budget=4096)
        self.addCleanup(self.renderer.close)

    def rgb_at(self, pixels, x, y):
        index = ((self.height-1-y) * self.width+x) * 3
        return pixels[index:index+3]

    def test_fractional_visibility_clips_have_no_lines_or_unseen_pixels(self):
        xs, ys = (3.2, 20.7, 36.3, 61.8), (2.1, 24.8, 49.4)
        clips = tuple((x0, y0, x1, y1)
                      for y0, y1 in zip(ys, ys[1:])
                      for x0, x1 in zip(xs, xs[1:]))
        command = SpriteCommand('authorized-material', 'solid', 1, COLOR, 1, 1,
                                (0., 0., 67., 53.), clips)
        self.renderer.draw((command,), clear=(0., 0., 0., 0.), target=self.target)
        pixels = self.target.read(components=3, alignment=1)
        for y in range(self.height):
            for x in range(self.width):
                admitted = xs[0] <= x+.5 < xs[-1] and ys[0] <= y+.5 < ys[-1]
                self.assertEqual(self.rgb_at(pixels, x, y), COLOR[:3] if admitted else b'\0\0\0',
                                 f'visibility edge at {(x, y)}')

    def test_fractional_outdoor_ground_quads_already_cover_without_scissor_gaps(self):
        class SolidMaterials:
            def asset(self, path):
                return ('solid-ground', 1, COLOR, 1, 1)

        # Distinctly fractional scale and origin reproduce normal smooth
        # movement/zoom. Full-viewport clips distinguish this path from the
        # per-sight-cell clipping regression above.
        camera = WorldCamera(WorldFoot(.23, -.17, 0), self.width, self.height, 9.3, 1.17)
        left, top, right, bottom = cell_bounds(camera)
        terrain = {(x, y, 0): 'core:grass'
                   for y in range(top, bottom) for x in range(left, right)}
        visible = frozenset(terrain)
        frame = prepare_gpu_frame(camera=camera, terrain_by=terrain, resource_by={},
            resource_defs={}, resource_style=lambda _: {}, visible_cells=visible,
            discovered_cells=visible, viewer=WorldFoot(0, 0, 0), materials=SolidMaterials(),
            show_player=False)
        self.renderer.draw(frame.ground, clear=(0., 0., 0., 0.), target=self.target)
        pixels = self.target.read(components=3, alignment=1)
        self.assertEqual(pixels, COLOR[:3] * (self.width*self.height))


if __name__ == '__main__':
    unittest.main()
