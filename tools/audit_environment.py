"""Audit Phase 4 derived fields and write an exact, seed-grounded map preview."""
from __future__ import annotations

import argparse
import base64
from dataclasses import asdict
from hashlib import blake2b
from html import escape
import json
from pathlib import Path
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.audit_phase3_geography import PALETTE, write_png
from worldseed.config import DATA_DIR, ENVIRONMENT_VERSION
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.world.generator import WorldGenerator
from worldseed.world.hydrology import HydrologyGenerator, audit_window_seams

FIELDS = ('slope', 'relief', 'soil_fertility', 'wetness', 'drainage', 'flood_risk', 'resource_opportunity', 'farmland')


def audit(seed: str, radius: int, step: int, out: Path, registry) -> dict:
    gen = WorldGenerator(seed.encode(), registry, version=5)
    hydro = HydrologyGenerator(gen); gen.attach_hydrology(hydro)
    domains = hydro.prepare_world_bounds(-radius, -radius, radius - 1, radius - 1, persist=False)
    seams = audit_window_seams(domains)
    samples = []; layers = {name: bytearray() for name in ('terrain', *FIELDS)}
    coords = list(range(-radius, radius, step)); fingerprint = blake2b(digest_size=16)
    issues = list(seams); values = {name: [] for name in FIELDS}
    started = perf_counter()
    for y in coords:
        for x in coords:
            p = WorldPos(x, y, 0); f = gen.environment_at(p)
            if f is None:
                issues.append(f'missing prepared sample {x},{y}'); continue
            samples.append((p, f))
            fingerprint.update(json.dumps(asdict(f), sort_keys=True, separators=(',', ':')).encode())
            layers['terrain'].extend(PALETTE.get(gen.terrain_at(p), (90, 95, 84)))
            for name in FIELDS:
                v = getattr(f, name); values[name].append(v)
                if not 0 <= v <= 100: issues.append(f'out of bounds: {name} at {x},{y}')
                # Dark indigo (0) to pale gold (100), shared numeric scale.
                layers[name].extend((30 + v * 220 // 100, 42 + v * 180 // 100, 72 + v * 38 // 100))
            if f.open_water and (f.farmland or f.resources.timber or f.resources.forage):
                issues.append(f'land resource on open water at {x},{y}')
    cold_ms = (perf_counter() - started) * 1000 / max(1, len(samples))
    # Each sampled point has just been queried; warm a bounded subset before
    # timing pure reads, so the benchmark never disguises LRU evictions.
    warm = samples[-min(len(samples), 4096):]
    for p, _ in warm: gen.environment_at(p)
    started = perf_counter()
    for p, expected in reversed(warm):
        if gen.environment_at(p) != expected: issues.append('query-order instability')
    warm_us = (perf_counter() - started) * 1000000 / max(1, len(warm))
    out.mkdir(parents=True, exist_ok=True)
    safe_seed = ''.join(c if c.isalnum() or c in '-_' else '_' for c in seed)[:80] or 'seed'
    svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="930" height="1070" viewBox="0 0 930 1070">',
           '<rect width="930" height="1070" fill="#111820"/>',
           '<g font-family="sans-serif" fill="#edf0e9">',
           '<text x="28" y="38" font-size="25">WORLDSEED / Environmental geography</text>',
           f'<text x="28" y="64" font-size="14">{escape(seed)} · worldgen 5 · environmental fields {ENVIRONMENT_VERSION}</text>']
    for i, name in enumerate(layers):
        png = out / f'{safe_seed}_{name}.png'
        write_png(png, len(coords), len(coords), bytes(layers[name]))
        data = base64.b64encode(png.read_bytes()).decode(); png.unlink()
        x, y = 28 + (i % 3) * 302, 102 + (i // 3) * 290
        svg.append(f'<text x="{x}" y="{y}" font-size="17">{name.replace("_", " ").title()}</text>')
        svg.append(f'<image x="{x}" y="{y+12}" width="250" height="250" preserveAspectRatio="none" style="image-rendering:pixelated" href="data:image/png;base64,{data}"/>')
    svg.extend([f'<text x="28" y="998" font-size="14">Each map: x/y −{radius} to {radius-1}; one sample per {step} cells. North is up.</text>',
                '<text x="28" y="1023" font-size="14">Scores: dark indigo = 0, pale gold = 100. Natural potential, not current stocks or crop yields.</text>',
                '<text x="28" y="1048" font-size="14">Slope and relief use game indices; water is excluded from farmland and terrestrial resources.</text>', '</g></svg>'])
    (out / f'{safe_seed}_environment.svg').write_text('\n'.join(svg), encoding='utf-8')
    report = {'seed': seed, 'environment_version': ENVIRONMENT_VERSION, 'samples': len(samples),
              'domains': len(domains), 'issues': issues, 'fingerprint': fingerprint.hexdigest(),
              'sample_and_terrain_ms': cold_ms, 'cached_read_us': warm_us,
              'fields': {name: {'min': min(v), 'max': max(v), 'mean': round(sum(v)/len(v), 2)} for name, v in values.items()}}
    (out / f'{safe_seed}_environment.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seeds', nargs='+', default=['rc14-golden-00', 'rc14-golden-01', 'rc14-golden-02'])
    parser.add_argument('--radius', type=int, default=128)
    parser.add_argument('--step', type=int, default=4)
    parser.add_argument('--out-dir', type=Path, default=Path('artifacts/phase4'))
    args = parser.parse_args()
    if args.radius <= 0 or args.step <= 0: parser.error('radius and step must be positive')
    registry = ContentRegistry.load(DATA_DIR)
    reports = [audit(seed, args.radius, args.step, args.out_dir, registry) for seed in args.seeds]
    print(json.dumps(reports, indent=2))
    return int(any(r['issues'] for r in reports))


if __name__ == '__main__':
    raise SystemExit(main())
