#!/usr/bin/env python3
"""Import generated artwork sheets without drawing or painting item artwork.

The input manifest pins each generated source image to ordered item IDs. This
tool only extracts cells, trims transparent margins, resamples existing RGBA
pixels, and centers them on inventory canvases. Original source sheets and a
reproducible per-item provenance manifest are retained inside the repository.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[1]
ITEMS = ROOT / "worldseed/data/items.json"
SPRITES = ROOT / "worldseed/assets/sprites/items"
SOURCE_DIR = ROOT / "worldseed/assets/source_items/dev64"
PROVENANCE = SOURCE_DIR / "manifest.json"
POLICY = {
    "version": 1,
    "canvas_size": 64,
    "padding": 4,
    "trim_alpha_threshold": 16,
    "boundary_alpha_threshold": 96,
    "resampler": "lanczos_premultiplied_rgba",
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def pixel_hash(image: Image.Image) -> str:
    return sha256_bytes(image.convert("RGBA").tobytes())


def generated_item_ids(provenance: Path = PROVENANCE) -> set[str]:
    """Published generated artwork is protected from legacy redraw tools."""
    if not provenance.exists():
        return set()
    data = json.loads(provenance.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("items"), list):
        raise ValueError("invalid generated-art provenance; refusing to overwrite item artwork")
    ids = [row["item_id"] for row in data["items"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate generated-art provenance; refusing to overwrite item artwork")
    return set(ids)


def alpha_mask(image: Image.Image, threshold: int) -> Image.Image:
    return image.getchannel("A").point(lambda a: 255 if a >= threshold else 0)


def occupied_count(mask: Image.Image) -> int:
    return mask.histogram()[255]


def regular_edges(start: int, end: int, count: int) -> list[int]:
    return [start + (end - start) * i // count for i in range(count + 1)]


def gutter_edges(source: Image.Image, grid: tuple[int, int, int, int], count: int, axis: str) -> list[int]:
    """Choose only nearby, globally empty gutters; never cut occupied artwork.

    Generated sheets can drift slightly from equal cells. A separator may move
    by at most 15% of the nominal cell dimension and must sit inside a gutter
    containing at least three rows/columns empty at the meaningful threshold.
    If no safe nearby gutter exists, the solid-boundary check requires a
    reviewed explicit override rather than guessing from connected objects.
    """
    start, end = (grid[0], grid[2]) if axis == "x" else (grid[1], grid[3])
    edges = regular_edges(start, end, count)
    mask = alpha_mask(source, POLICY["trim_alpha_threshold"])
    radius = max(2, math.floor((end - start) / count * 0.15))
    for i in range(1, count):
        nominal = edges[i]
        low, high = max(start + 1, nominal - radius), min(end - 1, nominal + radius)
        empty = []
        for position in range(low, high + 1):
            line = (position, grid[1], position + 1, grid[3]) if axis == "x" else (grid[0], position, grid[2], position + 1)
            empty.append(occupied_count(mask.crop(line)) == 0)
        candidates = []
        run_start = None
        for j, is_empty in enumerate(empty + [False]):
            if is_empty and run_start is None:
                run_start = j
            elif not is_empty and run_start is not None:
                if j - run_start >= 3:
                    a, b = low + run_start + 1, low + j - 2
                    candidate = max(a, min(b, nominal))
                    candidates.append((abs(candidate - nominal), -(j - run_start), candidate))
                run_start = None
        if candidates:
            edges[i] = min(candidates)[2]
    if any(a >= b for a, b in zip(edges, edges[1:])):
        raise ValueError("inferred gutters are not ordered")
    return edges


def checked_edges(value: Any, start: int, end: int, count: int, label: str) -> list[int]:
    edges = regular_edges(start, end, count) if value is None else value
    if (not isinstance(edges, list) or len(edges) != count + 1
            or any(type(x) is not int for x in edges)
            or edges[0] != start or edges[-1] != end
            or any(a >= b for a, b in zip(edges, edges[1:]))):
        raise ValueError(f"{label}: expected {count + 1} increasing integer boundaries from {start} to {end}")
    return edges


def checked_box(value: Any, width: int, height: int, label: str) -> tuple[int, int, int, int]:
    if not isinstance(value, (list, tuple)) or len(value) != 4 or any(type(x) is not int for x in value):
        raise ValueError(f"{label}: expected four integer bounds")
    x0, y0, x1, y1 = value
    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        raise ValueError(f"{label}: bounds are outside {width}x{height}: {value}")
    return x0, y0, x1, y1


def edge_occupancy(mask: Image.Image) -> int:
    w, h = mask.size
    return sum(mask.getpixel((x, 0)) != 0 or mask.getpixel((x, h - 1)) != 0 for x in range(w)) + sum(
        mask.getpixel((0, y)) != 0 or mask.getpixel((w - 1, y)) != 0 for y in range(1, h - 1))


def component_partition(source: Image.Image, grid: tuple[int, int, int, int], cols: int, rows: int,
                        item_count: int) -> tuple[Image.Image, list[dict[str, Any]]]:
    """Separate existing disconnected artwork; never synthesize object pixels.

    Whole foreground components belong to the expected grid cell containing
    their bounding-box center. Several pieces may belong to one item. Unlike
    rectangular cells, this keeps neighboring slanted objects out of a crop.
    The derived ownership map is saved and hashed for exact reproduction.
    """
    meaningful = alpha_mask(source, POLICY["trim_alpha_threshold"])
    width, height = source.size
    ownership = Image.new("L", source.size, 0)
    groups = [{"cell_index": i, "source_pixels": 0, "components": []} for i in range(cols * rows)]
    try:
        import numpy as np
        from scipy import ndimage
    except ImportError:
        np = ndimage = None
    components = []
    if ndimage is not None:
        labels, _ = ndimage.label(np.asarray(meaningful) > 0)
        sizes = np.bincount(labels.ravel())
        owner_array = np.zeros((height, width), dtype=np.uint8)
        for label, slices in enumerate(ndimage.find_objects(labels), start=1):
            if slices is None or sizes[label] < 8:
                continue
            y, x = slices
            components.append((int(sizes[label]), (x.start, y.start, x.stop, y.stop), label))
    else:
        # Portable authoring fallback; production icon reads need only Pillow.
        remaining = bytearray(meaningful.tobytes())
        for index in range(len(remaining)):
            if not remaining[index]:
                continue
            remaining[index] = 0
            pending, pixels = deque([index]), []
            x0 = x1 = index % width
            y0 = y1 = index // width
            while pending:
                pixel = pending.popleft()
                pixels.append(pixel)
                y, x = divmod(pixel, width)
                x0, x1, y0, y1 = min(x0, x), max(x1, x), min(y0, y), max(y1, y)
                neighbors = []
                if x: neighbors.append(pixel - 1)
                if x + 1 < width: neighbors.append(pixel + 1)
                if y: neighbors.append(pixel - width)
                if y + 1 < height: neighbors.append(pixel + width)
                for neighbor in neighbors:
                    if remaining[neighbor]:
                        remaining[neighbor] = 0
                        pending.append(neighbor)
            if len(pixels) >= 8:
                components.append((len(pixels), (x0, y0, x1 + 1, y1 + 1), pixels))
        owner_bytes = bytearray(width * height)
    for size, box, label_or_pixels in components:
        cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
        column = int((cx - grid[0]) * cols / (grid[2] - grid[0]))
        row = int((cy - grid[1]) * rows / (grid[3] - grid[1]))
        if not (0 <= column < cols and 0 <= row < rows):
            raise ValueError("source artwork lies outside declared grid")
        slot = row * cols + column
        if slot >= item_count:
            raise ValueError(f"unused cell {slot + 1} contains generated artwork; source/item count mismatch")
        groups[slot]["source_pixels"] += size
        groups[slot]["components"].append({"bounds": list(box), "pixels": size})
        if ndimage is not None:
            owner_array[labels == label_or_pixels] = slot + 1
        else:
            for pixel in label_or_pixels:
                owner_bytes[pixel] = slot + 1
    for group in groups[:item_count]:
        if group["source_pixels"] < 200:
            raise ValueError(f"expected cell {group['cell_index'] + 1} lacks a substantial identifiable object")
    ownership = Image.fromarray(owner_array) if ndimage is not None else Image.frombytes("L", source.size, bytes(owner_bytes))
    return ownership, groups[:item_count]


def isolate_source(source: Image.Image, ownership: Image.Image, label: int) -> tuple[Image.Image, tuple[int, int, int, int]]:
    core = ownership.point(lambda value: 255 if value == label else 0)
    bounds = core.getbbox()
    if bounds is None:
        raise ValueError("ownership map has no item pixels")
    # Keep the original faint antialiasing within two source pixels of this
    # object's core. Pixels owned by a different item are always excluded.
    expanded = core.filter(ImageFilter.MaxFilter(5))
    unowned = ownership.point(lambda value: 255 if value == 0 else 0)
    keep = ImageChops.lighter(core, ImageChops.multiply(expanded, unowned))
    isolated = source.copy()
    isolated.putalpha(ImageChops.multiply(source.getchannel("A"), keep))
    x0, y0, x1, y1 = bounds
    cell = (max(0, x0 - 3), max(0, y0 - 3), min(source.width, x1 + 3), min(source.height, y1 + 3))
    return isolated, cell


def extract_icon(source: Image.Image, cell: tuple[int, int, int, int]) -> tuple[Image.Image, dict[str, Any]]:
    crop = source.crop(cell)
    meaningful = alpha_mask(crop, POLICY["trim_alpha_threshold"])
    count = occupied_count(meaningful)
    occupancy = count / (crop.width * crop.height)
    bounds = meaningful.getbbox()
    if bounds is None or count < 8 or occupancy < 0.0005:
        raise ValueError("cell has no meaningful icon")
    if occupancy > 0.94:
        raise ValueError("cell lacks transparent margins (possible opaque background)")
    boundary = edge_occupancy(alpha_mask(crop, POLICY["boundary_alpha_threshold"]))
    if boundary:
        raise ValueError(f"{boundary} solid pixels touch a cell boundary; use reviewed row_edges/column_edges/cell_bounds")
    trimmed = crop.crop(bounds)
    if min(trimmed.size) < 3:
        raise ValueError("icon is too narrow to identify")
    available = POLICY["canvas_size"] - 2 * POLICY["padding"]
    scale = available / max(trimmed.size)
    target = tuple(max(1, round(dimension * scale)) for dimension in trimmed.size)
    # RGBa is Pillow's explicit premultiplied-alpha mode. Filtering cannot mix
    # invisible neon RGB values into the visible outline of generated art.
    resized = trimmed.convert("RGBa").resize(target, Image.Resampling.LANCZOS).convert("RGBA")
    icon = Image.new("RGBA", (POLICY["canvas_size"], POLICY["canvas_size"]), (0, 0, 0, 0))
    offset = tuple((POLICY["canvas_size"] - dimension) // 2 for dimension in target)
    icon.paste(resized, offset)
    final_mask = alpha_mask(icon, POLICY["trim_alpha_threshold"])
    final_bounds = final_mask.getbbox()
    final_count = occupied_count(final_mask)
    if final_bounds is None or final_count < 8:
        raise ValueError("icon vanishes at inventory resolution")
    if edge_occupancy(final_mask):
        raise ValueError("resized icon touches inventory boundary")
    # The technical transform must retain source details inside its chosen box.
    if icon.crop((offset[0], offset[1], offset[0] + target[0], offset[1] + target[1])).tobytes() != resized.tobytes():
        raise AssertionError("center placement changed generated pixels")
    x0, y0, _, _ = cell
    metadata = {
        "cell_bounds": list(cell),
        "trim_bounds_in_cell": list(bounds),
        "trim_bounds_in_source": [x0 + bounds[0], y0 + bounds[1], x0 + bounds[2], y0 + bounds[3]],
        "trim_size": list(trimmed.size),
        "resized_size": list(target),
        "canvas_offset": list(offset),
        "source_occupancy": round(occupancy, 6),
        "source_solid_boundary_pixels": boundary,
        "output_alpha_bounds": list(final_bounds),
        "output_occupancy": round(final_count / (icon.width * icon.height), 6),
        "rgba_sha256": pixel_hash(icon),
    }
    return icon, metadata


@dataclass
class SheetPlan:
    record: dict[str, Any]
    source: Path
    source_bytes: bytes
    outputs: list[tuple[dict[str, Any], Image.Image]]
    ownership: Image.Image | None = None


def resolve_source(value: str, manifest: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    local = manifest.parent / path
    return local if local.exists() else ROOT / path


def plan_sheet(sheet: dict[str, Any], manifest: Path, catalog: dict[str, dict]) -> SheetPlan:
    sid = sheet.get("id", "")
    if not isinstance(sid, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", sid):
        raise ValueError(f"unsafe sheet id: {sid!r}")
    source_path = resolve_source(str(sheet.get("source", "")), manifest)
    if not sheet.get("source") or not source_path.is_file():
        raise ValueError(f"{sid}: generated source is not ready")
    source_bytes = source_path.read_bytes()
    with Image.open(source_path) as raw:
        if raw.mode != "RGBA":
            raise ValueError(f"{sid}: source must supply real RGBA transparency, found {raw.mode}")
        source = raw.copy()
    cols, rows = sheet.get("columns"), sheet.get("rows")
    if type(cols) is not int or type(rows) is not int or not (1 <= cols <= 24 and 1 <= rows <= 24):
        raise ValueError(f"{sid}: invalid grid dimensions")
    item_ids = sheet.get("item_ids")
    if not isinstance(item_ids, list) or not item_ids or len(item_ids) > cols * rows or len(set(item_ids)) != len(item_ids):
        raise ValueError(f"{sid}: item_ids must be unique and fit the grid")
    grid = checked_box(sheet.get("grid_bounds", [0, 0, source.width, source.height]), *source.size, sid)
    xs = checked_edges(sheet.get("column_edges", gutter_edges(source, grid, cols, "x")), grid[0], grid[2], cols, sid + " columns")
    ys = checked_edges(sheet.get("row_edges", gutter_edges(source, grid, rows, "y")), grid[1], grid[3], rows, sid + " rows")
    overrides = sheet.get("cell_bounds", {})
    if not isinstance(overrides, dict):
        raise ValueError(f"{sid}: cell_bounds overrides must map item IDs to bounds")
    unknown_overrides = set(overrides) - set(item_ids)
    if unknown_overrides:
        raise ValueError(f"{sid}: cell bounds reference unknown IDs: {sorted(unknown_overrides)}")
    outputs = []
    partition = None
    partition_groups = []
    if sheet.get("partition_mode") == "components":
        partition, partition_groups = component_partition(source, grid, cols, rows, len(item_ids))
    elif not overrides:
        # Exact grids remain lossless rectangular crops. When a generated
        # object crosses those cells, select whole source components instead.
        for i in range(len(item_ids)):
            c, r = i % cols, i // cols
            candidate = source.crop((xs[c], ys[r], xs[c + 1], ys[r + 1]))
            if edge_occupancy(alpha_mask(candidate, POLICY["boundary_alpha_threshold"])):
                partition, partition_groups = component_partition(source, grid, cols, rows, len(item_ids))
                break
    for i, iid in enumerate(item_ids):
        if iid not in catalog:
            raise ValueError(f"{sid}: unknown item: {iid}")
        row = catalog[iid]
        asset = row.get("asset", "")
        if not re.fullmatch(r"[a-z0-9_]+", asset) or row.get("sprite_tag") != asset:
            raise ValueError(f"{iid}: invalid or mismatched asset/sprite_tag")
        column, grid_row = i % cols, i // cols
        cell = checked_box(overrides.get(iid, [xs[column], ys[grid_row], xs[column + 1], ys[grid_row + 1]]), *source.size, iid)
        extraction_source = source
        if partition is not None:
            extraction_source, cell = isolate_source(source, partition, i + 1)
        try:
            icon, metadata = extract_icon(extraction_source, cell)
        except ValueError as exc:
            raise ValueError(f"{sid} cell {i + 1} ({iid}): {exc}") from exc
        record = {"item_id": iid, "asset": asset, "sprite_tag": asset, "sheet_id": sid,
                  "cell_index": i, "column": column, "row": grid_row, **metadata}
        if partition is not None:
            record["ownership_label"] = i + 1
        outputs.append((record, icon))
    blank_cells = []
    for i in range(len(item_ids), cols * rows):
        column, grid_row = i % cols, i // cols
        cell = (xs[column], ys[grid_row], xs[column + 1], ys[grid_row + 1])
        count = occupied_count(alpha_mask(source.crop(cell), POLICY["trim_alpha_threshold"])) if partition is None else 0
        if count > 8:
            raise ValueError(f"{sid}: unused cell {i + 1} contains {count} visible pixels; source/item count mismatch")
        blank_cells.append(i)
    stored_source = SOURCE_DIR / (sid + ".png")
    record = {
        "id": sid, "source": stored_source.relative_to(ROOT).as_posix(),
        "original_source": str(source_path), "source_sha256": sha256_bytes(source_bytes),
        "source_size": list(source.size), "columns": cols, "rows": rows,
        "grid_bounds": list(grid), "column_edges": xs, "row_edges": ys,
        "item_ids": item_ids, "blank_cell_indices": blank_cells,
        "generator": sheet.get("generator", "image_gen"), "prompt": sheet.get("prompt", ""),
        "generation_parameters": sheet.get("generation_parameters", {"transparent_background": True}),
    }
    if partition is not None:
        record["ownership_map"] = (SOURCE_DIR / (sid + "-cell-map.png")).relative_to(ROOT).as_posix()
        record["ownership_rgba_sha256"] = sha256_bytes(partition.tobytes())
        record["partition"] = {"method": "connected_components_by_grid_center", "alpha_threshold": 16,
                               "connectivity": 4, "minimum_component_pixels": 8, "minimum_item_pixels": 200,
                               "antialias_extension_source_pixels": 2, "groups": partition_groups}
    return SheetPlan(record, source_path, source_bytes, outputs, partition)


def preview(outputs: list[tuple[dict[str, Any], Image.Image]], catalog: dict[str, dict], path: Path) -> None:
    columns = 5
    cell_w, cell_h = 240, 130
    canvas = Image.new("RGB", (columns * cell_w, math.ceil(len(outputs) / columns) * cell_h), (28, 31, 35))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 11)
    except OSError:
        font = ImageFont.load_default()
    for i, (record, icon) in enumerate(outputs):
        x, y = (i % columns) * cell_w, (i // columns) * cell_h
        old_path = SPRITES / (record["asset"] + ".png")
        if old_path.exists():
            with Image.open(old_path) as old:
                old = old.convert("RGBA")
                old.thumbnail((64, 64), Image.Resampling.LANCZOS)
                canvas.paste(old, (x + 16 + (64 - old.width) // 2, y + 12 + (64 - old.height) // 2), old)
        canvas.paste(icon, (x + 132, y + 12), icon)
        draw.text((x + 16, y + 78), "Previous", font=font, fill=(157, 166, 172))
        draw.text((x + 132, y + 78), "Generated", font=font, fill=(222, 225, 218))
        name = catalog[record["item_id"]]["name"]
        draw.text((x + 8, y + 100), name[:36], font=font, fill=(223, 223, 212))
    path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(path)


def review_pages(catalog: dict[str, dict], directory: Path) -> list[dict[str, Any]]:
    """Publish manageable native-64px contact pages in canonical catalog order."""
    sys.path.insert(0, str(ROOT))
    from worldseed.content.item_catalog import ITEM_TYPE_LABELS, ordered_items
    ordered = ordered_items(list(catalog.values()))
    columns, page_size, cell_w, cell_h, header = 8, 72, 160, 132, 60
    directory.mkdir(parents=True, exist_ok=True)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 10)
        small = ImageFont.truetype("DejaVuSans.ttf", 8)
        title = ImageFont.truetype("DejaVuSans.ttf", 18)
    except OSError:
        font = small = title = ImageFont.load_default()
    pages = []
    for start in range(0, len(ordered), page_size):
        rows = ordered[start:start + page_size]
        page = len(pages) + 1
        canvas = Image.new("RGB", (columns * cell_w, header + math.ceil(len(rows) / columns) * cell_h), (24, 28, 32))
        draw = ImageDraw.Draw(canvas)
        draw.text((12, 10), f"WORLDSEED generated item art — page {page}", font=title, fill=(234, 232, 219))
        draw.text((12, 36), f"Items {start + 1}–{start + len(rows)} of {len(ordered)} • native 64px • canonical category/name order", font=font, fill=(161, 171, 176))
        for i, row in enumerate(rows):
            x, y = (i % columns) * cell_w, header + (i // columns) * cell_h
            draw.rectangle((x + 2, y + 2, x + cell_w - 3, y + cell_h - 3), outline=(49, 58, 64))
            with Image.open(SPRITES / (row["asset"] + ".png")) as raw:
                icon = raw.convert("RGBA")
            if icon.size != (64, 64):
                raise ValueError(f"{row['id']}: native review requires imported64px art")
            canvas.paste(icon, (x + (cell_w - 64) // 2, y + 4), icon)
            name_lines = [""]
            for word in row["name"].split():
                candidate = (name_lines[-1] + " " + word).strip()
                if font.getlength(candidate) > cell_w - 12:
                    name_lines.append(word)
                else:
                    name_lines[-1] = candidate
            if len(name_lines) > 2:
                raise ValueError(f"{row['id']}: review name requires a wider card")
            for j, line in enumerate(name_lines):
                draw.text((x + 6, y + 70 + j * 12), line, font=font, fill=(225, 226, 216))
            label = ITEM_TYPE_LABELS[row["category"]]
            draw.text((x + 6, y + 99), label, font=small, fill=(160, 171, 177))
            iid = row["id"]
            # Full IDs wrap deterministically; the review never drops identity.
            split = len(iid)
            while split > 0 and small.getlength(iid[:split]) > cell_w - 12:
                split -= 1
            draw.text((x + 6, y + 110), iid[:split], font=small, fill=(142, 151, 157))
            if split < len(iid):
                draw.text((x + 6, y + 119), iid[split:], font=small, fill=(142, 151, 157))
        destination = directory / f"dev64-items-page-{page:02d}.png"
        canvas.save(destination, optimize=True)
        pages.append({"page": page, "image": destination.name, "first_item": start + 1,
                      "last_item": start + len(rows), "item_ids": [row["id"] for row in rows],
                      "size": list(canvas.size), "icon_size": 64})
    write_json(directory / "dev64-items-review-index.json", {"catalog_items": len(ordered), "pages": pages})
    return pages


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def verify(provenance: Path, require_complete: bool) -> dict[str, Any]:
    data = json.loads(provenance.read_text(encoding="utf-8"))
    if data.get("extraction_policy") != POLICY:
        raise ValueError("unsupported provenance extraction policy")
    catalog = {row["id"]: row for row in json.loads(ITEMS.read_text(encoding="utf-8"))}
    sheet_map = {sheet["id"]: sheet for sheet in data["sheets"]}
    images = {}
    ownership_maps = {}
    for sid, sheet in sheet_map.items():
        source = ROOT / sheet["source"]
        if sha256_bytes(source.read_bytes()) != sheet["source_sha256"]:
            raise ValueError(f"{sid}: source provenance hash changed")
        with Image.open(source) as raw:
            images[sid] = raw.convert("RGBA")
        if "ownership_map" in sheet:
            with Image.open(ROOT / sheet["ownership_map"]) as raw:
                ownership_maps[sid] = raw.convert("L")
            if sha256_bytes(ownership_maps[sid].tobytes()) != sheet["ownership_rgba_sha256"]:
                raise ValueError(f"{sid}: source ownership map hash changed")
    hashes = {}
    for record in data["items"]:
        iid = record["item_id"]
        row = catalog.get(iid)
        if row is None or row["asset"] != record["asset"] or row["sprite_tag"] != record["sprite_tag"]:
            raise ValueError(f"{iid}: catalog changed from imported mapping")
        source = images[record["sheet_id"]]
        if "ownership_label" in record:
            source, isolated_bounds = isolate_source(source, ownership_maps[record["sheet_id"]], record["ownership_label"])
            if list(isolated_bounds) != record["cell_bounds"]:
                raise ValueError(f"{iid}: isolation bounds changed")
        recomputed, metadata = extract_icon(source, tuple(record["cell_bounds"]))
        if metadata != {key: record[key] for key in metadata}:
            raise ValueError(f"{iid}: extraction metadata mismatch")
        path = SPRITES / (record["asset"] + ".png")
        with Image.open(path) as actual:
            if actual.mode != "RGBA" or actual.size != (64, 64) or actual.tobytes() != recomputed.tobytes():
                raise ValueError(f"{iid}: output differs from generated source crop")
        if sha256_bytes(path.read_bytes()) != record["png_sha256"]:
            raise ValueError(f"{iid}: encoded sprite hash changed")
        digest = metadata["rgba_sha256"]
        if digest in hashes:
            raise ValueError(f"duplicate generated sprite pixels: {iid}, {hashes[digest]}")
        hashes[digest] = iid
    covered = {row["item_id"] for row in data["items"]}
    if len(covered) != len(data["items"]):
        raise ValueError("duplicate item provenance")
    declared = [iid for sheet in data["sheets"] for iid in sheet["item_ids"]]
    if set(declared) != covered or len(declared) != len(covered):
        raise ValueError("sheet/item source counts disagree")
    if require_complete and covered != set(catalog):
        raise ValueError(f"generated coverage incomplete: {len(covered)}/{len(catalog)}; missing {sorted(set(catalog) - covered)}")
    return {"sheets": len(sheet_map), "imported_items": len(covered), "catalog_items": len(catalog),
            "unique_rgba_hashes": len(hashes), "source_pixel_reproduction": "passed"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--sheet", action="append", default=[])
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--preview", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--review-pages", type=Path, help="write native64px catalog review pages in canonical order")
    args = parser.parse_args()
    if args.verify:
        report = verify(PROVENANCE, args.require_complete)
        if args.review_pages:
            catalog = {row["id"]: row for row in json.loads(ITEMS.read_text(encoding="utf-8"))}
            report["review_pages"] = len(review_pages(catalog, args.review_pages))
        if args.report:
            write_json(args.report, report)
        print(json.dumps(report))
        return 0
    if args.manifest is None:
        parser.error("--manifest is required for import")
    document = json.loads(args.manifest.read_text(encoding="utf-8"))
    if document.get("schema_version") != 1 or not isinstance(document.get("sheets"), list):
        raise ValueError("expected a schema_version=1 generation manifest")
    catalog = {row["id"]: row for row in json.loads(ITEMS.read_text(encoding="utf-8"))}
    wanted = set(args.sheet)
    definitions = [sheet for sheet in document["sheets"] if not wanted or sheet["id"] in wanted]
    if wanted - {sheet["id"] for sheet in definitions}:
        raise ValueError("unknown requested sheet IDs")
    plans = [plan_sheet(sheet, args.manifest, catalog) for sheet in definitions]
    if not plans:
        raise ValueError("no sheets selected")
    if len({plan.record["id"] for plan in plans}) != len(plans):
        raise ValueError("duplicate sheet IDs")
    outputs = [output for plan in plans for output in plan.outputs]
    if args.preview:
        preview(outputs, catalog, args.preview)
    existing = json.loads(PROVENANCE.read_text(encoding="utf-8")) if PROVENANCE.exists() else {
        "schema_version": 1, "extraction_policy": POLICY, "sheets": [], "items": []}
    if existing.get("extraction_policy") != POLICY:
        raise ValueError("existing provenance uses a different extraction policy")
    replacement_ids = {plan.record["id"] for plan in plans}
    previous_items = [row for row in existing["items"] if row["sheet_id"] not in replacement_ids]
    combined = previous_items + [record for record, _ in outputs]
    item_ids = [record["item_id"] for record in combined]
    if len(set(item_ids)) != len(item_ids):
        raise ValueError("an item is mapped to more than one generated source cell")
    hashes = [record["rgba_sha256"] for record in combined]
    if len(set(hashes)) != len(hashes):
        raise ValueError("generated outputs contain duplicate decoded RGBA pixels")
    if args.require_complete and set(item_ids) != set(catalog):
        raise ValueError(f"generated coverage incomplete: {len(item_ids)}/{len(catalog)}")
    report = {"selected_sheets": len(plans), "selected_items": len(outputs), "total_imported_items": len(combined),
              "catalog_items": len(catalog), "unique_rgba_hashes": len(set(hashes)), "validation": "passed"}
    if args.report:
        write_json(args.report, {**report, "items": [record for record, _ in outputs]})
    if args.validate_only:
        print(json.dumps(report))
        return 0
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    SPRITES.mkdir(parents=True, exist_ok=True)
    for plan in plans:
        destination = ROOT / plan.record["source"]
        if plan.source.resolve() != destination.resolve():
            temporary = destination.with_suffix(".png.tmp")
            temporary.write_bytes(plan.source_bytes)
            temporary.replace(destination)
        if plan.ownership is not None:
            destination = ROOT / plan.record["ownership_map"]
            temporary = destination.with_suffix(".png.tmp")
            plan.ownership.save(temporary, format="PNG", optimize=True)
            temporary.replace(destination)
        for record, icon in plan.outputs:
            destination = SPRITES / (record["asset"] + ".png")
            temporary = destination.with_suffix(".png.tmp")
            icon.save(temporary, format="PNG", optimize=True)
            record["png_sha256"] = sha256_bytes(temporary.read_bytes())
            temporary.replace(destination)
    existing["sheets"] = sorted([sheet for sheet in existing["sheets"] if sheet["id"] not in replacement_ids]
                                + [plan.record for plan in plans], key=lambda sheet: sheet["id"])
    existing["items"] = sorted(combined, key=lambda row: row["item_id"])
    write_json(PROVENANCE, existing)
    if args.review_pages:
        report["review_pages"] = len(review_pages(catalog, args.review_pages))
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
