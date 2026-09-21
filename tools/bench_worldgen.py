from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from time import perf_counter
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import ChunkKey
from worldseed.world.generator import WorldGenerator

registry = ContentRegistry.load(DATA_DIR)
gen = WorldGenerator(b"benchmark-seed", registry)
start = perf_counter()
count = 100
for i in range(count):
    gen.generate_chunk(ChunkKey(i - 50, (i * 37) % 41 - 20))
elapsed = perf_counter() - start
print(f"Generated {count} chunks in {elapsed:.3f}s ({elapsed / count * 1000:.2f} ms/chunk)")
