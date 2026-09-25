import unittest
from types import SimpleNamespace

from worldseed.config import DATA_DIR, SETTLEMENT_PLAN_VERSION
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.systems.ai import NPCSystem
from worldseed.systems.economy import EconomySystem
from worldseed.systems.family import FamilySystem
from worldseed.systems.law import LawSystem
from worldseed.systems.physicalization import SettlementPhysicalizationSystem
from worldseed.systems.settlement_planner import SettlementSkeletonPlanner
from worldseed.systems.settlement_population import SettlementPopulationBinder
from worldseed.systems.state import (
    CultureState,
    FactionState,
    LivingWorldState,
    NPCState,
    SettlementState,
)
from worldseed.world.region_blocks import RegionBlockPlan, RegionRoadExit


class NullHistory:
    def __init__(self):
        self.rows=[]
    def record(self,*args,**kwargs):
        self.rows.append((args,kwargs))


class CivicEconomySocialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)

    def _world_and_region(self):
        class Cache:
            def load_generated_settlement_plan(self,*_): return None
            def store_generated_settlement_plan(self,*_): pass
            def commit_generated(self): pass

        env=SimpleNamespace(
            open_water=False,slope=4,flood_risk=3,wetness=42,
            soil_fertility=76,farmland=82,
            resources=SimpleNamespace(stone=78,timber=62,freshwater=58),
            resource_opportunity=68,
        )
        world=SimpleNamespace(
            generator=SimpleNamespace(world_seed=b'civic-social-test'),
            delta_source=Cache(),
            registry=self.registry,
            environment_at=lambda pos:env,
        )
        region=RegionBlockPlan(
            uid='civic-region',region_x=0,region_y=0,version=1,
            dominant_biome='grassland',biome_mix={'grassland':25},
            mean_elevation=1,mean_moisture=1,mean_temperature=1,relief=1,
            settlement_present=True,settlement_anchor=(180,180),settlement_score=86,
            settlement_archetype='mining',control_potential='settled',
            roads=(
                RegionRoadExit('north',180,'road'),
                RegionRoadExit('east',180,'road'),
                RegionRoadExit('south',180,'road'),
                RegionRoadExit('west',180,'road'),
            ),
        )
        return world,region

    def test_civic_service_buildings_are_physical_and_bind_professions(self):
        world,region=self._world_and_region()
        region_planner=SimpleNamespace(plan=lambda rx,ry,persist=True:region)
        planner=SettlementSkeletonPlanner(world)
        skeleton=planner.plan(region,'settlement:civic',120,persist=False)
        expected={'market','clinic','watchhouse','shrine','archive'}
        purposes={p.purpose for p in skeleton.parcels if p.kind=='civic'}
        self.assertTrue(expected.issubset(purposes),purposes)
        functions={s.function for s in skeleton.structures}
        self.assertTrue(expected.issubset(functions),functions)
        roles={s.function:s.workplace_role for s in skeleton.structures}
        self.assertEqual(roles['market'],'merchant')
        self.assertEqual(roles['clinic'],'healer')
        self.assertEqual(roles['watchhouse'],'guard')
        self.assertEqual(roles['shrine'],'priest')
        self.assertEqual(roles['archive'],'scholar')
        # WU19 intentionally advances persistent building geometry for new worlds.
        self.assertEqual(SETTLEMENT_PLAN_VERSION,3)

        physical=SettlementPhysicalizationSystem(world,self.registry,region_planner,planner)
        town=SettlementState(
            uid='settlement:civic',name='Civic Test',region_x=0,region_y=0,x=180,y=180,
            population=120,culture_id='culture:test',religion_id='religion:test',
            faction_id='faction:test',
        )
        state=LivingWorldState()
        state.settlements[town.uid]=town
        for i,occ in enumerate(('merchant','healer','guard','scholar','priest')):
            npc=NPCState(
                uid=f'npc:{occ}',name=occ.title(),age=30+i,occupation=occ,
                traits=['patient','kind'],x=180,y=180,z=0,
                settlement_id=town.uid,faction_id=town.faction_id,
            )
            state.npcs[npc.uid]=npc
        physical.sync([town],(0,0),radius=0)
        binder=SettlementPopulationBinder(state,self.registry,b'civic-social-test',physical)
        binder.bind_settlement(town)
        structure_by_id={s.uid:s for s in physical.skeleton_for(town.uid).structures}
        expected_work={
            'merchant':'market','healer':'clinic','guard':'watchhouse',
            'scholar':'archive','priest':'shrine',
        }
        for npc in state.npcs.values():
            self.assertTrue(npc.workplace_id,npc.occupation)
            self.assertEqual(structure_by_id[npc.workplace_id].function,expected_work[npc.occupation])

    def test_family_identity_creates_lineage_backstory_needs_wants_and_kin(self):
        state=LivingWorldState()
        town=SettlementState(
            uid='settlement:family',name='Stoneford',region_x=0,region_y=0,x=0,y=0,
            population=80,culture_id='culture:test',religion_id='religion:test',
            faction_id='faction:test',
        )
        state.settlements[town.uid]=town
        rows=[
            ('elder-a',62,'farmer'),('elder-b',57,'healer'),
            ('adult-a',38,'smith'),('adult-b',34,'merchant'),
            ('young-a',23,'scholar'),('young-b',20,'guard'),
        ]
        for uid,age,occ in rows:
            state.npcs[uid]=NPCState(
                uid=uid,name=uid,age=age,occupation=occ,traits=['curious','kind'],
                x=0,y=0,z=0,settlement_id=town.uid,faction_id=town.faction_id,
            )
        family=FamilySystem(state,b'family-test',NullHistory())
        family.ensure_settlement_identity(town.uid)
        snapshot={}
        for npc in state.npcs.values():
            self.assertTrue(npc.family_uid)
            self.assertTrue(npc.lineage_uid)
            self.assertEqual(npc.backstory['birthplace'],'Stoneford')
            self.assertTrue(npc.wants)
            self.assertTrue({'social','safety','health','faith','learning','purpose'}.issubset(npc.needs))
            snapshot[npc.uid]=(npc.family_uid,npc.lineage_uid,dict(npc.kinship),dict(npc.backstory),list(npc.wants))
        self.assertTrue(any(n.parents or n.children or n.spouse_uid for n in state.npcs.values()))
        family.ensure_settlement_identity(town.uid)
        self.assertEqual(snapshot,{
            npc.uid:(npc.family_uid,npc.lineage_uid,dict(npc.kinship),dict(npc.backstory),list(npc.wants))
            for npc in state.npcs.values()
        })

    def test_regional_currency_barter_and_witnessed_theft_have_real_state(self):
        state=LivingWorldState()
        culture=CultureState('culture:test','Stonefolk',['trade'],'short',[],'stone')
        faction=FactionState('faction:test','Stonefolk League',culture.uid,laws={'theft':100})
        state.cultures[culture.uid]=culture
        state.factions[faction.uid]=faction
        a=SettlementState(
            uid='settlement:a',name='A',region_x=0,region_y=0,x=0,y=0,population=50,
            culture_id=culture.uid,religion_id='religion:test',faction_id=faction.uid,
            stocks={'core:wheat':20,'core:wood':20},law={'theft':100},
        )
        b=SettlementState(
            uid='settlement:b',name='B',region_x=1,region_y=0,x=512,y=0,population=50,
            culture_id=culture.uid,religion_id='religion:test',faction_id=faction.uid,
            stocks={'core:wheat':20,'core:wood':20},law={'theft':100},
        )
        state.settlements[a.uid]=a;state.settlements[b.uid]=b
        thief=NPCState('npc:thief','Thief',30,'merchant',['greedy'],0,0,0,a.uid,faction.uid,wealth=20)
        guard=NPCState('npc:guard','Guard',35,'guard',['patient'],0,0,0,a.uid,faction.uid,wealth=20)
        state.npcs[thief.uid]=thief;state.npcs[guard.uid]=guard
        history=NullHistory()
        economy=EconomySystem(state,self.registry,b'economy-test',history)
        economy.update_prices()
        self.assertEqual(a.currency_id,b.currency_id)
        self.assertEqual(a.currency_name,b.currency_name)
        self.assertGreater(a.currency_value,0)
        offered=economy.barter_value(a.uid,{'core:wood':2},offered=True)
        requested=economy.barter_value(a.uid,{'core:wheat':1},offered=False)
        self.assertIsInstance(economy.barter_balance(a.uid,{'core:wood':2},{'core:wheat':1}),int)
        self.assertGreater(offered,0);self.assertGreater(requested,0)

        before=a.stocks['core:wheat']
        theft=economy.record_theft(a.uid,thief.uid,a.uid,'core:wheat',1,1440,witnessed=True)
        a.stocks['core:wheat']-=1
        self.assertEqual(a.stocks['core:wheat'],before-1)
        self.assertIn(theft.uid,state.theft_records)
        self.assertFalse(theft.resolved)
        law=LawSystem(state,b'economy-test',history)
        for day in range(2,20):
            law.daily_update(day*1440)
            if theft.resolved:break
        self.assertTrue(theft.resolved)
        self.assertLess(thief.wealth,20)

    def test_need_driven_ai_routes_services_to_real_building_functions(self):
        state=LivingWorldState()
        town=SettlementState(
            uid='settlement:needs',name='Needs',region_x=0,region_y=0,x=10,y=10,population=60,
            culture_id='culture:test',religion_id='religion:test',faction_id='faction:test',
        )
        state.settlements[town.uid]=town
        npc=NPCState(
            uid='npc:healer-patient',name='Patient',age=30,occupation='healer',
            traits=['patient'],x=10,y=10,z=0,settlement_id=town.uid,faction_id=town.faction_id,
            hp=50,
        )
        npc.needs={'social':0,'safety':0,'health':70,'faith':0,'learning':0,'purpose':0}
        state.npcs[npc.uid]=npc
        destinations={
            ('clinic',):(30,30),
            ('market',):(20,20),
            ('watchhouse',):(40,40),
            ('archive','school'):(50,50),
            ('shrine',):(60,60),
            ('market','shrine'):(20,20),
        }
        physical=SimpleNamespace(
            destination_for_function=lambda sid,functions: WorldPos(*destinations.get(tuple(functions),(10,10)),0),
            destination_for=lambda structure_id,room_id='':WorldPos(10,10,0),
        )
        ai=NPCSystem(state,b'needs-test',NullHistory())
        ai.settlement_physicalization=physical
        ai._choose_goal_and_plan(npc,town,600)
        self.assertEqual(npc.goal,'heal')
        self.assertEqual((npc.tasks[0]['x'],npc.tasks[0]['y']),(30,30))


if __name__ == '__main__':
    unittest.main()
