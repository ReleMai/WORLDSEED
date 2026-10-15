"""M2 alpha-layer compositing probe using actual WORLDSEED weather producers.

The shipping renderer remains unchanged. We layer its original forest/camp/
village frame beneath the *real* fog, cloud and rain passes from EffectStack,
then compare exact software pixels with a separate SDL2 accelerated renderer.
The overlay is deliberately diagnostic: it is not a replay of the final
gameplay frame or a claim that SDL automatically supplies volumetric effects.

Windows native example:
 python -m tools.gpu_layer_compositing_probe --scene forest --width 1920 --height 1080 --frames 120 --output scratch/gpu-layers.json

No user save is loaded, and a dummy SDL driver is never treated as a GPU.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import time

from tools.gpu_reference_scene_probe import (
    MAX_CAMERA_OFFSET, _driver, _stats, capture_real_frames, validate as validate_reference,
)
from worldseed.presentation.atmosphere import EffectFrame, WeatherSample
from worldseed.presentation.gpu_layers import (
    GPUCompositionUnavailable, RenderLayer, SDL2GpuLayerCompositor,
    compose_software, MAX_GPU_LAYER_BYTES,
)
from worldseed.presentation.weather_fx import WeatherFxRenderer


def layers_for_frame(fx, width, height, *, seed, phase, left, top, tile_px,
                     weather):
    frame = EffectFrame(seed.encode("utf-8"), width, height, left, top, tile_px,
                        phase, 720, weather)
    return tuple(RenderLayer(name, surface,
                             # Cache only stable fog images by source identity.
                             # Animated rain/cloud phases are deliberately not
                             # treated as immutable across presentation ticks.
                             cache_key=id(surface) if name == "fog" else None)
                 for name, surface in fx.effects.iter_layers(frame))


def capture_layered_frames(scene, width, height, zoom, camera_dx, camera_dy, *,
                           headless=False, seed="worldseed-reference-v1"):
    with _driver(headless):
        bases, reference = capture_real_frames(
            scene, width, height, zoom, camera_dx, camera_dy,
            headless=headless, seed=seed)
        import pygame as pg
        pg.init()
        # The cloud art loader uses convert_alpha(), which requires a display
        # pixel format even though all layering is performed on offscreen
        # Surfaces. Keep this diagnostic display hidden and independent of the
        # production UI window.
        pg.display.set_mode((1, 1), getattr(pg, "HIDDEN", 0))
        try:
            fx = WeatherFxRenderer(pg)
            # Intentionally assert an active mixed-weather scene; the normal
            # prepared fixture can be sunny, which would exercise no overlays.
            weather = WeatherSample(cloud_cover=65, rain=4, fog=40,
                                    storm_intensity=15, wind_dx=150, wind_dy=-40)
            result = []
            for index, base in enumerate(bases):
                layers = layers_for_frame(
                    fx, width, height, seed=seed, phase=1600+index*231,
                    left=256+index*camera_dx, top=256+index*camera_dy,
                    tile_px=zoom, weather=weather)
                expected = base.copy()
                fx.effects.draw(expected, pg.Rect(0, 0, width, height),
                                EffectFrame(seed.encode("utf-8"), width, height,
                                            256+index*camera_dx, 256+index*camera_dy,
                                            zoom, 1600+index*231, 720, weather))
                composed = compose_software(base, layers)
                if pg.image.tobytes(expected, "RGB") != pg.image.tobytes(composed, "RGB"):
                    raise AssertionError("Layer compositor differs from the original weather paint order")
                result.append((base, layers, expected))
            return result, {
                "source": reference,
                "effect_names": [[layer.name for layer in layers] for _, layers, _ in result],
                "software_parity": True,
                "weather": {"cloud_cover": 65, "rain": 4, "fog": 40, "storm_intensity": 15},
                "expected_sha256": [
                    hashlib.sha256(pg.image.tobytes(expected, "RGB")).hexdigest()
                    for _, _, expected in result
                ],
            }
        finally:
            pg.quit()


def run_probe(*, scene="forest", width=1280, height=720, zoom=28,
              frames=120, camera_dx=1, camera_dy=0,
              software_only=False, headless=False, seed="worldseed-reference-v1"):
    validate_reference(scene, width, height, zoom, frames, camera_dx, camera_dy)
    if headless and not software_only:
        raise ValueError("SDL dummy cannot demonstrate accelerated GPU layering")
    # Prevent a source scene plus 16 full-screen overlays from violating
    # the frame budget before allocating or generating layers.
    if width * height * 4 * 6 > MAX_GPU_LAYER_BYTES:
        raise ValueError("Reference + mixed weather layers exceed 192 MiB at this resolution")
    with _driver(headless):
        frames_data, source = capture_layered_frames(
            scene, width, height, zoom, camera_dx, camera_dy,
            headless=headless, seed=seed)
        import pygame as pg
        pg.init()
        renderer = window = compositor = None
        try:
            cpu_ms = []
            for index in range(frames):
                base, layers, _ = frames_data[index % 2]
                start = time.perf_counter()
                compose_software(base, layers)
                cpu_ms.append((time.perf_counter() - start)*1000)
            result = {
                "kind": "worldseed-m2-native-layer-compositing-experiment",
                "scene": scene, "resolution": [width, height],
                "frames": frames, "software_composite": _stats(cpu_ms),
                "source": source, "gpu_composite": None,
                "gpu_error": None, "readback_parity": None,
                "texture_uploads": None, "texture_reuses": None,
                "gpu_cache_bytes": None, "production_renderer_unchanged": True,
                "renderer_replacement": False, "volumetric_fog": False,
                "hardware_certified": False, "not_gameplay_fps": True,
                "os": platform.platform(),
            }
            if software_only:
                return result
            try:
                from pygame._sdl2.video import Window, Renderer, Texture
                window = Window("WORLDSEED M2 layered compositor diagnostic",
                                size=(width, height))
                renderer = Renderer(window, accelerated=1, vsync=False)
                compositor = SDL2GpuLayerCompositor(renderer, pg, Texture)
                # Readback of both phases/camera positions is outside timings.
                checks = []
                for index, (base, layers, expected) in enumerate(frames_data):
                    compositor.compose(base, layers, base_key=("prepared-frame", index))
                    readback = renderer.to_surface()
                    source_rgb = pg.image.tobytes(expected, "RGB")
                    gpu_rgb = pg.image.tobytes(readback, "RGB")
                    checks.append({
                        "exact_rgb": source_rgb == gpu_rgb,
                        "software_sha256": hashlib.sha256(source_rgb).hexdigest(),
                        "gpu_sha256": hashlib.sha256(gpu_rgb).hexdigest(),
                    })
                result["readback_parity"] = checks
                gpu_ms = []
                for frame_no in range(frames):
                    pg.event.pump()
                    index = frame_no % 2
                    base, layers, _ = frames_data[index]
                    start = time.perf_counter()
                    compositor.compose(base, layers, base_key=("prepared-frame", index),
                                       present=True)
                    gpu_ms.append((time.perf_counter() - start)*1000)
                result["gpu_composite"] = _stats(gpu_ms)
                result["texture_uploads"] = compositor.uploads
                result["texture_reuses"] = compositor.reuses
                result["gpu_cache_bytes"] = compositor.cache_bytes
            except (ImportError, GPUCompositionUnavailable, pg.error, OSError, RuntimeError) as exc:
                result["gpu_error"] = type(exc).__name__
            return result
        finally:
            if compositor is not None:
                compositor.close()
            renderer = None
            window = None
            pg.quit()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--scene", choices=("forest", "camp", "village_street",
                                       "interior", "open_panel", "large_save"),
                   default="forest")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    p.add_argument("--zoom", type=int, choices=(20, 28, 36, 48), default=28)
    p.add_argument("--frames", type=int, default=120)
    p.add_argument("--camera-dx", type=int, default=1)
    p.add_argument("--camera-dy", type=int, default=0)
    p.add_argument("--software-only", action="store_true")
    p.add_argument("--headless", action="store_true")
    p.add_argument("--output", type=Path)
    args = p.parse_args(argv)
    try:
        validate_reference(args.scene, args.width, args.height, args.zoom,
                           args.frames, args.camera_dx, args.camera_dy)
        if args.headless and not args.software_only:
            raise ValueError("--headless requires --software-only")
        report = run_probe(scene=args.scene, width=args.width, height=args.height,
                           zoom=args.zoom, frames=args.frames,
                           camera_dx=args.camera_dx, camera_dy=args.camera_dy,
                           software_only=args.software_only, headless=args.headless)
    except ValueError as exc:
        p.error(str(exc))
    output = json.dumps(report, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    print(output, end="")
    return 0 if args.software_only or report["gpu_composite"] is not None else 3


if __name__ == "__main__":
    raise SystemExit(main())
