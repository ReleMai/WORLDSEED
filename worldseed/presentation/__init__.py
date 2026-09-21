"""Presentation adapters for WORLDSEED.

The simulation is renderer-agnostic.  Presentation converts stable content/state IDs
into visual IDs, sprites, glyph fallbacks, and window-space layouts.
"""
from .visuals import VisualRegistry, VisualRef

__all__ = ["VisualRegistry", "VisualRef"]
