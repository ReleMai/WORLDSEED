# Current build systems audit

Updated against synchronized `main` at `4f00caa` on 2026-09-28, including the subsequently integrated workshop expansion.

| Area | Included in current build | Evidence / scope |
| --- | --- | --- |
| Faction simulation | Yes | `worldseed/systems/factions.py` is initialized in `worldseed/sim/engine.py`; settlements hold faction allegiance and diplomacy/conflict logic runs in simulation. |
| Regional influence and route control | Yes | `worldseed/systems/route_planner.py` derives influence and hinterland regions, contested/frontier areas, and controlled border posts with tolls. |
| NPC professions | Yes | `worldseed/systems/professions.py` and `mining_profession.py` are constructed in the engine and attached to NPCs. Existing profession and transport tests pass. |
| Claim-monument capture | No | The Phase 4 handoff describes this as future steps (monument sites, structures, garrisons and capture). There is no completed implementation on `main` or a validated matching branch to merge. |
| Expanded workshop production | Yes | Integrated into main at `4f00caa`; `worldseed/systems/workshops.py`, specialist processes and station UIs are present. All five workshop expansion regressions passed during the resumed workflow audit. |

The old `work/grand-regional-civ-wu22` branch contains an early regional planning module. Current `main` already contains the newer terrain-first `worldseed/world/regional_civilization.py`; replacing it with that branch would regress the current world planner.

The recipe catalog now has 82 recipes and 73 distinct output items. Each output resolves through its `items.json` asset key to a distinct RGBA sprite. The authored craftable refresh uses 64×64 icons; workshop additions also use the supported 32×32 format. `tests/test_craftable_sprite_coverage.py` guards the mapping, dimensions and uniqueness.
