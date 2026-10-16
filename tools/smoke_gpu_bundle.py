"""Launch the actual frozen candidate, separating packaging from GL acceptance."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess


def unsupported_context(report: dict, context: dict, returncode: int) -> bool:
    """Only an observed insufficient current GL version is a graceful rejection."""
    if (returncode != 3 or report.get('status') != 'gpu-candidate-unavailable'
            or report.get('error_type') != 'GPUBackendUnavailable'
            or context.get('stage') != 'rejected'):
        return False
    events = context.get('events', ())
    preflight = next((row.get('evidence', {}) for row in events
                      if row.get('stage') == 'preflight'), {})
    native = preflight.get('native', {})
    match = re.match(r'^\s*(\d+)\.(\d+)', native.get('version') or '')
    return bool(native.get('current_context') and match
                and int(match[1]) * 100 + int(match[2]) * 10 < 330)


def smoke(executable: Path, output: Path) -> dict:
    executable = executable.resolve()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    statuses = {}
    for mode, arguments in (
        ('selfcheck', ['--selfcheck']),
        ('main', ['--smoke-main', '--frames', '2',
                  '--report', str(output / 'main.json'),
                  '--screenshot', str(output / 'main.png')]),
        ('render', ['--prepared-scene', 'camp', '--qa-weather', 'rain',
                    '--qa-season', 'autumn', '--qa-time', 'sunset', '--frames', '2',
                    '--report', str(output / 'render.json'),
                    '--screenshot', str(output / 'render.png')]),
    ):
        if mode != 'selfcheck':
            # A repeated smoke must validate this child, not a previous run's
            # retained screenshot or successful report.
            for suffix in ('.json', '.context.json', '.png'):
                (output / (mode + suffix)).unlink(missing_ok=True)
        child = subprocess.run([str(executable), *arguments], cwd=output,
                               text=True, capture_output=True, timeout=180, check=False)
        (output / (mode + '.stdout.log')).write_text(child.stdout, encoding='utf-8')
        (output / (mode + '.stderr.log')).write_text(child.stderr, encoding='utf-8')
        if mode == 'selfcheck':
            if child.returncode or '"status": "gpu-bundle-selfcheck-ok"' not in child.stdout:
                raise RuntimeError('Actual frozen executable failed dependency/data selfcheck')
            continue
        report = json.loads((output / (mode + '.json')).read_text(encoding='utf-8'))
        context = json.loads((output / (mode + '.context.json')).read_text(encoding='utf-8'))
        if child.returncode == 0:
            frame_count = report.get('render_frames') if mode == 'main' else report.get('frames')
            if (frame_count != 2 or context.get('stage') != 'ready'
                    or not (output / (mode + '.png')).is_file()):
                raise RuntimeError('Executable returned success without real render evidence')
            if mode == 'main' and (report.get('source') != 'main-game'
                                   or not report.get('saved_world_support')):
                raise RuntimeError('Main startup smoke did not use the full-game backend')
            status = 'rendered-current-driver'
        elif unsupported_context(report, context, child.returncode):
            status = 'unsupported-hosted-driver-rejected'
        else:
            raise RuntimeError('Frozen rendering failed beyond a diagnosed insufficient GL context; '
                               'see retained smoke logs')
        statuses[mode] = status
    result = {'schema': 'worldseed-gpu-executable-smoke-v2',
              'packaging_selfcheck': 'passed', 'render_status': status,
              'main_game_startup': statuses['main'],
              'qa_render_status': statuses['render'],
              'native_hardware_accepted': False,
              'note': 'Main-menu startup and secondary QA rendering are probed separately. '
                      'This smoke does not load a save or exercise every gameplay screen. '
                      'Executable packaging is verified. Unsupported-driver rejection is not '
                      'rendering success. Rendering/CPU samples alone do not certify hardware.'}
    (output / 'SMOKE_RESULT.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(smoke(args.executable, args.output_dir), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
