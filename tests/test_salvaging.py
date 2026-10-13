import tempfile
import unittest
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from worldseed.content.registry import ContentRegistry, ItemDef, SalvageDef, SalvageRareYield
from worldseed.entities.components import Inventory
from worldseed.persistence.database import WorldDatabase
from worldseed.persistence.validation import validate_sim_state
from worldseed.sim.commands import (StartSalvageCommand, StartSalvageGameCommand,
    SalvageActionCommand, QuickSalvageCommand, SalvagePerkCommand,
    ResetSalvagePerksCommand, ResearchSalvageDossierCommand)
from worldseed.systems.salvaging import SalvagingSystem
from worldseed.systems.state import LivingWorldState


def sample_registry():
    registry = ContentRegistry()
    registry.items = {
        'test:damaged_box': ItemDef('test:damaged_box', 'Damaged box', tool_qualities={'cut': 2}),
        'test:wood_parts': ItemDef('test:wood_parts', 'Wood pieces'),
        'test:rare_gear': ItemDef('test:rare_gear', 'Fine gear'),
        'test:knife': ItemDef('test:knife', 'Knife', tool_qualities={'cut': 2}),
    }
    registry.salvage['test:damaged_box'] = SalvageDef(
        'test:salvage_box', 'test:damaged_box', 8, 2,
        {'test:wood_parts': (1, 5)}, (SalvageRareYield('test:rare_gear', 1, 1, 12),),
        method='unfasten', description='Recover wood and intact fasteners from a damaged box.')
    return registry


def informed_choice(view):
    cue = view['cue']
    if view['phase'] == 'inspection':
        return 'inspect'
    if view['step'] == 0:
        return 'brace' if cue.startswith('Loose') else 'pad' if cue.startswith('Thin') else 'brush'
    if view['step'] == 1:
        return 'unfasten'
    return 'sort_parts' if 'mixed' in cue else 'clean_parts' if 'grit' in cue else 'lift_core'


def finish(system, inv, seed=b'salvage-fixture', careful=True):
    while (view := system.session_view()) is not None:
        choice = informed_choice(view)
        if not careful and view['phase'] != 'inspection':
            choice = next(row['id'] for row in view['choices'] if row['id'] != choice)
        ok, message, _ = system.act(choice, inv, seed, minute=500)
        if not ok:
            raise AssertionError(message)


class SalvagingTests(unittest.TestCase):
    def setUp(self):
        self.registry = sample_registry()
        self.state = LivingWorldState(player_crafting_discovery_enabled=True)
        self.inv = Inventory({'test:damaged_box': 2})
        self.system = SalvagingSystem(self.state, self.registry)

    def test_preview_and_session_rendering_are_observational(self):
        before = self.state.to_dict(), dict(self.inv.items)
        preview = self.system.preview('test:damaged_box', self.inv)
        self.assertEqual(preview['guaranteed'][0]['min'], 1)
        self.assertEqual(preview['rare'][0]['chance_percent'], 12)
        self.assertEqual(len(self.system.available_items(self.inv)), 1)
        preview['tools']['cut'] = 999
        self.assertIsNone(self.system.preview('missing:thing'))
        self.assertEqual((self.state.to_dict(), self.inv.items), before)
        self.system.begin('test:damaged_box', self.inv, b'salvage-fixture', 480)
        saved = self.state.to_dict()
        view = self.system.session_view()
        view['choices'].clear()
        self.assertEqual(self.state.to_dict(), saved)

    def test_input_consumed_at_start_and_only_three_valid_decisions_create_outputs(self):
        ok, message, _ = self.system.begin('test:damaged_box', self.inv, b'salvage-fixture', 480)
        self.assertTrue(ok, message)
        self.assertEqual(self.inv.count('test:damaged_box'), 1)
        self.assertEqual(self.state.salvaging_attempts, 1)
        before = self.state.to_dict(), dict(self.inv.items)
        self.assertFalse(self.system.begin('test:damaged_box', self.inv, b'salvage-fixture')[0])
        self.assertFalse(self.system.act('unfasten', self.inv, b'salvage-fixture')[0])
        self.assertFalse(self.system.act([], self.inv, b'salvage-fixture')[0])
        self.assertEqual((self.state.to_dict(), self.inv.items), before)
        self.assertTrue(self.system.act('inspect', self.inv, b'salvage-fixture')[0])
        self.assertEqual(self.state.player_salvaging_xp, 0)
        self.assertEqual(self.inv.count('test:wood_parts'), 0)
        for step in range(3):
            view = self.system.session_view()
            self.assertEqual(view['step'], step)
            self.assertEqual(len(view['choices']), 3)
            self.assertTrue(self.system.act(informed_choice(view), self.inv, b'salvage-fixture')[0])
            if step < 2:
                self.assertEqual(self.inv.count('test:wood_parts'), 0)
        self.assertFalse(self.state.player_salvage_session)
        self.assertGreaterEqual(self.inv.count('test:wood_parts'), 1)
        self.assertEqual(self.inv.count('test:damaged_box'), 1)
        self.assertEqual(self.state.player_salvage_log[-1]['score'], 6)
        self.assertEqual(self.state.player_salvaging_xp, 5)
        before = self.state.to_dict(), dict(self.inv.items)
        self.assertFalse(self.system.act('lift_core', self.inv, b'salvage-fixture')[0])
        self.assertEqual((self.state.to_dict(), self.inv.items), before)
        self.assertEqual(validate_sim_state(self.state.to_dict()), [])

    def test_every_stage_save_reload_preserves_result_and_does_not_alias_save(self):
        outputs = []
        for save_reload in (False, True):
            state = LivingWorldState()
            inv = Inventory({'test:damaged_box': 1})
            system = SalvagingSystem(state, self.registry)
            system.begin('test:damaged_box', inv, b'salvage-fixture', 480)
            while (view := system.session_view()) is not None:
                if save_reload:
                    raw = state.to_dict()
                    self.assertEqual(validate_sim_state(raw), [])
                    state = LivingWorldState.from_dict(raw)
                    raw['player_salvage_session']['challenges'].clear()
                    self.assertEqual(len(state.player_salvage_session['challenges']), 3)
                    system = SalvagingSystem(state, self.registry)
                system.act(informed_choice(view), inv, b'salvage-fixture', 500)
            outputs.append((inv.items, state.player_salvage_log, state.player_salvaging_xp))
        self.assertEqual(outputs[0], outputs[1])

    def test_care_and_skill_improve_yield_and_rare_odds_without_rerolls(self):
        rare_low = rare_high = 0
        for attempt in range(500):
            low = self.system.roll_outputs('test:damaged_box', 0, 0, b'quality-test', attempt)
            high = self.system.roll_outputs('test:damaged_box', 6, 10, b'quality-test', attempt)
            self.assertGreaterEqual(low['test:wood_parts'], 1)
            self.assertGreaterEqual(high['test:wood_parts'], low['test:wood_parts'])
            self.assertLessEqual(high['test:wood_parts'], 5)
            rare_low += low.get('test:rare_gear', 0)
            rare_high += high.get('test:rare_gear', 0)
            self.assertEqual(high, self.system.roll_outputs('test:damaged_box', 6, 10, b'quality-test', attempt))
        self.assertGreater(rare_low, 0)
        self.assertGreater(rare_high, rare_low)
        self.assertEqual(self.state.salvaging_attempts, 0)

    def test_failed_minigame_still_returns_useful_common_parts_and_practice(self):
        self.system.begin('test:damaged_box', self.inv, b'salvage-fixture', 480)
        finish(self.system, self.inv, careful=False)
        self.assertEqual(self.state.player_salvage_log[-1]['score'], 0)
        self.assertGreaterEqual(self.inv.count('test:wood_parts'), 1)
        self.assertGreater(self.state.player_salvaging_xp, 0)

    def test_requirements_equipment_and_readied_weapon_are_protected(self):
        definition = self.registry.salvage['test:damaged_box']
        self.registry.salvage[definition.item_id] = replace(definition, tool_qualities={'cut': 1})
        self.inv.items['test:damaged_box'] = 1
        before = dict(self.inv.items)
        self.assertFalse(self.system.begin('test:damaged_box', self.inv, b'tools')[0])
        self.assertEqual(self.inv.items, before)  # The source cannot act as its own tool.
        self.inv.add('test:knife', 1)
        self.state.player_equipment['hands'] = 'test:damaged_box'
        self.assertFalse(self.system.begin('test:damaged_box', self.inv, b'tools')[0])
        self.state.player_equipment.clear()
        self.state.player_readied_weapon = 'test:damaged_box'
        self.assertFalse(self.system.begin('test:damaged_box', self.inv, b'tools')[0])
        self.state.player_readied_weapon = ''
        self.assertTrue(self.system.begin('test:damaged_box', self.inv, b'tools', 480)[0])
        self.assertEqual(self.inv.count('test:knife'), 1)

    def test_progression_and_legacy_defaults(self):
        self.state.player_salvaging_xp = 22
        self.system.begin('test:damaged_box', self.inv, b'salvage-fixture', 480)
        finish(self.system, self.inv)
        self.assertEqual(self.state.player_skills['salvaging'], 1)
        self.assertEqual(self.state.player_salvaging_xp, 3)
        restored = LivingWorldState.from_dict({'player_skills': {'crafting': 2}})
        self.assertEqual(restored.player_skills['salvaging'], 0)
        self.assertEqual(restored.player_salvaging_xp, 0)
        self.assertEqual(restored.player_salvage_session, {})
        self.assertEqual(restored.salvaging_attempts, 0)

    def test_all_material_methods_offer_valid_three_choice_disassembly(self):
        definition = self.registry.salvage['test:damaged_box']
        for method in ('unfasten', 'strip', 'sort', 'crush', 'carve', 'clean'):
            for minutes in (5, 6, 7, 8, 11):
                self.registry.salvage[definition.item_id] = replace(definition, method=method, minutes=minutes)
                state = LivingWorldState()
                inv = Inventory({'test:damaged_box': 1})
                system = SalvagingSystem(state, self.registry)
                ok, message, elapsed = system.begin('test:damaged_box', inv, b'material-methods', 480)
                self.assertTrue(ok, message)
                while (view := system.session_view()) is not None:
                    choice = method if view['phase'] == 'disassembly' and view['step'] == 1 else informed_choice(view)
                    if view['phase'] == 'disassembly':
                        self.assertEqual(len({row['id'] for row in view['choices']}), 3)
                    ok, message, duration = system.act(choice, inv, b'material-methods', 480 + elapsed)
                    self.assertTrue(ok, message)
                    elapsed += duration
                self.assertEqual(elapsed, minutes)
                self.assertEqual(state.player_salvage_log[-1]['score'], 6)
                self.assertEqual(validate_sim_state(state.to_dict()), [])

    def test_verifier_rejects_corrupt_progress_and_duplicate_completion(self):
        self.system.begin('test:damaged_box', self.inv, b'salvage-fixture', 480)
        valid = self.state.to_dict()
        for key, value in (('step', 3), ('score', 99), ('challenges', []), ('attempt', 2), ('version', 9)):
            raw = deepcopy(valid)
            raw['player_salvage_session'][key] = value
            self.assertTrue(any('salvage' in issue for issue in validate_sim_state(raw)), key)
        self.assertTrue(validate_sim_state({'player_salvaging_xp': -1}))
        self.assertTrue(validate_sim_state({'player_salvage_session': ['broken']}))
        finish(self.system, self.inv)
        raw = self.state.to_dict()
        raw['player_salvage_log'].append(deepcopy(raw['player_salvage_log'][0]))
        self.assertTrue(any('duplicate' in issue for issue in validate_sim_state(raw)))
        # A corrupted project is not silently repaired or allowed to yield parts.
        self.state.player_salvage_session = {'version': 9}
        before = deepcopy(self.inv.items)
        self.assertFalse(self.system.act('inspect', self.inv, b'salvage-fixture')[0])
        self.assertEqual(self.inv.items, before)

    def test_catalog_validation_requires_common_yields_and_real_components(self):
        self.registry._validate()
        definition = self.registry.salvage['test:damaged_box']
        for invalid in (replace(definition, yields={}), replace(definition, yields={'test:missing': (1, 1)}),
                        replace(definition, yields={'test:wood_parts': (0, 2)}),
                        replace(definition, rare_yields=(SalvageRareYield('test:rare_gear', 1, 1, 101),))):
            self.registry.salvage[definition.item_id] = invalid
            with self.assertRaises(ValueError):
                self.registry._validate()

    def test_sqlite_save_verifier_preserves_active_project(self):
        from worldseed.core.coords import WorldPos
        self.system.begin('test:damaged_box', self.inv, b'salvage-fixture', 480)
        self.system.act('inspect', self.inv, b'salvage-fixture', 480)
        with tempfile.TemporaryDirectory() as folder:
            database = WorldDatabase.create(Path(folder) / 'salvage.db', 'Salvage fixture', b'salvage-fixture'.hex())
            try:
                database.save_state(turn=1, tile_deltas={}, player_id=1, position=WorldPos(0, 0, 0),
                                    inventory=self.inv.items, sim_state=self.state.to_dict())
                restored = LivingWorldState.from_dict(database.load_sim_state())
                self.assertEqual(restored.player_salvage_session, self.state.player_salvage_session)
                self.assertEqual(database.verify(), [])
            finally:
                database.close()


class SalvagingCommandTests(unittest.TestCase):
    def setUp(self):
        from tests.test_interior_engine import InteriorEngineTests
        fixture = InteriorEngineTests()
        self.addCleanup(fixture.doCleanups)
        self.sim, self.plan = fixture.prepared_simulation()
        registry = sample_registry()
        self.sim.registry.items.update(registry.items)
        self.sim.registry.salvage.update(registry.salvage)
        self.inv = self.sim.entities.get(self.sim.player_id, Inventory)
        self.inv.add('test:damaged_box', 1)

    def test_timed_work_advances_authoritative_clock_before_return_without_double_charge(self):
        from worldseed.sim.commands import WaitCommand
        sim=self.sim
        start=sim.clock.minute
        seen=[]
        def progress(command, duration, advance):
            self.assertIsInstance(command, WaitCommand)
            self.assertEqual(duration, 12)
            self.assertEqual(sim.clock.minute, start)
            advance(4)
            seen.append(sim.clock.minute)
            advance(8)
            seen.append(sim.clock.minute)
        sim._action_progress_callback=progress
        self.addCleanup(lambda: setattr(sim,'_action_progress_callback',None))
        sim.execute(WaitCommand(sim.player_id,12))
        self.assertEqual(seen,[start+4,start+12])
        self.assertEqual(sim.clock.minute,start+12)

    def test_rejected_salvage_does_not_start_a_progress_bar(self):
        sim=self.sim
        called=[]
        sim._action_progress_callback=lambda *_args:called.append(True)
        self.addCleanup(lambda: setattr(sim,'_action_progress_callback',None))
        start=sim.clock.minute
        sim.execute(StartSalvageCommand(sim.player_id,'test:not_owned'))
        self.assertEqual(called,[])
        self.assertEqual(sim.clock.minute,start)

    def test_actual_execute_handles_indoor_project_and_discovers_output_items(self):
        self.sim.state.player_crafting_discovery_enabled = True
        minute = self.sim.clock.minute
        self.sim.execute(StartSalvageCommand(self.sim.player_id, 'test:damaged_box'))
        self.assertEqual(self.inv.count('test:damaged_box'), 0)
        with patch.object(self.sim.building, 'nearby_station_ids', side_effect=AssertionError('Outdoor query')):
            while (view := self.sim.salvaging.session_view()) is not None:
                self.sim.execute(SalvageActionCommand(self.sim.player_id, informed_choice(view)))
        self.assertGreater(self.sim.clock.minute, minute)
        self.assertIn('test:wood_parts', self.sim.state.player_discovered_items)
        self.assertFalse(self.sim.state.player_salvage_session)
        self.assertEqual(validate_sim_state(self.sim.state.to_dict()), [])

    def test_new_tabletop_is_authorized_and_completes_inside_an_interior(self):
        sim, inv = self.sim, self.inv
        self.assertIsNotNone(sim.interiors.player_presence())
        start_minute = sim.clock.minute
        with patch.object(sim.building, 'nearby_station_ids',
                          side_effect=AssertionError('Outdoor station lookup from indoors')):
            sim.execute(StartSalvageGameCommand(sim.player_id, 'test:damaged_box'))
            self.assertEqual(inv.count('test:damaged_box'), 0)
            self.assertEqual(sim.salvaging.session_view()['version'], 2)
            self.assertEqual(sim.state.player_salvage_session['game'], 'disassembly')
            sim.execute(SalvageActionCommand(sim.player_id, 'inspect'))
            for _ in range(5):
                view = sim.salvaging.session_view()
                if view is None: break
                nodes = sim.state.player_salvage_session['nodes']
                chosen = next(i for i, n in enumerate(nodes) if not n['done'] and (
                    n['depends'] < 0 or nodes[n['depends']]['done']))
                sim.execute(SalvageActionCommand(sim.player_id, 'select:' + str(chosen)))
                sim.execute(SalvageActionCommand(sim.player_id, 'survey'))
                sim.execute(SalvageActionCommand(sim.player_id, 'work:' + nodes[chosen]['ideal']))
        self.assertIsNone(sim.salvaging.session_view())
        self.assertGreater(inv.count('test:wood_parts'), 0)
        self.assertEqual(sim.state.player_salvage_log[-1]['max_score'], 100)
        self.assertGreater(sim.clock.minute, start_minute)
        self.assertEqual(validate_sim_state(sim.state.to_dict()), [])

    def test_new_tabletop_can_resume_after_transition_to_outdoors(self):
        sim = self.sim
        sim.execute(StartSalvageGameCommand(sim.player_id, 'test:damaged_box'))
        sim.execute(SalvageActionCommand(sim.player_id, 'inspect'))
        saved = deepcopy(sim.state.player_salvage_session)
        # Simulate the permitted indoor/outdoor transition without moving the
        # outdoor player anchor to an unrelated point in this isolated fixture.
        sim.state.interior_actors.pop('player')
        self.assertIsNone(sim.interiors.player_presence())
        self.assertEqual(saved, sim.state.player_salvage_session)
        while sim.salvaging.session_view() is not None:
            nodes = sim.state.player_salvage_session['nodes']
            selected = next(i for i, node in enumerate(nodes) if not node['done'] and (
                node['depends'] < 0 or nodes[node['depends']]['done']))
            sim.execute(SalvageActionCommand(sim.player_id, 'select:' + str(selected)))
            sim.execute(SalvageActionCommand(sim.player_id, 'work:' + nodes[selected]['ideal']))
        self.assertEqual(len(sim.state.player_salvage_log), 1)
        self.assertEqual(validate_sim_state(sim.state.to_dict()), [])

    def test_new_commands_perks_batch_and_invalid_actor_are_guarded_indoor(self):
        sim, inv = self.sim, self.inv
        start = (deepcopy(sim.state.to_dict()), dict(inv.items), sim.clock.minute)
        for cmd in (StartSalvageGameCommand(999, 'test:damaged_box'),
                    SalvagePerkCommand(999, 'seam_sense'),
                    ResetSalvagePerksCommand(999),
                    ResearchSalvageDossierCommand(999, 'core:forge'),
                    QuickSalvageCommand(999, 'test:damaged_box', 1),
                    StartSalvageGameCommand(sim.player_id, 'test:missing'),
                    SalvagePerkCommand(sim.player_id, 'invalid_perk')):
            sim.execute(cmd)
        self.assertEqual((sim.state.to_dict(), inv.items, sim.clock.minute), start)
        sim.state.player_skills['salvaging'] = 10
        with patch.object(sim.building, 'nearby_station_ids',
                          side_effect=AssertionError('Outdoor station lookup from indoors')):
            for perk in ('fast_hands','sorted_scrap','sweep_job'):
                sim.execute(SalvagePerkCommand(sim.player_id, perk))
                self.assertIn(perk, sim.state.player_salvage_perks)
            inv.add('test:damaged_box', 3)
            sim.execute(QuickSalvageCommand(sim.player_id,'test:damaged_box', 4))
            self.assertEqual(inv.count('test:damaged_box'), 0)
            self.assertEqual(len(sim.state.player_salvage_log), 4)
            self.assertEqual(sim.state.salvaging_attempts, 4)
            sim.execute(ResearchSalvageDossierCommand(sim.player_id, 'core:forge'))
            self.assertIn('Lost Arts', sim.log[-1].message)
        self.assertEqual(validate_sim_state(sim.state.to_dict()), [])

    def test_invalid_actor_item_and_decision_leave_inventory_progress_and_time_unchanged(self):
        before = self.sim.state.to_dict(), dict(self.inv.items), self.sim.clock.minute
        for command in (StartSalvageCommand(999, 'test:damaged_box'), StartSalvageCommand(self.sim.player_id, 'test:absent'),
                        StartSalvageCommand(self.sim.player_id, []), SalvageActionCommand(self.sim.player_id, 'inspect')):
            self.sim.execute(command)
            self.assertEqual((self.sim.state.to_dict(), self.inv.items, self.sim.clock.minute), before)


if __name__ == '__main__':
    unittest.main()
