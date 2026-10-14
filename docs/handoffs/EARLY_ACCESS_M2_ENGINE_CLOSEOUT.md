# WORLDSEED M2 — measured engine implementation closeout

Code baseline: [ab3f035](https://github.com/ReleMai/WORLDSEED/commit/ab3f03530dac9fdac0e66ff4a30d18a9f56bea0e). Measurements from prepared synthetic QA scenes only; this is **not** a release acceptance certificate.

## Completed implementation

- Authoritative transient spatial locators for NPCs, creatures and every tracked exterior collection: structures, containers, crops, fires, fluids, ground piles, carcasses, animal signs and animal homes. Production rendering does not scan global populations or rebuild their locators.
- Compact exact discovery persistence. No RNG, worldgen or save-schema rewrite.
- Save capture of detached NPC rows optimized by skipping generic per-primitive dataclass recursion and redundant row copying; preserves full old JSON payload and failed-save transactional retry.
- Read-only viewport projection cache for static water and wet-ground classification. Animated water/current/weather, terrain edit and visibility changes continue through authoritative game paths.
- Reproducible six-scene 720p/1080p benchmarking and same-run 1,000/10,000 distant-NPC movement and save-capture comparisons.

## Measured synthetic results

Machine: Linux Azure x86_64, Python 3.11.17, four logical CPUs, SDL dummy driver, zoom 28, seed `worldseed-reference-v1`. 40 measured unpaced frames after five warmups. Milliseconds are p95 *frame work* (not input-to-pixel latency).

| Scene | Final 720p p95 | Prior 1080p p95 | Final 1080p p95 | 1080p target |
| --- | ---: | ---: | ---: | --- |
| forest | 10.93 | 35.92 | 32.39 | Above target |
| camp | 10.57 | 37.95 | 29.18 | Above target |
| village street | 15.80 | 46.95 | 36.61 | Above target |
| interior | 4.12 | 6.02 | 5.95 | Within target |
| open panel | 16.00 | 47.63 | 38.29 | Above target |
| large save | 16.46 | 46.95 | 39.23 | Above target |

- 1,024 versus 10,024 NPC movement test: p50 local-query cost increased **8.2%**, within proposed 20% threshold on this runner.
- Detached checkpoint capture: 1,000 NPCs **14.56 ms** revised versus 58.49 ms duplicate-copy comparator; achieves the proposed 50-ms ordinary sample. 10,000 NPCs **198.27 ms** revised versus 695.12 ms comparator; this *does not* achieve 50 ms. Snapshot equality and independent actor/state isolation are regression-tested; these are capture-only times, not complete database commits.
- Six of six prepared 720p scenes had p95 below 16.7 ms. **Only the interior** prepared 1080p scene met the 16.7-ms frame target; the other five did not, although terrain projection caching lowered them from the earlier run. This remains a meaningful high-resolution rendering bottleneck, not a proven hardware defect.
- All prepared scenes reported unchanged simulation authority. No measured 1080p reference frame exceeded 100 ms in these short runs, but that does not establish long-session stall targets.

Machine-readable source: [M2 performance numbers](../development/M2_PERFORMANCE_MEASUREMENTS_2026-10-13.json). Benchmark evidence: [final 720p and 1080p GitHub run](https://github.com/ReleMai/WORLDSEED/actions/runs/38503212708), [prior 1080p control](https://github.com/ReleMai/WORLDSEED/actions/runs/38502850784). Archived GitHub artifacts expire; this condensed report persists.

## Completion versus release acceptance

**M2's scoped engine implementation is complete:** local actor/static spatial lookup, compact discovery, reproducible scene profiling and responsive ordinary checkpoint capture are in place. **Full release-performance acceptance remains open.** The 1080p p95 target is not met on this synthetic runner, very large saves still exceed 50 ms on the gameplay thread, and real Windows input acknowledgment, hardware variation, RAM growth and multi-hour soak remain unmeasured. Do not declare the entire early-access release validation completed.

## Regression verification and handoff

Previously validated [indexing Fast Gate](https://github.com/ReleMai/WORLDSEED/actions/runs/38496327538) and [save capture with Linux geometry gate](https://github.com/ReleMai/WORLDSEED/actions/runs/38497617195) passed. The fast NPC serialization revision [38502501693](https://github.com/ReleMai/WORLDSEED/actions/runs/38502501693) passed all seven Fast Gate jobs. The terrain projection revision [38503212617](https://github.com/ReleMai/WORLDSEED/actions/runs/38503212617) **passed all seven jobs** on code commit `ab3f03530dac9fdac0e66ff4a30d18a9f56bea0e` (main smoke, world UI/content, settlement/economy, two NPC simulations, Linux process runner, full headless building geometry audit).

**Next dependency:** reduce 1080p terrain/settlement overlay rendering cost without reducing art quality or bypassing animation; repeat same-machine reference scenes and confirm player-hardware responsiveness, big-checkpoint UX, and exploration soak. Work unit 5 is the shared graphical panels plus complete cabin/rest/recovery gameplay sequence. Preserve one simulation authority and saved geography.

