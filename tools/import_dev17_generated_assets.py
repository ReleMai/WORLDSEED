from __future__ import annotations

from collections import deque
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = Path('/mnt/data')
SPRITES = ROOT / 'worldseed' / 'assets' / 'sprites'


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def save(img: Image.Image, path: Path) -> None:
    ensure_parent(path)
    img.save(path)


def trim_alpha(img: Image.Image) -> Image.Image:
    img = img.convert('RGBA')
    alpha = img.getchannel('A')
    box = alpha.getbbox()
    return img.crop(box) if box else img


def fit_canvas(img: Image.Image, size: tuple[int, int], *, pad: int = 1, background=(0, 0, 0, 0)) -> Image.Image:
    img = trim_alpha(img)
    cw, ch = size
    tw, th = max(1, cw - pad * 2), max(1, ch - pad * 2)
    scale = min(tw / max(1, img.width), th / max(1, img.height))
    nw = max(1, int(round(img.width * scale)))
    nh = max(1, int(round(img.height * scale)))
    img = img.resize((nw, nh), Image.Resampling.NEAREST)
    out = Image.new('RGBA', size, background)
    x = (cw - nw) // 2
    y = ch - nh - pad
    out.alpha_composite(img, (x, y))
    return out


def alpha_components(path: Path, *, min_pixels: int = 500) -> tuple[list[tuple[int, int, int, int, int]], Image.Image]:
    img = Image.open(path).convert('RGBA')
    w, h = img.size
    px = img.load()
    seen = bytearray(w * h)
    comps: list[tuple[int, int, int, int, int]] = []
    for y in range(h):
        for x in range(w):
            idx = y * w + x
            if seen[idx]:
                continue
            seen[idx] = 1
            if px[x, y][3] == 0:
                continue
            q = deque([(x, y)])
            minx = maxx = x
            miny = maxy = y
            n = 0
            while q:
                cx, cy = q.popleft()
                n += 1
                if cx < minx:
                    minx = cx
                if cx > maxx:
                    maxx = cx
                if cy < miny:
                    miny = cy
                if cy > maxy:
                    maxy = cy
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < w and 0 <= ny < h:
                        nidx = ny * w + nx
                        if seen[nidx]:
                            continue
                        seen[nidx] = 1
                        if px[nx, ny][3] != 0:
                            q.append((nx, ny))
            if n >= min_pixels:
                comps.append((minx, miny, maxx, maxy, n))
    return comps, img


def merge_boxes(boxes: list[tuple[int, int, int, int, int]]) -> tuple[int, int, int, int]:
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def grouped_columns(path: Path, *, band: str, x_tolerance: int = 70, min_pixels: int = 500) -> tuple[list[tuple[int, int, int, int]], Image.Image]:
    comps, img = alpha_components(path, min_pixels=min_pixels)
    h = img.height
    if band == 'top':
        comps = [c for c in comps if ((c[1] + c[3]) / 2) < h / 2]
    else:
        comps = [c for c in comps if ((c[1] + c[3]) / 2) >= h / 2]
    comps = sorted(comps, key=lambda c: ((c[0] + c[2]) / 2, (c[1] + c[3]) / 2))
    groups: list[list[tuple[int, int, int, int, int]]] = []
    centers: list[float] = []
    for c in comps:
        xc = (c[0] + c[2]) / 2
        placed = False
        for i, center in enumerate(centers):
            if abs(xc - center) < x_tolerance:
                groups[i].append(c)
                centers[i] = sum((g[0] + g[2]) / 2 for g in groups[i]) / len(groups[i])
                placed = True
                break
        if not placed:
            groups.append([c])
            centers.append(xc)
    merged = [merge_boxes(g) for g in groups]
    merged.sort(key=lambda b: (b[0] + b[2]) / 2)
    return merged, img


def import_column_frames(path: Path, *, band: str, frames: int, frame_index: int, limit: int | None,
                         size: tuple[int, int], out_paths: list[Path]) -> None:
    columns, img = grouped_columns(path, band=band)
    if limit is not None:
        columns = columns[:limit]
    if len(columns) < len(out_paths):
        raise RuntimeError(f'{path.name}:{band} expected {len(out_paths)} columns, found {len(columns)}')
    for box, out_path in zip(columns, out_paths):
        x1, y1, x2, y2 = box
        col = img.crop((max(0, x1 - 3), max(0, y1 - 3), min(img.width, x2 + 4), min(img.height, y2 + 4)))
        frame_h = col.height / frames
        top = int(round(frame_index * frame_h))
        bottom = int(round((frame_index + 1) * frame_h))
        frame = col.crop((0, top, col.width, bottom))
        save(fit_canvas(frame, size), out_path)


def crop_grid(path: Path, *, cols: int, rows: int, size: tuple[int, int], out_paths: list[Path],
              row_offset: int = 0, count: int | None = None) -> None:
    img = Image.open(path).convert('RGBA')
    cell_w = img.width / cols
    cell_h = img.height / rows
    total = count if count is not None else len(out_paths)
    for i, out_path in enumerate(out_paths[:total]):
        idx = i + row_offset
        r = idx // cols
        c = idx % cols
        left = int(round(c * cell_w))
        top = int(round(r * cell_h))
        right = int(round((c + 1) * cell_w))
        bottom = int(round((r + 1) * cell_h))
        tile = img.crop((left, top, right, bottom))
        save(fit_canvas(tile, size, pad=0), out_path)


def import_large_sprites(path: Path, *, count: int, size: tuple[int, int], out_paths: list[Path], min_pixels: int = 3000) -> None:
    comps, img = alpha_components(path, min_pixels=min_pixels)
    comps.sort(key=lambda c: c[4], reverse=True)
    comps = comps[:count]
    comps.sort(key=lambda c: ((c[1] + c[3]) / 2, (c[0] + c[2]) / 2))
    if len(comps) < len(out_paths):
        raise RuntimeError(f'{path.name} expected {len(out_paths)} sprites, found {len(comps)}')
    for c, out_path in zip(comps, out_paths):
        x1, y1, x2, y2, _ = c
        sprite = img.crop((max(0, x1 - 2), max(0, y1 - 2), min(img.width, x2 + 3), min(img.height, y2 + 3)))
        save(fit_canvas(sprite, size), out_path)


def main() -> None:
    # Player choices: 10 male, 10 female.
    male_paths = [SPRITES / 'player' / 'male' / f'variant_{i:02d}.png' for i in range(10)]
    female_paths = [SPRITES / 'player' / 'female' / f'variant_{i:02d}.png' for i in range(10)]
    import_column_frames(SRC / 'pixel_art_survivor_sprite_sheet.png', band='top', frames=4, frame_index=2, limit=5,
                         size=(32, 48), out_paths=male_paths[:5])
    import_column_frames(SRC / 'pixel_art_rpg_character_sprite_sheet.png', band='top', frames=4, frame_index=2, limit=5,
                         size=(32, 48), out_paths=male_paths[5:])
    import_column_frames(SRC / 'pixel_art_female_survivor_sprite_sheet.png', band='top', frames=3, frame_index=2, limit=5,
                         size=(32, 48), out_paths=female_paths[:5])
    import_column_frames(SRC / 'pixel_art_female_survivor_sprite_sheet.png', band='bottom', frames=3, frame_index=2, limit=5,
                         size=(32, 48), out_paths=female_paths[5:])

    # NPC sheet: 12 front-facing variants.
    npc_paths = [SPRITES / 'npc' / f'dev17_variant_{i:02d}.png' for i in range(12)]
    import_column_frames(SRC / 'earthy_medieval_npc_sprite_sheet.png', band='top', frames=4, frame_index=2, limit=6,
                         size=(32, 48), out_paths=npc_paths[:6])
    import_column_frames(SRC / 'earthy_medieval_npc_sprite_sheet.png', band='bottom', frames=3, frame_index=2, limit=6,
                         size=(32, 48), out_paths=npc_paths[6:])

    # Wildlife and monsters imported as reusable grounded variants.
    wildlife_out = [SPRITES / 'species' / '_dev17' / f'wildlife_{i:02d}.png' for i in range(12)]
    monster_out = [SPRITES / 'species' / '_dev17' / f'monster_{i:02d}.png' for i in range(10)]
    crop_grid(SRC / 'pixel_art_wildlife_sprite_sheet.png', cols=4, rows=3, size=(56, 48), out_paths=wildlife_out)
    crop_grid(SRC / 'pixel_art_monster_sprite_atlas.png', cols=5, rows=2, size=(56, 48), out_paths=monster_out)

    # Cave presentation tiles.
    cave_floor_paths = [SPRITES / 'terrain' / f'dev17_cave_floor_{i:02d}.png' for i in range(16)]
    crop_grid(SRC / 'pixel_cave_terrain_tileset.png', cols=8, rows=3, size=(128, 128), out_paths=cave_floor_paths,
              row_offset=0, count=16)
    cave_wall_paths = [SPRITES / 'terrain' / f'dev17_cave_wall_{i:02d}.png' for i in range(6)]
    crop_grid(SRC / 'pixel_cave_terrain_tileset.png', cols=8, rows=3, size=(128, 128), out_paths=cave_wall_paths,
              row_offset=16, count=6)
    cave_mouth_paths = [SPRITES / 'terrain' / f'dev17_cave_mouth_{i:02d}.png' for i in range(16)]
    crop_grid(SRC / 'pixel_art_cave_entrance_sprite_sheet.png', cols=4, rows=4, size=(96, 96), out_paths=cave_mouth_paths)

    # Ore item art replacements from the new ore atlas.
    ore_targets = [
        (0, SPRITES / 'items' / 'coal.png'),
        (1, SPRITES / 'items' / 'copper_ore.png'),
        (2, SPRITES / 'items' / 'iron_ore.png'),
    ]
    grid_img = Image.open(SRC / '16_pixel_art_ore_sprites_sheet.png').convert('RGBA')
    cell_w = grid_img.width / 4
    cell_h = grid_img.height / 4
    for idx, out_path in ore_targets:
        r, c = divmod(idx, 4)
        box = (int(round(c * cell_w)), int(round(r * cell_h)), int(round((c + 1) * cell_w)), int(round((r + 1) * cell_h)))
        tile = grid_img.crop(box)
        save(fit_canvas(tile, (80, 80), pad=2), out_path)

    # Default app icon / fallback player sprite updated to the first male front-facing look.
    first_male = Image.open(male_paths[0]).convert('RGBA')
    save(first_male, SPRITES / 'special' / 'player.png')

    print('Dev17 generated assets imported successfully.')


if __name__ == '__main__':
    main()
