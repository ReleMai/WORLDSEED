# WORLDSEED Fast Gate smoke triage — 2026-10-12

## Completed and confirmed
- `7bc4678`: territory guard movement test now provides `StubWorld`, rather than expecting collision-aware movement with no world.
- `8e64694`: fixed-tick movement test provides a passable world and tests tick ownership instead of obsolete one-cell pacing.
- `8e64694`: 20-module settlement/economy suite moved to a parallel, non-fail-fast job; **134 tests passed** in run `38262564241`.
- `f6f83c9`: building art audit now uses the homestead catalog and directional atlas manifest, separately validates the 26 cabin sprites, and continues to reject unknown PNGs. Run `38263448413` passed 57 facades, 4 doors, 26 cabin PNGs and 2,052 geometry cases.
- Short NPC lab, full-day conservation and Linux process-runner were green at last check. The eight-worker full-duration NPC lab passed an earlier run `38256812858` and takes much longer than smoke.

## Next blocking failure (not fixed)
Run `38263448413` smoke fails at `tests.test_biome_atlas.BiomeAtlasTests.test_committed_generated_catalog_and_markdown_are_current`.
The generated `build_catalog()` content contains newer resource IDs (including `core:salvage_patch_burdock_burr_cluster`) than the committed `worldseed/assets/biome_catalog.json` and `worldseed/assets/BIOME_ATLAS.md`.
This is a stale generated-output issue following resource/content expansion, not evidence that those source items are invalid. The unrelated biome catalog, fishing and image-readability assertions passed.

### Resume in a checked-out development environment
1. Run `python -m tools.build_biome_atlas` from the repository root. This regenerates JSON, Markdown and biome PNGs. **Inspect all generated diffs before publishing**.
2. Run `python -m unittest -v tests.test_biome_atlas`, plus `python -m compileall -q worldseed tools tests`.
3. If regenerated outputs match the source catalog and visuals are valid, commit them to `main` as a coherent validated unit; observe the Fast Gate without disabling this equality assertion.
4. Continue diagnosing the next actual smoke failure, if any. Keep authored source systems and long-running NPC lab behavior intact.

The CI URLs are:
- https://github.com/ReleMai/WORLDSEED/actions/runs/38262564241
- https://github.com/ReleMai/WORLDSEED/actions/runs/38263448413
