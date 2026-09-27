# Current build systems audit

Audited against the synchronized `main` tree for the craftable sprite update.

| Area | Included in current build | Evidence / scope |
| --- | --- | --- |
| Faction simulation | Yes | `worldseed/systems/factions.py` is initialized in `worldseed/sim/engine.py`; settlements hold faction allegiance and diplomacy/conflict logic runs in simulation. |
| Regional influence and route control | Yes | `worldseed/systems/route_planner.py` derives influence and hinterland regions, contested/frontier areas, and controlled border posts with tolls. |
| NPC professions | Yes | `worldseed/systems/professions.py` and `mining_profession.py` are constructed in the engine and attached to NPCs. Existing profession and transport tests pass. |
| Claim-monument capture | No | The Phase 4 handoff describes this as future steps (monument sites, structures, garrisons and capture). There is no completed implementation on `main` or a validated matching branch to merge. |
| Expanded workshop production | No | `phase4-workshop-expansion-wu6` contains branch-only workshop code, but the branch diverged from current `main` and its gate failed. It is not merged into this validated build. |

The old `work/grand-regional-civ-wu22` branch contains an early regional planning module. Current `main` already contains the newer terrain-first `worldseed/world/regional_civilization.py`; replacing it with that branch would regress the current world planner.

The recipe catalog has 72 recipes and 64 distinct output items. Each output now resolves through its `items.json` asset key to a unique 64×64 RGBA sprite. `tests/test_craftable_sprite_coverage.py` guards that mapping.
