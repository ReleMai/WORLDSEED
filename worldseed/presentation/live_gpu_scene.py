"""W1: detached, bounded GPU view of the authoritative prepared simulation.

Capture runs after simulation updates, on its owning thread. It never prepares
terrain/resources, advances time, discovers cells, rebuilds indexes or opens
interiors. W3 closed exterior shells use a separate exact-cell sight mask;
unsupported interior/player-roof cells remain closed. No names, inventories or
private room contents cross here.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite

from worldseed.core.coords import WorldPos
from worldseed.core.clock import SEASONS, DAYS_PER_SEASON
from worldseed.systems.resources import FeatureView
from worldseed.systems.building_shells import BuildingShell
from worldseed.systems.state import pos_key
from .gl_atmosphere import MAX_LIGHTS, WorldLight, weather_frame
from .gpu_scene_bridge import cell_bounds, prepare_gpu_frame
from .gpu_buildings import (MAX_BUILDING_CELLS, MAX_BUILDING_EXTENT,
    MAX_PREPARED_BUILDINGS, PreparedBuildingDoor, PreparedBuildingShell)
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
    buildings: tuple[PreparedBuildingShell, ...] = ()
    ambient_light: float | None = None

    def gpu_frame(self, *, materials, registry, resource_style):
        """Only static content/material services are needed after capture."""
        return prepare_gpu_frame(camera=self.camera, terrain_by=dict(self.terrain),
            resource_by={cell: (feature, None) for cell, feature in self.resources},
            resource_defs=registry.resources, resource_style=resource_style,
            visible_cells=self.current_cells, discovered_cells=self.remembered_cells,
            viewer=self.viewer, actors=self.actors, materials=materials,
            season=self.season, fire_cells=tuple(row.cell for row in self.fires),
            buildings=self.buildings, terrain_defs=registry.terrains)

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
        return replace(weather_frame(weather, minute=self.minute,
            elapsed_seconds=elapsed_seconds, camera_pixel_x=origin.x*self.camera.scale,
            camera_pixel_y=origin.y*self.camera.scale, lights=tuple(lights)), sun=self.ambient_light)


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
    buildings = {}
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
                shell = physical.shell_at(pos)
                if shell is not None:
                    if seen and z == 0 and isinstance(shell, BuildingShell):
                        # O(1) local cell index lookup. Do not use the existing
                        # shells_in_bounds helper: it scans every active shell.
                        if shell.uid not in buildings:
                            if len(buildings) >= MAX_PREPARED_BUILDINGS:
                                raise ValueError('live GPU building budget exceeded')
                            buildings[shell.uid] = (shell, set())
                        buildings[shell.uid][1].add((x, y, z))
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
    ambient_light = None
    if z == 0 and not interior:
        weather, lighting = sim.environment.visual_conditions(minute, sim.player_pos)
        if lighting is not None:
            ambient_light = max(0., min(1., lighting.ambient_light/65535.))
    # Copy only numeric/string shader inputs, never a mutable weather dictionary.
    keys = ('kind', 'rain', 'fog', 'cloud_cover', 'wind_dx', 'wind_dy', 'wind_speed')
    weather_values = tuple((key, weather[key]) for key in keys if key in weather)
    prepared_buildings = []
    for uid, (shell, cells) in sorted(buildings.items()):
        # Unsupported huge/modded plans stay hidden instead of expanding a
        # bounded presentation query into their complete physical footprint.
        left, top, right, bottom = shell.bounds
        if (len(shell.footprint) > MAX_BUILDING_CELLS
                or right-left+1 > MAX_BUILDING_EXTENT
                or bottom-top+1 > MAX_BUILDING_EXTENT):
            continue
        door = None
        if shell.entrance is not None and shell.door_uid:
            threshold = (*shell.entrance, 0)
            if threshold in cells:
                state = sim.state.door_security.get(shell.door_uid)
                opened = bool(state and (state.forced or (state.answering_npc_uid
                    and state.answered_minute >= state.answer_requested_minute >= 0)))
                door = PreparedBuildingDoor(shell.door_uid, threshold, opened)
        # Reuse only a prepared/persisted visual pin. Never open/prepare a room
        # to choose exterior art, and never copy its occupants or private name.
        plan = sim.state.interiors.get('interior:'+uid)
        variant_id = str(getattr(plan, 'variant_id', ''))
        prepared_buildings.append(PreparedBuildingShell(shell,
            frozenset(cells), variant_id, door))
    return LiveGpuSnapshot(camera, viewer, tuple(terrain), tuple(resources),
        tuple(sorted(actors, key=lambda actor: actor.uid)), frozenset(current),
        frozenset(remembered), tuple(sorted(fires, key=lambda fire: fire.cell)),
        weather_values, minute, season, interior, tuple(prepared_buildings), ambient_light)
