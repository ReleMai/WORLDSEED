"""M2 opt-in hardware bridge for frames produced by the real WORLDSEED renderer.

This is NOT a production GPU renderer or a claim about game FPS. The reference
fixture renders with the shipping software backend. This tool measures the
upload and GPU presentation costs of *those exact complete frames*, verifies
optional SDL readback parity and reports a safe software baseline. It tests the
transfer boundary before moving individual alpha/weather passes to SDL2.

Example, Windows desktop with a real GPU:
 python -m tools.gpu_reference_scene_probe --scene village_street --width 1920 --height 1080 --zoom 36 --frames 120 --output scratch/gpu-village.json

No player save is opened or modified. SDL dummy is allowed only with
--software-only; a dummy driver must never be counted as accelerated hardware.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

from tools.gpu_compositing_probe import percentile
from tools.reference_scene_fixtures import SCENES, ANIMATION_MILLISECONDS, build_fixture
from tools.reference_scenes import render_fixture, service_events
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.entities.components import Position
from worldseed.ui.pygame_terminal import PygameTerminal

MAX_TEXTURE_BYTES = 192 * 1024 * 1024
MAX_CAMERA_OFFSET = 4


def validate(scene: str, width: int, height: int, zoom: int, frames: int,
             camera_dx: int, camera_dy: int) -> None:
    if scene not in SCENES:
        raise ValueError("Unknown prepared WORLDSEED scene")
    for name, value in (("width", width), ("height", height), ("zoom", zoom),
                        ("frames", frames), ("camera_dx", camera_dx), ("camera_dy", camera_dy)):
        if type(value) is not int:
            raise ValueError(name + " must be an integer")
    if not 640 <= width <= 3840 or not 480 <= height <= 2160:
        raise ValueError("Unsupported reference viewport")
    if zoom not in (20, 28, 36, 48):
        raise ValueError("Unsupported reference zoom")
    if not 10 <= frames <= 600:
        raise ValueError("Frame count must be from 10 to 600")
    if any(abs(v) > MAX_CAMERA_OFFSET for v in (camera_dx, camera_dy)):
        raise ValueError("Camera step exceeds prepared-fixture envelope")
    if texture_budget(width, height) > MAX_TEXTURE_BYTES:
        raise ValueError("Two captured RGB textures exceed 192 MiB")


def texture_budget(width: int, height: int) -> int:
    """Bound two GPU RGBA textures; readback and software copies are separate."""
    return width * height * 4 * 2


def _stats(samples: list[float]) -> dict:
    if not samples:
        return {"samples": 0, "p50_ms": None, "p95_ms": None,
                "p99_ms": None, "worst_ms": None}
    return {"samples": len(samples), "p50_ms": percentile(samples, 50),
            "p95_ms": percentile(samples, 95),
            "p99_ms": percentile(samples, 99),
            "worst_ms": round(max(samples), 3)}


@contextmanager
def _driver(headless):
    previous = {key: os.environ.get(key) for key in ("SDL_VIDEODRIVER", "SDL_AUDIODRIVER")}
    if headless:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ["SDL_AUDIODRIVER"] = "dummy"
    try:
        yield
    finally:
        if headless:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def capture_real_frames(scene, width, height, zoom, camera_dx, camera_dy,
                        *, headless=False, seed="worldseed-reference-v1"):
    """Capture two real software renderer outputs; restore fixture state exactly."""
    if not PygameTerminal.available():
        raise RuntimeError("pygame-ce required")
    with tempfile.TemporaryDirectory(prefix="worldseed-gpu-bridge-") as temporary, _driver(headless):
        registry = ContentRegistry.load(DATA_DIR)
        fixture = build_fixture(scene, registry, Path(temporary),
                                width=width, height=height, zoom=zoom, seed=seed)
        term = None
        try:
            original_hash = fixture.authority_fingerprint()
            term = PygameTerminal(width, height)
            term.enter()
            term._tile_px = zoom
            term._last_mouse = (-1, -1)
            term.clock = SimpleNamespace(tick=lambda *_: 0)
            actor = fixture.sim.entities.get(fixture.sim.player_id, Position)
            original_pos = actor.value
            samples = []
            for index in (0, 1):
                # This is a temporary QA-only camera displacement. The exact
                # authoritative position is restored even if rendering raises.
                try:
                    if index:
                        actor.value = original_pos.moved(camera_dx, camera_dy)
                    ticks = ANIMATION_MILLISECONDS + index * 231
                    with patch.object(term.pg.time, "get_ticks", return_value=ticks):
                        render_fixture(term, fixture)
                    samples.append(term.screen.copy())
                finally:
                    actor.value = original_pos
            restored_hash = fixture.authority_fingerprint()
            if restored_hash != original_hash:
                raise AssertionError("GPU probe modified simulation, discovery or prepared world")
            return samples, {
                "source": "real-worldseed-software-reference-frames",
                "scene": scene, "fixture_version": 1, "seed": seed,
                "authority_unchanged": True,
                "camera_step_cells": [camera_dx, camera_dy],
                "phase_step_ms": 231,
                "zoom": zoom,
                "sdl_driver": term.pg.display.get_driver(),
                "pixel_sha256": [
                    hashlib.sha256(term.pg.image.tobytes(surface, "RGB")).hexdigest()
                    for surface in samples
                ],
            }
        finally:
            if term is not None:
                term.restore()
            fixture.close()


def _comparison(pg, expected, actual):
    """Readback parity is RGB-exact; no alpha normalization or tolerance masking."""
    original = pg.image.tobytes(expected, "RGB")
    observed = pg.image.tobytes(actual, "RGB")
    return {"exact_rgb": original == observed,
            "source_sha256": hashlib.sha256(original).hexdigest(),
            "readback_sha256": hashlib.sha256(observed).hexdigest()}


def benchmark(frames, width, height, *, software_only=False, headless=False,
              scene="forest", zoom=28, camera_dx=1, camera_dy=0, seed="worldseed-reference-v1"):
    """Compare CPU framebuffer copies with cached GPU texture presentation.

    GPU timings exclude fixture generation, upload and readback. Upload timing
    includes two real captured frames; neither is disguised as a steady frame.
    """
    validate(scene, width, height, zoom, frames, camera_dx, camera_dy)
    if headless and not software_only:
        raise ValueError("SDL dummy cannot establish GPU acceleration; use --software-only")
    captured, source = capture_real_frames(scene, width, height, zoom, camera_dx, camera_dy,
                                           headless=headless, seed=seed)
    import pygame as pg
    if not software_only:
        pg.init()
    window = renderer = None
    textures = []
    try:
        software_canvas = pg.Surface((width, height))
        cpu_samples = []
        for index in range(frames):
            start = time.perf_counter()
            software_canvas.blit(captured[index % 2], (0, 0))
            cpu_samples.append((time.perf_counter() - start) * 1000)
        report = {
            "kind": "worldseed-m2-real-scene-gpu-presentation-bridge",
            "hardware_accelerated_requested": not software_only,
            "hardware_confirmed": False,
            "production_renderer_unchanged": True,
            "gpu_compositing_of_individual_alpha_layers": False,
            "not_gameplay_fps_or_60fps_certification": True,
            "source_frames": source,
            "resolution": [width, height],
            "sample_frames": frames,
            "texture_budget_bytes": texture_budget(width, height),
            "software_copy": _stats(cpu_samples),
            "texture_upload_ms": None,
            "gpu_present": None,
            "readback_parity": None,
            "gpu_error": None,
            "pygame": pg.version.ver,
            "sdl_driver": source["sdl_driver"],
            "os": platform.platform(),
        }
        if software_only:
            return report
        try:
            from pygame._sdl2.video import Window, Renderer, Texture
            window = Window("WORLDSEED M2 GPU reference diagnostic", size=(width, height))
            renderer = Renderer(window, accelerated=1, vsync=False)
            # Creating a Renderer with accelerated=1 must either succeed or
            # throw; never reinterpret a software/dummy render as GPU proof.
            report["hardware_confirmed"] = True
            start = time.perf_counter()
            textures = [Texture.from_surface(renderer, surface) for surface in captured]
            report["texture_upload_ms"] = round((time.perf_counter() - start) * 1000, 3)
            # Parity is checked outside the timed loop. GPU pixel formats and
            # color spaces can disagree even on fully opaque inputs; report it.
            try:
                parity = []
                for index, texture in enumerate(textures):
                    renderer.clear()
                    texture.draw()
                    readback = renderer.to_surface()
                    parity.append(_comparison(pg, captured[index], readback))
                report["readback_parity"] = parity
            except (pg.error, RuntimeError, OSError) as exc:
                report["readback_parity"] = {"unavailable": type(exc).__name__}
            gpu_samples = []
            for index in range(frames):
                pg.event.pump()
                start = time.perf_counter()
                renderer.clear()
                textures[index % 2].draw()
                renderer.present()
                gpu_samples.append((time.perf_counter() - start) * 1000)
            report["gpu_present"] = _stats(gpu_samples)
        except (ImportError, pg.error, RuntimeError, OSError) as exc:
            report["hardware_confirmed"] = False
            report["gpu_error"] = type(exc).__name__
        return report
    finally:
        textures.clear()
        renderer = None
        window = None
        if not software_only:
            pg.quit()


def make_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene", choices=SCENES, default="forest")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--zoom", type=int, choices=(20, 28, 36, 48), default=36)
    parser.add_argument("--frames", type=int, default=120)
    parser.add_argument("--camera-dx", type=int, default=1)
    parser.add_argument("--camera-dy", type=int, default=0)
    parser.add_argument("--software-only", action="store_true")
    parser.add_argument("--headless", action="store_true",
                        help="Require --software-only: synthetic reference rendering without a GPU")
    parser.add_argument("--output", type=Path)
    return parser


def main(argv=None):
    parser = make_parser()
    options = parser.parse_args(argv)
    try:
        validate(options.scene, options.width, options.height, options.zoom,
                 options.frames, options.camera_dx, options.camera_dy)
        if options.headless and not options.software_only:
            parser.error("--headless requires --software-only")
    except ValueError as exc:
        parser.error(str(exc))
    result = benchmark(options.frames, options.width, options.height,
                       software_only=options.software_only, headless=options.headless,
                       scene=options.scene, zoom=options.zoom,
                       camera_dx=options.camera_dx, camera_dy=options.camera_dy)
    encoded = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if options.output:
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0 if options.software_only or result["hardware_confirmed"] else 3


if __name__ == "__main__":
    raise SystemExit(main())
