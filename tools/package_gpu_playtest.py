"""Build the self-contained Windows full-game GPU test distribution."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NAME = 'WORLDSEED_GPU'
LAUNCHERS = ('PLAY_WORLDSEED_GPU.bat', 'PLAY_GPU_NEW_WORLD.bat', 'PLAY_GPU_CAMP_RAIN.bat',
             'PLAY_GPU_VILLAGE.bat', 'PREVIEW_GPU_WEATHER.bat')
SUPPORT_FILES = ('OPEN_LOGS.bat',)
FIXED_ZIP_TIME = (2026, 1, 1, 0, 0, 0)


def build_command(output: Path, work: Path) -> list[str]:
    return [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir',
            '--console', '--noupx', '--name', NAME, '--contents-directory', '_internal',
            '--distpath', str(output), '--workpath', str(work / 'build'),
            '--specpath', str(work), '--paths', str(ROOT),
            '--add-data', str(ROOT / 'worldseed' / 'data') + ';worldseed/data',
            '--add-data', str(ROOT / 'worldseed' / 'assets') + ';worldseed/assets',
            '--collect-submodules', 'worldseed',
            '--collect-all', 'moderngl', '--collect-all', 'glcontext',
            '--copy-metadata', 'glcontext', '--copy-metadata', 'moderngl',
            '--copy-metadata', 'pygame-ce', '--hidden-import', 'glcontext.wgl',
            '--hidden-import', '_moderngl', '--hidden-import', 'worldseed.app',
            '--hidden-import', 'worldseed.ui.gpu_terminal', str(ROOT / 'run_worldseed_gpu.py')]


def validate_bundle(directory: Path, *, minimum_exe_bytes=1048576) -> dict:
    directory = Path(directory)
    required = (NAME + '.exe', 'GPU_BUILD.json', 'README_GPU_TEST.txt', *LAUNCHERS, *SUPPORT_FILES,
                '_internal/worldseed/data/terrain.json',
                '_internal/worldseed/assets/shaders/worldspace_sprite.vert',
                '_internal/worldseed/assets/shaders/worldspace_sprite.frag',
                '_internal/worldseed/assets/shaders/worldspace_post.vert',
                '_internal/worldseed/assets/shaders/worldspace_post.frag',
                '_internal/worldseed/assets/sprites/ui/gpu_controls/manifest.json',
                '_internal/worldseed/assets/sprites/worldspace/trees/manifest.json',
                '_internal/worldseed/assets/sprites/worldspace/trees/tree_layers.b85')
    missing = [name for name in required if not (directory / name).is_file()]
    if missing:
        raise ValueError('GPU distribution missing: ' + ', '.join(missing))
    if (directory / (NAME + '.exe')).stat().st_size < minimum_exe_bytes:
        raise ValueError('GPU executable is empty or unusually small')
    identity = json.loads((directory / 'GPU_BUILD.json').read_text(encoding='utf-8'))
    if not re.fullmatch('[0-9a-f]{40}', str(identity.get('commit', ''))):
        raise ValueError('GPU build needs exact commit SHA')
    if identity.get('build_kind') != 'windows-gpu-candidate-one-dir':
        raise ValueError('GPU candidate identity mismatch')
    if (identity.get('default_entrypoint') != 'worldseed.app.main'
            or identity.get('default_backend') != 'gpu'
            or identity.get('existing_saves_supported') is not True):
        raise ValueError('GPU test distribution must launch the persistent main game')
    for launcher in LAUNCHERS:
        if NAME + '.exe' not in (directory / launcher).read_text(encoding='utf-8'):
            raise ValueError('Launcher does not target GPU executable: ' + launcher)
    forbidden = {'saves', '.git', '__pycache__', 'playtest_reports'}
    leaked = [path for path in directory.rglob('*')
              if forbidden.intersection(path.relative_to(directory).parts)
              or path.suffix.lower() in ('.db', '.db-wal', '.db-shm')]
    if leaked:
        raise ValueError('GPU bundle contains runtime/development state: ' + str(leaked[0]))
    return {'schema': 'worldseed-gpu-bundle-v2', 'commit': identity['commit'],
            'build_kind': identity['build_kind'], 'executable': NAME + '.exe',
            'default_entrypoint': identity['default_entrypoint'],
            'existing_saves_supported': True,
            'native_hardware_accepted': False}


def write_archive(directory: Path, destination: Path) -> str:
    """Package only the verified one-dir output, preserving a stable file order."""
    validate_bundle(directory)
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(directory.rglob('*')):
            if not path.is_file():
                continue
            name = NAME + '/' + path.relative_to(directory).as_posix()
            entry = zipfile.ZipInfo(name, FIXED_ZIP_TIME)
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            with archive.open(entry, 'w') as output, path.open('rb') as source:
                shutil.copyfileobj(source, output, 1024 * 1024)
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise RuntimeError('GPU package ZIP integrity check failed')
    digest = hashlib.sha256()
    with destination.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    sha = digest.hexdigest()
    destination.with_suffix('.zip.sha256').write_text(sha + '  ' + destination.name + '\n',
                                                   encoding='utf-8')
    return sha


def build(output: Path, commit: str) -> Path:
    if sys.platform != 'win32':
        raise RuntimeError('A real Windows x64 runner is required to create the Windows EXE')
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('--commit must be an exact Git commit SHA')
    output = output.resolve()
    directory = output / NAME
    if directory.exists():
        raise ValueError('Use a clean output directory; GPU bundle already exists')
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='worldseed-gpu-build-') as work:
        subprocess.run(build_command(output, Path(work)), cwd=ROOT, check=True, timeout=900)
    for name in (*LAUNCHERS, *SUPPORT_FILES, 'README_GPU_TEST.txt'):
        shutil.copyfile(ROOT / 'packaging' / 'windows_gpu' / name, directory / name)
    (directory / 'GPU_BUILD.json').write_text(json.dumps({
        'commit': commit, 'build_kind': 'windows-gpu-candidate-one-dir',
        'native_hardware_accepted': False, 'existing_saves_supported': True,
        'default_entrypoint': 'worldseed.app.main', 'default_backend': 'gpu',
        'save_location': '%LOCALAPPDATA%/WORLDSEED/saves',
    }, indent=2) + '\n', encoding='utf-8')
    evidence = validate_bundle(directory)
    (directory / 'BUNDLE_VERIFY.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    return directory


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'dist')
    parser.add_argument('--commit', required=True)
    parser.add_argument('--archive-only', action='store_true',
                        help='Verify/archive an already built and smoke-tested directory')
    parser.add_argument('--build-only', action='store_true',
                        help='Build/verify; defer archive creation until executable smoke passes')
    args = parser.parse_args(argv)
    if args.archive_only and args.build_only:
        parser.error('--archive-only and --build-only are mutually exclusive')
    directory = args.output_dir / NAME if args.archive_only else build(args.output_dir, args.commit)
    evidence = validate_bundle(directory)
    if evidence['commit'] != args.commit:
        parser.error('--commit does not match the bundled identity')
    if args.build_only:
        print(json.dumps(evidence, indent=2))
        return 0
    destination = args.output_dir / ('WORLDSEED-Windows-GPU-CANDIDATE-' + args.commit[:8] + '.zip')
    sha = write_archive(directory, destination)
    print(json.dumps({'directory': str(directory), 'zip': str(destination), 'sha256': sha}, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
