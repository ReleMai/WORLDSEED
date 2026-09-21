from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
TERRAIN_DIR = ROOT / 'worldseed' / 'assets' / 'sprites' / 'terrain'
VISUALS_PATH = ROOT / 'worldseed' / 'assets' / 'visuals.json'
PREVIEW_PATH = ROOT / 'artifacts' / 'terrain-variant-preview.png'
VARIANT_COUNT = 10
SIZE = 128


@dataclass(frozen=True)
class TerrainStyle:
    base: tuple[int, int, int]
    dark: tuple[int, int, int]
    light: tuple[int, int, int]
    accent: tuple[int, int, int]
    accent2: tuple[int, int, int]


STYLES: Dict[str, TerrainStyle] = {
    'core:grass': TerrainStyle((104, 119, 55), (70, 84, 37), (151, 156, 83), (92, 121, 44), (181, 168, 95)),
    'core:forest': TerrainStyle((67, 81, 47), (35, 47, 30), (116, 129, 79), (144, 105, 61), (90, 112, 52)),
    'core:scrub': TerrainStyle((120, 121, 68), (83, 81, 46), (169, 162, 102), (102, 118, 51), (126, 98, 59)),
    'core:sand': TerrainStyle((203, 183, 133), (170, 149, 102), (229, 210, 162), (138, 126, 86), (117, 132, 79)),
    'core:rock': TerrainStyle((108, 108, 106), (72, 74, 74), (152, 151, 147), (126, 118, 102), (90, 94, 101)),
    'core:tundra': TerrainStyle((191, 188, 173), (133, 129, 116), (228, 228, 220), (144, 146, 118), (109, 116, 98)),
    'core:wetland': TerrainStyle((82, 95, 69), (49, 61, 44), (121, 133, 93), (78, 99, 80), (111, 88, 60)),
    'core:water': TerrainStyle((34, 110, 150), (17, 68, 104), (83, 157, 193), (163, 216, 227), (28, 96, 127)),
    'core:river': TerrainStyle((42, 116, 153), (22, 74, 104), (96, 164, 196), (177, 220, 228), (36, 102, 136)),
    'core:river_shallow': TerrainStyle((68, 128, 149), (37, 90, 102), (124, 175, 189), (196, 225, 220), (180, 181, 136)),
    'core:floodplain': TerrainStyle((173, 163, 121), (130, 120, 84), (206, 196, 154), (158, 145, 104), (118, 129, 90)),
    'core:tilled_soil': TerrainStyle((118, 81, 49), (82, 52, 29), (151, 109, 68), (92, 65, 39), (165, 123, 80)),
    'core:cave_floor': TerrainStyle((96, 90, 83), (63, 58, 52), (136, 130, 123), (117, 103, 88), (80, 85, 89)),
    'core:berry_thicket': TerrainStyle((76, 96, 50), (44, 62, 31), (123, 140, 74), (145, 42, 50), (92, 114, 53)),
}

TERRAIN_OUTPUTS: Dict[str, str] = {
    'core:grass': 'grass_hd',
    'core:forest': 'forest_hd',
    'core:scrub': 'scrub_hd',
    'core:sand': 'sand_hd',
    'core:rock': 'rock_hd',
    'core:tundra': 'tundra_hd',
    'core:wetland': 'wetland_hd',
    'core:water': 'water_hd',
    'core:river': 'river_hd',
    'core:river_shallow': 'river_shallow_hd',
    'core:floodplain': 'floodplain_hd',
    'core:tilled_soil': 'tilled_soil_hd',
    'core:cave_floor': 'cave_floor',
    'core:berry_thicket': 'berry_thicket',
}


def mix(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return tuple(int(round(x * (1.0 - t) + y * t)) for x, y in zip(a, b))


def clamp(n: float) -> int:
    return max(0, min(255, int(round(n))))


def shade(color: tuple[int, int, int], delta: float) -> tuple[int, int, int]:
    return tuple(clamp(c + delta) for c in color)


def tileable_noise(seed: int, coarse: int) -> Image.Image:
    rng = random.Random(seed)
    img = Image.new('L', (coarse + 1, coarse + 1))
    px = img.load()
    first_col = [rng.randint(0, 255) for _ in range(coarse)]
    first_row = []
    for y in range(coarse):
        row = []
        for x in range(coarse):
            v = rng.randint(0, 255)
            px[x, y] = v
            row.append(v)
        first_row = row if y == 0 else first_row
        px[coarse, y] = row[0]
    for x in range(coarse):
        px[x, coarse] = first_row[x]
    px[coarse, coarse] = first_row[0]
    return img.resize((SIZE + 1, SIZE + 1), Image.Resampling.BICUBIC).crop((0, 0, SIZE, SIZE))


def base_texture(style: TerrainStyle, seed: int) -> Image.Image:
    n1 = tileable_noise(seed + 101, 14)
    n2 = tileable_noise(seed + 211, 32)
    n3 = tileable_noise(seed + 307, 8)
    out = Image.new('RGBA', (SIZE, SIZE))
    p1, p2, p3, dst = n1.load(), n2.load(), n3.load(), out.load()
    for y in range(SIZE):
        for x in range(SIZE):
            v1 = p1[x, y] / 255.0
            v2 = p2[x, y] / 255.0
            v3 = p3[x, y] / 255.0
            low = mix(style.dark, style.base, v1)
            high = mix(style.base, style.light, v2)
            color = mix(low, high, 0.5)
            color = mix(color, style.accent, v3 * 0.18)
            delta = (v2 - 0.5) * 18 + (v1 - 0.5) * 14
            dst[x, y] = (*shade(color, delta), 255)
    return out


def _wrapped_positions(x: int, y: int):
    for ox in (-SIZE, 0, SIZE):
        for oy in (-SIZE, 0, SIZE):
            yield x + ox, y + oy


def scatter_ellipse(img: Image.Image, x: int, y: int, rx: int, ry: int, fill, outline=None):
    draw = ImageDraw.Draw(img)
    for px, py in _wrapped_positions(x, y):
        draw.ellipse((px - rx, py - ry, px + rx, py + ry), fill=fill, outline=outline)


def scatter_line(img: Image.Image, points, fill, width=1):
    draw = ImageDraw.Draw(img)
    for ox in (-SIZE, 0, SIZE):
        for oy in (-SIZE, 0, SIZE):
            shifted = [(x + ox, y + oy) for x, y in points]
            draw.line(shifted, fill=fill, width=width)


def decorate(img: Image.Image, terrain_id: str, variant: int, seed: int) -> Image.Image:
    style = STYLES[terrain_id]
    rng = random.Random(seed + variant * 1229)
    overlay = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))

    def grass_blade(x, y, h, color, lean=0):
        scatter_line(overlay, [(x, y), (x + lean, y - h)], color, 1)
        scatter_line(overlay, [(x, y), (x - lean // 2, y - h + 2)], (*color[:3], max(0, color[3] - 10)), 1)

    if terrain_id == 'core:grass':
        for _ in range(128):
            x, y = rng.randint(0, SIZE - 1), rng.randint(0, SIZE - 1)
            grass_blade(x, y, rng.randint(5, 10), (*style.accent, rng.randint(42, 68)), rng.randint(-2, 2))
        for _ in range(40):
            scatter_ellipse(overlay, rng.randint(0, SIZE - 1), rng.randint(0, SIZE - 1), rng.randint(1, 2), rng.randint(1, 2), (*style.accent2, 26))
    elif terrain_id == 'core:floodplain':
        for _ in range(16):
            y = rng.randint(2, SIZE - 2)
            pts = []
            phase = rng.random() * math.pi * 2
            amp = 1 + rng.randint(0, 1)
            for x in range(0, SIZE + 9, 8):
                pts.append((x, y + int(math.sin((x / SIZE) * math.pi * 2 + phase) * amp)))
            scatter_line(overlay, pts, (*style.light, 32), 1)
        for _ in range(72):
            scatter_ellipse(overlay, rng.randint(0, SIZE - 1), rng.randint(0, SIZE - 1), rng.randint(1, 2), rng.randint(1, 2), (*style.accent, 28))
        for _ in range(36):
            x, y = rng.randint(0, SIZE - 1), rng.randint(0, SIZE - 1)
            grass_blade(x, y, rng.randint(4, 7), (*style.accent2, rng.randint(18, 30)), rng.randint(-1, 1))
        for _ in range(12):
            scatter_ellipse(overlay, rng.randint(0, SIZE - 1), rng.randint(0, SIZE - 1), rng.randint(4, 9), rng.randint(2, 4), (*style.dark, 18))
    elif terrain_id == 'core:forest':
        for _ in range(112):
            scatter_ellipse(overlay, rng.randint(0, SIZE - 1), rng.randint(0, SIZE - 1), rng.randint(3, 6), rng.randint(2, 4), (*style.accent, rng.randint(32, 54)))
        for _ in range(24):
            x, y = rng.randint(0, SIZE - 1), rng.randint(0, SIZE - 1)
            scatter_line(overlay, [(x - 4, y + rng.randint(-1, 1)), (x + 5, y + rng.randint(-1, 1))], (*style.accent2, 48), 1)
    elif terrain_id == 'core:scrub':
        for _ in range(72):
            x, y = rng.randint(0, SIZE - 1), rng.randint(0, SIZE - 1)
            for _ in range(rng.randint(2, 4)):
                grass_blade(x + rng.randint(-2, 2), y + rng.randint(-1, 1), rng.randint(5, 8), (*style.accent, rng.randint(34, 56)), rng.randint(-3, 3))
        for _ in range(18):
            scatter_ellipse(overlay, rng.randint(0, SIZE - 1), rng.randint(0, SIZE - 1), rng.randint(2, 3), rng.randint(2, 3), (*style.accent2, 30))
    elif terrain_id == 'core:sand':
        for _ in range(10):
            y = rng.randint(2, SIZE - 2)
            pts = []
            phase = rng.random() * math.pi * 2
            for x in range(0, SIZE + 9, 8):
                pts.append((x, y + int(math.sin((x / SIZE) * math.pi * 2 + phase) * rng.randint(1, 3))))
            scatter_line(overlay, pts, (*style.light, 48), 1)
        for _ in range(45):
            scatter_ellipse(overlay, rng.randint(0, SIZE - 1), rng.randint(0, SIZE - 1), rng.randint(1, 2), rng.randint(1, 2), (*style.accent, 40))
        for _ in range(8):
            x, y = rng.randint(0, SIZE - 1), rng.randint(0, SIZE - 1)
            for _ in range(4):
                grass_blade(x + rng.randint(-2, 2), y + rng.randint(-1, 1), rng.randint(4, 7), (*style.accent2, 42), rng.randint(-2, 2))
    elif terrain_id in {'core:rock', 'core:cave_floor'}:
        for _ in range(34):
            x, y = rng.randint(0, SIZE - 1), rng.randint(0, SIZE - 1)
            scatter_line(overlay, [(x - 6, y + rng.randint(-2, 2)), (x + 5, y + rng.randint(-2, 2))], (*style.dark, 42), 1)
        for _ in range(20):
            scatter_ellipse(overlay, rng.randint(0, SIZE - 1), rng.randint(0, SIZE - 1), rng.randint(2, 4), rng.randint(1, 3), (*style.light, 28))
    elif terrain_id == 'core:tundra':
        for _ in range(70):
            scatter_ellipse(overlay, rng.randint(0, SIZE - 1), rng.randint(0, SIZE - 1), rng.randint(1, 2), rng.randint(1, 2), (*style.light, 28))
        for _ in range(24):
            x, y = rng.randint(0, SIZE - 1), rng.randint(0, SIZE - 1)
            grass_blade(x, y, rng.randint(3, 6), (*style.accent, 34), rng.randint(-2, 2))
    elif terrain_id == 'core:wetland':
        for _ in range(16):
            scatter_ellipse(overlay, rng.randint(0, SIZE - 1), rng.randint(0, SIZE - 1), rng.randint(6, 15), rng.randint(3, 7), (*style.dark, 36))
        for _ in range(42):
            x, y = rng.randint(0, SIZE - 1), rng.randint(0, SIZE - 1)
            grass_blade(x, y, rng.randint(5, 10), (*style.accent, 40), rng.randint(-1, 1))
    elif terrain_id in {'core:water', 'core:river', 'core:river_shallow'}:
        count = 18 if terrain_id == 'core:water' else 24
        for _ in range(count):
            y = rng.randint(0, SIZE - 1)
            pts = []
            phase = rng.random() * math.pi * 2
            for x in range(0, SIZE + 9, 8):
                pts.append((x, y + int(math.sin((x / SIZE) * math.pi * 2 + phase) * rng.randint(1, 3))))
            scatter_line(overlay, pts, (*style.accent, 40 if terrain_id == 'core:water' else 48), 1)
        if terrain_id == 'core:river_shallow':
            for _ in range(22):
                scatter_ellipse(overlay, rng.randint(0, SIZE - 1), rng.randint(0, SIZE - 1), rng.randint(2, 4), rng.randint(1, 2), (*style.accent2, 22))
    elif terrain_id == 'core:tilled_soil':
        gap = 10 + rng.randint(-1, 2)
        for y in range(4, SIZE, gap):
            scatter_line(overlay, [(0, y), (SIZE, y + rng.randint(-1, 1))], (*style.dark, 42), 1)
            scatter_line(overlay, [(0, y + 2), (SIZE, y + 2 + rng.randint(-1, 1))], (*style.light, 28), 1)
        for _ in range(22):
            scatter_ellipse(overlay, rng.randint(0, SIZE - 1), rng.randint(0, SIZE - 1), rng.randint(2, 3), rng.randint(1, 2), (*style.accent2, 18))
    elif terrain_id == 'core:berry_thicket':
        for _ in range(84):
            scatter_ellipse(overlay, rng.randint(0, SIZE - 1), rng.randint(0, SIZE - 1), rng.randint(3, 5), rng.randint(2, 4), (*style.accent2, 24))
        for _ in range(26):
            scatter_ellipse(overlay, rng.randint(0, SIZE - 1), rng.randint(0, SIZE - 1), 1, 1, (*style.accent, 110))
    blur = 0.18 if terrain_id in {'core:sand', 'core:water', 'core:river', 'core:river_shallow'} else 0.28
    return overlay if blur <= 0 else overlay.filter(ImageFilter.GaussianBlur(blur))


def make_variant(terrain_id: str, index: int) -> Image.Image:
    style = STYLES[terrain_id]
    base_seed = sum(ord(c) for c in terrain_id) * 911 + index * 10103
    img = base_texture(style, base_seed)
    # Subtle tile-wide grading keeps variants related but distinct.
    rng = random.Random(base_seed + 99)
    img = ImageEnhance.Contrast(img).enhance(0.99 + rng.random() * 0.08)
    img = ImageEnhance.Color(img).enhance(0.96 + rng.random() * 0.10)
    overlay = decorate(img, terrain_id, index, base_seed)
    img = Image.alpha_composite(img, overlay)
    img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=85, threshold=3))
    return img.convert('RGBA')


def build_preview(entries):
    if not entries:
        return
    cols = VARIANT_COUNT
    rows = len(entries) // cols
    cell = 96
    label_h = 18
    out = Image.new('RGBA', (cols * cell, rows * (cell + label_h)), (16, 18, 20, 255))
    draw = ImageDraw.Draw(out)
    for idx, (label, img) in enumerate(entries):
        x = (idx % cols) * cell
        y = (idx // cols) * (cell + label_h)
        thumb = img.resize((cell, cell), Image.Resampling.LANCZOS)
        out.alpha_composite(thumb, (x, y))
        draw.text((x + 4, y + cell + 2), label, fill=(230, 230, 230, 255))
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.save(PREVIEW_PATH, optimize=True)


def ensure_variants():
    manifest = json.loads(VISUALS_PATH.read_text(encoding='utf-8'))
    preview = []
    for terrain_id, stem in TERRAIN_OUTPUTS.items():
        base_output = TERRAIN_DIR / f'{stem}.png'
        variant_paths = []
        first = None
        for i in range(VARIANT_COUNT):
            img = make_variant(terrain_id, i)
            out_name = f'{stem}_v{i:02d}.png'
            out_path = TERRAIN_DIR / out_name
            out_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(out_path, optimize=True)
            variant_paths.append(f'assets/sprites/terrain/{out_name}')
            if i == 0:
                img.save(base_output, optimize=True)
                first = img
            if terrain_id in {'core:grass', 'core:forest', 'core:sand', 'core:water'}:
                preview.append((f"{terrain_id.split(':')[-1]} {i}", img))
        manifest['terrain'][terrain_id] = variant_paths
        if first is not None:
            print(base_output.relative_to(ROOT))
    VISUALS_PATH.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    build_preview(preview)


if __name__ == '__main__':
    ensure_variants()
