"""Prepared synthetic QA scenes using WORLDSEED's real simulation and plans.

These are controlled renderer fixtures, not naturally generated world samples.
The temporary database, synthetic terrain and environmental opportunity fields
are fixture inputs. Buildings, portals and interiors use production planners.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from worldseed.config import CHUNK_SIZE, SETTLEMENT_PLAN_VERSION, WORLDGEN_VERSION
from worldseed.core.coords import ChunkKey, WorldPos
from worldseed.core.rng import hash_u64
from worldseed.entities.components import Inventory, Position, Vitals
from worldseed.entities.store import EntityStore
from worldseed.persistence.database import WorldDatabase
from worldseed.sim.engine import Simulation
from worldseed.systems.interior_state import InteriorActor
from worldseed.systems.state import (
    ContainerState, FireCell, GroundPile, LivingWorldState, NPCState,
    SettlementState, StructureInstance, pos_key,
)
from worldseed.world.chunk import Chunk
from worldseed.world.generator import WorldGenerator
from worldseed.world.region_blocks import RegionBlockPlan, RegionRoadExit
from worldseed.world.world import World


SCENES = ('forest', 'camp', 'village_street', 'interior', 'open_panel', 'large_save')
FIXTURE_VERSION = 1
GAME_MINUTE = 720
ANIMATION_MILLISECONDS = 1600


class PreparedReferenceSimulation(Simulation):
    """Keep real systems while replacing new-game realization with preparation."""

    def _ensure_nearby_world(self, *args, **kwargs):
        pass

    def _discover(self, *args, **kwargs):
        pass


def _unprepared(*args, **kwargs):
    raise RuntimeError('Reference scene attempted raw generation or planning during rendering')


@dataclass
class ReferenceFixture:
    name: str
    sim: Simulation
    db: WorldDatabase
    seed: str
    bounds: tuple[int, int, int, int]
    plan_fingerprint: str = ''
    distant_npcs: int = 0
    state_json_bytes: int = 0

    @property
    def world(self):
        return self.sim.world

    def counts(self):
        state = self.sim.state
        return {
            'npcs': len(state.npcs), 'distant_npcs': self.distant_npcs,
            'settlements': len(state.settlements), 'structures': len(state.structures),
            'planned_structures': len(self.sim.settlement_physicalization._structures),
            'physical_cells': len(self.sim.settlement_physicalization._cells),
            'containers': len(state.containers), 'interiors': len(state.interiors),
            'interior_actors': len(state.interior_actors),
            'discovered_cells': len(self.sim.discovered_tiles_set),
            'visible_cells': len(self.sim.visible_tiles_set),
        }

    def authority_fingerprint(self):
        """Audit authoritative state outside measured frames, including terrain."""
        sim = self.sim
        payload = {
            'state': sim.state.to_dict(), 'turn': sim.turn,
            'clock_minute': sim.clock.minute, 'log': [str(row) for row in sim.log],
            'discovered': sorted(sim.discovered_tiles_set),
            'visible': sorted(sim.visible_tiles_set),
            'settlement_plans': {uid: plan.to_dict() for uid, plan in
                                 sim.settlement_physicalization._skeletons.items()},
            'position': asdict(sim.entities.get(sim.player_id, Position)),
            'inventory': asdict(sim.entities.get(sim.player_id, Inventory)),
            'vitals': asdict(sim.entities.get(sim.player_id, Vitals)),
            'world_revision': self.world.revision,
            'dirty_tiles': sorted((p.x, p.y, p.z, value)
                                  for p, value in self.world.dirty_tiles.items()),
            'db_total_changes': self.db.connection.total_changes,
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode())
        for key, chunk in sorted(self.world.cache._chunks.items(), key=lambda row: (row[0].z, row[0].y, row[0].x)):
            digest.update(f'{key.x},{key.y},{key.z}:'.encode())
            digest.update(chunk.terrain.tobytes())
        return digest.hexdigest()

    def guard_preparation(self):
        # A missing prepared cell must fail the audit instead of silently making
        # a benchmark frame perform geography/resource/settlement generation.
        self.world.cache.loader = _unprepared
        self.world.generator.generate_chunk = _unprepared
        self.sim.region_planner.plan = _unprepared
        self.sim.settlement_planner.plan = _unprepared
        self.sim.resources._raw_feature = _unprepared
        self.sim.resources._build_feature_chunk = _unprepared

    def close(self):
        self.db.close()


def _region():
    return RegionBlockPlan(
        uid='reference:region', region_x=0, region_y=0, version=1,
        dominant_biome='grassland', biome_mix={'grassland': 25},
        mean_elevation=1, mean_moisture=1, mean_temperature=1, relief=1,
        settlement_present=True, settlement_anchor=(256, 256), settlement_score=90,
        settlement_archetype='agrarian', control_potential='settled',
        roads=tuple(RegionRoadExit(side, 256, 'road')
                    for side in ('north', 'east', 'south', 'west')),
    )


def _prepare_village(sim, width, height, zoom):
    # A uniform, causal opportunity field deliberately makes planning bounded
    # and repeatable. The production planner still owns the resulting geometry.
    opportunity = SimpleNamespace(
        open_water=False, slope=3, flood_risk=2, wetness=40,
        soil_fertility=80, farmland=94, resource_opportunity=94,
        resources=SimpleNamespace(stone=72, timber=70, freshwater=66),
    )
    sim.world.environment_at = lambda pos: opportunity
    town = SettlementState('reference:town', 'Reference Village', 0, 0, 256, 256,
                           230, '', '', '', stocks={'core:wood': 70, 'core:stone': 50},
                           law={'theft': 100, 'tax': 5})
    sim.state.settlements[town.uid] = town
    physical = sim.settlement_physicalization
    physical.region_planner = SimpleNamespace(plan=lambda *args, **kwargs: _region())
    physical.route_planner = None
    physical.sync([town], (0, 0))
    skeleton = physical.skeleton_for(town.uid)
    if skeleton is None:
        raise RuntimeError('Reference village production plan did not materialize')
    sim.civics.ensure_settlement(town.uid)
    sim.property_security.sync_active()
    sim.property_storage.sync_active()
    # Select a real connected street frontage with many nearby real shells.
    half_x = max(3, (width - max(280, min(350, width // 4)) - 40) // zoom // 2)
    half_y = max(3, (height - 240) // zoom // 2)
    candidates = [physical.frontage_for(row.uid) for row in skeleton.structures if row.enclosed]
    candidates = sorted({p for p in candidates if p is not None}, key=lambda p: (p.y, p.x))
    if not candidates:
        raise RuntimeError('Reference village has no usable street frontage')
    def density(pos):
        return len(physical.shells_in_bounds(pos.x-half_x, pos.y-half_y, pos.x+half_x, pos.y+half_y))
    center = max(candidates, key=density)
    roads = sorted({(x, y) for road in skeleton.roads for x, y in road.polyline
                    if abs(x-center.x) <= half_x and abs(y-center.y) <= half_y
                    and physical.passable(WorldPos(x, y), True)},
                   key=lambda p: (abs(p[0]-center.x)+abs(p[1]-center.y), p[1], p[0]))
    for i, (x, y) in enumerate(roads[1:25]):
        uid = f'reference:resident:{i:02d}'
        sim.state.npcs[uid] = NPCState(uid, f'Resident {i+1}', 32, 'farmer',
                                      ['patient'], x, y, 0, town.uid, '', goal='idle')
    return center, skeleton


def _prepare_camp(sim, center):
    for identifier, dx, dy in (('core:campfire', 2, 1), ('core:bed', -2, -1),
                                ('core:workbench', 2, -2)):
        pos = center.moved(dx, dy)
        sim.state.structures[pos_key(pos.x, pos.y, 0)] = StructureInstance(identifier, pos.x, pos.y, 0)
    fire = center.moved(2, 1)
    sim.state.fires[pos_key(fire.x, fire.y, 0)] = FireCell(fire.x, fire.y, 0, 65, 100)
    chest = center.moved(-2, 1)
    sim.state.containers[pos_key(chest.x, chest.y, 0)] = ContainerState(
        'reference:camp-storage', chest.x, chest.y, 0, 'player', 90000, 140000,
        {'core:wood': 5, 'core:stone': 3}, source_id='core:chest')
    pile = center.moved(0, 2)
    sim.state.ground_piles[pos_key(pile.x, pile.y, 0)] = GroundPile(pile.x, pile.y, 0, {'core:wood': 3})


def build_fixture(name, registry, directory: Path, *, seed='worldseed-reference-v1',
                  width=1280, height=720, zoom=28, distant_npcs=0):
    """Prepare a bounded, isolated fixture; never open or copy a player save."""
    if name not in SCENES:
        raise ValueError(f'Unknown reference scene: {name}')
    if not 640 <= width <= 3840 or not 480 <= height <= 2160 or zoom not in (20, 28, 36, 48):
        raise ValueError('Reference fixture size or zoom is outside supported bounds')
    if not 0 <= distant_npcs <= 50000:
        raise ValueError('distant_npcs must be between 0 and 50000')
    seed_bytes = seed.encode('utf-8')
    db = WorldDatabase.create(Path(directory) / f'{name}.db', f'QA {name}', seed_bytes.hex())
    try:
        world = World(WorldGenerator(seed_bytes, registry, version=WORLDGEN_VERSION),
                      registry, db, cache_chunks=512, auto_hydrology=False)
        # No natural-world generation is needed even during fixture planning:
        # the planner uses the synthetic opportunity field and storage queries
        # use cache.peek. Catch unexpected fallback reads immediately.
        world.generator.generate_chunk = _unprepared
        world.cache.loader = _unprepared
        world.settlement_plan_version = SETTLEMENT_PLAN_VERSION
        entities = EntityStore()
        player = entities.spawn(preferred_id=1)
        center = WorldPos(256, 256)
        entities.add(player, Position(center))
        entities.add(player, Inventory({'core:wood': 12, 'core:stone': 8, 'core:fiber': 6}))
        entities.add(player, Vitals())
        state = LivingWorldState(clock_minute=GAME_MINUTE, player_name='Reference Wanderer')
        sim = PreparedReferenceSimulation(world, entities, registry, state=state, world_seed=seed_bytes)
        skeleton = None
        if name in ('village_street', 'interior', 'open_panel', 'large_save'):
            center, skeleton = _prepare_village(sim, width, height, zoom)
        elif name == 'camp':
            _prepare_camp(sim, center)
        entities.get(player, Position).value = center
        # Prepare a complete camera envelope including resource/transition
        # neighbor reads. Clamped CLI size/zoom bounds keep this below 512 chunks.
        radius_x = width // zoom // 2 + CHUNK_SIZE
        radius_y = height // zoom // 2 + CHUNK_SIZE
        bounds = (center.x-radius_x, center.y-radius_y, center.x+radius_x, center.y+radius_y)
        season = sim.resources._season(GAME_MINUTE)
        for cy in range(bounds[1] // CHUNK_SIZE, bounds[3] // CHUNK_SIZE + 1):
            for cx in range(bounds[0] // CHUNK_SIZE, bounds[2] // CHUNK_SIZE + 1):
                key = ChunkKey(cx, cy, 0)
                chunk = Chunk.empty(key)
                resources = []
                for ly in range(CHUNK_SIZE):
                    for lx in range(CHUNK_SIZE):
                        x, y = cx*CHUNK_SIZE+lx, cy*CHUNK_SIZE+ly
                        token = hash_u64(seed_bytes, 'reference-terrain', x, y)
                        forest = name == 'forest' or (name == 'camp' and max(abs(x-center.x), abs(y-center.y)) > 5)
                        terrain = 'core:forest' if forest else 'core:grass'
                        if forest and token % 11 == 0:
                            terrain = 'core:rock'
                        chunk.set(lx, ly, registry.terrain_index(terrain))
                        tree = ('core:oak_tree' if token % 2 else 'core:pine_tree') if forest and token % 7 == 0 else None
                        if abs(x-center.x)+abs(y-center.y) < 3:
                            tree = None
                        resources.append(tree)
                world.cache.put(key, chunk)
                sim.resources._cache_feature_chunk((cx, cy, season), tuple(resources))
        known = {pos_key(x, y, 0) for y in range(bounds[1], bounds[3]+1)
                 for x in range(bounds[0], bounds[2]+1)}
        state.discovered_tiles = sorted(known)
        sim._discovered_tile_set = known
        sim._visible_tile_set = set(known)
        sim._discovered_surface_cells_by_chunk = {}
        for y in range(bounds[1], bounds[3]+1):
            for x in range(bounds[0], bounds[2]+1):
                sim._discovered_surface_cells_by_chunk.setdefault((x//CHUNK_SIZE, y//CHUNK_SIZE), set()).add(
                    (y%CHUNK_SIZE)*CHUNK_SIZE + x%CHUNK_SIZE)
        sim._discovered_surface_chunks = set(sim._discovered_surface_cells_by_chunk)
        if name == 'interior':
            house = next(row for row in skeleton.structures if row.enclosed and row.function == 'residence')
            plan = sim.interiors.prepare_workplace(house.uid)
            if plan is None:
                raise RuntimeError('Reference interior production portal did not prepare')
            sim.interiors._put_actor('player', InteriorActor(plan.uid, plan.entry_x, plan.entry_y))
            entities.get(player, Position).value = WorldPos(plan.exterior_x, plan.exterior_y, plan.exterior_z)
        for i in range(distant_npcs):
            uid = f'reference:distant:{i:05d}'
            state.npcs[uid] = NPCState(uid, f'Distant Resident {i}', 30, 'farmer', [],
                                      100000 + i*3, 100000, 0, '', '', goal='idle')
        # Serialize to the fixture-owned SQLite database before measurement so
        # reported save bytes correspond to actual state, including large saves.
        serialized_state = state.to_dict()
        db.save_state(turn=sim.turn, tile_deltas={}, player_id=player,
                      position=entities.get(player, Position).value,
                      inventory=entities.get(player, Inventory).items,
                      vitals=asdict(entities.get(player, Vitals)), sim_state=serialized_state)
        fixture = ReferenceFixture(name, sim, db, seed, bounds,
                                   skeleton.fingerprint if skeleton else '', distant_npcs,
                                   len(json.dumps(serialized_state, sort_keys=True, separators=(',', ':')).encode()))
        fixture.guard_preparation()
        return fixture
    except BaseException:
        db.close()
        raise
