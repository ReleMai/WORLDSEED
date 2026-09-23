# WORLDSEED Combat & Hunting Handoff

## Baseline

Combat/hunting phase 1 was merged to `main` at commit `f5f2a40448a6670217031b26d9ea899a56645d92`.

Combat/hunting phase 2 was merged to `main` at commit `0d17b4f441350c80f5cbd8cc6848f0215d2f4967`.

Validated phase-2 source branch: `combat-hunting-phase2`.

Validated phase-2 PR: #20, **Deepen combat readiness aiming and primitive weapon handling**.

Combat targeting/range visualization was merged to `main` at commit `766fff52bdd43c64e7eaa85a8ccc025b5ac86a1f`.

Validated range-overlay PR: #21, **Add skill-graded melee and ranged attack radius overlays**.

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

## Phase 2 implemented

### Explicit weapon handling

Combat no longer silently chooses the strongest weapon in inventory. The player now has persistent readied-weapon state and can ready/lower carried weapons through the authoritative command path.

Readied weapons expose handling data:

- weapon class;
- melee reach;
- ranged range;
- accuracy modifier;
- stamina cost;
- thrown/recoverable behavior;
- projectile recovery rate;
- one-hand/two-hand requirement.

Two-handed weapons require the off-hand to be free. If a readied item leaves inventory, readiness and aim are reconciled automatically.

### Tactical aiming

Ranged combat now has persistent aim state:

- target creature;
- target zone;
- accumulated steadiness.

Supported zones:

- center mass;
- vital area;
- head / neck;
- legs.

Repeated Aim actions build steadiness, while animal movement degrades it. Shot resolution combines weapon handling, range, target motion, aim quality, Perception, Hunting, fatigue and arm injuries. Target-zone difficulty trades hit probability for anatomical placement.

### Melee handling and reach

Melee now uses the explicitly readied weapon and evaluates:

- weapon reach;
- weapon handling accuracy;
- Agility;
- Melee skill;
- stamina/fatigue;
- arm injuries;
- moving target state.

Long thrusting weapons can attack beyond adjacent range. Pure ranged weapons such as bows/slings cannot be used as ordinary melee weapons.

### Tactical time and stamina

Aim, melee attack and ranged attack now use a one-minute tactical cadence instead of the ordinary survival action interval. Weapons have stamina costs, allowing light knives/slings to handle differently from heavier clubs, axes and javelins.

### Physical projectile semantics

- arrows and sling stones can survive a shot and remain as physical ground items according to recovery probability;
- thrown javelins leave inventory when thrown;
- thrown javelins physically land at the target tile and can be recovered;
- invalid/out-of-range/empty-ammunition attempts do not incorrectly consume/throw projectiles.

### Primitive weapon progression

The early craftable combat set now includes:

- Stone Knife — light close combat/carcass utility;
- Stone Axe — heavier cutting weapon/tool;
- Club — basic blunt weapon;
- Sling + Sling Stones — low-cost small-game ranged option;
- Primitive Self Bow + Stone Arrows — deliberately aimed early bow;
- Fire-Hardened Javelin — two-tile thrust reach plus recoverable thrown attack.

The historical `core:wooden_spear` content ID is retained for save/asset compatibility, but its authored identity is now the Fire-Hardened Javelin.

The Primitive Self Bow is intentionally craftable from wood + plant cordage without a workbench. The javelin is shaped/fire-hardened at a campfire.

## Validation

Phase-2 Fast Gate run #61 completed successfully. It passed compile, item assets, biome atlas, fishing, combat/hunting, storage/inventory, world interaction, floating interaction UI, crafting/discovery, natural containers, coast/worldgen, save compatibility, atlas drag, content audit, visual audit, coast morphology and coastal-mouth checks.

The combat/hunting suite additionally covers explicit readiness, primitive weapon definitions/recipes, accumulated aim, targeted head/leg shots, readied/aim save persistence, animal behavior/sign persistence, wound behavior and retained player armor mechanics.

## Combat targeting overlays implemented

Combat targeting now has a read-only tactical range projection backed by the exact hit-chance formulas used by live combat.

### Ranged attack radius

- entering Aim / Fire displays a directional sector from the player toward the targeting cursor;
- moving the mouse across the world rotates the sector immediately;
- the sector is bounded by the readied weapon's physical range;
- cells grade continuously from green (easier) through yellow/orange to red (harder);
- the grading responds to Perception, Hunting, weapon accuracy, range, selected anatomical zone, accumulated aim, stamina, arm injury and target motion;
- blocked lines of fire are neutral/grey rather than presented as viable shots;
- undiscovered tiles are not revealed by the combat overlay;
- the selected tile is outlined more strongly;
- hover/sidebar feedback exposes only qualitative difficulty: easy, favorable, fair, hard, very hard, or blocked.

Higher skill therefore does not arbitrarily increase the weapon's physical maximum range; it makes a larger part of that range tactically reliable and visibly greener.

### Melee attack radius

The Attack action now opens a proper targeting state rather than immediately requesting a direction.

- all legal cells inside the current weapon's reach are displayed;
- reach-2 thrusting weapons show their full outer ring;
- melee difficulty uses Agility, Melee skill, weapon handling, reach distance, stamina, arm injuries and target motion;
- extended melee thrusts may no longer pass through blocking terrain/objects;
- right-click animal attacks route through the same targeting view.

### Rendering contract

The graphical renderer draws a faint skill-colored ground fill beneath sprites plus a stronger outline above weather/lighting so animals remain readable. The terminal fallback colorizes the same cells. The overlay never mutates simulation state.

### Validation

Fast Gate run #66 passed completely on the final PR head. New deterministic regressions verify:

- ranged sector rotation;
- skill improving downrange difficulty;
- blocked-cell classification;
- harder anatomical aim zones;
- melee reach geometry;
- skill improving attacks at outer reach.

## Phase 3 — projectile cover, shields, and combat test arena

### Projectile flight / cover

Ranged attacks now use a dedicated deterministic local `ProjectileSystem` rather than treating line-of-sight as the entire ballistic model.

- projectile paths are traced cell-by-cell through the already materialized local world;
- solid sight-blocking terrain/structures stop the projectile before the target;
- trees, boulders, brush, reeds, crops and other physical cover contribute bounded partial-cover penalties;
- sufficiently substantial partial cover can deterministically intercept the projectile;
- ranged difficulty overlays read the same projectile cover preview, so displayed shot difficulty and simulation resolution agree;
- misses land at a deterministic bounded fall-short/long/lateral location rather than always at the target cell;
- recoverable projectiles stop at the actual obstacle/landing cell;
- arrows and thrown javelins that hit can remain embedded in living animals and transfer into the resulting carcass;
- carcass processing exposes a Recover action and automatically recovers remaining embedded projectiles during deboning.

Projectile RNG namespaces are isolated as `projectile-cover` and `projectile-miss`.

### Active shield system

Shields are off-hand defensive equipment rather than passive armor coverage. The combat resolver now evaluates shields before body armor and wound penetration.

Shield interception chance combines:

- shield melee or ranged base coverage;
- shield-specific coverage of the struck body region;
- player facing relative to the source attack;
- Shield skill;
- Agility;
- active Guard bonus;
- fatigue;
- heavy-shield handling penalty.

Front, side and rear attacks therefore produce different effective coverage. A tower shield can dominate frontal missile defense without pretending to cover the player's back. Once intercepted, block strength/stability determine how much incoming force is removed; Shield skill and Strength improve the block, while successful blocks consume stamina. Durable metal shields also lose artifact condition when absorbing impacts.

The new Shield skill is part of character creation and is backfilled to 0 on older saves.

Six authored shield profiles are present:

- Rawhide Buckler — fast, excellent arm/melee interception, weak missile/body coverage;
- Wicker Shield — broad low-cost primitive coverage with low stability;
- Wooden Round Shield — balanced close/ranged coverage;
- Hide Kite Shield — long torso/leg coverage with more weight;
- Iron Heater Shield — high-stability frontal melee/ranged defense;
- Steel Tower Shield — extreme frontal missile/body coverage at the highest stamina and weight cost.

All six have distinct data profiles. The five new shield items have unique item sprites and all six have crafting recipes/progression.

### Guard action

The Combat Action Hub now exposes Guard. Guard requires an equipped shield, spends stamina, raises coverage for the immediate defensive exchange, and remains entirely on the authoritative command/combat path.

Two-handed weapons and off-hand shields are mutually exclusive in both directions: a two-handed weapon cannot be readied while the off hand is occupied, and an off-hand item cannot be equipped while a two-handed weapon is readied.

### Combat Test Arena

The Combat Action Hub also contains a dedicated **Combat Test Arena** developer laboratory. It uses `NavigationStack` and authoritative arena commands rather than mutating state from UI code.

Arena controls include:

- spawn any combat weapon, shield, or ammunition;
- spawn any authored/procedural animal at chosen bearings/ranges;
- edit all player combat-relevant attributes and skills from bounded test values;
- apply/heal light wounds, major bleeding, arm fracture, leg fracture, and exhaustion;
- simulate incoming front/side/rear melee and ranged impacts against the current shield/facing;
- clear arena creatures and restore player vitals.

Practice presets provide:

- close-combat ring — animals from several orientations plus knife/club/javelin/shields;
- ranged lane — rabbit/deer/boar/wolf at several ranges with bow/sling/javelin supplies;
- injury lab — fractures/bleeding, treatment supplies, shield set and a close threat;
- shield gauntlet — all six shields and threats from opposite sides.

Arena animals use an `arena:` UID prefix, are marked notable locally, and have no cohort key. They therefore cannot decrement or pollute authoritative wildlife cohorts. Arena management commands intentionally do not advance world time or trigger ecology/world simulation side effects.

### Persistence and validation contracts

New persistent state is backward-compatible by defaults:

- shield skill;
- player facing;
- transient saved guard flag (cleared on Simulation construction);
- creature embedded projectiles;
- carcass source identity / embedded recoverables.

Dedicated regression coverage verifies shield catalog/profile distinctness, facing-dependent coverage, buckler-vs-tower ranged behavior, Guard effects, shield-before-wound resolution, legacy skill backfill, state roundtrip, projectile partial/hard cover, deterministic miss landing, ecology-safe arena animals, arena stats/injuries/presets, and embedded-projectile recovery.

## Known gaps / next coherent phase

The next pass should extend tactical depth without replacing the phase-1/2 contracts.

1. **Stealth and stalking**
   - crouch/stalk stance;
   - slower/quiet movement;
   - vegetation/terrain concealment;
   - equipment noise;
   - weather masking;
   - wind-readable scent approach.

2. **Projectile depth beyond the phase-3 foundation**
   - target-cell posture/cover exposure;
   - projectile speed / time-of-flight where tactically meaningful;
   - embedded-projectile extraction wounds from living targets;
   - richer material-specific ricochet/breakage.

3. **Animal combat decision depth**
   - committed boar/moose/bear charges;
   - wolf pack pursuit and flanking;
   - herd cohesion, panic cascades and regrouping;
   - defensive threat displays before some attacks;
   - exhaustion and pain altering attack selection.

4. **Melee defense beyond shields**
   - explicit dodge/parry choices;
   - reach control and closing distance;
   - weapon-class specific attack modes;
   - shield bash / bind / brace decisions.

5. **Expanded sign**
   - scat;
   - beds;
   - feeding sign;
   - disturbed vegetation;
   - calls;
   - dens/nests.

6. **Traps and snares**
   - persistent placement;
   - bait/scent;
   - species suitability;
   - injury/escape outcomes;
   - delayed checking;
   - ecology reconciliation.

7. **Hunting progression**
   - XP for correctly reading sign, stalking, good shot placement and carcass handling;
   - avoid simple kill-count grinding.

8. **Weapon depth**
   - improved bows and arrows;
   - stone-tipped spear distinct from light javelin when dedicated new art is added;
   - weapon condition/breakage for primitive gear;
   - material quality effects on penetration/handling.

## Important caveats

- Weapon readiness currently references carried stack items; dedicated per-item weapon instances/condition are still future work outside existing durable-artifact handling.
- Aiming has four broad anatomical zones rather than species-specific named organs.
- Only track and blood physical signs are implemented.
- No crouch/stalk stance exists yet.

## Next starting point

Start with stealth/stalking + projectile flight/cover + active melee defense. Those three systems will make the existing readiness, aim, anatomy, animal perception and weapon classes interact as one coherent combat loop.
