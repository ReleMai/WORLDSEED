# WORLDSEED v1.0 RC14 Development — systems and causality map

This document describes **ownership boundaries and causal contracts**. WORLDSEED should become more complex by composing systems, not by allowing every module to edit every other module's state.

## Central architecture

```text
Terminal Input
    ↓
Typed Command
    ↓
Simulation Kernel ─────────────→ Clock / Scheduler
    │
    ├→ World Service → deterministic generation / chunk cache / sparse mutations
    ├→ Entity Store  → local player/entity components
    ├→ Living State  → sparse semantic world records
    ├→ Domain Systems
    │    ecology / AI / combat / disease / economy / factions / etc.
    └→ History Events
             ↓
          SQLite

Read Model / Renderer / World Console
    ↑
  observes only
```

The UI may ask the simulation questions. It must not create content simply because a player opened a screen.

---

## Determinism contract

The canonical inputs to procedural decisions are:

```text
world seed
system RNG namespace
stable semantic identifiers / coordinates
simulation boundary / ordinal where required
worldgen or protocol version
```

Never use Python's global `random` in authoritative generation/simulation.

Adding one random draw to ecology must not shift settlement generation, magic laws or another unrelated stream.

State hashing and cross-process replay are used as regression contracts.

---

## RC14 regional physical-plan layer (development)

RC14 adds a new authority bridge between aggregate simulation and exact nearby materialization:

```text
Simulation / ledger
    population, stocks, occupations, prices, events
            ↓
Regional physical plan
    stable roads, crossings, parcels, structure IDs, capacities, ownership links
            ↓
Local materialization
    exact footprints, doors, containers, nearby actor positions/tasks
```

The physical plan is persistent identity, not a renderer-owned decorative copy. Generated base hydrology/plans/routes are rebuildable from seed + generator versions and may be cached in SQLite. Player/history mutations are not rebuildable and therefore belong in authoritative simulation state or `physical_plan_deltas`.

### Hydrology / physical geography — Hydrology v2

WORLDGEN v8 new saves use hydrology contract v2. Prepared adjacent domains are still solved together in one larger Priority-Flood lattice and sliced back into cache records, preserving the proven seam-safe window authority. V2 samples authoritative v8 elevation plus Phase-3 precipitation, converts precipitation into bounded local runoff, accumulates discharge downstream, and persists both runoff and channel gradient beside watershed IDs, river hierarchy and floodplain strength.

Wet uplands receive bounded headwater support, while rain-shadow/arid regions contribute less runoff because the physical climate field already reduces precipitation there. Local channel projection uses gradient-sensitive meanders, tributary/confluence widening, gradient/ruggedness-driven rapid and gorge labels, physically screened ford candidates, and first-pass braided/meandering/oxbow/delta read signals. Dedicated braided islands, oxbow scars and delta terrain remain later materialization work; they do not exist as renderer-invented features.

Hydrology is independently versioned from worldgen. New saves record hydrology v2. Existing saves continue using the `hydrology_version` in their metadata; saves missing that metadata are inferred as legacy v1 rather than silently changing rivers. Generated hydrology remains rebuildable cache data, while bridges/crossing damage and other historical mutations stay in authoritative plan deltas.

River projection/morphology is independently pinned as `HYDROLOGY_MORPHOLOGY_VERSION`. Morphology v2 uses deterministic four-point centerlines, physically suitable braid splits that rejoin at drainage nodes, detached oxbow-scar water, and rocky banks around steep rugged gorge reaches. Saves missing morphology metadata infer Dev29 morphology v1. Surface chunk caches therefore use the tuple `(worldgen_version, hydrology_version, morphology_version)`; never reuse a worldgen-only surface cache for v5+ terrain.

Regional hydrology is prepared during startup pregeneration. Movement, hover, rendering and map inspection may read prepared hydrology but never solve it.

---

# Spatial model

## Tile / chunk / macro-region hierarchy

```text
Tile
  integer x,y,z

Chunk
  32 × 32 tiles

Macro-region
  coarse 512 × 512 world-tile cell
  used by settlements, economy, LOD and long-distance routing
```

Negative coordinates use floor division semantics and are regression-tested.

## Realized vs potential

A macro-region becomes realized because the player or a valid existing realized-world process makes it relevant.

Tier-E regions do **not** spontaneously instantiate daughter settlements, NPC families and markets forever into infinity.

This boundary is mandatory for scalability.

---

# Simulation LOD

## Tier A — immediate

Ownership:
- exact local map state;
- materialized individuals;
- combat and anatomy;
- local fire/fluids;
- player interactions;
- local navigation.

## Tier B — nearby

Ownership:
- named/persistent individuals;
- reduced AI cadence;
- meaningful local travel;
- state that the player could soon observe.

## Tier C — region

Ownership:
- wildlife cohorts;
- settlements;
- labor/economy;
- trade/migration;
- aggregate outbreaks;
- coarse social/political state.

## Tier D — distant realized

Ownership:
- scheduled/coarse daily or monthly equations;
- no need for every ordinary actor to receive an individual tick.

## Tier E — unrealized

Ownership:
- deterministic potential only.

Promotion/demotion must conserve authoritative quantities. Example:

```text
cohort count = 37
    ↓ materialize 3 visible wolves
player kills 1
    ↓
authoritative cohort count = 36
    ↓ surviving wolves dematerialize
count remains 36
```

Dematerialization is not a death event and must not change the aggregate.

---

# Time and offline progression

The engine separates player command cadence from slow systems.

Examples:

```text
combat/action           immediate command resolution
player survival         action / short cadence
weather/crops/fire      hourly/coarse blocks
disease/economy/ecology daily
families/politics       monthly
scheduled arrivals      exact/coarse arrival boundaries
```

Offline advancement uses event boundaries, not one-minute replay.

A newly created caravan during a fast-forward must enter the boundary schedule and may arrive before the rest of the offline interval completes.

SAFE offline policy prevents named-character fatal outcomes while still allowing illness/economic absence and aggregate progression. FULL allows eligible named mortality.

---

# Player knowledge and discovery

Simulation existence is not player knowledge. `LivingWorldState` carries discovery sets for tiles, settlements, NPC identities, factions, sites and historical events. Read models must filter through those sets rather than directly iterating all simulation records.

Discovery sources include line-of-sight exploration, entering/approaching places, direct conversation, rumors, books/records, site interaction and witnessing events. NPC identity is deliberately separate from NPC existence: an active nearby person can render as `Stranger` until `TalkCommand` reveals them.

Important invariant:

```text
engine knows X
    ≠
player knows X
```

Alerts, ledgers, ecology views, settlement/economy menus, history and look mode must never leak undiscovered proper names/details.

# Natural resource layer

Ground terrain is immutable deterministic base context unless the terrain itself is physically excavated. Surface vegetation/boulders are deterministic **features** layered over that ground. Persistent harvest state records depletion time, enabling staged regrowth without rewriting the underlying biome.

Resourcegen v3 first applies a biome-level placement budget, then chooses among habitat-eligible definitions. Blocking structural features (trees/boulders) are deterministically thinned so cardinally adjacent candidates cannot form solid walls. Cave mouths and terrain necks are protected from optional blockers. Nonblocking forage uses broader patch richness plus local gates, producing ecological pockets without making every definition an independent placement roll.

Movement and sight query both terrain and the feature layer. Mature trees/boulders may block; stumps/saplings may not. Construction, containers, crops and cultivated soils suppress wild feature realization to protect player-authored space and old-save compatibility.

Gathering accepts relative target coordinates. Surface features are harvested from current/adjacent cells; underground solid terrain is mined from adjacent cells and transformed to its declared depleted terrain.

# World generation

Base terrain is a deterministic function of seed/coordinates/version.

The persistent database stores changes such as:

- mined/changed tiles;
- structures/roofs;
- containers;
- crops/soil;
- realized fluid/fire state;
- discovered tiles;
- semantic sites/entities.

It does **not** need a serialized copy of every untouched generated tile.

Worldgen v4 keeps terrain deterministic but separates spatial scales: elevation retains local relief while moisture and temperature vary across much broader regions. Biome classification is climate-first, so forests/grasslands/scrub form coherent regions instead of depending on decoration rolls. The v3 reciprocal cave-column rules remain part of the underground contract. Recorded terrain-generation version is immutable per world; legacy saves continue to use their original generator. Natural-resource generation is versioned separately so resource-placement fixes do not require rewriting old geography.

WORLDGEN v8 is the current new-world geography/climate contract. It composes deterministic continentalness, aligned major/branch mountain belts, basins, plateaus, structural valleys, coastal detail and local roughness into one geological elevation field. A derived topography read model exposes slope, relief, ridge exposure, valley depth and ruggedness without realizing chunks. V8 physical climate then derives mean temperature, precipitation potential, humidity, maritime influence, continentality, prevailing wind, orographic lift and leeward rain shadow from that geography. `WorldGenerator.sample_fields()` consumes those physical climate values for v8, while explicit v1-v7 worlds keep their frozen field contract. New v8 cave entrances use geological/topographic fields; v1-v7 saves remain pinned to their recorded generators and are never retroactively rewritten. Hydrology remains independently versioned until the dedicated hydrology-v2 phase.

Players may also create persistent supported shafts through simulation commands. These mutations are stored as world deltas rather than changing the base generator.

Historical-site base layouts are deterministic; runtime overlays persist locks/traps/loot/occupants/clearance.

---


## Climate, weather and lighting

V8 separates long-term climate from short-term weather. Climate is reconstructable from seed + coordinates + climate version; weather is reconstructable from seed + game-time slot + weather cell + climate. The simulation owns cloud cover, precipitation, storm/fog state, recent-rain wetness and weather temperature deltas. Rain affects crops and suppresses fire through the environment system.

The pygame renderer is observational. It may render wet-ground material overlays, soft projected cloud-shadow masks, animated rain streaks/splashes, fog haze, dawn/day/dusk/night grading and local fire glow, but these effects never create or alter weather, time, terrain, discovery, or light-source simulation state. Visual animation time may move rain frames while input waits; authoritative weather remains fixed until simulation time changes.

# Ecology

## Coarse populations

`PopulationCohort` is the authoritative distant population representation.

Daily ecology uses bounded reproduction/mortality/predation/carrying-capacity equations.

## Materialized creatures

Local individuals acquire:
- position;
- HP/anatomy;
- behavior state;
- wounds;
- notable/legend status if earned.

Ordinary healthy individuals can collapse back into cohorts. Named/notable creatures remain explicit.

## Procedural species

Generation samples trait combinations under an ecological niche and runs viability checks. A species definition can affect combat, habitat, population dynamics, drops and behavior.

---

# Combat, anatomy and equipment

Combat owns attack legality/resolution. AI may request an attack but does not directly edit wounds.

Attack resolution can produce:

```text
hit location
armor interception
material/quality mitigation
surface/tissue damage
bleeding
fracture
pain/blood loss
item wear
history/legend consequences
```

Player wounds persist and can require bandage/splint treatment. Body state feeds back into stamina, movement and combat performance.

Specific durable equipment artifacts track condition and provenance. Equipment references a particular artifact where available rather than an abstract infinite item type.

---

# Crafting, materials and metallurgy

Content defines materials/items/processes. Simulation owns transformations.

Material properties include mechanical/economic characteristics. Component designs choose actual inputs per part.

Metallurgy introduces intermediate batches with carbon/purity/temperature/treatment state. Heat treatment changes quality, and that quality can flow into the finished artifact.

Important invariant:

```text
inputs consumed + outputs created
must be explainable by one declared process
```

No occupation or recipe receives resources from nowhere merely to keep gameplay moving.

---

# Building, structure, storage and fluids

Construction consumes physical inventory and creates persistent world state.

Floor-level structures and roof structures are separate layers.

Structural simulation uses support/load abstractions. Unsupported roof sections deteriorate and may collapse.

Room classification uses enclosure + semantic contents + roof/shelter data.

Containers own inventories with mass/volume capacity. Destroying a container spills contents.

Fluids use cells rather than one entity per liter. Local flow is intentionally approximate and bounded.

---

# Agriculture

Crop state depends on:

```text
species growth requirements
season / temperature
moisture / irrigation
soil N/P/K
organic matter
crop-disease pressure
rotation history
```

Agriculture feeds player survival and settlement economy through the same item/stock model.

---

# NPC AI and social state

NPC AI uses utility scoring + hierarchical tasks.

```text
needs / personality / danger / duty
              ↓
          goal score
              ↓
      selected current goal
              ↓
 typed task queue / path / action
```

Relationships are multidimensional (affection/trust/fear/respect/etc.), not one universal friendliness score.

Memories refer to meaningful events and can feed relationships/history. Families and property connect NPC identity to the settlement economy.

---

# Economy

The settlement ledger is physical/causal:

```text
labor reservation
      ↓
production process
      ↓ consumes inputs
      ↓ creates goods
stock level versus target
      ↓
price
      ↓
trade opportunity
```

Disease, hunger and war can reduce the usable labor pool.

Market price histories are bounded daily samples so the UI can render trends without unbounded save growth.

---

# Routing, caravans and migration

Long-distance movement uses:

```text
macro-region route
    ↓
chunk corridor
    ↓
local tile path
```

Trade routes are sparse and bounded per origin rather than every settlement connecting to every other settlement.

Caravans carry cargo, value, guards and pathogen load. Arrival transfers actual goods/currency and may seed infection.

Migration cohorts transfer aggregate population plus selected named representatives. War/famine/housing pressure can create them.

---

# Epidemiology

Epidemiology owns human pathogen state.

## Definitions

A `DiseaseDef` contains transmission modes, incubation/illness duration, contagiousness, severity, mortality, immunity and season/symptoms.

## Aggregate outbreak

`DiseaseState` belongs to a settlement and tracks cases/recovered/deaths/immunity/strain/policy/trend.

Aggregate transmission considers:

```text
susceptible population
case prevalence
crowding/homelessness
sanitation
quarantine
transmission channel
season
healer/medicine capacity
```

## Named infection

`InfectionState` belongs to an NPC or player and progresses:

```text
exposed → incubating → symptomatic → recovered / fatal
```

Treatment can reduce severity/risk but is not a guaranteed cure.

## Logistics

Traveling caravans and migrants can carry pathogen loads. Quarantine reduces transmission opportunity but also trade capacity and costs municipal resources.

Disease therefore has economic consequences through labor absence, medical consumption, quarantine, transport and mortality.

## Compaction

Resolved individual infection records are removed after a retention period when no longer referenced. Durable consequences remain in host immunity/history/outbreak aggregates.

---

# Property and settlements

Properties connect physical structures to ownership/occupancy, rent/value/condition and settlement housing capacity.

Settlement state owns aggregate population, goods, labor, policy and public resources—not every distant anonymous citizen.

Large stable settlements may found new realized-region settlements; collapse can leave ruins/history. This lifecycle is bounded by realized-region rules.

---

# Factions, government and law

Governance owns offices/succession/claims. Faction simulation owns diplomacy/war. Economy owns material stocks. Combat owns physical wounds.

This prevents circular "god object" behavior.

War consumes manpower and supplies, can damage settlements and routes, and can create migration pressure.

Claims provide durable political reasons that can influence relations.

Law/crime responds to social/economic conditions; it does not simply roll random flavor events independent of scarcity/security.

---

# Knowledge and language

Knowledge is represented as facts held by people/settlements/player.

Discovery checks prerequisites. Scholars/schools bias research focus. Books are physical persistent records with author/language/facts and ownership.

Libraries own book IDs and copying consumes parchment.

Language fluency gates comprehension, creating a path from exploration → manuscript → study → knowledge instead of instant global unlocking.

---

# Religion and magic

Religious institutions own priest/follower/influence state. Migration/conversion can alter local belief and pressure may generate schisms.

Magic is seed-specific. `MagicLaw` constrains source/form/catalyst/time/terrain/instability/contamination. Experimentation yields discovered spell records. Rituals combine social/religious/material requirements.

Magic effects mutate authoritative systems (fire, water, crops, wounds, contamination). Major acts can become historical events, then myths interpreted by cultures.

---

# History / archival maintenance

History receives events; it does not directly run the systems that caused them.

High-salience events remain first-class records. Old low-salience events compact into archive buckets keyed by year/type with count/sample metadata.

Transient logistics records are pruned once their consequences are durable elsewhere.

This distinction is required for century-scale worlds.

---

# Persistence and recovery

SQLite is canonical persistent storage.

Current schema = 3.

Checkpoint principles:

- transactional save;
- engine/save/worldgen versions stored separately;
- stable JSON serialization with sorted keys for canonical hashing;
- no pickle;
- rotating SQLite backup;
- cross-record semantic verifier;
- migration rather than silent overwrite.

Schema changes must preserve old public fixtures or explicitly introduce tested migrations.

---

# UI/read-model contract

Complex systems must be inspectable.

The World Console and World Ledger expose:

- current causal alerts;
- player anatomy/infection/equipment;
- settlement economy and health;
- routes and logistics;
- ecology and LOD;
- people/families;
- institutions/knowledge;
- artifacts/provenance;
- sites/graves/history;
- magic/contamination;
- engine diagnostics.

Screens are pure read models. A UI test should compare `state.to_dict()` before/after rendering for new complex views.

---

# Example multi-system chains

## Epidemic logistics spiral

```text
crowding + poor sanitation
    ↓
outbreak
    ↓
workers become symptomatic
    ↓
productive labor shrinks
    ↓
food / metal output falls
    ↓
prices rise
    ↓
quarantine imposed
    ↓
trade capacity falls
    ↓
shortage worsens
    ↓
migration pressure
    ↓
infected migrants may export pathogen
```

## War / famine / refugees

```text
political claim
    ↓
relations deteriorate
    ↓
war
    ↓
army consumes manpower + supplies
    ↓
route danger rises / caravans lost
    ↓
food imports fail
    ↓
food stress + crime + population loss
    ↓
refugee cohort
    ↓
destination housing pressure
```

## Predator legend

```text
prey decline
    ↓
predator pressure
    ↓
local individual materializes
    ↓
attacks player
    ↓
kills player
    ↓
becomes persistent named monster
    ↓
bounty/history survive successor
```

## Scholarship / craft

```text
school focus + prerequisite knowledge
    ↓
discovery
    ↓
author writes book
    ↓
library / market ownership
    ↓
book crosses cultural border
    ↓
reader learns language/fact
    ↓
new craft process becomes usable
```

# RC7 Early-Game Integration

RC7 adds an early-game production layer without bypassing the existing authoritative simulation. New state includes carcasses, timed processing jobs, prepared meals, nutrition history and food effects. These records are persisted through `LivingWorldState` and advanced by simulation time.

## Causal chains

### Primitive technology
natural resource -> hand process -> tool quality -> new harvest/process capability -> better station -> improved efficiency/yield

### Hunting
habitat/cohort -> local animal -> combat damage -> carcass quality -> field processing -> meat/hide/bone/fat/sinew/offal -> cooking/preservation/craft/trade

### Food
forage/hunt/farm -> ingredient -> cooking method + station -> prepared meal -> hunger/macros/diet groups -> short food effects -> recovery/stamina/exposure

### Farming
wild/farm seed -> tilling tool -> soil N/P/K + water + climate + disease -> crop -> food/fiber/seed -> cooking/craft -> soil depletion/rotation

### Furniture
materials -> construction -> environmental/work/processing/storage effect -> survival or production efficiency

## Ownership boundaries

- `ResourceSystem` owns deterministic natural features and depletion/regrowth.
- `ProcessingSystem` owns carcass actions and timed preservation jobs.
- `CookingSystem` composes meals.
- `NutritionSystem` owns diet history and food effects.
- `FarmingSystem` owns crop growth and soil demand.
- `BuildingSystem` exposes station/environmental bonuses but does not perform crafting itself.
- `Simulation` validates commands, advances time and composes these systems.

## RC8 presentation adapter

Graphics are downstream of simulation. `worldseed/presentation/visuals.py` resolves stable content IDs into visual paths. `worldseed/ui/pygame_terminal.py` may inspect already-realized local state for presentation, but it must not advance time, roll simulation RNG, realize distant regions, create entities or alter saves. See `VISUAL_ARCHITECTURE.md`.


## Seeded world preparation (RC13)

New worlds pre-generate and persist a bounded opening envelope before the simulation begins. The database stores deterministic base terrain chunks keyed by generator version and deterministic natural-resource chunks keyed by resource-generator version plus season. Runtime tile deltas, depletion, crops, structures and other authored state remain separate overlays. If a prepared terrain ID no longer resolves because content changed, the engine safely falls back to deterministic regeneration.

## Dev31 exploration presentation/performance contract

Ordinary movement advances **1 game minute**. Other actions retain authored durations; simulation time remains command-owned rather than tied to render frames.

Surface visibility has two layers: persistent **discovery memory** and transient **current visibility**. Current visibility is a circular, line-of-sight-limited radius derived from Perception, Survival, talents, weather visibility/fog, and ambient light. Previously discovered but currently unseen terrain may be shown dimly, but entities/resources must not be rendered outside current visibility.

The terrain atlas reads only actually discovered cells. Discovery of one cell never promotes a whole 512-cell region. Atlas reads use the same versioned surface-cache contract as local terrain, remain generation-free, and use a runtime per-chunk discovery index so panning cost is bounded by the requested view. Atlas LOD is categorical rather than raw RGB averaging so thin rivers do not acquire thick floodplain/riverbank halos.

Cloud shadows are presentation-only world-space fields. Their absolute positions derive from seed/world coordinates and their drift from weather wind plus visual elapsed time, so moving the camera cannot drag clouds with the player. Visual elapsed time never advances simulation weather or the game clock.

Local pygame entity lookup is spatially bucketed; a frame must not scan every realized NPC/creature/structure in the explored world. Routine autosaves persist authoritative state without making a full rotating SQLite backup; explicit manual/menu/quit saves retain rotating backups.

## WORLDGEN v8 Phase 5 coastal morphology

`worldseed/world/coast_v8.py` is the Phase-5 read authority over v8 coastal shape. It consumes the existing geological elevation/topography, physical climate and prepared hydrology; it does not generate a second coastline, mutate terrain, or render effects. Current fields include continental-geometry shelf depth, open-sea exposure, shelter, bay/headland tendency, coast class, shore-material tendency, tidal-flat/marsh/lagoon potential, sediment proxy, estuary strength and delta potential.

Dev33 introduces the first save-visible materialization contract. New v8 worlds record `coast_morphology_version = 1`; existing v8 saves missing the field infer version 0 and retain their previous shoreline. Surface cache identity is now `worldgen + hydrology + hydrology morphology + coast morphology`. Coast v1 can materialize `core:shore`, `core:coastal_gravel`, `core:rocky_shore`, `core:coastal_cliff`, `core:tidal_flat`, `core:salt_marsh`, and the existing ocean depth family. River-mouth fields are allowed to remain zero when hydrology is unprepared; inspection must never solve missing drainage merely to populate a coast read.

For generation performance, detailed coast geometry is reused on an absolute 8-cell materialization lattice while exact geological elevation still decides land/ocean for every tile. This is a bounded projection optimization, not a second coastline authority.
