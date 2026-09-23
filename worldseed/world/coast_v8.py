"""WORLDGEN v8 Phase 5 coastal morphology read model.

This layer interprets authoritative geology, topography, climate and prepared
hydrology.  It does not own terrain IDs, persistence or rendering.  Phase 5 can
therefore be audited before any save-visible coastline projection changes.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from functools import lru_cache
from typing import TYPE_CHECKING

from worldseed.config import COAST_MORPHOLOGY_VERSION
from worldseed.core.coords import WorldPos
from worldseed.world.landforms import SEA_LEVEL_REFERENCE

if TYPE_CHECKING:
    from worldseed.world.generator import WorldGenerator

COAST_MORPHOLOGY_ALGORITHM = "worldgen-v8-coast-readmodel-v1"
Q = 65535
COAST_MATERIALIZATION_GRID = 8

_DIRECTIONS_8 = (
    (-1,-1),(0,-1),(1,-1),
    (-1,0),         (1,0),
    (-1,1), (0,1), (1,1),
)


def _score(value: int) -> int:
    return max(0, min(100, int(value)))


@dataclass(frozen=True, slots=True)
class CoastMorphology:
    ocean: bool
    near_coast: bool
    depth_below_sea: int
    coast_distance: int
    shelf_depth: int
    shelf_class: str
    land_fraction: int
    open_sea: int
    wave_exposure: int
    shelter: int
    coast_kind: str
    shore_material: str
    bay_score: int
    headland_score: int
    tidal_flat_potential: int
    marsh_potential: int
    sediment_potential: int
    estuary_strength: int
    delta_potential: int
    lagoon_potential: int
    version: int = COAST_MORPHOLOGY_VERSION
    algorithm: str = COAST_MORPHOLOGY_ALGORITHM


class CoastV8Sampler:
    """Bounded absolute-coordinate coast classifier for v8 worlds."""

    def __init__(self, generator: "WorldGenerator") -> None:
        self.generator = generator

    def _elevation(self, x: int, y: int) -> int:
        # Coast geometry needs geological elevation only. Calling sample_fields
        # here would also run the full physical climate sampler for every ring
        # probe, multiplying Phase-5 cost for information we do not consume.
        landforms=getattr(self.generator,"landforms_v8",None)
        if landforms is not None:
            return int(landforms.sample(int(x),int(y)).elevation)
        return int(self.generator.sample_fields(WorldPos(int(x),int(y),0)).elevation)

    def _ring_land_fraction(self, x: int, y: int, radius: int) -> int:
        land=0
        for dx,dy in _DIRECTIONS_8:
            if self._elevation(x+dx*radius,y+dy*radius) >= SEA_LEVEL_REFERENCE:
                land+=1
        return land*100//len(_DIRECTIONS_8)

    def _nearest_opposite_distance(self, x: int, y: int, ocean: bool) -> int:
        # Geometric shelf/coastal distance.  This deliberately samples several
        # physical scales rather than converting only local slope into "depth".
        for radius in (4,8,16,32,64,96,128,192,256):
            for dx,dy in _DIRECTIONS_8:
                sample_ocean=self._elevation(x+dx*radius,y+dy*radius) < SEA_LEVEL_REFERENCE
                if sample_ocean != ocean:
                    return radius
        return 320

    def _hydrology_context(self, pos: WorldPos, prepared_only: bool):
        hydro=getattr(self.generator,"hydrology",None)
        if hydro is None:
            return None
        try:
            return getattr(hydro,'drainage_surface_at',hydro.surface_at)(pos,prepared_only=prepared_only)
        except TypeError:
            return hydro.surface_at(pos)

    @lru_cache(maxsize=32768)
    def _sample_cached(self, x: int, y: int, hydro_token: str, prepared_only: bool) -> CoastMorphology:
        pos=WorldPos(int(x),int(y),0)
        fields=self.generator.sample_fields(pos)
        topo=self.generator.topography_at(pos)
        climate=self.generator.climate_at(pos)
        elevation=int(fields.elevation)
        ocean=elevation < SEA_LEVEL_REFERENCE
        distance=self._nearest_opposite_distance(x,y,ocean)
        near_coast=distance <= 64

        land16=self._ring_land_fraction(x,y,16)
        land64=self._ring_land_fraction(x,y,64)
        land128=self._ring_land_fraction(x,y,128)
        land_fraction=(land16*5+land64*3+land128*2)//10
        open_sea=100-land_fraction

        slope=_score((int(getattr(topo,"slope",0))*100)//Q)
        relief=_score((int(getattr(topo,"relief",0))*100)//Q)
        moisture=_score(int(fields.moisture)*100//Q)
        wind=_score(int(getattr(climate,"wind_strength",0))*100//Q) if climate is not None else 45

        depth=max(0,SEA_LEVEL_REFERENCE-elevation)
        if ocean:
            # Continental geometry is primary, raw vertical depth secondary.
            geometry=min(100,distance*100//256)
            vertical=min(100,depth*100//14000)
            shelf_depth=_score(geometry*3//5+vertical*2//5)
            shelf_class=("intertidal" if shelf_depth<12 else
                         "shallow" if shelf_depth<32 else
                         "shelf" if shelf_depth<67 else "deep")
        else:
            shelf_depth=0
            shelf_class="land"

        # Concave ocean coast -> bay; convex exposed land -> headland.
        bay_score=_score((land16*2+land64)//3 - slope//4) if ocean and near_coast else 0
        headland_score=_score((open_sea*2+relief)//3 + slope//4) if (not ocean and near_coast) else 0

        wave_exposure=_score(open_sea*3//5+wind*2//5 + headland_score//5 - bay_score//4)
        shelter=_score(100-wave_exposure + bay_score//3)

        hydro=self._hydrology_context(pos,prepared_only=prepared_only)
        river_class=int(getattr(hydro,"river_class",0) or 0) if hydro is not None else 0
        floodplain=int(getattr(hydro,"floodplain_strength",0) or 0) if hydro is not None else 0
        wetland=int(getattr(hydro,"wetland_probability",0) or 0) if hydro is not None else 0
        delta_hint=bool(getattr(hydro,"delta",False)) if hydro is not None else False

        low_gradient=100-slope
        sediment=_score(river_class*24 + floodplain//2 + low_gradient//4)
        estuary=_score(river_class*22 + shelter//3 + (25 if near_coast else 0)) if near_coast and river_class else 0
        delta=_score(sediment*2//3 + shelter//4 + (18 if delta_hint else 0) - wave_exposure//4)
        if river_class < 2 or not near_coast:
            delta=0

        tidal_flat=_score(low_gradient*2//5+shelter*2//5+sediment//5) if near_coast else 0
        marsh=_score(tidal_flat*2//5+moisture*2//5+wetland//5) if near_coast else 0
        lagoon=_score(shelter//2+tidal_flat//4+delta//4-wave_exposure//5) if ocean and near_coast else 0

        coast_kind="open_ocean" if ocean else "inland"
        shore_material="none"
        if near_coast:
            if ocean:
                if bay_score>=62:
                    coast_kind="protected_bay"
                elif tidal_flat>=68:
                    coast_kind="tidal_flat"
                else:
                    coast_kind="nearshore"
            else:
                if slope>=68 or relief>=72:
                    coast_kind="cliff"
                elif headland_score>=68:
                    coast_kind="headland"
                elif marsh>=68:
                    coast_kind="marsh"
                elif tidal_flat>=64:
                    coast_kind="tidal_flat"
                elif wave_exposure>=62 and slope>=38:
                    coast_kind="rocky"
                else:
                    coast_kind="beach"

            if coast_kind in {"cliff","headland","rocky"}:
                shore_material="rock"
            elif coast_kind in {"marsh","tidal_flat","protected_bay"}:
                shore_material="mud"
            elif slope>=45:
                shore_material="gravel"
            else:
                shore_material="sand"

        return CoastMorphology(
            ocean=ocean,near_coast=near_coast,depth_below_sea=depth,
            coast_distance=distance,shelf_depth=shelf_depth,shelf_class=shelf_class,
            land_fraction=land_fraction,open_sea=open_sea,
            wave_exposure=wave_exposure,shelter=shelter,
            coast_kind=coast_kind,shore_material=shore_material,
            bay_score=bay_score,headland_score=headland_score,
            tidal_flat_potential=tidal_flat,marsh_potential=marsh,
            sediment_potential=sediment,estuary_strength=estuary,
            delta_potential=delta,lagoon_potential=lagoon,
        )

    def sample(self, pos: WorldPos, *, prepared_only: bool = True) -> CoastMorphology | None:
        if self.generator.version < 8 or pos.z != 0:
            return None
        hydro=getattr(self.generator,"hydrology",None)
        token="none"
        if hydro is not None:
            domain=hydro.cached_domain(*hydro.domain_for_world(pos.x,pos.y))
            if domain is not None:
                token=str(domain.fingerprint)
            elif prepared_only:
                # Coast geometry itself is still readable; river-mouth fields
                # remain zero until prepared hydrology exists.
                token="unprepared"
            else:
                token="generate"
        return replace(self._sample_cached(int(pos.x),int(pos.y),token,bool(prepared_only)),
                       version=self.generator.coast_morphology_version)

    def materialization_at(self,pos:WorldPos,fields=None)->CoastMorphology|None:
        """Cheap coast projection for per-tile terrain generation.

        The expensive exposure/geometry classifier is sampled on an 8-cell
        absolute lattice and reused across nearby tiles. Exact geological
        elevation still decides land versus water for every cell, so coastline
        position is not quantized into 8x8 blocks.
        """
        if self.generator.version<8 or pos.z!=0:
            return None
        grid=COAST_MATERIALIZATION_GRID
        qx=(int(pos.x)//grid)*grid
        qy=(int(pos.y)//grid)*grid
        coarse=self.sample(WorldPos(qx,qy,0),prepared_only=True)
        if coarse is None:
            return None
        if fields is None:
            fields=self.generator.sample_fields(pos)
        elevation=int(fields.elevation)
        ocean=elevation<SEA_LEVEL_REFERENCE
        if ocean:
            depth=max(0,SEA_LEVEL_REFERENCE-elevation)
            distance=int(coarse.coast_distance)
            if ocean!=coarse.ocean:
                distance=min(distance,grid)
            geometry=min(100,distance*100//256)
            vertical=min(100,depth*100//14000)
            shelf_depth=_score(geometry*3//5+vertical*2//5)
            shelf_class=("intertidal" if shelf_depth<12 else
                         "shallow" if shelf_depth<32 else
                         "shelf" if shelf_depth<67 else "deep")
            kind=coarse.coast_kind if coarse.ocean else "nearshore"
            if kind not in {"nearshore","protected_bay","tidal_flat","open_ocean"}:
                kind="nearshore"
            return replace(
                coarse,ocean=True,near_coast=coarse.near_coast or ocean!=coarse.ocean,
                depth_below_sea=depth,coast_distance=distance,
                shelf_depth=shelf_depth,shelf_class=shelf_class,coast_kind=kind,
            )

        distance=int(coarse.coast_distance)
        if ocean!=coarse.ocean:
            distance=min(distance,grid)
        kind=coarse.coast_kind if not coarse.ocean else "beach"
        if kind not in {"beach","rocky","cliff","headland","marsh","tidal_flat","inland"}:
            kind="beach"
        material=coarse.shore_material if coarse.shore_material!="none" else "sand"
        return replace(
            coarse,ocean=False,near_coast=coarse.near_coast or ocean!=coarse.ocean,
            depth_below_sea=0,coast_distance=distance,
            shelf_depth=0,shelf_class="land",coast_kind=kind,
            shore_material=material,
        )
