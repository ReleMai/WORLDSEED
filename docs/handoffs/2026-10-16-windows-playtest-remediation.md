# WORLDSEED October 16 — Windows gameplay visual / interaction remediation

## User-reported symptoms and changes made
- Player painted under exterior building art: adjusted grounded depth at the shell's southern edge.
- Side-facing facade roofs and empty black centers: replaced the giant fitted front-elevation sprite with a bounded top-down roof compositor using existing eight build-mode roof materials. Exact footprint tiles get connected eaves; absent courtyard tiles remain transparent. Doors are placed and oriented for north/east/south/west entrance cells. Authoritative building access, storage, physical footprints and settlements are unchanged.
- Hunger/thirst reserves: GPU HUD labels now present `100 - depletion`, consistent with existing filled bar and gameplay semantics.
- Container transfer delay: store/take/steal commands outside combat have no simulated wait or animated timer. Failed Stalk prerequisites are reported immediately. Lock, witness and access checks remain in simulation code.
- Container HUD interactivity: storage window draws/registers stance targets outside the floating panel, and handles `UI_STANCE:*` without closing. Other main toolbar panels remain modal.
- Slow idle interior GPU redraw: suppress redundant fixed indoor world renders on idle, retaining redraw on gameplay changes, resize and smoke mode. This is not a guarantee of acceptable *moving* FPS.
- Click-to-pickup: right-click a visible nonadjacent ground pile for a bounded `Move over` action. Optional `Pick nearby of same type` checks at most eight nearby visible piles. Each movement step is still handled by the authoritative engine; stops on new combat/blocked route. No hidden/unprepared route discovery, max 24 steps.
- Outdoor jagged sight: added a fragment shader alpha falloff *inside* currently visible ground tiles where neighboring tiles are not visible. Unknown terrain remains undisclosed; known memory stays separate.
- Outdoor daylight shadows: cast daylight-dependent player contact shadow and roof silhouette projected onto *only* admitted outdoor ground; dawn/dusk longer, night disabled. Does not yet provide physically simulated vertical shadow casting in every environment.

## Remaining scoped work
- Interior active-movement profiling and stronger draw batching; current optimization only suppresses idle GPU frames.
- Continuous time-based remembered-object fade at interior visibility boundary (current snapshot switches directly between live/remembered visual classes).
- Interior fog edge gradients, light-shadow polish, window/door variants and authored top-down eaves/roofs beyond the current material-based procedural compositor.
- Outdoor sun shadow occlusion by trees/terrain and full physically accurate solar casting.
- Broader live UI interactions while storage is open (only stance buttons are now wired).
- Stress/playtest-click verification of pile-specific pickup options, pack capacity, NPC movement, route interruption, and theft during pathfinding.

## Validation and reproduction
- New tests: `tests.test_auto_pickup`; expanded `tests.test_gpu_buildings`, `tests.test_gpu_live_materials`, `tests.test_gpu_hud`.
- Existing `tests.test_gpu_house_alignment` updated for current top-down and short door art: no facade-specific tall door projections.
- GitHub Fast Gate tests the new route suite with the live GPU visibility contracts.
- Keep full Windows GPU and Windows Playtest packaging evidence for user testing. Do not treat CI passing as a substitute for measuring real Windows indoor movement latency.
- For manual review: approach every door side, walk directly south of the southern threshold, explore and leave a furnished interior, check reserve labels, open stolen storage and switch Stalk without closing, take and deposit stacks without timing, right-click pickup a reachable visible pile then same-item piles, confirm sunlight shadow changes by time of day and unknown cells never appear.

## Continuation priorities
1. Await the latest Fast Gate after all commits, inspect every failed job and fix failures before claiming a clean release.
2. Verify current Windows candidate was packaged after rendering and UI changes; repack if it predates any code.
3. Profile an actual Windows interior walk (GPU draw calls, per-frame LOS, memory clips, SDL/GPU timings).
4. Implement stable interpolated object-memory fades without leaking current actor/prop state through walls.
5. Continue build-mode architecture improvements (top-down roof/door assets, sun casts, soft indoor visibility).
