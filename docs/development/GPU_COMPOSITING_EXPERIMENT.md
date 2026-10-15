# WORLDSEED M2 native compositing experiment

Status: **opt-in diagnostic only**. No engine renderer replacement or released GPU claims.

The preceding [October 14 handoff](../handoffs/EARLY_ACCESS_NATIVE_HIGHRES_HANDOFF_2026-10-14.md) reports that software-headless 1440p/4K outdoor render p95 values remain above the 16.7-ms target. Live Windows input latency, full animated-weather parity, multi-hour exploration soak and large 10,000-NPC checkpoint capture remain unverified. The existing pygame Surface renderer remains the supported backend.

## Native desktop commands

Run in a real desktop environment with pygame-ce installed, without setting SDL_VIDEODRIVER=dummy:

    python -m tools.gpu_compositing_probe --width 1920 --height 1080 --frames 120 --output scratch/gpu-1080p.json
    python -m tools.gpu_compositing_probe --width 2560 --height 1440 --frames 120 --output scratch/gpu-1440p.json
    python -m tools.gpu_compositing_probe --width 3840 --height 2160 --frames 120 --output scratch/gpu-4k.json

The probe compares cached synthetic terrain, translucent fog and three animated rain/cloud phases composed by software Surface.blit versus a separately created SDL2 Renderer requested with accelerated=1. Texture-upload and source-preparation times are separated from unpaced frame samples; source textures are reused across frames, with a 192-MiB cap. A driver initialization failure is reported, not silently counted as accelerated.

Results do not prove GPU speedups in real WORLDSEED scenes. The probe neither verifies exact output pixels nor handles resizing/device resets; those are explicitly future acceptance gates. Do not migrate live terrain, weather or UI without reference-image parity, moving-camera tests, actual Windows GPU-driver identification and comparisons to the current production Surface fallback.

The parallel M3 work begins at worldseed/ui/presentation_style.py: an immutable theme, independent palette instances, and a reusable menu-frame painter. The component initially preserves the established menu pixels and input semantics. Next: approve forest/camp/village/interior screenshots and gradually share spacing, text hierarchy, focus states and draggable panel primitives across crafting, inventory, health, dialogue and building UI.

## October 14 — M2 real-scene GPU presentation bridge (experimental)

The separate `tools/gpu_reference_scene_probe.py` takes **two complete
software-rendered frames from actual WORLDSEED prepared reference fixtures**,
including an optional one-cell camera displacement and a +231 ms animation
clock phase. It verifies the authoritative fixture fingerprint remains identical
after frame capture. Those exact frames are then used for:
- CPU framebuffer copy throughput (no generation or GPU work included);
- SDL2 **accelerated=1** texture uploads of both images, timed separately;
- cached GPU texture draws/present over a pacing-free frame sample;
- optional single-readback exact RGB digest parity for each real image;
- bounded texture allocation (two complete RGBA frames, <=192 MiB) and explicit
  driver / parity / initialization errors.

Run with source checkout, pygame-ce, a real Windows desktop GPU driver:

    python -m tools.gpu_reference_scene_probe --scene forest --width 1920 --height 1080 --zoom 36 --frames 120 --output scratch/forest-1080p.json
    python -m tools.gpu_reference_scene_probe --scene village_street --width 2560 --height 1440 --zoom 36 --frames 120 --camera-dx 1 --output scratch/village-1440p.json
    python -m tools.gpu_reference_scene_probe --scene camp --width 3840 --height 2160 --zoom 48 --frames 120 --output scratch/camp-4k.json

A source-level diagnostic on CI without GPU can use:

    python -m tools.gpu_reference_scene_probe --software-only --headless --scene forest --width 640 --height 480 --zoom 28 --frames 10

**Scope boundary:** This bridge tests full-frame CPU-to-GPU upload and accelerated
presentation from **real game scenes**. It **does not** yet composite separate
weather/lighting/terrain/UI alpha layers on the GPU, integrate the SDL2 renderer
into the running game, or establish a speedup over gameplay software rendering.
A fresh complete texture upload every render frame can lose rather than gain
performance; static vs animated upload cost must be measured before architecture
changes. Pixel hash mismatches are reported, never quietly accepted. No changes
to the supported software fallback, simulation or player saves.

The next gate is separately capturing/compositing explicit
terrain/weather/light/alpha passes, with readback parity across camera, zoom,
resize, rain and night transitions. Production migration stays blocked until
those tests succeed on a native desktop GPU.

## October 14 — layered GPU alpha compositor work unit

This follow-up introduces:

- `worldseed/presentation/gpu_layers.py`: explicit, bounded SDL2 layer
  compositing with immutable-surface opt-in texture caching, LRU eviction,
  invalidation on renderer/viewport replacement, and failure reporting.
  `compose_software` is a pure-on-input Surface alpha-blit fallback/reference.
- `worldseed/presentation/atmosphere.py:EffectStack.iter_layers`:
  one shared, ordered lazy producer used by the shipping software draw and
  experimental GPU layer path. The software render order and clip semantics
  remain unchanged.
- `tools/gpu_layer_compositing_probe.py`: real prepared WORLDSEED frames
  used as the background for production fog, cloud and rain effect producers.
  It proves matching software pixels, reports explicit SDL2 readback RGB
  equality/mismatch, and separates software compositing from GPU compositing.
- `tests/test_gpu_layer_compositing.py`: exact software alpha-layer parity,
  camera/animation changes, conservative texture reuse, cache lifecycle,
  input validation and simulated GPU failures. The Fast Gate runs pure
  contracts on Linux and actual pygame reference layers in the Windows job.

This is **not** a production GPU renderer cutover: the actual game still uses
pygame-ce software presentation. The diagnostic GPU window does not own UI
input, navigation, window sizing, sprite batching, player shadows, shadow
occlusion, or a 3D depth field. The scenes are real renderer output with
separately layered diagnostic weather; they are not a byte-for-byte replay of
one captured game screen. A successful SDL2 accelerated Renderer creation
alone is not certification of physical GPU performance. Hardware driver,
readback accuracy, pixel parity across full game scenes, and multi-hour
Windows gameplay remain required acceptance gates.

Feature roadmap, in order: choose a shader-capable presentation API and
GPU-native sprites/terrain batches with cache and resize lifecycle; retain
working software fallback until visual/reference/input/save regression gates
pass. Then implement an explicit sun/moon lighting field, 2D normal/height
maps for objects/tiles, bounded occluder shadow maps, particles and world-space
fog; finally optional bloom/blur/water distortion/terrain blending. True
volumetric raymarching requires a 3D depth/volume approximation beyond plain
SDL2 2D alpha blending and is not part of this initial compositor.
