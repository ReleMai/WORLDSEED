"""W1: detached, bounded GPU view of the authoritative prepared simulation.

Capture runs after simulation updates, on its owning thread. It never prepares
terrain/resources, advances time, discovers cells, rebuilds indexes or opens
interiors. Unsupported interior/roof cells fail closed until W3 supplies their
own presentation. No names, inventories or private room contents cross here.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from worldseed.core.coords import WorldPos
from worldseed.core.clock import SEASONS, DAYS_PER_SEASON
from worldseed.systems.resources import FeatureView
from worldseed.systems.state import pos_key
from .gl_atmosphere import MAX_LIGHTS, WorldLight, weather_frame
from .gpu_scene_bridge import cell_bounds, prepare_gpu_frame
from .worldspace import WorldCamera, WorldFoot
from .worldspace_adapter import MAX_PREPARED_ACTORS, MAX_PREPARED_RESOURCES, PreparedActor


def _fraction(value):
    value = float(value)
    if not isfinite(value):
        raise ValueError('actor fraction must be finite')
    return max(0., min(.999, value))


def player_foot(sim):
    """Same saved cell/fraction authority used by existing free movement."""
    p = sim.player_pos
    return WorldFoot(p.x + _fraction(sim.state.player_fx),
                     p.y + _fraction(sim.state.player_fy), p.z)


@dataclass(frozen=True, slots=True)
class LiveFire:
    cell: tuple[int, int, int]
    intensity: int


@dataclass(frozen=True, slots=True)
class LiveGpuSnapshot:
    camera: WorldCamera
    viewer: WorldFoot
    terrain: tuple[tuple[tuple[int, int, int], str], ...]
    resources: tuple[tuple[tuple[int, int, int], FeatureView], ...]
    actors: tuple[PreparedActor, ...]
    current_cells: frozenset[tuple[int, int, int]]
    remembered_cells: frozenset[tuple[int, int, int]]
    fires: tuple[LiveFire, ...]
    weather: tuple[tuple[str, object], ...]
    minute: int
    season: str
    interior: bool = False

    def gpu_frame(self, *, materials, registry, resource_style):
        """Only static content/material services are needed after capture."""
        return prepare_gpu_frame(camera=self.camera, terrain_by=dict(self.terrain),
            resource_by={cell: (feature, None) for cell, feature in self.resources},
            resource_defs=registry.resources, resource_style=resource_style,
            visible_cells=self.current_cells, discovered_cells=self.remembered_cells,
            viewer=self.viewer, actors=self.actors, materials=materials,
            season=self.season, fire_cells=tuple(row.cell for row in self.fires))

    def atmosphere(self, elapsed_seconds=0.):
        origin = self.camera.to_world(0, 0, ground_z=self.camera.center.z)
        lights = []
        for fire in self.fires[:MAX_LIGHTS]:
            x, y, z = fire.cell
            px, py = self.camera.to_screen(WorldFoot(x+.5, y+.5, z))
            # W1 deliberately confines glow to its admitted source cell. Wider
            # light requires W4 wall/roof occlusion, not a second LOS authority.
            lights.append(WorldLight(px, py, max(1., self.camera.scale*.48),
                                     min(1.5, fire.intensity/85.)))
        weather = dict(self.weather)
        # The simulation uses rain 0..10 and v8 direction vectors +/-1024;
        # weather_frame accepts percent precipitation and a shader wind vector.
        weather['rain'] = float(weather.get('rain', 0))*10.
        speed = float(weather.get('wind_speed', 0))/100.
        weather['wind_dx'] = float(weather.get('wind_dx', 0))/1024.*speed
        weather['wind_dy'] = float(weather.get('wind_dy', 0))/1024.*speed
        return weather_frame(weather, minute=self.minute,
            elapsed_seconds=elapsed_seconds, camera_pixel_x=origin.x*self.camera.scale,
            camera_pixel_y=origin.y*self.camera.scale, lights=tuple(lights))


def capture_live_scene(sim, camera: WorldCamera) -> LiveGpuSnapshot:
    """Copy one viewport using simulation sight and prepared spatial indexes.

    Current sight is never inferred from discovery or lighting. The existing
    engine's NPC/creature model has no separate hidden-NPC flag: outdoor living
    actors are admitted by current sight, exterior membership and roof masks.
    Player stealth remains entirely simulation-owned; capture never asks the
    detection system to recompute awareness or changes observer state.
    """
    left, top, right, bottom = cell_bounds(camera)
    viewer = player_foot(sim)
    z = sim.player_pos.z
    if camera.center.z != z:
        raise ValueError('live GPU camera must match player elevation')
    minute = sim.clock.minute
    season = SEASONS[(minute//1440//DAYS_PER_SEASON) % len(SEASONS)]
    interior = sim.interiors.player_presence() is not None
    terrain = []
    resources = []
    current = set()
    remembered = set()
    actors = []
    fires = []
    physical = sim.settlement_physicalization

    if not interior:
        for y in range(top, bottom):
            for x in range(left, right):
                token = pos_key(x, y, z)
                seen = token in sim.visible_tiles_set
                if not seen and token not in sim.discovered_tiles_set:
                    continue  # no geometry reads for unexplored cells
                pos = WorldPos(x, y, z)
                roof = sim.building.roof_at(pos)
                if roof is not None and roof.condition > 0:
                    continue  # player-built covered spaces also fail closed
                if physical.shell_at(pos) is not None:
                    continue  # no floor/actor/resource leakage through a roof
                plan_cell = physical.cell_at(pos)
                if plan_cell is not None and (plan_cell.room_id or plan_cell.roof_piece_id):
                    continue  # legacy roof/room plans have no whole shell
                tile = sim.world.prepared_tile_at(pos)
                if tile is None:
                    continue  # missing prepared terrain remains unknown
                cell = (x, y, z)
                if not seen:
                    remembered.add(cell)
                    continue  # W1 draws only current ground, no live memory props
                current.add(cell)
                terrain.append((cell, tile.terrain_id))
                feature = sim.resources.prepared_feature_at(pos, minute)
                if feature is not None and feature.stage != 'depleted':
                    resources.append((cell, feature))
                    if len(resources) > MAX_PREPARED_RESOURCES:
                        raise ValueError('live GPU resource budget exceeded')

        # Never fall back to world-size dictionaries or repair stale indexes.
        candidates = sim.npcs.indexed_npcs_in_rect(left, top, right-1, bottom-1, z)
        for npc in candidates:
            cell = (npc.x, npc.y, npc.z)
            if (not npc.alive or npc.hp <= 0 or npc.uid in sim.state.interior_actors
                    or cell not in current):
                continue
            actors.append(PreparedActor('npc:'+npc.uid, 'core:npc',
                WorldFoot(npc.x+_fraction(npc.fx), npc.y+_fraction(npc.fy), npc.z), True))
            if len(actors) >= MAX_PREPARED_ACTORS:
                raise ValueError('live GPU actor budget exceeded')
        for creature in sim.state.creatures.near_rect(left, top, right-1, bottom-1, z):
            if creature.hp <= 0 or (creature.x, creature.y, creature.z) not in current:
                continue
            actors.append(PreparedActor('creature:'+creature.uid, creature.species_id,
                WorldFoot(creature.x+.5, creature.y+.5, creature.z), True))
            if len(actors) >= MAX_PREPARED_ACTORS:
                raise ValueError('live GPU actor budget exceeded')
        for fire in sim.state.fires.near_rect(left, top, right-1, bottom-1, z):
            cell = (fire.x, fire.y, fire.z)
            if cell in current and fire.fuel > 0 and fire.intensity > 0:
                fires.append(LiveFire(cell, int(fire.intensity)))
                if len(fires) > 32:
                    raise ValueError('live GPU fire budget exceeded')

    weather = {}
    if z == 0 and not interior:
        weather, _lighting = sim.environment.visual_conditions(minute, sim.player_pos)
    # Copy only numeric/string shader inputs, never a mutable weather dictionary.
    keys = ('kind', 'rain', 'fog', 'cloud_cover', 'wind_dx', 'wind_dy', 'wind_speed')
    weather_values = tuple((key, weather[key]) for key in keys if key in weather)
    return LiveGpuSnapshot(camera, viewer, tuple(terrain), tuple(resources),
        tuple(sorted(actors, key=lambda actor: actor.uid)), frozenset(current),
        frozenset(remembered), tuple(sorted(fires, key=lambda fire: fire.cell)),
        weather_values, minute, season, interior)
