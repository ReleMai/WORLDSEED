from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
TERRAIN_DIR = ROOT / 'worldseed' / 'assets' / 'sprites' / 'terrain'
VISUALS_PATH = ROOT / 'worldseed' / 'assets' / 'visuals.json'
PREVIEW_PATH = ROOT / 'artifacts' / 'contextual-water-preview.png'
SIZE = 128
VARIANT_COUNT = 10


@dataclass(frozen=True)
class Style:
    base: tuple[int, int, int]
    dark: tuple[int, int, int]
    light: tuple[int, int, int]
    accent: tuple[int, int, int]
    accent2: tuple[int, int, int]


STYLES = {
    'render:ocean_deep': Style((28, 99, 136), (12, 59, 92), (76, 144, 184), (178, 219, 230), (24, 78, 112)),
    'render:ocean_shallow': Style((86, 151, 166), (44, 103, 116), (154, 198, 201), (226, 232, 205), (202, 184, 133)),
    'render:estuary_mix': Style((88, 136, 138), (48, 90, 95), (138, 178, 168), (194, 203, 152), (178, 161, 117)),
    'render:freshwater_deep': Style((49, 122, 156), (24, 82, 110), (99, 168, 198), (189, 225, 231), (43, 108, 132)),
    'render:freshwater_shallow': Style((110, 164, 168), (62, 112, 114), (170, 203, 193), (223, 224, 184), (174, 156, 124)),
}

STEMS = {
    'render:ocean_deep': 'ocean_deep_hd',
    'render:ocean_shallow': 'ocean_shallow_hd',
    'render:estuary_mix': 'estuary_mix_hd',
    'render:freshwater_deep': 'freshwater_deep_hd',
    'render:freshwater_shallow': 'freshwater_shallow_hd',
}


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(round(x * (1.0 - t) + y * t)) for x, y in zip(a, b))


def clamp(n):
    return max(0, min(255, int(round(n))))


def shade(color, delta):
    return tuple(clamp(c + delta) for c in color)


def tileable_noise(seed: int, coarse: int) -> Image.Image:
    rng = random.Random(seed)
    img = Image.new('L', (coarse + 1, coarse + 1))
    px = img.load()
    first_row = None
    for y in range(coarse):
        row = []
        for x in range(coarse):
            v = rng.randint(0, 255)
            px[x, y] = v
            row.append(v)
        if first_row is None:
            first_row = row[:]
        px[coarse, y] = row[0]
    for x in range(coarse):
        px[x, coarse] = first_row[x]
    px[coarse, coarse] = first_row[0]
    return img.resize((SIZE + 1, SIZE + 1), Image.Resampling.BICUBIC).crop((0, 0, SIZE, SIZE))


def make_base(style: Style, seed: int) -> Image.Image:
    n1, n2 = tileable_noise(seed + 11, 14), tileable_noise(seed + 53, 30)
    out = Image.new('RGBA', (SIZE, SIZE))
    p1, p2, dst = n1.load(), n2.load(), out.load()
    for y in range(SIZE):
        for x in range(SIZE):
            v1 = p1[x, y] / 255.0
            v2 = p2[x, y] / 255.0
            c = mix(style.dark, style.base, v1)
            c = mix(c, style.light, v2 * 0.7)
            c = mix(c, style.accent2, max(0.0, (v1 - 0.78) / 0.22) * 0.18)
            dst[x, y] = (*shade(c, (v2 - 0.5) * 18 + (v1 - 0.5) * 12), 255)
    return out


def wline(draw, pts, fill, width=1):
    for ox in (-SIZE, 0, SIZE):
        for oy in (-SIZE, 0, SIZE):
            draw.line([(x + ox, y + oy) for x, y in pts], fill=fill, width=width)


def wellipse(draw, x, y, rx, ry, fill, outline=None):
    for ox in (-SIZE, 0, SIZE):
        for oy in (-SIZE, 0, SIZE):
            draw.ellipse((x + ox - rx, y + oy - ry, x + ox + rx, y + oy + ry), fill=fill, outline=outline)


def decorate(style: Style, kind: str, variant: int, seed: int) -> Image.Image:
    rng = random.Random(seed + variant * 941)
    ov = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(ov)

    def wave_pass(lines: int, amp_lo: int, amp_hi: int, alpha: int, step: int = 8, color=None):
        tint = color or style.accent
        for _ in range(lines):
            y = rng.randint(0, SIZE - 1)
            amp = rng.randint(amp_lo, amp_hi)
            phase = rng.random() * math.pi * 2
            freq = rng.uniform(0.7, 1.4)
            pts = [(x, y + int(math.sin((x / SIZE) * math.pi * 2 * freq + phase) * amp))
                   for x in range(0, SIZE + step + 1, step)]
            wline(draw, pts, (*tint, alpha), 1)

    def current_streaks(lines: int, alpha: int):
        for _ in range(lines):
            x = rng.randint(0, SIZE - 1)
            y = rng.randint(0, SIZE - 1)
            pts = []
            for i in range(-3, 6):
                pts.append((x + i * 8, y + int(math.sin(i * 0.8 + rng.random() * 0.7) * 2)))
            wline(draw, pts, (*style.accent2, alpha), 1)

    def sandbars(count: int, alpha: int):
        for _ in range(count):
            cx = rng.randint(0, SIZE - 1)
            cy = rng.randint(0, SIZE - 1)
            rx = rng.randint(4, 12)
            ry = rng.randint(2, 5)
            wellipse(draw, cx, cy, rx, ry, (*style.accent2, alpha))
            if rng.random() < 0.6:
                wellipse(draw, cx + rng.randint(-1, 1), cy + rng.randint(-1, 1), max(1, rx - 2), max(1, ry - 1), (*style.light, max(0, alpha - 10)))

    # Base moving-water language for all contextual waters.
    wave_pass(16 if 'deep' in kind else 20, 1, 3 if 'deep' in kind else 4, 30 if 'deep' in kind else 36)
    wave_pass(8 if 'deep' in kind else 10, 1, 2, 20, step=10, color=style.light)

    if kind == 'render:ocean_deep':
        current_streaks(18, 16)
        for _ in range(10):
            wellipse(draw, rng.randint(0, SIZE - 1), rng.randint(0, SIZE - 1), rng.randint(3, 7), rng.randint(2, 5), (*style.accent2, 9))
    elif kind == 'render:ocean_shallow':
        sandbars(58, 18)
        current_streaks(12, 18)
        wave_pass(10, 1, 2, 16, step=12, color=(243, 241, 230))
    elif kind == 'render:estuary_mix':
        sandbars(34, 16)
        current_streaks(20, 20)
        for _ in range(16):
            cx = rng.randint(0, SIZE - 1); cy = rng.randint(0, SIZE - 1)
            pts = [(cx + i * 7, cy + int(math.sin(i * 0.9 + rng.random()) * 3)) for i in range(-3, 5)]
            wline(draw, pts, (*style.accent, 18), 1)
    elif kind == 'render:freshwater_deep':
        current_streaks(24, 16)
        for _ in range(18):
            x = rng.randint(0, SIZE - 1); y = rng.randint(0, SIZE - 1)
            pts = [(x + i * 8, y + int(math.sin(i + rng.random()) * 2)) for i in range(-2, 5)]
            wline(draw, pts, (*style.light, 14), 1)
    elif kind == 'render:freshwater_shallow':
        sandbars(48, 18)
        current_streaks(16, 14)
        for _ in range(20):
            x = rng.randint(0, SIZE - 1); y = rng.randint(0, SIZE - 1)
            pts = [(x + i * 7, y + int(math.sin(i * 0.9 + rng.random()) * 2)) for i in range(-2, 5)]
            wline(draw, pts, (*style.accent, 20), 1)
        for _ in range(18):
            wellipse(draw, rng.randint(0, SIZE - 1), rng.randint(0, SIZE - 1), rng.randint(2, 5), rng.randint(1, 3), (*style.light, 14))
    return ov.filter(ImageFilter.GaussianBlur(0.18))


def main():
    manifest = json.loads(VISUALS_PATH.read_text(encoding='utf-8'))
    preview = []
    for kind, style in STYLES.items():
        seed = sum(ord(c) for c in kind) * 611
        rels = []
        stem = STEMS[kind]
        for i in range(VARIANT_COUNT):
            img = make_base(style, seed + i * 103)
            img = ImageEnhance.Contrast(img).enhance(0.99 + (i % 5) * 0.015)
            img = ImageEnhance.Color(img).enhance(0.98 + (i % 4) * 0.02)
            img = Image.alpha_composite(img, decorate(style, kind, i, seed))
            img = img.filter(ImageFilter.UnsharpMask(radius=1.0, percent=70, threshold=3))
            filename = f'{stem}_v{i:02d}.png'
            img.save(TERRAIN_DIR / filename, optimize=True)
            rels.append(f'assets/sprites/terrain/{filename}')
            if i < 5:
                preview.append((f'{kind.split(":")[-1]} {i}', img))
        manifest['terrain'][kind] = rels
    VISUALS_PATH.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    cols = 5
    rows = len(preview) // cols
    cell = 96
    out = Image.new('RGBA', (cols * cell, rows * (cell + 18)), (18, 20, 22, 255))
    draw = ImageDraw.Draw(out)
    for idx, (label, img) in enumerate(preview):
        x = (idx % cols) * cell; y = (idx // cols) * (cell + 18)
        out.alpha_composite(img.resize((cell, cell), Image.Resampling.LANCZOS), (x, y))
        draw.text((x + 4, y + cell + 2), label, fill=(232, 232, 232, 255))
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    out.save(PREVIEW_PATH, optimize=True)


if __name__ == '__main__':
    main()
