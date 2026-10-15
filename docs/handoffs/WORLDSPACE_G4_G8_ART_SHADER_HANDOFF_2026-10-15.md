# WORLDSEED G4 + shader-capable G8 candidate — implementation handoff

**Date:** 2026-10-15. **Source:** canonical `ReleMai/WORLDSEED` `main`; read the [G4/G8 ADR](../development/WORLDSPACE_G4_G8_LAYERED_ART_AND_OPENGL_ADR_2026-10-15.md) and original [G0–G9 roadmap](../development/WORLDSPACE_RENDERER_ART_WORLDGEN_ROADMAP_2026-10-14.md) before advancing.

## Changes / changelog

- Original source-controlled 12-image 2.5D oak/pine layered art with four seasons (trunk + independent shadow + canopy). Deterministic builder and SHA256 manifest; ZIP-packed Base85 PNG archive for text-safe Git commits and package runtime inclusion.
- `worldseed/presentation/tree_art.py`: integrity-checked source access and bounded cached pygame scaling; default software path unaffected.
- `canopy_preview.py`: preserve `prepare_one_oak` contract, add bounded `prepare_tree_cluster` for up to four mature oaks/pines with one resource identity per source cell; swap provisional shapes for authored PNGs, and keep physical trunk, visibility, gameplay and shadows separate.
- `pygame_terminal.py`: developer opt-in `WORLDSEED_G2_CANOPY_PREVIEW=1` invokes multi-cover viewer but does not alter legacy pixels when off. Existing building, roof, player-house masking conservative.
- `gl_worldspace.py` and `.vert/.frag`: shader-based ModernGL/OpenGL candidate with per-fragment fade and ambient grade, sprite batching, clipped world-space presentation, immutable authorized sprites, bounded revisioned GPU texture bank. **Separate native probe** owns one SDL window; no live GPU cutover.
- `tests/test_worldspace_gpu_art.py` and `tests/test_worldspace_art_integration.py`: source PNG hashes/integrity, no path escape, two species/layers/harvest source, FOW/roof isolation, shader uniforms/GL scissor/sort/caches, dummy GPU test doubles, plus pygame-dependent layer rendering. Fast Gate includes pure + existing Windows live-sprite/scene regressions; native hardware shader test is manual.

## Validation and compatibility

- Locally (isolated Python 3.13): focused G0/G1a, G1b, G2, G4/G8 pure tests pass. Pygame/OpenGL and real installed-world tests cannot run in this isolated runtime; GitHub CI validates existing game/pygame regressions after commit. Native Windows GL/driver/resize requires hardware playtest, **not asserted green by the presence of shader code**.
- The preexisting `WORLDGEN_VERSION`, `RESOURCEGEN_VERSION`, saved-world format, persistent tree identities, collision, input and all engine optimization documents are unchanged. The non-opt-in software renderer remains default and supported.

## Next verified unit

1. Check post-commit **Fast Gate** jobs and any automatically triggered other workflows. Fix real CI errors before treating commit as green.
2. Capture and visually inspect four M3 reference scene screenshots (forest/camp/village/interior), plus seasonal G2 opt-in output; ask for player approval on silhouette/alpha and scaling. Run harvesting, stump, reloading and roof/stealth checks on actual Windows hardware.
3. Run the manually dispatched `WORLDSEED Native OpenGL Candidate Probe` workflow and local native hardware test (including 720/1080/1440/4K if supported); verify driver strings, screenshot output and p50/p95/p99. GL context missing => no GPU cutover.
4. G8 live integration: one window/context owner, map all events/click coordinates through the shared camera, world draw graph with bounded GPU terrain/static-geometry batches, full pixel/perceptual parity, alt-tab/resize/device loss, fallback. G5–G7 real lighting/shadows/weather and G3 resource-spacing still require separate versioned milestones. Do not promise default GPU game acceleration before these pass.

**Session boundary:** leave a clean validated main commit and avoid branch proliferation. Do not claim G8/G9 shipped or shader speedups without native hardware evidence.
