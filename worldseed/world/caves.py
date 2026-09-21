"""Deterministic v7 cave geology and entrance planning.

Caves are generated from the same immutable world seed contract as terrain.
The subsystem deliberately stays queryable without realizing chunks: a cave
mouth, level topology, and mineral vein can be reconstructed from coordinates.
Player excavations remain sparse terrain deltas owned by World/persistence.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

from worldseed.core.coords import WorldPos
from worldseed.core.rng import hash_u64


@dataclass(frozen=True, slots=True)
class CaveEntrance:
    x: int
    y: int
    depth: int
    relief: int
    elevation: int


@dataclass(frozen=True, slots=True)
class CaveLevelInfo:
    depth: int
    band: str
    rock: str
    moisture: str
    ore_bias: tuple[str, ...]


class CaveGeneratorV7:
    """Karst-style entrances, vertically coherent chambers and clustered ores.

    This is not a full geological simulator.  It models the useful causal
    pieces for WORLDSEED: entrances prefer exposed relief, caves correlate
    between adjacent z-levels, shallow sedimentary layers favor coal/aquifers,
    and deeper fractured rock increasingly favors metallic ore veins.
    """

    ENTRANCE_CELL = 36
    MAX_NATURAL_DEPTH = 14

    def __init__(self, seed: bytes, sample_fields: Callable[[WorldPos], object], noise: Callable[[str, int, int, int], int]) -> None:
        self.seed = seed
        self.sample_fields = sample_fields
        self.noise = noise

    @lru_cache(maxsize=8192)
    def _entrance_for_cell(self, cx: int, cy: int) -> CaveEntrance | None:
        # Roughly one in five macro-cells is geologically eligible; terrain
        # scoring rejects flat/wet candidates, keeping actual mouths sparse.
        if hash_u64(self.seed, "cave-v7-cell", cx, cy) % 100 >= 22:
            return None
        base_x, base_y = cx * self.ENTRANCE_CELL, cy * self.ENTRANCE_CELL
        best: tuple[int, int, int, int, int] | None = None
        for i in range(14):
            x = base_x + 3 + hash_u64(self.seed, "cave-v7-x", cx, cy, i) % (self.ENTRANCE_CELL - 6)
            y = base_y + 3 + hash_u64(self.seed, "cave-v7-y", cx, cy, i) % (self.ENTRANCE_CELL - 6)
            f = self.sample_fields(WorldPos(x, y, 0))
            elevation = int(f.elevation)
            if elevation < 27800:
                continue
            e = [
                int(self.sample_fields(WorldPos(x + 5, y, 0)).elevation),
                int(self.sample_fields(WorldPos(x - 5, y, 0)).elevation),
                int(self.sample_fields(WorldPos(x, y + 5, 0)).elevation),
                int(self.sample_fields(WorldPos(x, y - 5, 0)).elevation),
            ]
            relief = max(abs(elevation - q) for q in e)
            # Exposed slopes and uplands are favored. A small stable jitter
            # avoids grid-aligned ties without becoming the placement cause.
            score = relief * 7 + max(0, elevation - 33000) // 2
            score += int(hash_u64(self.seed, "cave-v7-site-jitter", x, y) % 900)
            if relief < 420 and elevation < 43000:
                continue
            row = (score, relief, elevation, x, y)
            if best is None or row > best:
                best = row
        if best is None:
            return None
        _, relief, elevation, x, y = best
        depth = 3 + int(hash_u64(self.seed, "cave-v7-depth", x, y) % 7)
        # Rugged/high terrain is more likely to expose a deeper connected system.
        if relief > 1700 or elevation > 50000:
            depth = min(self.MAX_NATURAL_DEPTH, depth + 2)
        return CaveEntrance(x, y, depth, relief, elevation)

    def entrance(self, x: int, y: int) -> CaveEntrance | None:
        cell = self.ENTRANCE_CELL
        ent = self._entrance_for_cell(x // cell, y // cell)
        return ent if ent and ent.x == x and ent.y == y else None

    def connector_span(self, x: int, y: int) -> int:
        ent = self.entrance(x, y)
        return ent.depth if ent else 0

    def has_connector(self, pos: WorldPos) -> bool:
        span = self.connector_span(pos.x, pos.y)
        return span > 0 and 0 >= pos.z >= -span

    def near_entrance_chamber(self, pos: WorldPos) -> bool:
        if pos.z >= 0:
            return False
        # Search only a tiny landing neighborhood. The macro-cell entrance plan
        # is cached, so this remains cheap during chunk generation.
        depth = abs(pos.z)
        for dy in range(-3, 4):
            for dx in range(-3, 4):
                if dx * dx + dy * dy > 10:
                    continue
                span = self.connector_span(pos.x - dx, pos.y - dy)
                if span >= depth:
                    return True
        return False

    def level_info(self, depth: int) -> CaveLevelInfo:
        depth = max(1, int(depth))
        if depth <= 2:
            return CaveLevelInfo(depth, "shallow caverns", "weathered limestone", "damp", ("coal", "copper"))
        if depth <= 5:
            return CaveLevelInfo(depth, "sedimentary caves", "layered sedimentary rock", "variable", ("coal", "copper", "iron"))
        if depth <= 9:
            return CaveLevelInfo(depth, "deep fracture caves", "metamorphic rock", "dry", ("copper", "iron"))
        return CaveLevelInfo(depth, "deep crystalline caves", "crystalline basement rock", "dry", ("iron",))

    def _open_cave(self, pos: WorldPos) -> bool:
        depth = abs(pos.z)
        if depth > self.MAX_NATURAL_DEPTH:
            # Natural cavities become rare below the modeled crustal band, but
            # player shafts can still be excavated indefinitely as deltas.
            return self.noise("cave-v7:deep-fracture", pos.x + depth * 11, pos.y - depth * 7, 56) > 61800
        # Correlated 2.5D fields: each deeper level drifts rather than re-rolling
        # an unrelated cave sheet. Low ridge distance makes branching tunnels;
        # high macro values create chambers.
        macro = self.noise("cave-v7:macro", pos.x + depth * 7, pos.y - depth * 5, 58)
        tunnel = self.noise("cave-v7:tunnel", pos.x - depth * 3, pos.y + depth * 4, 24)
        ridge = abs(tunnel - 32768)
        info = self.level_info(depth)
        chamber_threshold = 44800 if depth <= 2 else 46600 if depth <= 5 else 48600 if depth <= 9 else 51200
        tunnel_width = 7200 if depth <= 2 else 6300 if depth <= 5 else 5400 if depth <= 9 else 4300
        return macro > chamber_threshold or ridge < tunnel_width

    def _wall_material(self, pos: WorldPos) -> str:
        depth = abs(pos.z)
        f = self.sample_fields(WorldPos(pos.x, pos.y, 0))
        moisture = int(getattr(f, "moisture", 32768))

        # Aquifers form broad wet lenses, mostly shallow/mid-depth.
        if depth <= 6:
            wet = self.noise("cave-v7:aquifer", pos.x + 1301, pos.y - 901, 34)
            # This field is deliberately broader than ore noise.  The cutoff is
            # high enough to keep aquifers uncommon, but reachable in ordinary
            # seeds; wetter surface climates lower it modestly so underground
            # water still has a causal relationship to regional moisture.
            threshold = 51200 - max(0, moisture - 32000) // 10
            if wet > threshold:
                return "core:aquifer"

        # Coal follows relatively thin sedimentary seams. The ridge function
        # produces long bands rather than single-cell salt-and-pepper deposits.
        if depth <= 5:
            seam = abs(self.noise("cave-v7:coal-seam", pos.x + 401, pos.y - 577, 42) - 32768)
            if seam < (1800 if depth <= 2 else 2500):
                return "core:coal_seam"

        # Copper favors mid-depth hydrothermal-style clustered veins.
        if 2 <= depth <= 8:
            copper = self.noise("cave-v7:copper", pos.x - depth * 9, pos.y + depth * 5, 30)
            # Mid-depth copper is rarer than coal but common enough for a
            # player to prospect rather than depend on a pathological seed.
            if copper > (51200 if depth < 4 else 49800):
                return "core:copper_vein"

        # Iron becomes more common with depth and occurs in larger lenses.
        if depth >= 3:
            iron = self.noise("cave-v7:iron", pos.x + depth * 5, pos.y - depth * 8, 38)
            threshold = max(54800, 61800 - depth * 900)
            if iron > threshold:
                return "core:iron_vein"
        return "core:cave_wall"

    def terrain_at(self, pos: WorldPos) -> str:
        if pos.z >= 0:
            raise ValueError("CaveGeneratorV7 only classifies underground cells")
        if self.has_connector(pos):
            return "core:shaft"
        if self.near_entrance_chamber(pos):
            return "core:cave_floor"
        return "core:cave_floor" if self._open_cave(pos) else self._wall_material(pos)


class CaveGeneratorV8(CaveGeneratorV7):
    """Phase-2 v8 entrance planner over geological/topographic fields.

    Underground chamber/ore generation intentionally inherits the v7 contract
    until the later underground-geology phase. Only natural entrance siting and
    entrance depth are replaced here, so v7 saves remain untouched.
    """

    ENTRANCE_CELL = 48

    def __init__(
        self,
        seed: bytes,
        sample_fields: Callable[[WorldPos], object],
        noise: Callable[[str, int, int, int], int],
        landform_at: Callable[[int, int], object],
        topography_at: Callable[[WorldPos], object],
    ) -> None:
        super().__init__(seed, sample_fields, noise)
        self.landform_at = landform_at
        self.topography_at = topography_at

    @lru_cache(maxsize=8192)
    def _entrance_for_cell(self, cx: int, cy: int) -> CaveEntrance | None:
        if hash_u64(self.seed, "cave-v8-cell", cx, cy) % 100 >= 20:
            return None
        base_x, base_y = cx * self.ENTRANCE_CELL, cy * self.ENTRANCE_CELL
        best: tuple[int, int, int, int, int] | None = None
        for i in range(16):
            x = base_x + 4 + hash_u64(self.seed, "cave-v8-x", cx, cy, i) % (self.ENTRANCE_CELL - 8)
            y = base_y + 4 + hash_u64(self.seed, "cave-v8-y", cx, cy, i) % (self.ENTRANCE_CELL - 8)
            pos = WorldPos(x, y, 0)
            fields = self.sample_fields(pos)
            elevation = int(fields.elevation)
            if elevation < 28200:
                continue
            topo = self.topography_at(pos)
            geology = self.landform_at(x, y)
            if topo is None or geology is None:
                continue

            # Mouths should read as exposed geological openings, not random holes
            # in flat plains. Relief and actual slope dominate; mountain/upland
            # structure breaks ties and deep valley floors are mildly penalized.
            if (
                int(topo.relief_raw) < 360
                and int(topo.slope) < 10500
                and int(geology.mountain_chain) < 18000
                and int(geology.plateau) < 25000
            ):
                continue
            score = int(topo.relief_raw) * 8
            score += int(topo.slope) // 18
            score += int(topo.ridge_exposure) // 28
            score += int(geology.mountain_chain) // 24
            score += int(geology.tectonic_uplift) // 42
            score += int(geology.plateau) // 70
            score -= int(topo.valley_depth) // 42
            score += int(hash_u64(self.seed, "cave-v8-site-jitter", x, y) % 700)

            row = (score, int(topo.relief_raw), elevation, x, y)
            if best is None or row > best:
                best = row

        if best is None:
            return None
        _, relief, elevation, x, y = best
        topo = self.topography_at(WorldPos(x, y, 0))
        geology = self.landform_at(x, y)
        depth = 3 + int(hash_u64(self.seed, "cave-v8-depth", x, y) % 7)
        if topo is not None and (
            int(topo.ruggedness) > 36000 or int(topo.relief_raw) > 1800
        ):
            depth += 2
        if geology is not None and int(geology.tectonic_uplift) > 42000:
            depth += 1
        depth = min(self.MAX_NATURAL_DEPTH, depth)
        return CaveEntrance(x, y, depth, relief, elevation)
