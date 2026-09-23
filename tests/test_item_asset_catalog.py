from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools.build_sprite_atlases import ITEM_TYPE_ORDER, ordered_items

ROOT = Path(__file__).resolve().parents[1]
ITEMS = ROOT / "worldseed" / "data" / "items.json"
SPRITES = ROOT / "worldseed" / "assets" / "sprites" / "items"


class ItemAssetCatalogTests(unittest.TestCase):
    def setUp(self):
        self.items = json.loads(ITEMS.read_text(encoding="utf-8"))

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

    def test_item_types_are_canonical_and_sort_deterministically(self):
        allowed = set(ITEM_TYPE_ORDER)
        for row in self.items:
            self.assertIn(row["category"], allowed, row["id"])
        first = [(x["category"], x["name"], x["id"]) for x in ordered_items(self.items)]
        second = [(x["category"], x["name"], x["id"]) for x in ordered_items(list(reversed(self.items)))]
        self.assertEqual(first, second)
        rank = {name: n for n, name in enumerate(ITEM_TYPE_ORDER)}
        self.assertEqual(first, sorted(first, key=lambda x: (rank[x[0]], x[1].casefold(), x[2])))

    def test_names_are_clean_and_unique(self):
        names = [row["name"] for row in self.items]
        self.assertEqual(len(names), len(set(names)))
        self.assertNotIn("Flax Seed Seed", names)
        for name in names:
            self.assertEqual(name, name.strip())
            self.assertNotRegex(name, r"\s{2,}")


if __name__ == "__main__":
    unittest.main()
