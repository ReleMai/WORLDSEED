# WORLDSEED Combat & Hunting Handoff

## Baseline

Combat/hunting phase 1 was merged to `main` at commit `f5f2a40448a6670217031b26d9ea899a56645d92`.

Validated source branch: `combat-hunting-phase1`.

Validated PR: #19, **Begin detailed animal combat and hunting phase**.

## Design contract

The new hunting layer must preserve WORLDSEED's existing simulation authority:

- ecology cohorts remain population authority;
- materialized animals are local projections of that ecology;
- killing a materialized animal reconciles the cohort exactly once;
- renderer/UI code remains observational;
- combat/hunting mutations are issued through simulation commands;
- same seed + same command sequence must remain deterministic;
- animal signs must be evidence of real animal movement/state, not unrelated decorative placement;
- local animal state must remain bounded and distant simulation must remain cohort-based.

## Implemented foundation

### Animal state

`CreatureState` now persists local combat/behavior information:

- behavior state;
- alertness;
- stamina;
- remembered threat position;
- last threat turn;
- last movement turn;
- facing direction;
- existing wounds, pain, blood and HP remain authoritative for physical injury.

`AnimalSignState` persists bounded physical evidence:

- tracks;
- blood sign;
- position;
- age;
- travel direction;
- strength;
- source creature identity;
- species identity.

### Species behavior data

`SpeciesDef` now supports:

- vision;
- hearing;
- scent;
- flee threshold;
- defensive aggression;
- stamina;
- trackability;
- herd response.

Rabbit, white-tailed deer, wild boar and grey wolf have deliberately distinct authored profiles. Other species currently inherit safe defaults and should be tuned in later passes.

### HuntingSystem

`worldseed/systems/hunting.py` owns local hunting perception and behavior.

Current perception channels:

- line-of-sight vision;
- recent player noise;
- wind-aware scent;
- close-proximity threat awareness.

Current behavioral states:

- calm;
- alert;
- flee;
- wounded_flee;
- defend;
- pursue.

Current physical behavior includes:

- deterministic terrain-aware local movement;
- fleeing toward distance/cover;
- pursuit toward the player;
- occupied-tile avoidance;
- wound-driven movement penalties;
- stamina-limited movement;
- same-species/cohort alarm propagation;
- actual movement-derived tracks;
- bleeding-derived blood trails;
- bounded sign count and expiration.

### Combat integration

Existing detailed melee wounds remain in place.

Ranged animal combat now resolves:

- usable in-range weapon/ammunition;
- target movement penalty;
- perception + Hunting skill;
- weighted species body location;
- skin/muscle/bone/organ penetration;
- fractures;
- bleeding;
- blood loss;
- pain;
- wound severity;
- weapon identity on the wound.

Hits and misses can alert animals. Nonlethal attacks feed directly into hunting AI so wounded animals flee, defend or pursue instead of behaving like untouched wildlife.

### Hunt continuity

Wounded or actively alarmed animals are kept materialized over a larger chase envelope than ordinary wildlife. This prevents a wounded animal from disappearing merely because it crossed the normal ecology materialization boundary.

### Player interaction

Right-clicking a visible animal can expose:

- Observe;
- close-range Attack;
- Aim / fire when a usable ranged weapon can reach the target.

Right-clicking real animal sign can expose inspection.

Look/Wildlife read models now surface behavior and, according to character skill, visible injuries, limping, blood loss, tracks, freshness and travel direction.

## Validation

Fast Gate run #59 completed successfully on the validated PR tree. The successful gate included:

- Python compile;
- combat/hunting regressions;
- fishing regressions;
- inventory/storage regressions;
- world-interaction regressions;
- floating interaction UI regressions;
- crafting-discovery regressions;
- natural-container regressions;
- coast tests;
- surface-cache/save-compatibility tests;
- atlas drag regression;
- content audit;
- visual audit;
- coast morphology audit;
- coastal-mouth audit.

The combat/hunting regression suite specifically covers:

- distinct rabbit/deer/boar/wolf behavior profiles;
- wounded deer fleeing and producing real blood sign;
- defensive boar response;
- weighted ranged body/tissue wounds and ammo consumption;
- behavior/sign persistence roundtrip;
- wounded-animal chase envelope;
- retained player armor/wound mechanics.

## Known gaps / next coherent phase

The next pass should deepen interaction rather than add unrelated combat content.

1. **Readied equipment**
   - Stop silently choosing the strongest melee/ranged item from inventory.
   - Add explicit ready/main-hand/off-hand/ranged state.
   - Preserve durable artifact identity when readied.

2. **Aiming and targeted attacks**
   - Add an Aim command/state with accumulated aim quality.
   - Allow center-mass, head/neck and limb targeting with appropriate difficulty.
   - Moving targets, cover, pain, arm wounds and fatigue should alter aim.
   - Keep exact percentages hidden unless a debug view requests them.

3. **Projectile semantics**
   - Separate bows/slings from thrown weapons.
   - A thrown spear must leave inventory/equipment, occupy a physical landing/embedded state and be recoverable.
   - Add projectile obstruction/cover checks rather than line-of-sight only.

4. **Stealth/stalking**
   - Add crouch/stalk movement.
   - Terrain, vegetation, weather, movement speed and equipment noise should modify sight/sound detection.
   - Wind already participates in scent and should remain a readable hunting consideration.

5. **More animal decision depth**
   - Herd cohesion and panic propagation.
   - Pack pursuit/flanking for wolves.
   - Boar/bear threat displays and charge commitment.
   - Deer/rabbit cover-seeking and escape-route preference.
   - Exhaustion, pain, blood loss and injury should continuously reshape choices.

6. **Expanded physical sign**
   - scat;
   - feeding sign;
   - bedding sites;
   - calls;
   - disturbed vegetation;
   - dens/nests;
   - species/terrain-specific footprint clarity.
   - These must still come from real state/events.

7. **Traps and snares**
   - Persistent placed traps;
   - bait/scent;
   - species suitability;
   - maintenance;
   - delayed outcomes;
   - injury/escape possibility;
   - population reconciliation.

8. **Combat time**
   - Current attacks still advance normal survival-time increments.
   - Introduce a bounded tactical action cadence so multi-action combat does not advance implausibly large world time while preserving the normal minute/hour/day simulation.

9. **Skill progression**
   - Hunting XP should come from meaningful actions such as identifying sign, successful stalking, placing useful shots and correctly processing carcasses rather than raw kill count alone.

10. **Species tuning**
    - Extend authored perception/temperament values beyond the first four vertical-slice species after the behavior contracts are stable.

## Important caveats

- `CombatSystem.best_weapon()` still auto-selects melee equipment from inventory.
- Ranged selection still chooses a usable ranged-capable inventory item rather than explicit readied gear.
- The wooden spear currently has ranged metadata but does not yet implement true thrown/recoverable projectile behavior.
- `EcologySystem.update_local_ai()` still exists as legacy code but the live Simulation post-action path now uses `HuntingSystem.update_local_ai()`.
- Only track/blood physical signs are currently implemented.
- No crouch/stalk input or targeted-shot UI exists yet.
- Combat still uses the normal action-time model.

## Next starting point

Start with explicit readied weapons + aim/targeting + projectile semantics. Those systems should be completed before adding many more weapons or animals because they define the command/data contract every later combat system will consume.
