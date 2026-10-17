"""Bounded native GPU trace of an isolated furnished interior, never player saves.

Run from the checkout: python -m tools.bench_indoor_render --output <directory>
Reports CPU capture/preparation and synchronized GPU draw cost separately.
Positions are legal fixture samples, not an interactive movement FPS claim.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import statistics
import tempfile
import time


def summary(samples):
    ordered=sorted(samples)
    return {'p50_ms':round(statistics.median(samples),3),
            'p95_ms':round(ordered[max(0,int(len(ordered)*.95)-1)],3)}


def run(output,frames=90):
    import moderngl
    import pygame
    from worldseed.config import DATA_DIR
    from worldseed.content.registry import ContentRegistry
    from worldseed.presentation.gl_worldspace import GLWorldspaceRenderer
    from worldseed.presentation.gpu_scene_bridge import GpuMaterialSource
    from worldseed.presentation.live_gpu_scene import capture_live_scene
    from worldseed.presentation.visuals import VisualRegistry
    from worldseed.presentation.worldspace import WorldCamera,WorldFoot
    from worldseed.systems.interiors import position_clear
    from tools.reference_scene_fixtures import build_fixture

    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    registry=ContentRegistry.load(DATA_DIR)
    width,height=960,640
    ctx=moderngl.create_standalone_context(require=330)
    texture=ctx.texture((width,height),4)
    target=ctx.framebuffer(color_attachments=[texture])
    renderer=GLWorldspaceRenderer(ctx,width,height)
    materials=GpuMaterialSource(pygame,visuals=VisualRegistry.load_default())
    captures,prepares,draws,calls,totals=[],[],[],[],[]
    try:
        with tempfile.TemporaryDirectory(dir=output) as directory:
            fixture=build_fixture('interior',registry,Path(directory),
                                  width=width,height=height,zoom=36)
            try:
                sim=fixture.sim
                player=sim.interiors.player_presence()
                plan=sim.interiors.current_plan()
                positions=[(x,y) for y in range(max(400,player.y-2400),
                           min(plan.height-400,player.y+400),160)
                           for x in range(max(400,player.x-1400),
                           min(plan.width-400,player.x+1400),160)
                           if position_clear(plan,x,y)]
                if not positions:
                    raise RuntimeError('fixture has no legal trace positions')
                for i in range(frames+5):
                    player.x,player.y=positions[max(0,i-5)%len(positions)]
                    camera=WorldCamera(WorldFoot(player.x/1000,player.y/1000,0),
                                       width,height,48)
                    start=time.perf_counter()
                    snap=capture_live_scene(sim,camera)
                    captured=time.perf_counter()
                    frame=snap.gpu_frame(materials=materials,registry=registry,
                                         resource_style=lambda _: {})
                    prepared=time.perf_counter()
                    report=renderer.draw(frame.commands,target=target,clear=(0,0,0,0))
                    ctx.finish()
                    finished=time.perf_counter()
                    if i>=5:
                        captures.append((captured-start)*1000)
                        prepares.append((prepared-captured)*1000)
                        draws.append((finished-prepared)*1000)
                        totals.append((finished-start)*1000)
                        calls.append(report.draw_calls)
                raw=target.read(components=4,alignment=1)
                art=pygame.image.frombytes(raw,(width,height),'RGBA')
                art=pygame.transform.flip(art,False,True)
                background=pygame.Surface((width,height))
                background.fill((0,0,0));background.blit(art,(0,0))
                pygame.image.save(background,str(output/'frame.png'))
                result={'renderer':ctx.info['GL_RENDERER'],'viewport':[width,height],
                    'frames':frames,'warmup_frames':5,'capture':summary(captures),
                    'prepare':summary(prepares),'draw_and_finish':summary(draws),
                    'total':summary(totals),'draw_calls_p50':statistics.median(calls),
                    'last_frame_commands':len(frame.commands),
                    'texture_bytes':renderer.bank.bytes}
                (output/'timings.json').write_text(json.dumps(result,indent=2)+'\n',
                                                   encoding='utf-8',newline='\n')
                return result
            finally:
                fixture.close()
    finally:
        renderer.close();target.release();texture.release();ctx.release()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--frames',type=int,default=90)
    args=parser.parse_args()
    if not 10<=args.frames<=240:
        parser.error('--frames must be between 10 and 240')
    print(json.dumps(run(args.output,args.frames),indent=2))


if __name__=='__main__':
    main()
