"""Import Dev42 character sheets into normalized, tile-safe actor sprites.

The generated source sheets are retained under ``artifacts/source-art``. Each
active actor sprite is cropped to its own alpha component, scaled to a common
height, centered on a 160x256 canvas, and anchored to the same foot baseline.
"""

from __future__ import annotations

from collections import deque
import json
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
CANVAS_SIZE = (160, 256)
CONTENT_HEIGHT = 232
CONTENT_MAX_WIDTH = 144
FOOT_BASELINE = 248
ALPHA_THRESHOLD = 8
GRID_COLUMNS = 5
GRID_ROWS = 2

SHEETS = {
    ("player", "male"): ROOT / "artifacts/source-art/dev42_player_male_sheet.png",
    ("player", "female"): ROOT / "artifacts/source-art/dev42_player_female_sheet.png",
    ("npc", "male"): ROOT / "artifacts/source-art/dev42_npc_male_sheet.png",
    ("npc", "female"): ROOT / "artifacts/source-art/dev42_npc_female_sheet.png",
}


def _largest_alpha_component(image: Image.Image) -> Image.Image:
    """Keep the cell's main figure and discard neighboring-cell fragments."""

    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    width, height = rgba.size
    solid = bytearray(1 if value >= ALPHA_THRESHOLD else 0 for value in alpha.tobytes())
    visited = bytearray(width * height)
    largest: list[int] = []

    for start, value in enumerate(solid):
        if not value or visited[start]:
            continue
        visited[start] = 1
        queue = deque([start])
        component: list[int] = []
        while queue:
            index = queue.popleft()
            component.append(index)
            x = index % width
            y = index // width
            if x and solid[index - 1] and not visited[index - 1]:
                visited[index - 1] = 1
                queue.append(index - 1)
            if x + 1 < width and solid[index + 1] and not visited[index + 1]:
                visited[index + 1] = 1
                queue.append(index + 1)
            if y and solid[index - width] and not visited[index - width]:
                visited[index - width] = 1
                queue.append(index - width)
            if y + 1 < height and solid[index + width] and not visited[index + width]:
                visited[index + width] = 1
                queue.append(index + width)
        if len(component) > len(largest):
            largest = component

    if not largest:
        raise ValueError("sprite cell contains no visible alpha component")

    kept_alpha = bytearray(width * height)
    original_alpha = alpha.tobytes()
    for index in largest:
        kept_alpha[index] = original_alpha[index]
    rgba.putalpha(Image.frombytes("L", (width, height), bytes(kept_alpha)))
    bounds = rgba.getchannel("A").getbbox()
    if bounds is None:
        raise ValueError("sprite component has an empty alpha bound")
    return rgba.crop(bounds)


def _normalize_actor(image: Image.Image) -> Image.Image:
    actor = _largest_alpha_component(image)
    source_width, source_height = actor.size
    scale = min(CONTENT_HEIGHT / source_height, CONTENT_MAX_WIDTH / source_width)
    size = (
        max(1, round(source_width * scale)),
        max(1, round(source_height * scale)),
    )
    actor = actor.resize(size, Image.Resampling.LANCZOS)

    # Remove resampling-only transparent margins before the final placement.
    alpha = actor.getchannel("A")
    bounds = alpha.point(lambda value: 255 if value >= ALPHA_THRESHOLD else 0).getbbox()
    if bounds is None:
        raise ValueError("normalized actor became transparent")
    actor = actor.crop(bounds)

    canvas = Image.new("RGBA", CANVAS_SIZE, (0, 0, 0, 0))
    x = (CANVAS_SIZE[0] - actor.width) // 2
    y = FOOT_BASELINE - actor.height
    if x < 0 or y < 0:
        raise ValueError(f"normalized actor does not fit the canvas: {actor.size}")
    canvas.alpha_composite(actor, (x, y))
    return canvas


def _cell(sheet: Image.Image, column: int, row: int) -> Image.Image:
    width, height = sheet.size
    return sheet.crop(
        (
            round(column * width / GRID_COLUMNS),
            round(row * height / GRID_ROWS),
            round((column + 1) * width / GRID_COLUMNS),
            round((row + 1) * height / GRID_ROWS),
        )
    )


def import_sheet(kind: str, sex: str, source: Path) -> list[str]:
    sheet = Image.open(source).convert("RGBA")
    destination = ROOT / "worldseed/assets/sprites/characters" / kind / sex
    destination.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []

    for index in range(GRID_COLUMNS * GRID_ROWS):
        row, column = divmod(index, GRID_COLUMNS)
        sprite = _normalize_actor(_cell(sheet, column, row))
        path = destination / f"{index:02d}.png"
        sprite.save(path, optimize=True)
        paths.append(path.relative_to(ROOT / "worldseed").as_posix())
    return paths


def build_preview(groups: list[tuple[str, list[str]]]) -> None:
    cell_width = CANVAS_SIZE[0]
    row_height = CANVAS_SIZE[1] + 28
    preview = Image.new(
        "RGBA",
        (cell_width * 10, row_height * len(groups)),
        (12, 16, 18, 255),
    )
    draw = ImageDraw.Draw(preview)
    for row, (label, paths) in enumerate(groups):
        top = row * row_height
        draw.text((8, top + 7), label, fill=(218, 164, 66, 255))
        for column, raw in enumerate(paths):
            sprite = Image.open(ROOT / "worldseed" / raw).convert("RGBA")
            preview.alpha_composite(sprite, (column * cell_width, top + 28))
    preview.save(ROOT / "artifacts/dev42_character_normalization_preview.png", optimize=True)


def main() -> None:
    imported = {
        key: import_sheet(key[0], key[1], source)
        for key, source in SHEETS.items()
    }

    manifest_path = ROOT / "worldseed/assets/visuals.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    player_male = imported[("player", "male")]
    player_female = imported[("player", "female")]
    npc_male = imported[("npc", "male")]
    npc_female = imported[("npc", "female")]
    manifest["player_variants"] = {
        "male": player_male,
        "female": player_female,
    }
    manifest["npc_variants"] = npc_male + npc_female
    manifest["npc_variant_sexes"] = ["male"] * 10 + ["female"] * 10
    manifest["special"]["player"] = player_male[0]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    build_preview(
        [
            ("PLAYER MALE", player_male),
            ("PLAYER FEMALE", player_female),
            ("NPC MALE", npc_male),
            ("NPC FEMALE", npc_female),
        ]
    )
    print("Imported 20 player and 20 NPC sprites on 160x256 tile-safe canvases")


if __name__ == "__main__":
    main()
