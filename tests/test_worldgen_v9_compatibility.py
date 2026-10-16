from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from worldseed.config import DATA_DIR, WORLDGEN_VERSION
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.persistence.database import WorldDatabase
from worldseed.world.generator import WorldGenerator
from worldseed.world.world import World


class WorldgenV9CompatibilityTests(unittest.TestCase):
    # Captured from canonical main before introducing v9. Samples include both
    # sides of the origin, chunk edges and +/-2048, without attached hydrology.
    V8_COORDINATES = (-2049, -2048, -1024, -1, 0, 1, 1024, 2048, 2049)
    V8_SURFACE_FIELDS_SHA256 = (
        "e1be6a814ddc2035360a84d3aa95dc3f7c7fd1a37a507b752838abe0cb8ab4fc"
    )

    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)
        cls.seed = b"v9-legacy-fingerprint"

    def _surface_fields_fingerprint(self, generator):
        self.assertIsNone(generator.hydrology)
        rows = []
        for y in self.V8_COORDINATES:
            for x in self.V8_COORDINATES:
                pos = WorldPos(x, y, 0)
                fields = generator.sample_fields(pos)
                rows.append([
                    x, y, fields.elevation, fields.moisture,
                    fields.temperature, fields.fertility,
                    generator.terrain_at(pos),
                ])
        payload = json.dumps(rows, separators=(",", ":")).encode()
        return hashlib.sha256(payload).hexdigest()

    def test_explicit_v8_surface_and_fields_are_frozen(self):
        generator = WorldGenerator(self.seed, self.registry, version=8)
        self.assertEqual(
            self._surface_fields_fingerprint(generator),
            self.V8_SURFACE_FIELDS_SHA256,
        )

    def test_reopened_v8_database_keeps_recorded_generation_contracts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy-v8.db"
            database = WorldDatabase.create(path, "legacy-v8", self.seed.hex())
            database.set_meta("worldgen_version", 8)
            contracts = {
                key: database.get_meta(key)
                for key in (
                    "worldgen_version", "hydrology_version",
                    "hydrology_morphology_version", "coast_morphology_version",
                    "resourcegen_version", "settlement_plan_version", "routegen_version",
                )
            }
            database.connection.commit()
            database.close()

            reopened = WorldDatabase.open(path)
            try:
                for key, expected in contracts.items():
                    self.assertEqual(reopened.get_meta(key), expected, key)
                generator = WorldGenerator(
                    self.seed, self.registry,
                    version=int(reopened.get_meta("worldgen_version")),
                )
                world = World(generator, self.registry, reopened, auto_hydrology=False)
                self.assertEqual(world.generator.version, 8)
                self.assertEqual(
                    self._surface_fields_fingerprint(world.generator),
                    self.V8_SURFACE_FIELDS_SHA256,
                )
            finally:
                reopened.close()

    def test_v7_pre_v8_geography_fields_remain_frozen(self):
        expected = {
            (-4097, -2049): (32639, 28033, 20425, 36803),
            (-1, -1): (47792, 19303, 24469, 33183),
            (0, 0): (47799, 19235, 24445, 33133),
            (913, -1441): (46888, 39719, 45726, 46155),
            (4096, 2048): (38268, 27122, 37929, 41715),
        }
        generator = WorldGenerator(b"v8-authority-fixture", self.registry, version=7)
        for (x, y), row in expected.items():
            fields = generator.sample_fields(WorldPos(x, y, 0))
            self.assertEqual(
                (fields.elevation, fields.moisture, fields.temperature, fields.fertility),
                row, (x, y),
            )

    def test_new_save_records_v9_without_upgrading_legacy_metadata(self):
        self.assertEqual(WORLDGEN_VERSION, 9)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "new-v9.db"
            database = WorldDatabase.create(path, "new-v9", self.seed.hex())
            database.close()
            reopened = WorldDatabase.open(path)
            try:
                self.assertEqual(reopened.get_meta("worldgen_version"), 9)
                generator = WorldGenerator(
                    self.seed, self.registry,
                    version=int(reopened.get_meta("worldgen_version")),
                )
                self.assertEqual(generator.version, 9)
            finally:
                reopened.close()


if __name__ == "__main__":
    unittest.main()
