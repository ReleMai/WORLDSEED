# G1b architecture note — prepared resource → immutable world-space instance

G1b implements the narrow follow-up to [G0/G1a](WORLDSPACE_RENDERER_G0_G1A_ADR_2026-10-14.md) in the approved [2.5D roadmap](WORLDSPACE_RENDERER_ART_WORLDGEN_ROADMAP_2026-10-14.md). This is a test/probe path. **No changes to production world painting or input ownership.**

## Data flow

```text
existing Simulation/World/ResourceSystem (authoritative)
     ↓ existing guarded prepared snapshot: resource_by, visibility, actors
worldseed.presentation.worldspace_adapter (read-only, bounded)
     ↓ WorldVisualInstance collection, one saved resource identity per tree
worldseed.presentation.worldspace.project_scene (read-only)
     ↓ explicit passes, foot sort, clip rectangles, local cover fade descriptors
G1b JSON/probe/tests only  —  production pygame Surface remains unchanged
```

Ownership boundaries:

| Element | Source | Not permitted |
| --- | --- | --- |
| Resource stage/depletion | `ResourceSystem.feature_at` before creating a prepared snapshot; `FeatureView` in caller's view | Re-rolling a tree, adding a second stump or mutable resource in presentation |
| Single-cell trunk movement blocker | `registry.resources[fid].blocks_movement`, mature stage and existing `(x,y,z)` | Inferring collision from canopy width or ground-shadow silhouette |
| Viewer and NPC positions/authorization | Caller-authorized actor `WorldFoot`/visibility/stealth/room state | Scanning arbitrary NPCs or exposing private-room actors; adapter omits unapproved room visuals |
| Vision/discovery | `sim.visible_tiles_set`, `sim.discovered_tiles_set`, `pos_key` supplied to `visibility_key` | Rebuilding worldwide discovery list or promoting memory into current vision |
| Visual source and layout | Existing resource content ID, prepared software visual, provisional oak/pine profiles | New asset catalog, renderer replacement, GPU driver claim, worldgen/save version mutation |
| Source extent | Capped prepared resource collection, camera-cell membership lookups | Entire-world scans, renderer-side generation or unbounded cache growth |

**Critical adapter detail:** WORLDSEED's authoritative membership keys are strings such as `"256,256,0"`; G1a model keys are `(256, 256, 0)` tuples. `visibility_key=worldseed.systems.state.pos_key` is mandatory for real current/remembered sight snapshot use. The adapter does not guess which of multiple coordinate representations it received.

## Scope and open decisions

This test model has no claim that a generic PNG can be separated cleanly into oak crown/trunk/shadow, or that its test cover rectangle matches actual art alpha. Real masks, shadow sources, sprite anchors, canopy depth order across buildings, owned rendering passes and local alpha cutouts remain G2/G4. The existing `exterior_view.py` and `interior_view.py` own building and room click/visibility constraints. A real renderer integration must not leak objects through roofs or let alpha-transparency steal pointer hits.

Reference scenes from `tools/reference_scene_fixtures.py` are synthetic *prepared WORLDSEED systems*; they are not arbitrary art or a naturally discovered save. Full real prepared-scene tests require the repository plus `ContentRegistry`, SQLite, production ResourceSystem and full fixture scaffolding. The local isolated unit tests do not cover those dependencies; CI must confirm. A large-screen viewport exceeding 8192 cells is explicitly blocked until a bounded/chunked 4K visibility representation is implemented, not silently misrendered.

**GPU:** SDL2 alpha probe remains an opt-in diagnostic. ModernGL vs another shader-capable renderer is undecided pending actual Windows driver and frame measurements. All M2 optimization documents and the software fallback remain fully authoritative for current gameplay.
