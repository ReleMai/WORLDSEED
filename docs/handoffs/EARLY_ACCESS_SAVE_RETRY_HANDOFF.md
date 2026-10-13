# Early access save retry preservation — 2026-10-13

Started from freshly fetched canonical main `cc6b63e7e3c404fd8a77496d2fa346f10f0275e0`; the complete checkout passed workspace preflight before editing. Reviewed `EARLY_ACCESS_PYGAME_PLAN.md`. Its code baseline remains applicable: the intervening commit added planning documents only. This implements the first proposed work unit, synchronous save correctness and recoverable failure UI.

## Scope and contracts

- `World.snapshot_dirty_tiles()` captures immutable terrain values and per-tile mutation revisions without draining edits or releasing chunk pins. `acknowledge_dirty_tiles(snapshot)` clears only revisions confirmed by that checkpoint, including correct handling of a tile changed back to its earlier value. Other pending edits in the same chunk keep it pinned.
- `set_terrain` pins before cache loading so an all-dirty, full cache cannot evict the newly edited chunk before applying its mutation. Failed loads remove unnecessary pins. Once pending edits commit, normal cache eviction resumes.
- `app._save` captures detached inventory, vitals and nested simulation state before backup/database writes. It acknowledges terrain and updates the live offline checkpoint time only after `save_state` returns from a successful SQLite commit.
- `WorldDatabase.save_state` accepts optional checkpoint metadata and writes it in the same transaction as turn, player components, terrain, simulation state and events. Serialization, SQL or commit failure retains the previous durable checkpoint. Generated cache work already pending before snapshot capture may remain in its existing transaction when capture or backup fails.
- `_try_save` reports the actual path/error and retry instructions through existing UI widgets, pauses realtime while the panel is open, and logs diagnostics best effort. Failed pause-menu save/menu/quit, direct quit and modal window close retain the live context/database. Closing the recovery panel also preserves the session.
- Autosave tracks the last attempted turn, preventing frame-by-frame retries after failure. Another normal interval retries automatically; Pause > Save game retries immediately. Full rotating backups remain limited to explicit checkpoints.
- Added 16 persistence/cache regressions and nine failure-routing UI regressions, with a bounded step in the existing automatic fast gate. `drain_dirty_tiles` remains an eager compatibility helper for older tooling/tests; checkpoint writers must use snapshot/acknowledgement.

## Persistence, determinism and cost

No persistent fields, schema migration, generation versions or RNG namespaces changed. Existing schema-1/2 migration defaults and schema-3 round trips remain covered; legacy terrain stays pinned to its recorded generator. Mutation revisions are transient and exist only for currently pending edits.

Snapshot/acknowledgement work follows pending terrain edits, not total world size. Unsaved chunks may exceed the normal cache capacity until a successful retry. A detached simulation snapshot adds copying cost to synchronous saves; large-save capture/encoding/SQL/backup timing belongs in the planned instrumentation unit. No async worker, persistence-format replacement, renderer replacement or performance-target claim is included.

## Local development validation

- Compileall for `worldseed`, `tools` and `tests`, plus `git diff --check`, passed.
- Final bounded targeted run passed 34 tests in 0.658 seconds: `test_save_retry`, `test_save_failure_ui`, `test_cache`, `test_conversation_pause` and the existing modal-close save/cleanup regression in `test_dev21_mouse_ui`.
- The existing `test_persistence.PersistenceTests.test_gather_save_reload` also passed in an earlier invocation. That invocation selected a nonexistent `test_hardening` module and consequently exited with a loader error; the corrected final suite above is green.
- All five `test_development_workflow` checks passed through a separate bounded runner.
- Failure injection covers state capture, JSON encoding, backup, actual SQLite write rejection and transaction-exit failure, followed by successful retry/reload. Tests also cover newer edits after capture, identical-value edits, same-chunk dirty pins, one-slot cache pressure, detached nested state and previous-checkpoint backups.
- A representative legacy-v3/schema-3 fixture created with `tests.test_save_retry.make_save_fixture`, saved twice including an explicit rotating backup, passed bounded `tools/verify_save.py` with `Save integrity: OK`.

Validation is development-level. The automatic GitHub gate runs once on publication; comprehensive release hardening and invited playtests remain separate.

## Next dependency

Implement the plan's second P0 unit: cabin stage occupancy and reachable-exit safety, using the same stable door/interior/collision authority for players and NPCs, with rotation, rejection, cancellation and reload regressions. Keep async saving, spatial/discovery changes and broad visual work in later coherent units.
