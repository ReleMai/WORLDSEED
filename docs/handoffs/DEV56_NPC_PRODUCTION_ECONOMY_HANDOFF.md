# Dev56 - autonomous production, home storage and paid trade

## Scope and causes

Exact workers previously deposited output at workplaces, while market shipments
were generated only by aggregate production. Removing exact labor from the
aggregate batch consequently stranded its goods. Crafters also collected inputs
from arbitrary settlement containers without paying, including other households.

Named miners, farmers, lumberjacks and supported workshop professions now use
their assigned home's real storage, with existing workplace storage as fallback
when no usable home storage is materialized. Workers retain household food/fuel,
replanting seeds and a process-input reserve, collect surplus into their carried
inventory, walk to the market, and receive payment from settlement wealth.
Crafters collect their own home/work inputs or physically buy missing supplies
from settlement market stock. Production still consumes inputs at the existing
reserved activity, then carries the resulting batch home. These exact workers
continue to replace their aggregate labor share rather than duplicating it.

Indoor cargo walks use the actual exterior portal, floor stairs and furniture
approach. Entering a home preserves cargo tasks. Nearby household purchases now
move reserved market stock into NPC inventory on pickup and into home storage
on arrival; overdue delivery cannot teleport an active carrier's goods home.
Households, individual meals and aggregate consumption recognize bread, cooked
meat and smoked fish. Existing profile activity labels describe trade and hauling.

## Modules and public contracts

- `npc_home_storage.NPCStorageAccess`: owned storage selection, transfer tasks,
  reachable outdoor use cells and exact indoor reach checks.
- `npc_commerce.NPCCommerceSystem`: non-mutating input/surplus plans,
  `after_deposit`, physical cash purchases/sales and unsold-cargo returns.
- `professions`, `mining_profession`, `ai`, `interiors`, `sim.engine`: integrate
  those plans with existing fixed ticks, activity reservations and material goods.
- `household_economy`, `economy`: physical local household cargo and food demand.
- `physical_goods`: retain at most 1,000 transfer audits, pruning to 800 when
  crossed. The audit never owns goods; removing old rows cannot delete cargo.
- `ui.npc_activity`: observational labels; no new global controls or routes.

Cash and goods transfer at execution, never while merely planning a job.
Insufficient funds or a changed market abandons the dependent craft plan with
already collected cargo intact. Equipped units are excluded from surplus sales.
Neighbouring private stores are not free sources. A full store retains cargo.

## Persistence, determinism and LOD

Schema remains 3; all geography contracts are unchanged. New tasks use existing
serialized task dictionaries. `HouseholdDeliveryState.physical_cargo` is an
additive boolean defaulting to false for old saves/deliveries. For a new physical
delivery, `assigned` quantity owns reserved market stock; `carried` quantity is
an obligation referencing NPC inventory. It is not a second copy of the goods.
The save verifier checks carried household obligations against actor inventory.

No new RNG namespace. Storage and surplus ordering use stable IDs. Active local
workers execute on simulation ticks, including bounded Tier-B work trips;
distant/offline household deliveries retain coarse completion. No rendering,
hover or ordinary player-movement code generates regional plans. No new global
per-frame scan or persistent shipment collection is introduced.

## Validation

- `compileall -q worldseed tools tests`: passed.
- Bounded `dev56-targeted`: 115 tests passed across new production/economy tests,
  exact professions/miners/activities, workshop expansion, interiors, household
  and workplace logistics, transactions, NPC routines/gear/UI, combat and territory.
- Autonomous fixed-tick tree -> worker inventory -> home -> market sale ->
  carpenter purchase -> bench -> home -> bowl sale, with cash/goods conservation.
- Generated smithy -> indoor production -> assigned home -> market sale;
  separate continuous home-entry/storage test verifies physical arrival.
- Local household pickup/carry/dropoff/consumption; no overdue local teleport;
  insufficient cash, private storage, capacity/reserves, audit bounds, old defaults,
  task round trips and representative `tools/verify_save.py`: passed.
- Bounded one-seed, one-year full-policy smoke soak: 120 game days, no invariant
  errors. This is a coarse offline check, not a live graphical playtest.
- Prior Dev55 CI's territory guard assertion now respects its 60-minute activity
  deadline and explicitly tests that an hourly decision cannot bypass it.
- Automatic fast gate includes the new production tests on publication. Full
  release validation and a live playtest remain outstanding.

## Known limitations and next dependency

Trades use the existing cash market as intermediary; direct NPC-to-NPC barter
negotiation is not added. Distant economy and older shipment records remain
aggregate/coarse. Existing property bindings, prepared home storage, access and
funding still constrain work: shortages produce waiting rather than invented
goods or cash. Workshop recipes and balance are existing content; this work
connects their material flow rather than adding new professions or item assets.
Next dependency is longer live-village observation and economy balancing across
scarce-input/cash scenarios, followed by deliberate release hardening.

The original dirty D:\Codex Project\wsLIVING checkout was preserved. This work
uses the attached living-village-combat managed checkout based on main 9c66ae9.
