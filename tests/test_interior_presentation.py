"""Headless continuous interior rendering and pointer regression checks."""
import copy
import os
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.entities.components import Inventory, Vitals
from worldseed.entities.store import EntityStore
from worldseed.ui.interior_view import InteriorCamera, pointer_units
from worldseed.ui.pygame_terminal import PygameTerminal


class InteriorCameraTests(unittest.TestCase):
    def test_transform_retains_sub_tile_positions(self):
        camera = InteriorCamera(-1037.25, 303.75, .035, 18, 62)
        for x, y in ((2193, 3367), (4481, 6691), (105, 307)):
            px, py = camera.to_screen(x, y)
            rx, ry = camera.to_units(px, py)
            self.assertLessEqual(abs(x - rx), 15)
            self.assertLessEqual(abs(y - ry), 15)
        self.assertNotEqual(camera.to_screen(2100, 2200), camera.to_screen(2300, 2200))


@unittest.skipUnless(PygameTerminal.available(), 'pygame optional')
class InteriorPresentationTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'SDL_VIDEODRIVER': 'dummy', 'SDL_AUDIODRIVER': 'dummy'})
        self.env.start()
        self.term = PygameTerminal(960, 640)
        self.term.enter()
        self.pg = self.term.pg
        self.pg.event.clear()
        self.reg = ContentRegistry.load(DATA_DIR)
        self.entities = EntityStore()
        self.pid = self.entities.spawn(preferred_id=1)
        self.entities.add(self.pid, Inventory())
        self.entities.add(self.pid, Vitals())
        self.player = NS(space_id='interior:one', x=6200, y=4850, action='walking')
        self.furniture = NS(uid='bed-one', piece_id='core:bed_piece', x=4230, y=3520, w=1400, h=1900)
        rect = lambda x, y, w, h: NS(x=x, y=y, w=w, h=h)
        self.plan = NS(uid='interior:one', width=18000, height=15000, name='House interior', function='house',
                       entry_x=6000, entry_y=14000,
                       walls=[rect(0, 0, 18000, 220), rect(7900, 220, 200, 5200)],
                       rooms=[NS(name='Sleeping chamber', rect=rect(200, 200, 7600, 6100)),
                              NS(name='Common room', rect=rect(8100, 200, 9700, 6100))],
                       furniture=[self.furniture])
        state = NS(player_name='Wanderer', player_sex='male', player_sprite_index=0, npcs={})
        interior = NS(current_plan=lambda: self.plan, player_presence=lambda: self.player,
                      actors_in_space=lambda space: (('player', self.player),))
        self.sim = NS(interiors=interior, state=state, clock=NS(label=lambda: 'Y1 Spring 1, 12:00'),
                      known_npc_ids=lambda: set(), log=[])

    def tearDown(self):
        self.term.restore()
        self.env.stop()

    def render(self):
        # These deliberately have no outdoor APIs. An interior render must not
        # inspect terrain, query outdoor actors, or discover the exterior map.
        self.term.present_game(self.reg, object(), self.entities, self.sim, self.pid)

    def test_render_is_observational_and_uses_no_outdoor_entities(self):
        before = copy.deepcopy((vars(self.player), vars(self.furniture), vars(self.plan)))
        for width, height in ((960, 640), (800, 520)):
            self.term._resize(width, height)
            for scale in (16, 28, 56):
                self.term._tile_px = scale
                self.render()
                ctx = self.term._interior_context
                self.assertEqual(ctx['camera'].to_screen(self.player.x, self.player.y), ctx['used'].center)
                self.assertIsNone(self.term._hover_context)
                self.assertIsNone(self.term._weather_animation_context)
                self.assertEqual(self.term._input_mode, 'world')
        after = (vars(self.player), vars(self.furniture), vars(self.plan))
        self.assertEqual(before, after)

    def test_right_click_retains_continuous_local_coordinates(self):
        self.render()
        ctx = self.term._interior_context
        point = ctx['camera'].to_screen(4517, 3892)
        expected = pointer_units(self.term, point)
        self.assertIsNotNone(expected)
        self.assertNotEqual(expected[0] % 1000, 0)
        self.pg.event.post(self.pg.event.Event(self.pg.MOUSEBUTTONDOWN, button=3, pos=point))
        self.assertEqual(self.term.read_key(), f'INTERIOR_CONTEXT:{expected[0]}:{expected[1]}')
        self.assertIsNone(pointer_units(self.term, (0, 0)))

    def test_indoor_hud_exposes_same_stances_and_trespass_without_mutation(self):
        self.plan.building_id='home:one'
        self.sim.state.player_trespass_property_id='home:one'
        self.sim.state.player_hunting_stance='crouch'
        before=copy.deepcopy(vars(self.sim.state))
        self.render()
        controls=[(r,t) for r,t in self.term._pointer_targets if t.startswith('UI_STANCE:')]
        self.assertEqual(len(controls),4)
        self.assertTrue(all(self.term.screen.get_rect().contains(r) for r,t in controls))
        self.assertEqual(vars(self.sim.state),before)

    def test_left_click_only_places_when_explicitly_armed(self):
        self.render()
        point = self.term._interior_context['camera'].to_screen(5133, 4215)
        expected = pointer_units(self.term, point)
        self.term._interior_placing = self.furniture.uid
        self.pg.event.post(self.pg.event.Event(self.pg.MOUSEBUTTONDOWN, button=1, pos=point))
        self.assertEqual(self.term.read_key(), f'INTERIOR_PLACE:{expected[0]}:{expected[1]}')

    def test_held_movement_combines_directions_without_grid_tokens(self):
        self.render()
        self.pg.event.post(self.pg.event.Event(self.pg.KEYDOWN, key=self.pg.K_w, unicode='w'))
        self.assertEqual(self.term.read_key(), 'INTERIOR_MOVE:0:-1')
        self.pg.event.post(self.pg.event.Event(self.pg.KEYDOWN, key=self.pg.K_d, unicode='d'))
        self.assertEqual(self.term.read_key(), 'INTERIOR_MOVE:1:-1')
        self.pg.event.post(self.pg.event.Event(self.pg.KEYUP, key=self.pg.K_w, unicode=''))
        self.pg.event.post(self.pg.event.Event(self.pg.KEYDOWN, key=self.pg.K_ESCAPE, unicode='\x1b'))
        self.assertEqual(self.term.read_key(), 'ESC')
        self.assertNotIn(self.pg.K_w, self.term._held_movement)

    def test_hover_uses_furniture_rectangle_and_does_not_move_it(self):
        self.render()
        point = self.term._interior_context['camera'].to_screen(4500, 3900)
        self.pg.event.post(self.pg.event.Event(self.pg.MOUSEMOTION, pos=point, rel=(0, 0), buttons=(0, 0, 0)))
        self.pg.event.post(self.pg.event.Event(self.pg.KEYDOWN, key=self.pg.K_ESCAPE, unicode='\x1b'))
        self.assertEqual(self.term.read_key(), 'ESC')
        self.assertEqual(self.term._interior_context['hover_uid'], self.furniture.uid)
        self.assertEqual((self.furniture.x, self.furniture.y), (4230, 3520))

    def test_interior_assets_exist_and_bed_is_a_transparent_cutout(self):
        for visual_id in ('core:interior_floor', 'core:interior_wall', 'core:interior_bed'):
            path = self.term._visuals.resolve(self.term._visuals.ref('interiors', visual_id))
            self.assertIsNotNone(path)
            self.assertTrue(path.is_file(), str(path))
            self.assertGreater(self.pg.image.load(str(path)).get_width(), 100)
        bed = self.pg.image.load(str(self.term._visuals.resolve(self.term._visuals.ref('interiors', 'core:interior_bed'))))
        self.assertTrue(bed.get_flags() & self.pg.SRCALPHA)
        self.assertEqual(bed.get_at((0, 0)).a, 0)
        self.assertGreater(bed.get_bounding_rect(min_alpha=1).width, 0)

    def test_legacy_clutter_uses_native_prop_art_without_glyph_blocks(self):
        piece_ids = ('core:domestic_crockery_piece', 'core:hearth_wood_piece',
                     'core:laundry_basket_piece', 'core:pantry_crate_piece',
                     'core:metal_scrap_piece', 'core:smith_tool_rack_piece',
                     'core:bottle_shelf_piece', 'core:herb_bundle_piece')
        native_draw = self.term._draw_settlement_yard_piece
        for piece_id in piece_ids:
            with self.subTest(piece_id=piece_id):
                furniture = NS(uid='clutter-one', piece_id=piece_id, x=4230, y=3520,
                               w=1400, h=1200, solid=False)
                self.plan.furniture = [furniture]
                before = copy.deepcopy((vars(furniture), vars(self.player), vars(self.plan)))
                rendered = []

                def capture(piece, rect):
                    result = native_draw(piece, rect)
                    rendered.append((piece.id, result))
                    return result

                with patch.object(self.term, '_draw_settlement_yard_piece', side_effect=capture), \
                        patch.object(self.pg.draw, 'rect', wraps=self.pg.draw.rect) as rectangles:
                    self.render()
                self.assertEqual(rendered, [(piece_id, True)])
                self.assertFalse(any(call.args[1] == (132, 99, 63) for call in rectangles.call_args_list),
                                 'Native clutter must not fall through to the glyph block')
                self.assertEqual(before, (vars(furniture), vars(self.player), vars(self.plan)))

    def test_narrow_actual_window_keeps_interior_viewport_inside_window(self):
        self.term.screen = self.pg.display.set_mode((480, 360))
        self.render()
        self.assertTrue(self.term.screen.get_rect().contains(self.term._interior_context['used']))
        self.assertEqual(self.term.screen.get_clip(), self.term.screen.get_rect())


if __name__ == '__main__':
    unittest.main()
