# RC12 Responsive Renderer Report

## Problem reproduced in code

RC11 still routed every mouse-tile change back through `run_game()`. That made a hover update pay for a complete `present_game()` even though simulation state had not changed. On a busy viewport this meant rebuilding/rendering terrain, natural resources, object dictionaries, sidebar text and the whole display simply to move the inspection box.

## Hover architecture fix

RC12 keeps hover entirely inside `PygameTerminal.read_key()`. Mouse-motion events are coalesced to the newest pointer position. When the pointer crosses into a different map tile, the backend:

1. restores only the old tooltip/highlight damage rectangle from a clean map snapshot;
2. looks up information for the new tile;
3. draws a one-tile highlight and tooltip;
4. calls `pygame.display.update()` only for the union of the old/new damaged rectangles;
5. continues waiting for actual gameplay input without returning to the application/simulation loop.

Movement inside the same tile produces no redraw at all. Menus explicitly clear the gameplay hover snapshot so stale map pixels cannot be repainted over menu screens.

## Renderer optimizations

- Terrain/discovery cache is keyed by viewport + world revision and patches only cells newly discovered since the prior frame.
- Natural-resource cache is keyed by viewport + resource revision/day and patches only newly visible cells. Harvesting/regrowth invalidates the cache through a resource revision counter.
- Terrain edits invalidate through a monotonic world revision counter rather than `dirty_tiles` length.
- Main sprite pass builds a union of occupied overlay cells and renders those in y/x order; empty viewport cells are no longer visited by the dynamic overlay loop.
- NPC/species path pools and known-NPC IDs are resolved once per frame.
- Nearby sidebar entries reuse viewport-local entity dictionaries.
- Full-window alpha scanline blending is disabled by default because it added a large blended surface operation every frame without gameplay value.

## Simulation-side optimization

Discovery LOS was the dominant movement cost in profiling. `_discover()` now creates a per-pass occlusion cache shared across Bresenham rays. Repeated rays reuse whether intermediate cells block sight instead of repeating terrain, natural-resource and building queries.

Built-in 400-step benchmark:

- RC11 documented movement: ~0.639 ms/step
- RC12 movement: ~0.351 ms/step
- RC11 documented movement + terminal render: ~3.54 ms/step
- RC12 movement + terminal render: ~3.125 ms/step

The container does not include pygame-ce and has no package-network access, so a reliable pygame FPS benchmark cannot be executed here. The pygame fast path is covered structurally by RC12 regression tests, while existing visual, worldgen, system, persistence and replay suites remain passing.

## Compatibility

- Save schema: unchanged (`3`)
- Worldgen: unchanged (`4`)
- Natural-resource generation: unchanged (`3`)
- Existing RC10/RC11 saves remain compatible.
