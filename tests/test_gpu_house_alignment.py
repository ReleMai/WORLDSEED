"""GPU building pixels and pointer regions share frozen physical-cell geometry."""
from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from unittest import TestCase

from worldseed.presentation.gl_worldspace import SpriteCommand
from worldseed.presentation.gpu_buildings import (PreparedBuildingDoor,
    PreparedBuildingShell, _fit_building_geometry, building_commands,
    building_hit_regions, load_building_art)
from worldseed.presentation.worldspace import WorldCamera, WorldFoot
from worldseed.systems.building_shells import BuildingShell
from worldseed.ui.exterior_view import shell_at_pointer


def shell(columns=6, rows=5, *, entrance_x=2, cutout=()):
    occupied = tuple((x, y) for y in range(rows) for x in range(columns) if (x, y) not in cutout)
    return BuildingShell('stable-house', 'town', 'residence', 'core:house', occupied,
        (min(entrance_x, columns-1), rows-1), 'stable-door', 0,
        'courtyard' if cutout else 'rectangular', (0, 0, columns-1, rows-1))


def prepared(building, *, cells=None, variant='core:reed_cottage'):
    visible = frozenset((x, y, 0) for x, y in building.footprint) if cells is None else frozenset(cells)
    door = PreparedBuildingDoor(building.door_uid, (*building.entrance, 0)) if (*building.entrance, 0) in visible else None
    return PreparedBuildingShell(building, visible, variant, door)


class GPUHouseAlignmentTests(TestCase):
    def setUp(self):
        try:
            import pygame
        except ImportError:
            self.skipTest('optional pygame image dependency unavailable')
        self.pg = pygame

    def material_source(self):
        from worldseed.presentation.gpu_scene_bridge import GpuMaterialSource
        return GpuMaterialSource(self.pg)

    def test_three_authored_houses_have_the_same_human_sized_threshold(self):
        building, materials = shell(), self.material_source()
        original = (building.footprint, building.bounds, building.entrance, building.door_uid)
        geometries = []
        for variant in ('core:reed_cottage', 'core:slate_townhouse', 'core:courtyard_home'):
            with self.subTest(variant=variant):
                row = prepared(building, variant=variant)
                art = load_building_art(materials, row)
                width, height = art.body[3:]
                dx, dy, dw, dh = art.door_rect
                # A top-down threshold lies wholly inside its real cell;
                # tall door projections would cover roof tiles and players.
                self.assertGreater(dw*width, .45*width/6)
                self.assertLess(dw*width, width/6)
                self.assertGreater(dh*height, .15*height/5)
                self.assertLess(dh*height, .5*height/5)
                self.assertAlmostEqual((dx+dw/2)*6, 2.5, delta=.03)
                self.assertGreaterEqual(dy*5, 4.)
                self.assertLessEqual((dy+dh)*5, 5.)
                geometries.append(art.door_rect)
                self.assertLessEqual(max(width, height), 512)
                self.assertIs(load_building_art(materials, row).body, art.body)
        self.assertEqual(len(set(geometries)), 1)
        self.assertEqual(original, (building.footprint, building.bounds, building.entrance, building.door_uid))

    def test_wide_tall_and_courtyard_shells_never_resize_the_physical_extent(self):
        materials = self.material_source()
        for building in (shell(12, 3), shell(3, 12, entrance_x=1),
                         shell(6, 5, cutout=((3, 2), (3, 3)))):
            with self.subTest(bounds=building.bounds, form=building.building_form):
                before = repr(building)
                row = prepared(building)
                art = load_building_art(materials, row)
                width, height = art.body[3:]
                columns, rows = building.bounds[2]+1, building.bounds[3]+1
                self.assertLess(art.door_rect[2]*columns, 1)
                self.assertLess(art.door_rect[3]*rows, 1.65)
                camera = WorldCamera(WorldFoot(3, 3), 640, 480, 28)
                commands = building_commands((row,), camera, materials)
                self.assertEqual(commands[0].bounds,
                    (*camera.to_screen(WorldFoot(0, 0)), *camera.to_screen(WorldFoot(columns, rows))))
                for y in range(rows):
                    for x in range(columns):
                        if (x, y) not in building.footprint:
                            px, py = int((x+.5)*width/columns), int((y+.5)*height/rows)
                            self.assertEqual(art.body[2][(py*width+px)*4+3], 0)
                self.assertEqual(repr(building), before)

    def test_actual_house_alpha_gaps_are_not_selectable_roof_rectangles(self):
        building, materials, pg = shell(), self.material_source(), self.pg
        camera = WorldCamera(WorldFoot(3, 2.5), 288, 240, 48)
        viewport = pg.Rect(0, 0, 288, 240)
        for variant in ('core:reed_cottage', 'core:slate_townhouse', 'core:courtyard_home'):
            with self.subTest(variant=variant):
                row = prepared(building, variant=variant)
                commands = building_commands((row,), camera, materials)
                regions = building_hit_regions((row,), commands, pg, viewport)
                context = {'used': viewport, 'shell_hit_regions': regions}
                # Connected top-down roofs intentionally fill their footprint;
                # only physically missing courtyard cells remain transparent.
                self.assertEqual(commands[0].rgba[3], 255)
                self.assertEqual(shell_at_pointer(context, (0, 0)), (building, 'body'))
                door = commands[1]
                center = (round((door.bounds[0]+door.bounds[2])/2),
                          round((door.bounds[1]+door.bounds[3])/2))
                self.assertEqual(shell_at_pointer(context, center), (building, 'door'))

    def test_side_doors_stay_inside_their_real_threshold_cell(self):
        original = shell()
        materials = self.material_source()
        camera = WorldCamera(WorldFoot(3, 2.5), 288, 240, 48)
        for cell, side in (((0, 2), 'west'), ((5, 2), 'east'), ((2, 0), 'north')):
            with self.subTest(side=side):
                building = replace(original, entrance=cell)
                self.assertEqual(building.door_side, side)
                command = building_commands((prepared(building),), camera, materials)[1]
                px, py = camera.to_screen(WorldFoot(*cell))
                x0, y0, x1, y1 = command.bounds
                self.assertGreater(x0, px)
                self.assertGreater(y0, py)
                self.assertLess(x1, px+camera.scale)
                self.assertLess(y1, py+camera.scale)
                self.assertEqual(command.clip_rects, ((px, py, px+camera.scale, py+camera.scale),))

    def test_tall_door_leaf_never_paints_or_targets_a_hidden_upper_cell(self):
        building, materials, pg = shell(), self.material_source(), self.pg
        camera = WorldCamera(WorldFoot(3, 2.5), 288, 240, 48)
        viewport = pg.Rect(0, 0, 288, 240)
        row = prepared(building, cells={(*building.entrance, 0)})
        commands = building_commands((row,), camera, materials)
        door = commands[1]
        px, py = camera.to_screen(WorldFoot(*building.entrance))
        self.assertGreaterEqual(door.bounds[1], py)
        self.assertLessEqual(door.bounds[3],py+48)
        self.assertEqual(door.clip_rects, ((px, py, px+48, py+48),))
        context = {'used': viewport, 'shell_hit_regions': building_hit_regions((row,), commands, pg, viewport)}
        self.assertIsNone(shell_at_pointer(context, (round(px+24), round(py-5))))
        self.assertEqual(shell_at_pointer(context, (round((door.bounds[0]+door.bounds[2])/2), round((door.bounds[1]+door.bounds[3])/2))), (building, 'door'))

    def test_recess_pixels_and_independent_door_share_uniform_fit(self):
        source = self.pg.Surface((100, 100), self.pg.SRCALPHA)
        source.fill((120, 90, 60, 255))
        self.pg.draw.rect(source, (0, 0, 255, 255), (20, 60, 10, 30))
        before = self.pg.image.tobytes(source, 'RGBA')
        axes, door = _fit_building_geometry(shell(), 288, 240, source, (200, 600, 100, 300))
        self.assertTrue(all(b > a for axis in axes for a, b in zip(axis, axis[1:])))
        sx, sy, tx, ty = axes
        self.assertEqual((door[0], door[0]+door[2], door[1], door[1]+door[3]),
                         (tx[1], tx[2], ty[1], ty[2]))
        self.assertLessEqual(door[2], 36)
        self.assertLessEqual(door[3], 75)
        self.assertEqual(self.pg.image.tobytes(source, 'RGBA'), before)

    def command(self, name, rgba, bounds=(20., 30., 28., 38.), clips=((20., 30., 28., 38.),)):
        return SpriteCommand(name, name, 1, rgba, 2, 2, bounds, clips)

    def test_transparent_pixels_hidden_cells_and_viewport_have_no_body_hit(self):
        building, pg = shell(), self.pg
        row = prepared(building)
        # Left source column is fully transparent; only top row is admitted.
        rgba = b'\0\0\0\0'+b'\x90\x70\x50\xff'+b'\0\0\0\0'+b'\x90\x70\x50\xff'
        body = self.command('building:'+building.uid, rgba, clips=((20., 30., 28., 34.),))
        viewport = pg.Rect(21, 30, 7, 8)
        regions = building_hit_regions((row,), (body,), pg, viewport)
        ctx = {'used': viewport, 'shell_hit_regions': regions}
        self.assertIsNone(shell_at_pointer(ctx, (21, 31)))
        self.assertIsNone(shell_at_pointer(ctx, (27, 35)))
        self.assertIsNone(shell_at_pointer(ctx, (20, 31)))
        self.assertEqual(shell_at_pointer(ctx, (27, 31)), (building, 'body'))

    def test_door_priority_uses_its_painted_pixels_and_stable_physical_identity(self):
        building, pg = shell(), self.pg
        row = prepared(building)
        opaque = b'\x90\x70\x50\xff'*4
        leaf = b'\0\0\0\0'*2+b'\x60\x40\x20\xff'*2
        body = self.command('building:'+building.uid, opaque)
        door = self.command('building-door:'+building.door_uid, leaf)
        viewport = pg.Rect(0, 0, 100, 100)
        # Reverse command order deliberately: shared pointer routing gives
        # the actual painted doorway priority over its parent's opaque body.
        regions = building_hit_regions((row,), (door, body), pg, viewport)
        context = {'used': viewport, 'shell_hit_regions': regions}
        self.assertEqual(shell_at_pointer(context, (23, 31)), (building, 'body'))
        self.assertEqual(shell_at_pointer(context, (23, 36)), (building, 'door'))
        self.assertEqual(next(r for r in regions if r['kind'] == 'door')['target'], building.entrance)
        hidden_door = prepared(building, cells={(0, 0, 0)})
        regions = building_hit_regions((hidden_door,), (door, body), pg, viewport)
        self.assertFalse(any(r['kind'] == 'door' for r in regions))

    def test_fractional_camera_masks_follow_render_scissors_without_edge_leaks(self):
        building, pg = shell(), self.pg
        command = self.command('building:'+building.uid, b'\x90\x70\x50\xff'*4,
            bounds=(20.2, 30.2, 28.2, 38.2), clips=((20.2, 30.2, 27.8, 37.8),))
        viewport = pg.Rect(0, 0, 100, 100)
        regions = building_hit_regions((prepared(building),), (command,), pg, viewport)
        context = {'used': viewport, 'shell_hit_regions': regions}
        self.assertEqual(shell_at_pointer(context, (20, 31)), (building, 'body'))
        self.assertEqual(shell_at_pointer(context, (27, 31)), (building, 'body'))
        self.assertEqual(shell_at_pointer(context, (21, 37)), (building, 'body'))
        self.assertIsNone(shell_at_pointer(context, (28, 31)))
        self.assertIsNone(shell_at_pointer(context, (21, 38)))
        self.assertEqual(shell_at_pointer(context, (21, 31)), (building, 'body'))

    def test_fractional_pointer_admission_matches_actual_renderer_pixel_clips(self):
        from worldseed.presentation.gl_worldspace import pixel_clip
        building, pg = shell(), self.pg
        viewport = pg.Rect(0, 0, 100, 100)
        # Includes exact half-pixel ties and adjacent fractional sight cells.
        # Source pixels are opaque, so the renderer's scissor is the complete
        # expected coverage; old ceil(start)/floor(end) masks lose edge pixels.
        for clips in (((20.2, 30.2, 27.8, 37.8),),
                      ((20.5, 30.5, 27.5, 37.5),),
                      ((20.8, 30.8, 27.2, 37.2),),
                      ((20.2, 30.2, 24.7, 37.8), (24.7, 30.2, 27.8, 37.8))):
            with self.subTest(clips=clips):
                command = self.command('building:'+building.uid, b'\x90\x70\x50\xff'*4,
                    bounds=(18., 28., 32., 42.), clips=clips)
                regions = building_hit_regions((prepared(building),), (command,), pg, viewport)
                context = {'used': viewport, 'shell_hit_regions': regions}
                expected = set()
                for clip in clips:
                    sx, gl_y, width, height = pixel_clip(clip, viewport.width, viewport.height)
                    top = viewport.height-gl_y-height
                    expected.update((x, y) for y in range(top, top+height) for x in range(sx, sx+width))
                actual = {(x, y) for y in range(28, 42) for x in range(18, 32)
                          if shell_at_pointer(context, (x, y)) is not None}
                self.assertEqual(actual, expected)

    def test_main_backend_builds_regions_from_the_commands_it_actually_draws(self):
        from worldseed.ui.gpu_terminal import GpuTerminal
        building, pg = shell(), self.pg
        row = prepared(building)
        opaque = b'\x90\x70\x50\xff'*4
        command = self.command('building:'+building.uid, opaque)
        term = object.__new__(GpuTerminal)
        term.pg = pg
        term._world_commands = (command,)
        camera = WorldCamera(WorldFoot(3, 3), 100, 100, 16)
        snapshot = SimpleNamespace(buildings=(row,), interior_scene=None)
        sim = SimpleNamespace(player_pos=SimpleNamespace(z=0), discovered_tiles_set=set(), visible_tiles_set=set())
        viewport = pg.Rect(0, 0, 100, 100)
        term._set_pointer_context(snapshot, None, None, sim, viewport, camera)
        regions = term._hover_context['shell_hit_regions']
        self.assertEqual(len(regions), 1)
        self.assertIs(regions[0]['mask'].command, command)
        self.assertEqual(shell_at_pointer(term._hover_context, (23, 33)), (building, 'body'))
