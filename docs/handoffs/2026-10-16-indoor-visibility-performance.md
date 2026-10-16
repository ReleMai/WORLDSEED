# WORLDSEED — Indoor visibility/performance continuation (2026-10-16)

## Completed changes
- Scene capture builds bounded spatial indexes over *already-authorized* live and explored-memory rectangles. Every indoor furniture, stairs, floor pile, actor, wall and remembered prop can query candidate sight patches by rectangle instead of scanning all 1024 patches each time. Existing exact wall occlusion/scissors and deterministic ordering remain in force.
- Indoor GPU floor material draw batching uses pixel-exact cropped geometry and preserved world-aligned UVs for each half-metre tile. Consecutive same-material floor patches can share one OpenGL draw submission, preserving foreground/remembered blending classification and all visibility boundaries. Non-floor sprites continue to use their existing per-clip scissor.
- On a live-to-remembered transition, the last-seen immutable furniture/fixture art eases over 0.7 seconds to its normal 0.62 memory opacity. Actors are never retained as ghosts. No renderer knows about private rooms, hidden current positions or undiscovered objects. The transition is ephemeral and is neither saved nor simulation-owned.
- Optional profiler now distinguishes `gpu.scene_capture`, `gpu.command_preparation` and `gpu.world_draw` in its existing rolling runtime measurements. This allows a real Windows movement trace to separate LOS CPU cost from OpenGL draw cost.
- Added tests to verify index equivalence to full ordered scan over randomized fine-sight patches, hidden-room isolation, unchanged sprite scissor, memory identity/scope, final idle fade, UV geometry, and real GPU pixel/draw-call parity when EGL is available.

## Validation
- `tests.test_gpu_interior_smoothing` and `tests.test_gpu_floor_batch` are added to the regular W1/W2 Fast Gate suite, alongside `tests.test_gpu_interiors`. Existing privacy/visibility and persistent plan-memory regressions remain authoritative.
- On a known simple three-tile same-source reference, the new GPU branch is intended to render in one draw call rather than three without changing any pixels. Do not claim a specific FPS speedup until a hardware playtest confirms it.
- Windows GPU packaging from the earlier clip-index commit `aa24f2b` passed. A newer package is needed after the batching revision.
- No save schema, world generation, NPC logic, physics or gameplay time semantics were changed.

## Unfinished gameplay and visual requests
- Optimize remaining authoritative indoor visibility/fine-LOS sampling if profiler confirms it is still expensive.
- Author indoor directional shadows, daylight passing through actually modeled windows, room-specific art palettes, furniture outlines and smooth interior fog borders without disclosing hidden rooms.
- Improve roof silhouettes/eaves and door orientation with dedicated top-down assets beyond current generated build-material roofs.
- Allow other context-safe HUD buttons to interact while storage windows stay visible (Stalk/Normal/Crouch/Aggro already wired).
- Stress-test click-to-walk-and-pick-up with NPC obstructions, pack-full outcomes, path interruptions, and several close piles in a real Windows game.
- Complete a native Windows 20–60 second indoor movement performance capture before treating lag as resolved. Prefer an explicit timed report (p50/p95 capture/prepare/draw; GPU draw_calls; fps), not a screenshot or only a green CI test.
