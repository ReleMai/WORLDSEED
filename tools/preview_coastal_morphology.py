"""Render real coast-v1/v2 terrain side by side, without opening player saves."""
import argparse,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from worldseed.config import DATA_DIR
from worldseed.core.coords import WorldPos
from worldseed.content.registry import ContentRegistry
from worldseed.world.generator import WorldGenerator
from worldseed.world.hydrology import HydrologyGenerator


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--capture',type=Path,default=Path('artifacts/coastal-morphology.png'))
    args=parser.parse_args();os.environ['SDL_VIDEODRIVER']='dummy';os.environ['SDL_AUDIODRIVER']='dummy'
    import pygame as pg
    pg.init();pg.display.set_mode((1,1));font=pg.font.Font(None,24)
    gen=WorldGenerator(b'v8-phase5-mouth-0',ContentRegistry.load(DATA_DIR),version=8)
    hydro=HydrologyGenerator(gen,version=2,morphology_version=2);gen.attach_hydrology(hydro)
    hydro.prepare_world_bounds(-3072,-3072,-1025,-2049,persist=False)
    palette={'core:ocean_deep':(21,49,78),'core:ocean_shelf':(28,69,99),'core:ocean_shallow':(41,97,121),
             'core:ocean_wade':(70,132,139),'core:estuary_shallow':(95,154,158),'core:estuary_deep':(41,109,143),
             'core:river':(35,98,169),'core:river_shallow':(69,136,180),'core:stream':(72,148,194),
             'core:tidal_flat':(143,129,98),'core:salt_marsh':(89,110,76),'core:shore':(202,186,136),
             'core:coastal_gravel':(154,148,129),'core:rocky_shore':(109,117,115),'core:coastal_cliff':(82,87,88),
             'core:forest':(49,77,44),'core:grass':(96,128,68),'core:wetland':(80,118,93)}
    screen=pg.Surface((1180,660));screen.fill((20,25,28));left,top=-2240,-3016
    for panel,version in enumerate((1,2)):
        gen.set_coast_morphology_version(version)
        screen.blit(font.render('Coast '+str(version)+' | same seed and drainage',True,(229,229,221)),(16+panel*590,14))
        for y in range(88):
            for x in range(96):
                tid=gen.terrain_at(WorldPos(left+x,top+y,0))
                pg.draw.rect(screen,palette.get(tid,(126,119,92)),(16+panel*590+x*6,46+y*6,6,6))
    for i,(label,color) in enumerate((('Sea',(41,97,121)),('Estuary',(95,154,158)),('River',(35,98,169)),('Tidal flat',(143,129,98)),('Sand',(202,186,136)))):
        x=20+i*226;pg.draw.rect(screen,color,(x,596,18,18));screen.blit(font.render(label,True,(229,229,221)),(x+25,595))
    screen.blit(font.render('Actual generated terrain IDs | seed v8-phase5-mouth-0 | around -2192, -2976',True,(180,188,185)),(20,630))
    args.capture.parent.mkdir(parents=True,exist_ok=True);pg.image.save(screen,str(args.capture));pg.quit()

if __name__=='__main__':main()
