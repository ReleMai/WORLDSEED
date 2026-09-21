# WORLDSEED RC7 Balance Guide

## Philosophy

Balance protects possibility, not a fixed sequence. A sandbox start should be difficult because of world conditions and player choices, not because a necessary primitive ingredient failed to exist anywhere nearby.

## Start fairness metrics

`tools/balance_early_game.py` samples generated starts without granting supplies. Final 20-seed sample, radius 14:

- weak starts: 0
- empty starts: 20/20
- median resource cells: stone 100.5, branch 36, fiber 39, edible 45.5, water 123, trees 206
- worst nearest distance observed: stone 13, branch 9, fiber 6, edible 5, water 10, tree 3

These are *opportunity* metrics, not guaranteed pickups; resources remain undisclosed and must be found.

## Zero-item bootstrap gate

`tools/bootstrap_smoke.py --seeds 10` must pass. It validates generated-material access through:

empty inventory -> stone/branch/fiber -> flakes/cordage -> knife/axe/sling -> campfire -> timber -> carcass processing -> cooked meal -> nutrition history.

Farming is intentionally not required in that exact chain because wild seed availability is seasonal/exploratory rather than a guaranteed spawn resource.

## Time targets

Primitive actions should create meaningful day planning. Guidelines:

- trivial hand processing: minutes;
- crude tool construction: tens of minutes;
- felling/mining: meaningful work blocks affected by skill/tool quality;
- drying: many hours;
- tanning: roughly a day or more;
- crop growth: many days/seasonal;
- construction: scales with material and sophistication.

## Food balance

Food has four simultaneous concerns:

1. immediate hunger/satiety;
2. energy/macros;
3. diet-group diversity;
4. spoilage/preservation.

No single primitive food should be optimal across all four. Cooking increases usability/satiety; preservation trades time/station requirements for shelf life; diverse meals improve longer-term diet.

## Animal balance

Mass, health, aggression, group behavior, habitat and carcass yield must correlate. Small prey should be accessible but low-yield. Large herbivores offer more material but are harder/dangerous. Predators can be resource-rich but are not intended as optimal early-game prey.

## Farming balance

Each crop has a niche across growth time, climate, nutrition, fiber utility, N/P/K usage and disease family. Crop rotation should outperform repeating one crop indefinitely, but no single rotation should be mandatory.

## Performance budgets

Final RC7 measurements in this environment:

- world generation: ~15.11 ms per 32x32 chunk (100-chunk benchmark)
- movement: ~1.62 ms per step
- movement + 100x30 render: ~3.97 ms per step
- 25-year aggregate worlds: zero invariant failures across three seeds
- 100-year aggregate world: zero invariant failures; ~1.96 MB state

These are engineering budgets, not hardware guarantees.
