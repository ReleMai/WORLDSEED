import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

import unittest
from types import SimpleNamespace

from worldseed.config import DATA_DIR, CHUNK_SIZE
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import ChunkKey
from worldseed.systems.settlement_planner import SettlementSkeleton
from worldseed.systems.state import SettlementState
from worldseed.ui.atlas_map import (
    atlas_input,
    begin_atlas,
    read_prepared_settlement_detail,
)
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.world.regional_plan import (
    LandUseParcel,
    RoadSegmentPlan,
    RoomPlanState,
    SettlementPlanState,
    StructurePlanState,
)


def settlement_fixture(uid='settlement:atlas'):
    plan = SettlementPlanState(
        uid='plan:atlas',
        settlement_id=uid,
        version=1,
        anchor_x=10,
        anchor_y=10,
        archetype='mining',
        rank='village',
        common_cells=[(10,10),(11,10),(10,11),(11,11)],
    )
    roads = [
        RoadSegmentPlan(
            uid='road:main',
            settlement_plan_id=plan.uid,
            road_class='road',
            polyline=[(6,10),(7,10),(8,10),(9,10),(10,10),(11,10),(12,10),(13,10),(14,10)],
        )
    ]
    residential_cells=[(x,y) for y in range(7,12) for x in range(14,19)]
    industrial_cells=[(x,y) for y in range(12,19) for x in range(7,14)]
    parcels = [
        LandUseParcel(
            uid='parcel:home',
            settlement_plan_id=plan.uid,
            cells=residential_cells,
            kind='residential',
            purpose='home_lot',
            access_road_id='road:main',
        ),
        LandUseParcel(
            uid='parcel:industry',
            settlement_plan_id=plan.uid,
            cells=industrial_cells,
            kind='industrial',
            purpose='mine_approach',
            access_road_id='road:main',
        ),
        LandUseParcel(
            uid='parcel:farm',
            settlement_plan_id=plan.uid,
            cells=[(x,y) for y in range(13,18) for x in range(16,22)],
            kind='farm',
            purpose='field',
            access_road_id='road:main',
        ),
    ]
    home_footprint=[(x,y) for y in range(8,12) for x in range(15,19)]
    smithy_footprint=[(x,y) for y in range(13,18) for x in range(8,13)]
    structures = [
        StructurePlanState(
            uid='structure:home',
            settlement_plan_id=plan.uid,
            content_id='core:generated_residence',
            function='residence',
            footprint=home_footprint,
            entrance=(15,10),
            building_type='residence',
            enclosed=True,
            interior_area=4,
            room_ids=['room:bedroom'],
        ),
        StructurePlanState(
            uid='structure:smithy',
            settlement_plan_id=plan.uid,
            content_id='core:generated_smithy',
            function='smithy',
            footprint=smithy_footprint,
            entrance=(10,13),
            building_type='smithy',
            workplace_role='smith',
            enclosed=True,
            interior_area=9,
            room_ids=['room:smithy','room:storage'],
        ),
    ]
    parcels[0].structure_ids=['structure:home']
    parcels[1].structure_ids=['structure:smithy']
    rooms = [
        RoomPlanState(
            uid='room:bedroom',
            structure_plan_id='structure:home',
            kind='bedroom',
            cells=[(16,9),(17,9),(16,10),(17,10)],
            area=4,
            sheltered=True,
            roof_percent=100,
        ),
        RoomPlanState(
            uid='room:smithy',
            structure_plan_id='structure:smithy',
            kind='smithy',
            cells=[(9,14),(10,14),(9,15),(10,15)],
            area=4,
            sheltered=True,
            roof_percent=100,
        ),
        RoomPlanState(
            uid='room:storage',
            structure_plan_id='structure:smithy',
            kind='storage',
            cells=[(11,14),(11,15)],
            area=2,
            sheltered=True,
            roof_percent=100,
        ),
    ]
    plan.road_segment_ids=[row.uid for row in roads]
    plan.parcel_ids=[row.uid for row in parcels]
    plan.structure_site_ids=[row.uid for row in structures]
    return SettlementSkeleton(plan, roads, parcels, structures, rooms, [], 'atlas-ui-test')


class SettlementAtlasDetailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)

    def test_detail_read_model_exposes_use_function_entrance_and_room_labels(self):
        skeleton=settlement_fixture()
        town=SettlementState(
            uid=skeleton.plan.settlement_id,name='Stoneford',region_x=0,region_y=0,
            x=10,y=10,population=72,culture_id='culture:test',
            religion_id='religion:test',faction_id='faction:test',
        )
        sim=SimpleNamespace(
            state=SimpleNamespace(settlements={town.uid:town}),
            known_settlements=lambda:[town],
            settlement_physicalization=SimpleNamespace(skeleton_for=lambda uid:skeleton if uid==town.uid else None),
            settlement_planner=SimpleNamespace(
                read_prepared=lambda uid: (_ for _ in ()).throw(AssertionError('active skeleton should win'))
            ),
        )
        detail=read_prepared_settlement_detail(sim,town.uid)
        self.assertIsNotNone(detail)
        entrance=detail.snapshot.cell_at(15,10)
        self.assertEqual(entrance.land_use,'residential')
        self.assertEqual(entrance.parcel_purpose,'home_lot')
        self.assertEqual(entrance.structure_function,'residence')
        self.assertTrue(entrance.entrance)
        smithy=detail.snapshot.cell_at(9,14)
        self.assertEqual(smithy.building_type,'smithy')
        self.assertEqual(smithy.room_kind,'smithy')
        room_labels={(kind,name) for kind,name,_,_ in detail.snapshot.labels if kind=='room'}
        self.assertIn(('room','bedroom'),room_labels)
        self.assertIn(('room','smithy'),room_labels)
        self.assertIn(('room','storage'),room_labels)

    def test_detail_falls_back_to_prepared_plan_cache_without_generation(self):
        skeleton=settlement_fixture('settlement:cached')
        town=SettlementState(
            uid=skeleton.plan.settlement_id,name='Cached Town',region_x=0,region_y=0,
            x=10,y=10,population=65,culture_id='culture:test',
            religion_id='religion:test',faction_id='faction:test',
        )
        reads=[]
        sim=SimpleNamespace(
            state=SimpleNamespace(settlements={town.uid:town}),
            known_settlements=lambda:[town],
            settlement_physicalization=SimpleNamespace(skeleton_for=lambda uid:None),
            settlement_planner=SimpleNamespace(read_prepared=lambda uid:reads.append(uid) or skeleton),
        )
        detail=read_prepared_settlement_detail(sim,town.uid)
        self.assertEqual(reads,[town.uid])
        self.assertEqual(detail.snapshot.settlement_plan_id,skeleton.plan.uid)


@unittest.skipUnless(PygameTerminal.available(),'pygame optional')
class SettlementAtlasDetailRenderTests(unittest.TestCase):
    def setUp(self):
        from tests.test_dev22_atlas import fixture
        self.td,self.db,self.world,self.sim=fixture()
        values=['core:grass']*(CHUNK_SIZE*CHUNK_SIZE)
        self.db.store_generated_chunk(ChunkKey(0,0,0),self.world.generator.version,values)
        self.sim.discovered_tiles_set.update(f'{x},{y},0' for y in range(0,24) for x in range(0,24))
        self.skeleton=settlement_fixture()
        self.town=SettlementState(
            uid=self.skeleton.plan.settlement_id,name='Stoneford',region_x=0,region_y=0,
            x=10,y=10,population=72,culture_id='culture:test',
            religion_id='religion:test',faction_id='faction:test',
        )
        self.sim.state.settlements[self.town.uid]=self.town
        self.sim.known_settlements=lambda:[self.town]
        self.sim.settlement_physicalization=SimpleNamespace(
            skeleton_for=lambda uid:self.skeleton if uid==self.town.uid else None
        )
        self.sim.settlement_planner=SimpleNamespace(read_prepared=lambda uid:None)

    def tearDown(self):
        self.db.close();self.td.cleanup()

    def test_detail_view_is_responsive_and_keeps_information_scoped(self):
        term=PygameTerminal();term.enter()
        try:
            begin_atlas(term,self.sim)
            term.present_region_map(self.sim)
            self.assertTrue(atlas_input(term,self.sim,'ATLAS_POI:'+self.town.uid))
            term.present_region_map(self.sim)
            self.assertTrue(any(token=='ATLAS_DETAIL_OPEN:'+self.town.uid for _,token in term._pointer_targets))
            self.assertTrue(atlas_input(term,self.sim,'ATLAS_DETAIL_OPEN:'+self.town.uid))

            for size in ((800,520),(1280,800),(1920,1080)):
                term._resize(*size)
                term.present_region_map(self.sim)
                screen_rect=term.screen.get_rect()
                for rect,token in term._pointer_targets:
                    self.assertTrue(screen_rect.contains(rect),(size,token,rect))
                tokens={token for _,token in term._pointer_targets}
                self.assertIn('ATLAS_DETAIL_INSPECT',tokens)
                self.assertIn('ATLAS_DETAIL_BACK',tokens)
                self.assertNotIn('ATLAS_DRAG_ZONE',tokens)

            snap=term._atlas_controls.detail.snapshot
            rect=term._settlement_detail_rect
            wx,wy=9,14
            mx=rect.x+((wx-snap.left)*rect.width)//snap.width+1
            my=rect.y+((wy-snap.top)*rect.height)//snap.height+1
            term._last_mouse=(mx,my)
            self.assertTrue(atlas_input(term,self.sim,'ATLAS_DETAIL_INSPECT'))
            self.assertEqual(term._atlas_controls.detail_inspected,(wx,wy))
            term.present_region_map(self.sim)
            self.assertTrue(atlas_input(term,self.sim,'ATLAS_DETAIL_BACK'))
            self.assertIsNone(term._atlas_controls.detail)
        finally:
            term.restore()


if __name__ == '__main__':
    unittest.main()
