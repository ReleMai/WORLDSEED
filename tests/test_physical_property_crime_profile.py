import os
os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')

import unittest
from types import SimpleNamespace

from worldseed.app import _npc_profile_data
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory
from worldseed.sim.commands import StealMarketCommand
from worldseed.sim.engine import Simulation
from worldseed.systems.civics import CivicsSystem
from worldseed.systems.economy import EconomySystem
from worldseed.systems.law import LawSystem
from worldseed.systems.physicalization import SettlementPhysicalizationSystem
from worldseed.systems.settlement_planner import SettlementSkeletonPlanner
from worldseed.systems.settlement_population import SettlementPopulationBinder
from worldseed.systems.state import LivingWorldState, NPCState, SettlementState
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.world.region_blocks import RegionBlockPlan, RegionRoadExit


class NullHistory:
    def __init__(self):self.rows=[]
    def record(self,*args,**kwargs):self.rows.append((args,kwargs))


class MemoryCache:
    def __init__(self):self.rows={}
    def load_generated_settlement_plan(self,uid,version):return self.rows.get((uid,version))
    def store_generated_settlement_plan(self,uid,version,payload):self.rows[(uid,version)]=payload
    def commit_generated(self):pass


class PhysicalPropertyCrimeProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)

    def _fixture(self):
        cache=MemoryCache()
        env=SimpleNamespace(
            open_water=False,slope=3,flood_risk=2,wetness=45,
            soil_fertility=78,farmland=82,
            resources=SimpleNamespace(stone=72,timber=68,freshwater=61),
            resource_opportunity=70,
        )
        world=SimpleNamespace(
            generator=SimpleNamespace(world_seed=b'physical-property-crime'),
            delta_source=cache,
            registry=self.registry,
            environment_at=lambda pos:env,
        )
        region=RegionBlockPlan(
            uid='property-region',region_x=0,region_y=0,version=1,
            dominant_biome='grassland',biome_mix={'grassland':20},
            mean_elevation=1,mean_moisture=1,mean_temperature=1,relief=1,
            settlement_present=True,settlement_anchor=(180,180),settlement_score=90,
            settlement_archetype='river_market',control_potential='settled',
            roads=(
                RegionRoadExit('north',180,'road'),RegionRoadExit('east',180,'road'),
                RegionRoadExit('south',180,'road'),RegionRoadExit('west',180,'road'),
            ),
        )
        region_planner=SimpleNamespace(plan=lambda rx,ry,persist=True:region)
        planner=SettlementSkeletonPlanner(world)
        physical=SettlementPhysicalizationSystem(world,self.registry,region_planner,planner)
        town=SettlementState(
            uid='settlement:property',name='Rivermarket',region_x=0,region_y=0,
            x=180,y=180,population=120,culture_id='culture:test',
            religion_id='religion:test',faction_id='faction:test',
            stocks={'core:wheat':60,'core:wood':40,'core:stone':30},
            law={'theft':100,'tax':5},
        )
        state=LivingWorldState();state.settlements[town.uid]=town
        residents=(
            ('npc:merchant','Mara',37,'merchant'),
            ('npc:guard','Tomas',42,'guard'),
            ('npc:healer','Eda',31,'healer'),
        )
        for uid,name,age,occ in residents:
            state.npcs[uid]=NPCState(
                uid=uid,name=name,age=age,occupation=occ,traits=['patient','kind'],
                x=180,y=180,z=0,settlement_id=town.uid,faction_id=town.faction_id,
                wealth=80,
            )
        physical.sync([town],(0,0),radius=0)
        binder=SettlementPopulationBinder(state,self.registry,b'physical-property-crime',physical)
        binder.bind_settlement(town)
        history=NullHistory()
        civics=CivicsSystem(state,b'physical-property-crime',history)
        civics.attach_settlement_physicalization(physical)
        civics.ensure_settlement(town.uid)
        economy=EconomySystem(state,self.registry,b'physical-property-crime',history)
        economy.update_prices()
        return state,town,physical,binder,civics,economy,history

    def test_civics_uses_physical_structures_as_property_authority(self):
        state,town,physical,binder,civics,economy,history=self._fixture()
        skeleton=physical.skeleton_for(town.uid)
        structure_ids={s.uid for s in skeleton.structures if not s.destroyed}
        active={p.uid:p for p in civics._properties(town.uid)}
        self.assertTrue(active)
        self.assertTrue(set(active).issubset(structure_ids))
        self.assertFalse(any(uid.startswith(f'property:{town.uid}:') for uid in active))
        market=next(s for s in skeleton.structures if s.function=='market')
        self.assertEqual(active[market.uid].kind,'shop')
        for npc in state.npcs.values():
            home=next(s for s in skeleton.structures if s.uid==npc.home_id)
            if home.function=='residence':self.assertEqual(npc.property_id,npc.home_id)
            else:self.assertFalse(npc.property_id)
            self.assertIn(npc.home_id,active)
            self.assertIn(npc.uid,active[npc.home_id].occupants)
        before={n.uid:n.home_id for n in state.npcs.values()}
        civics.monthly_update(30*1440)
        self.assertEqual(before,{n.uid:n.home_id for n in state.npcs.values()})

    def test_player_market_theft_records_real_property_witness_and_bounty(self):
        state,town,physical,binder,civics,economy,history=self._fixture()
        market_pos=physical.destination_for_function(town.uid,('market',))
        self.assertIsNotNone(market_pos)
        skeleton=physical.skeleton_for(town.uid)
        market=next(s for s in sorted(skeleton.structures,key=lambda s:s.uid) if s.function=='market' and not s.destroyed)
        self.assertFalse(physical.shell_blocks(market_pos))
        guard=state.npcs['npc:guard']
        guard.x,guard.y,guard.z=market_pos.x+1,market_pos.y,0
        inv=Inventory()
        messages=[]
        state.player_stealth_mode=True
        harness=SimpleNamespace(
            state=state,registry=self.registry,economy=economy,civics=civics,
            settlement_physicalization=physical,entities=SimpleNamespace(get=lambda actor,typ:inv),
            player_pos=market_pos,clock=SimpleNamespace(minute=600),
            stealth=SimpleNamespace(witnesses=lambda pos,minute,settlement_id:(guard.uid,)),
            _message=lambda message:messages.append(message),
        )
        before=town.stocks['core:wheat']
        Simulation._steal_market(harness,StealMarketCommand(1,town.uid,'core:wheat',2))
        self.assertEqual(town.stocks['core:wheat'],before-2)
        self.assertEqual(inv.count('core:wheat'),2)
        theft=next(reversed(state.theft_records.values()))
        self.assertEqual(theft.thief_uid,'player')
        self.assertEqual(theft.property_id,market.uid)
        self.assertEqual(theft.source_kind,'market')
        self.assertIn(guard.uid,theft.witness_uids)
        self.assertGreater(state.player_crime_heat[town.uid],0)
        law=LawSystem(state,b'physical-property-crime',history)
        for day in range(1,30):
            law.daily_update(day*1440)
            if theft.resolved:break
        self.assertTrue(theft.resolved)
        self.assertGreater(state.player_bounties.get(town.uid,0),0)

    def test_npc_profile_reveals_known_people_without_raw_ids(self):
        state,town,physical,binder,civics,economy,history=self._fixture()
        npc=state.npcs['npc:merchant'];spouse=state.npcs['npc:healer']
        state.introduced_npcs.append(npc.uid)
        npc.spouse_uid=spouse.uid;npc.kinship[spouse.uid]='spouse'
        npc.relationships['player']={'affection':15,'trust':25,'fear':0,'respect':12,'familiarity':40}
        npc.relationships[spouse.uid]={'affection':70,'trust':65,'fear':0,'respect':30,'familiarity':90}
        npc.backstory={'birthplace':town.name,'upbringing':'market household','formative_event':'hard winter','ambition':'build a reliable trade'}
        npc.wants=['build a reliable trade','family security']
        npc.needs={'social':65,'safety':10,'health':0,'faith':5,'learning':20,'purpose':35}
        sim=SimpleNamespace(
            state=state,settlement_physicalization=physical,
            known_npc_ids=lambda:{npc.uid},
            known_settlement_ids=lambda:{town.uid},
        )
        data=_npc_profile_data(sim,npc,'family')
        family_text=' '.join(str(v) for row in data['tabs']['family'] for v in row)
        self.assertNotIn(spouse.name,family_text)
        self.assertNotIn(spouse.uid,family_text)
        sim.known_npc_ids=lambda:{npc.uid,spouse.uid}
        data=_npc_profile_data(sim,npc,'family')
        family_text=' '.join(str(v) for row in data['tabs']['family'] for v in row)
        self.assertIn(spouse.name,family_text)
        rendered=str(data)
        self.assertNotIn(npc.uid,rendered)
        self.assertNotIn(npc.home_id,rendered)


@unittest.skipUnless(PygameTerminal.available(),'pygame optional')
class NPCProfileRenderTests(unittest.TestCase):
    def test_profile_panel_is_movable_resizable_and_scoped(self):
        term=PygameTerminal();term.enter()
        try:
            rows=[
                SimpleNamespace(key='overview',label='Overview'),
                SimpleNamespace(key='family',label='Family'),
                SimpleNamespace(key='relations',label='Relations'),
                SimpleNamespace(key='needs',label='Needs'),
                SimpleNamespace(key='history',label='History'),
            ]
            data={
                'active_tab':'overview',
                'summary':{
                    'name':'Mara','age':37,'occupation':'Merchant',
                    'settlement':'Rivermarket','activity':'Socialize',
                    'traits':['Patient','Kind'],
                },
                'tabs':{
                    'overview':[('Age','37'),('Occupation','Merchant'),('Home','Residence')],
                    'family':[('Spouse','Eda, age 31')],
                    'relations':[('Eda','Close · Spouse')],
                    'needs':[('Social','high',65),('Safety','low',10)],
                    'history':[('Social','Eda')],
                },
            }
            for size in ((800,520),(1280,800),(1920,1080)):
                term._resize(*size)
                term.present_feature_menu(
                    'npc_profile','Mara',rows,0,
                    subtitle='Merchant · Rivermarket · Socialize',data=data,
                )
                screen=term.screen.get_rect()
                tokens={token for rect,token in term._pointer_targets if screen.contains(rect)}
                self.assertTrue(all(screen.contains(rect) for rect,_ in term._pointer_targets))
                self.assertIn('UI_SELECT:0',tokens)
                self.assertIn('UI_SELECT:4',tokens)
                self.assertIn('UI_WINDOW_DRAG:npc_profile',tokens)
                self.assertIn('UI_WINDOW_RESIZE:npc_profile',tokens)
                self.assertIn('ESC',tokens)
        finally:
            term.restore()


if __name__=='__main__':
    unittest.main()
