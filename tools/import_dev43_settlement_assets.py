from __future__ import annotations

"""Slice and normalize the authored Dev43 settlement expansion atlases."""

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "artifacts" / "source-art"
SPRITES = ROOT / "worldseed" / "assets" / "sprites"


def _cell(sheet: Image.Image, columns: int, rows: int, index: int) -> Image.Image:
    column = index % columns
    row = index // columns
    left = round(column * sheet.width / columns)
    right = round((column + 1) * sheet.width / columns)
    top = round(row * sheet.height / rows)
    bottom = round((row + 1) * sheet.height / rows)
    return sheet.crop((left, top, right, bottom))


def _normalize(cell: Image.Image, size: tuple[int, int], *, ground: bool = False) -> Image.Image:
    cell = cell.convert("RGBA")
    bbox = cell.getchannel("A").getbbox()
    if bbox is None:
        raise ValueError("generated atlas cell has no visible pixels")
    content = cell.crop(bbox)
    inset = 0 if ground else max(4, min(size) // 18)
    max_width = max(1, size[0] - inset * 2)
    max_height = max(1, size[1] - inset * 2)
    scale = min(max_width / content.width, max_height / content.height)
    resized = content.resize(
        (max(1, round(content.width * scale)), max(1, round(content.height * scale))),
        Image.Resampling.LANCZOS,
    )
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    x = (size[0] - resized.width) // 2
    y = size[1] - inset - resized.height
    if ground:
        y = (size[1] - resized.height) // 2
    canvas.alpha_composite(resized, (x, y))
    return canvas


def _save(image: Image.Image, relative: str) -> None:
    path = SPRITES / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, optimize=True)


def import_workshops() -> None:
    sheet = Image.open(SOURCE / "dev43_workshop_atlas.png")
    names = (
        "mine_entrance", "quarry_ground", "iron_ore_pile", "mine_shed",
        "farm_shed", "field_fence", "field_fence_corner", "field_gate",
        "plowed_soil", "logging_hut", "logging_tool_rack", "timber_stack",
        "animal_pen_fence", "animal_pen_gate", "livestock_trough", "hay_rack",
    )
    ground_names = {"quarry_ground", "plowed_soil"}
    for index, name in enumerate(names):
        ground = name in ground_names
        size = (192, 192) if ground else (256, 256)
        _save(_normalize(_cell(sheet, 4, 4, index), size, ground=ground), f"settlement/dev43/{name}.png")


def import_crops() -> None:
    sheet = Image.open(SOURCE / "dev43_crops_atlas.png")
    for row, crop in enumerate(("corn", "pumpkin")):
        for stage in range(3):
            image = _normalize(_cell(sheet, 5, 2, row * 5 + stage), (128, 128))
            _save(image, f"crops/{crop}/stage_{stage}.png")
        _save(_normalize(_cell(sheet, 5, 2, row * 5 + 3), (128, 128)), f"items/{crop}.png")
        _save(_normalize(_cell(sheet, 5, 2, row * 5 + 4), (128, 128)), f"items/{crop}_seed.png")


def import_livestock() -> None:
    sheet = Image.open(SOURCE / "dev43_livestock_atlas.png")
    for column, animal in enumerate(("pig", "cow", "chicken", "sheep")):
        for pose in range(2):
            image = _normalize(_cell(sheet, 4, 2, pose * 4 + column), (320, 256))
            _save(image, f"species/domestic/{animal}_{pose}.png")


def import_logging_trees() -> None:
    sheet = Image.open(SOURCE / "dev43_logging_trees_atlas.png")
    for column, name in enumerate(("logging_sapling", "logging_managed_tree")):
        _save(
            _normalize(_cell(sheet, 2, 1, column), (256, 320)),
            f"settlement/dev43/{name}.png",
        )


def main() -> None:
    import_workshops()
    import_crops()
    import_livestock()
    import_logging_trees()
    print("Imported 18 workshop, 10 crop/item, and 8 livestock sprites.")


if __name__ == "__main__":
    main()
