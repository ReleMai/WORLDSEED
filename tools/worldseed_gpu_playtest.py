"""WORLDSEED Windows GPU-first walkable *visual* test arena (NOT gameplay yet).

This opens one native OpenGL 3.3 window and reads the production prepared
forest/camp reference fixture, original terrain, oak/pine layers and visibility.
WASD moves the visual camera/player marker ONLY; no gameplay input/saves,
AI simulation, resource harvest or worldgen changes are implied. It never
launches or reads player saves and does not render a software Surface frame.

Windows: python -m pip install -e '.[gpu]'
         python -m tools.worldseed_gpu_playtest --scene forest
Controls: WASD move; 1-4 seasons; F weather; T torch; [/] time of day;
          +/- zoom; P screenshot; Esc exits. The window title displays state.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from math import ceil,floor,sqrt
import json
import os
from pathlib import Path
import statistics
import tempfile
import time

from worldseed.presentation.gl_atmosphere import AtmosphereFrame,GLAtmospherePass,WorldLight
from worldseed.presentation.gl_worldspace import GLWorldspaceRenderer,GPUBackendUnavailable
from worldseed.presentation.gl_context import create_sdl_context
from worldseed.presentation.gpu_scene_bridge import GpuMaterialSource,prepare_gpu_frame,cell_bounds
from worldseed.presentation.worldspace import WorldCamera,WorldFoot

WEATHER=(
    ('Clear',dict(rain=0.,fog=0.,cloud=0.,wind_x=.2,wind_y=0.)),
    ('Clouds',dict(rain=0.,fog=.07,cloud=.84,wind_x=.45,wind_y=.1)),
    ('Rain',dict(rain=.65,fog=.18,cloud=.86,wind_x=.48,wind_y=.15)),
    ('Storm',dict(rain=1.,fog=.39,cloud=1.,wind_x=1.35,wind_y=.32)),
    ('Snow',dict(snow=.75,fog=.20,cloud=.91,wind_x=.46,wind_y=.18)),
    ('Fog',dict(fog=.87,cloud=.65,wind_x=.13,wind_y=.07)),
)
SEASONS=('spring','summer','autumn','winter')


def bounded_camera(x,y,width,height,zoom,bounds):
    """Never inspect/generate a tile outside the prepared fixture envelope."""
    if type(zoom) is not int or not 20<=zoom<=56:
        raise ValueError('unsupported test zoom')
    # Tree-rich reference scenes may hold ~three upright parts per seven cells.
    # Refuse viewport combinations that would overflow GPU frame command limits.
    if (ceil(width/zoom)+2)*(ceil(height/zoom)+2)>2800:
        raise ValueError('zoom too wide for bounded GPU tree-rich scene')
    lo_x,lo_y,hi_x,hi_y=bounds
    radius_x=ceil(width/(zoom*2))+2;radius_y=ceil(height/(zoom*2))+2
    if lo_x+radius_x >= hi_x-radius_x or lo_y+radius_y >= hi_y-radius_y:
        raise ValueError('resize/zoom needs a larger pre-prepared reference fixture')
    return WorldCamera(WorldFoot(max(lo_x+radius_x,min(hi_x-radius_x,x)),
                                 max(lo_y+radius_y,min(hi_y-radius_y,y)),0),
                       width,height,zoom)


def visible_prepared_window(fixture,camera):
    """Exactly one bounded prepared viewport, no worldgen and no global index walk."""
    from worldseed.core.coords import WorldPos
    from worldseed.systems.state import pos_key
    x0,y0,x1,y1=cell_bounds(camera)
    terrain={};resources={};seen=set()
    for y in range(y0,y1):
        for x in range(x0,x1):
            cell=(x,y,0)
            if pos_key(x,y,0) not in fixture.sim.visible_tiles_set:
                continue
            seen.add(cell)
            pos=WorldPos(x,y,0)
            terrain[cell]=fixture.world.tile_at(pos).terrain_id
            fv=fixture.sim.resources.feature_at(pos)
            if fv is not None and fv.stage!='depleted' and fv.feature_id in ('core:oak_tree','core:pine_tree'):
                resources[cell]=(fv,None)
    return terrain,resources,frozenset(seen)


def fire_lights(sim,camera,seen, *,torch=False):
    """Approved fixture fires only; temporary torch is labeled debugging art."""
    result=[]
    player_x,player_y=camera.to_screen(camera.center)
    if torch:
        result.append(WorldLight(player_x,player_y,6.5*camera.scale,1.18))
    for fire in getattr(sim.state,'fires',{}).values():
        if len(result)>=8:break
        if (fire.x,fire.y,fire.z) not in seen or fire.fuel<=0 or fire.intensity<=0:
            continue
        x,y=camera.to_screen(WorldFoot(fire.x+.5,fire.y+.6,fire.z))
        result.append(WorldLight(x,y,5.3*camera.scale,min(1.5,fire.intensity/85.),(1.,.52,.24)))
    return tuple(result)


def _screenshot(pg,ctx,width,height,path):
    source=ctx.screen.read(components=3,alignment=1)
    raw=pg.image.fromstring(source,(width,height),'RGB')
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    pg.image.save(pg.transform.flip(raw,False,True),str(path))


def run(*,scene='forest',width=1280,height=720,zoom=28,frames=0,
        screenshot=None,report=None,context_report=None):
    if os.environ.get('SDL_VIDEODRIVER')=='dummy':
        raise GPUBackendUnavailable('SDL dummy is not native GPU evidence')
    if scene not in ('forest','camp'):
        raise ValueError('choose prepared forest or camp')
    if type(frames) is not int or not 0<=frames<=36000 or not 640<=width<=1920 or not 480<=height<=1080:
        raise ValueError('playtest dimensions or duration outside bounded native test scope')
    # Imports are deferred: pure GPU contracts work even without pygame/glcontext.
    import pygame as pg
    from tools.reference_scene_fixtures import build_fixture
    from worldseed.config import DATA_DIR
    from worldseed.content.registry import ContentRegistry
    registry=ContentRegistry.load(DATA_DIR)
    with tempfile.TemporaryDirectory(prefix='worldseed-gpu-visual-') as directory:
        fixture=build_fixture(scene,registry,Path(directory),width=width,height=height,zoom=zoom)
        before=fixture.authority_fingerprint()
        renderer=post=None
        pg.init()
        try:
            pg.display.gl_set_attribute(pg.GL_CONTEXT_MAJOR_VERSION,3)
            pg.display.gl_set_attribute(pg.GL_CONTEXT_MINOR_VERSION,3)
            pg.display.gl_set_attribute(pg.GL_CONTEXT_PROFILE_MASK,pg.GL_CONTEXT_PROFILE_CORE)
            pg.display.gl_set_attribute(pg.GL_DOUBLEBUFFER,1)
            pg.display.set_mode((width,height),pg.DOUBLEBUF|pg.OPENGL|pg.RESIZABLE)
            diagnostics=context_report or (Path(report).with_suffix('.context.json') if report else None)
            ctx=create_sdl_context(pg,diagnostics=diagnostics)
            renderer=GLWorldspaceRenderer(ctx,width,height)
            post=GLAtmospherePass(ctx,width,height)
            assets=GpuMaterialSource(pg)
            x=y=256.5
            zoom=max(zoom,ceil(sqrt(width*height/2200)))
            season_index=1;weather_index=0;minute=720;torch=True
            clock=pg.time.Clock();start=time.perf_counter();last_tick=start
            samples=[];last_report=None;count=0;running=True
            cache_key=None;cached_terrain=cached_resources=cached_seen=None
            gpu_info={k:ctx.info.get(k,'unknown') for k in ('GL_VENDOR','GL_RENDERER','GL_VERSION')}
            while running and (frames==0 or count<frames):
                now=time.perf_counter();dt=min(.09,max(0.,now-last_tick));last_tick=now
                for ev in pg.event.get():
                    if ev.type==pg.QUIT:running=False
                    elif ev.type==pg.VIDEORESIZE:
                        # Resize same context and both GPU surfaces. No new SDL window.
                        if 640<=ev.w<=1920 and 480<=ev.h<=1080:
                            width,height=ev.w,ev.h
                            renderer.resize(width,height);post.resize(width,height)
                            zoom=max(zoom,ceil(sqrt(width*height/2200)))
                            cache_key=None
                    elif ev.type==pg.KEYDOWN:
                        if ev.key==pg.K_ESCAPE:running=False
                        elif ev.key in (pg.K_1,pg.K_2,pg.K_3,pg.K_4):season_index=ev.key-pg.K_1
                        elif ev.key==pg.K_f:weather_index=(weather_index+1)%len(WEATHER)
                        elif ev.key==pg.K_t:torch=not torch
                        elif ev.key==pg.K_LEFTBRACKET:minute=(minute-90)%1440
                        elif ev.key==pg.K_RIGHTBRACKET:minute=(minute+90)%1440
                        elif ev.key in (pg.K_EQUALS,pg.K_KP_PLUS):zoom=min(48,zoom+4);cache_key=None
                        elif ev.key in (pg.K_MINUS,pg.K_KP_MINUS):zoom=max(20,ceil(sqrt(width*height/2200)),zoom-4);cache_key=None
                        elif ev.key==pg.K_p:
                            target=Path(screenshot) if screenshot else Path('scratch/gpu-playtest.png')
                            # Main-loop captures after the next finished frame.
                            screenshot=target
                if not running:break
                keys=pg.key.get_pressed();speed=4.2*dt
                x+=(int(bool(keys[pg.K_d]))-int(bool(keys[pg.K_a])))*speed
                y+=(int(bool(keys[pg.K_s]))-int(bool(keys[pg.K_w])))*speed
                camera=bounded_camera(x,y,width,height,zoom,fixture.bounds)
                x,y=camera.center.x,camera.center.y
                new_key=(*cell_bounds(camera),season_index)
                if cache_key!=new_key:
                    cached_terrain,cached_resources,cached_seen=visible_prepared_window(fixture,camera)
                    cache_key=new_key
                scene_frame=prepare_gpu_frame(camera=camera,terrain_by=cached_terrain,
                    resource_by=cached_resources,resource_defs=registry.resources,
                    resource_style=lambda fid: {'width':1.35,'height':1.9},
                    visible_cells=cached_seen,discovered_cells=cached_seen,
                    viewer=WorldFoot(x,y,0),materials=assets,season=SEASONS[season_index],
                    fire_cells=tuple((f.x,f.y,f.z) for f in fixture.sim.state.fires.values()
                                     if f.fuel>0 and f.intensity>0))
                cam_corner=camera.to_world(0,0,ground_z=0)
                lights=fire_lights(fixture.sim,camera,cached_seen,torch=torch)
                name,weather=WEATHER[weather_index]
                fx=AtmosphereFrame(minute=minute,elapsed_seconds=now-start,
                    camera_pixel_x=cam_corner.x*zoom,camera_pixel_y=cam_corner.y*zoom,
                    lights=lights,**weather)
                began=time.perf_counter()
                last_report=renderer.draw(scene_frame.commands,target=post.scene_target,
                                          frame_time_seconds=fx.elapsed_seconds)
                post.present(fx)
                if screenshot and (count==frames-1 or frames==0):
                    _screenshot(pg,ctx,width,height,screenshot)
                    screenshot=None
                pg.display.flip()
                samples.append((time.perf_counter()-began)*1000)
                count+=1
                pg.display.set_caption(f'WORLDSEED G8 GPU visual arena | {scene} | '
                    f'{SEASONS[season_index]} | {name} | {minute//60:02d}:{minute%60:02d} | '
                    f'{round(x,1)},{round(y,1)} | {round(1000/(max(.1,samples[-1])))} CPU render/present Hz | F weather, 1-4 seasons, WASD, [ ] sun, T torch, P capture')
                clock.tick(60)
            after=fixture.authority_fingerprint()
            if before!=after:
                raise AssertionError('GPU visual arena mutated production fixture authority')
            samples.sort()
            result={'status':'visual-sample-not-gameplay-certification',
                'gpu':gpu_info,'scene':scene,'size':[width,height],'frames':count,
                'sdl_video_driver':pg.display.get_driver(),'native_hardware_accepted':False,
                'p50_render_ms':statistics.median(samples) if samples else None,
                'p95_render_ms':samples[min(len(samples)-1,int(len(samples)*.95))] if samples else None,
                'last_frame':asdict(last_report) if last_report else {},
                'scene_authority_unchanged':before==after,
                'controls':'visual camera only: WASD/F/T/1-4/[ ]/+ -/P/Esc',
                'limitations':'GPU visual arena only; CPU draw/present wall time, no explicit GPU completion sync; '
                    'driver may be software; production gameplay input/UI/weather/saving NOT cut over'}
            if report:
                path=Path(report);path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
            return result
        finally:
            if post is not None:post.close()
            if renderer is not None:renderer.close()
            pg.quit()
            fixture.close()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scene',choices=('forest','camp'),default='forest')
    parser.add_argument('--size',default='1280x720')
    parser.add_argument('--zoom',type=int,default=28)
    parser.add_argument('--frames',type=int,default=0,help='0 is until Esc; 180 for automated capture')
    parser.add_argument('--screenshot',type=Path)
    parser.add_argument('--report',type=Path)
    parser.add_argument('--context-report',type=Path,help='flushed current-context bootstrap evidence')
    a=parser.parse_args(argv)
    try:
        w,h=(int(v) for v in a.size.lower().split('x'))
        result=run(scene=a.scene,width=w,height=h,zoom=a.zoom,frames=a.frames,
                   screenshot=a.screenshot,report=a.report,context_report=a.context_report)
    except Exception as exc:
        print(json.dumps({'status':'gpu-playtest-unavailable','error':str(exc),
            'note':'Old game renderer remains separate; OpenGL 3.3 hardware and optional gpu extras required'},indent=2))
        return 1
    print(json.dumps(result,indent=2));return 0

if __name__=='__main__':raise SystemExit(main())
