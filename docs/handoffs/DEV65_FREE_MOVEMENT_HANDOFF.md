# Dev65 Free Movement Handoff

## Scope / modules changed
Implemented outdoor continuous free movement from the supplied `free_movement.py` / patch while adapting it to current WORLDSEED authority boundaries. Changes cover the movement subsystem, simulation bridge, NPC path traversal, state persistence, Pygame input/rendering, focused tests, and the existing realtime fast-gate step.

## Public APIs / contracts
`Simulation.set_free_movement_enabled()`, `Simulation.update_free_movement()`, and `Simulation.try_free_movement_step()` are the runtime integration points. Continuous interpolation never replaces tile authority: every player tile crossing still goes through `Simulation._move()`, preserving buildings, property locks, crossings, swimming, creatures, traps, stealth/noise, and other current movement consumers.

The Pygame backend consumes outdoor held WASD/arrow input continuously. Interior movement and the text-terminal backend retain their existing discrete/fixed-tick behavior.

## Persistent fields / migration
`LivingWorldState.player_fx/player_fy` and `NPCState.fx/fy` default to 0.5. Player fractions are explicitly serialized/deserialized; NPC fractions use existing dataclass map serialization. This is additive under save schema 3, so legacy saves load centered and no schema bump is required.

## RNG namespaces
None.

## Tests added / changed
`tests.test_free_movement` covers walk/sprint distance, authoritative boundary crossing, blocked-direction latching, NPC cached-path interpolation, and save round-trip defaults. The automatic fast gate now runs it beside realtime social-world regressions; compileall remains part of the same gate.

## Performance implications
Frame delta is capped at 100 ms. Pygame integrates at no more than roughly 60 Hz and redraws only when a fractional actor position changes. NPC work is limited to realized outdoor NPCs that already have cached local move paths; interpolation does not generate paths, hydrology, settlements, or routes.

## UI exposure
Outdoor Pygame movement is hold-to-move with diagonal normalization and Shift sprint. Actor sprites consume sub-tile fractions. Combat remains action-driven, and focus loss clears held motion.

## Known limitations
The local camera remains centered on the player's authoritative integer tile. Actor motion is sub-tile smooth, but the camera can still shift by one cell at a tile boundary. Camera interpolation is a separate presentation-only work unit.

## Next dependency
If sprint later consumes stamina or terrain changes locomotion speed, keep those costs in simulation authority and expose only read state to presentation.

## Dev65 follow-up: smooth outdoor camera (2026-10-10)

The Pygame outdoor camera now projects terrain, actors, and overlays from the same authoritative player tile plus persistent fractional offsets. One extra tile is drawn around each edge, clipped to the unchanged viewport to prevent panel bleed and blank strips. Hover picking now accounts for the shifted pixel origin, while weather snapshots and UI panels continue using the fixed viewport. No simulation, save-schema, or generation contract changes.
