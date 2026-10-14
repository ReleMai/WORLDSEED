"""M3 shared visual language for Pygame windows and controls.

Drawing helpers are observational: they cannot register clickable regions,
change navigation, consume simulation RNG, or commit a game command.
"""
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


FONT_SIZES = MappingProxyType({'body': 17, 'small': 14, 'title': 21})
PANEL_METRICS = MappingProxyType({'header_height': 42, 'content_top': 52,
                                  'side_padding': 16, 'footer_inset': 39})
PANEL_HELP = MappingProxyType({
    'inventory_unified': 'Select item · Wheel scrolls · Arrows navigate · Shift-click stores · Esc closes',
    'container_inventory': 'Shift-click transfers stack · Right-click actions · Drag title · Esc closes',
    'crafting': 'Select recipe · Wheel scrolls · Inspect requirements · Drag title · Esc closes',
    'salvaging': 'Select salvage · Review recovery · Drag title · Esc closes',
    'homestead_styles': 'Arrow keys browse styles · Enter selects · Drag title · Esc closes',
    'homestead_depot': 'Click materials to deposit · Build when ready · Drag title · Esc closes',
    'npc_profile': 'Select a tab · Drag title · Resize corner · Esc closes',
    'npc_dialogue': 'Select dialogue · Arrows navigate · Esc returns to previous topic',
})


def panel_help_text(panel_id: str | None, explicit: str | None = None) -> str:
    """Display contextual instructions without mutating navigation state."""
    if explicit:
        return str(explicit)
    return PANEL_HELP.get(str(panel_id), 'Drag title · Resize corner · Esc closes')


def draw_panel_focus_outline(pg, screen, rect, colors) -> None:
    """Extra inner border: active-window feedback beyond color alone."""
    pg.draw.rect(screen, colors['edge_hi'], rect.inflate(-6, -6), 1, border_radius=6)


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

def draw_floating_panel_frame(pg, screen, rect, colors) -> None:
    """Draw one retained frame for inventory, crafting, salvage and building.

    Paint only. Caller owns drag/resize hit regions, focus and simulation.
    """
    pg.draw.rect(screen, (0, 0, 0), pg.Rect(rect.x + 6, rect.y + 7, rect.w, rect.h), border_radius=8)
    pg.draw.rect(screen, (18, 23, 24), rect, border_radius=8)
    pg.draw.rect(screen, (99, 86, 61), rect, 2, border_radius=8)
    pg.draw.rect(screen, (31, 38, 37), rect.inflate(-10, -10), 1, border_radius=5)
    pg.draw.rect(screen, colors['panel2'], pg.Rect(rect.x, rect.y, rect.w, 42), border_radius=8)
    pg.draw.line(screen, colors['edge'], (rect.x, rect.y + 42), (rect.right, rect.y + 42), 1)
    pg.draw.line(screen, colors['accent'], (rect.x + 14, rect.y + 42),
                 (rect.x + min(rect.w - 14, 150), rect.y + 42), 2)


def button_style(colors, *, hovered=False, enabled=True, prominent=False,
                 destructive=False, context='general') -> tuple:
    """Return fill, border, text and stroke for the button's semantic state."""
    if context not in ('general', 'homestead'):
        raise ValueError('unknown button context')
    if not enabled:
        return (30, 34, 34), colors['edge'], colors['muted'], 1
    if destructive:
        return ((79, 38, 38) if hovered else (61, 34, 34),
                colors['danger'], colors['text'], 2)
    if context == 'homestead':
        fill = ((92, 85, 56) if hovered else (76, 72, 51)) if prominent else (
            (54, 62, 57) if hovered else (43, 49, 47))
        return fill, colors['accent'] if prominent else colors['edge'], colors['text'], 2 if prominent else 1
    return ((43, 48, 48) if hovered else colors['panel2'],
            colors['accent'] if hovered else colors['edge_hi'], colors['text'], 1)


def draw_button_background(pg, screen, rect, colors, *, hovered=False,
                           enabled=True, prominent=False, destructive=False,
                           context='general') -> tuple[int, int, int]:
    """Paint button chrome only; click targets remain owned by the caller."""
    fill, edge, text_color, stroke = button_style(
        colors, hovered=hovered, enabled=enabled,
        prominent=prominent, destructive=destructive, context=context)
    pg.draw.rect(screen, fill, rect, border_radius=5)
    pg.draw.rect(screen, edge, rect, stroke, border_radius=5)
    return text_color
