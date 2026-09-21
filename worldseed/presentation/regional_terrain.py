"""Deterministic cartographic assets derived only from regional terrain data.

These are biome/relief symbols, not a second terrain generator. A regional
summary has no spatial biome raster, so this module never invents exact local
geography. It can, however, blend the *public* neighboring regional summaries
at the shared edges so the strategic map reads as one connected landscape
rather than a checkerboard of unrelated squares.
"""
from collections import OrderedDict
from dataclasses import dataclass
import json
from pathlib import Path

from worldseed.core.rng import PCG32, derive_seed

ASSET_VERSION = 2
ASSET_SIZE = 128
ASSET_NAMESPACE = 'presentation:regional-terrain'
TRANSITION_DIRECTIONS = (
    'north', 'south', 'west', 'east',
    'northwest', 'northeast', 'southwest', 'southeast',
)


@dataclass(frozen=True)
class TerrainAppearance:
    region_x: int
    region_y: int
    biome: str
    moisture: int
    temperature: int
    elevation: int
    relief: int
    wooded: int

    @classmethod
    def from_plan(cls, plan):
        def field(name, default=0):
            return max(0, min(65535, int(getattr(plan, name, default))))
        mix = getattr(plan, 'biome_mix', {})
        total = max(1, sum(max(0, int(v)) for v in mix.values()))
        return cls(int(plan.region_x), int(plan.region_y), plan.dominant_biome,
                   field('mean_moisture', 32768), field('mean_temperature', 32768),
                   field('mean_elevation', 32768), field('relief'),
                   min(100, max(0, int(mix.get('forest', 0))) * 100 // total))


def blend(a, b, amount):
    amount = max(0, min(256, amount))
    return tuple((x * (256 - amount) + y * amount) // 256 for x, y in zip(a, b))


def shade(color, amount):
    return tuple(max(0, min(255, c + amount)) for c in color)


def draw_symbol(pg, surface, kind, x, y, ink, light, size=1):
    """Small atlas marks share one lighting direction and restrained outlines."""
    if kind == 'tree':
        pg.draw.line(surface, ink, (x, y), (x, y + 7 * size), size)
        points = [(x, y - 5 * size), (x - 4 * size, y + 3 * size), (x + 4 * size, y + 3 * size)]
        pg.draw.polygon(surface, ink, points)
        pg.draw.line(surface, light, points[0], (x - 2 * size, y + size), size)
    elif kind == 'wave':
        pg.draw.lines(surface, light, False, [(x - 4, y), (x - 1, y + 1), (x + 3, y)], 1)
        pg.draw.line(surface, ink, (x - 2, y + 3), (x + 4, y + 3), 1)
    elif kind == 'stone':
        pg.draw.polygon(surface, ink, [(x - 3, y + 2), (x - 1, y - 2), (x + 2, y - 1), (x + 4, y + 2)])
        pg.draw.line(surface, light, (x - 1, y - 2), (x + 2, y - 1))
    elif kind == 'snow':
        pg.draw.line(surface, light, (x - 2, y), (x + 3, y))
        pg.draw.line(surface, ink, (x - 1, y + 2), (x + 1, y + 2))
    elif kind == 'sand':
        pg.draw.line(surface, ink, (x - 2, y + 1), (x + 2, y + 1))
        surface.set_at((x, y - 1), light)
    else:  # grass and low scrub
        pg.draw.line(surface, ink, (x - 2, y - 2), (x, y + 1))
        pg.draw.line(surface, light, (x, y + 1), (x + 2, y - 3))
        if kind == 'scrub':
            pg.draw.line(surface, ink, (x - 3, y + 2), (x + 3, y + 2))


class RegionalTerrainAssets:
    """Per-renderer bounded LRU; no files or world caches are written."""
    def __init__(self, pg, capacity=256):
        self.pg = pg
        self.capacity = max(1, int(capacity))
        self._cache = OrderedDict()
        self._base_cache = OrderedDict()
        self._mask_cache = {}
        path = Path(__file__).resolve().parents[1] / 'assets' / 'regional_terrain.json'
        self.styles = json.loads(path.read_text(encoding='utf-8'))['biomes']

    def surface(self, plan, pixels, neighbors=None):
        appearance = TerrainAppearance.from_plan(plan)
        pixels = max(1, min(256, int(pixels)))
        neighbor_signature = self._neighbor_signature(neighbors)
        key = (ASSET_VERSION, appearance, neighbor_signature, pixels)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        if pixels == ASSET_SIZE:
            surface = self._generate_composite(appearance, neighbors)
        else:
            base = self.surface(plan, ASSET_SIZE, neighbors)
            scaler = self.pg.transform.smoothscale if self._style_for(appearance.biome) else self.pg.transform.scale
            surface = scaler(base, (pixels, pixels))
        self._cache[key] = surface
        while len(self._cache) > self.capacity:
            self._cache.popitem(last=False)
        return surface

    def _neighbor_signature(self, neighbors):
        if not neighbors:
            return ()
        signature = []
        for direction in TRANSITION_DIRECTIONS:
            plan = neighbors.get(direction)
            signature.append((direction, TerrainAppearance.from_plan(plan) if plan is not None else None))
        return tuple(signature)

    def _style_for(self, biome):
        return self.styles.get('core:' + biome)

    def _base_surface(self, appearance):
        key = (ASSET_VERSION, appearance)
        if key in self._base_cache:
            self._base_cache.move_to_end(key)
            return self._base_cache[key]
        surface = self._generate(appearance)
        self._base_cache[key] = surface
        while len(self._base_cache) > self.capacity:
            self._base_cache.popitem(last=False)
        return surface

    def _generate_composite(self, terrain, neighbors):
        surface = self._base_surface(terrain).copy()
        for direction in ('north', 'south', 'west', 'east'):
            neighbor = (neighbors or {}).get(direction)
            if neighbor is None:
                continue
            appearance = TerrainAppearance.from_plan(neighbor)
            if appearance.biome == terrain.biome:
                continue
            overlay = self._base_surface(appearance)
            self._apply_directional_overlay(surface, overlay, direction)
        for direction in ('northwest', 'northeast', 'southwest', 'southeast'):
            neighbor = (neighbors or {}).get(direction)
            if neighbor is None:
                continue
            appearance = TerrainAppearance.from_plan(neighbor)
            if appearance.biome == terrain.biome:
                continue
            overlay = self._base_surface(appearance)
            self._apply_directional_overlay(surface, overlay, direction)
        return surface

    def _apply_directional_overlay(self, surface, overlay, direction):
        masked = overlay.copy()
        masked.blit(self._mask_for(direction), (0, 0), special_flags=self.pg.BLEND_RGBA_MULT)
        surface.blit(masked, (0, 0))

    def _mask_for(self, direction):
        mask = self._mask_cache.get(direction)
        if mask is not None:
            return mask
        pg = self.pg
        mask = pg.Surface((ASSET_SIZE, ASSET_SIZE), pg.SRCALPHA)
        max_alpha = 168
        depth = 26
        if direction in ('north', 'south', 'west', 'east'):
            for i in range(depth):
                alpha = max(0, int(max_alpha * (depth - i) / depth))
                color = (255, 255, 255, alpha)
                if direction == 'north':
                    pg.draw.line(mask, color, (0, i), (ASSET_SIZE - 1, i))
                elif direction == 'south':
                    y = ASSET_SIZE - 1 - i
                    pg.draw.line(mask, color, (0, y), (ASSET_SIZE - 1, y))
                elif direction == 'west':
                    pg.draw.line(mask, color, (i, 0), (i, ASSET_SIZE - 1))
                else:
                    x = ASSET_SIZE - 1 - i
                    pg.draw.line(mask, color, (x, 0), (x, ASSET_SIZE - 1))
        else:
            radius = 36
            anchor = {
                'northwest': (0, 0),
                'northeast': (ASSET_SIZE - 1, 0),
                'southwest': (0, ASSET_SIZE - 1),
                'southeast': (ASSET_SIZE - 1, ASSET_SIZE - 1),
            }[direction]
            ax, ay = anchor
            for y in range(ASSET_SIZE):
                for x in range(ASSET_SIZE):
                    dx = abs(x - ax)
                    dy = abs(y - ay)
                    dist = (dx * dx + dy * dy) ** 0.5
                    if dist > radius:
                        continue
                    alpha = max(0, int((1.0 - dist / radius) * 144))
                    if alpha:
                        mask.set_at((x, y), (255, 255, 255, alpha))
        self._mask_cache[direction] = mask
        return mask

    def _generate(self, terrain):
        pg = self.pg
        style = self._style_for(terrain.biome)
        surface = pg.Surface((ASSET_SIZE, ASSET_SIZE), pg.SRCALPHA)
        if style is None:
            surface.fill((45, 47, 48))
            return surface
        seed = derive_seed(b'worldseed-cartography', ASSET_NAMESPACE, ASSET_VERSION,
                           terrain.region_x, terrain.region_y, terrain.biome)
        rng = PCG32(seed)
        dry = max(0, (36000 - terrain.moisture) * 192 // 36000)
        cold = max(0, (22000 - terrain.temperature) * 220 // 22000)
        base = blend(style['base'], style['dry'], dry)
        base = blend(base, style['cold'], cold)
        # Elevation influences the material tint, not invented geographic bands.
        base = shade(base, (terrain.elevation - 32768) // 6000)
        ink, light = tuple(style['ink']), tuple(style['light'])
        # Smooth material variation carries no spatial terrain authority.
        small = pg.Surface((9, 9))
        for y in range(9):
            for x in range(9):
                small.set_at((x, y), shade(base, rng.randbelow(25) - 12))
        surface.blit(pg.transform.smoothscale(small, surface.get_size()), (0, 0))
        for _ in range(700):
            x, y = rng.randbelow(128), rng.randbelow(128)
            color = surface.get_at((x, y))[:3]
            surface.set_at((x, y), shade(color, rng.randbelow(17) - 8))
        count = style['density']
        if terrain.biome in ('grassland', 'forest', 'scrub'):
            count = count * (70 + terrain.moisture * 60 // 65535) // 100
        for _ in range(count):
            x, y = 7 + rng.randbelow(114), 7 + rng.randbelow(110)
            kind = style['symbol']
            if terrain.biome == 'grassland' and rng.randbelow(100) < terrain.wooded:
                kind = 'tree'
            draw_symbol(pg, surface, kind, x, y, ink, light)
        if terrain.biome not in ('water', 'coast'):
            # Relief glyphs communicate ruggedness, not precise mountain sites.
            ridges = min(12, terrain.relief // 4500)
            for row in range(ridges):
                slot = row * 5 % 12
                x = 14 + (slot % 3) * 36 + rng.randbelow(12)
                y = 22 + (slot // 3) * 27 + rng.randbelow(10)
                height = 8 + min(10, terrain.relief // 5000) + rng.randbelow(4)
                left, peak, right = (x - 11, y + 7), (x, y - height), (x + 14, y + 7)
                pg.draw.polygon(surface, shade(base, -12), [left, peak, right])
                pg.draw.polygon(surface, shade(base, 18), [left, peak, (x - 1, y + 6)])
                pg.draw.lines(surface, ink, False, [left, peak, right], 1)
                if cold > 80 or terrain.elevation > 54000:
                    pg.draw.lines(surface, light, False, [(x - 3, y - height + 6), peak, (x + 3, y - height + 6)], 2)
        return surface
