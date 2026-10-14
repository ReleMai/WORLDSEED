# WORLDSEED M2 high-resolution terrain performance — bounded follow-up

**Baseline:** [M2 closeout](EARLY_ACCESS_M2_ENGINE_CLOSEOUT.md), code `ab3f03530dac9fdac0e66ff4a30d18a9f56bea0e`, seven-job Fast Gate green. **Current code:** [`20846c0`](https://github.com/ReleMai/WORLDSEED/commit/20846c0ddc7eb53a76cd58aadd18dd5f23f84cc2). No engine migration, save-schema/worldgen changes, or graphical quality reduction.

## Implementation

- `DiscoveryTiles.revision`: monotonic transient version bump for actual additions/removals and reset. A same-count replacement cannot masquerade as unchanged discovery. No version field is persisted in the compact chunk save format.
- `PygameTerminal._build_base_layer`: when viewport coordinates, render size, z, world identity, terrain revision and compact discovery identity/revision all match the previous frame, immediately reuse the existing pixel surface. Standalone controllers using legacy sets retain the previous conservative traversal.
- Existing one-tile scroll/terrain-generation rules still apply when the viewport or memory changes. A follow-up now redraws unknown cells when known memory is pruned and recalculates neighbor transitions on both discovery additions and removals.
- Added `test_discovery_revision_detects_same_count_replacement` and `test_unchanged_discovered_base_does_not_rescan_terrain` to the existing Fast Gate regression modules.
- The first code commit `6814810` had an invalid test assumption: `1,0,0` was already discovered in the prepared test world, so the test's expectation of a terrain read was incorrect. The follow-up commit `20846c0` chooses genuinely undiscovered prepared viewport cells and covers removals. **Do not mistake the first CI failure for a demonstrated production renderer defect.**

## Measurement on `6814810`

Benchmark evidence: [run 38504109693](https://github.com/ReleMai/WORLDSEED/actions/runs/38504109693), two successful jobs using Linux Azure x86_64, Python 3.11, four logical CPUs, SDL dummy headless, seed `worldseed-reference-v1`, zoom 28, 40 measured frames and five warmups. Unpaced synthetic reference scenes, not actual Windows end-user gameplay.

| Scene | Earlier 1080p p95 (ms) | Fast-path 1080p p95 (ms) |
| --- | ---: | ---: |
| Forest | 32.39 | 17.21 |
| Camp | 29.18 | 17.56 |
| Village street | 36.61 | 25.08 |
| Interior | 5.95 | 5.36 |
| Open panel | 38.29 | 26.71 |
| Large save | 39.23 | 25.02 |

All six latest 720p reference scenes remained below 12 ms p95. Large synthetic 1,000-NPC capture median 9.50 ms, 10,000-NPC capture median 122.37 ms; 10x distant-NPC local-movement median cost growth 5.45%. Captures retain matching payloads and reference scenes reported unchanged simulation authority. Cross-run CPU noise may affect exact percentages.

**Acceptance status:** Rendering improved substantially, but 1080p outdoor p95 still exceeds 16.7 ms, with dense scenes near 25–27 ms. The 10,000-NPC capture is also above 50 ms. Live input latency, representative Windows hardware, long soak and save growth remain unverified. Do not assert full early-access release acceptance.

## Validation checkpoint and next steps

- Initial fast-path code `6814810`: benchmark passed; initial [Fast Gate 38504109682](https://github.com/ReleMai/WORLDSEED/actions/runs/38504109682) failed a *new test* because the selected cell was already known.
- Corrected `20846c0`: [Fast Gate 38504409687](https://github.com/ReleMai/WORLDSEED/actions/runs/38504409687) was **still running when this handoff was written**. Do not mark the corrected commit validated until all seven jobs pass; inspect `tests.test_render_profiling.RenderProfilingTests.test_unchanged_discovered_base_does_not_rescan_terrain` first.
- The updated code's ordinary unchanged frames use the same fast path as the successfully benchmarked preceding commit, but the exact correction should still pass CI before further changes.
- Once green, record validation here. The remaining M2 work is high-resolution terrain/wet-ground animation and dense settlement/actor presentation profiling (1080p latest approx. terrain 7–9 ms, actors 3–6 ms, preparation 3–6 ms). Optimize each with unchanged output pixels, deterministic per-seed rendering and targeted tests; rerun fixed-seed 1080p references after substantive code changes.
- Preserve the established 25-minute bounded session approach: one coherent validated unit and handoff rather than several unvalidated performance rewrites.
