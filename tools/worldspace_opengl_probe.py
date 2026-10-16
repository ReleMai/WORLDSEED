"""Native, single-window WORLDSEED shader renderer candidate smoke/probe.

This is an isolated scene (NOT a game renderer cutover), with exact display
ownership and no SDL dummy driver. Real Windows GPU/driver evidence required.
Run: python -m tools.worldspace_opengl_probe --frames 180 --output scratch/gpu-tree.json
     python -m tools.worldspace_opengl_probe --frames 180 --size 2560x1440 --screenshot scratch/gpu-trees.png
Requirements (optional extras): pygame-ce, moderngl, glcontext.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict
from functools import lru_cache
from io import BytesIO
from hashlib import sha256
import json
import os
from pathlib import Path
import statistics
import time

from worldseed.presentation.gl_worldspace import GPUBackendUnavailable,GLWorldspaceRenderer,SpriteCommand
from worldseed.presentation.gl_context import create_sdl_context
from worldseed.presentation.tree_art import layer_png
from worldseed.presentation.worldspace import VisualLayer, WorldCamera, WorldFoot
from worldseed.presentation.worldspace_adapter import PreparedActor,prepare_worldspace_scene
from worldseed.systems.state import pos_key


def one_scene(w,h,zoom,phase):
    from types import SimpleNamespace
    cx,cy=10.5+phase,10.5
    camera=WorldCamera(WorldFoot(cx,cy,0),w,h,zoom)
    visible={pos_key(x,y,0) for x in range(-20,48) for y in range(-20,48)}
    resources={(10,10,0):(SimpleNamespace(feature_id='core:oak_tree',stage='mature'),None),
               (13,10,0):(SimpleNamespace(feature_id='core:pine_tree',stage='mature'),None)}
    definitions={name:SimpleNamespace(tags=('tree',),blocks_movement=True)
                 for name in ('core:oak_tree','core:pine_tree')}
    viewer=PreparedActor('player','core:player',WorldFoot(11.5,10.6),True,is_viewer=True)
    return prepare_worldspace_scene(camera=camera,resource_by=resources,
        resource_defs=definitions,resource_style=lambda fid:{'width':1.3,'height':1.8},
        current_cells=visible,discovered_cells=visible,actors=(viewer,),z=0,
        visibility_key=pos_key)


@lru_cache(maxsize=16)
def _material_rgba(species,layer,season):
    import pygame as pg
    img=pg.image.load(BytesIO(layer_png(species,layer,season)),species+'_'+layer+'.png')
    return (pg.image.tobytes(img,'RGBA'),*img.get_size())


def scene_commands(scene,pg,season='summer'):
    from worldseed.presentation.gl_worldspace import commands_from_projected
    from worldseed.presentation.tree_art import layer_png
    def texture(v):
        if v.instance.resource_id is None:return None
        species='oak' if 'oak' in v.instance.content_id else 'pine'
        layer={VisualLayer.GROUNDED:'trunk',VisualLayer.GROUND_SHADOW:'shadow',
               VisualLayer.OVERHEAD:'crown'}.get(v.instance.layer)
        if layer is None:return None
        rgba,w,h=_material_rgba(species,layer,season)
        return (f'{species}:{layer}:{season}',1,rgba,w,h)
    return commands_from_projected(scene.projection,texture)


def run(width=1280,height=720,frames=180,screenshot=None,context_report=None):
    if os.environ.get('SDL_VIDEODRIVER')=='dummy':
        raise GPUBackendUnavailable('SDL dummy driver is not real hardware validation')
    import pygame as pg
    pg.init()
    renderer=None
    try:
        pg.display.gl_set_attribute(pg.GL_CONTEXT_MAJOR_VERSION,3)
        pg.display.gl_set_attribute(pg.GL_CONTEXT_MINOR_VERSION,3)
        pg.display.gl_set_attribute(pg.GL_CONTEXT_PROFILE_MASK,pg.GL_CONTEXT_PROFILE_CORE)
        pg.display.set_mode((width,height),pg.DOUBLEBUF|pg.OPENGL|pg.RESIZABLE)
        ctx=create_sdl_context(pg,diagnostics=context_report)
        renderer=GLWorldspaceRenderer(ctx,width,height)
        samples=[];first_last=None;interrupted=False
        screenshot_pixels=None
        driver={'vendor':ctx.info.get('GL_VENDOR','unknown'),
                'renderer':ctx.info.get('GL_RENDERER','unknown'),
                'version':ctx.info.get('GL_VERSION','unknown')}
        for i in range(frames):
            for event in pg.event.get():
                if event.type==pg.QUIT:
                    interrupted=True
                if event.type==pg.VIDEORESIZE:
                    width,height=event.size
                    renderer.resize(width,height)
            if interrupted:break
            scene=one_scene(width,height,32,0.15*i/frames)
            commands=scene_commands(scene,pg,'summer')
            started=time.perf_counter()
            report=renderer.draw(commands,ambient=(.91,.96,1.0))
            if screenshot and i==frames-1:
                screenshot_pixels=ctx.screen.read(components=3,alignment=1)
            pg.display.flip()
            samples.append((time.perf_counter()-started)*1000)
            first_last=report
        if screenshot_pixels is not None:
            # GL framebuffer reads are inverted; capture BEFORE swap/present.
            image=pg.image.fromstring(screenshot_pixels,(width,height),'RGB')
            path=Path(screenshot);path.parent.mkdir(parents=True,exist_ok=True)
            pg.image.save(pg.transform.flip(image,False,True),str(path))
        nums=sorted(samples)
        def percentile(p):return nums[min(len(nums)-1,int((len(nums)-1)*p))] if nums else None
        return {'status':'opengl-sample-not-release-certification','backend':'ModernGL/OpenGL 3.3',
            'driver':driver,'window_owned':'single pygame SDL OPENGL context',
            'sdl_video_driver':pg.display.get_driver(),'native_hardware_accepted':False,
            'frames':len(samples),'interrupted':interrupted,'size':[width,height],
            'present_included':True,'p50_ms':percentile(.50),'p95_ms':percentile(.95),
            'p99_ms':percentile(.99),'worst_ms':max(samples) if samples else None,
            'last_frame':asdict(first_last) if first_last else {},
            'software_fallback':'unchanged, no production cutover',
            'limitations':'prepared synthetic trees; CPU draw/present wall time, no explicit GPU completion sync; '
                'driver may be software; no full gameplay/UI parity, hardware approval or native soak'}
    finally:
        if renderer is not None:renderer.close()
        pg.quit()


def main(argv=None):
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--size',default='1280x720')
    a.add_argument('--frames',type=int,default=180)
    a.add_argument('--output',type=Path)
    a.add_argument('--screenshot',type=Path)
    a.add_argument('--context-report',type=Path,help='flushed current-context bootstrap evidence')
    args=a.parse_args(argv)
    try:
        width,height=map(int,args.size.lower().split('x'))
        if not 1<=args.frames<=600 or not 640<=width<=3840 or not 480<=height<=2160:
            raise ValueError('invalid bounded probe size or frame count')
        context_report=args.context_report or (args.output.with_suffix('.context.json') if args.output else None)
        report=run(width,height,args.frames,args.screenshot,context_report)
    except Exception as exc:
        report={'status':'unavailable','error':type(exc).__name__+': '+str(exc),
                'software_fallback':'unchanged; native GPU not validated'}
        print(json.dumps(report,indent=2));return 1
    data=json.dumps(report,indent=2)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(data)
    print(data)
    return 0

if __name__=='__main__':raise SystemExit(main())
