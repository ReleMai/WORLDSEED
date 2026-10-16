"""W2 single-window GPU gameplay candidate; existing game/preview stay separate.

Default: a new temporary world through normal authoritative game startup, with
empty inventory and real simulation discovery. No player save is opened or saved.
Optional --prepared-scene uses synthetic QA terrain and production commands;
its prepared discovery/realization overrides are NOT a natural-world playtest.
Controls: WASD/arrows move, Shift sprint, . wait, P pickup, Enter Action Hub,
Tab World Console, mouse selects a visible cell, wheel zooms/pages, F12 captures.
Esc opens pause or goes back one route. Full interiors/game UI remain W3 work.
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
from worldseed.presentation.gl_context import create_sdl_context
from worldseed.presentation.gl_gameplay_ui import GLGameplayUI
from worldseed.presentation.gl_worldspace import GLWorldspaceRenderer, GPUBackendUnavailable
from worldseed.presentation.gpu_scene_bridge import GpuMaterialSource
from worldseed.presentation.live_gpu_scene import capture_live_scene, player_foot
from worldseed.presentation.worldspace import WorldCamera
from worldseed.ui.gpu_gameplay_input import GpuGameplayInput, project_pointer
from worldseed.ui.gpu_gameplay_session import GpuGameplaySession


def _percentile(samples, fraction):
    ordered = sorted(samples)
    return ordered[min(len(ordered)-1, int((len(ordered)-1)*fraction))] if ordered else None


def _screenshot(pg, ctx, size, path):
    pixels = ctx.screen.read(viewport=(0, 0, *size), components=3, alignment=1)
    surface = pg.image.fromstring(pixels, size, 'RGB')
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pg.image.save(pg.transform.flip(surface, False, True), str(path))


def run(*, width=1280, height=720, zoom=36, frames=0,
        seed='worldseed-gpu-gameplay-w2', prepared_scene=None, screenshot=None, report=None,
        qa_weather=None, qa_season=None, qa_time=None):
    if (type(frames) is not int or not 0 <= frames <= 36000
            or not 640 <= width <= 1920 or not 480 <= height <= 1080
            or type(zoom) is not int or not 20 <= zoom <= 56):
        raise ValueError('candidate dimensions, zoom or duration outside bounded scope')
    if prepared_scene not in (None, 'forest', 'camp', 'village_street'):
        raise ValueError('prepared scene must be forest, camp or village_street')
    from tools.gpu_qa_scene import PreparedWeather, qa_minute
    if any(value is not None for value in (qa_weather,qa_season,qa_time)) and not prepared_scene:
        raise ValueError('QA environment options require an explicit prepared scene')
    fixture_minute = qa_minute(qa_season,qa_time)
    fixture_weather = PreparedWeather(qa_weather) if qa_weather is not None else None
    if not isinstance(seed, str) or not 1 <= len(seed.encode('utf-8')) <= 128:
        raise ValueError('seed must contain 1..128 UTF-8 bytes')
    if os.environ.get('SDL_VIDEODRIVER') == 'dummy':
        raise GPUBackendUnavailable('SDL dummy cannot create a native OpenGL gameplay window')
    import pygame as pg
    from worldseed.app import _load_context
    from worldseed.ui.startup import StartSelection
    renderer = post = controller = session = overlay = fixture = context = None
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
            ctx = create_sdl_context(pg, diagnostics=Path(report).with_suffix('.context.json')
                                     if report else None)
            renderer = GLWorldspaceRenderer(ctx, width, height)
            post = GLAtmospherePass(ctx, width, height)
            materials = GpuMaterialSource(pg)
            overlay = GLGameplayUI(ctx, pg, width, height)
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
                                        width=width, height=height, zoom=36, game_minute=fixture_minute)
                sim = fixture.sim
                if fixture_weather is not None:
                    sim.environment.weather = fixture_weather
            else:
                context = _load_context(StartSelection(
                    Path(directory)/'gpu-w2.db', True, 'GPU gameplay candidate',
                    seed.encode('utf-8').hex(), 'GPU QA', 'wilderness'),
                    startup_progress)
                sim, registry = context.sim, context.registry
            initial_pos = sim.player_pos
            initial_minute = sim.clock.minute
            controller = GpuGameplayInput(sim)
            session = GpuGameplaySession(sim, registry, input_controller=controller)
            key_map = {pg.K_UP:'UP', pg.K_DOWN:'DOWN', pg.K_LEFT:'LEFT', pg.K_RIGHT:'RIGHT',
                       pg.K_w:'w', pg.K_a:'a', pg.K_s:'s', pg.K_d:'d',
                       pg.K_PERIOD:'.', pg.K_p:'p', pg.K_RETURN:'\r', pg.K_TAB:'\t',
                       pg.K_ESCAPE:'ESC', pg.K_g:'g', pg.K_i:'i', pg.K_f:'f',
                       pg.K_PAGEUP:'PAGEUP', pg.K_PAGEDOWN:'PAGEDOWN'}
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
            camera = layout = None
            while running and (not frames or count < frames):
                frame_start = time.perf_counter()
                # The sole event pump precedes simulation updates, so release
                # and focus loss cannot sit behind an expensive redraw.
                for event in pg.event.get():
                    if session.quit_requested:
                        break
                    if event.type == pg.QUIT:
                        running = False
                        break
                    elif event.type == getattr(pg, 'WINDOWFOCUSLOST', -1):
                        session.set_focus(False)
                    elif event.type == getattr(pg, 'WINDOWFOCUSGAINED', -2):
                        session.set_focus(True)
                    elif event.type == pg.VIDEORESIZE:
                        if 1 <= event.w <= 3840 and 1 <= event.h <= 2160:
                            width, height = event.w, event.h
                            renderer.resize(width, height)
                            post.resize(width, height)
                            overlay.resize(width, height)
                    elif event.type == pg.KEYUP and event.key in key_map:
                        session.release(key_map[event.key])
                    elif event.type == pg.KEYDOWN:
                        if event.key == pg.K_F12:
                            pending_capture = Path(screenshot or 'scratch/gpu-gameplay.png')
                        elif event.key in key_map:
                            session.press(key_map[event.key], snapshot,
                                repeat=bool(getattr(event, 'repeat', False)))
                    elif event.type == pg.MOUSEMOTION:
                        pointer = event.pos
                    elif event.type == pg.MOUSEWHEEL:
                        if not event.y:
                            continue
                        if session.modal:
                            session.press('PAGEUP' if event.y > 0 else 'PAGEDOWN', snapshot)
                        else:
                            zoom = max(20, min(56, zoom+event.y*4))
                    elif (event.type == pg.MOUSEBUTTONDOWN and event.button in (1,3)
                          and session.window_focused):
                        pointer = event.pos
                        hit = layout.hit_test(*pointer) if layout else None
                        if hit and snapshot is not None:
                            session.activate(hit, snapshot)
                        elif not session.modal and camera is not None and snapshot is not None:
                            if layout is None or not layout.blocks_world(*pointer):
                                target = project_pointer(camera, *pointer)
                                if target is not None:
                                    session.select_cell((target.x,target.y,target.z), snapshot)
                                if event.button == 3:
                                    session.open('actions')
                if session.quit_requested:
                    running = False
                if not running:
                    break
                session.update(time.monotonic(), sprint=bool(pg.key.get_mods() & pg.KMOD_SHIFT))
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
                model = session.observe(snapshot)
                layout = overlay.draw(model)
                session.page_size = max(1, layout.page_size or layout.detail_page_size)
                render_times.append((time.perf_counter()-draw_start)*1000.)
                if pending_capture and (not frames or count == frames-1):
                    _screenshot(pg, ctx, (width, height), pending_capture)
                    pending_capture = None
                pg.display.flip()
                target = project_pointer(camera, *pointer) if pointer else None
                cell = (target.x,target.y,target.z) if target else None
                hover = str(cell) if cell in snapshot.current_cells else 'unknown'
                pg.display.set_caption(f'WORLDSEED W2 GPU candidate | TEMPORARY session | {sim.player_pos} | '
                    f'minute {sim.clock.minute} | hover {hover} | Enter actions / Tab world / Esc pause')
                frame_times.append((time.perf_counter()-frame_start)*1000.)
                count += 1
                clock.tick(60)
            result = {
                'status':'gpu-gameplay-candidate-not-production-certification',
                'gpu':driver, 'platform':os.name, 'size':[width,height], 'frames':count,
                'source':'prepared-synthetic-'+prepared_scene if prepared_scene else 'temporary-normal-game-startup',
                'player_saves_opened':False, 'native_hardware_accepted':False,
                'qa_environment':{'weather':qa_weather,'season':qa_season,'time':qa_time}, 'initial_position':asdict(initial_pos),
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
                'limitations':'W2 outdoor movement/actions/HUD candidate; full game UI, interiors, save/load, '
                    'directional shadows and native Windows hardware approval pending. CPU timings '
                    'measure submission, not GPU completion. Prepared scenes override discovery '
                    'and world realization and do not demonstrate natural-world exploration.'}
            if report:
                path = Path(report)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
            return result
        finally:
            if session is not None: session.close()
            elif controller is not None: controller.close()
            if overlay is not None: overlay.close()
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
    parser.add_argument('--prepared-scene', choices=('forest','camp','village_street'))
    parser.add_argument('--qa-weather', choices=('clear','cloudy','rain','storm','snow','fog'))
    parser.add_argument('--qa-season', choices=('spring','summer','autumn','winter'))
    parser.add_argument('--qa-time', choices=('noon','night','sunrise','sunset'))
    parser.add_argument('--screenshot', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args(argv)
    try:
        width,height = (int(value) for value in args.size.lower().split('x'))
        result = run(width=width,height=height,zoom=args.zoom,frames=args.frames,seed=args.seed,
                     prepared_scene=args.prepared_scene,screenshot=args.screenshot,report=args.report,
                     qa_weather=args.qa_weather,qa_season=args.qa_season,qa_time=args.qa_time)
    except Exception as exc:
        print(json.dumps({'status':'gpu-gameplay-unavailable','error':str(exc)},indent=2))
        return 1
    print(json.dumps(result,indent=2))
    return 0


if __name__ == '__main__': raise SystemExit(main())
