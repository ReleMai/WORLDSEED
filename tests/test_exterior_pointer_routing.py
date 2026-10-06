"""Painted exterior pixels route by stable object IDs, not hidden floor cells."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from worldseed.app import UI_BACK, _building_context_menu
from worldseed.core.coords import WorldPos
from worldseed.systems.building_shells import BuildingShell
from worldseed.systems.state import pos_key
from worldseed.ui.pygame_terminal import PygameTerminal


class HiddenRecords(dict):
    """Fail immediately if a static building interaction inspects live cargo."""
    def get(self, *args, **kwargs):
        raise AssertionError('hidden records were inspected')

    def values(self):
        raise AssertionError('hidden entities were inspected')


def shell_fixture():
    return BuildingShell('house:pointer', 'town:pointer', 'residence', 'core:house',
                         ((0, 0), (1, 0), (0, 1), (1, 1)), (1, 0),
                         'door:pointer', 0, 'rectangular', (0, 0, 1, 1))


@unittest.skipUnless(PygameTerminal.available(), 'pygame optional')
class ExteriorPointerEventTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'SDL_VIDEODRIVER': 'dummy', 'SDL_AUDIODRIVER': 'dummy'})
        self.env.start()
        self.term = PygameTerminal(640, 480)
        self.term.enter()
        self.pg = self.term.pg
        self.shell = shell_fixture()
        self.world = SimpleNamespace(tile_at=Mock(side_effect=AssertionError('hidden terrain query')))
        used = self.pg.Rect(30, 30, 200, 200)
        body = self.pg.Rect(30, 30, 100, 100)
        door = self.pg.Rect(90, 100, 10, 20)
        mask = self.pg.Mask(body.size, fill=True)
        door_mask = self.pg.Mask(door.size, fill=True)
        self.context = {'used': used, 'tile_px': 20, 'left': 0, 'top': 0, 'z': 0,
                        'known': {pos_key(0, 0, 0), pos_key(1, 0, 0)},
                        'world': self.world, 'npc_by': HiddenRecords(),
                        'creature_by': HiddenRecords(), 'pile_by': HiddenRecords(),
                        'shell_hit_regions': [
                            {'shell': self.shell, 'kind': 'body', 'rect': body, 'mask': mask},
                            {'shell': self.shell, 'kind': 'door', 'role': 'facade',
                             'rect': door, 'mask': door_mask, 'target': self.shell.entrance}]}
        self.term._hover_context = self.context
        self.term._input_mode = 'world'
        self.term._interior_context = None
        self.term._hit_regions = []

    def tearDown(self):
        self.term.restore()
        self.env.stop()

    def click(self, pixel):
        self.pg.event.clear()
        self.pg.event.post(self.pg.event.Event(self.pg.MOUSEBUTTONDOWN,
                                              button=3, pos=pixel))
        # A fallback Escape keeps a broken handler finite under the runner.
        self.pg.event.post(self.pg.event.Event(self.pg.KEYDOWN,
                                              key=self.pg.K_ESCAPE, unicode=''))
        with patch.object(self.term, '_animate_idle_effects'), \
             patch.object(self.term, '_pump_realtime', return_value=False):
            return self.term.read_key()

    def test_right_click_routes_unknown_projected_roof_pixel_to_building_body(self):
        pixel = (95, 50)
        self.assertNotIn(pos_key(3, 1, 0), self.context['known'])
        self.assertEqual(self.click(pixel), 'UI_BUILDING_MENU:body:house:pointer')
        self.world.tile_at.assert_not_called()

    def test_right_click_routes_unknown_projected_facade_pixel_to_authoritative_door(self):
        pixel = (95, 110)
        self.assertNotIn(pos_key(3, 4, 0), self.context['known'])
        self.assertEqual(self.click(pixel), 'UI_BUILDING_MENU:door:house:pointer')
        self.world.tile_at.assert_not_called()

    def test_facade_hover_reports_threshold_without_terrain_or_entity_queries(self):
        before = set(self.context['known'])
        lines = self.term._hover_lines_for(3, 4, (95, 110))
        self.assertEqual(lines[0], 'Residence')
        self.assertIn('Access threshold: 1, 0', lines)
        self.assertTrue(any('Entrance door' in line for line in lines))
        self.world.tile_at.assert_not_called()
        self.assertEqual(self.context['known'], before)

    def test_body_hover_is_exterior_only_even_above_an_unknown_ground_cell(self):
        lines = self.term._hover_lines_for(3, 1, (95, 50))
        self.assertEqual(lines, ['Residence', 'Building exterior — right-click to inspect'])
        self.world.tile_at.assert_not_called()

    def test_alpha_gap_falls_back_to_unexplored_without_hidden_queries(self):
        for region in self.context['shell_hit_regions']:
            region['mask'].clear()
        self.assertEqual(self.term._hover_lines_for(3, 4, (95, 110)), ['Unexplored'])
        self.assertEqual(self.click((95, 110)), 'UI_WORLD_MENU:3:4')
        self.world.tile_at.assert_not_called()

    def test_known_transparent_corner_describes_footprint_not_painted_action(self):
        for region in self.context['shell_hit_regions']:
            region['mask'].clear()
        self.context.update(shell_by={(0, 0, 0): self.shell}, registry=SimpleNamespace(),
                            sim=SimpleNamespace(), creature_by={}, npc_by={})
        self.world.tile_at = Mock(return_value=SimpleNamespace(
            terrain=SimpleNamespace(name='Grass', tags=())))
        lines = self.term._hover_lines_for(0, 0, (35, 35))
        self.assertIn('Building footprint — movement blocked', lines)
        self.assertFalse(any('right-click' in line for line in lines))


class ExteriorBuildingMenuTests(unittest.TestCase):
    def fixture(self):
        shell = shell_fixture()
        planned = SimpleNamespace(uid=shell.uid, footprint=shell.footprint,
                                  entrance=shell.entrance, enclosed=True,
                                  destroyed=False, condition=100, function='residence')
        physical = SimpleNamespace(structure_by_id=Mock(return_value=planned))
        sim = SimpleNamespace(interiors=SimpleNamespace(player_presence=lambda: None),
                              player_pos=WorldPos(-1, 0, 0),
                              discovered_tiles_set={pos_key(0, 0, 0), pos_key(1, 0, 0)},
                              settlement_physicalization=physical)
        return SimpleNamespace(sim=sim), shell, planned

    def test_body_routes_to_nearest_observed_plan_cell_not_painted_pixel(self):
        ctx, shell, _ = self.fixture()
        with patch('worldseed.app._world_context_menu', return_value='body inspected') as menu:
            result = _building_context_menu(ctx, object(), shell.uid, 'body')
        self.assertEqual(result, 'body inspected')
        self.assertEqual(menu.call_args.args[2], WorldPos(0, 0, 0))
        self.assertEqual(menu.call_args.kwargs, {'building_part': 'body'})

    def test_door_routes_to_known_authoritative_entrance(self):
        ctx, shell, _ = self.fixture()
        with patch('worldseed.app._world_context_menu', return_value='door inspected') as menu:
            result = _building_context_menu(ctx, object(), shell.uid, 'door')
        self.assertEqual(result, 'door inspected')
        self.assertEqual(menu.call_args.args[2], WorldPos(1, 0, 0))
        self.assertEqual(menu.call_args.kwargs, {'building_part': 'door'})

    def test_unobserved_building_and_unknown_entrance_do_not_open_actions(self):
        ctx, shell, _ = self.fixture()
        with patch('worldseed.app._world_context_menu') as menu:
            ctx.sim.discovered_tiles_set = {pos_key(0, 0, 0)}
            self.assertEqual(_building_context_menu(ctx, object(), shell.uid, 'door'), UI_BACK)
            ctx.sim.discovered_tiles_set.clear()
            self.assertEqual(_building_context_menu(ctx, object(), shell.uid, 'body'), UI_BACK)
        menu.assert_not_called()

    def test_real_building_actions_do_not_read_hidden_actors_cargo_or_resources(self):
        ctx, shell, planned = self.fixture()
        sim = ctx.sim
        sim.player_pos = WorldPos(1, -1, 0)
        sim.state = SimpleNamespace(ground_piles=HiddenRecords(), creatures=HiddenRecords(),
                                    npcs=HiddenRecords(), claim_monuments=HiddenRecords(),
                                    player_casing_property_id='', player_hunting_stance='normal')
        hidden = lambda label: Mock(side_effect=AssertionError(label))
        sim.building = SimpleNamespace(container_at=hidden('hidden container'))
        sim.hunting = SimpleNamespace(signs_at=hidden('hidden tracks'), home_at=hidden('hidden den'))
        sim.resources = SimpleNamespace(is_harvestable=hidden('hidden resource'))
        sim.fishing = SimpleNamespace(is_fishable=hidden('hidden fish'))
        sim.casing = SimpleNamespace(can_case=lambda structure: False)
        physical = sim.settlement_physicalization
        physical.shell_at = Mock(return_value=shell)
        physical.cell_at = Mock(return_value=SimpleNamespace(structure_id=planned.uid))
        physical.crossing_at = hidden('hidden crossing')
        physical.border_post_at = hidden('hidden border post')
        door = SimpleNamespace(role='entrance', locked=False, forced=False, condition=100)
        sim.property_security = SimpleNamespace(door_at=Mock(return_value=door))
        for part in ('body', 'door'):
            with self.subTest(part=part), patch('worldseed.app._select', return_value=None) as select:
                self.assertEqual(_building_context_menu(ctx, object(), shell.uid, part), UI_BACK)
                rows = dict(select.call_args.args[2])
                self.assertNotIn('gather', rows)
                self.assertNotIn('pickup', rows)
                self.assertNotIn('open', rows)
                self.assertNotIn('inspect_fixture', rows)
                self.assertEqual('enter_interior' in rows, part == 'door')
                self.assertEqual('inspect_building_exterior' in rows, part == 'body')
        self.assertEqual(sim.property_security.door_at.call_count, 1)


if __name__ == '__main__':
    unittest.main()
