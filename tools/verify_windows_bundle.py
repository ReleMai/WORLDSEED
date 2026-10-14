"""Validate the exact Windows one-directory artifact before GitHub upload.

This is intentionally a packaging-only verification. It does not launch the
game, test graphics hardware, contact external services, or change saves.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


REQUIRED_FILES = (
    'WORLDSEED.exe', 'PLAY_WORLDSEED_TEST.bat',
    'EXPORT_WORLDSEED_REPORT.bat', 'README_PLAYTEST.txt',
    'PLAYTEST_BUILD.json',
)


def validate_bundle(directory: Path, *, minimum_exe_bytes: int = 1048576) -> dict:
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError('Windows distribution directory missing')
    missing = [name for name in REQUIRED_FILES if not (directory / name).is_file()]
    if not (directory / '_internal').is_dir():
        missing.append('_internal/')
    if missing:
        raise ValueError('Windows executable distribution missing: ' + ', '.join(missing))
    exe = directory / 'WORLDSEED.exe'
    if exe.stat().st_size < minimum_exe_bytes:
        raise ValueError('WORLDSEED.exe is empty or unusually small')
    if not any((directory / '_internal').rglob('*.*')):
        raise ValueError('PyInstaller _internal data/dependencies missing')
    try:
        identity = json.loads((directory / 'PLAYTEST_BUILD.json').read_text(encoding='utf-8-sig'))
    except (ValueError, OSError) as exc:
        raise ValueError('PLAYTEST_BUILD.json missing/invalid') from exc
    commit = str(identity.get('commit', ''))
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('build identity must be an exact Git commit SHA')
    if identity.get('build_kind') != 'windows-one-dir':
        raise ValueError('build identity is not the Windows standalone distribution')
    for name in ('PLAY_WORLDSEED_TEST.bat', 'EXPORT_WORLDSEED_REPORT.bat'):
        content = (directory / name).read_text(encoding='utf-8')
        if 'WORLDSEED.exe' not in content:
            raise ValueError(name + ' does not target the Windows executable')
    digest = hashlib.sha256()
    with exe.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return {
        'schema': 'worldseed-windows-bundle-v1',
        'commit': commit,
        'build_kind': identity['build_kind'],
        'executable': 'WORLDSEED.exe',
        'exe_size_bytes': exe.stat().st_size,
        'exe_sha256': digest.hexdigest(),
        'launchers': ['PLAY_WORLDSEED_TEST.bat', 'EXPORT_WORLDSEED_REPORT.bat'],
        'dependencies': '_internal/',
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args(argv)
    try:
        evidence = validate_bundle(args.directory)
    except ValueError as exc:
        parser.exit(2, 'WINDOWS_BUNDLE_VERIFY_FAILED: ' + str(exc) + '\n')
    path = args.directory / 'BUNDLE_VERIFY.json'
    path.write_text(json.dumps(evidence, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    print('WINDOWS_BUNDLE_VERIFIED ' + json.dumps(evidence, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
