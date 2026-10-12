"""Primitive recipe substitutions, recovered plant uses and discovery stay physical."""
from collections import Counter
import unittest

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.entities.components import Inventory
from worldseed.systems.crafting import CraftingSystem
from worldseed.systems.state import LivingWorldState


class CraftingMaterialProgressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    def crafting(self, discovery=False):
        return CraftingSystem(
            LivingWorldState(player_crafting_discovery_enabled=discovery),
            self.registry,
        )

    def test_wild_fiber_to_cordage_to_salvaged_handle_knife(self):
        crafting = self.crafting()
        bag = Inventory({
            "core:nettles": 3, "core:stone_flake": 1,
            "core:tool_handles": 1,
        })
        for rid in ("core:strip_fibrous_plants", "core:twist_prepared_fiber",
                    "core:stone_knife"):
            ok, reason, _ = crafting.craft(rid, bag, set())
            self.assertTrue(ok, reason)
        self.assertEqual(bag.items, {"core:stone_knife": 1})

    def test_mixed_fibrous_plants_and_fine_fibers_are_interchangeable(self):
        crafting = self.crafting()
        bag = Inventory({"core:nettles": 1, "core:reed_bundle": 1,
                         "core:beachgrass": 1})
        self.assertEqual(crafting.resolve_inputs(
            self.registry.recipes["core:strip_fibrous_plants"], bag),
            {"core:nettles": 1, "core:reed_bundle": 1, "core:beachgrass": 1})
        self.assertTrue(crafting.craft("core:strip_fibrous_plants", bag, set())[0])
        bag = Inventory({"core:milkweed_pod": 1, "core:cotton_grass_tuft": 1})
        self.assertTrue(crafting.craft("core:tease_fine_plant_fiber", bag, set())[0])
        self.assertEqual(bag.items, {"core:fiber": 1})

    def test_campfire_tinder_from_salvaged_scraps_has_no_loop_gain(self):
        crafting = self.crafting()
        source = self.registry.recipes["core:craft_sort_brush_offcuts"]
        self.assertLess(source.outputs["core:plant_scraps"], 10)
        bag = Inventory({"core:plant_scraps": 10})
        self.assertIn("tinder_material", self.registry.items["core:plant_scraps"].tags)
        self.assertTrue(crafting.craft("core:pack_scrap_tinder", bag, set())[0])
        self.assertEqual(bag.items, {"core:brush": 1})
        self.assertIn("core:brush", self.registry.structures["core:campfire"].cost)

    def test_plant_scraps_are_generic_plant_feedstock_for_pulp(self):
        crafting = self.crafting()
        bag = Inventory({"core:plant_scraps": 3, "core:bark": 3,
                         "core:clean_water": 1})
        self.assertTrue(crafting.craft("core:blend_plant_pulp", bag, set())[0])
        self.assertEqual(bag.items, {"core:plant_fiber_pulp": 1})
        self.assertTrue(crafting.recipe_uses_item(
            self.registry.recipes["core:blend_plant_pulp"], "core:plant_scraps"))

    def test_stone_axe_requires_multiple_distinct_parts_and_accepts_sinew(self):
        crafting = self.crafting()
        bag = Inventory({"core:stone_flake": 1, "core:stone": 1,
                         "core:stout_branch": 1, "core:sinew_cord": 1})
        self.assertTrue(crafting.craft("core:stone_axe", bag, set())[0])
        self.assertEqual(bag.items, {"core:stone_axe": 1})
        bag = Inventory({"core:stone_flake": 1, "core:stone": 1,
                         "core:stout_branch": 1})
        before = bag.items.copy()
        self.assertFalse(crafting.craft("core:stone_axe", bag, set())[0])
        self.assertEqual(bag.items, before)

    def test_recipe_clues_match_real_alternative_items_without_omniscience(self):
        crafting = self.crafting(discovery=True)
        cases = {
            "core:stone_knife": (
                "core:stone_flake", "core:tool_handles", "core:sinew_cord"),
            "core:stone_axe": (
                "core:stone_flake", "core:stone", "core:stout_branch",
                "core:sinew_cord"),
            "core:strip_fibrous_plants": ("core:reed_bundle",),
            "core:tease_fine_plant_fiber": ("core:milkweed_pod",),
            "core:blend_plant_pulp": (
                "core:clean_water", "core:plant_scraps"),
        }
        for rid, samples in cases.items():
            with self.subTest(recipe=rid):
                recipe = self.registry.recipes[rid]
                bag = Inventory(dict(Counter(samples)))
                before = bag.items.copy()
                self.assertTrue(crafting.discovery_matches(recipe, samples))
                self.assertIn(recipe, crafting.pot_candidates(samples, bag))
                self.assertEqual(bag.items, before)

    def test_every_tagged_recipe_conserves_mass_even_with_lightest_option(self):
        for recipe in self.registry.recipes.values():
            if not recipe.input_tags:
                continue
            mass = sum(self.registry.items[iid].mass_g * n
                       for iid, n in recipe.inputs.items())
            for tag, count in recipe.input_tags.items():
                mass += min(item.mass_g for item in self.registry.items.values()
                            if tag in item.tags) * count
            output = sum(self.registry.items[iid].mass_g * n
                         for iid, n in recipe.outputs.items())
            self.assertLessEqual(output, mass, recipe.id)


if __name__ == "__main__":
    unittest.main()
