"""Run the full WORLDSEED game with the GPU backend; QA scenes are opt-in."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from importlib.metadata import version
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import traceback


def self_check() -> dict:
    """Check frozen imports/content/art without a window, world or saved game."""
    import pygame as pg
    import moderngl
    import glcontext
    from worldseed.config import DATA_DIR, ENGINE_VERSION, PACKAGE_ROOT
    from worldseed.content.registry import ContentRegistry
    from worldseed.presentation.tree_art import layer_png, SEASONS, SPECIES
    # Resolve the platform's extension now; do not create a GL context here.
    glcontext.default_backend()
    registry = ContentRegistry.load(DATA_DIR)
    if not registry.items or not registry.terrains:
        raise RuntimeError('Bundled engine content is missing')
    shaders = ('worldspace_sprite.vert', 'worldspace_sprite.frag',
               'worldspace_post.vert', 'worldspace_post.frag', 'worldspace_cover.frag')
    for name in shaders:
        text = (PACKAGE_ROOT / 'assets' / 'shaders' / name).read_text(encoding='utf-8')
        if '#version 330' not in text or 'void main' not in text:
            raise RuntimeError('Missing or invalid shader: ' + name)
    tree_layers = 0
    for species in SPECIES:
        for channel, seasons in (('trunk', ('summer',)), ('shadow', ('summer',)),
                                 ('crown', SEASONS)):
            for season in seasons:
                image = pg.image.load(BytesIO(layer_png(species, channel, season)), 'tree.png')
                if min(image.get_size()) < 1:
                    raise RuntimeError('Empty bundled tree layer')
                tree_layers += 1
    from worldseed.presentation.gpu_scene_bridge import GpuMaterialSource, terrain_source
    materials = GpuMaterialSource(pg)
    materials.player()
    materials.asset(terrain_source('core:forest', 0, 0))
    from worldseed.ui.gpu_control_art import ICON_PATHS, load_icon
    for key in ICON_PATHS:
        load_icon(pg, key, 32)
    # These imports must survive freezing, including the QA namespace package.
    from tools import reference_scene_fixtures, worldseed_gpu_gameplay, worldseed_gpu_playtest
    from worldseed import app
    from worldseed.ui import startup, gpu_terminal
    return {'status': 'gpu-bundle-selfcheck-ok', 'engine': ENGINE_VERSION,
            'pygame': pg.version.ver, 'moderngl': moderngl.__version__,
            'glcontext': version('glcontext'), 'items': len(registry.items),
            'terrains': len(registry.terrains), 'tree_layers': tree_layers,
            'shaders': len(shaders), 'control_icons': len(ICON_PATHS), 'player_saves_opened': False,
            'native_hardware_accepted': False, 'main_game_imports': True,
            'note': 'Packaging/import check only; no OpenGL context was created.'}


def _runtime_directory() -> Path:
    return Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'WORLDSEED'


@contextmanager
def _game_environment(args):
    settings = {'WORLDSEED_UI': 'gpu', 'WORLDSEED_GPU_SIZE': args.size,
                'WORLDSEED_GPU_REPORT': str(args.report.resolve()),
                'WORLDSEED_GPU_SMOKE_FRAMES': str(args.frames or 2) if args.smoke_main else None,
                'WORLDSEED_GPU_SCREENSHOT': str(args.screenshot.resolve()) if args.screenshot else None,
                'WORLDSEED_PROFILE': '1' if args.profile_runtime else os.environ.get('WORLDSEED_PROFILE')}
    previous = {key: os.environ.get(key) for key in settings}
    original_directory = Path.cwd()
    try:
        for key, value in settings.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        # A frozen executable may live under a read-only installation directory.
        # Keep normal save format/startup; source launches retain current saves.
        if getattr(sys, 'frozen', False):
            runtime = _runtime_directory()
            runtime.mkdir(parents=True, exist_ok=True)
            os.chdir(runtime)
        yield
    finally:
        os.chdir(original_directory)
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _main_game(args) -> int:
    """Select presentation only; startup, commands and persistence stay in app."""
    with _game_environment(args):
        # The import belongs after working-directory selection: config pins the
        # normal save directory on first import, including frozen cold startup.
        from worldseed.app import main as game_main
        result = int(game_main())
    # app.main also supports the legacy terminal and catches display startup
    # errors. Preserve a diagnosed GPU rejection for the frozen smoke harness.
    if result == 2:
        context_path = args.report.with_suffix('.context.json')
        try:
            evidence = json.loads(context_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            evidence = {}
        if evidence.get('stage') == 'rejected':
            from worldseed.presentation.gl_worldspace import GPUBackendUnavailable
            raise GPUBackendUnavailable('The current driver rejected the GPU startup; '
                                        'see ' + str(context_path))
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selfcheck', action='store_true')
    parser.add_argument('--smoke-main', action='store_true',
                        help='Bounded production startup-menu smoke; never selects or loads a world')
    parser.add_argument('--profile-runtime', action='store_true',
                        help='Enable the existing main-game runtime profiler')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--prepared-scene', choices=('forest', 'camp', 'village_street'),
                       help='Temporary synthetic scene using authoritative gameplay commands')
    modes.add_argument('--preview', choices=('forest', 'camp'),
                       help='Visual-only arena: F weather, 1-4 seasons, [/] sun, T torch')
    parser.add_argument('--qa-weather', choices=('clear', 'cloudy', 'rain', 'storm', 'snow', 'fog'))
    parser.add_argument('--qa-season', choices=('spring', 'summer', 'autumn', 'winter'))
    parser.add_argument('--qa-time', choices=('noon', 'night', 'sunrise', 'sunset'))
    parser.add_argument('--size', default='1280x720')
    parser.add_argument('--frames', type=int, default=0)
    parser.add_argument('--seed', default='worldseed-gpu-gameplay-w2')
    parser.add_argument('--screenshot', type=Path)
    parser.add_argument('--report', type=Path,
                        help='Local diagnostics JSON (default: logs in the game runtime folder)')
    args = parser.parse_args(argv)
    if not 0 <= args.frames <= (600 if args.smoke_main else 36000):
        parser.error('--frames exceeds the bounded smoke/QA duration')
    if args.report is None:
        normal = not (args.prepared_scene or args.preview or args.selfcheck)
        base = _runtime_directory() if normal and getattr(sys, 'frozen', False) else Path.cwd()
        args.report = base / 'logs' / 'gpu-session.json'
    if args.smoke_main and (args.prepared_scene or args.preview):
        parser.error('--smoke-main cannot be combined with a QA scene')
    if args.frames and not (args.prepared_scene or args.preview or args.smoke_main):
        parser.error('--frames requires --smoke-main or an explicit QA scene')
    if (args.qa_weather or args.qa_season or args.qa_time) and not args.prepared_scene:
        parser.error('--qa-weather/--qa-season/--qa-time require --prepared-scene')
    try:
        if args.selfcheck:
            result = self_check()
        elif not args.preview and not args.prepared_scene:
            # Resolve diagnostics before a frozen production launch selects its
            # writable runtime directory. The game itself owns all save I/O.
            args.report = args.report.resolve()
            return _main_game(args)
        else:
            width, height = (int(value) for value in args.size.lower().split('x'))
            if args.preview:
                from tools.worldseed_gpu_playtest import run
                result = run(scene=args.preview, width=width, height=height,
                             frames=args.frames, screenshot=args.screenshot, report=args.report)
            else:
                from tools.worldseed_gpu_gameplay import run
                settings = dict(width=width, height=height, frames=args.frames, seed=args.seed,
                                prepared_scene=args.prepared_scene,
                                screenshot=args.screenshot, report=args.report)
                if args.qa_weather is not None:
                    settings['qa_weather'] = args.qa_weather
                if args.qa_season is not None:
                    settings['qa_season'] = args.qa_season
                if args.qa_time is not None:
                    settings['qa_time'] = args.qa_time
                result = run(**settings)
        print(json.dumps(result, indent=2), flush=True)
        return 0
    except Exception as exc:
        from worldseed.presentation.gl_worldspace import GPUBackendUnavailable
        unavailable = isinstance(exc, GPUBackendUnavailable)
        result = {'status': 'gpu-candidate-unavailable' if unavailable else 'gpu-candidate-error',
                  'error_type': type(exc).__name__, 'error': str(exc),
                  'player_saves_opened': False if args.smoke_main or args.prepared_scene or args.preview else None,
                  'native_hardware_accepted': False,
                  'note': 'Requires a desktop OpenGL 3.3+ driver. Update your graphics driver. '
                          'This executable does not silently switch renderers. '
                          'Normal startup supports persistent worlds; QA scenes are temporary.'}
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        args.report.with_suffix('.error.log').write_text(traceback.format_exc(), encoding='utf-8')
        print(json.dumps(result, indent=2), flush=True)
        print('Startup evidence: ' + str(args.report.resolve()), file=sys.stderr, flush=True)
        return 3 if unavailable else 1


if __name__ == '__main__':
    raise SystemExit(main())
