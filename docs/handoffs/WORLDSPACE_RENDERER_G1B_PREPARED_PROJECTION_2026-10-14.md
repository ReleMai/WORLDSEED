# WORLDSEED — G1b prepared-resource world-space adapter handoff

**Date:** 2026-10-14. **Dependency:** G0/G1a `647d6d7540dddf61e49de04073f52b10ad520279` (Fast Gate `38672864961`: **success, all seven jobs**). New G1b code is a small additive/test-only projection; the current pygame world renderer remains the supported game output.

## Changelog — delivered in G1b

- `worldseed/presentation/worldspace_adapter.py`: immutable/observational bridge from the **already prepared** `resource_by[(x,y,z)] = (FeatureView, software_visual_ref)` rows of `PygameTerminal._resource_view` to G1a `WorldVisualInstance` children and `project_scene`.
- Trees in the opt-in projection have a single stable `feature:{z}:{x}:{y}:{feature_id}` gameplay source identity shared by test-only trunk, shadow and crown visual parts. The real resource's saved cell and `FeatureView.stage` remain authoritative: mature trees use the existing `blocks_movement` definition, stumps and saplings gain no new collision or mature canopy, depletion projects no parts.
- Oak/pine crown dimensions and rectangular coverage in `PREVIEW_CROWN_PROFILES` are **explicit provisional test geometry**, not approved artwork, physical hitboxes, a new resource generator, or finished visual silhouettes. Must be replaced with approved authored trunk/crown masks before G2 promotion.
- `SceneVisibility` is built from a **bounded camera-cell membership window**. The read adapter accepts `visibility_key=pos_key` so real `Simulation.visible_tiles_set`/discovery membership (`"x,y,z"`) is mapped to immutable `(x,y,z)` projection cells without global discovery scans. Remembered-only cells never authorize tree objects or actors. No NPC is added unless the source passes an explicit sight/stealth authorization gate; private-room actors are excluded until a production indoor room-gate adapter exists.
- `tools/worldspace_prepared_probe.py`: read-only JSON fingerprint/manifest for real, already-prepared forest or camp resources from existing reference fixtures. No new world planning is allowed by fixture preparation guards.
- `tests/test_worldspace_adapter.py`: 10 pure contract tests and one guarded full-repository forest reference test. The Fast Gate's compact pure stage covers both G1a and G1b. The existing fully installed CI smoke job runs the prepared real forest case.

## Verification and remaining blockers

- Isolated source subset: `python -m unittest -v tests.test_worldspace_scene tests.test_worldspace_adapter` ran **25 pass, one skipped** because this isolated session has no full checked-out game module graph. `python -m compileall -q worldseed tests tools` passed. Real fixture and the unchanged software screenshot regressions must be verified in the pushed Fast Gate before calling G1b fully validated.
- No gameplay files, `worldseed/config.py`, save or worldgen version constants, resource placement, renderer drawing, caches, existing M2/GPU experiment, `docs/development/EARLY_ACCESS_PYGAME_PLAN.md`, `docs/development/GPU_COMPOSITING_EXPERIMENT.md`, or legacy save format are changed.
- Camera-cell capture deliberately rejects a viewport greater than the current G1a 8,192-cell visibility budget. **4K wide-zoom and dense forest production scaling remain future gates**, not claimed G1b acceptance. Read-only probe is not a 4-scene artwork approval, true software/GPU pixel parity, or Windows interactive playtest.
- Normal play has zero G1b calls; this architecture is strictly test-only. Do not enable it in live rendering simply because pure tests succeed.

## Next bounded work unit — G1c and early G2 proof

1. Run the new Fast Gate to completion; inspect the real prepared forest fixture and regression statuses, and fix any discovered bridge/schema assumptions before advancing.
2. Use the existing M3 forest/camp/village/interior software-reference tooling, collect actual reference images and obtain art-direction/canopy-opacity approval. **No approval is implied by this document.**
3. Add a *single opt-in* live tree demonstration through an isolated renderer helper, with per-cell FOW clipping, existing tree click/harvest target, physical trunk blocker, independently drawn shadow, and localized crown fade. Keep player-visible NPC privacy, building shell/roof room occlusion and interior portals as unchanged authoritative gates.
4. Only after G2 and tree coverage metrics pass may G3 version new resource placement on new worlds. GPU backend ownership remains an independent future G8 milestone requiring native shader/context evidence. Never silently change v8/resourcegen v5 legacy world placement.

**Development source of truth:** https://github.com/ReleMai/WORLDSEED. Keep each session green and resumable on `main` rather than opening persistent phase branches.
