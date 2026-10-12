"""Authored stock grades share real, mass-safe recipes across recovery sources."""
from contextlib import redirect_stdout
from copy import deepcopy
from fractions import Fraction
import io
import json
import runpy
import shutil
from tempfile import TemporaryDirectory
from pathlib import Path
import unittest

from tools.build_material_crafting import (
    ITEM_PROFILES, RECIPE_PROFILES, apply_item_profiles, apply_recipe_profiles, audit_profiles,
)
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.entities.components import Inventory
from worldseed.systems.crafting import CraftingSystem
from worldseed.systems.state import LivingWorldState


class MaterialCraftingContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)
        cls.items = json.loads((Path(DATA_DIR) / "items.json").read_text(encoding="utf-8"))
        cls.recipes = json.loads((Path(DATA_DIR) / "recipes.json").read_text(encoding="utf-8"))

    def system(self):
        return CraftingSystem(LivingWorldState(), self.registry)

    def test_checked_in_profiles_are_idempotent_and_mass_safe(self):
        self.assertEqual(apply_item_profiles(deepcopy(self.items)), self.items)
        self.assertEqual(apply_recipe_profiles(deepcopy(self.recipes)), self.recipes)
        audit_profiles(self.items, self.recipes)
        self.assertEqual(set(ITEM_PROFILES) - set(self.registry.items), set())
        self.assertEqual(set(RECIPE_PROFILES) - set(self.registry.recipes), set())

    def test_salvage_regeneration_preserves_material_tags_and_shared_recipes(self):
        source = Path(__file__).resolve().parents[1] / "tools" / "build_salvage_content.py"
        rows = runpy.run_path(str(source))
        with TemporaryDirectory(prefix="worldseed-material-content-") as directory:
            target = Path(directory)
            for name in ("items.json", "recipes.json"):
                shutil.copyfile(Path(DATA_DIR) / name, target / name)
            rows["save"].__globals__["DATA"] = target
            with redirect_stdout(io.StringIO()):
                rows["finalize"]()
                rows["save"]()
            for name in ("items.json", "recipes.json", "salvage.json", "crafting_expansion.json"):
                self.assertEqual(json.loads((target / name).read_text(encoding="utf-8")),
                                 json.loads((Path(DATA_DIR) / name).read_text(encoding="utf-8")), name)

    def test_recovered_raw_and_refined_stock_have_meaningful_grades(self):
        catalog = self.registry.items
        for recovered, raw, refined in (("core:wood_pieces", "core:stout_branch", "core:hardwood_blank"),
                                         ("core:cloth_scraps", "core:pasture_fiber_bundle", "core:fiber")):
            self.assertEqual([catalog[iid].crafting_source for iid in (recovered, raw, refined)],
                             ["recovered", "raw", "refined"])
            self.assertLess(catalog[recovered].crafting_quality, catalog[raw].crafting_quality)
            self.assertLess(catalog[raw].crafting_quality, catalog[refined].crafting_quality)
        self.assertLess(catalog["core:metal_scraps"].crafting_quality,
                        catalog["core:iron_bloom"].crafting_quality)
        self.assertLess(catalog["core:iron_bloom"].crafting_quality,
                        catalog["core:steel_billet"].crafting_quality)

    def test_same_sword_recipe_consumes_more_recovered_parts_than_refined_stock(self):
        recipe = self.registry.recipes["core:iron_sword"]
        system = self.system()
        scraps = {"core:metal_scraps": 25, "core:wood_pieces": 25, "core:hide": 1}
        refined = {"core:iron_bloom": 1, "core:wood": 1, "core:hide": 1}
        for stock in (scraps, refined):
            bag = Inventory(stock.copy())
            self.assertEqual(system.resolve_inputs(recipe, bag), stock)
            self.assertEqual(bag.items, stock, "requirement browsing cannot consume stock")
        self.assertTrue(recipe.material_quality)
        self.assertEqual(recipe.outputs, {"core:iron_sword": 1})
        self.assertEqual(recipe.station, "core:forge")
        self.assertEqual(recipe.knowledge, "tech:smelting")
        self.assertEqual(recipe.process, "forge_metal_item")
        short = dict(scraps, **{"core:metal_scraps": 24})
        self.assertIsNone(system.resolve_inputs(recipe, Inventory(short)))

    def test_primitive_handle_and_shaft_retain_legacy_physical_counts(self):
        system = self.system()
        for rid, stock in (
            ("core:stone_knife", {"core:stone_flake": 1, "core:stout_branch": 1, "core:plant_cordage": 1}),
            ("core:stone_knife", {"core:stone_flake": 1, "core:tool_handles": 1, "core:plant_cordage": 1}),
            ("core:stone_knife", {"core:stone_flake": 1, "core:wood_pieces": 2, "core:plant_cordage": 1}),
            ("core:stone_axe", {"core:stone_flake": 1, "core:stone": 1, "core:stout_branch": 1, "core:sinew_cord": 1}),
            ("core:stone_hammer", {"core:stone": 1, "core:wood_pieces": 6, "core:plant_cordage": 1}),
        ):
            with self.subTest(recipe=rid, stock=stock):
                self.assertEqual(system.resolve_inputs(self.registry.recipes[rid], Inventory(stock)), stock)

    def test_same_yarn_recipe_accepts_clean_scraps_and_prepared_fiber(self):
        recipe = self.registry.recipes["core:craft_spun_yarn"]
        system = self.system()
        for stock in ({"core:cloth_scraps": 30}, {"core:fiber": 2},
                      {"core:pasture_fiber_bundle": 1, "core:cloth_scraps": 10}):
            with self.subTest(stock=stock):
                self.assertEqual(system.resolve_inputs(recipe, Inventory(stock)), stock)
        self.assertEqual(recipe.outputs, {"core:spun_yarn": 2})
        self.assertTrue(recipe.material_quality)
        self.assertIsNone(system.resolve_inputs(recipe, Inventory({"core:cloth_scraps": 29})))
        self.assertFalse(system.recipe_uses_item(recipe, "core:plant_scraps"),
                         "plant residue must first be stripped into usable fiber")

    def test_weighted_recipes_have_mass_safe_options_and_one_npc_authority(self):
        for rid in RECIPE_PROFILES:
            recipe = self.registry.recipes[rid]
            minimum = sum(self.registry.items[iid].mass_g * n for iid, n in recipe.inputs.items())
            for tag, demand in recipe.input_tags.items():
                minimum += min(Fraction(item.mass_g, recipe.input_units.get(item.id, 1))
                               for item in self.registry.items.values() if tag in item.tags) * demand
            output = sum(self.registry.items[iid].mass_g * n for iid, n in recipe.outputs.items())
            self.assertLessEqual(output, minimum, rid)
            processes = [proc for proc in self.registry.settlement_processes.values() if proc.recipe_id == rid]
            self.assertEqual(len(processes), 1, rid)
            self.assertEqual(processes[0].inputs, recipe.inputs)
            self.assertEqual(processes[0].outputs, recipe.outputs)

    def test_salvage_outputs_are_downstream_recipe_inputs(self):
        system = self.system()
        for component, recipe_id in (("core:metal_scraps", "core:iron_sword"),
                                     ("core:wood_pieces", "core:stone_knife"),
                                     ("core:cloth_scraps", "core:craft_spun_yarn"),
                                     ("core:plant_scraps", "core:reclaim_plant_fiber")):
            self.assertTrue(any(component in source.yields for source in self.registry.salvage.values()), component)
            self.assertTrue(system.recipe_uses_item(self.registry.recipes[recipe_id], component))


if __name__ == "__main__":
    unittest.main()
