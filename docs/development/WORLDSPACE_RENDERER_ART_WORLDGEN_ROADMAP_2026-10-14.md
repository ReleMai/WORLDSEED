# WORLDSEED — 2.5D Graphics, Living Canopies & GPU Renderer Roadmap

**Status:** Approved design direction / implementation **NOT STARTED** for the items marked proposed below.  
**Created:** 2026-10-14  
**Baseline:** `main` at `6de5197b14df05f48c4a65cb0981ae4c8f5ce464` (before this planning-only commit).  
**Owner of implementation:** subsequent WORLDSEED development sessions, not this planning session.

> **Preservation rule:** Do not delete, overwrite, replace, or silently supersede
> [the existing Pygame engine and early-access plan](EARLY_ACCESS_PYGAME_PLAN.md),
> [the M2 GPU experiment](GPU_COMPOSITING_EXPERIMENT.md),
> [the M2 measured-engine closeout](../handoffs/EARLY_ACCESS_M2_ENGINE_CLOSEOUT.md),
> or [the native high-resolution handoff](../handoffs/EARLY_ACCESS_NATIVE_HIGHRES_HANDOFF_2026-10-14.md).
> This is a **parallel and additive** graphics/worldgen roadmap. The existing
> optimization, profiling, CI, save reliability, and gameplay roadmaps continue.

## 1. Desired outcome: a grounded 2.5D living world

WORLDSEED remains a top-down 2D game with **height-aware 2.5D presentation**.
It needs believable depth, not just more detailed sprite sheets. Every tree,
large plant, wall, roof, bridge, furniture item, streetlight, fire, player, NPC
and creature should render in its correct visual layer with explicit ground
footprints, visual height, shadows, occlusion, and camera behavior.

**Required experience:**
- Walk **under** a tree's broad overhead crown while the **trunk** remains
  solid and the canopy fades locally to reveal the player when necessary.
  Walking under the crown does **not** mean walking through a trunk.
- Walk **behind/in front of** other tall objects based on feet/ground anchors;
  enter buildings and walk under roofs without losing readability or revealing
  private/undiscovered interior objects.
- Forest spacing responds to **species and mature crown size**, not simply
  adjacent blocking cells. A dense forest still has traversable clearings,
  understory, recognizable groves, believable silhouettes and no accidental
  generation seams.
- Character shadows **follow moving feet**, react to solar direction/height,
  and respond visually to nearby fire or lamp light; static contact shadows
  provide a visual grounding even when detailed directional shadows are culled.
- Time of day changes continuously on screen; dusk, moonlight, morning, cloud
  cover, shelter, torches and fireplaces feel connected. **Presentation**
  interpolation never fast-forwards gameplay or changes simulation clock rate.
- Fog/rain/snow/storm atmosphere and grass/flowers/leaf litter/reeds add visual
  life without covering gameplay icons, breaking fog-of-war, or hiding hazards.
- New assets use a common production art direction, fixed anchors, coherent
  relative scale and source provenance; no unbounded GPU/CPU cache growth.

**Not included in the initial deliverable:** a fully simulated 3D world,
physically exact ray tracing, global illumination, genuine volumetric fluid
simulation, or a claim of 4K/60 FPS without native measurements.

## 2. Reality check: existing implementation versus proposed work

| Existing (verified in baseline) | Gap / required work |
| --- | --- |
| `worldseed/ui/pygame_terminal.py` draws terrain, overlays, actors and weather onto pygame Surfaces; local camera uses player fractional coordinates, extra border tiles and tile-scaled viewport. | Make a reusable world-to-screen camera/projection and explicit ground/object/overhead/lighting/weather/UI passes; avoid a risky monolithic renderer rewrite. |
| `worldseed/systems/resources.py`: deterministic, per-cell resource placement; structural candidates use biome budgets and cardinal-adjacency priority thinning; generated resource overlays do not replace biome terrain. | Species-specific canopy geometry, minimum trunk/crown clearances, coherent groves, cross-chunk exclusion, visibility/interaction rules and versioned migration. |
| `worldseed/presentation/visuals.py` plus `worldseed/assets/visuals.json` manage content-to-asset mapping; Dev42 has 10 male/10 female player and NPC variants each, standardized 160×256 canvases with foot baselines. | Layered directional character parts/animations, tree crown/trunk/masks, height/occluder/emissive metadata, alpha/normal-map tests, art direction and provenance. |
| `worldseed/world/lighting.py` computes season-aware sun/dawn/dusk state; `worldseed/systems/illumination.py` supplies indoor wall-aware light and outdoor fueled fires used in visibility/gameplay. | Projected sun/moon shadows, moving actors/objects occlusion, visual flicker and colored light without diverging from gameplay illumination. |
| `worldseed/presentation/weather_fx.py`, `atmosphere.py`, `clouds.py` already render wet ground, cloud shadows, fog, rain, time tint and glow. | Height/depth-aware layering, localized mist, rain occlusion under roofs/canopies, splash/light response, effect quality tiers, fog-of-war-safe composition. |
| `worldseed/presentation/gpu_layers.py` and `tools/gpu_layer_compositing_probe.py` are an experimental bounded SDL2 compositing track. | Choose a **shader-capable** production backend; scene render graph, window/input ownership, GPU sprite batching, real hardware parity and robust fallback before default promotion. |
| Interior furniture separates upright image bounds from ground physical footprint; exterior shells/roofs have stable portals and obscuration rules. | Generalize visual height and occlusion contracts to vegetation, structures, tall decorations, indoors/outdoors and future objects. |
| `worldseed/config.py` pins current worldgen v8 and resourcegen v5; old saves retain their recorded versions. | Version new physical generation separately from **presentation-only** asset changes; never silently redistribute resources in legacy saves. |

**Design invariant:** real geometry/doors/collision/visibility/resources/saves
belong to the simulation, world and persistence systems. Renderers consume
bounded immutable view models. A shadow or sprite cannot create/remove an
obstacle, reveal an unseen NPC or alter player/NPC position.

## 3. Target render graph and height-aware visual contracts

### 3.1 Pass ordering (logical, not necessarily a GPU API implementation)

1. **Ground:** biome/terrain, soil, paths, shore gradients, river beds and low
   decals; respect discovery and authoritative map projection.
2. **Low-ground detail:** short grass clumps, flowers, pebbles, fallen leaves,
   footprints, puddles, moss; decorative and generally nonblocking.
3. **Projected ground shadows:** diffuse cloud/solar shadows, static-object
   shadows, actor contact shadows and height-aware directional shadows,
   composited only where they should appear.
4. **Grounded geometry:** trunks, roots, rocks, fences, doors, lower walls,
   foundations, low props, fire pits and character feet. Y-sort by **world-space
   ground anchors**, stable tie-break by visual instance ID.
5. **Upright actors/objects:** bodies, workstations, poles, vegetation middles,
   front/back segments; multi-cell art may overlap neighboring terrain.
6. **Overhead covers:** tree crowns, broad leaves, roof overhangs, awnings,
   bridge decks and upper floors. Per-object alpha cutouts respond to the
   viewer's actual under-cover relationship, not proximity alone.
7. **Light/atmosphere:** global grade, bounded point-light/occlusion buffers,
   emissives, smoke, wind-driven fog, rain/splashes, cloud layers and optional
   post effects. Split into before/after overhead subpasses where physical
   layering requires it; e.g. rain beneath an open canopy but not inside roof.
8. **Gameplay/UI:** selection outlines, interaction markers, combat warnings,
   HUD, panels, pointers and tooltips. Always preserve visibility and hit
   targets. Apply tactical overlays after darkening if required for legibility.

**Pass-order exception:** a 2.5D graph may interleave grounded actors and
overhead materials by world-space sort/occlusion groups rather than one
global pass. Establish deterministic sort ties, a per-entity layer ID, culling
bounds and ownership of each clip rectangle. Avoid a tree crown punching holes
in the world map or altering mouse targeting.

### 3.2 Render instance contract (proposed API; not implemented)

A bounded immutable `WorldVisualInstance` or equivalent carries:

- `instance_id`, stable `content_id`, `world_foot_x/y/z`, fractional
  movement offset; parent/child attachment IDs.
- **Physical footprint:** occupied ground cells or authoritative hitbox and
  movement/interaction rules, untouched by the sprite dimensions.
- **Visual bounds:** width/height, bottom-center foot anchor, top extent,
  viewport overlap bounds and sort key; includes neighboring cells when huge.
- **Elevation:** base terrain height, visual-object height band, overhead layer
  and contact point; enough for 2D projected sun and point-light shadows.
- **Optional components:** canopy occupancy polygon/mask, trunk mask,
  cast-shadow alpha/height mask, receive-light/normal mask, emissive map,
  transparent cutout regions, material/animation state.
- **Visibility:** currently seen vs remembered vs unknown (unchanged gameplay
  authority), plus presentation-only fade/opacity. Never let canopy fade or
  bloom reveal hidden entities.
- `revision` or deterministic material key for cache invalidation; no
  renderer-owned gameplay RNG or state mutation.

Represent one mature tree as **a group of child visuals sharing one persistent
resource identity**, not multiple collectible resources. One tree remains one
choppable/harvestable object even when its canopy spans several cells.

### 3.3 Canopy/roof occlusion and under-object movement

- Define crown coverage in world units (e.g. polygon or coarse occupancy mask)
  from the species/age variant's *actual* art silhouette; center it on an
  authored trunk ground anchor. A player under a crown is identified by their
  **foot point** inside that footprint and a matching elevation band.
- Render crown over the actor when appropriate, with a tunable **local fade
  mask** (initial target 35–60% alpha near the obstructed actor, subject to
  screenshot review), restoring full opacity outside the local area. Trunk,
  roots and physical collision **never fade out** as the player approaches.
- If player is not under the crown, keep full tree art even if nearby. Handle
  overlapping crowns with stable alpha composition and a capped count of
  local dynamic cutouts, not repeated viewport-wide CPU readbacks.
- When NPCs/creatures stand under cover, depth-sort correctly but **do not
  expose unseen/stealthed NPCs**. Optionally use approved local silhouettes
  only for actors the player is already entitled to see; prioritize the player
  for accessibility.
- Apply the same contract to roofs, arcades, oversized props and overhangs,
  while preserving established room/roof privacy, physical doors, cave entrances,
  interior portals, property collision and pointer masks.
- Shadows originate from trunk/canopy **separate** geometry. Fading a visible
  canopy should not remove its ground shadow; changes in cover affect whether
  rain hits the ground and how sunlight falls through gaps.
- Maintain full, independently stable `FogOfWar` / discovered-cell gates
  before any overhead drawing, interaction, light bloom or shadow preview.

### 3.4 Camera/projection

- Retain a top-down camera but shift to **ground-foot anchored projection**
  with optional look-ahead in walking direction; camera movement can be
  sub-tile smooth and follow the player without snapping on grid crossings.
- Camera framing should allow taller trees/buildings above the player without
  cutting their crowns at the top. Scale large silhouettes consistently; add
  overscan/culling margins derived from maximum authored asset extent.
- Decouple world units, zoom multiplier, render resolution, GUI safe regions
  and actual hit testing. Handle 720p, 1080p, 1440p, 4K, resizes and Windows
  display scaling, and ensure click targets follow the same transform.
- Use camera transforms for particle position, shadows, lighting and selection
  in **world space**, not screen-attached clouds or trees. Zoom/resize must not
  shift an actor relative to its footprint or reveal off-camera terrain.
- Introduce camera motion/accessibility settings (smoothing on/off, look-ahead
  on/off, optional reduced weather effects) without changing movement inputs:
  WASD moves only the player; UI remains mouse-operable.

## 4. World generation + ecology rework

### 4.1 Separate geography, resources and decoration

- **Base geology/climate/hydrology:** preserve v8 terrain and existing
  hydrology contracts until specifically revised; this phase is primarily
  resource/scene-placement and decoration evolution, not a fresh map generator.
- **Structural resource layer:** tree trunks, rocks and solid obstacles.
  Update type-aware deterministic candidate acceptance with crown footprint,
  trunk footprint, collision blocking and path clearance.
- **Understory/decorative layer:** grass clumps, flowers, mushrooms, saplings,
  fallen twigs, leaf litter, ferns and seasonal weeds. These are nonblocking
  **visual instances** unless explicitly promoted to real gatherable resources.
- **Generated site/settlement overrides:** clear or reconcile canopies across
  roads, door thresholds, plots, bridges, beds, cave mouths and prepared
  buildings. Crown extensions cannot obscure a doorway or grow through a roof
  unless the art/plan explicitly supports it.

### 4.2 Tree type and spacing rules

Define authored species-style profiles in a new versioned visual/resource
catalog. **Proposed** start (world-space tile units; tune from actual art):

| Type | Trunk/solid footprint | Crown visual footprint | Candidate separation | Biome intent |
| --- | --- | --- | --- | --- |
| Broadleaf/oak | 1 tile or authored larger | approx. 3–5 tiles wide | larger nearby crown clearance | temperate forests and scattered fields |
| Pine/conifer | 1 tile | approx. 2–3 tiles wide | moderately close, clustered stands | conifer forest and cool country |
| Swamp tree | root/trunk + optional wet edges | approx. 3–5 tiles wide | roots/water-aware clearance | wetlands and river margins |
| Small/sapling | optional nonblocking | approx. 1–2 tiles wide | fit in gaps beneath larger crowns | groves and regrowth |
| Dead/sparse | solid trunk | narrow/sparse top | ecological grouping but open crown | scrub, burn scars, dry terrain |

These values are **design hypotheses, not existing engine parameters**.
Tune against actual approved sprite measurements and biome playtests. Do not
uniformly prohibit all crown overlaps: moderate overlap is natural. Enforce
**stronger trunk clearance and traversal corridors** while allowing
selective crown overlap and sparse groves.

- Use deterministic world coordinates and stable hash-priority exclusion
  (species-aware Poisson/Matérn-like acceptance) over a bounded neighbor
  radius. Check neighboring chunks so the spacing has **no chunk seam**.
- Placement depends on biome, temperature, moisture, fertility, altitude,
  exposure, slope, rivers, roads, settlements and species ecology, not only
  on the local `forest` terrain ID.
- Separate old-style resource density from height/crown render density:
  canopy overhang should add natural forest fullness **without** filling
  every traversable ground cell with a blocker.
- Generate plausible forest edges, clearings, clustered saplings, mixed
  undergrowth and some deadwood. Preserve paths to caves, houses, water,
  world exits and settlement public routes.
- Multi-tile canopies should be **view data** tied to a single source anchor,
  not regenerated as a blocker in each cell. Deduplicate by unique source ID
  across nearby chunk queries, with conservative viewport extents.
- Cover collision/interaction tests for trunk/bridge/canopy, initial spawn,
  pathfinding, saving and restoring chopped/removed trees and construction
  clearing. No reappearing canopies after harvest.

### 4.3 Legacy-save safety

- **Presentation-only tree art:** existing saves keep identical resource ID,
  coordinates, depletion, loot, seasons and gameplay collision. Give their
  current trunks improved visual canopies and shadows without rerolling placement.
- **New structural spacing rules:** choose a new resource-generation version
  explicitly, only for **new worlds** or deliberate opt-in migrations with
  backed-up data. Older `resourcegen_version` continues producing the same
  feature identities at the same coordinates.
- Existing known cells and placed player-built structures have priority over
  decorative instances. Guard house occupancy, property, caves, crops, roofs,
  artificial light fixture state, save retry and deterministic world seeds.
- Any changed physical footprint, save field or interaction rule requires a
  reviewed migration and upgrade/rollback tests; never silently alter save
  schema or reinterpret an old trunk as multi-cell collision.

## 5. Art production pipeline / first approval pack

**Do not mass-generate content before the camera, anchor and material specs
exist.** First ship a coherent vertical slice and have the user approve actual
forest/camp/village/interior references. Preserve source art and provenance.

### Required asset channels

| Category | Deliverables | Metadata/behavior |
| --- | --- | --- |
| Trees (first: oak + pine) | trunk/root sprite, crown foreground, optional leaf gaps, projected shadow silhouette, seasonal variant | Separate trunk anchor, crown coverage, height, bounds, collision footprint; canopy fades only on overlap |
| Trees (later) | broadleaf families, birch, dead trees, saplings, swamp/riparian, biome growth variants | Distinct canopy sizes, ecological placement, winter/season states |
| Player + NPC (first: 1 each) | front/back/left/right idle and walking, optional equipment overlay | Same foot anchor, actor dimensions, cast-shadow mask and facing-independent hitbox |
| Player + NPC (later) | all approved appearance variants, profession outfits, animals/monsters | Maintain selection IDs and visual identity; no save-data reshuffling |
| Terrain | grassland/forest/shore/wetland paths, edge transitions, soil, low moss | Repeat-resistant ground decals; no artificial outline seams |
| Understory | grass tufts, tall grass, reeds, flowers, ferns, weeds, stones, leaf litter | World-seeded deterministic placement; no unintended interaction or extra items |
| Fire/light props | campfire, street torch, wall torch, lantern, sconce, brazier, hearth/fireplace, candles, forge later | Base art + warm emissive map + light anchor + optional smoke/flame sprite; fueled on/off from real state |
| Weather | rain streak/splash sheets, cloud shadows, localized fog banks, drifting mist, smoke | Multi-depth appearance, roof/canopy masking, wind and lighting cues |
| Building/large props | roof/canopy/overhang variants, beams, awnings, signs, tall storage props | Explicit occlusion mask, authoritatively grounded door/footprint, roof fade contract |

For every atlas, require a manifest entry in or referenced by
`worldseed/assets/visuals.json` with authored layers, orientation, atlas
coordinates, anchor and visual size; save original art sheets and derivation/
generation provenance. Add automated PNG alpha, trim, foot-anchor, orientation,
light-mask correspondence, duplicate/reuse, content-ID coverage and package
inclusion audits. Existing Dev42 art/IDs remain usable until replacements
pass reference review.

## 6. Sun, moon, shadow and real-time lighting design

**Shared authority:** use `LightingSystem.at`, simulation minutes, weather,
`indoor_sources`, `outdoor_sources` and room/wall occlusion as input. A
higher-quality rendering field is derived presentation, **not a separate
stealth/gameplay light authority**.

- **Directional sun/moon:** derive azimuth and height from time-of-day and
  season; cast shadow silhouettes scaled and offset by height. At midday
  shadows are shorter; at sunrise/sunset longer; strong overcast reduces
  contrast, darkness weakens sun shadows. Clamp length and quality tiers.
- **Trunk/canopy shadow:** canopy projected separately with soft alpha and
  light-gap masks; vegetation wind can animate masks without moving the actual
  physical trunk. Players beneath remain correctly lit/covered.
- **Actor shadows:** ground-contact shadow at feet, plus low-cost directional
  projected shape from authored mask. Recenter every movement frame; no ghost
  at the previous tile and no camera-tethered offset.
- **Point lights:** light color/radius/intensity from existing gameplay fixture
  and fire catalogs; optional new torch/hearth definitions use actual
  authoritatively placed, fueled or toggled instances (not decorative phantom
  lights). Support indoor wall occlusion and outdoor nearby occluders.
- **Flicker:** bounded seeded visual phase per light UID, smooth low-amplitude
  variation of emitted presentation intensity, emissive alpha and local
  projected shadows. Flicker must **not** randomize gameplay visibility or
  consume simulation RNG. Turn off immediately on authoritative extinguish.
- **Frame interpolation:** visually interpolate fractional sun angle/ambient
  between authoritative game-minute samples; never modify the game clock,
  schedule NPC AI, force additional ticks or fast-forward daylight. Current
  baseline pacing is in `REALTIME_SECONDS_PER_GAME_MINUTE` (1.5 seconds
  per game minute); pacing changes are a separate gameplay decision.
- **Quality:** low = ambient + contact shadows; medium = sun silhouette +
  capped lights; high = soft shadows, normals/emissive response, bloom and
  optional higher-resolution lighting. All share collision/visibility rules.
- **Visual correctness:** lights/shadows respect roofs, floor height, cliffs,
  canopy gaps, underground darkness and visibility masks, without lighting
  up unrevealed interiors or treating beauty lighting as x-ray vision.

## 7. Weather, terrain smoothing and graphics enhancements

- **Fog:** multi-depth, world-anchored coherent banks with humidity/biome/
  elevation preferences, slow wind drift, nocturnal/early-morning intensity,
  distant desaturation, rain haze and terrain-following contact mist. Ensure
  layering behind/in front of trunks, actors, crowns and roof edges.
- **Rain:** camera-independent streaks, depth layers, splash and ripple points
  on appropriate ground/water, wet-surface specular changes and warm light
  pickup under lamps. Mask rain under sealed roofs; differentiate canopy
  interception from indoor shelter and avoid damaging game visibility rules.
- **Storms:** clouds with directional shadow, lightning flashes and selected
  localized impact effects, with bounded particle budgets and seizure/reduced-
  flash accessibility option.
- **Terrain transitions:** deterministic material blending/decal matching
  across biomes, river banks, forest floor, sand, gravel and road edges.
  Tile ownership stays exact; art blending never smooths away impassable
  cliffs, river depths, doorways or hidden terrain boundaries.
- **Decorations:** seeded ground foliage at consistent world positions, not
  glued to the player camera. Use chunk/region caches, edge-overlap culling,
  changing seasons and revision invalidation; keep collectible forage separate
  from purely decorative grass.
- **Postprocessing:** shader-capable path only: blur, bloom, color grading,
  water distortion and height-aware fog are **optional** after core occlusion
  is stable. True volumetric scattering would require a deliberately bounded
  2.5D depth/height volume, not ordinary SDL2 alpha blits.

## 8. GPU backend and engine migration boundaries

- **Architectural decision record (ADR) first:** compare ModernGL/OpenGL,
  pygame SDL2 Renderer and other realistic Windows-capable 2D paths against
  texture atlases, batching, shaders, render-to-texture, alpha blending,
  framebuffers, UI/input compatibility, distributable dependencies and driver
  support. SDL2 compositing alone is **not** a general shader solution.
- **One presentation owner:** do not create competing SDL windows to deliver
  final gameplay. Define one window/context, one event pump, safe
  present/swap, framebuffer color/alpha contract and resize/device-loss
  recovery; keep input coordinates mapped through the shared camera.
- **Incremental ownership:** begin with terrain and decorations in GPU
  buffers, then static shadows / trees, actors, roofs/canopies, dynamic
  lighting, weather and finally UI composition. Use a stable isolated
  test scene and keep the software renderer as known-good fallback.
- **Memory and performance:** capped source/GPU texture atlases and per-frame
  upload budgets, bounded visible instances/particles/occluders, revision-based
  invalidation, scene material batching, no per-frame full-resolution uploads
  of unchanged layers. Log GPU driver, context loss, bytes, draw calls,
  frame p50/p95/p99 and timings by stage; report accurate fallback status.
- **Parity stages:** exact pixels where same algorithm/color pipeline is
  intended, otherwise reviewed perceptual reference targets with explicit
  signed-off differences. Do not claim pixel identity for shaders that
  intentionally implement new lighting or translucency.

## 9. Executable work plan (small resumable increments)

Use **G0–G9** as phase IDs. Each unit fits the project's ~25-minute
development-window rule: implement a coherent slice, run targeted validation,
update handoff and changelog, commit/sync a green state. Do not start several
half-finished phases in parallel or proliferate branches.

| Phase | Deliverable / minimal slice | Must pass to exit |
| --- | --- | --- |
| **G0 — reference and ADR** | Inventory current render order, actor/roof/structure hitboxes, sprite anchors and tree placement; approve 4 scenes and GPU API ADR; capture software baseline and save-version contracts. | Forest, camp, village, interior baseline captures; no world mutation; existing optimizations retained. |
| **G1 — unified 2.5D scene graph** | Introduce test-only `WorldVisualInstance`, world-space projection, foot-anchor sort and independent ground/upright/overhead passes. Start **without replacing** existing gameplay renderer. | Deterministic layering, scrolling, sub-tile motion, viewport culling, zoom/resize and exact old visuals in fallback. |
| **G2 — one interactive canopy** | Implement one oak tree with a trunk and overhanging crown; player walks under crown; crown local fade; shadow independent; accurate targeting. | Walk around tree, under canopy, behind trunk; NPC visibility and fog-of-war correct; old save positions unchanged. |
| **G3 — ecology and resourcegen** | New-tree spacing profiles and cross-chunk exclusion behind a new resourcegen version; trunk/canopy footprints; safe roads/spawns/caves. | 10+ deterministic seeds, chunk seam audit, traversal and village path/door access, legacy saves bit-for-bit resource positions. |
| **G4 — first art pack** | Approval-quality oak/pine trunks/crowns/shadows; player/NPC directional proof-of-concept; grass/fern details; metadata/atlas pipeline. | Anchors, alpha, sizes, provenance, package coverage and four-scene screenshots approved. |
| **G5 — solar shadow and camera** | Sub-tile follow camera, offset/culling policy; sun/moon direction, actor/tree projected shadows, cloud responsiveness, layered occlusion. | Morning/noon/dusk/night screenshot and frame tests; camera/zoom/occlusion/actor motion regressions. |
| **G6 — emissive lights + covered spaces** | One working street torch, fireplace and campfire with emissive, distance falloff, subtle seeded flicker, moving NPC shadows; interior wall blockers. | Fuel/on-off persists, shadow correct, no indoor light leak/visibility regression, reduced-flash option. |
| **G7 — weather and ground life** | Fog depth layers, improved rain/splashes, shelter/canopy interception, weather light response, grasses and terrain transitions. | Same-seed/replay/phase checks, no screen-attached fog, performance budget under storm load, legible interaction/UI. |
| **G8 — live GPU cutover candidate** | Integrate chosen shader backend into single game window by passes and quality tiers; fallback and context reset; new art enabled only when safe. | 4 reference scenes, active 30–60-minute Windows playtest, resize/alt-tab/fullscreen/input/dialogue and save/load; no hardware crash. |
| **G9 — visual polish and release gate** | Expand validated assets to more trees/actors/objects, optional bloom/blur, settlement lighting, terrain material polish and 4K benchmarking. | Device matrix, high-res p95 target evidence, 10k-NPC/performance tests, no memory creep, long-session stability, approved art. |

**Critical-path dependency:** G0 → G1 → G2 (visible proof) → G3 (new
placement) and G4 (asset expansion) → G5/G6/G7 → G8. GPU API research and
standalone hardware profiling may continue beside G1–G7, but **default live
GPU cutover cannot be declared before G8 gates**. Art creation follows early
occlusion/anchor specs; do not wait until the end to test camera and canopies.

## 10. Regression suite and acceptance checklist

1. **Spatial correctness:** one mature oak (trunk and multi-cell crown),
   overlapping pines, player underneath, NPC beside, player behind,
   walls/roof overhang, bridge and tall street torch. Feet anchor and art
   sorting correct at all supported zoom levels. No trunk collision drift.
2. **Worldgen:** compare fixed-seed old-version world/resource fingerprints;
   10+ seeded new-generation traversability, forest spacing statistics,
   seam-free crowns, road/cave/river/settlement entrance access; massive
   canopy clusters remain bounded.
3. **Visibility/privacy:** fog-of-war never exposes hidden NPCs, unexplored
   ground, interior furniture, blocked vision or another room. Canopy/roof
   fade affects only approved already-visible layers.
4. **Lighting:** sunrise/noon/sunset/night and seasonal variations; moving
   player/NPC actor-shadow lockstep, overlapping lights, flicker, fire out,
   indoor occlusion, cave darkness, storm cloud shadows. Presentation does
   not consume authoritative RNG or reschedule any NPC ticks.
5. **Weather:** wind movement world-space, rain/canopy/roof interception,
   lightning/reduced-flash, fog readability in village and forest,
   lake/shore puddles, idle animation stability and cache invalidation.
6. **Inputs/UI:** WASD movement only, hover/drag/select, click hit masks,
   building and inventory panels, map world interactions, portrait dialogue,
   tooltip, fullscreen/maximized/minimized/resize/alt-tab, reduced effects.
7. **Save compatibility:** open legacy and new saves; remove a tree then
   revisit/reload; torch extinguishes/persists; no asset-revision data
   migration without explicit versioning; failed-save retry remains atomic.
8. **Performance:** profiler stages for projection, terrain batch, sorting,
   shadow map, lights, particles, GPU uploads and present; report p50/p95/p99,
   worst frame, memory bounds and 60 FPS budget (16.7 ms p95 aspiration)
   at 1080p/1440p/4K on actual Windows drivers. No paper GPU win from
   dummy SDL; benchmark forest/village/camp/storm/night and distant NPC save.
9. **Packaging:** all referenced atlases, shader sources and fallback textures
   inside Windows build, with direct cold launch, diagnostic report and
   readable error handling. Never push a broken or unvalidated release.

## 11. Decisions to record before implementing G1–G3

- Art style and perspective: top-down 2.5D, coherent upright sprites with
  fixed ground anchors; **player approval** of four reference screenshots.
- Tree species, physical trunk footprint and overhanging crown sizes;
  how much selective crown overlap and density is acceptable.
- Default opacity and radius of a player-visible canopy cutout and
  whether visible allied NPCs also trigger local fade.
- Camera anchor/look-ahead/zoom scales and safe-space UI margins;
  whether roof fade remains room-driven instead of player proximity.
- Preferred GPU API and compatibility fallback; target low-end hardware,
  quality presets and real test device/driver.
- Simulation time-rate UX **independent** from render interpolation.
- Which light sources are purely decorative versus powered by actual
  fueled/toggled gameplay state. Avoid visual/gameplay desynchronization.

## 12. First next-chat work unit (start here; do not jump to full GPU migration)

**Task G0 → G1a: scene-layer and canopy contract.**

1. Re-check main Fast Gate and read existing M2 engine/graphics docs; preserve
   every engine optimization plan. Record baseline commit and source tests.
2. Add a small immutable scene-instance contract and camera projection
   module **outside** the 4,900-line pygame terminal; keep one owner of each
   hitbox, visual anchor and screen transform.
3. Implement deterministic z/foot-anchor sorting and a bounded overhead
   occlusion relationship for one synthetic tree, player and NPC. Treat
   canopy as separate visual child of unchanged tree resource.
4. Write focused tests for player-under-canopy alpha, trunk collision,
   NPC concealment, old save compatibility, zoom/camera and frame ordering.
5. Produce one comparative scene/probe and handoff; keep production software
   renderer unchanged until this slice is validated. Add one GPU integration
   test only if a real context is available; otherwise report it as untested.
6. Sync validated code/tests/handoff to `ReleMai/WORLDSEED` `main` in the
   same work session (descriptive commit); do not create a permanent feature
   branch or push failing states.

### Authoritative links for new chats

- Existing engine optimization: [`EARLY_ACCESS_PYGAME_PLAN.md`](EARLY_ACCESS_PYGAME_PLAN.md).
- Measured engine M2: [`EARLY_ACCESS_M2_ENGINE_CLOSEOUT.md`](../handoffs/EARLY_ACCESS_M2_ENGINE_CLOSEOUT.md).
- Existing GPU experiment: [`GPU_COMPOSITING_EXPERIMENT.md`](GPU_COMPOSITING_EXPERIMENT.md).
- This roadmap: `docs/development/WORLDSPACE_RENDERER_ART_WORLDGEN_ROADMAP_2026-10-14.md`.
- Startup instructions: [new graphics handoff](../handoffs/WORLDSPACE_RENDERER_ART_G0_START_2026-10-14.md).
