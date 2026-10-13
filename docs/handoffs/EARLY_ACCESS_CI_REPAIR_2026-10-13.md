# Early access Fast Gate regression repair — 2026-10-13

## Baseline and publication

The checked canonical `main` baseline was `12c3b164498414718744d5d29f5be8d5598f5d32`, immediately after the compact discovery/local NPC indexing work unit. The Pygame Engine and Early Access Development Plan remains the controlling roadmap. The validated repair commit is `f70a29b7aacd983929008729bd8ebaf9458e0f84`: [diff](https://github.com/ReleMai/WORLDSEED/commit/f70a29b7aacd983929008729bd8ebaf9458e0f84).

This is a **test-contract repair**, not a change to gameplay, the renderer, the simulation, saving or world generation. No persistent fields, schema, RNG namespaces or generation versions changed.

## Repaired failures

1. Windows Fast Gate: six `tests.test_save_failure_ui` assertions expected a Unix-style literal `/saves/recovery.db` even though `Path('/saves/recovery.db')` formats with Windows backslashes. The test now compares against the platform-native `str(Path(...))`, retaining validation that the failure panel discloses the real path, error and retry instructions. No product UI formatting or save retry semantics were changed.
2. Dev31 presentation: the test inserted 251 NPCs directly into `state.npcs` after `Simulation` initialization. It bypassed the new transient locator registration contract, then expected a recently seeded NPC to appear in the indexed renderer query. The fixture now rebuilds exactly once at its explicit setup boundary. It rejects any rebuilding during the `_spatial_state_views` render read. Production spawn/movement hooks and the observational renderer are unchanged.

The prior Fast Gate failures are documented in [run 38415806066](https://github.com/ReleMai/WORLDSEED/actions/runs/38415806066).

## Validation

[Windows/Linux Fast Gate run 38446353231](https://github.com/ReleMai/WORLDSEED/actions/runs/38446353231) on repair commit `f70a29b` **passed all six jobs**, including primary smoke, world UI/content smoke, settlement/economy regressions, the two NPC lab jobs and the Linux process runner. The previously failing save failure/recovery step and Dev31 spatial renderer test both passed. This is development-gate validation, not a release or long player-soak certification.

## Next bounded engine work unit

Complete the remaining local-state/spatial-index portion of [the Pygame plan](../../EARLY_ACCESS_PYGAME_PLAN.md) before broad UI/recovery expansions:

1. Replace `PygameTerminal._spatial_state_views`' remaining full-collection cache rebuild, currently keyed by `(id(sim), sim.clock.minute//60, len(collections))`. Implement authoritative-mutation-driven indexes for creatures, structures, containers, crops, fires, fluids, ground piles, carcasses, animal signs and animal homes. The index must be transient; queries must not change world state or run preparation.
2. Cover same-count replacements, container relocation, moving tactical creatures, negative coordinates, z/interior transitions, large distant populations, exact viewport bucket boundaries, removals and death. Make sure rendering never repairs the index by scanning every collection. Preserve existing draw order and hidden-knowledge filters.
3. Bound the live-creature queries in `worldseed/systems/hunting.py::update_local_ai` (currently enumerates all realized creatures) using the same maintained creature locator, with movement registration at gameplay-authoritative boundaries. Test determinism, hunting behavior, ecology materialization/dematerialization and combat repositions.
4. Re-run the six reference scenes and the same-machine 1,000/10,000 distant-state probes. The latest [local-state handoff](EARLY_ACCESS_LOCAL_STATE_HANDOFF.md) records 0.185/0.237 ms movement-update medians with 1,000/10,000 NPCs; the proposed <=20% scaling threshold has not yet been achieved across that sample. Profile and report rather than asserting improvement based on one average.
5. After the spatial-index unit, separately address large-checkpoint capture and whole-state copying: earlier reference benchmarks measured roughly 91/945 ms median capture for 1,000/10,000 distant NPCs. Preserve transactional retry and revision-based dirty-tile acknowledgment.

Start subsequent implementation from the newly verified canonical main. Keep edits in one coherent work unit, run bounded regression checks, update this handoff, and publish only validated changes. Do not add a parallel simulation authority or rewrite saved geography.
