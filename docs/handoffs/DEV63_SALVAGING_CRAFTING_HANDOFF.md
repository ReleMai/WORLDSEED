# RC14 Dev63 — Salvaging and profession crafting

Baseline: canonical `ReleMai/WORLDSEED` main at
`56588659c57255c1bfb52f3cdd6621408ce81849`. Engine/package:
`1.0.0-rc14-dev63` / `1.0.0rc14.dev63`.

## Content and player paths

The expansion adds 489 distinct items with individual transparent 64px PNGs:
252 salvageable miscellaneous finds, 19 recovery components, and 218 crafted
outputs. There are 180 village objects, 48 habitat-specific plants and wild
finds, and 24 animal parts recovered through existing carcass processing.
The complete catalog contains 643 items and 324 recipes, including 242 new
learnable recipes across all 19 crafting professions, with at least twelve per
profession. `crafting_expansion.json` records source, habitat, rarity, profession
and tier; `salvage.json` records actual component yields and disassembly methods.

Shared parts include wood pieces, metal scraps, nuts and bolts, handles, plant
scraps, cloth, leather, bone, ceramic and glass fragments, copper wire, resin and
mineral grit. Six rarer parts are intact springs, gears, clear optical fragments,
aromatic oil, tough fiber and decorative silver filament. Rare flora also appear
directly in crafting recipes. Crafted outputs provide tools, fishing equipment,
weapons, armor, food, treatment supplies and intermediate parts with downstream
recipes; catalysts remain carried rather than being consumed. New food statistics
derive conservatively from ingredient energy and supported food groups.

Open **Enter → Work → Craft → Salvaging**, or the graphical crafting Salvaging
tab. Inspect a carried object to preview common yields, tools and base rare odds.
Starting consumes one object and reserves its deterministic attempt. Inspection
and three material-aware decisions finish the work: preparation, disassembly and
recovery. Good decisions, spare tools and Salvaging skill improve recovery;
mistakes retain useful common parts and give practice. Escape preserves the
project, including across saves, and restores the parent selection and page.
Recipe learning continues through the existing physical 1–5 item experiment grid.

**Enter → Work → Collect clean water** draws one unit from an adjacent live well
with a bowl, pot or waterskin, or boils freshwater with a carried cooking pot and
a nearby fire station. Salt and brackish sources are rejected. Crafted lures are
selectable reusable bait; their quality contributes to fish attraction. The two
original well families share the existing semantic well tag.

## Authority, economy and world loot

`SalvagingSystem` owns the player project and exposes observational `preview`,
`available_items`, `session_view`, `can_start`, `skill_threshold` and shared
deterministic `roll_outputs` APIs. `StartSalvageCommand` and `SalvageActionCommand`
are the authoritative mutation paths. Rendering, search, hover and browsing
consume no RNG, time, inventory or discovery state. `CollectWaterCommand` owns
the new water acquisition action. Invalid crafting work commands commit no turn.

The NPC catalog has 280 processes, including 242 expansion recipes mirrored
exactly from player costs and outputs, ten crop field processes, source-backed
water gathering and primitive stone-flake production. Named workers withdraw,
buy, carry and deposit real goods through the existing property/storage and
ledger authorities. They can salvage carried or owned finds for missing parts.
Materialized work uses real fixtures, tools, catalysts and activity duration.
Recipe knowledge is honored. Named production replaces its aggregate labor slot;
persisted activity-reservation completion metadata prevents copied tasks or
reloads from creating another batch or reusing rare salvage rolls.

Anonymous labor excludes crafts without available inputs, tools or catalysts.
Jobs supplied only by a named worker are capped and bound to the eligible workers.
One town/property inventory index per reservation pass avoids a separate global
inventory scan for each recipe. Existing terrain-suited starting farm seed capital
provides the crop bootstrap, preserving its total quantity. Foods enter household
and settlement hunger baskets; crafted durable goods have bounded replacement
demand, while components are consumed by downstream production and trade.

Village refuse has a bounded, once-only initial origin batch, up to 64 prepared
structures with eight units each. Real containers and ground piles debit this
same stock through physical-goods transfers. All storage profile families,
natural caches and dungeons have contextual miscellaneous loot. A new tabletop
profile is allocated before interior preparation and binds reachable existing
furniture. Exposed table/desk goods render their own item sprites from real
inventory; closed containers retain their existing presentation.

Wild loose finds use habitat filtering and bounded local deterministic sampling.
Natural cache and ground collection markers survive reload, cleanup and repeated
materialization, preventing replenishment through reopening or destruction.
Forty-eight renewable flora use terrain, climate, moisture, season and rarity
rules. Animal additions are carcass outputs, so killing does not duplicate
butchery rewards. Existing geography and ground terrain remain authoritative.

## Persistence and deterministic selection

Save schema remains 3 and world generation remains 8. New resource generation
is version 5; saved version 4 and earlier exclude the added flora and preserve
their exact placement fingerprints. Additive player fields are
`player_salvaging_xp`, `salvaging_attempts`, `player_salvage_session` and
`player_salvage_log`, with missing legacy fields defaulting safely and Salvaging
skill defaulting to zero. Serialization detaches mutable project/log objects.
The verifier checks progress, choices, reserved attempts, skill/XP limits, bounded
logs and duplicate completion. Result history retains at most 80 entries.

Salvage RNG domains are `salvaging.challenges.v1`, `salvaging.common.v1`,
`salvaging.common_fraction.v1`, `salvaging.rare.v1` and
`salvaging.rare_amount.v1`. Loot uses independent origin, storage, village-ground,
wild-ground, natural-container and dungeon domains. NPC rolls use their reserved
activity identity. There is no shared mutable presentation RNG.

## Validation and authoring

Authoring tools are `tools/build_salvage_content.py`,
`tools/build_crafting_economy.py` (`--check` verifies recipe/process parity), and
`tools/draw_salvage_sprites.py`. Checked-in JSON and individual PNGs are runtime
content; the generators are development tools. A full item gallery and three
salvaging UI captures are in `artifacts/dev63-*.png`.

Targeted development validation covers all six material methods, exact action
duration, invalid commands, skill and rare odds, every-stage save/reload, real
recipe discovery, all profession coverage, acquisition and downstream sinks,
physical input/catalyst conservation, copied-task replay, labor starvation,
live wells, lures, container and ground origin conservation, habitat filtering,
animal processing, old resource fingerprints, table art and narrow UI geometry.

The focused crafting/salvaging/loot/storage/navigation batch passed 84 tests in
75.1 seconds. Economy, profession, workshop, miner, household and logistics checks
passed 63 tests. Three-seed empty-inventory bootstrap and resource-balance checks
passed. The bounded one-seed, one-year full-policy smoke passed in 41.6 seconds
with zero invariant errors (120 simulated days, 604 boundaries; 0.54 MB serialized
state). Representative actual-catalog SQLite checkpoints passed the command-line
save verifier both mid-project and after salvage, physical recipe discovery and
rivet crafting. Content and image audits pass; every new sprite has unique decoded
RGBA pixels. The final feature gate passed all 65 tests in 1.5 seconds; the
final economy integration batch passed all 63 tests in 7.1 seconds, and final
item/fish/container/tabletop art checks passed all 13 tests. Compilation,
recipe/process synchronization, content and visual audits, and diff validation
passed after the final catalog changes. The gallery and UI captures were
visually inspected.

This is targeted development validation. The comprehensive manual release suite
and multi-year matrices have not run. New foods use existing eating and nutrition
behavior; stack-level aging remains the existing engine limitation and is not
claimed as a new preservation simulation. Future content can extend the JSON
catalogs without another inventory, economy or terrain authority.
