import tempfile
import unittest
from pathlib import Path

from worldseed.config import (
    DATA_DIR, WORLDGEN_VERSION, RESOURCEGEN_VERSION,
    HYDROLOGY_VERSION, HYDROLOGY_MORPHOLOGY_VERSION,
)
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import ChunkKey, WorldPos
from worldseed.persistence.database import WorldDatabase
from worldseed.systems.resources import ResourceSystem
from worldseed.systems.state import LivingWorldState
from worldseed.world.generator import WorldGenerator
from worldseed.world.world import World


class RC13PregenerationTests(unittest.TestCase):
    def setUp(self):
        self.registry = ContentRegistry.load(DATA_DIR)
        self.seed = b'rc13-pregen-test'

    def test_prepared_terrain_persists_and_loads_without_generator(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'world.db'
            db = WorldDatabase.create(path, 'test', self.seed.hex())
            world = World(WorldGenerator(self.seed, self.registry), self.registry, db)
            stats = world.pre_generate(WorldPos(0, 0, 0), 1)
            self.assertEqual(stats['total'], 9)
            self.assertIsNotNone(db.load_generated_surface_chunk(
                ChunkKey(0, 0, 0), WORLDGEN_VERSION,
                HYDROLOGY_VERSION, HYDROLOGY_MORPHOLOGY_VERSION,
            ))
            expected = world.tile_at(WorldPos(4, 7, 0)).terrain_id
            db.close()

            db2 = WorldDatabase.open(path)
            gen2 = WorldGenerator(self.seed, self.registry, version=WORLDGEN_VERSION)
            def fail_generate(_key):
                raise AssertionError('prepared chunk should load from SQLite, not regenerate')
            gen2.generate_chunk = fail_generate
            world2 = World(gen2, self.registry, db2)
            self.assertEqual(world2.tile_at(WorldPos(4, 7, 0)).terrain_id, expected)
            db2.close()

    def test_prepared_resources_persist_and_skip_raw_generation(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'world.db'
            db = WorldDatabase.create(path, 'test', self.seed.hex())
            world = World(WorldGenerator(self.seed, self.registry), self.registry, db)
            world.resourcegen_version = RESOURCEGEN_VERSION
            world.pre_generate(WorldPos(0, 0, 0), 0)
            resources = ResourceSystem(LivingWorldState(), self.registry, self.seed, world)
            resources.pre_generate(WorldPos(0, 0, 0), 0)
            self.assertIsNotNone(db.load_generated_resource_chunk(ChunkKey(0, 0, 0), RESOURCEGEN_VERSION, 'spring'))
            db.close()

            db2 = WorldDatabase.open(path)
            world2 = World(WorldGenerator(self.seed, self.registry), self.registry, db2)
            world2.resourcegen_version = RESOURCEGEN_VERSION
            resources2 = ResourceSystem(LivingWorldState(), self.registry, self.seed, world2)
            def fail_raw(*_args, **_kwargs):
                raise AssertionError('prepared resource chunk should not run raw placement')
            resources2._raw_feature = fail_raw
            # Any surface lookup in the prepared chunk should use the stored map.
            resources2.feature_at(WorldPos(3, 3, 0))
            self.assertEqual(len(resources2._feature_chunk_cache), 1)
            db2.close()

    def test_loading_screen_contract_exists(self):
        src = Path('worldseed/ui/pygame_terminal.py').read_text(encoding='utf-8')
        self.assertIn('def present_loading', src)
        self.assertIn('GENERATING WORLD', src)
        app = Path('worldseed/app.py').read_text(encoding='utf-8')
        self.assertIn('world.pre_generate(pos,radius', app)
        self.assertIn('spawn_resources.pre_generate(pos,radius', app)


if __name__ == '__main__':
    unittest.main()
