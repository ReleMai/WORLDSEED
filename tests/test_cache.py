import unittest
from array import array
from worldseed.config import CHUNK_SIZE
from worldseed.core.coords import ChunkKey
from worldseed.world.cache import ChunkCache
from worldseed.world.chunk import Chunk


class CacheTests(unittest.TestCase):
    def test_cache_bound(self):
        def loader(key):
            return Chunk(key, array("H", [0]) * (CHUNK_SIZE * CHUNK_SIZE))
        cache = ChunkCache(8, loader)
        for i in range(100):
            cache.get(ChunkKey(i, 0))
        self.assertLessEqual(len(cache), 8)
