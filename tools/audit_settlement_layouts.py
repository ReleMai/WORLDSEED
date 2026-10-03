"""Bounded synthetic-terrain audit of authoritative settlement geometry.

This deliberately does not claim a real-world geography audit. It exercises the
same settlement planner and physical projection on five causal resource fields,
without realizing terrain, people, inventories, or strategic route networks.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from collections import deque
from pathlib import Path
from types import SimpleNamespace

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.systems.physicalization import SettlementPhysicalizationSystem
from worldseed.systems.settlement_planner import SettlementSkeletonPlanner
from worldseed.world.region_blocks import RegionBlockPlan, RegionRoadExit


ARCHETYPES = ('mining', 'forest', 'agrarian', 'fishing', 'frontier')
POPULATIONS = (4, 15, 45, 110, 230)


class MemoryCache:
    def __init__(self):
        self.rows = {}

    def load_generated_settlement_plan(self, uid, version):
        return self.rows.get((uid, version))

    def store_generated_settlement_plan(self, uid, version, payload):
        self.rows[(uid, version)] = payload

    def load_physical_plan_deltas(self, *args):
        return []

    def commit_generated(self):
        pass


def synthetic_fixture(registry, archetype, population, version=11, cache=None, seed=b'layout-audit'):
    # Values change the physical opportunity rather than just the town label.
    stone, timber, fresh, farmland, fertility, wetness = {
        'mining': (95, 46, 28, 30, 35, 28),
        'forest': (40, 96, 40, 38, 48, 50),
        'agrarian': (25, 35, 50, 96, 92, 48),
        'fishing': (24, 54, 98, 35, 43, 76),
        'frontier': (45, 52, 45, 74, 66, 32),
    }[archetype]
    env = SimpleNamespace(open_water=False, slope=8, flood_risk=5,
                          wetness=wetness, soil_fertility=fertility, farmland=farmland,
                          resources=SimpleNamespace(stone=stone, timber=timber, freshwater=fresh),
                          resource_opportunity=max(stone, timber, fresh, farmland))
    world = SimpleNamespace(generator=SimpleNamespace(world_seed=seed),
                            delta_source=cache or MemoryCache(), registry=registry,
                            settlement_plan_version=version, environment_at=lambda pos: env)
    region = RegionBlockPlan(uid=f'region:{archetype}', region_x=0, region_y=0, version=1,
                             dominant_biome='grassland', biome_mix={'grassland': 25},
                             mean_elevation=1, mean_moisture=1, mean_temperature=1, relief=1,
                             settlement_present=True, settlement_anchor=(256, 256), settlement_score=88,
                             settlement_archetype=archetype, control_potential='settled',
                             roads=(RegionRoadExit('north', 256, 'road'),
                                    RegionRoadExit('east', 256, 'road')))
    return world, region, f'settlement:layout:{archetype}:{population}'


def inspect_skeleton(world, registry, skeleton, require_all_resources=False):
    """Return geometric failures without mutating the plan or world authority."""
    failures = []
    plan = skeleton.plan
    road_ids = {row.uid for row in skeleton.roads}
    road_cells = {tuple(cell) for row in skeleton.roads for cell in row.polyline}
    for road in skeleton.roads:
        if any(abs(a[0]-b[0])+abs(a[1]-b[1]) != 1
               for a, b in zip(road.polyline, road.polyline[1:])):
            failures.append(f'non-cardinal road step: {road.uid}')
    if len(plan.resource_specializations) != 2 or len(set(plan.resource_specializations)) != 2:
        failures.append('primary resources must be exactly two distinct systems')
    selected = set(plan.resource_specializations)
    if require_all_resources and selected != {p.resource_deposit for p in skeleton.parcels if p.resource_deposit}:
        failures.append('suitable audit land lost an advertised production district')
    occupied = set()
    for parcel in skeleton.parcels:
        cells = set(map(tuple, parcel.cells))
        if occupied & cells:
            failures.append(f'overlapping parcel: {parcel.uid}')
        occupied.update(cells)
        if parcel.purpose != 'common' and parcel.access_road_id not in road_ids:
            failures.append(f'missing access road: {parcel.uid}')
        if parcel.resource_deposit and parcel.resource_deposit not in selected:
            failures.append(f'undeclared deposit: {parcel.uid}')
        if parcel.crop_id and ('farming' not in selected or parcel.crop_id not in plan.crop_ids):
            failures.append(f'unsupported crop: {parcel.uid}')
        if parcel.livestock_species_ids and ('livestock' not in selected
                or set(parcel.livestock_species_ids) != set(plan.livestock_species_ids)
                or len(parcel.livestock_species_ids) != 2):
            failures.append(f'unsupported livestock: {parcel.uid}')
    region_x = plan.anchor_x // 512
    region_y = plan.anchor_y // 512
    left, top = region_x*512+8, region_y*512+8
    if not all(left <= x <= left+495 and top <= y <= top+495
               for x, y in occupied | road_cells):
        failures.append('geometry left region planning margin')

    shells = [row for row in skeleton.structures if row.enclosed and not row.destroyed]
    blocked = set()
    for row in shells:
        owners = [parcel for parcel in skeleton.parcels if row.uid in parcel.structure_ids]
        if len(owners) != 1 or not set(map(tuple, row.footprint)) <= set(map(tuple, owners[0].cells)):
            failures.append(f'exterior outside its owning parcel: {row.uid}')
        body = set(map(tuple, row.footprint)) - ({tuple(row.entrance)} if row.entrance else set())
        if body & road_cells:
            failures.append(f'road through solid exterior: {row.uid}')
        blocked.update(map(tuple, row.footprint))
    # A nearby piece of road is not enough: every frontage must belong to the
    # connected road component that reaches the common, outside solid shells.
    traversable = road_cells - blocked
    common = set(map(tuple, plan.common_cells))
    starts = traversable & common
    if not starts and traversable:
        starts = {min(traversable, key=lambda p: min(abs(p[0]-x)+abs(p[1]-y) for x, y in common))}
    reached = set(starts)
    queue = deque(starts)
    while queue:
        x, y = queue.popleft()
        for cell in ((x, y-1), (x+1, y), (x, y+1), (x-1, y)):
            if cell in traversable and cell not in reached:
                reached.add(cell)
                queue.append(cell)
    physical = SettlementPhysicalizationSystem(world, registry, None, None)
    physical._skeletons[plan.settlement_id] = skeleton
    physical._index_skeleton(plan.settlement_id, skeleton)
    for x, y in sorted(road_cells - blocked):
        if not physical.passable(WorldPos(x, y, 0), True):
            failures.append(f'road obstructed by a physical fixture: {x},{y}')
    for row in shells:
        frontage = physical.frontage_for(row.uid)
        if frontage is None:
            failures.append(f'no usable exterior frontage: {row.uid}')
            continue
        cell = (frontage.x, frontage.y)
        if cell in set(map(tuple, row.footprint)) or cell not in reached:
            failures.append(f'frontage disconnected from common: {row.uid}')
        if abs(frontage.x-row.entrance[0])+abs(frontage.y-row.entrance[1]) != 1:
            failures.append(f'frontage not adjacent to stable door: {row.uid}')
    for row in skeleton.structures:
        if row.enclosed or row.destroyed or row.entrance is None:
            continue
        gate = tuple(row.entrance)
        if gate not in reached or not physical.passable(WorldPos(*gate, 0), True):
            failures.append(f'outdoor worksite gate disconnected or obstructed: {row.uid}')
        if (plan.version >= 12 or plan.plan_revision >= 1) and row.function in {'animal_pen','farm_field'}:
            footprint=set(map(tuple,row.footprint))
            boundary={p for p in footprint if any((p[0]+dx,p[1]+dy) not in footprint
                                                  for dx,dy in ((0,1),(1,0),(0,-1),(-1,0)))}
            if not any((gate[0]+dx,gate[1]+dy) in footprint-boundary
                       and physical.passable(WorldPos(gate[0]+dx,gate[1]+dy,0),True)
                       and (gate[0]-dx,gate[1]-dy) not in footprint
                       for dx,dy in ((0,1),(1,0),(0,-1),(-1,0))):
                failures.append(f'gate has no cardinal interior/exterior passage: {row.uid}')
    rooms = {}
    for room in skeleton.rooms:
        rooms.setdefault(room.structure_plan_id, []).append(room)
    housing = 0
    workplaces = {}
    for row in skeleton.structures:
        if row.destroyed:
            continue
        beds = sum(room.kind == 'bedroom' for room in rooms.get(row.uid, ()))
        if row.function == 'residence':
            housing += max(4, beds*4, row.interior_area//3)
        elif row.function in {'inn', 'barracks', 'outskirt_camp'}:
            housing += max(8, beds*8, row.interior_area*2//3)
        elif row.workplace_role:
            workplaces[row.workplace_role] = workplaces.get(row.workplace_role, 0) + max(1, row.interior_area//5)
    if plan.housing_capacity != housing or plan.workplace_capacity != workplaces:
        failures.append('capacity differs from authoritative generated structures')
    return failures


def audit(version=11, archetypes=ARCHETYPES, populations=POPULATIONS, seed=b'layout-audit', max_cases=25):
    registry = ContentRegistry.load(DATA_DIR)
    started = time.monotonic()
    cases = []
    for archetype in archetypes:
        for population in populations:
            if len(cases) >= max_cases:
                break
            world, region, uid = synthetic_fixture(registry, archetype, population, version, seed=seed)
            skeleton = SettlementSkeletonPlanner(world).plan(region, uid, population, persist=False)
            cases.append({'archetype': archetype, 'rank': skeleton.plan.rank,
                          'layout': skeleton.plan.morphology, 'population': population,
                          'resources': skeleton.plan.resource_specializations,
                          'parcels': len(skeleton.parcels), 'structures': len(skeleton.structures),
                          'roads': len(skeleton.roads), 'housing': skeleton.plan.housing_capacity,
                          'fingerprint': skeleton.fingerprint,
                          'failures': inspect_skeleton(world, registry, skeleton, require_all_resources=True)})
    return {'mode': 'synthetic-terrain-matrix', 'version': version,
            'seed': seed.hex(), 'cases': cases, 'case_count': len(cases),
            'elapsed_seconds': round(time.monotonic()-started, 3),
            'ok': bool(cases) and all(not row['failures'] for row in cases)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', type=int, default=11)
    parser.add_argument('--seed', default='layout-audit')
    parser.add_argument('--max-cases', type=int, default=25)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.max_cases <= 25:
        parser.error('--max-cases must be between 1 and 25')
    result = audit(version=args.version, seed=args.seed.encode(), max_cases=args.max_cases)
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(f"Synthetic terrain matrix: {result['case_count']} cases, {result['elapsed_seconds']}s")
        for case in result['cases']:
            print(f"{case['archetype']}/{case['rank']} {case['layout']}: "
                  f"{len(case['failures'])} failure(s)")
            for failure in case['failures']:
                print('  ' + failure)
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
