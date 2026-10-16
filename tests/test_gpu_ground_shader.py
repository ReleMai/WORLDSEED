"""Detached continuous ground shader contracts; EGL is optional, not hardware proof."""
from dataclasses import FrozenInstanceError, replace
import unittest

from worldseed.presentation.gl_worldspace import (
    GLWorldspaceRenderer, GroundBlend, GroundTexture, SpriteCommand,
)


OFFSETS = ((-1, 0), (1, 0), (0, -1), (0, 1),
           (-1, -1), (1, -1), (-1, 1), (1, 1))


def material(identity, rgb):
    return GroundTexture(identity, 1, bytes((*rgb, 255)), 1, 1,
                         tuple(channel / 255 for channel in rgb))


GRASS = material('grass', (83, 127, 59))


def command(cell, texture=GRASS, *, scale=64., offset=(0., 0.),
            neighbors=None, widths=(.42, .42, .42, .42), clips=((0., 0., 128., 128.),)):
    x, y = cell
    left, top = offset[0]+x*scale, offset[1]+y*scale
    return SpriteCommand(str(cell), texture.texture_id, texture.revision,
        texture.rgba, texture.image_w, texture.image_h,
        (left, top, left+scale, top+scale), clips,
        ground=GroundBlend(cell, neighbors or (texture,)*8, widths, texture.color))


class GroundCommandContracts(unittest.TestCase):
    def test_metadata_is_immutable_and_rejects_unbounded_or_incomplete_materials(self):
        blend = command((0, 0)).ground
        with self.assertRaises(FrozenInstanceError):
            blend.widths = (1.,)*4
        for fields in ({'neighbors': (GRASS,)*7}, {'widths': (.51,)*4},
                       {'color': (float('nan'), 0., 0.)}, {'cell': (.2, 0)}):
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                replace(blend, **fields)
        with self.assertRaises(ValueError):
            replace(GRASS, image_w=4097)
        with self.assertRaises(ValueError):
            replace(GRASS, rgba=b'')
        with self.assertRaises(ValueError):
            replace(command((0, 0)), ground=object())


class GroundShaderRasterContracts(unittest.TestCase):
    def setUp(self):
        try:
            import moderngl
        except ImportError:
            self.skipTest('optional ModernGL dependency unavailable')
        try:
            self.context = moderngl.create_standalone_context(require=330, backend='egl')
        except Exception as exc:
            self.skipTest('optional EGL driver unavailable: '+type(exc).__name__)
        self.addCleanup(self.context.release)
        self.texture = self.context.texture((128, 128), 4)
        self.addCleanup(self.texture.release)
        self.target = self.context.framebuffer(color_attachments=[self.texture])
        self.addCleanup(self.target.release)
        self.renderer = GLWorldspaceRenderer(self.context, 128, 128,
                                             texture_budget=1024*1024)
        self.addCleanup(self.renderer.close)

    def draw(self, commands):
        report = self.renderer.draw(commands, clear=(0., 0., 0., 0.), target=self.target)
        return self.target.read(components=3, alignment=1), report

    @staticmethod
    def pixel(pixels, x, y):
        index = ((127-y)*128+x)*3
        return tuple(pixels[index:index+3])

    def test_world_texture_stays_anchored_during_fractional_camera_translation(self):
        # Deliberately non-seamless authored source. The shader's two mirrored
        # sampling domains must be continuous and must not restart per cell.
        rgba = bytes(v for y in range(8) for x in range(8)
                     for v in (40+x*21, 75+y*15, 35+x*7, 255))
        source = GroundTexture('gradient', 1, rgba, 8, 8, (.4, .5, .25))
        cells = tuple((x, y) for y in range(-1, 5) for x in range(-1, 5))
        first, report = self.draw(tuple(command(c, source, scale=31.7,
            offset=(.3, -.7)) for c in cells))
        moved, _ = self.draw(tuple(command(c, source, scale=31.7,
            offset=(7.3, 4.3)) for c in cells))
        # Identical material cells still batch rather than one group per cell.
        self.assertEqual(report.draw_calls, 1)
        self.assertEqual(report.textures_uploaded, 1)
        max_delta = max(abs(a-b) for y in range(10, 115) for x in range(10, 115)
                        for a, b in zip(self.pixel(first, x, y), self.pixel(moved, x+7, y+5)))
        self.assertLessEqual(max_delta, 1)
        self.assertGreater(len({self.pixel(first, x, 30) for x in range(128)}), 15)
        # Crossing a camera cell edge does not produce an authored reset line.
        for boundary in (32, 64, 95):
            self.assertLessEqual(max(abs(a-b) for y in range(10, 115)
                for a, b in zip(self.pixel(first, boundary-1, y),
                                self.pixel(first, boundary, y))), 5)

    def test_four_distinct_materials_meet_continuously_at_edges_and_corner(self):
        terrain = {(0, 0): material('red', (167, 58, 41)),
                   (1, 0): material('green', (54, 144, 43)),
                   (0, 1): material('blue', (42, 84, 169)),
                   (1, 1): material('gold', (174, 143, 58))}
        commands = []
        for (x, y), source in terrain.items():
            neighbors = tuple(terrain.get((x+dx, y+dy), source) for dx, dy in OFFSETS)
            widths = tuple(.42 if (x+dx, y+dy) in terrain else 0.
                           for dx, dy in OFFSETS[:4])
            commands.append(command((x, y), source, neighbors=neighbors, widths=widths))
        pixels, report = self.draw(commands)
        self.assertEqual(report.textures_uploaded, 4)
        for y in range(10, 119):
            self.assertLessEqual(max(abs(a-b) for a,b in zip(
                self.pixel(pixels, 63, y), self.pixel(pixels, 64, y))), 6)
        for x in range(10, 119):
            self.assertLessEqual(max(abs(a-b) for a,b in zip(
                self.pixel(pixels, x, 63), self.pixel(pixels, x, 64))), 6)
        corner = [self.pixel(pixels, x, y) for x in (63,64) for y in (63,64)]
        self.assertLessEqual(max(max(channel)-min(channel) for channel in zip(*corner)), 6)

    def test_zero_width_edges_do_not_sample_neighbor_colors_or_escape_sight(self):
        first = command((0, 0), scale=80., offset=(15.2, 10.1),
            neighbors=(material('red', (255, 0, 0)),)*8,
            widths=(0.,)*4, clips=((18.2, 17.6, 74.8, 69.3),))
        second = replace(first, ground=replace(first.ground,
            neighbors=(material('blue', (0, 0, 255)),)*8))
        a, _ = self.draw((first,))
        b, _ = self.draw((second,))
        self.assertEqual(a, b)
        for y in range(128):
            for x in range(128):
                if not (18.2 <= x+.5 < 74.8 and 17.6 <= y+.5 < 69.3):
                    self.assertEqual(self.pixel(a, x, y), (0,0,0))
        self.assertNotEqual(self.pixel(a, 30, 30), (0,0,0))

    def test_ordinary_sprite_pixels_and_top_first_orientation_are_unchanged(self):
        rgba = bytes((255,0,0,255, 0,255,0,255, 0,0,255,255, 255,255,255,255))
        ordinary = SpriteCommand('art', 'four-corners', 1, rgba, 2, 2,
            (4.,5.,6.,7.), ((4.,5.,6.,7.),))
        # Draw ground first so the ordinary branch must reset ground uniforms.
        self.draw((command((0,0)),))
        pixels, _ = self.draw((ordinary,))
        self.assertEqual(self.pixel(pixels, 4, 5), (255,0,0))
        self.assertEqual(self.pixel(pixels, 5, 5), (0,255,0))
        self.assertEqual(self.pixel(pixels, 4, 6), (0,0,255))
        self.assertEqual(self.pixel(pixels, 5, 6), (255,255,255))
        self.assertEqual(self.pixel(pixels, 3, 5), (0,0,0))


if __name__ == '__main__':
    unittest.main()
