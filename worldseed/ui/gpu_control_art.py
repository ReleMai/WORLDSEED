"""Authored illustrated controls for the main GPU HUD.

Callers cache the returned surface at their bounded set of display sizes. Loading
art is observational and does not depend on simulation or open a display.
"""
from __future__ import annotations

from pathlib import Path
from types import MappingProxyType


_ROOT = Path(__file__).resolve().parents[1] / 'assets' / 'sprites' / 'ui' / 'gpu_controls'
ICON_PATHS = MappingProxyType({key: _ROOT / (key + '.png') for key in (
    'inventory', 'crafting', 'build', 'health', 'map', 'actions', 'world', 'look',
    'help', 'pause', 'normal', 'stalk', 'crouch', 'aggressive', 'confirm', 'cancel',
)})


def load_icon(pg, key: str, size: int):
    """Load one transparent art icon at a bounded square pixel size.

    Unknown control keys fail clearly; a UI caller may render its textual label
    if an optional asset cannot be loaded. No fallback glyph is manufactured.
    """
    if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= 256:
        raise ValueError('GPU control icon size must be an integer from 1 to 256')
    path = ICON_PATHS[str(key).lower()]
    source = pg.image.load(str(path))
    return pg.transform.smoothscale(source, (size, size))
