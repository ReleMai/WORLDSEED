# Branch audit and cleanup — 2026-09-28 UTC

## Cleanup result

Cleanup began from remote `main` at `05266a0c45ccaf1c89ec1707612cf6aa682dfd13`. Immediately before deletion, GitHub reported `main` as the default branch, no open pull requests, and 65 non-main remote branches. All 65 non-main branches were deleted in one Git push; `refs/heads/main` was then the only branch advertised by the canonical remote.

No historical branch was bulk-merged during cleanup. Merged and closed pull-request history remains available on GitHub, and the exact pre-deletion refs were captured and verified in the local repository recovery bundle `.git/branch-cleanup-backup-20260928.bundle`. The bundle is intentionally not a tracked project artifact.

The table below is the pre-cleanup audit record. Its SHAs remain useful recovery identifiers even though the named remote branches no longer exist.

## Pre-cleanup audit

Baseline: `4f00caa9925598cc611a0e7a302625a1ce558983` (`main`). Compared every branch tip with this exact commit. There were 65 branches including main: 1 other tip is fully contained in main; 63 have divergent ancestry. Ahead/behind counts describe commits, not missing features; copied or squashed work can already exist in main.

Only `main` is the active integration baseline under the updated development contract. At audit time, all branches below were parked historical references pending content-specific review. The recorded SHA makes every reviewed tip recoverable from Git object retention, pull-request history, or the cleanup bundle described above.

Do not bulk-merge divergent branches. Recover a specific needed implementation onto current main, test it, and publish it as one work unit. Do not start new per-chat/per-phase branches.

There are no open pull requests at this audit. Workshop expansion PR #67 has been closed and its work is present in main at the baseline above. Do not reapply the old branch merely because its history diverges. The fully contained `dev38-natural-container-art-variants` branch has no open PR and is the only ancestry-proven cleanup candidate.

| Branch | Tip SHA | Ahead of main | Behind main | Disposition |
| --- | --- | ---: | ---: | --- |
| `biome-atlas-20260923` | `37fc2cb87fa665259892278f541c24c31cf24190` | 11 | 59 | Parked; preserve pending content review |
| `ci/diagnostics-stall-reporting-20260923` | `b7db3927419433e2da48af3781209d8782e81934` | 1 | 64 | Parked; preserve pending content review |
| `ci-failure-diagnostics` | `460fa01c43e6236241c5b2c5f77e620cf0f94b1c` | 6 | 72 | Parked; preserve pending content review |
| `cleanup/stable-build-20260924` | `b7a28b5a34116f91df74140849967fa7c6f6867a` | 7 | 33 | Parked; preserve pending content review |
| `combat-active-defense-phase4` | `9e8330dedd520dcc050b2cd939876beb0d292e9d` | 14 | 49 | Parked; preserve pending content review |
| `combat-animal-tactics-phase5` | `b8790c6908fa46060a9f9f3961293289adcf69ad` | 17 | 48 | Parked; preserve pending content review |
| `combat-hunting-phase1` | `9c0fa2a25b511048511538a0d4c9b13630d71b9b` | 16 | 57 | Parked; preserve pending content review |
| `combat-hunting-phase2` | `460232b7cfc3550ce6f57c4b51cd028e8e55a875` | 17 | 55 | Parked; preserve pending content review |
| `combat-range-overlays` | `ebc2aba33b5851e323ce6f0623acfb00195635ff` | 12 | 53 | Parked; preserve pending content review |
| `combat-shields-arena-projectiles` | `0b40490e9c3e82f8b3085119f95f9feb10b7a0a3` | 27 | 51 | Parked; preserve pending content review |
| `combat-spacing-displacement-phase6` | `1ad196579feb630176ee032d7b3d3c3083180e19` | 15 | 45 | Parked; preserve pending content review |
| `crafting-village-polish-wu18` | `eb76a472f8acb5257c3ae12c8c278aade2a65f91` | 2 | 24 | Parked; preserve pending content review |
| `dev37-floating-interaction-panels` | `289e811d15029db8fb8cf5928af64d8599ea8a55` | 10 | 90 | Parked; preserve pending content review |
| `dev38-natural-container-art` | `12fc2b5ba4e2111ae1d1e8a2e4f4aae7a592afba` | 3 | 73 | Parked; preserve pending content review |
| `dev38-natural-container-art-variants` | `aabe8cbce5fe731fac63f424e58bbeba6ac5988f` | 0 | 80 | Fully contained; eligible for cleanup |
| `dev38-natural-container-png-repair` | `2f044074761ebcaf8344fc6971f9bde27783a0d0` | 3 | 66 | Parked; preserve pending content review |
| `dev38-natural-container-rgba-fix` | `24f871627dbf578d6493c2054f073a45263e94f8` | 1 | 65 | Parked; preserve pending content review |
| `fishing-ecology-20260923` | `f9aa7dfc0b1bad14793b1ff90f8e7ec8c8f5d1aa` | 35 | 58 | Parked; preserve pending content review |
| `hunting-stealth-anatomy-phase7-integrated` | `db098516b94338a738db671705fb413a8f485695` | 21 | 34 | Parked; preserve pending content review |
| `hunting-stealth-anatomy-phase7-rebased` | `336a3e8abd44e310c155f590c0f3286e883d9d59` | 16 | 34 | Parked; preserve pending content review |
| `hunting-stealth-anatomy-phase7` | `917b94088a7ae0f6c7ff9cc72bda2901722bd7c7` | 28 | 37 | Parked; preserve pending content review |
| `hunting-stealth-evidence-anatomy-phase7` | `652f7e06b49fbe7ddeaad782b103f3fa8211ebb2` | 46 | 44 | Parked; preserve pending content review |
| `item-atlas-cleanup-20260923` | `21352e749837a88d3fea8c7217187180afb487de` | 12 | 61 | Parked; preserve pending content review |
| `item-taxonomy-refine-20260923` | `f66dfce4498e3084164dc16ad74e6a3de4298f80` | 11 | 60 | Parked; preserve pending content review |
| `living-world-systems-wu13` | `dbc6aaba8b2a645cc35186b19251a0c9ff8ad30e` | 1 | 32 | Parked; preserve pending content review |
| `living-world-systems-wu14` | `5e940bd8ade636e31a7289ca3512f1a8d098a06d` | 2 | 31 | Parked; preserve pending content review |
| `living-world-systems-wu15` | `7da8ea444845113af655ef50f08a03fcdd0ddc70` | 1 | 30 | Parked; preserve pending content review |
| `living-world-systems-wu16` | `e2b7295df792dea89ef99159609bb7c08256efb4` | 1 | 29 | Parked; preserve pending content review |
| `living-world-systems-wu17-household-resilience` | `6fa0764ef4eca4a2cc82315b65430f17adec3bdd` | 5 | 25 | Parked; preserve pending content review |
| `living-world-systems-wu17` | `71fa2ad078cdf54ac8c46c98026b87107825b5c4` | 1 | 28 | Parked; preserve pending content review |
| `living-world-systems-wu18` | `a3daba495a3a730f549da57a5ba6fcc0bad23834` | 5 | 27 | Parked; preserve pending content review |
| `living-world-systems-wu19` | `7efb25d96c885abcfb1ff6e0abdf40abda82900b` | 1 | 26 | Parked; preserve pending content review |
| `phase4-activities-wu2` | `8386051540c6cb3d135794b3b8cae1346c2d3fd1` | 13 | 13 | Parked; preserve pending content review |
| `phase4-living-populations-wu1` | `2b64b949c8ed4cc376a1e4638fc50fe899facf4e` | 10 | 14 | Parked; preserve pending content review |
| `phase4-miners-wu3` | `7f83dd51d3c06e845e26cfc197e96e4e8a688048` | 21 | 12 | Parked; preserve pending content review |
| `phase4-profession-yards-roads-wu5` | `f031d90245d17e2dd7b7720579ad933188ca17b1` | 14 | 10 | Parked; preserve pending content review |
| `phase4-professions-wu4` | `a12169e5c2f735f805d54b921c7f80742d346974` | 16 | 11 | Parked; preserve pending content review |
| `phase4-workshop-expansion-wu6` | `92c4afdee42d06ffea333d7f2eee59dc91c92145` | 30 | 9 | Parked; preserve pending content review |
| `settlement-art-door-polish-wu20` | `76a9de6537dca3ed54cd5686b2e64aeb77c81bb4` | 3 | 20 | Parked; preserve pending content review |
| `settlement-autotile-door-polish-wu19` | `815e4042783c82f51e9109660e9ec85950b5c9f1` | 3 | 20 | Parked; preserve pending content review |
| `sync-wu23` | `b5ec3f883b2fa4eecc0bddd3c4dc99d5170f67b7` | 3 | 17 | Parked; preserve pending content review |
| `village-anchor-rootfix` | `c7789d429d538a03d61870fd2e594ef4234c4d0e` | 3 | 22 | Parked; preserve pending content review |
| `village-start-load-hotfix` | `7a7692f348326bc07d0f5e0eec3a0d9b20d4c29c` | 1 | 23 | Parked; preserve pending content review |
| `village-visuals-hotfix` | `81842500647345a1728720748917a149722a6907` | 2 | 21 | Parked; preserve pending content review |
| `work/building-stealth-vision` | `c057a46cb33de7765f40871729c63affc9dcb88d` | 18 | 37 | Parked; preserve pending content review |
| `work/civic-economy-social-foundation` | `cc8a63c686ebc2e72d143353fb8caa7225f9c52b` | 15 | 40 | Parked; preserve pending content review |
| `work/economy-routines-transactions` | `24d206a7fa3a4784c8b615bec3a2544e73d698f7` | 16 | 39 | Parked; preserve pending content review |
| `work/grand-regional-civ-wu22` | `575b8b4c74baabe95e379276e4b1bb198b19e18d` | 7 | 17 | Parked; preserve pending content review |
| `work/physical-property-security` | `f6863a48eb2039003be4242f9e5a676299d7e3b2` | 18 | 35 | Parked; preserve pending content review |
| `work/physical-property-theft-inspect` | `39c86457315e4989933d72635db7f743c15fe5e5` | 17 | 38 | Parked; preserve pending content review |
| `work/property-storage-casing-suspicion` | `62f79e6f55c21f66fd34db65680deb0878c6c47a` | 19 | 36 | Parked; preserve pending content review |
| `work/regional-civilization-phase1` | `b906fcb3f5510b1d3bcd7b61483322e89b7e217f` | 35 | 17 | Parked; preserve pending content review |
| `work/regional-civilization-phase2` | `eb7884738631627f1bc68f50aef3860df6275a43` | 27 | 16 | Parked; preserve pending content review |
| `work/regional-civilization-phase3` | `2e4ba839cb43d6a42aa03c1aa694a631e0bcf532` | 27 | 15 | Parked; preserve pending content review |
| `work/settlement-atlas-detail-ui` | `729c7e24814144f31b22e66b3480e4482586a6ff` | 9 | 41 | Parked; preserve pending content review |
| `work/settlement-building-generation` | `c34fb6ba273be619effbd245cd1146970749473f` | 1 | 45 | Parked; preserve pending content review |
| `work/settlement-buildings` | `20cda576eaa1322eea53a74911b474ee80836212` | 4 | 44 | Parked; preserve pending content review |
| `work/settlement-generation-foundation` | `c4cdaa86fe7d37a8b581933e3555e126430f0582` | 1 | 47 | Parked; preserve pending content review |
| `work/settlement-local-materialization` | `89ed87bded8c1c5f80933e18cb3cf8023e2b84b5` | 8 | 43 | Parked; preserve pending content review |
| `work/settlement-npc-bindings` | `21dba53a4f1187922e4ca48564a0e6de96c7db1e` | 9 | 42 | Parked; preserve pending content review |
| `work/settlement-skeleton-generation` | `3dd36a5390e6f6f3444db18f124fb81796df67df` | 4 | 46 | Parked; preserve pending content review |
| `work/wu21-settlement-art-clearance` | `57952f9a486eb94d54f59ef9bf92c5868268ff08` | 12 | 19 | Parked; preserve pending content review |
| `wu7-village-stability-debug-ux` | `38ee6912fa88ce3ce5bd34b14e2bb7dd40286d01` | 21 | 0 | Parked; preserve pending content review |
| `wu22-regional-civilization-foundation` | `3006657469c0980c985b802c9c051c509fa907d7` | 24 | 17 | Parked; preserve pending content review |
