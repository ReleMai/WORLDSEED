# Settlement and interior redesign

Requested September 30, 2026. Baseline: main `eed4a381` (Dev43).
This is the implementation order and acceptance contract for the complete request.
Dev44 implements stage 1. Dev45 implements the farm-compound and planting core
of stage 2; larger non-farm plots, terrain earthworks, explicit migration and
stages 3-6 remain pending in full. Dev46 implements the household/lodging slice
of stage 3 with fixed-point free movement, freely positioned furniture,
connected rooms, shared resident portals/routines and persistence. Workshop
Dev47 replaces generated building exteriors with solid stable-ID shells and
separate doors, introduces function-specific continuous layouts, same-space
intrusion witnesses, and shared indoor work reservations. Existing saved v1
interiors preserve their geometry and player furniture arrangements. See the
Dev47 handoff for validation and remaining boundaries.

## Findings and research

- Positions currently contain only x/y/z (`core/coords.py`). Rooms are exterior
  world footprints, and doors, crops, containers and AI tasks also assume that
  identity. An interior cannot safely be implemented by assigning a cave depth
  or teleporting into an arbitrary remote patch of the surface.
- `settlement_planner.py::_plan_open_worksite` puts soil/fences/shed in one field
  parcel. `_generate_buildings` also places a barn in the first field parcel.
  This explains overlapping agricultural and building responsibilities.
- The conversation renderer measured wrapping with small_font and drew with
  font, and abbreviated all relationship metrics into one line. Correct measured
  wrapping, clipping and independent reply/transcript paging are required.
- AI already separates utility selection, task plans and execution. Fixed
  locomotion ticks run while the real-time driver advances time. A failed local
  path currently returns without clearing its task, so an unreachable destination
  can leave an actor repeatedly trying the same task. Farmers already plant real
  CropPlot objects and consume seeds; missing inputs/access must be diagnosed
  before adding another production system.

Primary research sources:

1. [Godot scene lifecycle](https://docs.godotengine.org/en/stable/tutorials/scripting/change_scenes_manually.html)
   describes the memory, processing and data-integrity tradeoffs of unloading,
   hiding and detaching scenes. WORLDSEED remains Python/pygame; the applicable
   design principle is persistent authoritative state independent of whichever
   local map is being presented. Unobserved interiors use existing LOD rules.
2. [Red Blob A* implementation](https://www.redblobgames.com/pathfinding/a-star/implementation.html)
   treats locations as graph identities and supports directed transitions.
   Apply this to portals between exterior and interior spaces, with actor-aware
   door costs and access. Reuse local A*, rather than creating a second movement
   authority.
3. [Game AI Pro: utility decisions and behavior trees](https://www.gameaipro.com/GameAIPro/GameAIPro_Chapter10_Building_Utility_Decisions_into_Your_Existing_Behavior_Tree.pdf)
   supports relative action suitability. Keep the existing utility/planning/action
   split; improve measurable goals and failure feedback before adding behavior.

## Stage 1: immediate interaction safety (Dev44)

- Add Aggressive Stance to the existing movement command, action menu and HUD.
  Casing, door/container lockpicking and bashing reject other stances before
  changing property state. Leaving the stance cancels casing. Aggressive
  movement receives no crouch concealment or quieter-footfall bonus.
- Case enclosed intact buildings; inspect fields, pens, logging yards, mine
  approaches and monuments directly. A future exterior shell remains caseable
  through the same property identity.
- Wrap dialogue using the actual font, show full Community standing, keep
  Inspect available on every topic, and page both replies and long responses.
- Add nature/resource/town/skill questions. Basic home livelihood is known by
  residents; specific wildlife needs explicit species knowledge. Suspicious
  residents withhold facts until trust rises. Browsing is observational and
  selected disclosures update discovery. Advice does not fabricate skill XP.
- Successor placement starts near the death location on the surface, checks
  dry passability, occupancy, natural obstacles, buildings, locks and fluids,
  then checks known land and bounded sparse potential rings. Never force (0,0).

## Stage 2: generous farm compounds and site preparation

Dev45 completed slice: plan v10 compounds from 18x16 (homestead) to 60x50 (city),
with 40x34 village / 50x42 town fields, chamfered outer edges, up to four adjoining
crop blocks and one internal lane. The farm barn/shed/well court is disjoint from
the growing area; livestock space is reserved before housing. Existing ground
overlays clear vegetation, but ocean/cliff/flood constraints remain. Unbuildable
road-split housing/service lots are rejected before consuming a required slot.
Named farmers use real seeds, ignore healthy crops when more planting is possible,
avoid fences/pens/lanes, share unreserved plots and return seed from harvest.
Initial seed allocation and aggregate field processes respect terrain crop IDs.
No implicit old-world regeneration or earthwork system is implemented.

Use a new pinned settlement-plan version. Preserve existing plans and mutations;
provide an explicit opt-in rebuild/migration for old worlds, not silent rerolls.

- Reserve contiguous farm compounds outside the residential cluster: target
  24x32 cultivated tiles for a small farm and 40x48 or larger for a larger one.
  Actual final size responds to population, worker capacity and terrain context.
  Merge adjacent field parcels into one agricultural boundary, with crop bands,
  gentle stepped edges, foot lanes, and gates connected to authoritative roads.
- A split-rail fence follows the outer compound boundary only. No fence across
  the middle of a cultivated row. A separate service court holds the hut, shed,
  well, storage and wagon space; no house or barn occupies crop cells.
- Make homes/workshops/barracks plots larger and provide clear yards and service
  access. Use bounded parcel reservations and spatial collision checks.
- Permit clearing vegetation and grading suitable ground through stable plan
  preparation deltas. Do not overwrite ocean, protected river/shaft connectors,
  player property or existing historical structures to make a site fit. Larger
  terrain changes require actual earthwork/retaining-wall/crossing objects.
- Farmers get real seeds from stocks/containers through existing transfers,
  plant persistent plots, tend and harvest them. No decorative instant crop
  layer or duplicate yield beside the economic labor reservation.

Acceptance: deterministic/generation-order fingerprints; no field/building
overlap; fence forms outer boundary with accessible gates; every farm has real
seed supply and reachable crop cells; named output conserves ledger stocks.

## Stage 3: persistent spaces and portals

Introduce an explicit spatial identity (surface/cave vs `interior:<structure-id>`)
on actor locations, tasks, reservations, containers, structures, crops, dropped
goods, projectiles, discovery and spatial indexes. Keep cave z-depth distinct.
Default missing fields to world space; assess schema migration with verifier.

- A stable building ID owns an exterior shell plan, persistent InteriorPlan,
  local room graph and portal IDs. Interior dimensions are independent: a 4x4
  exterior can own a 6x6 usable interior plus its shell boundary.
- Right-click a prepared exterior door offers Enter; command validates reach,
  lock/key/invitation and exit landing occupancy. Enter through the linked
  interior portal. NPCs use exactly the same transition and access authority.
- Exits return to a validated prepared exterior landing. Blocked exits wait or
  offer another real exit; never teleport through a wall or duplicate an actor.
- World clock continues in all spaces. Nearby occupants use exact simulation;
  other rooms/buildings use reduced LOD. Loading a view does not advance time.
- Household goods/fixtures move once into their space with the same stable IDs.
  Mining remains connected to the authoritative cave graph rather than a private
  infinite ore instance. Crafting stations, crops and pens retain placement
  support outdoors and in permitted interiors.
- Claimstones stay outdoor capture objects; enterable tower/keep variants may
  link an interior without replacing their supply/capture ownership identity.

Acceptance: 2 houses with identical local coordinates remain isolated; enter,
exit, save/reload and cache rebuild preserve identity; actor/item conservation;
locks/knocking/keys/property crimes work across portal boundaries; UI never
shows outdoor entities from the inside; death drops cargo in its actual space.

## Stage 4: authored exterior architecture

After spaces/portals work, create at least six distinct house assets (timber
cottage, stone cottage, longhouse, thatched roundhouse, courtyard house, two-floor
townhouse), plus workshop, inn, barracks, farm hut, logging hut, mine entrance and
claimstone variants. Use ImageGen for source art, preserve originals and import
deterministic assets into the content catalog.

Each definition has sprite ID, footprint mask, anchor, entrance offset, usable
landing, interior template and material/culture tags. Render the complete shell
once across its multi-tile footprint. Sprite pixels never determine collision;
the plan mask does. Validate centering, doorway alignment and all zoom levels.

## Stage 5: active routines, local learning and relationships

- Add bounded failed-path counters/backoff with cancellation/replanning, clear
  reasons for missing tool/input/station, and observable NPC task diagnostics.
  Release reservations when replanning; prevent repeated impossible attempts.
- Make shift travel, tool pickup, work, meals, social meetings and home returns
  consume real destinations and durations. Utilities get hysteresis so actors
  finish useful work instead of changing their minds each tick.
- Nearby observations record bounded typed knowledge with source/time/confidence
  (animal signs, flora, resources, visited towns). Generate facts on sensing and
  work command paths. Chat reads that knowledge, and misinformation/staleness
  can remain explicit. Never reveal the hidden world through a dialogue screen.
- Social meetings change existing relationships and exchange known facts at
  bounded cadence; teach skills through timed mentoring with demonstrated
  expertise, learner prerequisites and normal XP limits.

Acceptance: stationary player watches actual workers commute, plant, transport,
socialize and return home; obstacles trigger bounded replans; inputs/output and
labor reconciliation conserve quantities; knowledge persists without unbounded
growth; long offline advances remain coarse and bounded.

## Stage 6: military expansion and housing demand

Use existing territory, road/supply, economy and settlement-plan owners.
Unclaimed neighboring claimstones compete against defend/supply priorities.
Orders reserve existing guards and supplies, travel via route/portal graphs,
capture through real presence, and react to ownership/hostility changes.

Housing growth responds to population vs actual bed/lodging capacity. Authoritative
construction orders reserve legal new parcels, builders, timber/stone and time;
completion adds a stable shell/interior/capacity object. Shortages delay building.
Keep distant construction aggregate until materialized, with bounded projects.

Acceptance: no free guards/materials/houses; no simultaneous duplicate orders;
claim control reflects supply and real capture state; plan mutations survive
cache deletion; paths and household bindings update after completed construction.

## Publication boundaries

Publish each coherent, tested stage together with its handoff. Targeted tests
and Fast Gate are development/integration evidence; deliberately run the full
manual release gate once the space migration and major settlement phase are
ready. Live screenshots/worker observation remain separate runtime evidence.
