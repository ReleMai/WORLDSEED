"""Pinned declarative production layout validation and deterministic selection."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from worldseed.core.rng import PCG32, hash_u64
from worldseed.systems.settlement_layouts import (
    LAYOUT_NAMESPACE, LAYOUT_VERSION, RANKS, RESOURCE_KINDS, choose_layout,
    layout_catalog, resource_definition, validate_catalog,
)


def environment(**overrides):
    values = dict(slope=20, relief=30, soil_fertility=70, wetness=40, drainage=65,
                  flood_risk=10, farmland=75, resource_opportunity=60,
                  resources=SimpleNamespace(forage=70, timber=60, stone=50, freshwater=65))
    values.update(overrides)
    return SimpleNamespace(**values)


class SettlementLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "worldseed" / "data" / "settlement_layouts_v11.json"
        cls.raw = json.loads(path.read_text(encoding="utf-8"))

    def test_catalog_covers_two_layouts_for_every_existing_resource(self):
        catalog = layout_catalog()
        self.assertEqual(catalog.version, 11)
        self.assertEqual(set(catalog.resources), RESOURCE_KINDS)
        self.assertEqual(len(catalog.recipes), 12)
        for kind in RESOURCE_KINDS:
            self.assertGreaterEqual(sum(kind in recipe.required_resources for recipe in catalog.recipes), 2)
            definition = resource_definition(kind)
            self.assertTrue(definition.purpose)
            self.assertEqual(len(definition.size), 2)
            self.assertTrue(all(5 <= n <= 25 for n in definition.size))
        self.assertGreaterEqual(sum(not recipe.required_resources for recipe in catalog.recipes), 2)

    def test_every_rank_has_bounded_targets_and_sparse_valid_links(self):
        for recipe in layout_catalog().recipes:
            for rank in RANKS:
                points = recipe.street_offsets(rank)
                self.assertTrue(6 <= len(points) <= 10)
                self.assertTrue(all(type(n) is int and -100 <= n <= 100 for p in points for n in p))
                self.assertEqual(len(points), len(set(points)))
                self.assertTrue(4 <= recipe.frontage_spacing <= 7)
                self.assertLessEqual(len(recipe.street_links), 5)
                for a, b in recipe.street_links:
                    self.assertNotEqual(a, b)
                    self.assertTrue(0 <= a < len(points) and 0 <= b < len(points))

    def test_same_inputs_and_resource_input_order_are_identical(self):
        env = environment()
        first = choose_layout(b"layout-order", "settlement:one", ["mining", "logging"], "stone_lane", env)
        self.assertIs(first, choose_layout(b"layout-order", "settlement:one", ["logging", "mining"], "stone_lane", env))
        self.assertEqual(first, choose_layout(b"layout-order", "settlement:one", {"logging", "mining"}, "stone_lane", env))

    def test_generation_order_and_unrelated_rng_draws_do_not_change_choice(self):
        seed, env = b"layout-isolation", environment()
        before = choose_layout(seed, "settlement:stable", ("farming", "livestock"), "market_green", env)
        rng = PCG32(123)
        for index in range(80):
            rng.u32()
            hash_u64(seed, "unrelated-layout-ui", index)
            choose_layout(seed, "settlement:" + str(index), ("logging", "fishing"), "riverfront", env)
        with patch.object(PCG32, "u32", side_effect=AssertionError("Shared random stream used")):
            self.assertEqual(before, choose_layout(seed, "settlement:stable", ("livestock", "farming"), "market_green", env))
        self.assertEqual(LAYOUT_NAMESPACE, "settlement-production-layout-v11")

    def test_recipe_selection_is_resource_causal_and_never_requires_an_absent_resource(self):
        env = environment()
        for kind in RESOURCE_KINDS:
            recipe = choose_layout(b"resource-only", "settlement:" + kind, [kind], "", env)
            self.assertIn(kind, recipe.required_resources)
        for pair in (("mining", "logging"), ("farming", "fishing"), ("logging", "livestock"), ()):
            recipe = choose_layout(b"pair-choice", "settlement:pair", pair, "riverfront", env)
            self.assertTrue(set(recipe.required_resources) <= set(pair))

    def test_physical_scoring_rewards_real_resources_and_penalizes_flooded_farmland(self):
        timber = resource_definition("logging")
        poor = environment(resources=SimpleNamespace(forage=60, timber=5, stone=70, freshwater=60))
        rich = environment(resources=SimpleNamespace(forage=60, timber=95, stone=70, freshwater=60))
        self.assertGreater(timber.score(rich), timber.score(poor))
        farm = resource_definition("farming")
        self.assertGreater(farm.score(environment(slope=5, flood_risk=5)),
                           farm.score(environment(slope=85, flood_risk=85)))
        recipe = choose_layout(b"physical", "settlement:physical", ["farming"], "wattle_common", environment())
        self.assertGreater(farm.score(environment(farmland=90), recipe.district_weights["farming"]),
                           farm.score(environment(farmland=5), recipe.district_weights["farming"]))

    def test_culture_preference_is_an_explicit_causal_term(self):
        recipe = next(r for r in layout_catalog().recipes if r.morphology == "quarry_fan")
        self.assertGreater(recipe.preference_score(["mining"], "stone_lane", environment()),
                           recipe.preference_score(["mining"], "riverfront", environment()))

    def test_returned_catalog_and_all_nested_collections_are_immutable(self):
        recipe = layout_catalog().recipes[0]
        with self.assertRaises(FrozenInstanceError): recipe.frontage_spacing = 9
        with self.assertRaises(TypeError): recipe.rank_counts["city"] = 4
        with self.assertRaises(TypeError): recipe.district_weights["farming"]["farmland"] = 100
        with self.assertRaises(TypeError): resource_definition("mining").weights["slope"] = -1
        with self.assertRaises(TypeError): layout_catalog().resources["mining"] = None

    def test_selection_only_reads_supplied_physical_fields(self):
        env = environment()
        before = deepcopy(env)
        for index in range(30):
            choose_layout(b"observational", "settlement:" + str(index), ["farming", "logging"], "", env)
        self.assertEqual(env, before)
        # No prepared environment is also a valid neutral selector; placement
        # legality is still the planner's responsibility, never this catalog.
        self.assertIsNotNone(choose_layout(b"missing-env", "settlement:test", [], "", None))

    def test_rejects_unsupported_rank_resource_and_version(self):
        recipe = layout_catalog().recipes[0]
        for rank in ("metropolis", 2, [], None):
            with self.assertRaises(ValueError): recipe.street_offsets(rank)
        for resources in (["unknown"], ["mining", "mining"], "farming", None):
            with self.assertRaises(ValueError): choose_layout(b"invalid", "settlement:test", resources, "", None)
        with self.assertRaises(ValueError): resource_definition("unknown")
        with self.assertRaises(ValueError): layout_catalog(12)
        with self.assertRaises(ValueError): layout_catalog(True)
        self.assertEqual(LAYOUT_VERSION, 11)

    def test_rejects_malformed_generation_catalog_without_silent_coercion(self):
        mutations = {
            "version": lambda d: d.update(version=12),
            "malformed id": lambda d: d["recipes"][0].update(id="Bad Id"),
            "duplicate id": lambda d: d["recipes"][1].update(id=d["recipes"][0]["id"]),
            "unknown required resource": lambda d: d["recipes"][0].update(required_resources=["gold"]),
            "duplicate resource": lambda d: d["resource_definitions"].append(deepcopy(d["resource_definitions"][0])),
            "negative weight": lambda d: d["recipes"][0]["environment_weights"].update(slope=-1),
            "boolean weight": lambda d: d["recipes"][0]["environment_weights"].update(slope=True),
            "unknown field": lambda d: d["recipes"][0]["environment_weights"].update(hidden_ore=5),
            "invalid inverse": lambda d: d["recipes"][0].update(inverse_fields=["hidden_ore"]),
            "malformed inverse": lambda d: d["recipes"][0].update(inverse_fields=[[]]),
            "oversized offset": lambda d: d["recipes"][0]["street_offsets"][0].__setitem__(0, 101),
            "fractional offset": lambda d: d["recipes"][0]["street_offsets"][0].__setitem__(0, 0.5),
            "missing rank": lambda d: d["recipes"][0]["rank_counts"].pop("city"),
            "unsupported rank": lambda d: d["recipes"][0]["rank_counts"].update(metropolis=10),
            "too many links": lambda d: d["recipes"][0]["street_links"].append([0,5]),
            "invalid link index": lambda d: d["recipes"][0]["street_links"][0].__setitem__(0, 6),
            "self link": lambda d: d["recipes"][0].update(street_links=[[0,0]]),
            "reversed duplicate link": lambda d: d["recipes"][0].update(street_links=[[0,1],[1,0]]),
            "invalid spacing": lambda d: d["recipes"][0].update(frontage_spacing=8),
            "unknown district": lambda d: d["recipes"][0]["district_weights"].update(gold={"slope":1}),
            "negative size": lambda d: d["resource_definitions"][0]["size"].__setitem__(0,-1),
            "unknown purpose": lambda d: d["resource_definitions"][0].update(purpose="gold_worksite"),
            "wrong resource purpose": lambda d: d["resource_definitions"][0].update(purpose="field"),
        }
        for label, mutate in mutations.items():
            with self.subTest(case=label):
                malformed = deepcopy(self.raw)
                mutate(malformed)
                with self.assertRaises(ValueError): validate_catalog(malformed)


if __name__ == "__main__":
    unittest.main()
