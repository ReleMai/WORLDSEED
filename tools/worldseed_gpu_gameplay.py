"""W2 single-window GPU gameplay candidate; existing game/preview stay separate.

Default: a new temporary world through normal authoritative game startup, with
empty inventory and real simulation discovery. No player save is opened or saved.
Optional --prepared-scene uses synthetic QA terrain and production commands;
its prepared discovery/realization overrides are NOT a natural-world playtest.
Controls: WASD/arrows move, Shift sprint, . wait, P pickup, mouse hover projects
the visible cell, F12 screenshot, Esc exit. Full game UI/actions remain W3 work.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from math import ceil, sqrt
import os
from pathlib import Path
import statistics
import tempfile
import time

from worldseed.presentation.gl_atmosphere import GLAtmospherePass
from worldseed.presentation.gl_worldspace import GLWorldspaceRenderer, GPUBackendUnavailable
from worldseed.presentation.gpu_scene_bridge import GpuMaterialSource
from worldseed.presentation.live_gpu_scene import capture_live_scene, player_foot
from worldseed.presentation.worldspace import WorldCamera
from worldseed.ui.gpu_gameplay_input import GpuGameplayInput, project_pointer


def _percentile(samples, fraction):
    ordered = sorted(samples)
    return ordered[min(len(ordered)-1, int((len(ordered)-1)*fraction))] if ordered else None


def _screenshot(pg, ctx, size, path):
    pixels = ctx.screen.read(components=3, alignment=1)
    surface = pg.image.fromstring(pixels, size, 'RGB')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pg.image.save(pg.transform.flip(surface, False, True), str(path))


def run(*, width=1280, height=720, zoom=36, frames=0,
        seed='worldseed-gpu-gameplay-w2', prepared_scene=None, screenshot=None, report=None):
    if os.environ.get('SDL_VIDEODRIVER') == 'dummy':
        raise GPUBackendUnavailable('SDL dummy cannot create a native OpenGL gameplay window')
    if (type(frames) is not int or not 0 <= frames <= 36000
            or not 640 <= width <= 1920 or not 480 <= height <= 1080
            or type(zoom) is not int or not 20 <= zoom <= 56):
        raise ValueError('candidate dimensions, zoom or duration outside bounded scope')
    if prepared_scene not in (None, 'forest', 'camp'):
        raise ValueError('prepared scene must be forest or camp')
    if not isinstance(seed, str) or not 1 <= len(seed.encode('utf-8')) <= 128:
        raise ValueError('seed must contain 1..128 UTF-8 bytes')
    import pygame as pg
    import moderngl
    from worldseed.app import _load_context
    from worldseed.ui.startup import StartSelection
    renderer = post = controller = fixture = context = None
    with tempfile.TemporaryDirectory(prefix='worldseed-gpu-gameplay-') as directory:
        try:
            # Validate the optional graphics backend before expensive normal
            # world startup. This is the same window used for every game frame.
            pg.init()
            pg.display.gl_set_attribute(pg.GL_CONTEXT_MAJOR_VERSION, 3)
            pg.display.gl_set_attribute(pg.GL_CONTEXT_MINOR_VERSION, 3)
            pg.display.gl_set_attribute(pg.GL_CONTEXT_PROFILE_MASK, pg.GL_CONTEXT_PROFILE_CORE)
            pg.display.gl_set_attribute(pg.GL_DOUBLEBUFFER, 1)
            pg.display.set_mode((width, height), pg.DOUBLEBUF | pg.OPENGL | pg.RESIZABLE)
            pg.display.set_caption('WORLDSEED W2 GPU candidate | TEMPORARY session | starting')
            pg.key.set_repeat()
            ctx = moderngl.create_context(require=330)
            renderer = GLWorldspaceRenderer(ctx, width, height)
            post = GLAtmospherePass(ctx, width, height)
            materials = GpuMaterialSource(pg)
            driver = {key: ctx.info.get(key, 'unknown')
                      for key in ('GL_VENDOR', 'GL_RENDERER', 'GL_VERSION')}
            ctx.screen.clear(0.,0.,0.,1.)
            pg.display.flip()

            def startup_progress(phase, progress, detail=''):
                pg.display.set_caption(f'WORLDSEED W2 GPU | TEMPORARY new world | '
                                       f'{int(progress*100)}% {phase}')
                print(f'{int(progress*100):3d}% {phase}: {detail}', flush=True)

            if prepared_scene:
                from tools.reference_scene_fixtures import build_fixture
                from worldseed.config import DATA_DIR
                from worldseed.content.registry import ContentRegistry
                registry = ContentRegistry.load(DATA_DIR)
                fixture = build_fixture(prepared_scene, registry, Path(directory),
                                        width=width, height=height, zoom=36)
                sim = fixture.sim
            else:
                context = _load_context(StartSelection(
                    Path(directory)/'gpu-w2.db', True, 'GPU gameplay candidate',
                    seed.encode('utf-8').hex(), 'GPU QA', 'wilderness'),
                    startup_progress)
                sim, registry = context.sim, context.registry
            initial_pos = sim.player_pos
            initial_minute = sim.clock.minute
            controller = GpuGameplayInput(sim)
            key_map = {pg.K_UP:'UP', pg.K_DOWN:'DOWN', pg.K_LEFT:'LEFT', pg.K_RIGHT:'RIGHT',
                       pg.K_w:'w', pg.K_a:'a', pg.K_s:'s', pg.K_d:'d',
                       pg.K_PERIOD:'.', pg.K_p:'p', pg.K_RETURN:'\r', pg.K_TAB:'\t'}
            frame_times = []
            render_times = []
            clock = pg.time.Clock()
            start = time.monotonic()
            running = True
            count = 0
            pointer = None
            pending_capture = Path(screenshot) if screenshot else None
            last_report = None
            snapshot = None
            while running and (not frames or count < frames):
                frame_start = time.perf_counter()
                # The sole event pump precedes simulation updates, so release
                # and focus loss cannot sit behind an expensive redraw.
                for event in pg.event.get():
                    if event.type == pg.QUIT:
                        running = False
                    elif event.type == getattr(pg, 'WINDOWFOCUSLOST', -1):
                        controller.set_focus(False)
                    elif event.type == getattr(pg, 'WINDOWFOCUSGAINED', -2):
                        controller.set_focus(True)
                    elif event.type == pg.VIDEORESIZE:
                        if 640 <= event.w <= 1920 and 480 <= event.h <= 1080:
                            width, height = event.w, event.h
                            renderer.resize(width, height)
                            post.resize(width, height)
                    elif event.type == pg.KEYUP and event.key in key_map:
                        controller.release(key_map[event.key])
                    elif event.type == pg.KEYDOWN:
                        if event.key == pg.K_ESCAPE:
                            running = False
                        elif event.key == pg.K_F12:
                            pending_capture = Path(screenshot or 'scratch/gpu-gameplay.png')
                        elif event.key in key_map:
                            controller.press(key_map[event.key], repeat=bool(getattr(event, 'repeat', False)))
                    elif event.type == pg.MOUSEMOTION:
                        pointer = event.pos
                if not running:
                    break
                controller.update(time.monotonic(), sprint=bool(pg.key.get_mods() & pg.KMOD_SHIFT))
                # Update -> immutable capture -> GPU draw. None of the latter
                # phases receive command callbacks or advance simulation time.
                scale = max(zoom, ceil(sqrt(width*height/2200)))
                camera = WorldCamera(player_foot(sim), width, height, scale)
                snapshot = capture_live_scene(sim, camera)
                frame = snapshot.gpu_frame(materials=materials, registry=registry,
                    resource_style=lambda fid: {'width':1.35, 'height':1.9})
                fx = snapshot.atmosphere(time.monotonic()-start)
                draw_start = time.perf_counter()
                last_report = renderer.draw(frame.commands, target=post.scene_target,
                    frame_time_seconds=fx.elapsed_seconds, clear=(0.,0.,0.,0.))
                post.present(fx)
                render_times.append((time.perf_counter()-draw_start)*1000.)
                if pending_capture and (not frames or count == frames-1):
                    _screenshot(pg, ctx, (width, height), pending_capture)
                    pending_capture = None
                pg.display.flip()
                target = project_pointer(camera, *pointer) if pointer else None
                cell = (target.x,target.y,target.z) if target else None
                hover = str(cell) if cell in snapshot.current_cells else 'unknown'
                pg.display.set_caption(f'WORLDSEED W2 GPU candidate | TEMPORARY session | {sim.player_pos} | '
                    f'minute {sim.clock.minute} | hover {hover} | WASD / Shift / . / P / F12 / Esc')
                frame_times.append((time.perf_counter()-frame_start)*1000.)
                count += 1
                clock.tick(60)
            result = {
                'status':'gpu-gameplay-candidate-not-production-certification',
                'gpu':driver, 'platform':os.name, 'size':[width,height], 'frames':count,
                'source':'prepared-synthetic-'+prepared_scene if prepared_scene else 'temporary-normal-game-startup',
                'player_saves_opened':False, 'initial_position':asdict(initial_pos),
                'final_position':asdict(sim.player_pos), 'initial_minute':initial_minute,
                'final_minute':sim.clock.minute,
                'frame_cpu_p50_ms':statistics.median(frame_times) if frame_times else None,
                'frame_cpu_p95_ms':_percentile(frame_times,.95),
                'frame_cpu_p99_ms':_percentile(frame_times,.99),
                'render_submit_p50_ms':statistics.median(render_times) if render_times else None,
                'render_submit_p95_ms':_percentile(render_times,.95),
                'render_submit_p99_ms':_percentile(render_times,.99),
                'last_frame':asdict(last_report) if last_report else {},
                'current_cells':len(snapshot.current_cells) if snapshot else 0,
                'limitations':'W2 movement foundation only; Action Hub, game UI, interiors, save/load, '
                    'directional shadows and native Windows hardware approval pending. CPU timings '
                    'measure submission, not GPU completion. Prepared scenes override discovery '
                    'and world realization and do not demonstrate natural-world exploration.'}
            if report:
                path = Path(report)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
            return result
        finally:
            if controller is not None: controller.close()
            if post is not None: post.close()
            if renderer is not None: renderer.close()
            pg.quit()
            if fixture is not None: fixture.close()
            if context is not None: context.db.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--size', default='1280x720')
    parser.add_argument('--zoom', type=int, default=36)
    parser.add_argument('--frames', type=int, default=0)
    parser.add_argument('--seed', default='worldseed-gpu-gameplay-w2')
    parser.add_argument('--prepared-scene', choices=('forest','camp'))
    parser.add_argument('--screenshot', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args(argv)
    try:
        width,height = (int(value) for value in args.size.lower().split('x'))
        result = run(width=width,height=height,zoom=args.zoom,frames=args.frames,seed=args.seed,
                     prepared_scene=args.prepared_scene,screenshot=args.screenshot,report=args.report)
    except Exception as exc:
        print(json.dumps({'status':'gpu-gameplay-unavailable','error':str(exc)},indent=2))
        return 1
    print(json.dumps(result,indent=2))
    return 0


if __name__ == '__main__': raise SystemExit(main())
