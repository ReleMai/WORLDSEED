"""Technical extraction preserves generated artwork and stable item identity."""
from __future__ import annotations

import tempfile
import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

from tools.import_generated_item_icons import (
    ITEMS, PROVENANCE, ROOT, SPRITES, component_partition, extract_icon,
    gutter_edges, isolate_source, plan_sheet,
)


class GeneratedItemIconImportTests(unittest.TestCase):
    def test_published_generated_art_covers_catalog_and_retains_source_and_pixel_hashes(self):
        catalog = {row["id"]: row for row in json.loads(ITEMS.read_text(encoding="utf-8"))}
        provenance = json.loads(PROVENANCE.read_text(encoding="utf-8"))
        records = provenance["items"]
        self.assertEqual(len(records), len(catalog))
        self.assertEqual({row["item_id"] for row in records}, set(catalog))
        declared = [iid for sheet in provenance["sheets"] for iid in sheet["item_ids"]]
        self.assertEqual(len(declared), len(set(declared)))
        self.assertEqual(set(declared), set(catalog))
        for sheet in provenance["sheets"]:
            source = ROOT / sheet["source"]
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), sheet["source_sha256"], sheet["id"])
            if "ownership_map" in sheet:
                with Image.open(ROOT / sheet["ownership_map"]) as ownership:
                    self.assertEqual(hashlib.sha256(ownership.convert("L").tobytes()).hexdigest(),
                                     sheet["ownership_rgba_sha256"], sheet["id"])
        hashes = set()
        for record in records:
            item = catalog[record["item_id"]]
            self.assertEqual((record["asset"], record["sprite_tag"]), (item["asset"], item["sprite_tag"]))
            sprite = SPRITES / (item["asset"] + ".png")
            self.assertEqual(hashlib.sha256(sprite.read_bytes()).hexdigest(), record["png_sha256"], item["id"])
            with Image.open(sprite) as icon:
                self.assertEqual((icon.mode, icon.size), ("RGBA", (64, 64)), item["id"])
                digest = hashlib.sha256(icon.tobytes()).hexdigest()
            self.assertEqual(digest, record["rgba_sha256"], item["id"])
            self.assertNotIn(digest, hashes, item["id"])
            hashes.add(digest)

    def test_transparent_neon_rgb_cannot_bleed_into_visible_art(self):
        source = Image.new("RGBA", (120, 100), (255, 0, 255, 0))
        ImageDraw.Draw(source).rectangle((15, 20, 104, 79), fill=(87, 52, 29, 252))
        output, metadata = extract_icon(source, (0, 0, 120, 100))
        self.assertEqual(output.mode, "RGBA")
        self.assertEqual(output.size, (64, 64))
        self.assertEqual(metadata["trim_bounds_in_source"], [15, 20, 105, 80])
        self.assertEqual(metadata["resized_size"], [56, 37])
        self.assertEqual(metadata["canvas_offset"], [4, 13])
        for r, g, b, alpha in output.getdata():
            if alpha >= 16:
                self.assertLess(b, 40)
                self.assertGreater(r, g)
        self.assertEqual(output.getpixel((0, 0)), (0, 0, 0, 0))

    def test_solid_art_on_cell_boundary_requires_reviewed_bounds(self):
        source = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        ImageDraw.Draw(source).rectangle((0, 15, 35, 75), fill=(120, 90, 50, 255))
        with self.assertRaisesRegex(ValueError, "solid pixels touch a cell boundary"):
            extract_icon(source, (0, 0, 100, 100))

    def test_nearby_empty_gutter_keeps_misaligned_objects_separate(self):
        source = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        draw = ImageDraw.Draw(source)
        draw.rectangle((10, 5, 90, 39), fill=(100, 80, 50, 255))
        draw.rectangle((10, 46, 90, 95), fill=(40, 90, 120, 255))
        edges = gutter_edges(source, (0, 0, 100, 100), 2, "y")
        self.assertGreater(edges[1], 39)
        self.assertLess(edges[1], 46)
        top, _ = extract_icon(source, (0, 0, 100, edges[1]))
        bottom, _ = extract_icon(source, (0, edges[1], 100, 100))
        self.assertGreater(top.getpixel((32, 32))[0], top.getpixel((32, 32))[2])
        self.assertLess(bottom.getpixel((32, 32))[0], bottom.getpixel((32, 32))[2])

    def test_unused_visible_cell_rejects_source_count_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            source = Image.new("RGBA", (120, 60), (0, 0, 0, 0))
            draw = ImageDraw.Draw(source)
            draw.rectangle((8, 8, 48, 51), fill=(100, 80, 40, 255))
            draw.rectangle((69, 8, 110, 51), fill=(50, 100, 80, 255))
            source.save(path / "source.png")
            sheet = {"id": "sample", "source": "source.png", "columns": 2, "rows": 1,
                     "item_ids": ["core:first"]}
            catalog = {"core:first": {"id": "core:first", "asset": "first", "sprite_tag": "first"}}
            with self.assertRaisesRegex(ValueError, "source/item count mismatch"):
                plan_sheet(sheet, path / "manifest.json", catalog)

    def test_overlapping_rectangles_keep_neighbor_colors_out_of_each_icon(self):
        source = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
        draw = ImageDraw.Draw(source)
        draw.line([(180, 20), (20, 20), (20, 110)], fill=(180, 60, 20, 255), width=9)
        draw.line([(100, 90), (100, 180), (180, 180)], fill=(20, 80, 180, 255), width=9)
        ownership, groups = component_partition(source, (0, 0, 200, 200), 1, 2, 2)
        self.assertEqual(len(groups), 2)
        top_source, top_bounds = isolate_source(source, ownership, 1)
        bottom_source, bottom_bounds = isolate_source(source, ownership, 2)
        top, _ = extract_icon(top_source, top_bounds)
        bottom, _ = extract_icon(bottom_source, bottom_bounds)
        for r, _, b, alpha in top.getdata():
            if alpha >= 16:
                self.assertGreater(r, b)
        for r, _, b, alpha in bottom.getdata():
            if alpha >= 16:
                self.assertLess(r, b)

    def test_salvage_authoring_preserves_published_generated_pixels_by_default(self):
        import json
        from tools import draw_salvage_sprites as author

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data, out = root / "data", root / "items"
            data.mkdir(); out.mkdir()
            rows = [{"id": "core:protected", "name": "Protected", "asset": "protected"},
                    {"id": "core:ordinary", "name": "Ordinary", "asset": "ordinary"}]
            (data / "items.json").write_text(json.dumps(rows))
            (data / "crafting_expansion.json").write_text("{}")
            image = Image.new("RGBA", (64, 64), (87, 54, 20, 252))
            image.save(out / "protected.png")
            original = (out / "protected.png").read_bytes()
            replacement = Image.new("RGBA", (64, 64), (30, 80, 150, 255))
            specs = [(row, "wood", "planks") for row in rows]
            with (patch.object(author, "DATA", data), patch.object(author, "OUT", out),
                  patch.object(author, "expansion_specs", return_value=specs),
                  patch.object(author, "contact_sheet"),
                  patch.object(author, "render", return_value=replacement) as render,
                  patch("tools.import_generated_item_icons.generated_item_ids", return_value={"core:protected"}),
                  patch("sys.argv", ["draw_salvage_sprites.py"])):
                self.assertEqual(author.main(), 0)
            self.assertEqual((out / "protected.png").read_bytes(), original)
            self.assertEqual(render.call_count, 1)
            self.assertEqual(render.call_args.args[0]["id"], "core:ordinary")

    def test_legacy_sprite_pack_preserves_published_generated_pixels_by_default(self):
        import json
        from tools import generate_sprite_pack as author

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data, out = root / "data", root / "worldseed/assets/sprites"
            data.mkdir(); (out / "items").mkdir(parents=True)
            rows = [{"id": "core:protected", "name": "Protected", "asset": "protected"},
                    {"id": "core:ordinary", "name": "Ordinary", "asset": "ordinary"}]
            (data / "items.json").write_text(json.dumps(rows))
            for name in ("terrain", "resources", "structures", "species", "crops"):
                (data / (name + ".json")).write_text("[]")
            original_image = Image.new("RGBA", (64, 64), (87, 54, 20, 252))
            original_image.save(out / "items/protected.png")
            original = (out / "items/protected.png").read_bytes()
            with (patch.object(author, "ROOT", root), patch.object(author, "DATA", data),
                  patch.object(author, "OUT", out), patch.object(author, "MANIFEST", root / "worldseed/assets/visuals.json"),
                  patch.object(author, "make_preview"),
                  patch.object(author, "item_sprite", return_value=Image.new("RGBA", (32, 32))) as render,
                  patch("tools.import_generated_item_icons.generated_item_ids", return_value={"core:protected"}),
                  patch("sys.argv", ["generate_sprite_pack.py"])):
                author.main()
            self.assertEqual((out / "items/protected.png").read_bytes(), original)
            self.assertEqual(render.call_count, 1)
            self.assertEqual(render.call_args.args[0]["id"], "core:ordinary")


if __name__ == "__main__":
    unittest.main()
