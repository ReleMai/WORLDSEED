# WORLDSEED RC14 Dev5 Handoff

Status: **development checkpoint — responsive movement + regional block architecture + Phase 5 settlement-siting foundation**. This is not the final RC14 release.

## Why this checkpoint exists

Dev4 completed deterministic environmental read models. Dev5 uses those fields to begin the next architecture layer while also fixing the held-movement latency/overshoot reported during normal play.

The governing contract remains:

**simulation state -> regional plan -> local materialization**

Regional blocks are generated planning data. They do not own a second population, economy, inventory, NPC list, or mutable settlement reality.

## 1. Held movement / latency fix

`worldseed/ui/pygame_terminal.py` no longer relies on pygame/SDL key repeat for gameplay movement.

- pygame key repeat is disabled;
- `KEYDOWN` and `KEYUP` are both tracked;
- held movement uses an explicit active-key state;
- initial delay: 165 ms;
- repeat interval: 72 ms;
- duplicate OS-generated `KEYDOWN` events for an already-held movement key are ignored;
- a slow frame never generates catch-up movement for intervals that were missed;
- release events clear the held direction before another synthetic repeat can be emitted;
- pending-input cleanup clears held state plus queued key-down/key-up events.

This prevents the former failure mode where many repeated movement events accumulated while rendering and were replayed after the player released the key.

### Renderer work paired with the input fix

The local pygame renderer now keeps a scrollable base-layer state. A normal one-tile camera move can shift the previous terrain surface and redraw only the newly exposed strip plus newly discovered cells instead of rebuilding the entire viewport.

Natural-resource presentation is also cached by **absolute world cell + resource revision/day state**, so moving the camera one cell reuses almost every resource projection rather than rebuilding a viewport-keyed result.

## 2. Regional world-block architecture

New module: `worldseed/world/region_blocks.py`

A strategic region is exactly:

`REGION_SIZE = CHUNK_SIZE * REGION_CHUNKS = 32 * 16 = 512 world cells`

`RegionBlockPlan` is reconstructable generated data containing:

- stable region UID / x / y / plan version;
- dominant biome and sampled biome mix;
- mean elevation, moisture, temperature and relief;
- settlement presence under the existing settlement-presence RNG contract;
- a deterministic settlement anchor, suitability score and archetype;
- coarse control potential (`settled`, `bandit_frontier`, `wild`);
- small wilderness-character tags;
- latent historical/site potential;
- symmetric regional road/trail exits;
- water exits read only from already-prepared authoritative RC14 hydrology;
- canonical fingerprint.

Plans are cached through the existing generated-regional-plan persistence table. They are safe to rebuild from seed/version. They do not replace authoritative state or physical-plan deltas.

## 3. Settlement siting

For settlement-bearing regions, Dev5 no longer chooses an unrelated random x/y anchor when a regional planner is active.

The planner samples a deterministic 6×6 candidate lattice with deterministic jitter and scores candidates from the approved RC14 environmental fields when available:

- soil fertility;
- farmland potential;
- freshwater opportunity;
- timber opportunity;
- stone opportunity;
- slope;
- flood risk;
- broad temperature suitability.

It selects an archetype from the same conditions (`river_market`, `agrarian`, `mining`, `forest`, `fishing`, `frontier`). Candidate evaluation is bounded instead of scanning every one of the 262,144 cells in a region.

Settlement anchors keep at least **64 cells of margin** from every regional boundary. A village/town block therefore remains mostly wilderness/farms/forest/other surrounding terrain instead of becoming a fully urban tile.

Important compatibility detail: Dev5 uses the exact same `derive_seed(..., "settlement-presence", rx, ry)` presence roll as `ProceduralSocietyGenerator`. A regression test verifies that the regional plan and the society generator agree on both settlement presence and anchor.

## 4. Roads and water on the strategic map

### Roads / trails

Regional road exits use a canonical unordered pair of adjacent region coordinates. Both neighboring blocks therefore derive:

- the same connection existence;
- the same edge offset;
- the same road class.

Road probability is higher when one or both endpoints contain settlements. This creates a sparse connected-looking strategic substrate without an all-to-all graph.

This is **not yet the final RC14 route system**. The next route phase must convert selected strategic connections into persistent terrain-aware corridors, crossings and route IDs using the existing hydrology/cost architecture.

### Rivers / waterways

The block planner never invents decorative river data. It only records water exits found in **prepared authoritative hydrology**. If hydrology for an area is not prepared, the strategic plan leaves the water exit unknown instead of generating an alternate river reality.

## 5. Directional region entry

WORLDSEED keeps continuous absolute local coordinates, so no teleport is needed at a block boundary.

`entry_side(old_x, old_y, new_x, new_y)` makes the contract explicit:

- move south -> enter destination from **north**;
- move north -> enter from **south**;
- move east -> enter from **west**;
- move west -> enter from **east**.

The movement log reports the destination region and entry side on a surface-region boundary crossing. Because the player position remains continuous, their exact boundary offset is naturally preserved.

## 6. Graphical region map

`M` on the pygame client opens `present_region_map()`.

The map intentionally remains quiet:

- unknown regions stay opaque;
- discovered regions show broad biome color and subtle relief only;
- prepared rivers/waterways are blue;
- roads/trails are gold;
- only known settlements are marked;
- hidden site/bandit/wildlife potential is not exposed;
- the current player region is highlighted;
- current-region details are limited to broad terrain character and already-known settlement information.

Road and water lines use their stable 0..511 edge offsets so adjacent region lines meet at the same boundary point instead of every line terminating at edge center.

## 7. Simulation integration

`Simulation` creates one `RegionBlockPlanner` and passes it to `ProceduralSocietyGenerator`.

On coarse nearby-world realization, regional plans are prepared before settlement society state is realized. Existing settlement/economy/NPC systems remain authoritative.

Normal movement within the same 512×512 region does not rerun nearby settlement/region realization. The existing region-boundary coarse-refresh rule remains in place.

## 8. Validation completed for Dev5

Compilation:

- `python -m compileall -q worldseed tools tests` — PASS

Focused regression set after the Dev5 changes:

- RC10 worldgen/input source contracts
- RC12 renderer contracts
- RC13 pregeneration
- RC14 environmental fields
- RC14 hydrology
- RC14 regional blocks
- RC14 world presentation
- living-world determinism/state
- persistence

Final focused result after all Dev5 changes: **49 tests passed in 22.04 s**, including the society/planner settlement-presence + anchor agreement test.

The pygame behavioral suite is present but is skipped on the build machine because pygame-ce is not installed there. The source compiles and the architecture-level input tests remain intact.

A complete repository-wide suite was attempted earlier in this work session but exceeded the 420-second execution window. The one source-contract failure observed before timeout was fixed and its test now passes. Dev5 therefore records the focused green gates above instead of claiming a full-suite pass.

## 9. Next work unit

Keep the next chat/work unit bounded. Recommended Dev6 scope:

1. replace probabilistic adjacency-road edges with the full sparse settlement route graph (candidate graph + connectivity backbone + limited redundant edges);
2. rasterize selected edges into terrain-aware persistent route corridors;
3. derive stable ford/bridge candidates from authoritative hydrology;
4. render those exact route corridors locally and on the region map;
5. begin the settlement skeleton: access road -> common -> functional seeds -> parcels -> footprints;
6. add plan/ledger consistency audits before advancing to settlement life.

Do not begin RC17 schedules/NPC life until the RC14 physical settlement plan exists.
