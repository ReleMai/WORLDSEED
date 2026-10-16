"""Separate Windows GPU candidate launcher; never opens an existing player save."""
from __future__ import annotations

import argparse
from importlib.metadata import version
from io import BytesIO
import json
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
               'worldspace_post.vert', 'worldspace_post.frag')
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
    # These imports must survive freezing, including the QA namespace package.
    from tools import reference_scene_fixtures, worldseed_gpu_gameplay, worldseed_gpu_playtest
    return {'status': 'gpu-bundle-selfcheck-ok', 'engine': ENGINE_VERSION,
            'pygame': pg.version.ver, 'moderngl': moderngl.__version__,
            'glcontext': version('glcontext'), 'items': len(registry.items),
            'terrains': len(registry.terrains), 'tree_layers': tree_layers,
            'shaders': len(shaders), 'player_saves_opened': False,
            'native_hardware_accepted': False,
            'note': 'Packaging/import check only; no OpenGL context was created.'}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selfcheck', action='store_true')
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
    parser.add_argument('--report', type=Path, default=Path('logs/gpu-session.json'))
    args = parser.parse_args(argv)
    if (args.qa_weather or args.qa_season or args.qa_time) and not args.prepared_scene:
        parser.error('--qa-weather/--qa-season/--qa-time require --prepared-scene')
    try:
        if args.selfcheck:
            result = self_check()
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
                  'player_saves_opened': False, 'native_hardware_accepted': False,
                  'note': 'Requires a desktop OpenGL 3.3+ driver. Update your graphics driver. '
                          'This candidate does not switch renderers or open existing saves.'}
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        args.report.with_suffix('.error.log').write_text(traceback.format_exc(), encoding='utf-8')
        print(json.dumps(result, indent=2), flush=True)
        print('Startup evidence: ' + str(args.report.resolve()), file=sys.stderr, flush=True)
        return 3 if unavailable else 1


if __name__ == '__main__':
    raise SystemExit(main())
