"""Workshop-gated experiments, persistent hints, and intentional salvage choices."""
import unittest

from worldseed.config import DATA_DIR, REALTIME_SECONDS_PER_GAME_MINUTE
from worldseed.content.registry import ContentRegistry
from worldseed.entities.components import Inventory
from worldseed.systems.crafting import CraftingSystem
from worldseed.systems.salvaging import SalvagingSystem
from worldseed.systems.state import LivingWorldState
from tests.test_salvaging import sample_registry, informed_choice


class WorkshopDiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)

    def fixture(self):
        state=LivingWorldState(player_crafting_discovery_enabled=True)
        crafting=CraftingSystem(state,self.registry)
        for recipe in sorted(self.registry.recipes.values(),key=lambda x:x.id):
            if not recipe.station or not 1<=len(crafting.discovery_signature(recipe))<=5:
                continue
            if recipe.knowledge:
                state.player_knowledge.append(recipe.knowledge)
            try:samples=crafting.discovery_examples(recipe)
            except (StopIteration,KeyError):continue
            inv=Inventory({iid:samples.count(iid)*3 for iid in samples})
            return state,crafting,recipe,inv,samples
        self.fail("No station recipe has a valid experiment sample")

    def test_field_experiment_records_persistent_workshop_hint_not_recipe(self):
        state,crafting,recipe,inv,samples=self.fixture()
        # Force a single matching station outcome for a deterministic audit.
        original=crafting.pot_candidates
        crafting.pot_candidates=lambda items, inventory, station_id='': [recipe]
        before=dict(inv.items)
        try:
            ok,message,elapsed=crafting.combine_in_pot(samples,inv,b'workshop-hint')
        finally:crafting.pot_candidates=original
        self.assertTrue(ok,message)
        self.assertIn('I could probably make something with this at a',message)
        self.assertIn(recipe.id,[row['recipe_id'] for row in state.player_crafting_hints])
        self.assertNotIn(recipe.id,state.player_discovered_recipes)
        self.assertEqual(inv.items,before)
        self.assertLessEqual(elapsed,5)
        loaded=LivingWorldState.from_dict(state.to_dict())
        self.assertEqual(loaded.player_crafting_hints,state.player_crafting_hints)

    def test_workshop_context_unlocks_recipe_and_consumes_items(self):
        state,crafting,recipe,inv,samples=self.fixture()
        crafting.pot_candidates=lambda items,inventory,station_id='': [recipe]
        ok,msg,duration=crafting.combine_in_pot(samples,inv,b'workshop',station_id=recipe.station)
        self.assertTrue(ok,msg)
        self.assertIn(recipe.id,state.player_discovered_recipes)
        self.assertGreater(duration,0)
        self.assertLess(sum(inv.items.values()),len(samples)*3+len(recipe.outputs)+len(samples))

    def test_clock_is_slower_than_old_half_second_rate(self):
        self.assertGreaterEqual(REALTIME_SECONDS_PER_GAME_MINUTE,1.25)


class QuickSalvageTests(unittest.TestCase):
    def test_quick_salvage_has_no_rare_materials_and_only_one_xp(self):
        reg=sample_registry();state=LivingWorldState()
        inv=Inventory({'test:damaged_box':1})
        salvage=SalvagingSystem(state,reg)
        ok,message,minutes=salvage.quick('test:damaged_box',inv,b'quick',500)
        self.assertTrue(ok,message)
        self.assertEqual(state.salvaging_attempts,1)
        self.assertEqual(inv.count('test:damaged_box'),0)
        self.assertGreater(inv.count('test:wood_parts'),0)
        self.assertEqual(inv.count('test:rare_gear'),0)
        self.assertEqual(state.player_salvage_log[-1]['xp_gained'],1)
        self.assertLessEqual(minutes,12)
        self.assertFalse(salvage.quick('test:damaged_box',inv,b'quick')[0])

    def test_precision_calibration_is_explicit_and_saveable(self):
        reg=sample_registry();state=LivingWorldState()
        inv=Inventory({'test:damaged_box':1});salvage=SalvagingSystem(state,reg)
        self.assertTrue(salvage.begin('test:damaged_box',inv,b'precision',480)[0])
        self.assertTrue(salvage.act('inspect',inv,b'precision')[0])
        target=salvage.session_view()['target']
        dial=salvage.session_view()['dial']
        while dial!=target:
            self.assertTrue(salvage.act('tune_right',inv,b'precision')[0])
            dial=salvage.session_view()['dial']
        stage=salvage._stage(state.player_salvage_session,reg.salvage['test:damaged_box'])
        self.assertTrue(salvage.act(stage['correct'],inv,b'precision')[0])
        self.assertEqual(state.player_salvage_session['precision'],1)
        self.assertEqual(LivingWorldState.from_dict(state.to_dict()).player_salvage_session,state.player_salvage_session)


if __name__=='__main__':unittest.main()
