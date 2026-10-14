# M3 four-scene visual reference and panel accessibility handoff

## Work unit A — coherent retained-panel conventions

- Existing Pygame font sizes (body 17 px, small 14 px, title 21 px) now come from the immutable `FONT_SIZES` map; the current pixels stay unchanged.
- Shared `PANEL_METRICS` owns floating-shell content padding and title/body offsets. The focused retained window receives a secondary inset outline. This is visual focus feedback, not a new input authority.
- `PANEL_HELP` supplies panel-aware contextual footer copy to inventory and crafting when a caller has not provided explicit instructions. Explicit labels and existing command/tooltips take precedence; no new UI tokens are introduced.
- Existing draggable/resizable windows, WASD world movement and terminal navigation remain as before.
- Pure tests cover sizing maps, immutable instructions, focus rendering without command changes, and live homestead draggable/resize hit targets.

## Work unit B — deterministic M3 reference-scene infrastructure

The new `tools/m3_reference_scenes.py` records forest, camp, village street and interior screenshots using the real read-only production renderer and prepared synthetic QA fixtures. It records the exact **RGB pixel SHA256** from each report, fixture and driver metadata, and authority fingerprints. Captures are verified across two independent fixture passes, with no player save opened or rewritten.

Default capture uses 1280×720, tile zoom 28, one warmup and two measured frames (SDL dummy for CI). The initial GitHub Actions run is triggered by changes to the M3 capture tool or its workflow, **not by every regular engine/asset commit**. Manual dispatch is also supported. Each run uploads the candidate PNGs and `candidate-manifest.json`. It is intentionally *unreviewed*; passing pixel repeat alone does not mean art quality is approved.

To review an actual run: examine the four PNGs in the workflow artifact, verify physical doors, actor feet, terrain/lighting, contrast and text readability, then make a copy of the manifest with status `approved` after a human review. Check future captures using `--compare path/to/approved-manifest.json`. Exact mismatches fail and name the changed scene or metadata. Never silently overwrite a reviewed baseline. Compare screenshots only across the same fixture, resolution, zoom, pygame and SDL driver.

Reproduce locally on the full checked-out repository with pygame-ce:

    python -m tools.m3_reference_scenes --headless --output-dir scratch/m3-reference --passes 2
    python -m tools.m3_reference_scenes --headless --output-dir scratch/m3-next --compare path/to/approved-manifest.json

This is **reference infrastructure**, not production art approval or live Windows/high-resolution GPU certification. Production scene screenshots and actual user playtesting remain required.

## Boundaries and next phase

No simulation/seed/worldgen/save schema changes. M2 Windows GPU and soak/performance targets remain open; M3 consistent panels have progressed but character animations, visual-art approvals, audio and accessibility settings remain open. Follow the 25-minute session rule, keep CI bounded, and do not mark M3 complete without a real visual review.

## Regression correction

Initial resource/homestead CI on `58bbec9` ran 66 focused tests and identified one faulty new pixel assertion: sampling the top-left corner of a rounded focus ring reads the underlying titlebar rather than the ring. The corrected test samples the middle of the straight top border instead, preserving the actual rounded design. This was an incorrect test coordinate, not a demonstrated gameplay failure. The replacement must pass the subsequent GitHub checks before this work unit is called validated.
