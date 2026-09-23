from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools.build_sprite_atlases import (
    ITEM_SUBCATEGORY_ORDER,
    ITEM_TYPE_ORDER,
    item_sort_key,
    ordered_items,
)

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
        self.assertEqual(len(assets), len(set(assets)), "duplicate item asset basenames")
        for row in self.items:
            asset = str(row.get("asset", ""))
            self.assertRegex(asset, r"^[a-z0-9_]+$", row["id"])
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
