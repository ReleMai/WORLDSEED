# Runtime profiling and reference scenes

Enable transient diagnostics with `python run_worldseed.py --profile-runtime` or
`WORLDSEED_PROFILE=1`. Open Diagnostics to inspect p50/p95/p99, worst duration and
samples over 100 ms. Profiling is disabled by default. It does not enter saves,
consume simulation RNG, advance time, or change geography/version contracts.

`RuntimeProfiler` retains 1,024 samples per stage and at most 64 stages in a live
simulation. Percentiles use linear interpolation over the retained rolling
window. `count`, `lifetime_worst_ms` and `lifetime_over_100ms_count` cover the
session; `window_count`, percentiles, mean, worst and `over_100ms_count` cover the
window. Stage overflow is counted without retaining new names. Disabled timers
skip clock access and sample storage; diagnostic clock failures cannot replace
gameplay/save exceptions.

The current stages measure:

- `simulation.command`, `simulation.realtime`, `simulation.free_movement` and
  `preparation.*` around existing engine work.
- `render.prepare`, `render.terrain`, `render.terrain_cache`,
  `render.objects_actors`, `render.effects`, `render.ui`, `render.present` and
  `render.frame`. Terrain cache work is nested in terrain; do not add them.
  Frame duration includes display flip and excludes `clock.tick` pacing and
  action animation playback. `render.action_animation` records actual playback,
  including its intentional pacing. Runtime `render.panel_total` and
  `render.menu_total` include menu pacing and may overlap fallback menu work.
- `save.total`, `save.capture`, `save.backup`, `save.database`, `save.json`,
  `save.sql`, `save.commit` and failed-transaction `save.rollback`. Capture
  includes component conversion, the dirty snapshot and detached simulation
  snapshot. Database contains JSON, SQL and transaction completion. Backup is
  recorded only at explicit backup checkpoints. These stages overlap.

These are subsystem duration measurements. They do not yet measure complete
input-to-display latency, every scheduling phase, or background preparation
queue latency.

## Repeatable renderer runs

```bash
python -u tools/run_ci_check.py --name reference-scenes --timeout 180 -- python -u tools/reference_scenes.py --scene all --headless --frames 40 --warmup 5 --width 1280 --height 720 --zoom 28 --png --output-dir scratch/reference-scenes
```

The six scenes are `forest`, `camp`, `village_street`, `interior`, `open_panel`
and `large_save`. Inputs are synthetic prepared QA fixtures using the production
world, simulation, settlement planner, portals and renderer. They do not predict
natural-world appearance or constitute approved final art. Every fixture saves
an actual SQLite checkpoint before measurement and forbids missing-world
creation during measured frames. Reports compare authoritative state before and
after, record save/state size, cache counts, source revision/dirty status,
hardware, seed, versions, viewport, timings and optional PNG hashes. Fixtures use
a temporary directory and never open player saves.

The tool freezes visual time, warms caches, services events each iteration and
uses an unpaced clock. `render.panel` is the reference tool's unpaced panel
measurement; it differs from runtime menu totals. `--headless` explicitly selects
SDL dummy. Omit it to exercise the installed display driver. Escape/window close
interrupts the run. Reports name the driver: dummy throughput is not live FPS,
display latency or a minimum-spec acceptance result. Cold asset loads and region
crossings require separate live measurements. Add `--allocations` for retained
and peak traced memory; tracing adds overhead and is a separate run.

To reproduce the population scaling probe, run these commands sequentially:

```bash
python -u tools/run_ci_check.py --name distant-1000 --timeout 60 -- python -u tools/reference_scenes.py --scene large_save --headless --frames 40 --warmup 5 --distant-npcs 1000 --idle-movement-probe --output-dir scratch/distant-1000
python -u tools/run_ci_check.py --name distant-10000 --timeout 60 -- python -u tools/reference_scenes.py --scene large_save --headless --frames 40 --warmup 5 --distant-npcs 10000 --idle-movement-probe --output-dir scratch/distant-10000
```

The probe invokes the real free-movement update with no directional input and
asserts that authoritative state remains unchanged. It measures actor-query
cost in this controlled scene, not NPC daily schedules. The default large-save
scene has 1,000 distant NPCs; the others have none. CLI bounds cap frames,
viewport, warmup, seed length and distant population.

## Initial baseline (2026-10-13)

[Machine-readable baseline](RUNTIME_REFERENCE_BASELINE.json) records the source
parent and dirty worktree used for these measurements. Linux, AMD EPYC 9V74,
three logical CPUs, Python 3.12.14, pygame-ce 2.5.8 / SDL 2.32.10, dummy driver,
1280×720, zoom 28, seed `worldseed-reference-v1`; five warmup and 40 measured
frames per scene. All six authority comparisons passed. Frame p50/p95/p99/worst:

| Scene | p50 ms | p95 ms | p99 ms | Worst ms |
| --- | ---: | ---: | ---: | ---: |
| Forest | 9.99 | 12.57 | 14.36 | 14.67 |
| Camp | 9.91 | 14.57 | 16.21 | 16.93 |
| Village street | 13.13 | 18.91 | 22.61 | 23.20 |
| Interior | 3.11 | 3.88 | 4.81 | 4.95 |
| Open panel (world frame) | 14.11 | 16.84 | 18.24 | 19.07 |
| Large save | 14.69 | 19.27 | 21.76 | 22.26 |

The open panel adds a separate 1.89 ms median unpaced panel draw. No measured
world frame exceeded 100 ms. This short warm-cache sample does not establish
long-session tail latency.

An exploratory save probe used the same large-save fixtures, five `_save(ctx,
backup=False)` calls followed by one `_save(ctx, backup=True)`, an enabled
profiler and database verification. At 1,000 distant NPCs, median capture was
91.22 ms, JSON 14.92 ms and total 108.99 ms; at 10,000, capture was 945.19 ms,
JSON 110.21 ms and total 1,075.25 ms. Median SQL/commit stayed below 9 ms.
The one explicit backup took 2.17 / 9.72 ms. Six saves and one backup per fixture
are exploratory samples, not storage hardware guarantees. Whole-state capture
is a measured follow-up target alongside local actor queries.

Sequential idle movement probes took 0.559 / 4.501 ms median at
1,000 / 10,000 distant NPCs, with identical scene geometry and unchanged
authority. This establishes an actor-query scaling target for the next unit.
