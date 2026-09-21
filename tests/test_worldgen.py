import unittest
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import ChunkKey
from worldseed.world.generator import WorldGenerator


class WorldGenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    def test_chunk_is_deterministic(self):
        gen_a = WorldGenerator(b"test-seed", self.registry)
        gen_b = WorldGenerator(b"test-seed", self.registry)
        a = gen_a.generate_chunk(ChunkKey(-7, 19))
        b = gen_b.generate_chunk(ChunkKey(-7, 19))
        self.assertEqual(a.terrain.tolist(), b.terrain.tolist())

    def test_generation_order_independent(self):
        gen = WorldGenerator(b"order-seed", self.registry)
        expected = gen.generate_chunk(ChunkKey(3, 4)).terrain.tolist()
        gen.generate_chunk(ChunkKey(500, -900))
        gen.generate_chunk(ChunkKey(-1, 0))
        self.assertEqual(expected, gen.generate_chunk(ChunkKey(3, 4)).terrain.tolist())
