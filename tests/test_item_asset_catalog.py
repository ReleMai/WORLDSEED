from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools.build_sprite_atlases import (
    ITEM_SUBCATEGORY_ORDER,
    ITEM_TYPE_ORDER,
    item_sort_key,
    item_sections,
    ordered_items,
)
from worldseed.config import DATA_DIR
from worldseed.content.item_catalog import canonical_item_catalog, classified_item
from worldseed.content.registry import ContentRegistry, ItemDef

ROOT = Path(__file__).resolve().parents[1]
ITEMS = ROOT / "worldseed" / "data" / "items.json"
SPRITES = ROOT / "worldseed" / "assets" / "sprites" / "items"

WILD_PLANTS = {
    "core:berries", "core:blueberries", "core:raspberries", "core:wild_strawberries",
    "core:nettles", "core:wild_onion", "core:wild_carrot", "core:wild_grain", "core:cattail_root",
}
FARMED_PLANTS = {
    "core:wheat", "core:turnip", "core:barley", "core:beans",
    "core:cabbage", "core:carrot", "core:onion", "core:flax",
}
COOKING_HERBS = {"core:dandelion_greens"}
MEDICAL_HERBS = {"core:medicinal_herb", "core:yarrow", "core:plantain_leaf"}


class ItemAssetCatalogTests(unittest.TestCase):
    def setUp(self):
        self.items = json.loads(ITEMS.read_text(encoding="utf-8"))
        self.by_id = {row["id"]: row for row in self.items}

    def test_every_item_has_one_simple_unique_asset(self):
        assets = [str(row.get("asset", "")) for row in self.items]
        sprite_tags = [str(row.get("sprite_tag", "")) for row in self.items]
        self.assertEqual(len(assets), len(set(assets)), "duplicate item asset basenames")
        self.assertEqual(len(sprite_tags), len(set(sprite_tags)), "duplicate item sprite tags")
        for row in self.items:
            asset = str(row.get("asset", ""))
            sprite_tag = str(row.get("sprite_tag", ""))
            self.assertRegex(asset, r"^[a-z0-9_]+$", row["id"])
            self.assertRegex(sprite_tag, r"^[a-z0-9_]+$", row["id"])
            self.assertEqual(sprite_tag, asset, f"{row['id']} sprite_tag must identify its custom sprite")
            self.assertTrue((SPRITES / f"{asset}.png").is_file(), f"missing item asset for {row['id']}: {asset}.png")

    def test_item_sprite_directory_has_no_orphans(self):
        expected = {f"{row['asset']}.png" for row in self.items}
        actual = {path.name for path in SPRITES.glob("*.png")}
        self.assertEqual(expected, actual)

    def test_item_types_and_subcategories_are_canonical(self):
        allowed = set(ITEM_TYPE_ORDER)
        for row in self.items:
            self.assertIn(row["category"], allowed, row["id"])
            category = row["category"]
            subcategory = row.get("subcategory", "")
            if category in ITEM_SUBCATEGORY_ORDER:
                self.assertIn(subcategory, ITEM_SUBCATEGORY_ORDER[category], row["id"])
            else:
                self.assertFalse(subcategory, f"{row['id']} should not need subcategory {subcategory!r}")

    def test_plants_are_split_wild_and_farmed(self):
        for iid in WILD_PLANTS:
            self.assertEqual((self.by_id[iid]["category"], self.by_id[iid].get("subcategory")), ("plant", "wild"))
        for iid in FARMED_PLANTS:
            self.assertEqual((self.by_id[iid]["category"], self.by_id[iid].get("subcategory")), ("plant", "farmed"))

    def test_herbs_are_split_by_use(self):
        for iid in COOKING_HERBS:
            self.assertEqual((self.by_id[iid]["category"], self.by_id[iid].get("subcategory")), ("herb", "cooking"))
        for iid in MEDICAL_HERBS:
            self.assertEqual((self.by_id[iid]["category"], self.by_id[iid].get("subcategory")), ("herb", "medical"))
        self.assertIn("poisonous", ITEM_SUBCATEGORY_ORDER["herb"])

    def test_common_resources_remain_broad(self):
        resources = [row for row in self.items if row["category"] == "resource"]
        self.assertGreaterEqual(len(resources), 10)
        for row in resources:
            self.assertFalse(row.get("subcategory", ""), row["id"])

    def test_item_sort_is_deterministic(self):
        first = [(x["category"], x.get("subcategory", ""), x["name"], x["id"]) for x in ordered_items(self.items)]
        second = [(x["category"], x.get("subcategory", ""), x["name"], x["id"]) for x in ordered_items(list(reversed(self.items)))]
        self.assertEqual(first, second)
        self.assertEqual(
            [x["id"] for x in ordered_items(self.items)],
            [x["id"] for x in sorted(self.items, key=item_sort_key)],
        )

    def test_persisted_database_runtime_registry_and_catalog_share_order(self):
        expected = [row['id'] for row in ordered_items(self.items)]
        self.assertEqual([row['id'] for row in self.items], expected)
        registry = ContentRegistry.load(DATA_DIR)
        self.assertEqual(list(registry.items), expected)
        grouped = [row['id'] for _, _, _, rows in item_sections(self.items) for row in rows]
        self.assertEqual(grouped, expected)
        self.assertEqual(self.items, canonical_item_catalog(self.items))

    def test_miscellaneous_finds_are_grouped_by_physical_object(self):
        expected = {
            'core:bent_door_hinge': 'hardware', 'core:split_wagon_spoke': 'woodwork',
            'core:torn_apron': 'textiles', 'core:split_harness_strap': 'leatherwork',
            'core:chipped_crock': 'ceramics', 'core:clouded_window_pane': 'glassware',
            'core:waterlogged_ledger': 'paperwork', 'core:worn_whetstone': 'stonework',
            'core:jammed_ratchet_wheel': 'mechanisms', 'core:spoiled_herb_sachet': 'provisions',
            'core:cow_horn_ring': 'animal_parts',
        }
        for iid, group in expected.items():
            self.assertEqual((self.by_id[iid]['category'], self.by_id[iid]['subcategory']), ('misc', group))
        for row in self.items:
            tags = set(row.get('tags', ()))
            if tags & {'animal_part', 'village_salvage'}:
                self.assertEqual(row['category'], 'misc', row['id'])
        self.assertEqual(sum(row['category'] == 'misc' for row in self.items), 204)

    def test_finished_tackle_vessels_crops_and_herbs_have_meaningful_types(self):
        for iid in ('core:corn', 'core:pumpkin'):
            self.assertEqual((self.by_id[iid]['category'], self.by_id[iid]['subcategory']), ('plant', 'farmed'))
        for iid in ('core:fiber_line', 'core:sinew_line', 'core:braided_line',
                    'core:waxed_casting_line', 'core:twisted_reed_line'):
            self.assertEqual(self.by_id[iid]['category'], 'tool', iid)
        for iid in ('core:ceramic_mould', 'core:stoneware_crucible', 'core:ceramic_distillation_coil', 'core:porous_filter_candle'):
            self.assertEqual(self.by_id[iid]['category'], 'utility', iid)
        for iid in ('core:moonmint_sprig', 'core:saffron_crocus_tuft', 'core:frost_sage_branch'):
            self.assertEqual((self.by_id[iid]['category'], self.by_id[iid]['subcategory']), ('herb', 'cooking'))
        for iid in ('core:silverleaf_sprig', 'core:ghost_orchid_stem', 'core:blue_lotus_stalk'):
            self.assertEqual((self.by_id[iid]['category'], self.by_id[iid]['subcategory']), ('herb', 'medical'))
        self.assertEqual(self.by_id['core:clean_dressing_pad']['category'], 'material')
        self.assertEqual(self.by_id['core:bandage']['category'], 'medicine')
        self.assertEqual(self.by_id['core:spoiled_herb_sachet'].get('nutrition', 0), 0)

    def test_classification_changes_only_metadata_and_is_idempotent(self):
        for row in self.items:
            classified = classified_item(row)
            strip = lambda item: {key: value for key, value in item.items() if key not in {'category', 'subcategory'}}
            self.assertEqual(strip(classified), strip(row), row['id'])
            self.assertEqual(classified_item(classified), classified, row['id'])
        self.assertEqual(canonical_item_catalog(list(reversed(self.items))), self.items)

    def test_runtime_sort_has_stable_fallback_for_mod_groups(self):
        rows = [ItemDef('mod:z', 'Zinc Wisp', category='modded', subcategory='spirits'),
                ItemDef('mod:a', 'Amber Wisp', category='modded', subcategory='spirits'),
                ItemDef('core:stone', 'Stone', category='resource')]
        self.assertEqual([row.id for row in ordered_items(rows)], ['core:stone', 'mod:a', 'mod:z'])
        self.assertEqual(ordered_items(rows), ordered_items(reversed(rows)))
        with self.assertRaises(ValueError):
            item_sections([{'id': 'mod:x', 'name': 'X', 'category': 'modded'}])

    def test_names_are_clean_and_unique(self):
        names = [row["name"] for row in self.items]
        self.assertEqual(len(names), len(set(names)))
        self.assertNotIn("Flax Seed Seed", names)
        self.assertEqual(self.by_id["core:medicinal_herb"]["name"], "Medical Herb")
        for name in names:
            self.assertEqual(name, name.strip())
            self.assertNotRegex(name, r"\s{2,}")


if __name__ == "__main__":
    unittest.main()
