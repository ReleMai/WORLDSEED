from __future__ import annotations

from collections import Counter
from types import SimpleNamespace
import unittest

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory
from worldseed.presentation.local_terrain import can_blend, configure_terrain_catalog
from worldseed.systems.crafting import CraftingSystem
from worldseed.systems.state import LivingWorldState
from worldseed.world.generator import WorldGenerator


class Dev16TerrainMeshingTests(unittest.TestCase):
    def tearDown(self):
        # Restore the module's built-in fallback contract for unrelated tests.
        configure_terrain_catalog({})

    def test_new_tagged_ground_terrain_auto_joins_mesher(self):
        configure_terrain_catalog({
            'core:grass': SimpleNamespace(tags=('surface','soil')),
            'mod:loam': SimpleNamespace(tags=('surface','soil')),
            'mod:ore': SimpleNamespace(tags=('underground','ore')),
        })
        self.assertTrue(can_blend('core:grass','mod:loam'))
        self.assertFalse(can_blend('core:grass','mod:ore'))


class Dev16CaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)
        cls.gen=WorldGenerator(b'dev16-cave-audit',cls.registry,version=7)

    def _first_entrance(self):
        caves=self.gen.caves
        self.assertIsNotNone(caves)
        for cy in range(-5,6):
            for cx in range(-5,6):
                ent=caves._entrance_for_cell(cx,cy)
                if ent:return ent
        self.fail('expected a deterministic v7 cave entrance in audit window')

    def test_surface_entrance_is_terrain_aware_and_reciprocal(self):
        ent=self._first_entrance()
        self.assertTrue(ent.relief>=420 or ent.elevation>=43000)
        self.assertEqual(self.gen.terrain_at(WorldPos(ent.x,ent.y,0)),'core:cave_mouth')
        for depth in range(1,ent.depth+1):
            self.assertEqual(self.gen.terrain_at(WorldPos(ent.x,ent.y,-depth)),'core:shaft')
        self.assertNotEqual(self.gen.terrain_at(WorldPos(ent.x,ent.y,-ent.depth-1)),'core:shaft')

    def test_depth_bands_and_ore_distribution_are_stratified(self):
        caves=self.gen.caves
        self.assertEqual(caves.level_info(1).band,'shallow caverns')
        self.assertEqual(caves.level_info(4).band,'sedimentary caves')
        self.assertEqual(caves.level_info(7).band,'deep fracture caves')
        self.assertEqual(caves.level_info(12).band,'deep crystalline caves')
        counts={}
        for z in (-1,-3,-6,-10):
            counts[z]=Counter(
                self.gen.terrain_at(WorldPos(x,y,z))
                for y in range(-48,49) for x in range(-48,49)
            )
        self.assertGreater(counts[-1]['core:coal_seam'],0)
        self.assertGreater(counts[-1]['core:aquifer'],0)
        self.assertGreater(counts[-3]['core:copper_vein'],0)
        self.assertGreater(counts[-10]['core:iron_vein'],counts[-3]['core:iron_vein'])
        self.assertEqual(counts[-10]['core:coal_seam'],0)
        self.assertEqual(counts[-10]['core:copper_vein'],0)


class Dev16CraftDiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)

    def test_material_discovery_requires_pot_for_recipe_branch(self):
        state=LivingWorldState(player_crafting_discovery_enabled=True)
        inv=Inventory()
        craft=CraftingSystem(state,self.registry)
        inv.add('core:stone',1)
        new_items,new_recipes=craft.sync_discoveries(inv)
        self.assertIn('core:stone',new_items)
        self.assertEqual(new_recipes,[])
        self.assertNotIn('core:stone_flake',state.player_discovered_recipes)
        # A compound tool is not handed out merely because stone was seen.
        self.assertNotIn('core:stone_axe',state.player_discovered_recipes)
        self.assertGreaterEqual(len(craft.recipe_pool_for_item('core:stone')),2)
        ok,msg,minutes=craft.combine_in_pot(('core:stone',),inv,b'pot-test')
        self.assertTrue(ok,msg)
        self.assertEqual(inv.count('core:stone'),0)
        self.assertEqual(len(state.player_discovered_recipes),1)
        # The stone axe now uses material-tag clues for shafts and bindings,
        # not two obsolete duplicate stone-flake clues. Use the actual
        # authored signature, including the physical item alternatives.
        axe=self.registry.recipes['core:stone_axe']
        ingredients=craft.discovery_examples(axe)
        self.assertLessEqual(len(ingredients),5)
        for iid in ingredients:
            inv.add(iid,1)
        craft.sync_discoveries(inv)
        self.assertEqual(craft.researchable_recipes(inv),[])
        ok,msg,minutes=craft.combine_in_pot(ingredients,inv,b'pot-test')
        self.assertTrue(ok,msg)
        self.assertGreaterEqual(minutes,10)
        self.assertIn(state.player_discovered_recipes[-1],self.registry.recipes)
        self.assertEqual(state.player_crafting_experiments,2)

    def test_browsing_discovery_tree_is_observational_and_state_roundtrips(self):
        state=LivingWorldState(player_crafting_discovery_enabled=True)
        inv=Inventory();inv.add('core:stone',1)
        craft=CraftingSystem(state,self.registry)
        before=state.to_dict()
        craft.discovered_recipes(inv);craft.researchable_recipes(inv);craft.discovery_tree_rows(inv)
        self.assertEqual(before,state.to_dict())
        craft.sync_discoveries(inv)
        restored=LivingWorldState.from_dict(state.to_dict())
        self.assertTrue(restored.player_crafting_discovery_enabled)
        self.assertEqual(restored.player_discovered_items,state.player_discovered_items)
        self.assertEqual(restored.player_discovered_recipes,state.player_discovered_recipes)

    def test_copper_content_has_full_mine_to_smelt_chain(self):
        self.assertIn('core:copper_vein',self.registry.terrains)
        self.assertIn('core:copper_ore',self.registry.items)
        self.assertIn('core:copper_ingot',self.registry.items)
        recipe=self.registry.recipes['core:copper_ingot']
        self.assertEqual(recipe.inputs.get('core:copper_ore'),2)
        self.assertEqual(recipe.process,'smelt_copper')


if __name__ == '__main__':
    unittest.main()
