from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import struct
import zlib
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worldseed.config import DATA_DIR, WORLDGEN_VERSION
from worldseed.content.registry import ContentRegistry
from worldseed.world.generator import WorldGenerator
from worldseed.world.hydrology import HydrologyGenerator, audit_domain


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack('>I', len(payload)) + kind + payload + struct.pack('>I', zlib.crc32(kind + payload) & 0xFFFFFFFF)


def write_png(path: Path, width: int, height: int, rgb: bytes, scale: int = 4) -> None:
    sw, sh = width * scale, height * scale
    rows = []
    for y in range(height):
        row = rgb[y * width * 3:(y + 1) * width * 3]
        expanded = bytearray()
        for x in range(width):
            px = row[x * 3:x * 3 + 3]
            expanded.extend(px * scale)
        scan = b'\x00' + bytes(expanded)
        rows.extend([scan] * scale)
    data = b''.join(rows)
    out = b'\x89PNG\r\n\x1a\n'
    out += _png_chunk(b'IHDR', struct.pack('>IIBBBBB', sw, sh, 8, 2, 0, 0, 0))
    out += _png_chunk(b'IDAT', zlib.compress(data, 9))
    out += _png_chunk(b'IEND', b'')
    path.write_bytes(out)


def render_domain(domain) -> bytes:
    lo = min(domain.elevation); hi = max(domain.elevation); span = max(1, hi - lo)
    pixels = bytearray()
    for i, elev in enumerate(domain.elevation):
        gray = 38 + ((elev - lo) * 150 // span)
        cls = domain.river_class[i]
        flood = domain.floodplain_strength[i]
        if cls == 3:
            rgb = (32, 96, 180)
        elif cls == 2:
            rgb = (46, 122, 196)
        elif cls == 1:
            rgb = (72, 148, 208)
        elif flood > 0:
            rgb = (max(25, gray - 24), min(210, gray + 22), max(35, gray - 12))
        else:
            rgb = (gray, gray, gray)
        pixels.extend(rgb)
    return bytes(pixels)


def main() -> int:
    ap = argparse.ArgumentParser(description='RC14 deterministic hydrology audit/debug export')
    ap.add_argument('--seed', default='rc14-hydrology-audit')
    ap.add_argument('--domain-x', type=int, default=0)
    ap.add_argument('--domain-y', type=int, default=0)
    ap.add_argument('--out-dir', type=Path, default=Path('artifacts/hydrology'))
    args = ap.parse_args()

    registry = ContentRegistry.load(DATA_DIR)
    seed = args.seed.encode('utf-8')
    generator = WorldGenerator(seed, registry, version=WORLDGEN_VERSION)
    domain = HydrologyGenerator(generator).generate(args.domain_x, args.domain_y)
    issues = audit_domain(domain)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    stem = f'{args.seed}_d{args.domain_x}_{args.domain_y}'
    csv_path = args.out_dir / f'{stem}.csv'
    with csv_path.open('w', newline='', encoding='utf-8') as fh:
        writer = csv.writer(fh)
        writer.writerow(['global_node_x','global_node_y','world_x','world_y','elevation','filled_elevation','flow_to','accumulation','watershed_id','river_class','floodplain_strength'])
        for i in range(domain.width * domain.height):
            gx, gy = domain.global_node_xy(i); wx, wy = domain.world_xy(i)
            writer.writerow([gx, gy, wx, wy, domain.elevation[i], domain.filled_elevation[i], domain.flow_to[i], domain.accumulation[i], domain.watershed_id[i], domain.river_class[i], domain.floodplain_strength[i]])

    png_path = args.out_dir / f'{stem}.png'
    write_png(png_path, domain.width, domain.height, render_domain(domain))
    report = {
        'seed': args.seed,
        'worldgen_version': WORLDGEN_VERSION,
        'hydrology_version': domain.version,
        'domain': [domain.domain_x, domain.domain_y],
        'fingerprint': domain.fingerprint,
        'nodes': domain.width * domain.height,
        'core_nodes': domain.core_nodes * domain.core_nodes,
        'outlets': len(domain.outlets),
        'river_cells_core': sum(1 for i in domain.core_indices() if domain.river_class[i] > 0),
        'river_class_core': {str(c): sum(1 for i in domain.core_indices() if domain.river_class[i] == c) for c in range(4)},
        'issues': issues,
        'csv': str(csv_path),
        'png': str(png_path),
    }
    report_path = args.out_dir / f'{stem}.json'
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding='utf-8')
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if issues else 0


if __name__ == '__main__':
    raise SystemExit(main())
