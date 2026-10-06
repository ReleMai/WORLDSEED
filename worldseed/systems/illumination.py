"""Shared, observational gameplay light over prepared physical spaces.

Intensity is fixed-point 0..65535. Installed light fixtures are steady sources;
outdoor fire emits only while its authoritative FireCell still has fuel and
intensity. There are no renderer-owned lights, clocks, random rolls or persistent
per-pixel maps. Indoor coordinates use InteriorPlan units, outdoor radii tiles.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
from math import isqrt

from worldseed.config import DATA_DIR
from worldseed.core.coords import WorldPos
from worldseed.systems.state import pos_key
from worldseed.world.lighting import LightingSystem

Q = 65535
MAX_SOURCES = 64
MAX_FIRE_RADIUS = 6


@dataclass(frozen=True, slots=True)
class LightSource:
    x: int
    y: int
    radius: int
    intensity: int
    uid: str = ""


def _clamp(value: int) -> int:
    return max(0, min(Q, int(value)))


@lru_cache(maxsize=1)
def lighting_catalog() -> dict:
    data = json.loads((DATA_DIR / "illumination.json").read_text(encoding="utf-8"))
    if (data.get("version") != 1 or type(data.get("indoor_ambient_percent")) is not int
            or not 0 <= data["indoor_ambient_percent"] <= 100
            or not isinstance(data.get("sources"), dict)):
        raise ValueError("Invalid illumination catalog")
    for uid, row in data["sources"].items():
        if (not uid.startswith("core:") or type(row.get("radius")) is not int
                or not 100 <= row["radius"] <= 12000
                or type(row.get("intensity")) is not int
                or not 0 <= row["intensity"] <= Q):
            raise ValueError("Invalid illumination source: " + uid)
    return data


def segment_clear(plan, x0: int, y0: int, x1: int, y1: int) -> bool:
    """Exact bounded wall intersection without sampling thin walls away."""
    precision = 1 << 30
    for wall in plan.walls:
        low, high = 0, precision
        for origin, delta, left, size in ((x0, x1-x0, wall.x, wall.w),
                                         (y0, y1-y0, wall.y, wall.h)):
            right = left + size - 1
            if delta == 0:
                if not left <= origin <= right:
                    low, high = 1, 0
                    break
                continue
            # Fixed-point parameter intervals retain sub-unit accuracy even in
            # the largest prepared room; all calculations stay integer-only.
            a, b = (left-origin)*precision//delta, (right-origin)*precision//delta
            low, high = max(low, min(a,b)), min(high, max(a,b))
            if low > high:
                break
        if low <= high:
            return False
    return True


def indoor_sources(plan) -> tuple[LightSource, ...]:
    from worldseed.systems.interior_furnishing import furniture_base_piece
    definitions = lighting_catalog()["sources"]
    rows = []
    for fixture in sorted(plan.furniture, key=lambda row: row.uid):
        source = definitions.get(furniture_base_piece(fixture.piece_id))
        if source is not None:
            rows.append(LightSource(fixture.x+fixture.w//2, fixture.y+fixture.h//2,
                                    source["radius"], source["intensity"], fixture.uid))
        if len(rows) == MAX_SOURCES:
            break
    return tuple(rows)


indoor_line_clear = segment_clear


def interior_ambient(environment, minute: int, plan) -> int:
    """One weather-aware exterior sample shared by indoor render and security."""
    if environment is None:
        return LightingSystem().at(minute).ambient_light
    _weather, lighting = environment.visual_conditions(minute,
        WorldPos(plan.exterior_x,plan.exterior_y,plan.exterior_z))
    return _clamp(lighting.ambient_light)


def source_strength(source: LightSource, x: int, y: int) -> int:
    distance = isqrt((int(x)-source.x)**2 + (int(y)-source.y)**2)
    if distance >= source.radius or source.radius <= 0:
        return 0
    # Smooth finite falloff, reaching exactly zero at the source radius.
    remaining = source.radius-distance
    return source.intensity*remaining*remaining//(source.radius*source.radius)


def indoor_light(plan, x: int, y: int, minute: int, *, ambient_light: int | None = None,
                 sources: tuple[LightSource, ...] | None = None) -> int:
    """Sample one prepared interior without materializing or changing it.

    Diffuse shell/daylight is attenuated indoors; installed point lights are
    wall-occluded and do not leak into neighboring rooms. Callers can supply a
    previously sampled weather-aware exterior ambient value and source tuple.
    """
    if ambient_light is None:
        ambient_light = LightingSystem().at(minute).ambient_light
    total = _clamp(ambient_light)*lighting_catalog()["indoor_ambient_percent"]//100
    for source in (indoor_sources(plan) if sources is None else sources)[:MAX_SOURCES]:
        strength = source_strength(source,x,y)
        if strength and segment_clear(plan,source.x,source.y,int(x),int(y)):
            total += strength
    return _clamp(total)


def outdoor_sources(state, pos: WorldPos, radius: int = MAX_FIRE_RADIUS) -> tuple[LightSource, ...]:
    """Bounded keyed local fire reads, never a scan of realized world fires."""
    radius = max(0,min(36,int(radius)))
    fires = getattr(state,"fires",{}) if state is not None else {}
    rows = []
    for y in range(pos.y-radius,pos.y+radius+1):
        for x in range(pos.x-radius,pos.x+radius+1):
            key = pos_key(x,y,pos.z)
            fire = fires.get(key)
            if fire is not None and fire.intensity > 0 and fire.fuel > 0:
                rows.append(LightSource(x,y,MAX_FIRE_RADIUS,
                    max(0,min(100,int(fire.intensity)))*Q//100,key))
    rows.sort(key=lambda row: ((row.x-pos.x)**2+(row.y-pos.y)**2,row.uid))
    return tuple(rows[:MAX_SOURCES])


def outdoor_light(environment, minute: int, pos: WorldPos, *, state=None,
                  sources: tuple[LightSource, ...] | None = None,
                  clear_line=None, ambient_light: int | None = None) -> int:
    """Surface clock/weather + real nearby fire; underground has no sunlight."""
    if pos.z != 0:
        ambient = 1500
    elif ambient_light is not None:
        ambient = _clamp(ambient_light)
    elif environment is None:
        ambient = LightingSystem().at(minute).ambient_light
    else:
        _weather, lighting = environment.visual_conditions(minute,pos)
        ambient = int(lighting.ambient_light)
    total = _clamp(ambient)
    for source in (outdoor_sources(state,pos) if sources is None else sources)[:MAX_SOURCES]:
        strength = source_strength(source,pos.x,pos.y)
        if strength and (clear_line is None or clear_line(WorldPos(source.x,source.y,pos.z),pos)):
            total += strength
    return _clamp(total)


def detection_scale(light: int, stalking: bool = False, skill: int = 0) -> int:
    """Target illumination determines recognition reach, not observer lighting.

    Darkness is useful concealment, never invisibility. Stalk and learned stealth
    improve concealment, while adjacent observers/noisy actions remain dangerous.
    """
    scale = 18000 + _clamp(light)*(Q-18000)//Q
    if stalking:
        scale = scale*max(55,82-max(0,min(12,int(skill)))*3)//100
    return max(1,min(Q,scale))


def light_description(light: int) -> str:
    value = _clamp(light)
    return "Dark" if value < 9000 else "Dim" if value < 24000 else "Lit" if value < 48000 else "Bright"


def indoor_actor_visible(plan, px: int, py: int, nx: int, ny: int, minute: int, *,
                         ambient_light: int | None = None, max_range: int = 12000) -> bool:
    """Player sight uses the same target light and wall occlusion as NPC sight."""
    if not segment_clear(plan,px,py,nx,ny):
        return False
    light = indoor_light(plan,nx,ny,minute,ambient_light=ambient_light)
    radius = max(1000,int(max_range)*detection_scale(light)//Q)
    return (nx-px)**2+(ny-py)**2 <= radius*radius
