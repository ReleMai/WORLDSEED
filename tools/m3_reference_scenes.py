"""Capture four deterministic M3 QA scenes and verify pixel stability.

These are synthetic production-renderer fixtures, NOT artist-approved scenes.
The reviewer must approve candidate hashes before they may be a golden baseline.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

SCENES = ('forest', 'camp', 'village_street', 'interior')
SCHEMA = 'worldseed-m3-reference-v1'
PROVENANCE = ('fixture_version', 'seed', 'size', 'zoom_tile_px',
              'pygame', 'driver', 'headless')


def build_manifest(reports: list[dict]) -> dict:
    """Fail closed for incomplete, interrupted, or world-mutating captures."""
    names = [row.get('scene') for row in reports]
    if len(names) != len(SCENES) or set(names) != set(SCENES):
        raise ValueError('exactly one report per required M3 scene is needed')
    by_name = {row['scene']: row for row in reports}
    first = by_name[SCENES[0]]
    for name in SCENES:
        row = by_name[name]
        if any(row.get(key) != first.get(key) for key in PROVENANCE):
            raise ValueError('incompatible reference settings for ' + name)
        if row.get('fixture_mode') != 'prepared-synthetic-qa':
            raise ValueError('non-reference fixture for ' + name)
        if not row.get('authority_unchanged') or row.get('interrupted'):
            raise ValueError('interrupted or authoritative-state-mutating scene: ' + name)
        if int(row.get('frames_measured') or 0) < 1:
            raise ValueError('unmeasured reference: ' + name)
        if not re.fullmatch(r'[0-9a-f]{64}', str(row.get('pixel_sha256') or '')):
            raise ValueError('missing RGB pixel digest for ' + name)
        if Path(str(row.get('png') or '')).name != name + '.png':
            raise ValueError('missing or incorrectly named PNG for ' + name)
    return {
        'schema': SCHEMA, 'status': 'candidate-unreviewed',
        **{key: first[key] for key in PROVENANCE},
        'scenes': {name: {
            'pixel_sha256': by_name[name]['pixel_sha256'],
            'authority_fingerprint': by_name[name].get('authority_fingerprint'),
            'png': 'pass-1/' + name + '.png',
        } for name in SCENES},
        'note': 'RGB surface hashes, not PNG file hashes; manual art review required',
    }


def compare_manifests(actual: dict, expected: dict, *, require_reviewed: bool = True) -> list[str]:
    """Report exact differences; never silently replace a reviewed baseline."""
    errors = []
    if expected.get('schema') != SCHEMA or actual.get('schema') != SCHEMA:
        errors.append('unsupported manifest schema')
    if require_reviewed and expected.get('status') != 'approved':
        errors.append('comparison baseline has not been explicitly approved')
    for key in PROVENANCE:
        if actual.get(key) != expected.get(key):
            errors.append(key + ' changed')
    if set(actual.get('scenes', {})) != set(SCENES) or set(expected.get('scenes', {})) != set(SCENES):
        errors.append('four-scene coverage differs')
    for name in SCENES:
        current = actual.get('scenes', {}).get(name, {})
        baseline = expected.get('scenes', {}).get(name, {})
        for key in ('pixel_sha256', 'authority_fingerprint'):
            if current.get(key) != baseline.get(key):
                errors.append(name + ': ' + key + ' differs')
    return errors


def capture_suite(output_dir: Path, runner, *, passes: int = 2) -> dict:
    """Capture one or two independent fixture runs; runner is injectable for tests."""
    if passes not in (1, 2):
        raise ValueError('only one or two bounded passes supported')
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    reference = None
    for attempt in range(1, passes + 1):
        directory = output_dir / ('pass-' + str(attempt))
        directory.mkdir(parents=True, exist_ok=True)
        reports = []
        for scene in SCENES:
            row = runner(scene, directory)
            if not (directory / (scene + '.png')).is_file():
                raise ValueError('missing PNG written for ' + scene)
            reports.append(row)
        candidate = build_manifest(reports)
        if reference is None:
            reference = candidate
        else:
            mismatches = compare_manifests(candidate, reference, require_reviewed=False)
            if mismatches:
                raise ValueError('repeat scene instability: ' + '; '.join(mismatches))
    assert reference is not None
    reference['passes_verified'] = passes
    target = output_dir / 'candidate-manifest.json'
    target.write_text(json.dumps(reference, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return reference


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--compare', type=Path, help='reviewer-approved baseline manifest')
    parser.add_argument('--frames', type=int, default=2)
    parser.add_argument('--warmup', type=int, default=1)
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--height', type=int, default=720)
    parser.add_argument('--zoom', type=int, default=28)
    parser.add_argument('--seed', default='worldseed-reference-v1')
    parser.add_argument('--passes', type=int, default=2)
    parser.add_argument('--headless', action='store_true')
    args = parser.parse_args(argv)
    if args.passes not in (1, 2):
        parser.error('passes must be 1 or 2')
    from tools.reference_scenes import run_scene, validate_settings
    try:
        validate_settings(frames=args.frames, warmup=args.warmup, width=args.width,
                          height=args.height, zoom=args.zoom, distant_npcs=0,
                          seed=args.seed)
    except ValueError as exc:
        parser.error(str(exc))
    from worldseed.config import DATA_DIR
    from worldseed.content.registry import ContentRegistry
    registry = ContentRegistry.load(DATA_DIR)

    def run_one(name, folder):
        print('M3_CAPTURE ' + name, flush=True)
        return run_scene(name, output_dir=folder, frames=args.frames,
                         warmup=args.warmup, width=args.width, height=args.height,
                         zoom=args.zoom, seed=args.seed, png=True,
                         headless=args.headless, registry=registry)
    manifest = capture_suite(args.output_dir, run_one, passes=args.passes)
    if args.compare:
        baseline = json.loads(args.compare.read_text(encoding='utf-8'))
        changes = compare_manifests(manifest, baseline)
        if changes:
            for issue in changes:
                print('M3_VISUAL_MISMATCH ' + issue, flush=True)
            return 1
    print('M3_REFERENCE_MANIFEST ' + str(args.output_dir / 'candidate-manifest.json'), flush=True)
    print('M3_REFERENCE_SCENES ' + ','.join(SCENES), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
