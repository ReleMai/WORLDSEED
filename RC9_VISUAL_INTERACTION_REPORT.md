# WORLDSEED v1.0 RC9 — Visual Interaction Pass

## Purpose

RC9 continues the RC8 renderer transition without touching simulation authority, save format, world generation or deterministic RNG.

## Added

- presentation-only zoom presets through `+`, `-`, and `0`;
- sprite-cache invalidation when zoom changes;
- mouse hover hit-testing over the local map;
- contextual hover tooltips for terrain, resources, crops, structures, items, animals and known/unknown NPCs;
- unexplored-cell tooltip behavior that does not reveal hidden state;
- updated control strip documenting zoom controls.

## Invariants

- Hovering does not advance time.
- Hovering does not realize undiscovered regions.
- Hovering does not roll RNG.
- Zooming changes only presentation scale.
- ANSI terminal fallback remains intact.

## Next visual milestone

The next pass should replace the deterministic placeholder art with the detailed WORLDSEED art direction while preserving stable visual IDs and the manifest. That allows every sprite to be upgraded independently without changing gameplay data or saves.
