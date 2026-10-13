"""Export and profile bounded synthetic QA scenes with the current game renderer.

Example: python tools/reference_scenes.py --scene all --headless --frames 60
    --warmup 5 --width 1280 --height 720 --zoom 28 --png --output-dir /tmp/worldseed-scenes

Dummy-display measurements are renderer throughput, not live FPS or a hardware
acceptance result. Fixtures never read a player save, advance gameplay or run
generation in a measured frame. See the fixture metadata in each JSON report.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.reference_scene_fixtures import (
    ANIMATION_MILLISECONDS, FIXTURE_VERSION, GAME_MINUTE, SCENES, build_fixture,
)
from worldseed.config import DATA_DIR, ENGINE_VERSION, SETTLEMENT_PLAN_VERSION, WORLDGEN_VERSION
from worldseed.content.registry import ContentRegistry
from worldseed.entities.components import Inventory
from worldseed.profiling import RuntimeProfiler
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.ui.widgets import MenuRow


ZOOMS = (20, 28, 36, 48)


def validate_settings(*, frames, warmup, width, height, zoom, distant_npcs, seed):
    for name, value, low, high in (
        ('frames', frames, 1, 600), ('warmup', warmup, 0, 120),
        ('width', width, 640, 3840), ('height', height, 480, 2160),
        ('distant_npcs', distant_npcs, 0, 50000),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError(f'{name} must be an integer between {low} and {high}')
    if zoom not in ZOOMS:
        raise ValueError(f'zoom must be one of {ZOOMS}')
    if not isinstance(seed, str) or not seed or len(seed.encode('utf-8')) > 256:
        raise ValueError('seed must contain 1 to 256 UTF-8 bytes')


@contextmanager
def _display_environment(headless):
    previous = {key: os.environ.get(key) for key in ('SDL_VIDEODRIVER', 'SDL_AUDIODRIVER')}
    if headless:
        os.environ['SDL_VIDEODRIVER'] = 'dummy'
        os.environ['SDL_AUDIODRIVER'] = 'dummy'
    try:
        yield
    finally:
        if headless:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


@contextmanager
def frozen_visual_clock(pg):
    """Freeze pygame's presentation phase while retaining real event servicing."""
    original = pg.time.get_ticks
    pg.time.get_ticks = lambda: ANIMATION_MILLISECONDS
    try:
        yield
    finally:
        pg.time.get_ticks = original


def service_events(term):
    """Drain the event queue every iteration; close/Escape interrupts promptly."""
    pg = term.pg
    for event in pg.event.get():
        if event.type == pg.QUIT or (event.type == pg.KEYDOWN and event.key == pg.K_ESCAPE):
            return False
        if event.type in (pg.VIDEORESIZE, getattr(pg, 'WINDOWRESIZED', pg.NOEVENT)):
            # Fixed size is an explicit fixture input. Reassert it instead of
            # mixing unrelated viewport sizes into a single timing sample.
            if term.screen.get_size() != (term.width, term.height):
                term.screen = pg.display.set_mode((term.width, term.height), pg.RESIZABLE)
    return True


def cache_counts(term, fixture):
    sizes = {'world_chunks': len(fixture.world.cache),
             'prepared_resource_chunks': len(fixture.sim.resources._feature_chunk_cache)}
    for name in ('_sprite_cache', '_terrain_transition_cache', '_terrain_transition_masks',
                 '_base_layer_cache', '_resource_view_cache', '_resource_cell_cache',
                 '_water_current_cache', '_overlay_cache', '_panel_icon_cache',
                 '_interior_art_sources', '_interior_art_scaled'):
        sizes[name.removeprefix('_')] = len(getattr(term, name, {}))
    weather = term._weather_fx
    for name in ('_cloud_cache', '_rain_cache'):
        sizes['weather_' + name.removeprefix('_')] = len(getattr(weather, name, {}))
    return sizes


def _hardware():
    processor = platform.processor()
    if not processor:
        try:
            for line in Path('/proc/cpuinfo').read_text().splitlines():
                if line.startswith('model name'):
                    processor = line.split(':', 1)[-1].strip()
                    break
        except OSError:
            pass
    return {'machine': platform.machine(), 'processor': processor or 'unknown',
            'logical_cpus': os.cpu_count(), 'os': platform.platform(),
            'python': platform.python_version(), 'python_build': list(platform.python_build()),
            'engine_version': ENGINE_VERSION}


def _build_identity():
    root = Path(__file__).resolve().parents[1]
    try:
        revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root,
                                  capture_output=True, text=True, timeout=3, check=True)
        status = subprocess.run(['git', 'status', '--porcelain'], cwd=root,
                                capture_output=True, text=True, timeout=3, check=True)
        return {'git_revision': revision.stdout.strip(),
                'working_tree_dirty': bool(status.stdout.strip())}
    except (OSError, subprocess.SubprocessError):
        return {'git_revision': None, 'working_tree_dirty': None}


def _panel_data(fixture):
    sim = fixture.sim
    inventory = sim.entities.get(sim.player_id, Inventory)
    items = {}
    for iid, count in sorted(inventory.items.items()):
        definition = sim.registry.items[iid]
        items[iid] = {'name': definition.name, 'count': count,
                      'description': definition.description, 'category': definition.category,
                      'mass_kg': definition.mass_g*count/1000,
                      'volume_l': definition.volume_ml*count/1000}
    rows = [MenuRow(iid, data['name']) for iid, data in items.items()]
    return rows, {'items': items, 'stack_count': len(items),
                  'item_count': sum(inventory.items.values()),
                  'total_mass_kg': sum(row['mass_kg'] for row in items.values()),
                  'total_volume_l': sum(row['volume_l'] for row in items.values()),
                  'selected_key': rows[0].key if rows else '', 'active_filter': 'all'}


def render_fixture(term, fixture, panel=None, *, idle_movement_probe=False):
    sim = fixture.sim
    if idle_movement_probe:
        # Fixture actors have no queued locomotion. This exercises the actual
        # continuous-NPC idle scan at growing distant-state counts without
        # advancing game time or changing an actor's authoritative position.
        if sim.update_free_movement(1/60, 0, 0, False):
            raise AssertionError('Idle reference movement unexpectedly changed actor position')
    term._input_mode = 'world'
    term._pointer_targets = []
    term.present_game(sim.registry, sim.world, sim.entities, sim, sim.player_id,
                      message=f'Synthetic QA reference: {fixture.name} · gameplay frozen')
    if panel is not None:
        rows, data = panel
        term._floating_backdrop = term.screen.copy()
        term._input_mode = 'ui'
        with sim.profiler.measure('render.panel'):
            term.present_feature_menu('inventory_unified', 'Inventory', rows, 0,
                                      subtitle='Prepared observational inventory fixture',
                                      total=len(rows), data=data)


def run_scene(name, *, output_dir, frames=60, warmup=5, width=1280, height=720,
              zoom=28, seed='worldseed-reference-v1', distant_npcs=None,
              headless=False, png=False, allocations=False, idle_movement_probe=False,
              registry=None):
    effective_distant = (1000 if name == 'large_save' else 0) if distant_npcs is None else distant_npcs
    validate_settings(frames=frames, warmup=warmup, width=width, height=height,
                      zoom=zoom, distant_npcs=effective_distant, seed=seed)
    if name not in SCENES:
        raise ValueError(f'Unknown reference scene: {name}')
    if not PygameTerminal.available():
        raise RuntimeError('pygame-ce is required for reference scenes')
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    registry = registry or ContentRegistry.load(DATA_DIR)
    # large_save shares exactly the village viewport; only distant state grows.
    with tempfile.TemporaryDirectory(prefix='worldseed-reference-') as temporary:
        prepare_started = time.perf_counter()
        fixture = build_fixture(name, registry, Path(temporary), seed=seed, width=width,
                                height=height, zoom=zoom, distant_npcs=effective_distant)
        preparation_ms = (time.perf_counter()-prepare_started)*1000
        term = None
        tracing_owned = False
        try:
            if idle_movement_probe:
                fixture.sim.set_free_movement_enabled(True)
            before = fixture.authority_fingerprint()
            panel = _panel_data(fixture) if name == 'open_panel' else None
            with _display_environment(headless):
                term = PygameTerminal(width, height)
                term.enter()
                term._tile_px = zoom
                term._last_mouse = (-1, -1)
                # Keep actual display presentation but measure unpaced renderer
                # throughput. Live scheduling/vsync are separate runtime probes.
                term.clock = SimpleNamespace(tick=lambda *args: 0)
                fixture.sim.profiler = RuntimeProfiler(enabled=False)
                interrupted = False
                measured = 0
                allocation_report = None
                with frozen_visual_clock(term.pg):
                    for _ in range(warmup):
                        if not service_events(term):
                            interrupted = True
                            break
                        render_fixture(term, fixture, panel, idle_movement_probe=idle_movement_probe)
                    fixture.sim.profiler = RuntimeProfiler(enabled=True, max_samples=600)
                    if allocations and not interrupted:
                        import tracemalloc
                        tracing_owned = not tracemalloc.is_tracing()
                        if tracing_owned:
                            tracemalloc.start()
                        allocation_before = tracemalloc.take_snapshot()
                        bytes_before, _ = tracemalloc.get_traced_memory()
                        if tracing_owned:
                            tracemalloc.reset_peak()
                    for _ in range(frames):
                        if interrupted or not service_events(term):
                            interrupted = True
                            break
                        with fixture.sim.profiler.measure('reference.iteration'):
                            render_fixture(term, fixture, panel, idle_movement_probe=idle_movement_probe)
                        measured += 1
                    if allocations and not interrupted:
                        allocation_after = tracemalloc.take_snapshot()
                        current_bytes, peak_bytes = tracemalloc.get_traced_memory()
                        comparison = allocation_after.compare_to(allocation_before, 'lineno')
                        allocation_report = {
                            'current_bytes': current_bytes, 'peak_bytes': peak_bytes,
                            'net_bytes': current_bytes-bytes_before,
                            'net_allocations': sum(row.count_diff for row in comparison),
                            'peak_scope': 'measured_frames' if tracing_owned else 'existing_tracer',
                            'top_growth': [{'location': str(row.traceback), 'bytes': row.size_diff,
                                            'allocations': row.count_diff}
                                           for row in comparison if row.size_diff > 0][:10],
                        }
                    screenshot = None
                    if png and measured:
                        screenshot = output_dir / f'{name}.png'
                        term.pg.image.save(term.screen, str(screenshot))
                    pixel_digest = hashlib.sha256(term.pg.image.tobytes(term.screen, 'RGB')).hexdigest() if measured else None
                    after = fixture.authority_fingerprint()
                    if before != after:
                        raise AssertionError('Reference rendering mutated authoritative simulation, terrain or database')
                    result = {
                        'scene': name, 'fixture_mode': 'prepared-synthetic-qa',
                        'fixture_version': FIXTURE_VERSION,
                        'hardware': _hardware(), 'pygame': term.pg.version.ver,
                        'build_identity': _build_identity(),
                        'sdl': list(term.pg.get_sdl_version()), 'driver': term.pg.display.get_driver(),
                        'headless': headless, 'pacing': 'unpaced-renderer-throughput',
                        'idle_movement_probe': idle_movement_probe,
                        'size': [width, height], 'zoom_tile_px': zoom, 'seed': seed,
                        'game_minute': GAME_MINUTE, 'animation_ms': ANIMATION_MILLISECONDS,
                        'worldgen_version': WORLDGEN_VERSION,
                        'settlement_plan_version': SETTLEMENT_PLAN_VERSION,
                        'plan_fingerprint': fixture.plan_fingerprint,
                        'preparation_ms': preparation_ms, 'warmup_requested': warmup,
                        'frames_requested': frames, 'frames_measured': measured,
                        'interrupted': interrupted, 'state_counts': fixture.counts(),
                        'cache_counts': cache_counts(term, fixture),
                        'save_bytes': fixture.db.path.stat().st_size,
                        'state_json_bytes': fixture.state_json_bytes,
                        'authority_fingerprint': before, 'authority_unchanged': True,
                        'pixel_sha256': pixel_digest,
                        'png': str(screenshot.resolve()) if screenshot else None,
                        'timings': fixture.sim.profiler.snapshot(), 'allocations': allocation_report,
                        'timing_notes': {
                            'percentiles': 'linear interpolation over retained rolling samples',
                            'nested_stages': {'render.terrain_cache': 'render.terrain'},
                            'reference.iteration': 'world frame plus optional panel/idle movement probe; events outside sample',
                            'render.frame': 'excludes clock pacing; includes display flip',
                            'cold_loads_included': warmup == 0,
                        },
                    }
                    (output_dir / f'{name}.json').write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
                    return result
        finally:
            if tracing_owned:
                import tracemalloc
                tracemalloc.stop()
            if term is not None:
                term.restore()
            fixture.close()


def make_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scene', choices=(*SCENES, 'all'), default='all')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--frames', type=int, default=60)
    parser.add_argument('--warmup', type=int, default=5)
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--height', type=int, default=720)
    parser.add_argument('--zoom', type=int, choices=ZOOMS, default=28)
    parser.add_argument('--seed', default='worldseed-reference-v1')
    parser.add_argument('--distant-npcs', type=int, default=None,
                        help='Distant NPCs (default: 1000 for large_save, 0 elsewhere)')
    parser.add_argument('--headless', action='store_true', help='Explicitly use SDL dummy display')
    parser.add_argument('--png', action='store_true', help='Export the last measured frame')
    parser.add_argument('--allocations', action='store_true', help='Trace measured Python allocations (adds overhead)')
    parser.add_argument('--idle-movement-probe', action='store_true',
                        help='Measure real idle continuous-NPC update without advancing game time')
    return parser


def main(argv=None):
    parser = make_parser()
    args = parser.parse_args(argv)
    options = vars(args).copy()
    scene = options.pop('scene')
    try:
        checked = {key: options[key] for key in
                   ('frames', 'warmup', 'width', 'height', 'zoom', 'distant_npcs', 'seed')}
        if checked['distant_npcs'] is None:
            checked['distant_npcs'] = 0
        validate_settings(**checked)
    except ValueError as exc:
        parser.error(str(exc))
    registry = ContentRegistry.load(DATA_DIR)
    reports = []
    for name in SCENES if scene == 'all' else (scene,):
        print(f'Preparing synthetic QA scene: {name}', file=sys.stderr, flush=True)
        result = run_scene(name, registry=registry, **options)
        reports.append(result)
        if result['interrupted']:
            break
    summary = {'fixture_mode': 'prepared-synthetic-qa', 'scenes': reports,
               'completed': len(reports) == (len(SCENES) if scene == 'all' else 1)
                            and not any(row['interrupted'] for row in reports)}
    (args.output_dir / 'summary.json').write_text(json.dumps(summary, indent=2, sort_keys=True)+'\n')
    print(json.dumps(summary, sort_keys=True))
    return 0 if summary['completed'] else 130


if __name__ == '__main__':
    raise SystemExit(main())
