# WORLDSEED — Resource / NPC / Crafting / UI balance pass
Date: 2026-10-11 (local). Baseline: `51a860c378d053666fe6982088ada1914445cf71`.

## Completed implementation

**Reeds.** Rooted reed beds are more abundant in freshwater-margin terrain.
Resourcegen v5 shallow river tiles get stable world-coordinate clustered patches
without modifying the source hydrology or prepared chunk cache. New/updated
definitions include riverbanks, shallow freshwater beds, faster regrowth and
thatching-friendly output quantities. An optional knife/cutting tool boosts
yield and reduces skill-adjusted harvest duration; barehand collection works.

**Work duration.** Foraging reports the time spent in game minutes. Simple
build actions and cabin blueprint stage advancement now advance different
amounts of in-world time based on the existing crafting skill, strength and
construction material volume. These are deterministic action durations rather
than a real-time interactive progress animation.

**Experimental crafting.** Pot success now consumes clues, discovers a recipe,
and gives one item per distinct recipe output; all physical samples have a
low-quality per-instance artifact record (quality 8-20 versus >=20 normal).
The existing artifact/state serialization persists these prototypes. Production
recipes are unchanged.

**UI.** The inventory details region no longer clips descriptions to two lines.
Wheel scrolling over the details region and clicking its visible scroll track
moves through wrapped description, flavor and other item statistics. Paging
the item grid still uses the wheel outside this region.

**NPCs.** Outdoor pathfinding and continuous traversal consult the existing
spatial index before stepping into a tile with another outdoor NPC. Settlement
binding moves later actors away from legacy duplicate initial coordinates,
preserving NPC identity and cargo. Homes now target reachable cells adjacent
to their actual door when a decorative frontage is too far for portal entry;
interior arrival chooses an unoccupied nearby entrance point instead of
placing every visitor at the same coordinates. Meal schedules prefer actual
home arrival, and occupants seek household chairs near tables and reduce
needs only during a completed meal interval.

**Introduction.** The stranger transcript cache is invalidated as soon as
IntroduceNPCCommand succeeds, so the identified NPC's name and opening speech
refresh without closing and reopening dialogue.

## Testing and limitations

- The new compact regression suite exercises deterministic reed distribution,
  cutter bonus, experimental prototype/save roundtrip, NPC outdoor collision,
  door-distance rebinding, and scroll gestures. A separate chat regression
  asserts introduction details refresh before conversation exit.
- No new wall-clock progress HUD / interruptible work queue was introduced;
  work is still an atomic action whose *game-time* cost varies by skill.
- NPC physical dining is still subject to actual building fixture availability;
  the system does not conjure nonexistent tables, chairs, or food items.
- Full graphical interaction and multiple-real-NPC crowding need desktop
  playtesting on an existing save, beyond automated SDL tests.
- The unrelated Dev62 legacy portrait fingerprint regression is known
  to fail fast gate after the early dedicated tests.

## Next work session

- An interruptible, visual construction/gathering progress bar with cancellation
  requires splitting atomic commands into scheduled multi-step jobs and save
  migration; do not fake an on-screen stopwatch after results are awarded.
- Check fixtures in all room types and NPC work arrival through shared doors.
- Tune reed biome density by multi-seed coverage benchmarks.

## 2026-10-11 final validation addendum

The original meal logic used only 30-minute clock boundaries for completion,
but each meal block is itself 30 minutes and normally ends at such a boundary.
Therefore the first attempt set "eating" action without ever reducing hunger.

Reworked meal completion to occur after ten scheduled in-world minutes *at
the routed seat position*. `InteriorActor.last_meal_minute` persists per-NPC
completion and prevents repeated meals from save/load or per-tick refreshes.
The added Windows CI regressions assert separate arrival points for two NPCs
sharing a house and a full indoor eating routine that actually reduces hunger.

On commit `d6b36d2512aa651ee396618df89ea43ab09f78c2`, targeted
Windows graphical/system tests passed, including reed generation and tool
bonus, prototype and save roundtrip, item description scrolling, outdoor NPC
collision and door routing, identity refresh, multi-NPC indoor entry, and meal
completion. Overall CI continues to fail only at the unrelated preexisting
Dev62 portrait fingerprint step; subsequent suites are skipped. This patch
requires manual real-Windows playtesting before declaring all graphical NPC
interactions flawless.

**Unfinished intentional scope:** user-requested visible interruptible
gathering/building countdown and cancellation. The implemented mechanic is
skill-adjusted *game-minutes charged when the action executes*, reported in
World Activity messages; it is not an active progress timer. A subsequent
job scheduler/animation pass is required to make timed, cancellable physical
work authoritative across saves and UI, rather than pretending to wait
after items were already awarded.
