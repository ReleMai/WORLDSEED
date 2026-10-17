# Indoor darkzone, visibility cost and roof player reveal

Baseline: canonical main `06d047fd02f3afe571b3c7a6c95824c0716e03d1`.

## Scope and public behavior

- Indoor unseen-space boundaries receive a soft inward penumbra. Coarse and fine sight patches cancel their shared edges, so the floor grid does not acquire artificial shadows. Unknown geometry remains black and no private-room data is supplied to the renderer.
- Furniture contact/cast shadows use lower opacity while retaining their existing physical anchors and light direction.
- A player standing beneath an admitted roof keeps the entire sprite, including the head. Previously only the foot cell was admitted to projection, clipping away the upper body. Only the player's own body receives this exception; terrain, NPCs, resources and roof hit/collision cells retain their existing admission. Roofs keep the tree-style local alpha of 0.08.

## Modules and contracts

`interior_visibility.py` retains exact convex-fan wall tests, with signed wall support corners instead of four allocated wall projections, validation once per request, cached probe rays and an ambient-reach shortcut. Its two-entry immutable-value cache includes player coordinates, viewport, wall geometry, plan dimensions, ambient intensity and up to 64 light sources. It retains no plan or simulation references. Time need not be in the key because callers supply authoritative ambient and the light sampler otherwise depends only on the supplied sources and geometry.

`interior_darkzone.py` consumes authorized screen clips only. Four immutable gradient textures are shared. Fog draws use the existing exact clipped-mesh batch in `gl_worldspace.py`; a maximum of 512 quads and the remaining frame budget prevent pathological visibility from overflowing the renderer.

`gpu_interiors.py` integrates fog/shadow presentation. `gpu_scene_bridge.py` preserves the player's full roof-covered body. The new regression module is included in Fast Gate.

Persistent fields/migration: none. RNG namespaces: none. Save schema, world generation, collision, discovery and simulation time are unchanged. No new production dependency.

## Verification and performance

- Complete pinned snapshot verified against every recursive Git tree blob before edits; unrelated dirty original checkout preserved.
- Compileall passed over `worldseed`, `tools`, `tests`.
- Broader targeted run: 91 tests completed successfully, 4 optional EGL cases skipped. After final visibility/budget refinements, 52 affected regressions completed successfully, 3 optional EGL cases skipped. The new native Windows OpenGL pixel test actually ran.
- Randomized exact SAT parity over 1,500 convex polygon/wall pairs, cache invalidation, mixed coarse/fine edge cancellation, fog bounds/budgets and full roof player-body admission regressions passed.
- Focused moving-sight comparison across 40 positions: original and optimized output tuples identical; median 4.18 ms -> 2.37 ms, p95 4.72 ms -> 2.69 ms (about 43% lower median CPU cost). These are sight-query timings, not FPS.
- A generated production interior was also checked across 30 positions before the final ambient shortcut: identical output, median 24.02 -> 18.51 ms. Do not confuse this different, more complex geometry with the smaller focused fixture.
- Native Windows WGL reference rendering on NVIDIA GeForce RTX 4060 Ti, 960x640, 90 legal prepared-interior positions: capture p50/p95 18.22/19.02 ms; preparation 8.43/10.42 ms; draw plus GPU finish 5.16/7.28 ms; median 107 draw submissions. Source PNG art and real renderer used. Screenshot and JSON are under `docs/evidence/indoor-darkzone/`.

## Limits and next dependency

This is targeted development validation and a native offscreen reference-scene trace, not an interactive saved-game movement/door-transition FPS capture or full release validation. Fine LOS remains conservative and its geometric silhouette is still exact. Extremely fragmented views may exhaust the optional fog budget and retain some hard edges. Remaining indoor CPU work is still measurable; a longer in-game trace should guide the next performance pass. The updated runnable source is the clean current-main snapshot; the stale original checkout was not overwritten.
