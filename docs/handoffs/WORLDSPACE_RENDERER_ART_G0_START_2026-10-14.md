# WORLDSEED graphics/world-space handoff — start G0/G1a

**Date:** 2026-10-14.  
**Planning baseline:** `6de5197b14df05f48c4a65cb0981ae4c8f5ce464` on `main`, with Fast Gate `38664994647` **completed successfully**.  
**Roadmap:** [2.5D graphics, canopy, GPU and worldgen roadmap](../development/WORLDSPACE_RENDERER_ART_WORLDGEN_ROADMAP_2026-10-14.md).

## Original intent and non-negotiables

The user wants a more spatially credible game world, not isolated higher-resolution PNGs:

1. **Trees have a solid trunk and an independent overhead crown.** Player and
   NPCs can move below the crown; it fades selectively over the obstructed
   player without removing trunk collision, tree identity or tree shadows.
   Forest generation spaces trunks and large crown profiles according to
   species instead of treating every tree like a one-tile obstacle.
2. **The camera and render ordering understand height.** Separate terrain,
   ground vegetation, structures/trunks, character feet/bodies, projected
   shadows, tree crowns, roofs, weather, emissive effects and UI. Large
   sprites overflow a cell while all interactions target the existing
   authoritative footprint. Apply this design to bridges, tall props and
   other overhead geometry too.
3. **Lighting and weather are connected to actual game time and objects.**
   Sun/moon shadows for trees/actors, torch and fireplace flicker with real
   fueled/toggled source state, proper actor shadow movement, fog drifting in
   world space, rain with wind/splashes and roof/canopy interception, and
   seasonal grass/ground detail. Visual time interpolation must not alter
   authoritative simulation ticks.
4. **New art accompanies engine work**, starting with approved oak/pine
   trunk+crown+shadow layers, one directional player/NPC sample, grassland
   detail, and campfire/street torch/hearth. Avoid generating dozens of
   unrelated assets without approved anchors or a common art direction.
5. **Preserve all existing optimization documents and work.** Do not delete
   or overwrite `docs/development/EARLY_ACCESS_PYGAME_PLAN.md` or
   `docs/development/GPU_COMPOSITING_EXPERIMENT.md`. Continue M2 profiling,
   existing spatial indexes, caching, save reliability and CI. A standalone
   SDL2 alpha compositor/probe is not a full shader-capable GPU game renderer.

## Baseline facts (verified in main)

- `worldseed/ui/pygame_terminal.py` contains the software pygame world
  surface and current sub-tile player camera. No renderer cutover.
- `worldseed/presentation/atmosphere.py`, `weather_fx.py`, `clouds.py`
  draw current lighting, rain and fog; `gpu_layers.py` and
  `tools/gpu_layer_compositing_probe.py` are opt-in diagnostic components.
- `worldseed/world/lighting.py` and `systems/illumination.py` define
  read-only/gameplay lighting and indoor wall occlusion; keep stealth and
  simulation authoritative.
- `worldseed/systems/resources.py` uses deterministic per-cell structural
  candidates and cardinal-neighbor priority spacing; `config.py` defaults
  to worldgen v8 and resourcegen v5, with older saves pinned to stored versions.
  A new tree-spacing algorithm must be **versioned and new-world-only**;
  existing saves can get visual overhang without redistributing tree resources.
- Dev42 player and NPC pools each have ten male/ten female variants, with
  normalized ground-foot anchors; the current figure art is static frontal.
  New directional art must retain selection IDs and anchored interactions.
- `worldseed/ui/exterior_view.py` and `ui/interior_view.py` already
  separate some physical footprints from drawn art and hide interiors
  appropriately. New overhead fading cannot reveal hidden rooms or NPCs.

## Next chat: first bounded work unit only

**G0/G1a — a renderer-independent world-space projection and occlusion
contract with tests.** Read the full roadmap and current main first.
Implement a small immutable visual-instance schema with physical footprint,
ground/foot anchor, visual height, crown coverage, shadow/source attachments,
sort layer and culling bounds. Add one test viewport with a synthetic tree,
player/NPC and overhead crown and tests proving: passable canopy over solid
trunk, deterministic depth order, local fade, correct occlusion, FOW/privacy,
camera sub-tile movement, zoom and legacy tree identity. Favor new, small
modules over editing the huge terminal renderer. Do not change generation,
asset catalogs or production GPU backend in this initial unit.

**Exit gate:** targeted tests, basic regression/CI, changelog plus handoff
updated, clean `main` commit. Project sessions aim for approximately
25 minutes; leave a resumable build. No user-approved art pack or renderer
cutover is implied merely by publishing this plan.

## Follow-on phase order

G0 baselines/ADR → G1 scene projections/layers → G2 functional tree canopy →
G3 deterministic species spacing with resourcegen version → G4 first asset
pack → G5 solar/actor shadows and camera → G6 torch/hearth/emissive flicker →
G7 weather/decorations → G8 shader-capable GPU owner/Window cutover →
G9 polish, native Windows/device, save/memory/performance release gates.

**Development source of truth:** https://github.com/ReleMai/WORLDSEED.
