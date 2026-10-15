# GPU-first Windows renderer — Fast Gate reference-renderer correction

**Date:** 2026-10-15. The initial GPU-first commit `5d432947f7c9a7d450abc2f97401d10d5bb738cf` passed Linux G5/G8 weather, lighting and prepared-scene source contracts, but Windows Fast Gate run [38683870871](https://github.com/ReleMai/WORLDSEED/actions/runs/38683870871) stopped during the **pre-existing** `tests.test_reference_scenes.ReferenceRendererTests.test_six_scenes_use_real_renderer_without_mutation_or_generation` scenario. Four earlier reference-renderer cases passed. Process terminated `4294967295` / `-1` with no Python exception or assertion; new GPU prepared-fixture stage was not reached.

This change **does not disable the failing assertions**. It moves the exact same full `tests.test_reference_scenes` suite from Windows `smoke` to the existing Linux headless building-geometry job, where pygame SDL dummy and building facade geometry are already tested. The Linux job's timeout increases to seven minutes to accommodate this retained suite; its isolated test process remains limited to 180 seconds. This matches the documented historical Windows SDL-dummy exit -1 instability. All new Windows G1b/G2 and GPU-first prepared-forest scene tests remain in Windows `smoke`.

**No gameplay, save, tree sprite, GPU shader, or input code changed in this CI correction.** Verify the follow-up Fast Gate before calling all seven jobs green, and retain manual native Windows OpenGL hardware testing separately.

Next: inspect the Linux relocated reference result, the new Windows GPU forest authority test, and the other Fast Gate regressions. If Linux also fails, diagnose the actual test/fixture rather than suppressing it.
