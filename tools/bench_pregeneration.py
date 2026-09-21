from __future__ import annotations
import tempfile, time
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from worldseed.config import DATA_DIR, RESOURCEGEN_VERSION
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.persistence.database import WorldDatabase
from worldseed.systems.resources import ResourceSystem
from worldseed.systems.state import LivingWorldState
from worldseed.world.generator import WorldGenerator
from worldseed.world.world import World


def main():
    registry=ContentRegistry.load(DATA_DIR);seed=b'worldseed-pregen-benchmark';pos=WorldPos(32*20+5,32*20+5,0)
    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/'bench.db';db=WorldDatabase.create(path,'bench',seed.hex())
        world=World(WorldGenerator(seed,registry),registry,db);world.resourcegen_version=RESOURCEGEN_VERSION
        resources=ResourceSystem(LivingWorldState(),registry,seed,world)
        t=time.perf_counter();world.tile_at(pos);fresh_terrain=(time.perf_counter()-t)*1000
        # Measure a complete resource chunk after preparing only terrain, which
        # approximates entering a never-seen viewport before RC13 preparation.
        chunk_origin=WorldPos((pos.x//32)*32,(pos.y//32)*32,0);world.pre_generate(chunk_origin,0)
        resources=ResourceSystem(LivingWorldState(),registry,seed,world)
        t=time.perf_counter()
        for y in range(chunk_origin.y,chunk_origin.y+32):
            for x in range(chunk_origin.x,chunk_origin.x+32):resources.feature_at(WorldPos(x,y,0))
        fresh_resources=(time.perf_counter()-t)*1000
        resources.pre_generate(chunk_origin,0);db.close()

        db2=WorldDatabase.open(path);world2=World(WorldGenerator(seed,registry),registry,db2);world2.resourcegen_version=RESOURCEGEN_VERSION
        resources2=ResourceSystem(LivingWorldState(),registry,seed,world2)
        t=time.perf_counter();world2.tile_at(pos);prepared_terrain=(time.perf_counter()-t)*1000
        t=time.perf_counter()
        for y in range(chunk_origin.y,chunk_origin.y+32):
            for x in range(chunk_origin.x,chunk_origin.x+32):resources2.feature_at(WorldPos(x,y,0))
        prepared_resources=(time.perf_counter()-t)*1000
        print({
            'fresh_first_terrain_tile_ms':round(fresh_terrain,3),
            'prepared_first_terrain_tile_ms':round(prepared_terrain,3),
            'fresh_resource_chunk_1024_cells_ms':round(fresh_resources,3),
            'prepared_resource_chunk_1024_cells_ms':round(prepared_resources,3),
        })
        db2.close()

if __name__=='__main__':main()
