"""Consolidated salvage panel navigation and observational rendering checks."""
import copy
import os
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry, SalvageDef
from worldseed.entities.components import Inventory
from worldseed.sim.commands import MoveCommand, SalvageActionCommand, StartSalvageCommand, StartSalvageGameCommand
from worldseed.systems.crafting import CraftingSystem
from worldseed.systems.salvaging import SalvagingSystem
from worldseed.systems.state import LivingWorldState
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.ui.salvage_panel import SalvagePanelMixin, run_salvage_panel, salvage_panel_data
from worldseed.ui.widgets import MenuRow


class SalvagePanelControllerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    def make(self, copies=2):
        reg = copy.copy(self.registry)
        reg.salvage = {'core:wood': SalvageDef('test:wood', 'core:wood', 8, 1,
                                             {'core:bark': (1, 3)}, method='carve',
                                             description='Dry grain marks the clean cuts.')}
        state = LivingWorldState(player_crafting_discovery_enabled=True)
        inv = Inventory({'core:wood': copies})
        system = SalvagingSystem(state, reg)
        commands = []
        sim = SimpleNamespace(state=state, salvaging=system, crafting=CraftingSystem(state, reg),
                              log=[], player_skill=lambda key: state.player_skills.get(key, 0))
        def execute(command):
            commands.append(command)
            if isinstance(command, (StartSalvageCommand,StartSalvageGameCommand)):
                begin=system.begin_game if isinstance(command,StartSalvageGameCommand) else system.begin
                ok, message, _ = begin(command.item_id, inv, b'salvage-panel')
            elif isinstance(command, SalvageActionCommand):
                ok, message, _ = system.act(command.choice_id, inv, b'salvage-panel')
            elif isinstance(command, MoveCommand):
                ok, message = True, 'Moved while retaining salvage.'
            else:
                raise AssertionError(type(command))
            self.assertTrue(ok, message)
            sim.log.append(SimpleNamespace(message=message))
        sim.execute = execute
        ctx = SimpleNamespace(sim=sim, registry=reg, player_id=1,
                              entities=SimpleNamespace(get=lambda actor, kind: inv))
        return ctx, state, inv, commands

    def term(self, read):
        class Term:
            mouse_ui = True
            _floating_panel_stack = [True]
            def __init__(self): self.frames = []; self.page_starts = []
            def size(self): return 100, 35
            def menu_page_size(self, presentation): return 6
            def menu_grid_columns(self, presentation): return 2
            def present_feature_menu(self, presentation, title, rows, selected, **kwargs):
                self.frames.append((presentation, rows, selected, kwargs['data']))
                self.page_starts.append(kwargs['page_start'])
            def read_key(self): return read(self)
            def present(self, text): pass
        return Term()

    @staticmethod
    def action(ctx):
        view = ctx.sim.salvaging.session_view()
        if view['phase'] == 'inspection':
            return 'inspect'
        if view.get('version') == 2:
            project=ctx.sim.state.player_salvage_session
            ready=next(index for index,node in enumerate(project['nodes'])
                       if not node['done'] and (node['depends']<0 or project['nodes'][node['depends']]['done']))
            if view['selected_node'] != ready:
                return 'select:'+str(ready)
            return 'work:'+project['nodes'][ready]['ideal']
        return ctx.sim.salvaging._stage(ctx.sim.state.player_salvage_session,
                                        ctx.registry.salvage[view['item_id']])['correct']

    def test_preview_escape_does_not_reserve_or_mutate(self):
        ctx, state, inv, commands = self.make()
        before = state.to_dict(), dict(inv.items)
        term = self.term(lambda term: 'ESC')
        self.assertEqual(run_salvage_panel(ctx, term), '__UI_BACK__')
        self.assertEqual((state.to_dict(), inv.items), before)
        self.assertEqual(commands, [])
        self.assertIn('previews', term.frames[0][3])
        self.assertEqual({frame[0] for frame in term.frames}, {'salvaging_unified'})

    def test_active_project_resumes_in_same_panel_when_last_source_is_reserved(self):
        ctx, state, inv, commands = self.make(1)
        ctx.sim.execute(StartSalvageCommand(1, 'core:wood'))
        reserved = copy.deepcopy(state.player_salvage_session)
        term = self.term(lambda term: 'ESC')
        run_salvage_panel(ctx, term)
        data = term.frames[0][3]
        self.assertIn('core:wood', data['items'])
        self.assertEqual(data['items']['core:wood']['count'], 0)
        self.assertEqual(data['active_session']['phase'], 'inspection')
        self.assertEqual(state.player_salvage_session, reserved)
        self.assertEqual(len(commands), 1)

    def test_two_salvages_complete_without_preview_or_result_routes_and_create_outputs_once(self):
        ctx, state, inv, commands = self.make()
        def read(term):
            view = ctx.sim.salvaging.session_view()
            if view:
                return 'UI_ACTION:salvage:act:' + self.action(ctx)
            if state.salvaging_attempts < 2:
                return 'UI_ACTION:salvage:begin'
            # A stale repeated final action cannot create another output batch.
            if not getattr(term, 'stale_sent', False):
                term.stale_sent = True
                return 'UI_ACTION:salvage:act:lift_core'
            return 'ESC'
        term = self.term(read)
        self.assertEqual(run_salvage_panel(ctx, term), '__UI_BACK__')
        self.assertFalse(state.player_salvage_session)
        self.assertEqual(state.salvaging_attempts, 2)
        self.assertEqual(inv.count('core:wood'), 0)
        self.assertEqual(len(state.player_salvage_log), 2)
        self.assertEqual(inv.count('core:bark'), sum(row['outputs']['core:bark'] for row in state.player_salvage_log))
        self.assertGreaterEqual(len(commands), 12)
        self.assertTrue(any(frame[3]['result'] for frame in term.frames))
        self.assertEqual({frame[0] for frame in term.frames}, {'salvaging_unified'})

    def test_keyboard_begin_and_numbered_stages_finish_without_mouse(self):
        ctx, state, inv, commands = self.make()
        def read(term):
            view = ctx.sim.salvaging.session_view()
            if view:
                correct = self.action(ctx)
                return 'UI_ACTION:salvage:act:' + correct
            return 'b' if not state.salvaging_attempts else 'ESC'
        term = self.term(read)
        run_salvage_panel(ctx, term)
        self.assertGreaterEqual(len(commands), 6)
        self.assertEqual(state.player_salvage_log[-1]['score'], 100)
        self.assertFalse(state.player_salvage_session)
        self.assertEqual({frame[0] for frame in term.frames}, {'salvaging_unified'})

    def test_escape_midgame_preserves_exact_project_for_reopen(self):
        ctx, state, inv, commands = self.make()
        keys = iter(['UI_ACTION:salvage:begin', 'UI_ACTION:salvage:act:inspect', 'ESC'])
        run_salvage_panel(ctx, self.term(lambda term: next(keys)))
        self.assertEqual(state.player_salvage_session['phase'], 'work')
        saved = copy.deepcopy(state.player_salvage_session)
        run_salvage_panel(ctx, self.term(lambda term: 'ESC'))
        self.assertEqual(state.player_salvage_session, saved)
        self.assertEqual(inv.count('core:wood'), 1)
        self.assertEqual(len(commands), 2)

    def test_cancel_search_pops_one_route_and_preserves_grid_selection_and_scroll(self):
        ctx, state, inv, commands = self.make()
        ctx.registry.salvage = dict(self.registry.salvage)
        for iid in list(ctx.registry.salvage)[:10]:
            inv.add(iid, 2)
        before = state.to_dict(), dict(inv.items)
        keys = iter(['END', 'UI_ACTION:search', 'ESC', 'ESC'])
        term = self.term(lambda term: next(keys))
        run_salvage_panel(ctx, term)
        self.assertEqual(term.page_starts[-2], term.page_starts[-1])
        self.assertGreater(term.page_starts[-1], 0)
        self.assertEqual(term.frames[-2][2], term.frames[-1][2])
        self.assertEqual(term.frames[-2][3]['selected_key'], term.frames[-1][3]['selected_key'])
        self.assertEqual((state.to_dict(), inv.items), before)
        self.assertEqual(commands, [])

    def test_tabs_and_world_movement_keep_navigation_and_salvage_authority(self):
        ctx, state, inv, commands = self.make()
        keys = iter(['w', 'UI_ACTION:tab:recipes'])
        term = self.term(lambda term: next(keys))
        self.assertEqual(run_salvage_panel(ctx, term), 'UI_ACTION:tab:recipes')
        self.assertEqual(len(commands), 1)
        self.assertIsInstance(commands[0], MoveCommand)
        self.assertFalse(state.player_salvage_session)
        self.assertEqual(inv.count('core:wood'), 2)

    def test_read_model_does_not_disclose_unknown_recipe_uses(self):
        ctx, state, inv, commands = self.make()
        before = state.to_dict(), dict(inv.items)
        data = salvage_panel_data(ctx, inv)
        parts = data['previews']['core:wood']['guaranteed']
        self.assertTrue(all(not part['uses'] for part in parts))
        self.assertEqual((state.to_dict(), inv.items), before)
        self.assertEqual(commands, [])


@unittest.skipUnless(PygameTerminal.available(), 'requires pygame-ce')
class SalvagePanelRenderingTests(unittest.TestCase):
    def setUp(self):
        # The mixin can also be checked before app/terminal wiring is applied.
        terminal_type = PygameTerminal if issubclass(PygameTerminal, SalvagePanelMixin) else type('SalvageTestTerminal', (PygameTerminal, SalvagePanelMixin), {})
        self.term = terminal_type(1280, 800)
        self.term.enter()
        self.term.pg.event.clear()
        self.registry = ContentRegistry.load(DATA_DIR)

    def tearDown(self): self.term.restore()

    def data(self):
        state = LivingWorldState()
        inv = Inventory({iid: 3 for iid in list(self.registry.salvage)[:36]})
        sim = SimpleNamespace(state=state, salvaging=SalvagingSystem(state, self.registry),
                              crafting=CraftingSystem(state, self.registry), player_skill=lambda key: 0)
        ctx = SimpleNamespace(sim=sim, registry=self.registry)
        data = salvage_panel_data(ctx, inv)
        return ctx, inv, data

    def test_minimum_and_standard_grid_capacity_and_controls_fit_panel(self):
        _, _, data = self.data()
        for size in ((740, 500), (900, 620)):
            with self.subTest(size=size):
                self.term._floating_panels['crafting'] = {'x': 16, 'y': 16, 'w': size[0], 'h': size[1]}
                capacity = self.term._salvage_browser_geometry()['capacity']
                rows = [MenuRow(iid, row['name']) for iid, row in data['items'].items()][:capacity]
                self.term._present_salvaging_unified('SALVAGING', rows, 0, data=data, total=len(data['items']))
                targets = self.term._pointer_targets
                bounds = self.term.pg.Rect(16, 16, *size)
                self.assertEqual(len([token for _, token in targets if token.startswith('UI_SELECT:')]), capacity)
                self.assertTrue(all(bounds.contains(rect) for rect, _ in targets))
                self.assertIn('UI_ACTION:salvage:begin', {token for _, token in targets})

    def test_hover_and_material_wheel_keep_action_selection_stable(self):
        _, _, data = self.data()
        self.term._floating_panels['salvaging'] = {'x': 16, 'y': 16, 'w': 740, 'h': 500}
        capacity = self.term.menu_page_size('salvaging_unified')
        rows = [MenuRow(iid, row['name']) for iid, row in data['items'].items()][:capacity]
        data['selected_key'] = rows[0].key
        self.term.present_feature_menu('salvaging_unified', 'SALVAGING', rows, 0, data=data, total=len(data['items']))
        second = next(rect for rect, token in self.term._pointer_targets if token == 'UI_SELECT:1')
        pg = self.term.pg
        pg.event.clear()
        pg.event.post(pg.event.Event(pg.MOUSEMOTION, pos=second.center, rel=(1, 0), buttons=(0, 0, 0)))
        pg.event.post(pg.event.Event(pg.KEYDOWN, key=pg.K_ESCAPE, unicode=''))
        self.assertEqual(self.term.read_key(), 'UI_REDRAW')
        self.assertEqual(self.term._panel_detail_view[0], 'salvage:' + rows[0].key)
        key, detail, maximum = self.term._panel_detail_view
        self.assertGreater(maximum, 0)
        self.term._last_mouse = detail.center
        pg.event.clear()
        pg.event.post(pg.event.Event(pg.MOUSEWHEEL, y=-1, x=0))
        self.assertEqual(self.term.read_key(), 'UI_REDRAW')
        self.assertGreater(self.term._panel_detail_states[key], 0)
        self.assertEqual(data['selected_key'], rows[0].key)

    def test_minigame_cue_fits_above_three_attached_choice_buttons(self):
        ctx, inv, data = self.data()
        iid = next(iter(data['items']))
        # Supply tools if the authored source requires them.
        for tool_id in self.registry.items:
            inv.add(tool_id, 2)
        self.assertTrue(ctx.sim.salvaging.begin(iid, inv, b'panel-cue')[0])
        self.assertTrue(ctx.sim.salvaging.act('inspect', inv, b'panel-cue')[0])
        data['active_session'] = ctx.sim.salvaging.session_view()
        self.term._floating_panels['crafting'] = {'x': 16, 'y': 16, 'w': 740, 'h': 500}
        rows = [MenuRow(iid, data['items'][iid]['name'])]
        before = copy.deepcopy(data)
        with patch.object(self.term, '_panel_text', wraps=self.term._panel_text) as text:
            self.term._present_salvaging_unified('SALVAGING', rows, 0, data=data)
        cue = data['active_session']['cue']
        call = next(call for call in text.call_args_list if call.args[0] == cue)
        rect = self.term.pg.Rect(call.args[1])
        lines = self.term._wrap_pixel_text(cue, self.term.small_font, rect.width)
        self.assertLessEqual(len(lines) * self.term.small_font.get_linesize(), rect.height)
        choices = [rect for rect, token in self.term._pointer_targets if token.startswith('UI_ACTION:salvage:act:') and not token.endswith(('tune_left','tune_right'))]
        self.assertEqual(len(choices), 3)
        self.assertLessEqual(rect.bottom, min(button.y for button in choices))
        self.assertEqual(data, before)


if __name__ == '__main__': unittest.main()
