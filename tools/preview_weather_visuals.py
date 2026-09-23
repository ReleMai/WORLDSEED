"""Inspect shipped visual assets/effects without opening or changing a save."""
from pathlib import Path
import argparse
import os
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--capture', type=Path)
    parser.add_argument('--cave', action='store_true')
    parser.add_argument('--storm', action='store_true')
    parser.add_argument('--gallery', action='store_true')
    args = parser.parse_args()
    if args.capture:
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
    from worldseed.ui.pygame_terminal import PygameTerminal
    from worldseed.systems.resources import FeatureView
    from worldseed.world.lighting import LightingSystem
    from worldseed.core.rng import hash_u64
    term = PygameTerminal(1200, 760)
    term.enter()
    pg, vis, screen = term.pg, term._visuals, term.screen
    pg.display.set_caption('WORLDSEED — visual test scene (no save)')
    rect = pg.Rect(0, 75, 1200, 645)
    size = 40
    minute, cave, cover, storm = 720, args.cave, 90, 85 if args.storm else 0
    rain = 8 if storm else 0
    gallery = args.gallery
    clock = pg.time.Clock()
    running = True
    try:
        while running:
            for event in pg.event.get():
                if event.type == pg.QUIT:
                    running = False
                elif event.type == pg.KEYDOWN:
                    if event.key == pg.K_ESCAPE:
                        running = False
                    if event.key in (pg.K_1, pg.K_2, pg.K_3, pg.K_4):
                        minute = {pg.K_1:720,pg.K_2:1110,pg.K_3:0,pg.K_4:330}[event.key]
                    if event.key == pg.K_g:
                        gallery = not gallery
                    if event.key == pg.K_v:
                        cave = not cave
                    if event.key == pg.K_c:
                        cover, storm, rain = 80, 0, 0
                    if event.key == pg.K_r:
                        cover, storm, rain = 85, 20, 6
                    if event.key == pg.K_s:
                        cover, storm, rain = 100, 85, 10
            now = 15000 if args.capture else pg.time.get_ticks()
            screen.fill((19,25,29))
            for y in range(17):
                for x in range(30):
                    token = hash_u64(b'visual-scene', x, y)
                    tid = ('core:cave_wall' if (x//4+y//3)%4==0 else 'core:cave_floor') if cave else 'core:forest'
                    ref = vis.ref('terrain', tid)
                    path = vis.resolve(ref, token % len(ref.paths))
                    tile = term._terrain_surface(tid,path,{}, {},size,world_x=x,world_y=y)
                    screen.blit(tile,(x*size,rect.y+y*size))
            saved = screen.get_clip()
            screen.set_clip(rect)
            if not cave:
                for y in (5,9,13):
                    for x in (4,9,15,21,26):
                        tid = 'core:pine_tree' if x%3 else 'core:morel_patch'
                        term._draw_resource_feature(FeatureView(tid),vis.resolve(vis.ref('resources',tid)),
                                                    pg.Rect(x*size,rect.y+y*size,size,size))
                light = LightingSystem().at(minute,cover,storm)
                term._weather_fx.set_lighting(light,now)
                term._weather_fx.draw_lighting(screen,rect,light,elapsed_ms=now)
                weather = dict(cloud_cover=cover,wind_dx=750,wind_dy=160,storm_intensity=storm,rain=rain)
                term._weather_fx.draw_atmosphere(screen,rect,b'visual-scene',weather,
                                                 world_left=0,world_top=0,tile_px=size,
                                                 elapsed_ms=now,game_minute=minute,lighting=light)
            screen.set_clip(saved)
            if gallery:
                pg.draw.rect(screen,(32,47,60),rect)
                for i in range(12):
                    identity=hash_u64(b'visual-scene','gallery',i)
                    shape,_=term._weather_fx._clouds._shape(identity,'wisp' if i%4==0 else 'bank')
                    x=(i%4)*300+54; y=rect.y+(i//4)*210
                    screen.blit(shape,(x,y))
                    screen.blit(term.small_font.render('Cloud '+str(i+1),True,(224,219,197)),(x+55,y+182))
            title = 'UNIQUE CLOUD SHAPES' if gallery else ('CAVE MATERIALS' if cave else 'DYNAMIC CLOUDS / PINE / MOREL')
            for text, y in [('WORLDSEED — '+title+' — synthetic visual test, no save',10),
                            ('1 Day   2 Dusk   3 Night   4 Dawn   C Clouds   R Rain   S Storm   V Cave   G Shapes   Esc Exit',42)]:
                screen.blit(term.small_font.render(text,True,(224,219,197)),(18,y))
            pg.display.flip()
            if args.capture:
                args.capture.parent.mkdir(parents=True,exist_ok=True)
                pg.image.save(screen,str(args.capture))
                break
            clock.tick(30)
    finally:
        term.restore()


if __name__ == '__main__':
    main()
