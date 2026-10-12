"""Household provisioning is a one-time debit-and-storage seed, not loot refill."""
from types import SimpleNamespace as NS
import unittest
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.systems.property_intrusion import PropertyStorageSystem
from worldseed.systems.state import LivingWorldState

class HouseholdProvisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)

    def test_new_dishes_are_edible_and_have_crafting_paths(self):
        for iid in ("core:berry_barley_bun","core:hearth_root_stew"):
            item=self.registry.items[iid]
            self.assertGreater(item.nutrition,0)
            self.assertIn("food",item.tags)
            self.assertTrue(any(iid in r.outputs for r in self.registry.recipes.values()))

    def test_generated_home_food_once_and_persists_across_reload(self):
        state=LivingWorldState()
        fake=NS(state=state,seed=b"homestead-provision",registry=self.registry)
        town=NS(uid="test-town",stocks={})
        homes=[NS(uid="home:1",function="residence",destroyed=False),
               NS(uid="home:2",function="residence",destroyed=False)]
        result=PropertyStorageSystem._seed_household_food(fake,town,homes)
        self.assertGreaterEqual(result,10)
        self.assertGreater(town.stocks.get("core:berry_barley_bun",0),0)
        self.assertGreater(town.stocks.get("core:hearth_root_stew",0),0)
        first=dict(town.stocks)
        self.assertEqual(PropertyStorageSystem._seed_household_food(fake,town,homes),0)
        self.assertEqual(town.stocks,first)
        fake.state=LivingWorldState.from_dict(state.to_dict())
        self.assertEqual(PropertyStorageSystem._seed_household_food(fake,town,homes),0)
        self.assertEqual(town.stocks,first)

if __name__=="__main__":unittest.main()
