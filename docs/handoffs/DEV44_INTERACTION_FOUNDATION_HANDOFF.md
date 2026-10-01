# Dev44 interaction foundation

## Scope

Stage 1 of [the settlement/interior redesign](../development/SETTLEMENT_INTERIOR_REDESIGN.md).
This work unit does not implement interior spaces, bigger farms, new architecture
art, AI recovery, housing construction or military expansion. Their researched
dependencies and acceptance checks are specified in that plan.

## Public contracts

- `SetHuntingStanceCommand(..., 'aggressive')` and `UI_STANCE:aggressive` select
  Aggressive Stance. The action menu and HUD expose it. Casing, both lockpick
  commands and forced door entry reject other stances before side effects.
- Leaving Aggressive Stance cancels casing. It uses normal movement speed and
  receives no crouch/stalk noise or concealment bonus. The HUD abbreviates its
  button to Aggro and spells out Aggressive Stance in its tooltip/action menu.
- `CasingSystem.can_case` accepts intact enclosed property. Open fields, pens,
  logging camps, mine approaches and monuments are directly inspected.
- Dialogue renders using pixel-measured wrapping and panel clipping. Community
  standing wraps in full; reply pages and transcript pages have separate controls.
  Inspect remains available across topics. Window title positions account for
  the width of the domain label.
- Nature/knowledge topic exposes animals, crops/plants, resources, towns and
  skill advice. NPC testimony derives from home livelihood, recorded knowledge,
  existing merchant routes and practiced skills; suspicious NPCs require trust.
  Wild animals require explicit known species facts. Selected answers disclose
  known species/towns, but browsing a topic has no simulation effects.
- Successors start on validated surface land near their death rather than (0,0).
  Bounded search checks local rings, known land, then sparse offshore rings;
  actual terrain/deltas, occupancy, natural blockers, doors/buildings and fluid
  passability are validated. Corpse goods stay at the original death location.

## Ownership, persistence, RNG and performance

New modules: `systems/npc_knowledge.py` (read testimony/explicit disclosure),
`systems/respawn.py` (bounded deterministic placement). Existing hunting state
owns stance; no new persistent fields or schema/worldgen/plan-version changes.
The aggressive stance round-trips through the existing string field. NPC facts
use existing knowledge and discovery collections. No new RNG namespaces.

Dialogue reads current facts without world generation. It does not teach skill
XP or invent sightings. Respawn samples fewer than 5,000 potential cells and
validates at most 512 actual candidate cells, only at the death command boundary.
Known-land ranking/occupancy collection are death-only work, not per-frame work.

## Validation

Passed: 13 new/routing tests, 55 direct-integration tests and a final 35-test
social/dialogue/hunting slice (overlapping coverage). Python compileall and
git diff --check passed. A headless preview was rendered and visually inspected:
`artifacts/dev44-dialogue-preview.png`; reproduce with
`python -m tools.preview_dev44_dialogue`.

New regressions cover command refusal, stance cancellation, property eligibility,
knowledge/read-only/disclosure/trust, nested dialogue routes, real-font wrapping,
paged choices and Inspect, bounded land search, death goods conservation and
pointer/movement routing. Existing property/social/retained-panel tests accompany
the focused suite. Compile all changed code and inspect the automatic Fast Gate.

The initial combined UI suite reached its 180s budget because existing UI fixtures
construct full simulations repeatedly. Keep follow-up checks to affected routing
tests and graphical fixtures, not a larger retry budget. The bounded runner can
misreport PASS when unittest reports errors on this host; read the unittest
summary and rerun corrected failures directly before publication.

## Known limitations / next dependency

Skill topics provide factual advice, not timed mentoring. Ordinary residents
know home agriculture/economy; active wildlife/plant observation is stage 5.
No safe candidate after the bounded spawn search leaves the death unresolved
with an explicit message; it never resurrects the player into water. UI graphical
checks are headless; live play/visual resizing remains a separate check.

Next: stage 2 farm compounds/seed/access audit, then explicit persistent space
identity before authoring the requested six house styles and interior portals.
