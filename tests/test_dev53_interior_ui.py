"""Room annotations, shared indoor HUD and observational light presentation."""
import copy
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from tests import test_interior_presentation as fixtures
from worldseed import app
from worldseed.sim.commands import MoveCommand
from worldseed.ui import interior_view
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.ui.router import HUD_BUTTONS, classify_key


@unittest.skipUnless(PygameTerminal.available(), 'pygame optional')
class InteriorRoomHUDTests(unittest.TestCase):
    setUp = fixtures.InteriorPresentationTests.setUp
    tearDown = fixtures.InteriorPresentationTests.tearDown
    render = fixtures.InteriorPresentationTests.render

    def test_room_tags_are_top_layer_backed_and_clipped(self):
        events = []
        original = interior_view._draw_backed_tag
        def tag(*args, **kwargs):
            events.append('tag')
            return original(*args, **kwargs)
        with patch.object(interior_view, '_draw_indoor_light', side_effect=lambda *args: events.append('light')), \
             patch.object(interior_view, '_draw_backed_tag', side_effect=tag):
            self.render()
        ctx = self.term._interior_context
        labels = [row for row in ctx['label_regions'] if row['kind'] == 'room']
        self.assertTrue(labels)
        self.assertLess(events.index('light'), events.index('tag'))
        for row in labels:
            self.assertTrue(ctx['used'].contains(row['rect']))
            self.assertEqual(self.term.screen.get_at((row['rect'].x+3, row['rect'].y+3))[:3], (25, 29, 29))

    def test_exit_annotation_follows_visible_door_and_upper_floor_has_no_exit(self):
        self.player.x, self.player.y = self.plan.entry_x, self.plan.entry_y
        self.render()
        exits = [row for row in self.term._interior_context['label_regions'] if row['kind'] == 'exit']
        self.assertEqual(len(exits), 1)
        self.assertIn('right-click door', exits[0]['text'])
        self.assertTrue(self.term._interior_context['used'].contains(exits[0]['rect']))
        self.plan.floor_index = 1
        self.render()
        self.assertFalse(any(row['kind'] == 'exit' for row in self.term._interior_context['label_regions']))
        self.plan.floor_index = 0
        self.player.y = 1000
        self.term._tile_px = 56
        self.render()
        self.assertFalse(any(row['kind'] == 'exit' for row in self.term._interior_context['label_regions']))

    def test_narrow_room_pill_retains_full_words_across_room_boundary(self):
        name = 'Service gallery'
        # This room paints only 84 pixels wide at normal zoom. Its label is
        # allowed to cross a room boundary rather than splitting Service.
        self.plan.rooms = [NS(name=name, rect=NS(x=6000, y=3500, w=3000, h=5000))]
        self.term._tile_px = 28
        self.render()
        ctx = self.term._interior_context
        pill = next(row for row in ctx['label_regions'] if row['kind'] == 'room')['rect']
        expected_width = self.term.small_font.size(name)[0]+12
        self.assertEqual(pill.width, expected_width)
        self.assertGreater(pill.width, round(3000*ctx['camera'].scale))
        self.assertEqual(pill.height, self.term.small_font.get_height()+8)
        self.assertTrue(ctx['used'].contains(pill))
        self.plan.rooms.append(NS(name='Private guest room', rect=NS(x=9000,y=3500,w=3000,h=5000)))
        self.render()
        room_pills = [row['rect'] for row in self.term._interior_context['label_regions'] if row['kind']=='room']
        self.assertEqual(len(room_pills),2)
        self.assertFalse(room_pills[0].colliderect(room_pills[1]))
        self.term.screen = self.pg.display.set_mode((480,360))
        self.render()
        for row in self.term._interior_context['label_regions']:
            self.assertTrue(self.term._interior_context['used'].contains(row['rect']))

    def test_door_context_retains_exact_free_coordinates(self):
        self.player.x, self.player.y = self.plan.entry_x, self.plan.entry_y
        self.render()
        point = self.term._interior_context['camera'].to_screen(self.plan.entry_x, self.plan.entry_y)
        expected = interior_view.pointer_units(self.term, point)
        self.pg.event.post(self.pg.event.Event(self.pg.MOUSEBUTTONDOWN, button=3, pos=point))
        self.assertEqual(self.term.read_key(), f'INTERIOR_CONTEXT:{expected[0]}:{expected[1]}')

    def test_indoor_toolbar_buttons_dispatch_same_router_tokens(self):
        self.render()
        targets = {token: rect for rect, token in self.term._pointer_targets}
        for label, token in HUD_BUTTONS:
            with self.subTest(button=label):
                self.assertIn(token, targets)
                self.assertNotEqual(classify_key(token).kind, 'none')
                self.pg.event.post(self.pg.event.Event(self.pg.MOUSEBUTTONDOWN, button=1, pos=targets[token].center))
                self.assertEqual(self.term.read_key(), token)

    def test_inventory_and_crafting_tokens_reach_retained_menu_dispatch(self):
        self.render()
        ctx = NS(sim=self.sim, registry=self.reg, entities=self.entities, player_id=self.pid)
        for token, callback in (('i', '_inventory_menu'), ('c', '_crafting_menu')):
            rect = next(r for r, t in self.term._pointer_targets if t == token)
            self.pg.event.post(self.pg.event.Event(self.pg.MOUSEBUTTONDOWN, button=1, pos=rect.center))
            intent = classify_key(self.term.read_key())
            with patch.object(app, callback, return_value=app.UI_BACK) as menu:
                self.assertEqual(app._handle_menu(ctx, self.term, intent.value), app.UI_BACK)
                menu.assert_called_once_with(ctx, self.term)
        self.assertEqual(self.player.space_id, self.plan.uid)

    def test_companion_panels_keep_indoor_backdrop_and_movement(self):
        self.render()
        self.term.present_feature_menu('inventory_unified', 'INVENTORY', [], 0, data={'items': {}})
        parent = self.pg.image.tostring(self.term.screen, 'RGBA')
        self.term.push_floating_panel()
        self.term.present_feature_menu('crafting_unified', 'CRAFTING', [], 0,
            data={'recipes': {}, 'categories': ['primitive'], 'category': 'primitive'})
        self.sim.execute = lambda command: commands.append(command)
        commands = []
        ctx = NS(sim=self.sim, registry=self.reg, entities=self.entities, player_id=self.pid)
        with patch.object(app, '_present_game_frame', side_effect=AssertionError('discarded retained stack')):
            app._live_panel_world_move(ctx, self.term, 'UI_WORLD_MOVE:w')
        self.assertEqual(commands, [MoveCommand(self.pid, 0, -1)])
        self.assertEqual(len(self.term._floating_panel_stack), 1)
        self.term.pop_floating_panel()
        self.assertEqual(self.pg.image.tostring(self.term.screen, 'RGBA'), parent)
        self.assertEqual(self.player.space_id, self.plan.uid)

    def test_hidden_npcs_are_not_painted_and_sidebar_never_lists_names(self):
        self.plan.walls = [NS(x=7800, y=0, w=300, h=15000)]
        other = NS(space_id=self.plan.uid, x=9500, y=self.player.y, action='sleeping')
        self.sim.state.npcs = {'secret': NS(name='Secret Resident')}
        self.sim.interiors.actors_in_space = lambda _: (('player', self.player), ('secret', other))
        actors = []
        native = interior_view._draw_actor
        def draw(term, sim, camera, uid, actor):
            actors.append(uid)
            return native(term, sim, camera, uid, actor)
        with patch.object(interior_view, '_draw_actor', side_effect=draw):
            self.render()
        self.assertEqual(actors, ['player'])

    def test_darkness_hides_distant_npc_art_but_real_light_reveals_it(self):
        self.plan.walls = []
        self.sim.clock.minute = 0
        other = NS(space_id=self.plan.uid, x=self.player.x+6500, y=self.player.y, action='standing')
        self.sim.state.npcs = {'secret': NS(name='Secret Resident')}
        self.sim.interiors.actors_in_space = lambda _: (('player', self.player), ('secret', other))
        with patch.object(interior_view, '_draw_actor') as draw:
            self.render()
            self.assertEqual([call.args[3] for call in draw.call_args_list], ['player'])
        self.plan.furniture.append(NS(uid='real-lamp', piece_id='core:lamp_stand_piece',
            x=other.x-200, y=other.y-200, w=400, h=400, solid=False))
        with patch.object(interior_view, '_draw_actor') as draw:
            self.render()
            self.assertIn('secret', [call.args[3] for call in draw.call_args_list])

    def test_indoor_look_reads_room_and_visible_furniture_not_outside_anchor(self):
        from worldseed.ui.interior_inspection import interior_look_screen
        self.plan.walls = [NS(x=7800, y=0, w=300, h=15000)]
        self.plan.furniture.append(NS(uid='hidden', piece_id='core:wardrobe_piece',
            x=10000, y=4000, w=1400, h=700))
        before = copy.deepcopy((vars(self.player), vars(self.plan), vars(self.sim.state)))
        for width in (28, 44, 88):
            text = interior_look_screen(self.sim, self.reg, width)
            self.assertIn('Sleeping chamber', text)
            self.assertNotIn('Wardrobe', text)
            self.assertTrue(all(len(line)<=width for line in text.splitlines()))
        ctx = NS(sim=self.sim, registry=self.reg)
        with patch.object(app, '_view_text') as display, \
             patch.object(app, '_present_game_frame', side_effect=AssertionError('look touched exterior')):
            app._look_mode(ctx, self.term)
        self.assertIn('INTERIOR LOOK', display.call_args.args[1])
        self.assertEqual(before, (vars(self.player), vars(self.plan), vars(self.sim.state)))

    def test_indoor_build_cannot_dispatch_outdoor_construction(self):
        ctx = NS(sim=self.sim, registry=self.reg, entities=self.entities, player_id=self.pid)
        with patch.object(app, '_select', side_effect=AssertionError('opened exterior construction')):
            result = app._handle_menu(ctx, self.term, 'b')
        self.assertIn('requires stepping outside', result)
        self.assertIn('Right-click indoor furniture', result)

    def test_light_display_is_observational_and_sample_budget_bounded(self):
        from worldseed.systems import illumination
        before = copy.deepcopy((vars(self.player), vars(self.plan), vars(self.sim.state)))
        self.term.screen = self.pg.display.set_mode((480, 360))
        with patch.object(illumination, 'indoor_light', wraps=illumination.indoor_light) as sample:
            self.render()
        self.assertLessEqual(sample.call_count, 30*22+1)
        self.assertEqual(before, (vars(self.player), vars(self.plan), vars(self.sim.state)))
        self.assertEqual(self.term.screen.get_clip(), self.term.screen.get_rect())
        for rect, token in self.term._pointer_targets:
            self.assertTrue(self.term.screen.get_rect().contains(rect), token)


if __name__ == '__main__':
    unittest.main()
