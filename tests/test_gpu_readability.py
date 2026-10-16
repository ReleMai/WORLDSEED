"""Human-scale art, local player clearance and detached static memory contracts."""
from __future__ import annotations

from types import SimpleNamespace
import unittest

from worldseed.presentation.gpu_objects import (
    PreparedObject, gpu_resource_style, object_geometry,
)
from worldseed.presentation.gpu_scene_bridge import prepare_gpu_frame
from worldseed.presentation.visuals import VisualRegistry
from worldseed.presentation.worldspace import WorldCamera, WorldFoot, VisualLayer


def definition(*tags, solid=False):
    return SimpleNamespace(tags=tags, blocks_movement=solid)


class SolidMaterials:
    @staticmethod
    def texture(name, rgba):
        return name, 1, bytes(rgba), 1, 1

    def asset(self, path): return self.texture('asset:'+str(path), (75, 80, 60, 255))
    def player(self): return self.texture('player', (255, 20, 20, 255))
    def tree(self, species, layer, season):
        color = (20, 220, 20, 255) if layer == 'crown' else (50, 30, 10, 255)
        return self.texture(':'.join((species, layer, season)), color)


class GPUReadabilityContracts(unittest.TestCase):
    def setUp(self):
        self.camera = WorldCamera(WorldFoot(0., 0.), 192, 192, 32)
        self.visible = frozenset((x, y, 0) for y in range(-3, 3) for x in range(-3, 3))
        self.defs = {'core:oak_tree': definition('tree', solid=True),
                     'core:fallen_branches': definition('branch', 'wood'),
                     'core:loose_stone': definition('rock', 'stone')}

    def frame(self, **changes):
        args = dict(camera=self.camera,
            terrain_by={cell: 'core:grass' for cell in self.visible},
            resource_by={}, resource_defs=self.defs,
            resource_style=lambda fid: gpu_resource_style(fid, self.defs.get(fid)),
            visible_cells=self.visible, discovered_cells=self.visible,
            viewer=WorldFoot(.6, .9), materials=SolidMaterials())
        args.update(changes)
        return prepare_gpu_frame(**args)

    def test_loose_resources_fit_below_player_knees_without_changing_identity(self):
        branches = SimpleNamespace(feature_id='core:fallen_branches', stage='mature')
        stone = SimpleNamespace(feature_id='core:loose_stone', stage='mature')
        frame = self.frame(resource_by={(0, 0, 0): (branches, None),
                                        (1, 0, 0): (stone, None)})
        commands = {row.visual_id: row for row in frame.scenery}
        for fid, cell, expected in (('core:fallen_branches', (0, 0), (.72, .48)),
                                     ('core:loose_stone', (1, 0), (.46, .38))):
            row = commands[f'feature:0:{cell[0]}:{cell[1]}:{fid}:mature:base']
            self.assertAlmostEqual((row.bounds[2]-row.bounds[0])/32, expected[0])
            self.assertAlmostEqual((row.bounds[3]-row.bounds[1])/32, expected[1])
            foot = self.camera.to_screen(WorldFoot(cell[0]+.5, cell[1]+.95))
            self.assertEqual((sum(row.bounds[::2])/2, row.bounds[3]), foot)

    def test_catalog_atlas_metadata_and_explicit_mod_dimensions_survive_scaling(self):
        catalog = VisualRegistry.load_default()
        style = gpu_resource_style('core:hollow_log_cache', definition('natural_container'), catalog)
        self.assertIn('atlas', style)
        self.assertEqual((style['width'], style['height']), (.9, .65))
        custom = SimpleNamespace(resource_style=lambda fid: {'gpu_width': 1.7,
                                 'gpu_height': .42, 'atlas_row': 4})
        self.assertEqual(gpu_resource_style('mod:fallen_willow', definition('branch'), custom),
                         {'gpu_width': 1.7, 'gpu_height': .42, 'atlas_row': 4,
                          'width': 1.7, 'height': .42})

    def test_ordinary_props_are_smaller_than_the_viewer_and_ground_geometry_stays_exact(self):
        for kind in ('pile', 'container', 'crop', 'sign'):
            width, height, layer = object_geometry(kind)
            self.assertLessEqual(width, .8)
            self.assertLess(height, 1.)
            self.assertIs(layer, VisualLayer.GROUNDED)
        self.assertEqual(object_geometry('structure', ground=True),
                         (1., 1., VisualLayer.LOW_DETAIL))

    def test_clearance_centers_on_whole_player_body_and_keeps_trunks_opaque(self):
        tree = SimpleNamespace(feature_id='core:oak_tree', stage='mature')
        frame = self.frame(resource_by={(1, 1, 0): (tree, None)})
        crown = next(row for row in frame.scenery if ':crown:' in row.texture_id)
        trunk = next(row for row in frame.scenery if ':trunk:' in row.texture_id)
        vx, vy = self.camera.to_screen(WorldFoot(.6, .9))
        self.assertEqual(crown.fade_center, (vx, vy-32*.76))
        self.assertAlmostEqual(crown.fade_radius, 32*1.12)
        self.assertAlmostEqual(crown.local_alpha, .08)
        self.assertEqual((trunk.opacity, trunk.fade_radius), (1., 0.))
        for clip in crown.clip_rects:
            self.assertIn(self.camera.to_world(clip[0], clip[1]).cell, self.visible)

    def test_hidden_viewer_does_not_trigger_clearance_or_reveal_canopy_cells(self):
        tree = SimpleNamespace(feature_id='core:oak_tree', stage='mature')
        visible = self.visible-{(0, 0, 0)}
        frame = self.frame(resource_by={(1, 1, 0): (tree, None)}, visible_cells=visible)
        self.assertFalse(any(row.fade_radius for row in frame.scenery))
        for row in frame.scenery:
            for x0, y0, _x1, _y1 in row.clip_rects:
                self.assertIn(self.camera.to_world(x0, y0).cell, visible)

    def test_static_memory_is_explicit_frozen_and_never_promotes_unknown_or_current_cells(self):
        tree = SimpleNamespace(feature_id='core:oak_tree', stage='stump')
        memories = (((1, 1, 0), tree), ((8, 8, 0), tree))
        current = frozenset({(0, 0, 0)})
        discovered = current | {(1, 1, 0)}
        object_row = PreparedObject('pile:old', 'pile', 'core:branch', WorldFoot(1.5, 1.999),
                                    *object_geometry('pile')[:2])
        frame = self.frame(visible_cells=current, discovered_cells=discovered,
            remembered_resources=memories, remembered_objects=(object_row,))
        memory = [row for row in frame.scenery if row.visual_id.startswith('memory:')]
        self.assertEqual(len(memory), 2)
        self.assertTrue(all(row.remembered and row.opacity == .62
                            and not row.sway_px and not row.fade_radius for row in memory))
        for row in memory:
            self.assertTrue(all(self.camera.to_world(a, b).cell == (1, 1, 0)
                                for a, b, _c, _d in row.clip_rects))
        self.assertFalse(any('8:8' in row.visual_id for row in frame.scenery))
        no_memory = self.frame(visible_cells=current, discovered_cells=discovered,
            remembered_resources=memories, show_explored_memory=False)
        self.assertFalse(any(row.remembered for row in no_memory.commands))

    def test_remembered_resources_never_spill_over_a_known_closed_shell(self):
        tree = SimpleNamespace(feature_id='core:oak_tree', stage='mature')
        # The absent public-ground cell represents a remembered opaque shell.
        terrain = {cell: 'core:grass' for cell in self.visible if cell != (1, 0, 0)}
        frame = self.frame(terrain_by=terrain, visible_cells={(0, 0, 0)},
            remembered_resources=(((1, 1, 0), tree),))
        for row in frame.scenery:
            if not row.remembered: continue
            self.assertNotIn((1, 0, 0), {self.camera.to_world(a, b).cell
                            for a, b, _c, _d in row.clip_rects})


class GPUPlayerClearanceRasterContracts(unittest.TestCase):
    def test_overlapping_crowns_leave_player_readable_with_unknown_pixels_black(self):
        try:
            import moderngl
            ctx = moderngl.create_standalone_context(require=330, backend='egl')
        except Exception as exc:
            self.skipTest('optional EGL unavailable: '+type(exc).__name__)
        from worldseed.presentation.gl_worldspace import GLWorldspaceRenderer
        self.addCleanup(ctx.release)
        texture = ctx.texture((192, 192), 4)
        self.addCleanup(texture.release)
        target = ctx.framebuffer(color_attachments=[texture])
        self.addCleanup(target.release)
        renderer = GLWorldspaceRenderer(ctx, 192, 192, texture_budget=4096)
        self.addCleanup(renderer.close)
        case = GPUReadabilityContracts()
        case.setUp()
        tree = SimpleNamespace(feature_id='core:oak_tree', stage='mature')
        admitted=case.visible-{(-3,-3,0)}
        frame = case.frame(resource_by={(1, 1, 0): (tree, None),
                                        (0, 1, 0): (tree, None)},
                           visible_cells=admitted,discovered_cells=admitted)
        # Keep independent trunks out of this canopy-only optical assertion.
        commands = tuple(row for row in frame.commands
                         if ':trunk:' not in row.texture_id and ':shadow:' not in row.texture_id)
        renderer.draw(commands, clear=(0., 0., 0., 0.), target=target)
        pixels = target.read(components=3, alignment=1)
        def pixel(x, y):
            index = ((191-y)*192+x)*3
            return tuple(pixels[index:index+3])
        vx, vy = case.camera.to_screen(WorldFoot(.6, .9))
        red, green, _blue = pixel(round(vx), round(vy-32*.76))
        self.assertGreater(red, 210)
        self.assertLess(green, 65)
        self.assertNotEqual(pixel(160, 140), (0, 0, 0))
        self.assertEqual(pixel(1, 1), (0, 0, 0))


if __name__ == '__main__':
    unittest.main()
