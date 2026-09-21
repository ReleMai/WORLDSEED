# RC11 Item Asset and Performance Report

## Summary

This RC11 pass tackled three things the latest feedback called out:

1. individual item art quality
2. delayed tile-hover inspection updates
3. lingering pygame window lag

## Item art pass

Because the image pipeline available in-chat can only emit ten finished images per batch, this release focuses on the first curated item-art wave rather than all 105 items at once. The following item sprite files were replaced with better standalone assets:

- `worldseed/assets/sprites/items/stone.png`
- `worldseed/assets/sprites/items/wood.png`
- `worldseed/assets/sprites/items/brush.png`
- `worldseed/assets/sprites/items/fiber.png`
- `worldseed/assets/sprites/items/berries.png`
- `worldseed/assets/sprites/items/stone_flake.png`
- `worldseed/assets/sprites/items/plant_cordage.png`
- `worldseed/assets/sprites/items/stone_knife.png`
- `worldseed/assets/sprites/items/stone_axe.png`
- `worldseed/assets/sprites/items/wooden_spear.png`

All ten are standalone transparent PNG sprites; no sheet-only authoring was introduced. Atlases were rebuilt only as a packaging convenience for existing tooling.

## Hover-box delay fix

The pygame backend previously absorbed `MOUSEMOTION` events without requesting a redraw, so the hover box often updated only after the next keyboard/gameplay event. RC11 changes that behavior so mouse movement now returns an internal hover event immediately and the current frame redraws right away.

## Optimization work

### Render-side improvements

- Added a cached terrain/discovery base layer in `worldseed/ui/pygame_terminal.py` so repeated redraws do not repaint every static tile from scratch.
- Reduced per-frame indexing cost by building object lookup tables only for the visible viewport, instead of every global object in the simulation state.
- Reused resolved NPC/species special sprite collections within the frame instead of repeatedly re-fetching them in the inner tile loop.
- Cleared the terrain cache on resize/zoom changes to keep the cache coherent.
- Limited the base-layer cache size to prevent unbounded growth.

### Input-side improvement

- Hover motion is now coalesced by draining queued `MOUSEMOTION` events and using only the newest position, which prevents stale box movement when the mouse is moved quickly.

## Validation

Commands run:

```bash
python -m compileall worldseed
PYTHONPATH=. python tools/audit_visuals.py
PYTHONPATH=. python tools/build_sprite_atlases.py
PYTHONPATH=. python tools/bench_movement.py
```

Observed movement benchmark after the RC11 changes:

- `move_ms`: `0.639`
- `move_plus_render_ms`: `3.54`

## Next recommended pass

Continue the individual item-art overhaul in batches, prioritizing the rest of the primitive survival loop, then common food/resources, then crafted gear.
