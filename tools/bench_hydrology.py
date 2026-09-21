from __future__ import annotations

from pathlib import Path
import sys
import tempfile
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worldseed.config import DATA_DIR, WORLDGEN_VERSION
from worldseed.content.registry import ContentRegistry
from worldseed.persistence.database import WorldDatabase
from worldseed.world.generator import WorldGenerator
from worldseed.world.hydrology import HydrologyGenerator

registry = ContentRegistry.load(DATA_DIR)
seed = b'rc14-hydrology-benchmark'

gen = WorldGenerator(seed, registry, version=WORLDGEN_VERSION)
planner = HydrologyGenerator(gen)
t0 = perf_counter(); domain = planner.generate(0, 0); generated = perf_counter() - t0

with tempfile.TemporaryDirectory() as td:
    path = Path(td) / 'bench.db'
    db = WorldDatabase.create(path, 'hydrology-bench', seed.hex())
    cached = HydrologyGenerator(WorldGenerator(seed, registry, version=WORLDGEN_VERSION), db)
    t0 = perf_counter(); cached.load_or_generate(0, 0, persist=True); persisted = perf_counter() - t0
    t0 = perf_counter(); cached.load_or_generate(0, 0); loaded = perf_counter() - t0
    db_size = path.stat().st_size
    db.close()

print({
    'nodes': domain.width * domain.height,
    'generate_ms': round(generated * 1000, 3),
    'generate_persist_ms': round(persisted * 1000, 3),
    'cached_load_ms': round(loaded * 1000, 3),
    'single_domain_db_bytes': db_size,
    'fingerprint': domain.fingerprint,
})
