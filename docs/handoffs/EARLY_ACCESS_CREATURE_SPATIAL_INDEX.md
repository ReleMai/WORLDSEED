# Early access creature spatial index — 2026-10-13

Continuation of `EARLY_ACCESS_PYGAME_PLAN.md` work unit 4. Baseline: canonical `main` following the green Fast Gate repair at `f70a29b` and its documentation handoff. Scope is a *bounded creature indexing slice*, not completion of all stationary indexing or M2.

## Changes and authority

- New `CreatureSpatialMap` (ordinary `dict` subclass) holds authoritative `CreatureState` objects and transient 16-tile bucket indexes. Dict insertion, replacement, deletion, pop, popitem and clear keep membership current. In-place position changes must call `refresh(creature)` on the authoritative mutation path; reads may not rebuild or repair indexes.
- Simulation wraps loaded realized creature state once during initialization. Generated/removed creatures through ecology and combat use existing dictionary mutators, now indexed without a UI-owned population scan. Dict serialization via `LivingWorldState.to_dict()` retains only existing creature data; no persistent schema changes.
- Hunting local updates, proximity group behavior, alarm propagation and immediate movement collision candidates query bounded creature buckets. The canonical hunting step refreshes after each creature tile movement. The older standalone system interface retains plain-dict fallback behavior.
- Simulation encounter candidate refresh and tactical tells use the local locator. Combat knockback cancellation refreshes its restored position. Ecology standalone local movement also refreshes registered creature positions.
- Pygame creature presentation uses the maintained creature locator and historical 32-tile bucket ordering; stationary objects stay under the pre-existing renderer cache for now. Rendering never writes simulation or generates terrain.

## Limitations and next dependency

This is not a full stationary/creature index completion. Structures, crops, containers, grounds piles, fluids, fires, carcasses, signs and homes still use the old hour/count-keyed presentation cache, which can miss same-count relocations; index their mutation sites separately. Direct third-party coordinate writes to indexed creatures require `refresh` just like the NPC locator. Audit additional simulation movement and creature read sites before removing any further global scans.

Do not claim M2 performance targets or full release validation from targeted checks. Repeat reference-scene benchmarks with identical machine/configuration for meaningful before/after comparisons. Next: maintained indexes for stationary objects with mutation-aware relocation, then large-save checkpoint capture improvements.

## Validation

The new creature-index regression module is included in the bounded automatic Fast Gate local-actor step. Full hunting/combat and renderer regressions remain in existing smoke jobs. The change must pass these checks on its published SHA. Do not treat an unverified pending workflow as a pass.
