"""Variant appearance must not create a second building or goods authority."""
from __future__ import annotations

import copy
from dataclasses import asdict
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.presentation.visuals import VisualRegistry
from worldseed.systems.building_variants import (
    building_variant, catalog, parse_catalog, validate_catalog, variant_by_id,
)
from worldseed.systems.container_profiles import building_storage_profile
from worldseed.systems.interior_state import InteriorPlan
from worldseed.systems.interior_templates import profile_for, rooms_for_profile
from worldseed.systems.interiors import InteriorSystem, build_interior, exit_reachable, position_clear
from worldseed.systems.property_intrusion import PropertyStorageSystem
from worldseed.systems.state import LivingWorldState, SettlementState


class BuildingVariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    def structure(self, variant, *, uid=None, pinned=True):
        return SimpleNamespace(
            uid=uid or "structure:" + variant["asset"], function=variant["function"],
            variant_id=variant["id"] if pinned else "", building_form="rectangular",
            footprint=[(x, y) for y in range(5) for x in range(5)],
            entrance=(2, 4), enclosed=True, destroyed=False,
        )

    def test_thirty_authored_variants_and_genuinely_unique_valid_loot_sets(self):
        variants = catalog()
        self.assertGreaterEqual(len(variants), 30)
        self.assertEqual(len({row["asset"] for row in variants}), len(variants))
        self.assertEqual(len({tuple(sorted(row["loot"])) for row in variants}), len(variants))
        self.assertEqual(len({tuple(sorted(row["loot"][:5])) for row in variants}), len(variants))
        validate_catalog(self.registry)
        for variant in variants:
            self.assertTrue(set(variant["loot"]) <= set(self.registry.items))
            self.assertEqual(variant_by_id(variant["id"]), variant)

    def test_selection_is_order_independent_read_only_and_shared_by_shell_identity(self):
        structures = [self.structure(row, pinned=False) for row in catalog()]
        before = [copy.deepcopy(vars(row)) for row in structures]
        forward = {row.uid: building_variant(row)["id"] for row in structures}
        backward = {row.uid: building_variant(row)["id"] for row in reversed(structures)}
        self.assertEqual(forward, backward)
        self.assertEqual([vars(row) for row in structures], before)
        for structure in structures:
            shell = SimpleNamespace(uid=structure.uid, function=structure.function)
            self.assertEqual(building_variant(shell)["id"], forward[structure.uid])

    def test_explicit_variant_is_frozen_and_unknown_or_mismatched_variant_does_not_reroll(self):
        variant = catalog()[0]
        structure = self.structure(variant, uid="unrelated:identity")
        self.assertEqual(building_variant(structure)["id"], variant["id"])
        structure.variant_id = "core:retired_variant"
        self.assertIsNone(building_variant(structure))
        structure.variant_id = variant["id"]
        structure.function = "mod:observatory"
        self.assertIsNone(building_variant(structure))
        self.assertIsNone(building_variant(SimpleNamespace(uid="unknown", function="mod:observatory")))

    def test_saved_ground_variant_freezes_facade_selection_by_lookup_without_mutation(self):
        from worldseed.ui.exterior_view import _art_ref

        shell = SimpleNamespace(uid='structure:saved-facade', function='residence')
        selected = building_variant(shell)
        pinned = next(row for row in catalog()
                      if row['function'] == 'residence' and row['id'] != selected['id'])
        plan = InteriorPlan('interior:' + shell.uid, shell.uid, 'door:saved-facade',
                            5, 6, 0, 12000, 12000, variant_id=pinned['id'])
        before = plan.to_dict()
        manifest = {'building_shells': {row['id']: row['asset'] + '.png'
                                        for row in catalog()}}
        term = SimpleNamespace(_visuals=VisualRegistry(manifest, Path('.')))

        class LookupOnly(dict):
            def __iter__(self):
                raise AssertionError('Facade rendering scanned all saved interiors')

            def values(self):
                raise AssertionError('Facade rendering scanned all saved interiors')

        plans = LookupOnly({plan.uid: plan})
        self.assertEqual(_art_ref(term, shell)[0], selected['asset'])
        self.assertEqual(_art_ref(term, shell, plans)[0], pinned['asset'])
        self.assertEqual(plan.to_dict(), before)
        self.assertEqual(list(dict.keys(plans)), [plan.uid])

    def test_every_variant_uses_a_connected_indoor_grammar(self):
        signatures = set()
        for variant in catalog():
            with self.subTest(variant=variant["id"]):
                profile = profile_for(self.structure(variant))
                plan = InteriorPlan("interior:grammar", "grammar", "door", 0, 0, 0,
                                    profile["width"], profile["height"])
                plan.rooms, plan.walls, (plan.entry_x, plan.entry_y) = rooms_for_profile(
                    plan.uid, profile, plan.width, plan.height)
                self.assertTrue(position_clear(plan, plan.entry_x, plan.entry_y))
                for room in plan.rooms:
                    self.assertTrue(exit_reachable(plan, room.rect.x + room.rect.w // 2,
                                                  room.rect.y + room.rect.h // 2), room.name)
                signatures.add((plan.width, plan.height, profile["geometry"],
                                tuple(room.name for room in plan.rooms)))
        self.assertEqual(len(signatures), len(catalog()))

    def test_missing_upper_floor_uses_saved_variant_after_catalog_expansion(self):
        original = catalog()
        added = dict(variant_by_id("core:reed_cottage"))
        added.update(id="core:future_cottage", asset="future_cottage")
        expanded = tuple(sorted((*original, added), key=lambda row: row["id"]))
        # Find a deterministic identity whose unpinned choice changes when a
        # later content pack adds a style. Its saved ground floor is authority.
        for index in range(100):
            structure = self.structure(original[0], uid="structure:floor-pin:" + str(index), pinned=False)
            structure.function = "residence"
            selected = building_variant(structure)
            with patch("worldseed.systems.building_variants.catalog", return_value=expanded):
                changed = building_variant(structure)
            if selected["id"] != changed["id"]:
                break
        else:
            self.fail("Regression fixture did not exercise a changed catalog choice")
        door = SimpleNamespace(uid="door:floor-pin", property_id=structure.uid,
                               owner_uid="npc:owner", x=2, y=4, z=0)
        ground = build_interior(structure, door)
        pinned_profile = profile_for(structure, variant_id=ground.variant_id)
        expected_rooms, expected_walls, _ = rooms_for_profile(
            ground.uid + ":floor:1", pinned_profile, ground.width, ground.height)
        saved_geometry = copy.deepcopy((ground.rooms, ground.walls, ground.furniture))
        state = LivingWorldState()
        state.interiors[ground.uid] = ground
        physical = SimpleNamespace(structure_by_id=lambda uid: structure)
        system = InteriorSystem(SimpleNamespace(state=state, settlement_physicalization=physical))
        with patch("worldseed.systems.building_variants.catalog", return_value=expanded), \
                patch.object(system, "_bind_storage"), patch.object(system, "_furnish_prepared"):
            self.assertEqual(profile_for(structure, variant_id=""), profile_for(structure))
            self.assertEqual(building_variant(structure)["id"], changed["id"])
            self.assertIs(system._prepare(door), ground)
        upper = state.interiors[ground.uid + ":floor:1"]
        self.assertEqual((upper.rooms, upper.walls), (expected_rooms, expected_walls))
        self.assertEqual((upper.variant_id, upper.floor_material, upper.wall_material),
                         (ground.variant_id, ground.floor_material, ground.wall_material))
        self.assertEqual((ground.rooms, ground.walls, ground.furniture), saved_geometry)

    def test_existing_saved_rooms_are_not_rebuilt_by_catalog_inspection(self):
        payload = InteriorPlan("interior:legacy", "legacy", "door:legacy", 4, 5, 0,
                               9000, 10000, version=1).to_dict()
        payload.pop("variant_id", None)
        payload.pop("floor_material", None)
        payload.pop("wall_material", None)
        legacy = InteriorPlan.from_dict(payload)
        before = legacy.to_dict()
        for variant in catalog():
            profile_for(self.structure(variant))
        self.assertEqual(legacy.to_dict(), before)
        self.assertEqual((legacy.width, legacy.height, legacy.version), (9000, 10000, 1))

    def test_variant_stock_tables_preserve_original_container_slots_and_styles(self):
        for variant in catalog():
            structure = self.structure(variant)
            base = building_storage_profile(variant["function"])
            themed = building_storage_profile(variant["function"], structure)
            self.assertEqual((themed.primary, themed.inside, themed.outside),
                             (base.primary, base.inside, base.outside))
            self.assertEqual(themed.stock, variant["loot"])

    def storage_fixture(self, variant):
        structure = self.structure(variant)
        room = SimpleNamespace(uid=structure.uid + ":room", structure_plan_id=structure.uid,
                               kind="storage", cells=[(1, 1), (2, 1), (3, 1)])
        skeleton = SimpleNamespace(structures=[structure], rooms=[room], pieces=[])
        physical = SimpleNamespace(skeleton_for=lambda uid: skeleton,
                                   frontage_for=lambda uid: WorldPos(2, 5, 0),
                                   passable=lambda *args: True, cell_at=lambda pos: None)
        state = LivingWorldState()
        town = SettlementState("town:variants", "Stockford", 0, 0, 2, 4, 4, "", "", "",
                               stocks={iid: 20 for iid in self.registry.items})
        state.settlements[town.uid] = town
        # Isolate the original authored-stock reservation contract from the
        # separate, once-only village salvage-origin mechanism.
        state.resource_depletion["salvage-village-stock:" + town.uid] = state.clock_minute
        civics = SimpleNamespace(ensure_settlement=lambda uid: None,
                                 owner_for_structure=lambda *args: "npc:owner")
        return PropertyStorageSystem(state, self.registry, b"variant-stock-test", physical, civics), town, structure

    def test_every_variant_reserves_actual_existing_stock_once_without_creating_goods(self):
        for variant in catalog():
            with self.subTest(variant=variant["id"]):
                storage, town, structure = self.storage_fixture(variant)
                before = dict(town.stocks)
                result = storage.sync_settlement(town.uid)
                self.assertGreater(result.created, 0)
                primary = storage.by_id("property-storage:" + structure.uid)
                self.assertTrue(set(variant["loot"][:5]) <= set(primary.items))
                # Additional physical salvage finds can be allocated to this
                # container, but every item must debit existing town stock.
                self.assertTrue(set(primary.items) <= set(before))
                for iid, total in before.items():
                    self.assertEqual(town.stocks[iid] + sum(c.items.get(iid, 0)
                                                           for c in storage.state.containers.values()), total)
                stocks = dict(town.stocks)
                containers = {c.uid: asdict(c) for c in storage.state.containers.values()}
                self.assertEqual(storage.sync_settlement(town.uid).created, 0)
                self.assertEqual(town.stocks, stocks)
                self.assertEqual({c.uid: asdict(c) for c in storage.state.containers.values()}, containers)

    def test_empty_settlement_does_not_generate_themed_loot(self):
        storage, town, _ = self.storage_fixture(catalog()[0])
        town.stocks.clear()
        self.assertEqual(storage.sync_settlement(town.uid).reserved_items, 0)
        self.assertTrue(all(not container.items for container in storage.state.containers.values()))

    def test_restocking_and_catalog_changes_do_not_reseed_or_restyle_existing_containers(self):
        variant = variant_by_id("core:reed_cottage")
        storage, town, structure = self.storage_fixture(variant)
        storage.sync_settlement(town.uid)
        primary = storage.by_id("property-storage:" + structure.uid)
        primary.items.clear(); primary.name = "Player renamed chest"
        primary.locked = False; primary.picked = True; primary.last_tampered_minute = 123
        before = asdict(primary)
        stocks = dict(town.stocks)
        structure.variant_id = "core:merchant_villa"
        storage.sync_settlement(town.uid)
        self.assertEqual(asdict(primary), before)
        self.assertEqual(town.stocks, stocks)

    def test_bad_ids_duplicate_loot_and_invalid_grammars_are_rejected(self):
        raw = json.loads((Path(DATA_DIR) / "building_variants.json").read_text(encoding="utf-8"))
        for change in (lambda row: row.update(id="not namespaced"),
                       lambda row: row.update(asset="../../escape"),
                       lambda row: row["interior"].update(width=-4),
                       lambda row: row["interior"].update(geometry="unconnected_rooms"),
                       lambda row: row.update(loot=["core:wood", "core:wood"])):
            broken = copy.deepcopy(raw); change(broken["variants"][0])
            with self.assertRaises(ValueError):
                parse_catalog(broken)
        broken = copy.deepcopy(raw)
        broken["variants"][1]["loot"] = list(reversed(broken["variants"][0]["loot"]))
        with self.assertRaises(ValueError):
            parse_catalog(broken)


class BuildingVariantAssetTests(unittest.TestCase):
    def test_every_variant_has_its_own_exterior_asset_and_measured_door_anchor(self):
        from PIL import Image

        visuals = VisualRegistry.load_default()
        anchors = json.loads((Path(DATA_DIR).parent / "assets" / "building_shell_anchors.json").read_text(encoding="utf-8"))["assets"]
        paths = set()
        for variant in catalog():
            with self.subTest(variant=variant["id"]):
                path = visuals.resolve(visuals.ref("building_shells", variant["id"]))
                self.assertIsNotNone(path)
                self.assertTrue(path.is_file(), str(path))
                self.assertNotIn(path, paths); paths.add(path)
                image = Image.open(path).convert("RGBA")
                self.assertEqual(image.getpixel((0, 0))[3], 0)
                anchor = anchors[variant["asset"]]["door_rect"]
                x, y, width, height = anchor
                self.assertTrue(0 <= x < x + width <= 1000)
                self.assertTrue(0 <= y < y + height <= 1000)
                # The selectable threshold must sit on real facade art, never
                # on a transparent padded export corner.
                center = (min(image.width - 1, round((x + width // 2) * image.width / 1000)),
                          min(image.height - 1, round((y + height // 2) * image.height / 1000)))
                self.assertGreater(image.getpixel(center)[3], 16)


if __name__ == "__main__":
    unittest.main()
