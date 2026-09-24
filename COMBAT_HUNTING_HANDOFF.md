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

## Phase 4 — active melee defense and attack decisions

### Active defensive choices

Combat now supports explicit one-exchange defensive actions instead of relying only on passive armor/shield coverage:

- **Dodge** spends stamina and creates an active evasion window based on Agility, Athletics, leg condition, fatigue, ranged/melee context, and carried shield weight. A successful active dodge avoids the hit completely.
- **Parry** requires a readied melee-capable weapon and only applies to melee attacks. Its interception window is driven by Melee skill, Agility, weapon handling, arm condition, fatigue, and incoming force. Successful parries can fully redirect light attacks or partially reduce heavier ones before shield/armor resolution.
- **Shield Guard** remains the broad-coverage shield action and maximizes interception area.
- **Shield Brace** is now mechanically distinct: it gives less coverage than Guard but increases shield stability, flat force control, and stamina efficiency against heavy impacts.
- Defensive intent is transient. It exists for the immediate post-action combat exchange and is cleared afterward or on load so stale save state cannot grant a free defense.

Incoming player-hit order is now:

`active dodge/parry -> passive evasion -> shield interception -> armor -> tissue/wound`

This preserves the existing wound/armor authority while making defense a player decision.

### Melee attack modes

The melee targeting interface now supports attack-mode choice while keeping the existing reach/difficulty overlay:

- **Standard** — baseline handling, damage, penetration, and stamina.
- **Quick** — higher accuracy and lower stamina use, but reduced damage/penetration.
- **Power** — lower accuracy and substantially higher stamina use in exchange for more damage/penetration and a higher blunt-fracture opportunity.
- **Thrust** — available to piercing/spear/javelin/knife-style weapons; trades some accuracy/stamina for stronger penetration and bleeding.

The green→red melee overlay uses the selected mode's real hit-chance modifier, so switching from Quick to Power visibly changes the tactical field before committing the attack.

### Shield bash and stagger

Equipped shields can now be used offensively against adjacent animals.

Shield-bash success combines Shield skill, Agility, shield stability, shield mass, fatigue, and deterministic combat RNG. Bash force uses shield block value, Strength, and Shield skill.

A sufficiently effective bash can:

- inflict blunt injury/pain;
- drain animal stamina;
- place the animal in a short **staggered** state;
- suppress the animal's immediate movement/attack response for the current exchange.

The stagger state is persisted on the creature for deterministic save/roundtrip behavior, but its duration is explicitly turn-bounded.

### Test arena extensions

The combat arena's incoming-hit laboratory now includes defense-specific drills:

- no-defense baseline;
- Dodge tests against melee and arrows;
- Parry tests against melee piercing attacks;
- Shield Guard tests against heavy frontal, side, rear, and ranged hits;
- Shield Brace tests against heavy frontal impacts.

Arena defense injection is local to the single synthetic strike and does not advance world time or mutate ecology authority.

### UI / navigation

All new verbs remain inside the Combat Action Hub rather than creating new global keys:

- Melee Attack
- Aim / Fire
- Dodge
- Parry
- Shield Guard
- Shield Brace
- Shield Bash
- Equipment / Wounds
- Combat Test Arena

This preserves the RC6 movement and navigation contract.

### Validation contract

Phase-4 regression coverage verifies:

- Quick/Standard/Power/Thrust tradeoffs;
- thrust legality by weapon class;
- active Dodge producing full avoidance;
- Parry being melee-only and weapon-dependent;
- Guard prioritizing coverage while Brace prioritizes stability;
- shield bash producing bounded animal stagger;
- defense/stagger save roundtrip;
- Combat Action Hub exposure without adding global key bindings.

## Phase 5 — tactical animal combat AI

### Data-driven tactical profiles

Species can now declare tactical combat behavior rather than relying only on aggression/flee thresholds:

- `combat_style`
- `charge_range`
- `charge_power`
- `display_range`
- `pack_coordination`
- `herd_cohesion`

Validation constrains those fields and older/modded species safely fall back to `generic`.

The first tuned tactical set includes rabbits/deer, elk, moose, wild boar, marsh boar, grey wolves, and brown bears.

### Committed charges and threat displays

Boar, moose, and bears can now distinguish between warning behavior and a committed attack.

- an uninjured territorial animal may stop and perform a visible threat display before committing;
- a recently attacked high-defensive-aggression charger can skip the warning and commit immediately;
- a charge persists for a bounded number of turns rather than being re-rolled every step;
- movement during the charge builds physical `charge_momentum`;
- leg trauma, critical blood/HP state, exhaustion, stagger, or reaching the target can end the commitment;
- charge movement is faster/more direct and costs more stamina;
- charge attacks prefer authored rush/charge/goring/trampling attacks where available;
- impact damage and fracture pressure scale with species charge power and accumulated momentum.

Dodge and Shield Brace now interact with that momentum. Dodging a committed charge forces the animal into a short recovery window. A successful braced shield collision can drain the charger, inflict recoil pain, and stagger it.

### Reach control against charges

A player who explicitly chooses **Parry** while holding a reach-2+ piercing weapon can meet a committed charge before body contact.

This is not a passive spear bonus. It requires:

- an actual committed charge;
- the Parry defensive action;
- a readied piercing reach weapon.

The interception uses the normal thrust/melee wound resolver. A successful point interception cancels charge momentum, spends the prepared defense, drains animal stamina, and produces a bounded stagger. A failed interception spends the prepared parry and lets the charge continue.

### Wolf pack tactics

Grey wolves now use deterministic pack roles when multiple local members of the same materialized group are present:

- one **anchor** applies direct pursuit pressure;
- remaining wolves alternate between **flank left** and **flank right** roles;
- flankers choose side/back approach positions using the player's actual facing;
- flank attacks prefer bite/hamstring-style authored attacks and bias toward lower limbs;
- exhausted or heavily pained wolves disengage instead of blindly continuing pressure;
- disengaging wolves move away from the player while also biasing toward pack cohesion.

Pack role assignment uses an isolated deterministic hash namespace and never creates distant individuals.

### Herd panic and cohesion

Prey/herd species now carry bounded local `panic`.

- direct attacks spike panic;
- alarm propagation transfers panic through nearby members according to `herd_cohesion`;
- panicked deer/herd animals flee away from the threat while retaining a cohesion pressure toward their group centroid;
- once the threat is lost, residual panic can produce regroup behavior rather than independent wandering;
- panic decays when the animal no longer perceives the threat.

This keeps the authoritative ecology cohort unchanged: tactics operate only on already-materialized local individuals.

### Tactical legibility

The local action log reports state transitions such as:

- threat display;
- committed charge;
- pack flanking;
- herd panic;
- disengagement.

Look/Wildlife screens expose pack role, charge momentum, and panic only at appropriate Hunting/Survival skill thresholds. Rendering remains observational.

### Test arena

A new **Tactical AI Field** preset loads:

- a boar charger;
- a moose territorial charger;
- a three-wolf pack;
- a three-deer herd;
- reach weapon and shield equipment.

This is designed specifically to exercise charge timing, side pressure, panic propagation, Parry/reach control, Dodge, Guard, and Brace.

### Persistence / determinism

Creature tactical state is save-compatible through appended defaults:

- committed charge deadline;
- charge momentum;
- pack role;
- panic;
- last threat-display turn;
- last attacked turn.

Tests cover tactical profile loading, reliable attacked-boar charge commitment, threat displays, wolf role assignment/flanking, low-stamina wolf disengagement, herd panic/cohesion, tactical-state roundtrip, reach interception, braced-charge recoil, charge impact cleanup, and the tactical arena preset.

## Phase 6 — combat spacing, displacement, and reach control

### Physical displacement

High-force combat can now change position instead of resolving every impact in place.

- committed animal charges can physically drive the player backward after a real damaging impact;
- heavier animals and higher accumulated charge momentum can move the player farther;
- a successful Shield Brace that catches the charge suppresses that knockback path;
- Shield Bash can drive an animal one tile away when enough force is generated;
- Power attacks can knock animals backward when weapon mass, weapon damage, and Strength produce enough force;
- ordinary movement can no longer step directly into a living creature's occupied tile.

Displacement checks the actual local terrain, resources, structures, fluids, player position, and other materialized creatures. It never manufactures a free cell.

### Collision injuries

If forced displacement runs into occupied/solid terrain, movement stops and Combat owns the resulting blunt trauma.

Player collision can create:
- blunt HP damage;
- pain;
- body-part damage;
- a bounded fracture chance at higher force.

Animal collision can create:
- blunt damage/pain;
- a physical wound;
- a short stagger;
- death/carcass resolution through the normal combat authority if the collision is lethal.

This keeps positional resolution in Simulation while wound/death resolution remains in Combat.

### Prepared reach control

Parry with a reach-2+ melee weapon now applies to ordinary closing pressure as well as committed charges.

When a hostile animal crosses from outside adjacency into attack range during the post-action exchange:

- a prepared reach weapon can make one interception attack before body contact;
- piercing reach weapons use Thrust while other valid reach weapons use Quick;
- a successful interception stops that approach for the exchange and attempts to restore the animal to its prior physical cell;
- if that prior cell is no longer free, the animal remains where physical occupancy allows, but the successful interception still spends/stops the attack;
- a failed interception spends the prepared Parry and the animal continues into its attack.

Only one prepared defense is consumed; this is not an unlimited passive opportunity-attack system.

### Disengage

The Combat Action Hub now exposes **Disengage**.

A disengage:
- requires an adjacent threat;
- requires a cardinal retreat tile;
- must increase distance from every currently adjacent threat;
- requires the destination to be physically free/passable;
- costs stamina, with additional cost from serious leg injury;
- creates one exchange of spacing grace against ordinary animals that must move to re-enter adjacency.

Committed charges explicitly ignore disengage grace. This means disengage creates tactical space without becoming a universal escape button.

### Tactical movement difficulty

Aim and melee/ranged hit calculations now recognize the expanded tactical movement states. Charging, flanking, herd flight, disengagement, and regrouping are no longer treated as if the target were standing calmly.

### Validation contract

Phase-6 regression coverage verifies:
- disengage distance/stamina/turn markers;
- invalid sideways/blocked retreat rejection;
- open creature knockback;
- collision injury when knockback hits solid terrain;
- player displacement followed by collision trauma;
- ordinary reach interception;
- disengage spacing grace;
- committed charges bypassing that grace;
- Combat Action Hub exposure without new global bindings.

## Phase 7 — stalking, animal life routines, physical evidence, homes, anatomy, and basic combat animation

### Unified stealth / stalking

Animal hunting now uses the same player stealth intent as the settlement/NPC sight-cone system instead of introducing a second stealth authority.

The existing Stealth skill remains the general trained-noise component. Hunting adds an explicit posture layer:

- **Normal** — full movement speed and normal visual/noise profile.
- **Stalk** — roughly double movement time with substantially quieter footfalls and a lower visual profile.
- **Crouch** — roughly triple movement time with the strongest posture concealment/noise reduction.

Stalk/Crouch automatically enable the existing stealth observer-cone mode; returning to Normal disables it. The legacy ToggleStealth command maps to Stalk/Normal for compatibility.

Animal movement detection now combines:

- posture;
- Hunting / Survival field skill;
- the existing Stealth skill and Agility noise reduction;
- terrain noise;
- equipped/readied gear mass and hard-metal noise;
- vegetation cover;
- rain/fog/wind masking;
- animal facing, vision and hearing;
- current animal activity/distraction.

Scent remains a separate wind-aware channel. Crouching cannot make the player scentless.

### Animal needs and distracted behaviors

Materialized animals now accumulate bounded local hunger and thirst and can perform physical routines instead of remaining combat/idle agents all day.

Implemented routines:

- seek real accessible water;
- stop and drink at a real water edge;
- seek actual mature edible wild resource features;
- forage at that physical feature;
- return to a persistent home/rest site;
- lie down/rest and recover stamina;
- wounded animals can retreat toward an established den/nest/bed where species behavior permits.

Resting animals are substantially easier to approach visually/audibly, drinking/foraging animals are moderately distracted, and traveling-to-need states have a smaller attention penalty. Threat/combat behavior still overrides routine behavior.

Needs advance from elapsed simulation minutes with bounded deltas; routines do not create distant animals.

### Persistent dens, nests, beds, forms, setts, lodges, and holts

Species now declare a home type, search radius and whether the home can hold a physical cache.

Initial home types include:

- rabbit burrows and hare forms;
- deer/elk/moose/goat/boar resting beds;
- bird nests;
- fox/wolf/bear/cave-predator dens;
- badger setts;
- muskrat/beaver lodges;
- otter holts.

Home placement is deterministic and bounded around an already materialized animal/group. It respects passability, cover, species-specific water adjacency for lodges/holts, and suitable cover for nests/dens. Cohort/group members can share one home instead of each creating a duplicate.

Homes are persistent state, capped at 600. Old undiscovered, unreferenced homes are eligible for bounded pruning.

A home can only store items by **transferring already-physical nearby food from a ground pile**. No den loot is invented. Discovered shelters can be inspected and searched from the world context menu; searching transfers the real cached items into inventory and empties the shelter cache.

### Expanded hunting evidence

Tracks and blood remain evidence of actual movement/wounds. Phase 7 adds:

- scat/droppings generated by the actual animal;
- feeding sign created when a real forage activity occurs;
- flattened bedding from rest;
- water-edge disturbance from drinking;
- disturbed vegetation created by movement through substantial cover;
- short-lived alarm/warning calls created from real group alarm events;
- den/nest/home-use sign from an actual persistent shelter.

Evidence has type-specific lifetimes rather than one universal expiry window. Descriptions remain skill-gated by Hunting/Survival and expose freshness, species, direction, print strength, and evidence type only where the player has enough field skill.

The terminal and pygame local maps now render visible evidence and discovered shelters. Rendering remains observational: evidence exists in simulation state before the renderer can display it.

### Data-driven animal anatomy

Species definitions now include explicit body layout, named organs, harvestable anatomy and mass-derived size bands.

The current shared organ vocabulary is:

- heart;
- lungs;
- liver;
- kidneys;
- brain;
- trachea.

Each organ defines:

- anatomical zone;
- relative hit weight;
- vitality;
- bleeding tendency;
- species-derived size band/mass percentage.

Body layouts now distinguish standard quadrupeds, birds (including wings), and seals/flippers. Locomotion targeting/injury rules recognize flippers as well as legs.

Melee and projectile penetration can now reach a named organ. The wound stores the organ and organ-damage percentage; organ vitality/bleeding changes the resulting trauma. Severe heart/brain trauma is especially dangerous and tracheal trauma can worsen bleeding.

When the animal dies, maximum recorded damage for each named organ transfers to the carcass.

### Anatomical harvesting

Carcass processing adds **Harvest organs / anatomical parts**.

Recovery is deterministic and depends on:

- species body mass;
- configured part mass percentage;
- rarity;
- Hunting skill;
- cutting/butchering tool quality;
- recorded organ damage.

Current named harvests include heart, liver, kidneys and lungs for all authored animals, plus antlers for deer/elk/moose, tusks for boar, and flight feathers for birds.

To preserve the existing item-asset invariant, named organs currently resolve to the existing physical `offal` inventory commodity, while antlers/tusks resolve to bone and flight feathers to feather. The carcass record and processing messages retain the named anatomy, size and damage. Dedicated per-organ inventory items should only be added together with unique art assets.

Named parts cannot be harvested twice.

### Basic combat presentation events

Simulation emits a bounded, runtime-only presentation event for:

- projectile flight / blocked projectile impact;
- melee attacks;
- shield bash;
- animal attacks.

Pygame consumes only unseen events and draws short, non-authoritative animations:

- projectile tracer/travel dot;
- melee/bash attack sweep;
- animal attack sweep/impact pulse.

The buffer is capped at 24 and is intentionally absent from save state. Rendering never determines whether an attack hit.

### Persistence and validation contracts

New save-compatible state includes:

- animal homes;
- animal hunger/thirst activity target/timers;
- home association;
- carcass organ damage and harvested-part history;
- player hunting posture and reserved hunting XP field.

Regression coverage validates posture noise/concealment, equipment noise, real water drinking, real-resource foraging, shared persistent homes, wounded retreat, evidence/home save roundtrip, organ definitions and size bands, named vital trauma, damaged-organ harvest loss, non-repeat harvesting, and bounded nonpersistent visual effects.

## Known gaps / next coherent phase

The next pass should extend tactical depth without replacing the phase-1/2 contracts.

1. **Stealth / stalking beyond phase 7**
   - explicit scent-control consumables / washing where later survival systems justify them;
   - crawling/prone posture if animation and collision support warrant it;
   - deeper animal investigation of an uncertain sound/scent source instead of only alert/flee/attack;
   - persistent territorial memory and learned player danger.

2. **Projectile depth beyond the phase-3 foundation**
   - target-cell posture/cover exposure;
   - projectile speed / time-of-flight where tactically meaningful;
   - embedded-projectile extraction wounds from living targets;
   - richer material-specific ricochet/breakage.

3. **Animal combat depth beyond phase 5**
   - species-specific feints, bluff displays and retreat thresholds;
   - pack target switching and wounded-member protection;
   - true knockback / trampling displacement;
   - den/young defense and territorial memory;
   - predator-prey combat between non-player animals.

4. **Melee depth beyond phase 6**
   - bind/feint/counter interactions;
   - weapon-class specific parry quality and attack animations;
   - grappling / clinch behavior for appropriate actors;
   - richer knockback outcomes such as prone, wall pinning, and downhill momentum.

5. **Evidence depth beyond phase 7**
   - continuous track chains / trail reconstruction;
   - terrain-specific hoof/paw print clarity and weather erosion;
   - seasonal/age interpretation;
   - species-specific scrape/rub/shed sign;
   - marking/scent-post behavior.

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
- The targeting UI still exposes four broad anatomical aim zones; once penetration resolves, Phase 7 can record damage to species-specific named organs.
- Hunting evidence now includes tracks, blood, scat, feeding sign, bedding, water-edge disturbance, disturbed vegetation, alarm calls, and home-use sign. Continuous trail reconstruction and richer terrain/weather interpretation remain future work.
- Stalk and Crouch are implemented and share the settlement stealth intent; crawling/prone remains future work.

## Next starting point

The next coherent hunting work is **traps/snares + hunting progression + animal investigation behavior**. Phase 7 now provides the physical homes, needs, evidence, concealment, anatomy, and carcass detail those systems need to consume rather than inventing parallel abstractions.
