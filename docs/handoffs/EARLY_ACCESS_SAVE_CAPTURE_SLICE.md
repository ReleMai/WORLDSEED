# Early access save-capture optimization slice — 2026-10-13

Baseline: `2e7aa80e1e483cdf8b1303d432204f5afc288382` (stationary indexes at `2e7aa80`; code work started after its targeted local tests passed, pending full gate confirmation at drafting time). This opens the next M2 performance work unit; it is **not** a release-ready 50 ms save-capture claim.

## Safe snapshot change

- The previous `_save_checkpoint` path did `deepcopy(state.to_dict())`. `LivingWorldState.to_dict()` already constructs each NPC payload via `dataclasses.asdict`, which recursively copies nested actor memory, tasks, inventory and relationships. The outer deep copy repeated that work for every remembered NPC.
- New `LivingWorldState.checkpoint_snapshot()` generates exactly the same detached payload, but uses a local `deepcopy` memo entry for **only** the freshly constructed `npcs` map. Every other field still follows the former deep-copy route.
- The checkpoint remains detached from live actors. No changes to fail/retry transaction semantics, revision-aware dirty terrain acknowledgment, persistence schema, JSON ordering, engine versions or world generation.
- Save code still captures snapshot before database writes and only acknowledges terrain after successful SQLite commit.
- `tools/save_capture_probe.py` supplies a bounded, optional, deterministic same-machine comparison of legacy and revised snapshot capture at 1,000 and 10,000 synthetic distant NPCs. The probe does not open saves or mutate the game and checks payload equality each repetition. It is *not* a gameplay-frame, transaction or long-session benchmark.

## Validation

- Four regression tests cover exact payload equality, deep nested actor isolation, non-NPC field isolation and the synthetic probe's bounds/equality. Existing save failure, serialization-error, SQL rollback, retry and old-format tests are still mandatory.
- Fast Gate extends the existing profiling/reference-scenes check. **Exact SHA needs a full green gate before this unit can be called validated.**
- Do not claim the original 91 ms / 945 ms capture figures have improved until comparable probes are measured on named hardware. Run `python -m tools.save_capture_probe --npc-count 1000 --npc-count 10000 --repeats 3` and record results.

## Handoff

Next: repeat all six reference scenes with equal seeds/viewports and save loads, address other costly state capture and broad hourly planning only after profiling. The planned work unit 5 is shared graphical panel style plus usable cabin/recovery loop; avoid unbounded UI rewrites.
