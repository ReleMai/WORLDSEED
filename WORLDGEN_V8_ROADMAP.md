# WORLDSEED WORLDGEN v8 — Geological Living World Roadmap

Status: **WORLDGEN v8 Phase 5 physical coast implementation is delivered in Dev35 (coast morphology v2). Phase 6 — Geomorphology, Substrate and Soil — is next. Release-hardening gates and wider visual calibration remain distinct from implementation completion; see DEV35_VALIDATION.md.**

WORLDGEN v8 is a staged replacement for WORLDSEED's noise-first surface
generation. It does not discard the existing RC14 architecture: deterministic
seeds, prepared hydrology domains, sparse persistence, environmental fields,
physical settlement plans, route planning, atlas truth, and renderer
observational boundaries remain mandatory.

The new causal chain is:

```text
seed + versions
-> geological provinces / landforms
-> elevation + bathymetry
-> climate circulation
-> drainage / rivers / lakes
-> coast morphology
-> soils / geomorphology
-> ecological mosaics
-> resource opportunity
-> settlements
-> roads / crossings
-> local materialization + cartography
```

## Non-negotiable compatibility rules

- Existing worldgen v1-v7 saves never receive v8 geography during normal load.
- `WORLDGEN_VERSION = 8` applies to newly created worlds only; never rewrite the `worldgen_version` stored in an existing v1-v7 save.
- v8 landforms/topography are authoritative only for v8 worlds. The explicit `version <= 7` generator path remains the compatibility contract for legacy saves.
- Every v8 random domain uses stable named namespaces and fixed version inputs.
- No renderer, hover, movement, or inspection path may generate regional data.
- Generated base geography may be rebuilt; player/history mutations may not.
- The terrain atlas remains a truth projection, not an alternate generator.

---

## Phase 0 — v7 Baseline Freeze and Comparison Harness

### Goal
Create a permanent before/after reference so v8 improvements can be measured
without accidentally rewriting old generation contracts.

### Work
- Select 10-16 golden seeds including negative-coordinate coverage.
- Record v7 terrain fingerprints, hydrology fingerprints, spawn positions,
  start fairness, resource density, traversability, pregeneration duration, and
  representative local/atlas/region screenshots.
- Add comparison scripts that can sample v7 and prototype-v8 fields over exactly
  the same coordinates.
- Record current coastline ratio, elevation histogram, slope distribution,
  river-class distribution, biome proportions, and connected walkable area.

### Exit gates
- Repeated v7 generation matches frozen fingerprints.
- Golden seeds can be regenerated in a clean checkout.
- Comparison reports are deterministic and machine-readable.

---

## Phase 1 — Geological Landform Prototype

### Goal
Replace "elevation is mostly blended noise" with deterministic broad physical
landforms while keeping the prototype non-authoritative.

### Work
- Add a dedicated `worldseed/world/landforms.py` subsystem.
- Generate broad continentalness independent of climate.
- Generate elongated deterministic orogeny/range features rather than circular
  high-noise blobs.
- Generate inland basins and broad plateaus.
- Add fine roughness only after large-scale structure exists.
- Classify sampled points into prototype provinces:
  oceanic plain, lowland, basin, rift valley, upland, plateau, mountain chain.
- Keep all math integer-based where it enters the generation contract.
- Add a bounded debug sampler cache.
- Add a standard-library audit exporter for field CSV + PPM preview.
- Add deterministic and negative-coordinate tests.
- Expose prototype sampling through `WorldGenerator` without altering v7
  authoritative fields.

### Validation
- Same seed/coordinates -> identical field values and province IDs.
- Negative coordinates contain no seams caused by modulo/division behavior.
- Mountain influence forms connected elongated structures across tectonic-cell
  boundaries.
- Multiple large landform types occur across golden-seed windows.
- v7 `sample_fields()` is unchanged before/after prototype sampling.
- Elevation remains on WORLDSEED's existing 0..65535 scale.

### Exit gates
- Visual review confirms recognizable ranges/basins/plateaus at multiple seeds.
- No live save or v7 terrain output changes.
- Prototype generation time is acceptable for prepared-domain use.

---

## Phase 2 — v8 Elevation Authority and Version Boundary

### Goal
Promote approved geological landforms into the authoritative elevation field.

**Dev25 progress:** the authority boundary is implemented for explicit
`WorldGenerator(version=8)` contexts. v8 now uses the geological elevation
compositor while retaining the frozen v4 moisture/temperature driver until
Phase 3. The default `WORLDGEN_VERSION` remains 7, with
`WORLDGEN_PREVIEW_VERSION = 8`, so this code can be exercised by audits/tests
without silently changing newly created player worlds. A v8-aware large-scale
spawn search and multi-seed calibration tool were added before promotion.

**Dev26 progress:** Phase 2 now exposes a deterministic topographic derivative
layer over v8 elevation (slope vector, normalized slope, raw/normalized relief,
ridge exposure, valley depth and ruggedness). Cave entrances for explicit v8
worlds now use these geological/topographic fields instead of the legacy v7
siting rule, while v7 cave placement and underground generation remain frozen.
A dedicated topography/cave audit was added for calibration before promotion.

**Dev27 promotion:** `WORLDGEN_VERSION` is now 8. New save databases record v8
at creation and therefore use geological elevation, v8 topography, v8 cave-mouth
siting and the existing prepared hydrology/coast projection. Existing saves keep
their recorded version and are not migrated. The former
`WORLDGEN_PREVIEW_VERSION` name remains as an alias to 8 for audit tooling.

### Work
- **DONE Dev27:** set `WORLDGEN_VERSION = 8` for newly created worlds; persisted older versions remain immutable.
- **DONE:** freeze the exact v7 field path behind `version <= 7`.
- **DONE:** v8 elevation uses the Phase-1 landform compositor.
- Calibrate sea-level/reference elevation and continental/ocean proportions.
- Add broad valley and intermontane-lowland shaping between ranges.
- Add subregional relief without destroying large forms.
- **DONE Dev26:** v8 cave-mouth suitability uses geological topography.
- Add v8 elevation fingerprint fixtures.

### Validation
- v1-v7 golden terrain remains byte-identical.
- v8 has bounded elevation/slope distributions across 20+ seeds.
- Spawn search can find viable land on all audit seeds.
- No pathological all-ocean/all-mountain prepared windows.
- Negative-coordinate generation remains seamless.

### Exit gates
- New v8 worlds load/save/reload deterministically.
- Legacy saves never silently adopt v8 terrain.

---

## Phase 3 — Physical Climate Circulation

### Goal
Make climate respond to geography instead of acting as an independent noise map.

**Dev28 implementation:** `ClimateV8Sampler` now owns v8 temperature and
precipitation fields. It combines repeating broad climate belts, maritime
moderation, continentality, prevailing wind belts, altitude cooling, upwind
terrain sampling, orographic lift and leeward rain shadows. V8
`WorldGenerator.sample_fields()` now consumes these fields directly, so the
existing hydrology/resource/environment consumers already see physical v8
climate instead of the temporary v4 moisture/temperature sheet.

The same phase now includes a deterministic weather/light presentation chain:

```text
physical climate
-> moving weather cell / cloud cover / rain / storm / fog
-> recent-rain surface wetness
-> day/dawn/dusk/night light state
-> pygame wet-ground texture + cloud-shadow mask + rain/splash animation
-> night grading + local fire glow
```

Weather remains simulation-owned and renderer-observed. Renderer animation may
advance visual rain frames using wall-clock time, but it cannot change the
authoritative weather sample or simulation clock.

### Work
- **DONE Dev28:** add stable broad latitude/climate-band potential.
- **DONE Dev28:** add prevailing wind belts/directions.
- **DONE Dev28:** add oceanic/maritime moderation near coasts.
- **DONE Dev28:** add continentality for large inland regions.
- **DONE Dev28:** derive orographic rainfall from windward ascent.
- **DONE Dev28:** derive rain shadows on leeward sides of major uplifts.
- **DONE Dev28:** keep altitude temperature lapse effects inside the physical climate sampler.
- **DONE Dev28:** separate long-term precipitation potential from dynamic weather wetness.
- **DONE Dev28:** preserve seasonal/game-time systems as consumers rather than geography authority.

### New read fields
- mean_temperature
- precipitation_potential
- maritime_influence
- continentality
- prevailing_wind_dx/dy
- orographic_lift
- rain_shadow
- humidity
- wind_strength
- dynamic cloud_cover / rain / storm / fog / wetness (weather read model)
- daylight / ambient_light / darkness_alpha (lighting read model)

### Exit gates
- Mountain chains produce measurable wet/dry asymmetry.
- Coasts moderate temperature relative to continental interiors.
- Climate fields remain continuous across chunk/domain boundaries.
- Weather is deterministic from seed + game time + coordinates and does not mutate from rendering.
- Rain visibly wets surface terrain and produces animated streak/splash presentation.
- Cloud cover projects soft terrain shadows without revealing undiscovered geography.
- Surface gameplay visibly transitions through dawn/day/dusk/night; UI remains readable.
- Night/local-fire presentation remains observational and does not create simulation light sources.

**Implementation status:** code landed in Dev28; executable multi-seed/pygame
validation is still required before declaring the Phase-3 release gate closed.

---

## Phase 4 — Hydrology v2: Drainage That Follows v8 Landforms

### Goal
Rebuild the proven Priority-Flood pipeline on v8 geography and improve local
river morphology.

**Dev29 implementation start:** `HYDROLOGY_VERSION = 2` is now the new-save
contract. Hydrology v2 keeps the seam-safe Priority-Flood window solver, but
runoff comes from Phase-3 precipitation, wet uplands receive headwater support,
and persisted domains now record runoff plus downstream channel gradient.
Existing saves retain their stored hydrology version; missing metadata is
treated as legacy v1 rather than silently upgrading river geography.

Local channel projection now uses gradient-sensitive meander amplitude,
confluence widening, physically screened ford candidates, and first-pass
channel morphology labels for rapids/gorges, braided reaches, meandering/oxbow
potential and low-gradient delta candidates. The latter are read-model signals
for later terrain/art refinement, not a separate river authority.

**Dev30 continuation:** the projection layer now has its own
`HYDROLOGY_MORPHOLOGY_VERSION = 2`. This lets new worlds use multi-point
centerlines, split braided threads, detached oxbow scars and rocky gorge banks
without rewriting Dev29 hydrology-v2 saves, which infer morphology v1 when the
new metadata is absent. Surface chunk caches are now keyed by worldgen +
hydrology + morphology version so independently versioned river projection
cannot reuse an incompatible cached chunk.

### Work
- **DONE Dev29:** introduce `HYDROLOGY_VERSION = 2` for new saves while preserving stored v1 contracts.
- **DONE Dev29:** preserve seam-safe multi-domain window solving, including v2 runoff/gradient overlap checks.
- **DONE Dev29:** run the existing Priority-Flood depression solver directly on authoritative v8 elevation.
- **DONE Dev29:** derive local runoff from authoritative Phase-3 precipitation; rain shadows therefore reduce discharge through the climate field itself.
- **DONE Dev29:** wet high terrain receives bounded headwater runoff/classification support.
- **DONE Dev29:** preserve class hierarchy from accumulated discharge with v2 thresholds.
- **DONE Dev30:** replace single-midpoint v2 projection with deterministic multi-point channel centerlines; morphology v1 preserves Dev29 midpoint geometry.
- **DONE Dev29:** meander amplitude increases as channel gradient falls and remains tight in steep headwaters.
- **DONE Dev30:** confluences/tributary junctions widen from upstream count and braided reaches physically split/rejoin, leaving base-terrain river islands between threads.
- **DONE Dev30:** suitable braided reaches materialize as two deterministic channel threads using the existing freshwater terrain family.
- **DONE Dev30:** mature low-gradient reaches can materialize detached shallow-water oxbow/meander-scar rings in their floodplains.
- **DONE Dev30:** rapids/gorge labels remain gradient/ruggedness-driven and steep confined banks can materialize as rocky gorge margins.
- **PARTIAL Dev29:** ford selection is now physically gated by class, gradient, bank slope, discharge and floodplain; deterministic hashing only breaks ties among suitable reaches.
- **PARTIAL Dev29:** low-gradient, high-discharge near-sea reaches expose deterministic delta candidates; delta morphology remains Phase 5 work.

### Exit gates
- Every core drainage node terminates correctly.
- Downstream discharge is monotonic absent explicit splits.
- River continuity is seam-safe.
- Major rivers are rarer/wider than minor streams.
- Fords and crossing costs are physically explainable.

---

## Phase 5 — Coast, Bathymetry, Estuary and Delta Morphology

### Goal
Replace mostly uniform shoreline bands with varied coast types.

**Dev32 implementation start:** a new `CoastV8Sampler` read model derives continental-geometry bathymetry, open-sea exposure, shelter, bay/headland scores, shore-material tendency, tidal-flat/marsh/lagoon potential and river-mouth sediment/estuary/delta potential. It is deliberately **terrain-neutral** in this first slice: no existing coast tiles, saves, surface caches or user-facing graphics are rewritten yet. The purpose is to establish and audit one causal coastal authority before materialization.

**Dev33 materialization:** new worlds now pin `COAST_MORPHOLOGY_VERSION = 1`. The approved Phase-5 fields materialize into real gameplay terrain: continental-geometry ocean depth bands plus sandy, gravel, rocky, cliff, tidal-flat and salt-marsh coast classes. Existing v8 saves without coast metadata infer coast version 0 and retain their pre-Phase-5 shoreline. Surface caches now include the coast contract. Expensive coast classification is sampled on an absolute 8-cell lattice for materialization while exact geological elevation still determines land versus water per cell.

**Dev35 completion:** coast morphology v2 adds bounded river-mouth indexes derived from prepared hydrology, broader estuaries, connected delta branches, shallow lobes and wind-directed sediment barriers/lagoon pockets. V0/v1 saves keep their recorded projection. Twelve real-seed domains and exact shared-boundary samples audit the implementation; dedicated biome art/substrate refinement and release-wide acceptance remain later work.

### Work
- **MATERIALIZED Dev33:** bathymetric shelf depth derives from continental geometry plus raw sea depth and now selects actual ocean depth terrain in new worlds.
- **PARTIAL/MATERIALIZED Dev33:** beaches, gravel shores, rocky shores, coastal cliffs, tidal flats and salt marshes now become real terrain. Protected-bay/headland reads exist; Dev35 adds sediment-fed spits/barrier candidates and sheltered lagoons beside physically suitable river mouths.
- **PARTIAL Dev32:** use slope, relief, shelter and wave exposure to derive shore-material tendency; Phase 6 substrate will later refine it.
- **FOUNDATION Dev32:** derive river-mouth sediment, estuary and delta potential from prepared hydrology; Dev35 materializes connected distributaries and shallow depositional lobes from those prepared drainage edges.
- **MATERIALIZED Dev35:** estuary width follows discharge class and coastal shelter; shallow/deep brackish cells, crossings and currents use the same mouth projection.
- **FOUNDATION Dev32:** derive shallow embayment/lagoon potential as a read field.
- Keep ocean current presentation tied to authoritative current fields.

### Exit gates
- Coastlines contain multiple morphology classes per large audit domain.
- River mouths connect cleanly into estuaries/deltas.
- No one-cell coastal discontinuities across prepared-domain seams.

---

## Phase 6 — Geomorphology, Substrate and Soil

### Goal
Make topography visible through the ground itself.

### Work
- Derive slope classes and aspect from v8 elevation.
- Add cliff/escarpment candidates on extreme gradients.
- Add talus/scree beneath steep exposed rock.
- Add alluvial fans where steep tributaries exit into flatter terrain.
- Add river terraces and young floodplain/alluvial deposits.
- Add substrate classes: sand, gravel, loam, clay-rich, shallow bedrock, rocky.
- Derive soil depth, fertility, drainage and erosion susceptibility.
- Separate stable physical substrate from seasonal surface presentation.

### Exit gates
- Soil/substrate follows landform/hydrology causally.
- Cliffs/scree do not create impossible start regions or route traps.
- Environmental fields consume the same substrate authority.

---

## Phase 7 — Ecological Mosaic / Continuous Vegetation

### Goal
Move beyond one discrete biome ID per cell while retaining readable gameplay.

### Work
- Keep broad biome/climate labels for summaries.
- Add continuous vegetation cover:
  tree canopy, shrub cover, grass/herb cover, wetland vegetation, bare ground.
- Add elevation/tree-line suppression and alpine transition.
- Add forest density/age/edge fields.
- Add woodland, savanna-like open tree cover, meadow/steppe, bog/marsh,
  alpine meadow, sparse tundra, and scree mosaics where climate supports them.
- Let disturbance/history later alter cover without rewriting climate.
- Retain terrain IDs as gameplay/materialization categories derived from fields.

### Exit gates
- Biome boundaries read as ecotones rather than threshold walls.
- Forests have internal clearings/edges and density variation.
- Vegetation distributions remain deterministic and spatially coherent.

---

## Phase 8 — Geological and Ecological Resource Placement

### Goal
Make resources appear because the world can support them.

### Work
- Tie timber/forage to actual vegetation cover.
- Tie stone/ore opportunity to geological province/substrate.
- Tie clays/sands/gravels to depositional environments.
- Tie fish/shellfish/reeds to real water habitat classes.
- Re-evaluate blocker spacing and resource clutter against new terrain.
- Preserve resource regeneration and sparse persistence contracts.

### Exit gates
- Resource opportunities correlate strongly with causal fields.
- Zero-item bootstrap remains achievable.
- Blocking resources preserve traversability.

---

## Phase 9 — Local Terrain Materialization and Visual Diversity

### Goal
Make the new physical fields visible without creating a second visual world.

### Work
- Extend terrain tags/material families for new substrate/landform categories.
- Add deterministic presentation variants driven by authoritative fields:
  wet/dry grass, exposed soil, gravel, moss/litter, reed margins, scree, etc.
- Add slope/shore/river edge overlays.
- Improve cliff and elevation readability without fake 3D topology.
- Use terrain-family autotiling rather than pair-by-pair exceptions.
- Keep microvariation presentation-only unless it affects simulation.

### Exit gates
- Local terrain visually communicates wetness, slope, substrate and vegetation.
- Tile transitions remain seamless and future/modded ground remains data-driven.
- Renderer cannot mutate or generate terrain.

---

## Phase 10 — Settlement Carrying Capacity and Geographic Siting

### Goal
Remove the remaining random 42%-presence dependency for v8 civilization.

### Work
- Preserve legacy settlement presence rules for v1-v7.
- Compute v8 settlement potential from water, farmland, timber, minerals,
  crossing value, climate stress, route opportunity and defense.
- Add regional carrying capacity and minimum spacing by settlement rank.
- Allow settlement clusters in productive valleys/coasts and sparse settlement
  in marginal environments.
- Generate daughter hamlets along routes/resource frontiers.
- Bind settlement archetypes to actual local opportunity.
- Keep simulation ledger authority separate from physical plans.

### Exit gates
- Settlement frequency tracks carrying capacity, not arbitrary region rolls.
- Settlement anchors occupy legal terrain and plausible access points.
- Same seed produces identical sites/archetypes.

---

## Phase 11 — Terrain-Constrained Roads, Passes and Crossings

### Goal
Make civilization's transport network explainable from terrain.

### Work
- Replace probability-only regional edge selection for v8.
- Build sparse strategic candidate graphs among realized/prepared settlements.
- Score economic/strategic utility.
- Rasterize accepted edges through terrain-cost corridors.
- Prefer valleys, ridgelines where appropriate, natural passes and existing roads.
- Use real ford/bridge candidates from hydrology.
- Persist route corridors and crossing IDs.
- Let road condition/traffic/history feed the same physical route plan.

### Exit gates
- Strategic graph remains sparse and connected where appropriate.
- Roads avoid cliffs/deep water unless crossing infrastructure exists.
- Route costs respond to slope, wetness, surface and bridge state.

---

## Phase 12 — Atlas and Regional Cartography Unification

### Goal
Ensure every zoom level tells the same geographic story.

### Work
- Keep the exact terrain atlas as the truth source.
- Replace dominant-biome regional squares with a prepared low-resolution
  generalized raster derived from authoritative terrain.
- Overlay relief, rivers, roads and known settlements from real plans.
- Preserve discovery/knowledge gating.
- Add cartographic generalization only; never invent unseen physical features.

### Exit gates
- Local map, terrain atlas and region map agree on coast/river/terrain placement.
- Region-map inspection performs no generation or simulation mutation.

---

## Phase 13 — Underground Geological Coupling

### Goal
Make caves and ore geology correspond to the new surface geology.

### Work
- Preserve v7 cave rules for v7 saves.
- Use v8 geological province/substrate to influence cave style/depth.
- Couple limestone/karst-like cave potential, fracture caves, volcanic/igneous
  zones, sedimentary coal and metallic ore belts to broad geology.
- Keep cave mouths terrain-aware and reciprocal.
- Preserve protected shaft/chamber traversal.

### Exit gates
- Surface geology predicts underground tendencies without perfect certainty.
- Ore/cave placement remains deterministic and bounded.

---

## Phase 14 — Pregeneration, Persistence and Performance

### Goal
Prepare richer worlds without moving expensive work into movement/render loops.

### Work
- Decide which v8 fields are reconstructable functions versus cached domains.
- Extend startup stage progress/timing.
- Precompute required geological/climate/hydrology domains for the opening ring.
- Add bounded LRU caches and revision/fingerprint keys.
- Prepare future expansion rings in explicit background/quiet phases.
- Profile CPU/memory/database growth before parallelization.
- Keep writes separate from pure CPU generation if worker pools are added.

### Exit gates
- Entering prepared chunks performs reads, not regional generation.
- Movement/hover/render latency does not trigger v8 planning.
- Cache deletion recreates identical base geography.

---

## Phase 15 — Release Hardening and WORLDGEN v8 Acceptance

### Required audits
- Determinism and RNG namespace isolation.
- v1-v7 legacy geography fingerprints.
- Hydrology sinks/cycles/seams/discharge hierarchy.
- Coast continuity/morphology distribution.
- Elevation/slope/ocean coverage distributions.
- Biome/ecotone/vegetation distribution.
- Resource opportunity and blocker density.
- Settlement legality/carrying-capacity distribution.
- Route connectivity/crossing legality.
- Spawn fairness and zero-item bootstrap.
- Save/reload and generated-cache rebuild.
- 25-year and 100-year simulation soaks.
- Pregeneration and ordinary movement/render benchmarks.
- Visual review across golden seeds at local, atlas and regional zoom.

### Final acceptance
WORLDGEN v8 is ready only when the generated world is both more believable and
more internally coherent: mountains shape climate; climate and elevation shape
water; water and soil shape ecology; ecology/resources shape settlement; terrain
and settlements shape roads; and all zoom levels display that same physical
world without contradicting simulation state.
