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
