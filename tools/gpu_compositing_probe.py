"""Opt-in M2 SDL2 hardware compositing benchmark, separate from game renderer.

Usage on a real Windows/Linux desktop (not SDL dummy):
  python -m tools.gpu_compositing_probe --width 1920 --height 1080 --frames 120

Reports synthetic CPU Surface.blit vs requested SDL2-accelerated Renderer with
cached source textures. Does not measure game FPS or certify alpha/pixel parity.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform
import time


def percentile(samples: list[float], pct: float) -> float | None:
    if not samples:
        return None
    values = sorted(samples)
    at = (len(values) - 1) * pct / 100
    left = int(at)
    return round(values[left] + (values[min(left + 1, len(values) - 1)] - values[left]) * (at - left), 3)


def estimate_texture_bytes(width: int, height: int, phases: int = 3) -> int:
    return width * height * 4 * (2 + phases)


def validate(width: int, height: int, frames: int) -> None:
    if not 640 <= width <= 3840 or not 480 <= height <= 2160:
        raise ValueError('resolution out of bounds')
    if not 10 <= frames <= 600:
        raise ValueError('sample count out of bounds')
    if estimate_texture_bytes(width, height) > 192 * 1048576:
        raise ValueError('more than 192 MiB of source textures')


def _layers(pg, w: int, h: int):
    base = pg.Surface((w, h))
    base.fill((32, 49, 40))
    for x in range(0, w, 60):
        pg.draw.line(base, (48, 65, 50), (x, 0), (x, h), 2)
    fog = pg.Surface((w, h), pg.SRCALPHA)
    fog.fill((15, 21, 27, 55))
    result = [base, fog]
    for phase in range(3):
        sky = pg.Surface((w, h), pg.SRCALPHA)
        for x in range(-160, w + 160, 350):
            pg.draw.ellipse(sky, (140, 150, 160, 52),
                            (x + phase * 17, h // 6, 270, 110))
        for x in range(phase * 12, w, 180):
            pg.draw.line(sky, (150, 177, 210, 90),
                         (x, h // 3), (x - 8, h // 3 + 75), 2)
        result.append(sky)
    return result


def _stats(samples: list[float]) -> dict:
    return {'samples': len(samples), 'p50_ms': percentile(samples, 50),
            'p95_ms': percentile(samples, 95), 'p99_ms': percentile(samples, 99),
            'worst_ms': round(max(samples), 3)}


def benchmark(width: int, height: int, frames: int) -> dict:
    import pygame as pg
    from pygame._sdl2.video import Renderer, Texture, Window

    pg.init()
    window = None
    renderer = None
    textures = []
    try:
        start = time.perf_counter()
        layers = _layers(pg, width, height)
        prepared_ms = round(1000 * (time.perf_counter() - start), 3)
        canvas = pg.Surface((width, height))
        cpu = []
        for index in range(frames):
            start = time.perf_counter()
            canvas.blit(layers[0], (0, 0))
            canvas.blit(layers[1], (0, 0))
            canvas.blit(layers[2 + index % 3], (0, 0))
            cpu.append(1000 * (time.perf_counter() - start))
        report = {'software': _stats(cpu), 'hardware': None,
                  'hardware_error': None, 'source_prepare_ms': prepared_ms,
                  'texture_upload_ms': None, 'pixel_parity_tested': False}
        try:
            window = Window('WORLDSEED compositor experiment', size=(width, height))
            renderer = Renderer(window, accelerated=1, vsync=False)
            start = time.perf_counter()
            textures = [Texture.from_surface(renderer, surface) for surface in layers]
            for texture in textures[1:]:
                texture.blend_mode = pg.BLENDMODE_BLEND
            report['texture_upload_ms'] = round(1000 * (time.perf_counter() - start), 3)
            gpu = []
            for index in range(frames):
                pg.event.pump()
                start = time.perf_counter()
                renderer.clear()
                textures[0].draw()
                textures[1].draw()
                textures[2 + index % 3].draw()
                renderer.present()
                gpu.append(1000 * (time.perf_counter() - start))
            report['hardware'] = _stats(gpu)
        except (pg.error, RuntimeError, OSError) as exc:
            report['hardware_error'] = f'{type(exc).__name__}: {exc}'
        return report
    finally:
        textures.clear()
        renderer = None
        window = None
        pg.quit()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--width', type=int, default=1280)
    parser.add_argument('--height', type=int, default=720)
    parser.add_argument('--frames', type=int, default=120)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--dry-run', action='store_true')
    options = parser.parse_args(argv)
    try:
        validate(options.width, options.height, options.frames)
    except ValueError as exc:
        parser.error(str(exc))
    report = {'kind': 'isolated-sdl2-compositing-probe',
              'resolution': [options.width, options.height],
              'frames': options.frames, 'os': platform.platform(),
              'requested_video_driver': os.environ.get('SDL_VIDEODRIVER'),
              'estimated_texture_bytes': estimate_texture_bytes(options.width, options.height),
              'not_gameplay_fps_or_hardware_certification': True}
    if not options.dry_run:
        report.update(benchmark(options.width, options.height, options.frames))
    rendered = json.dumps(report, indent=2, sort_keys=True) + '\n'
    if options.output:
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(rendered, encoding='utf-8')
    print(rendered, end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
