# WORLDSEED G0/G1a — immutable world-space scene contract (ADR, experimental)

**Date:** 2026-10-14. **Decision:** accept an additive Python-only reference contract; **do not** change the live pygame renderer, world generation or any save schema. Refer to [the graphics roadmap](WORLDSPACE_RENDERER_ART_WORLDGEN_ROADMAP_2026-10-14.md) and [G0 startup handoff](../handoffs/WORLDSPACE_RENDERER_ART_G0_START_2026-10-14.md).

## Baseline inventory and preservation

- Planning baseline `6de5197b14df05f48c4a65cb0981ae4c8f5ce464` passed Fast Gate run `38664994647`; roadmap publication advanced `main` to `798cf61216fdf8acfb555d9be0aac41112813ad3` without live renderer changes.
- `worldseed/ui/pygame_terminal.py` is the existing ~4,900-line software pygame renderer: fractional movement, 16–56 px tile zoom, cached view strips/resource snapshots and weather drawing. The pygame path is **not** imported by G1a.
- `worldseed/ui/exterior_view.py` owns building-shell art and masked door/body pointer regions; actual shells, footprint and door identities remain authoritative. `worldseed/ui/interior_view.py` already separates upright furniture art bounds and ground-hit footprints and uses an independent interior camera.
- `worldseed/systems/resources.py` derives structural resources from versioned deterministic per-cell candidates and priority spacing. Worldgen v8, resourcegen v5 and previously recorded world/save versions remain unchanged; G1a does not invoke resource placement or alter tree positions.
- `worldseed/presentation/gpu_layers.py` remains an opt-in SDL2 diagnostic, **not** a production shader renderer or validated hardware acceleration. Existing animation, bounded caches, discovery indexes and the software fallback are untouched.
- Preserve without replacement: [EARLY_ACCESS_PYGAME_PLAN.md](EARLY_ACCESS_PYGAME_PLAN.md), [GPU_COMPOSITING_EXPERIMENT.md](GPU_COMPOSITING_EXPERIMENT.md), [M2 closeout](../handoffs/EARLY_ACCESS_M2_ENGINE_CLOSEOUT.md), [native high-res handoff](../handoffs/EARLY_ACCESS_NATIVE_HIGHRES_HANDOFF_2026-10-14.md).

## G1a contract and ownership

`worldseed/presentation/worldspace.py` introduces frozen, slotted `WorldFoot`, `CoverRegion`, `WorldVisualInstance`, `WorldCamera`, `SceneVisibility`, `ProjectedVisual`, `LocalCoverFade` and `ProjectedScene`.

| Responsibility | Contract | Authority |
| --- | --- | --- |
| World foot/elevation | Fractional `WorldFoot` (x, y, z), bottom-center visual anchor and independent visual extent/height | Simulation owns positions; art catalog ultimately owns dimensions |
| Physical hitbox | Explicit tuple of occupied world cells; no occupied cells inferred from crown width or sprite overhang | Existing collision and building/route/terrain state |
| Visual group | Unique child `instance_id` plus persistent `resource_id` and optional `parent_id`, revision and shadow/emissive attachments | Source resource is the only choppable/collectible identity |
| 2.5D layers | Ground → low detail → projected shadow → combined foot-Y-sorted trunk/actor upright group → overhead → atmosphere → UI | Presentation only; tie-break by foot z/x then explicit layer and ID |
| Camera | World-to-screen and inverse on known ground elevation, independent zoom, pixel dimensions and fractional center/anchor | Read-only presentation; production pointer routing unchanged |
| Canopy/roof | Authored world-space coverage polygon and compatible foot z; if authorized player foot is inside, emit bounded local fade mask | Cover is not collision; no stealth, FOW or private-room bypass |
| Visibility | Explicit currently-visible and remembered cells, room whitelist, per-instance `authorized_visible` gate; per-cell screen clipping | Visibility, stealth and room access must come from gameplay authority |
| Culling | Full sprite overhang projected from ground foot, even when source trunk is offscreen; per-instance clip rectangles bounded | Test-only view projection; no world generation or dynamic indexing |

**Renderer integration precondition:** the future compositor must intersect every sprite/shadow/bloom pixel with `ProjectedVisual.clip_rects` (or an equivalent stronger authoritative visibility mask), and apply `LocalCoverFade` **only** inside its local radius **after** clipping. The transparent part of a crown may never become a selectable extra resource, reveal a hidden NPC, or erase its independent shadow. Per-cell clips are a conservative first contract, not a final shader/material or indoor wall-occlusion implementation. Visibility/room/stealth reads must be provided by the owning simulation snapshot. A visual instance's `authorized_visible` should be derived by a read-model adapter, never invented by the renderer.

G1a is deliberately not integrated into live code, not a replacement for existing `InteriorCamera`, and does not yet bind to art catalog metadata. The test-only synthetic leaf shape does not license tree-generation, player-physics or saved-world changes. Future G2 must check full game stealth, roof-room occlusion, click/hit masks and dynamic harvest/removal against real fixtures.

## Synthetic reference viewport

`python -m tools.worldspace_scene_probe --output-prefix scratch/worldspace-g01` creates a deterministic JSON fingerprint and SVG scene at 640×480 by default. The scene shows one persistent oak resource with separately drawn shadow/trunk/crown, a player under crown, a visible NPC and a concealed NPC excluded before projection. It demonstrates locally masked crown transparency, stable sorted passes, explicit footprint and current-sight clips. The reproducible SVG/JSON are generated locally by the command; see the test suite for deterministic manifest verification. **This is a wireframe proof, not approved game art or a production render screenshot.**

## GPU API ADR — options reviewed, selection pending

| Option | Strength | Limitation / next evidence |
| --- | --- | --- |
| ModernGL + OpenGL in one pygame-owned SDL window | Shaders, batched sprite vertices, texture atlases, framebuffers and possible normal/height lighting | Need real Windows driver/context/resize/alt-tab/device-reset and UI/input ownership proof |
| pygame SDL2 Renderer/Texture | Small migration surface; current bounded compositor proof exists | Does **not** itself supply the requested modern lighting/shader pipeline; no production cutover justified |
| wgpu/Python backend | Explicit GPU pipeline and shaders | More packaging/backend/UI/input complexity; driver/device matrix must be benchmarked |
| pygame software (`Surface`) | Existing proven fallback, exact replay/reference screens and pointer behavior | Performance bottlenecks at high resolution; keep as fallback during staged integration |

**Decision held:** no GPU production owner/backend chosen without driver measurements, comparative reference captures, window event/input/resize parity, atlas/caching discipline and screenshot approval. The four forest/camp/village/interior baseline approval captures and GPU hardware runs remain **unverified in this G1a environment**. Reuse the existing M2 and M3 reference-scene tooling for G0 completion.

## Verification gate

Run `python -m unittest -v tests.test_worldspace_scene` (pure Python) and `python -m tools.worldspace_scene_probe --output-prefix scratch/worldspace-g01`. The tests assert immutable IDs, footprint/canopy independence, canopy fade, depth sorting, hidden NPC/stealth/room privacy, exact current-vs-remembered clipping, offscreen overhang, camera zoom/sub-tile/resize round trips, bounds and deterministic SVG/JSON output. Fast Gate's Linux process-runner job runs the focused pure-Python test before future renderer development.

**Deferred, not claimed:** actual game screenshot parity, complete old-save round-trip against persisted world databases, live pygame rendering validation, native GPU tests, visual/performance release acceptance, new art, and G2 runtime canopy interaction. These belong to later bounded sessions and full CI/gameplay gates.
