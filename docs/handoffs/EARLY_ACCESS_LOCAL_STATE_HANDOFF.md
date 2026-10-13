# Early access local state handoff

Implemented the NPC and discovery portion of work unit 4 in
`EARLY_ACCESS_PYGAME_PLAN.md`. This is a coherent development unit; remaining
stationary/creature index work is listed below.

## Scope and runtime contracts

`NPCSystem` owns transient 16-cell actor buckets, level counts and insertion
ordinals. New read APIs are `indexed_npcs_in_rect`, `tick_managed_npcs` and
`continuous_movement_npcs`. Fixed ticks and graphical interpolation query these
bounded buckets instead of enumerating every named actor. Existing Tier A and
explicit mining/profession/commerce Tier B classification remains authoritative,
including adjacent cave levels. Taskless local actors still receive decisions.
Actor insertion order preserves contested collision outcomes; the existing
UID-sorted `nearby_npcs` API is unchanged. Distant route progress stays on its
coarse cadence rather than retaining an interpolated route forever.

Execution, tile/bucket crossings, connector changes, births, migration, deaths,
interior portals and settlement housing binding refresh actor membership. The
family, migration, disease and settlement population systems have optional
`npc_index` callbacks wired by Simulation. Direct actor mutations in a prepared
standalone controller must register through `_index_npc` or rebuild once at a
preparation boundary. The production activation/load paths still rebuild.

Pygame NPC drawing now queries the simulation locator and preserves the old
viewport-adjacent bucket extent/order. It cannot repair indexes or scan the
population. Reference fixtures explicitly register their actors before timing;
the standalone economy fixture does the same without changing its assertions.

`DiscoveryTiles` stores exact 32×32 chunk masks and compact surface indexes.
`DiscoverySet` supplies membership/set operations; explicit list iteration or
`export_legacy` expands tokens without a cap. Additions touch only affected
chunks and never sort/scan lifetime memory. A transient FIFO membership cache
holds at most 8,192 answers for repeated viewport reads; additions, removal and
clear invalidate the corresponding answers. Atlas terrain and cave-marker
queries enumerate only view chunks. Current sight remains separate from memory.

## Persistence and compatibility

Schema remains 3 with additive optional fields `discovered_format_version=1`
and `discovered_chunks`. Chunk keys are canonical `cx,cy,z`; masks are nonzero
hex strings of at most 256 digits, with bit `ly*32+lx` representing a cell.
Canonical checkpoints write an empty legacy `discovered_tiles` list. Missing
compact fields import the legacy list; mixed fields union both memories.
Malformed masks/keys and unknown versions fail load and verifier checks rather
than silently forgetting cells. Persistent discovery no longer drops cells at
120,000. RNG namespaces, geography and generation contract versions are unchanged.

Legacy saves load into the updated engine. Compact checkpoints require this
engine or newer; older binaries do not understand the new memory field.
`DiscoveryTiles.export_legacy(sorted_tokens=True)` provides an uncapped explicit
cell list for compatibility tooling. SQLite still saves one atomic simulation
checkpoint: per-chunk SQL dirty-row persistence and whole-state capture costs
remain follow-up work. Failed-save snapshot/retry guarantees are unchanged.

## Validation and measured behavior

The final bounded integration run passed 135 tests, including local query and
collision/LOD behavior, NPC lifecycle transitions, production/economy cadence,
legacy/current saves and failed-save retry, exact negative/z coordinates,
140,000-cell database round trip, set algebra, snapshot isolation, read-only
atlas and real rendering. The fixture registration adjustment was additionally
checked with 17 reference/render regressions. All six final reference PNG hashes
match the previous baseline and authoritative state is unchanged. Compileall
and diff checks pass.
`tools/verify_save.py` passed on a compact 140,090-cell checkpoint.

[Recorded measurements](../development/LOCAL_STATE_BASELINE.json) name source
revision, dirty worktree, hardware/driver and sample counts. Sequential runs use
the same synthetic large-save scene, Linux/AMD EPYC 9V74 (3 logical CPUs), Python
3.12.14, pygame-ce 2.5.8, SDL dummy, 1280×720, zoom 28, ten warmup and 80 measured
frames. Median real idle free-movement update: **0.185 ms / 0.237 ms** with
1,000 / 10,000 distant NPCs. The earlier same-machine 10,000-NPC baseline was
4.501 ms. Assertions forbid any population enumeration during local updates.
The medians differ by roughly 28 percent in this short sample, so the plan's
proposed 20 percent scaling target is not yet an achieved claim. This is
unpaced synthetic throughput, not live FPS or full input latency.

A separate sequential discovery probe builds 400-wide prepared memory containing
140,000 / 1,400,000 cells, warms ten one-cell additions, then measures 80 real
`_record_discovered_tiles` calls adding one cell each. Median addition cost was
0.0022 / 0.0021 ms. JSON masks were 39,306 / 384,383 bytes, versus
1,738,650 / 18,772,230 bytes for equivalent expanded lists (including the 90
probe additions). No history cap or old-cell loss occurs. These are small
controlled update samples, not a save-total benchmark.

Reproduce actor measurements using the runtime profiling guide's population
probe commands with `--frames 80 --warmup 10`; run sequentially. The discovery
probe shape/counts and warmup are above; the regression suite validates exact
persistence and no-history-iteration complexity without timing thresholds.

## UI and next dependency

No new controls or gameplay verbs. Existing map memory remains cell-exact and
NPC presentation updates immediately across actor bucket transitions.

Next: move the other presentation collections into maintained stationary and
creature indexes. Fractional motion still invalidates that older cache, and
count/hour invalidation cannot reliably handle same-count container relocation
or tactical creature movement. Also measure broad hourly/social planning and
whole-state save capture before introducing dirty discovery SQL rows or async
saving. These remaining items mean work unit 4 is partly completed; shared panel
style and recovery work should follow its remaining index/persistence work.
