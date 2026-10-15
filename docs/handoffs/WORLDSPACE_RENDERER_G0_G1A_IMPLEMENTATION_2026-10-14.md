# WORLDSEED — G0/G1a development handoff / changelog

**Work unit:** 2026-10-14, following [the roadmap](../development/WORLDSPACE_RENDERER_ART_WORLDGEN_ROADMAP_2026-10-14.md) and [the G0 handoff](WORLDSPACE_RENDERER_ART_G0_START_2026-10-14.md).

## Changelog: G0/G1a scene contract

- Added `worldseed/presentation/worldspace.py`: immutable source-world visual instances, explicit collision cells and IDs, fractional projected camera with optional elevation offset, deterministic foot-Y depth sorting and separate overhead/shadow presentation layers.
- Added bounded polygon cover relationship, independent tree parts sharing persistent resource identity, local alpha cutout descriptors, conservative current-FOW pixel clip rectangles and room/stealth restrictions.
- Added `tests/test_worldspace_scene.py`: 15 pure-Python contract tests; no pygame/GPU or world generator required.
- Added `tools/worldspace_scene_probe.py` and a reproducible synthetic SVG/JSON generator for repeatable visual-contract inspection. The probe does not imply any production art or renderer replacement.
- Added [G0/G1a ADR](../development/WORLDSPACE_RENDERER_G0_G1A_ADR_2026-10-14.md). Extend the **existing** Fast Gate with a small pure contract test stage; preserve all M2/engine optimization docs.

## Compatibility and what was intentionally not touched

No edits to `worldseed/config.py`, game physics, `worldseed/systems/resources.py`, simulation, `worldseed/world/`, persistence, saved-world versions, current resource/structure IDs, live pygame camera, weather, player movement, inventory, UI interaction, existing GPU probe or engine optimization plans. All new code is opt-in/read-model-only and has zero production call sites. Existing worlds therefore load the same code as before; the staged view contract itself does **not** constitute full save-game regression coverage.

## Validation and remaining gates

- Local isolated Python 3.13: **15/15 focused tests passed**, including the synthetic probe determinism. Source compile check passed. No pygame module or live current-repo checkout available in that isolated runtime; game-wide/Windows/persistent-save verification must be taken from GitHub CI or a source-equipped game runner.
- Planning Fast Gate `38664994647`: **success** on code baseline `6de5197b14df05f48c4a65cb0981ae4c8f5ce464`. The roadmap-only `main` head before this implementation was `798cf61216fdf8acfb555d9be0aac41112813ad3`.
- On next run: check the newly pushed Fast Gate, especially pure G1a tests, existing M2 compositor/software fallback tests, M3 reference-scene contracts, save retry and world/render tests. Do not claim post-commit CI green until confirmed.

## Next single coherent session (G1b, then G2)

1. Use current canonical `main`. Inspect this ADR and the G0/G1a JSON/SVG probe; reconcile the scene contract with actual visible-tree resource, per-cell FOW, stable room and shell hitboxes (no duplicate collision authority).
2. Add a **test-only adapter** for a prepared real forest/camp reference scene, mapping authoritative ground anchors and assets to immutable instances; maintain unchanged game output and fallback.
3. Capture/approve forest, camp, village and interior software references, choose tree crown silhouette and local alpha/radius based on the player's actual feet. Complete GPU API ADR using real Windows tests rather than SDL dummy assumptions.
4. Only then begin G2's *live one-tree proof* with renderer layering, local fade, selected-harvest tree identity and visibility/targeting regression. G3 structural tree spacing must remain versioned and new-world-only.

**Do not advance to G3–G8 or a live GPU backend on the strength of synthetic G1a alone.** Keep sessions within ~25 minutes; leave a green, resumable commit on `main`.
