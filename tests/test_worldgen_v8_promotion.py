from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from worldseed.config import DATA_DIR, WORLDGEN_VERSION
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.persistence.database import WorldDatabase
from worldseed.world.generator import WorldGenerator


class WorldgenV8PromotionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)
        cls.seed = b"worldgen-v8-promotion"

    def test_new_database_records_v8(self):
        self.assertEqual(WORLDGEN_VERSION, 8)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "new-v8.db"
            db = WorldDatabase.create(path, "new-v8", self.seed.hex())
            try:
                self.assertEqual(int(db.get_meta("worldgen_version")), 8)
            finally:
                db.close()

    def test_legacy_v7_save_remains_pinned_after_open(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "legacy-v7.db"
            db = WorldDatabase.create(path, "legacy-v7", self.seed.hex())
            db.set_meta("worldgen_version", 7)
            db.connection.commit()
            db.close()

            reopened = WorldDatabase.open(path)
            try:
                self.assertEqual(int(reopened.get_meta("worldgen_version")), 7)
                gen = WorldGenerator(
                    self.seed,
                    self.registry,
                    version=int(reopened.get_meta("worldgen_version")),
                )
                self.assertEqual(gen.version, 7)
                self.assertIsNone(gen.landform_at(WorldPos(0, 0, 0)))
            finally:
                reopened.close()

    def test_default_generator_is_v8_but_explicit_v7_stays_legacy(self):
        current = WorldGenerator(self.seed, self.registry)
        legacy = WorldGenerator(self.seed, self.registry, version=7)
        self.assertEqual(current.version, 8)
        self.assertEqual(legacy.version, 7)
        self.assertIsNotNone(current.caves)
        self.assertIsNotNone(legacy.caves)
        self.assertNotEqual(type(current.caves), type(legacy.caves))


if __name__ == "__main__":
    unittest.main()
