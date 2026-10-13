# Early access runtime profiling handoff

Completed work unit 3 from `EARLY_ACCESS_PYGAME_PLAN.md`: bounded opt-in runtime
measurements and repeatable prepared reference scenes. Published as one unit
with tests, the initial baseline and Fast Gate coverage.

## Scope and contracts

`worldseed/profiling.py` owns transient rolling timing samples. Simulation,
debug preparation stages, pygame frames/menus and save checkpoints report to it.
The renderer distinguishes frame work from intentional action/menu pacing.
Save phases distinguish detached capture, optional backup, JSON, SQL and
transaction completion; phase nesting is documented in
[the usage guide](../development/RUNTIME_PROFILING.md).

Public diagnostic API: `RuntimeProfiler`, `measure`, `record`, `snapshot`,
`measure_if_enabled`, `profiled` and `runtime_profile_enabled`. `save_state`
accepts an optional `profiler` keyword. Profiling failures preserve body
exceptions. JSON is encoded before SQL writes; dirty revisions are acknowledged
only after the existing transaction succeeds. Transaction entry/exit delegates
to SQLite. Malformed JSONL diagnostic rows are skipped safely.

`tools/reference_scenes.py` exposes six bounded scenes. Fixtures use real
production simulation/world/planner/portal contracts with prepared synthetic
inputs, actual checkpoint files and no measured raw-generation fallback.
Rendering and the optional idle movement probe must preserve authority.
The tool writes reports and optional PNGs, checks events every iteration, records
source/hardware/version identity and never accesses player saves.

Persistent fields/migration: none. Schema, worldgen, hydrology, settlement and
route versions are unchanged. RNG namespaces: none added or modified.

## Validation and performance

Compileall and whitespace checks passed. The bounded targeted run passed 92
tests covering profiler bounds/disabled clocks, unchanged simulation/RNG/pixels,
read-only diagnostics, render pacing, six fixtures, deterministic captures,
event servicing, save capture/serialization/SQL/commit failures, retry/reload,
legacy save behavior, interior presentation and weather animation. Reference
fixture checkpoints and save-probe databases pass verifier invariants.

[Baseline JSON](../development/RUNTIME_REFERENCE_BASELINE.json) and the usage
guide record six sequential 40-frame reference runs, sequential 1,000/10,000
NPC movement probes and exploratory save-phase measurements. Profiling is off
by default; bounded opt-in samples add clock and storage overhead. The measured
save capture and local update costs grow with distant individual NPC state.
This unit records that scaling; it does not change actor scheduling or discovery
storage yet.

## UI, limitations and next dependency

Diagnostics displays rolling percentiles and stall counts only when enabled.
Enable with `--profile-runtime` or `WORLDSEED_PROFILE=1`. The reference runs are
warm-cache unpaced synthetic QA throughput on SDL dummy, not minimum hardware,
live frame-rate, natural-world art approval or a release validation result.
Input-to-display latency, cold crossings and complete scheduling stage coverage
remain future measurements. PNGs can be regenerated using the documented CLI;
large machine-specific captures are not stored in the repository.

Next work unit: replace broad actor scans with rebuilt local spatial indexes
and a bounded active set while preserving task/movement authority. Reuse the
population probes to demonstrate flat local update cost. Then address growing
checkpoint capture and compact discovery data under explicit legacy-save
round-trip/migration tests. Preserve source-of-truth and no-generation-in-render
contracts throughout.
