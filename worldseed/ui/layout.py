from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Layout:
    width: int
    height: int
    mode: str
    map_width: int
    map_height: int
    sidebar_width: int
    footer_rows: int


def compute_layout(width: int, height: int, density: str = 'dense') -> Layout:
    """Return a terminal-safe layout that never exceeds the actual viewport."""
    width = max(1, int(width))
    height = max(1, int(height))
    if width < 60 or height < 18:
        return Layout(width, height, 'tiny', max(1, width - 4), max(1, height - 6), 0, 3)

    if width >= 124 and height >= 28 and density == 'dense':
        sidebar = min(38, max(32, width // 3))
        map_width = width - sidebar - 5
        mode = 'wide'
        footer = 4
    elif width >= 88:
        sidebar = 0
        map_width = width - 4
        mode = 'standard'
        footer = 5
    else:
        sidebar = 0
        map_width = width - 4
        mode = 'compact'
        footer = 4

    map_width = max(21, map_width)
    if map_width % 2 == 0:
        map_width -= 1
    map_height = max(7, height - footer - 2)
    if map_height % 2 == 0:
        map_height -= 1
    return Layout(width, height, mode, map_width, map_height, sidebar, footer)


def screen_width(columns: int, preferred: int = 112) -> int:
    """Width for modal/full-screen records without forcing terminal wrapping."""
    if columns < 44:
        return max(20, columns)
    return max(42, min(preferred, columns - 2))


def centered_tile_grid(width: int, height: int, tile_px: int) -> tuple[int, int, int, int]:
    """Odd tile counts keep the player's cell exactly at the viewport center.

    Returns columns, rows and pixel insets; partial edge tiles are excluded.
    """
    if tile_px <= 0 or width < tile_px or height < tile_px:
        raise ValueError('viewport must contain at least one positive-sized tile')
    cols, rows = width // tile_px, height // tile_px
    cols -= 1 - cols % 2
    rows -= 1 - rows % 2
    return cols, rows, (width - cols * tile_px) // 2, (height - rows * tile_px) // 2


def regional_grid(width: int, height: int) -> tuple[int, int, int, int, int]:
    """Bounded strategic overview: columns, rows, cell size, x/y inset."""
    width, height = max(1, width), max(1, height)
    cols, rows = (13 if width >= 1300 else 9), (9 if height >= 850 else 7)
    cols, rows = min(cols, width), min(rows, height)
    cols -= 1 - cols % 2
    rows -= 1 - rows % 2
    cell = max(1, min(width // cols, height // rows))
    return cols, rows, cell, (width - cols * cell) // 2, (height - rows * cell) // 2
