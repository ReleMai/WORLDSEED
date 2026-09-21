"""RC14 natural surface potential, derived from unchanged geography.

Scores are integer 0..100 game indices, not degrees, rainfall or crop yields.
This read model is not soil state, resource inventory or settlement authority.
No random draws, simulation writes, terrain realization or regional planning.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from worldseed.config import ENVIRONMENT_VERSION
from worldseed.core.coords import WorldPos

if TYPE_CHECKING:
    from worldseed.world.generator import WorldGenerator

Q = 65535
SAMPLE_RADIUS = 8
RELIEF_RADIUS = 32
CACHE_LIMIT = 8192


def _score(value: int) -> int:
    return max(0, min(100, int(value)))


@dataclass(frozen=True, slots=True)
class ResourceOpportunity:
    """Habitat potential; does not promise an item at this coordinate."""
    forage: int
    timber: int
    stone: int
    freshwater: int

    @property
    def score(self) -> int:
        return (self.forage * 3 + self.timber * 2 + self.stone + self.freshwater * 2) // 8


@dataclass(frozen=True, slots=True)
class EnvironmentalFields:
    slope: int
    relief: int
    soil_fertility: int
    wetness: int
    drainage: int
    flood_risk: int
    farmland: int
    resources: ResourceOpportunity
    open_water: bool
    version: int = ENVIRONMENT_VERSION

    @property
    def resource_opportunity(self) -> int:
        return self.resources.score

    def ground_signs(self) -> tuple[str, ...]:
        if self.open_water:
            return ('Ground signs: open water; unsuitable for fields or foundations',)
        grade = lambda n: 'low' if n < 34 else 'moderate' if n < 67 else 'high'
        soil = 'poor' if self.soil_fertility < 34 else 'fair' if self.soil_fertility < 67 else 'rich'
        wet = 'dry' if self.wetness < 25 else 'waterlogged' if self.wetness >= 75 else 'moist'
        drain = 'poor' if self.drainage < 34 else 'moderate' if self.drainage < 67 else 'good'
        return (
            f'Ground signs: {soil} natural soil, {wet}; {drain} drainage',
            f'Landform: {grade(self.slope)} slope, {grade(self.relief)} relief; {grade(self.flood_risk)} flood risk',
            f'Natural potential: {grade(self.farmland)} farmland, {grade(self.resource_opportunity)} resources',
        )


class EnvironmentalFieldSampler:
    """Bounded, reconstructable cache owned by one world's generator.

    v5 reads return None until a hydrology plan exists. Missing plans are never
    replaced with invented dry-land scores. Legacy worlds use their original
    climate/elevation and receive no v5 river influence. Fingerprint cache keys
    invalidate derived samples when a prepared drainage plan changes.
    """
    def __init__(self, generator: WorldGenerator, cache_limit: int = CACHE_LIMIT):
        self.generator = generator
        self.cache_limit = max(1, int(cache_limit))
        self._cache: OrderedDict[tuple, EnvironmentalFields] = OrderedDict()

    def at(self, pos: WorldPos) -> EnvironmentalFields | None:
        if pos.z != 0:
            return None
        gen = self.generator
        hydro = None
        fingerprint = 'legacy'
        if gen.version >= 5:
            hydro = gen.hydrology
            if hydro is None:
                return None
            domain = hydro.cached_domain(*hydro.domain_for_world(pos.x, pos.y))
            if domain is None:
                return None
            fingerprint = domain.fingerprint
        key = (ENVIRONMENT_VERSION, gen.version, fingerprint, pos.x, pos.y)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        surface = hydro.surface_at(pos, prepared_only=True) if hydro else None
        if hydro is not None and surface is None:
            return None
        result = self._derive(pos, surface)
        self._cache[key] = result
        if len(self._cache) > self.cache_limit:
            self._cache.popitem(last=False)
        return result

    def _derive(self, pos: WorldPos, surface) -> EnvironmentalFields:
        gen = self.generator
        base = gen.sample_fields(pos)
        elevation = lambda dx, dy: gen.sample_fields(WorldPos(pos.x + dx, pos.y + dy, 0)).elevation
        # Centered differences are anchored in absolute world coordinates, so
        # chunks and negative-coordinate boundaries do not reset the stencil.
        near = [elevation(-SAMPLE_RADIUS, 0), elevation(SAMPLE_RADIUS, 0),
                elevation(0, -SAMPLE_RADIUS), elevation(0, SAMPLE_RADIUS)]
        slope = _score((abs(near[1] - near[0]) + abs(near[3] - near[2])) * 100 // 12000)
        far = [base.elevation] + [elevation(dx, dy) for dx, dy in
                ((-RELIEF_RADIUS, 0), (RELIEF_RADIUS, 0), (0, -RELIEF_RADIUS), (0, RELIEF_RADIUS))]
        relief = _score((max(far) - min(far)) * 100 // 16000)
        moisture = base.moisture * 100 // Q
        temperature = base.temperature * 100 // Q
        depression = _score((sum(near) // 4 - base.elevation) * 100 // 2000)
        fp = surface.floodplain_strength if surface else 0
        hydro_wet = surface.wetland_probability if surface else 0
        flood = _score(surface.flood_risk if surface else 0)
        ocean = base.elevation < 23800
        open_water = ocean or bool(surface and (surface.lake or surface.river_depth_class))
        drainage = _score(55 + slope // 2 + relief // 5 - depression // 2 - hydro_wet // 2 - fp // 4)
        wetness = _score(moisture * 3 // 4 + (100 - drainage) // 4 + hydro_wet // 3 + fp // 5)
        bedrock = _score((base.elevation - 46000) * 100 // 15000)
        fertility = _score(base.fertility * 100 // Q + fp // 6 - slope // 3
                           - bedrock // 2 - max(0, wetness - 72) - max(0, 25 - wetness))
        temperate = _score(100 - abs(temperature - 55) * 2)
        farmland = fertility * (100 - slope) * (100 - flood) * temperate // 1000000
        forage = fertility * (100 - abs(wetness - 55)) * temperate // 10000
        timber = moisture * temperate * (100 - bedrock) * (100 - max(0, wetness - 75) * 3) // 1000000
        stone = _score(bedrock + relief // 2 + slope // 3)
        freshwater = _score(surface.water_access_score if surface and not ocean else 0)
        if open_water:
            fertility = farmland = forage = timber = stone = drainage = 0
            wetness = 100
            flood = 100
        return EnvironmentalFields(slope, relief, fertility, wetness, drainage, flood,
                                   _score(farmland), ResourceOpportunity(_score(forage), _score(timber), stone, freshwater), open_water)
