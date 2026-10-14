"""Shared M3 palette and retained menu frame. Pure presentation only."""
from __future__ import annotations

from types import MappingProxyType

DEFAULT_PALETTE = MappingProxyType({
    'bg': (13, 16, 18),
    'panel': (22, 26, 29),
    'panel2': (28, 33, 37),
    'edge': (66, 77, 81),
    'edge_hi': (122, 139, 139),
    'text': (222, 226, 220),
    'muted': (150, 160, 157),
    'accent': (195, 154, 77),
    'danger': (190, 76, 69),
    'good': (101, 158, 99),
})


def palette() -> dict[str, tuple[int, int, int]]:
    """Each renderer receives its own palette instance."""
    return dict(DEFAULT_PALETTE)


def draw_standard_menu_frame(pg, screen, rect, colors) -> None:
    """Draw existing menu card identically without input or simulation changes."""
    shadow = pg.Surface((rect.w + 16, rect.h + 16), pg.SRCALPHA)
    pg.draw.rect(shadow, (0, 0, 0, 110), shadow.get_rect(), border_radius=12)
    screen.blit(shadow, (rect.x - 8, rect.y + 5))
    pg.draw.rect(screen, (25, 31, 31), rect, border_radius=8)
    pg.draw.rect(screen, (119, 105, 72), rect, 2, border_radius=8)
    pg.draw.rect(screen, (57, 72, 67), rect.inflate(-12, -12), 1, border_radius=5)
    pg.draw.line(screen, colors['accent'], (rect.x + 26, rect.y + 8),
                 (rect.right - 26, rect.y + 8), 2)
