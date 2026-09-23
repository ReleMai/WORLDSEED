from __future__ import annotations

import json
import unittest
from pathlib import Path

from PIL import Image

from tools.build_biome_atlas import BIOME_GROUPS, build_catalog, markdown_catalog

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "worldseed" / "data"
ASSETS = ROOT / "worldseed" / "assets"


class BiomeAtlasTests(unittest.TestCase):
    def test_every_terrain_is_mapped_exactly_once(self):
        terrain_ids = {row["id"] for row in json.loads((DATA / "terrain.json").read_text(encoding="utf-8"))}
        mapped = [tid for biome in BIOME_GROUPS for tid in biome["terrains"]]
        self.assertEqual(terrain_ids, set(mapped))
        self.assertEqual(len(mapped), len(set(mapped)), "terrain appears in multiple biome groups")

    def test_catalog_references_only_real_content(self):
        catalog = build_catalog()
        terrain_ids = {row["id"] for row in json.loads((DATA / "terrain.json").read_text(encoding="utf-8"))}
        resource_ids = {row["id"] for row in json.loads((DATA / "resources.json").read_text(encoding="utf-8"))}
        species_ids = {row["id"] for row in json.loads((DATA / "species.json").read_text(encoding="utf-8"))}
        crop_ids = {row["id"] for row in json.loads((DATA / "crops.json").read_text(encoding="utf-8"))}
        for biome in catalog["biomes"]:
            for row in biome["terrain"]:
                self.assertIn(row["id"], terrain_ids)
            for key in ("trees", "plants", "deposits", "containers"):
                for row in biome[key]:
                    self.assertIn(row["id"], resource_ids)
            for row in biome["animals"]:
                self.assertIn(row["id"], species_ids)
            for row in biome["crops"]:
                self.assertIn(row["id"], crop_ids)

    def test_natural_containers_come_from_resource_tags(self):
        resources = {
            row["id"]: row
            for row in json.loads((DATA / "resources.json").read_text(encoding="utf-8"))
        }
        catalog = build_catalog()
        for biome in catalog["biomes"]:
            for row in biome["containers"]:
                self.assertIn("natural_container", resources[row["id"]].get("tags", []))

    def test_aquatic_gaps_are_explicit_not_invented(self):
        catalog = build_catalog()
        watery = [x for x in catalog["biomes"] if x["kind"] in {"freshwater", "coast", "marine"}]
        self.assertTrue(watery)
        for biome in watery:
            if not biome["animals"]:
                self.assertTrue(any("No authored animal habitat" in note for note in biome["gaps"]))
            if not (biome["trees"] or biome["plants"] or biome["deposits"] or biome["containers"]):
                self.assertTrue(any("No authored ResourceSystem spawn" in note for note in biome["gaps"]))

    def test_committed_generated_catalog_and_markdown_are_current(self):
        catalog = build_catalog()
        committed = json.loads((ASSETS / "biome_catalog.json").read_text(encoding="utf-8"))
        self.assertEqual(catalog, committed)
        self.assertEqual(markdown_catalog(catalog), (ASSETS / "BIOME_ATLAS.md").read_text(encoding="utf-8"))

    def test_visual_atlas_exists_and_is_readable(self):
        path = ASSETS / "biome_atlas.png"
        self.assertTrue(path.is_file())
        with Image.open(path) as image:
            self.assertGreaterEqual(image.width, 1000)
            self.assertGreaterEqual(image.height, 3000)
            image.verify()


if __name__ == "__main__":
    unittest.main()
