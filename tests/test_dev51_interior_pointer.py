"""Painted furniture, stairs and floor controls share stable object identity."""
import copy
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from tests import test_interior_presentation as fixtures
from worldseed import app
from worldseed.sim.commands import UseInteriorStairsCommand
from worldseed.ui.interior_view import _draw_furniture_shadow, furniture_art_rect, pointer_object, pointer_units
from worldseed.ui.pygame_terminal import PygameTerminal


@unittest.skipUnless(PygameTerminal.available(), 'pygame optional')
class IndoorPointerTests(unittest.TestCase):
    setUp = fixtures.InteriorPresentationTests.setUp
    tearDown = fixtures.InteriorPresentationTests.tearDown
    render = fixtures.InteriorPresentationTests.render

    def test_tall_art_bottom_anchor_and_click_above_footprint(self):
        self.furniture.piece_id = 'core:wardrobe_piece'
        self.furniture.w, self.furniture.h = 1400, 700
        before = copy.deepcopy(vars(self.furniture))
        self.render()
        region = self.term._interior_context['object_regions'][0]
        self.assertEqual(region['rect'].bottom, region['base'].bottom)
        self.assertGreater(region['rect'].height, region['base'].height)
        point = region['rect'].centerx, region['rect'].top + region['rect'].height // 4
        self.assertFalse(region['base'].collidepoint(point))
        self.assertEqual(pointer_object(self.term, point)['uid'], self.furniture.uid)
        self.pg.event.post(self.pg.event.Event(self.pg.MOUSEBUTTONDOWN, button=3, pos=point))
        self.assertEqual(self.term.read_key(), 'INTERIOR_OBJECT:furniture:bed-one')
        self.assertEqual(vars(self.furniture), before)

    def test_empty_floor_keeps_free_coordinates(self):
        self.render()
        point = self.term._interior_context['camera'].to_screen(6200, 5000)
        expected = pointer_units(self.term, point)
        self.assertIsNone(pointer_object(self.term, point))
        self.pg.event.post(self.pg.event.Event(self.pg.MOUSEBUTTONDOWN, button=3, pos=point))
        self.assertEqual(self.term.read_key(), f'INTERIOR_CONTEXT:{expected[0]}:{expected[1]}')

    def test_contact_shadow_does_not_paint_a_solid_footprint(self):
        canvas = self.pg.Surface((100, 100))
        canvas.fill((255, 255, 255))
        term = NS(pg=self.pg, screen=canvas)
        base = self.pg.Rect(20, 20, 50, 40)
        _draw_furniture_shadow(term, base)
        self.assertEqual(canvas.get_at(base.center)[:3], (255, 255, 255))
        self.assertNotEqual(canvas.get_at((base.centerx, base.bottom))[:3], (255, 255, 255))
        self.assertGreater(canvas.get_at((base.centerx, base.bottom)).r, 200)

    def test_stairs_have_art_hover_and_stable_pointer_target(self):
        stair = NS(uid='stairs:upper', x=6200, y=5000, w=1300, h=2300, direction='down')
        self.plan.floor_index, self.plan.floor_count, self.plan.stairs = 1, 2, [stair]
        self.render()
        point = self.term._interior_context['camera'].to_screen(6850, 6100)
        self.assertEqual(pointer_object(self.term, point)['kind'], 'stairs')
        self.pg.event.post(self.pg.event.Event(self.pg.MOUSEBUTTONDOWN, button=3, pos=point))
        self.assertEqual(self.term.read_key(), 'INTERIOR_OBJECT:stairs:stairs:upper')

    def test_upper_context_has_stairs_not_exterior_exit(self):
        stair = NS(uid='stairs:upper', x=6200, y=5000, w=1300, h=2300, direction='down')
        self.plan.floor_index, self.plan.floor_count, self.plan.stairs = 1, 2, [stair]
        self.sim.registry = self.reg
        self.sim.interiors.hit_test = lambda *args: None
        self.sim.introduced_npc_ids = lambda: set()
        commands = []
        self.sim.execute = commands.append
        self.plan.piles = []
        ctx = NS(sim=self.sim, player_id=self.pid)
        captured = []
        def select(term, title, rows, **kwargs):
            captured.extend(rows)
            return 'stairs'
        with patch.object(app, '_select', select):
            app._interior_context_menu(ctx, self.term, self.player.x, self.player.y, 'stairs', stair.uid)
        self.assertNotIn('exit', dict(captured))
        self.assertEqual(commands, [UseInteriorStairsCommand(self.pid, stair.uid)])

    def test_new_assets_have_real_alpha(self):
        for group, key in (('building_doors', 'wood'), ('building_doors', 'wood_open'),
                           ('interiors', 'core:market_stall_piece'),
                           ('interior_stairs', 'up'), ('interior_stairs', 'down')):
            path = self.term._visuals.resolve(self.term._visuals.ref(group, key))
            self.assertIsNotNone(path)
            source = self.pg.image.load(str(path))
            self.assertEqual(source.get_at((0, 0)).a, 0)
            self.assertTrue(source.get_flags() & self.pg.SRCALPHA)
            self.assertGreater(source.get_bounding_rect(16).width, 100)


if __name__ == '__main__':
    unittest.main()
