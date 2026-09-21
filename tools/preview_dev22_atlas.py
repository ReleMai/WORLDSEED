"""Reproducible atlas visual QA. Terrain is generated; named POIs are fixtures."""
import os
os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')
import sys
from pathlib import Path
from types import SimpleNamespace
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'tests')]
from test_dev22_atlas import fixture
from worldseed.core.coords import WorldPos
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.ui.atlas_map import begin_atlas
from worldseed.systems.state import StructureInstance


def main():
    td, db, world, sim = fixture(7,b'atlas-coast-preview',True)
    term = PygameTerminal(); term.enter()
    try:
        world.pre_generate(WorldPos(0,0,0),4)
        # Choose land for the clearly labeled QA settlements/camp, rather than
        # implying that the world generator creates towns in open water.
        land = [(x,y) for y in range(-112,113,16) for x in range(-112,113,16)
                if world.tile_at(WorldPos(x,y,0)).terrain_id in ('core:forest','core:grass','core:sand','core:rock')]
        village, city, camp = land[0], land[len(land)//2], land[-1]
        sim.known_settlements = lambda: [
            SimpleNamespace(uid='village',name='Village (QA fixture)',x=village[0],y=village[1],population=150),
            SimpleNamespace(uid='city',name='City (QA fixture)',x=city[0],y=city[1],population=1500)]
        sim.state.structures['camp'] = StructureInstance('core:campfire',*camp,0)
        begin_atlas(term,sim)
        term._atlas_controls.span = 256
        for size, name in (((1280,800),'dev22_atlas.png'),((800,520),'dev22_atlas_small.png')):
            term._resize(*size);term.present_region_map(sim)
            term.pg.image.save(term.screen,str(ROOT/'artifacts'/name))
        print('QA previews saved; POIs are labeled fixtures, terrain is actual v7 generation.')
    finally:
        term.restore();db.close();td.cleanup()


if __name__ == '__main__':
    main()
