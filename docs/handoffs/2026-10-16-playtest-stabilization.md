# 2026-10-16 WORLDSEED playtest stabilization (part 1)

- Hunger and thirst HUD numbers show remaining reserves (100 minus depletion), consistent with existing bar fill and simulation semantics.
- Container store, take and steal outside combat resolve immediately, without a transfer timer or world-time charge. Stalk checks remain authoritative, so failed theft no longer waits before the warning.
- Container panels register live stance controls outside their floating bounds. Switching Stalk, Normal, Crouch or Aggro stays inside the same panel; the next transfer uses that stance.
- Static indoor OpenGL scenes stop idly submitting the same GPU sprites at 20 FPS. Movement, state changes and resizing still redraw.
- Subsequent work units: top-down building/collision layering and cardinal door art; sun shadows; soft sight-edge mask; object-memory transitions; action-based world-item pathfinding.
