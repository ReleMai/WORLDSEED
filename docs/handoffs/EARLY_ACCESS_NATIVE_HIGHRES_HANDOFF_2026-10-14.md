# WORLDSEED native high-resolution performance handoff — 2026-10-14

**Latest implementation:** [`03d3c3a`](https://github.com/ReleMai/WORLDSEED/commit/03d3c3adbf4a3e5ac1ffe5c8f8c8e0b1151603a5) on main. This work extends the M2 benchmark and renderer improvements documented in [M2 engine closeout](EARLY_ACCESS_M2_ENGINE_CLOSEOUT.md), without changing authoritative simulation, world generation, save schema or art assets.

## Implemented and bounded

- `da4948b`: exact-visibility/revision cached memory-fog presentation and SDL alpha-blit batching for wet ground.
- `e5881e5`: exact current-LOS cached resource viewport projection with resource-revision invalidation.
- `935cf33` + `516ee8f`: one bounded immutable settlement cell and building-shell viewport projection by physicalization revision, with lifecycle regressions.
- `e2423d2`: invalidate exterior fixture projections on interior-state clearing, even when there are no replacement fixtures; add native 1440p and 4K six-scene benchmark jobs.
- `03d3c3a`: cache finished cloud composites by 33-ms animation phase and all weather, sun, viewport and camera parameters, with a fixed 64-MiB cap; reuse unchanged fog frame; avoid full viewport weather restoration snapshots when no idle animated weather or lighting fade needs them. New pixel and lifecycle regressions verify distinct animation phases still render independently.

These are read-only derived presentation caches, not a second game or world state. Do not bypass simulation RNG, player-visible fog rules or world-seed fidelity for performance.

## Latest software-headless native-resolution evidence

Source: [prior M2 run 38508613462](https://github.com/ReleMai/WORLDSEED/actions/runs/38508613462) against `e2423d2` and [atmosphere-cache run 38509407266](https://github.com/ReleMai/WORLDSEED/actions/runs/38509407266) against `03d3c3a`. GitHub-hosted Linux x86_64, Python 3.11, pygame-ce SDL dummy software renderer, 30 measured frames, five warmups, identical prepared scenes and seeds per resolution. Native 1440p uses 36-pixel tiles and 4K uses 48-pixel tiles. Values are milliseconds, **render.frame p95**, not frame pacing or input latency. Hardware variance across runners remains possible.

| Scene | 1440p before | 1440p after | 4K before | 4K after |
| --- | ---: | ---: | ---: | ---: |
| Forest | 26.39 | 23.12 | 61.81 | 46.32 |
| Camp | 26.95 | 22.41 | 59.97 | 45.85 |
| Village street | 30.79 | 27.32 | 67.88 | 53.41 |
| Interior | 12.25 | 11.64 | 26.22 | 25.16 |
| Open panel | 33.56 | 28.04 | 71.44 | 54.90 |
| Large save | 28.91 | 28.12 | 69.63 | 53.58 |

**All six pixel SHA256 outputs matched exactly** at 1440p and 4K before versus after. Each reference scene reported unchanged authoritative simulation state. At 4K the weather/light effect stage dropped from roughly 25–30 ms p50 to 14–16 ms in outdoor scenes. The atmospheric-caching gain is primarily for unchanged 33-ms presentation phases; the current reference tool freezes its visual clock, so no claim is made for uninterrupted animated 4K 60 fps.

1080p synthetic results also improved relative to the original M2 baseline and achieved all six p95 <=16.7 ms in one run (`935cf33`), but **the latest repeat on `03d3c3a` has p95 17.92 ms for village, 18.43 ms for open panel and 16.97 ms for large save**. The goal is not consistently met across different hosted-runner loads. Do not declare 1080p reliably certified on player hardware based on a single faster run.

## Acceptance state

- Completed: deterministic spatial-index, discovery/save capture, stable viewport/resource/settlement caches, bounded weather compositing, synthetic reference profilers, pure read-only presentation and source-level regressions.
- **Open:** 1440p/4K **16.7-ms p95** goal. All outdoor higher-resolution scenes remain above target on the CPU headless runner. No long-session 4K active-animated-weather, Windows GPU, input-to-pixel, continuous camera crossing, or real minimum-hardware load test has yet passed. The 10,000-NPC detached capture also exceeds 50 ms.
- Do not reduce sprite art resolution or disable rain, cloud, shadows, fog, lighting or shore/water animation just to meet a synthetic benchmark. Do not call M2 public early-access performance certification complete.

## Verification and next safe work unit

- Last complete Fast Gate before the weather change: [38508613423](https://github.com/ReleMai/WORLDSEED/actions/runs/38508613423), all seven jobs green.
- Weather-cloud code full seven-job gate: [38509407262](https://github.com/ReleMai/WORLDSEED/actions/runs/38509407262). **Check exact conclusion; still running when this file was first written.** 720p/1080p and native 1440p/4K benchmark [38509407266](https://github.com/ReleMai/WORLDSEED/actions/runs/38509407266) passed all three jobs.

Next technical priority is a **GPU-backed compositing prototype**, not more global simulation indexing. Benchmark fast-sky and fully animated weather phases separately; establish output/pixel parity, camera motion, viewport/zoom/resize, weather phase and light transition tests. Compare SDL software fallback and hardware renderer for 1080p/1440p/4K on actual Windows hardware. Only then migrate costly full-screen layers (lighting, fog, clouds, rain, wet ground and map backgrounds) incrementally with a clean software fallback and bounded texture caches. Preserve deterministic art/seed and transactional saves. Keep each work session resumable, validate before syncing code, and do not silently relax native rendering targets.

## Follow-up — prepared real-scene SDL2 GPU presentation bridge

M2 now includes an opt-in `tools.gpu_reference_scene_probe` using exact rendered
screens from the existing six prepared WORLDSEED fixtures, not just the synthetic
base/fog/cloud textures in the earlier probe. It measures software frame copy,
source-to-GPU upload and cached GPU present independently. A camera-displaced
second frame and changed visual clock phase are captured without retaining any
authoritative state change; optional GPU readback reports exact RGB parity.
Normal production pygame-ce presentation, save durability, and all reference
pixels remain unchanged. No first-party GPU speedup claim is made without actual
Windows hardware measurements. See `docs/development/GPU_COMPOSITING_EXPERIMENT.md`.
