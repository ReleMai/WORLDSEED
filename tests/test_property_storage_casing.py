import unittest
from types import SimpleNamespace

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory
from worldseed.sim.commands import StealContainerCommand
from worldseed.sim.engine import Simulation
from worldseed.systems.building import BuildingSystem
from worldseed.systems.civics import CivicsSystem
from worldseed.systems.economy import EconomySystem
from worldseed.systems.physicalization import SettlementPhysicalizationSystem
from worldseed.systems.property_intrusion import CasingSystem, PropertyStorageSystem
from worldseed.systems.settlement_planner import SettlementSkeletonPlanner
from worldseed.systems.settlement_population import SettlementPopulationBinder
from worldseed.systems.state import LivingWorldState, NPCState, SettlementState
from worldseed.systems.stealth import StealthSystem
from worldseed.world.region_blocks import RegionBlockPlan, RegionRoadExit


class NullHistory:
    def __init__(self):
        self.rows=[]
    def record(self,*args,**kwargs):
        self.rows.append((args,kwargs))


class MemoryCache:
    def __init__(self):
        self.rows={}
    def load_generated_settlement_plan(self,uid,version):
        return self.rows.get((uid,version))
    def store_generated_settlement_plan(self,uid,version,payload):
        self.rows[(uid,version)]=payload
    def commit_generated(self):
        pass


class OpenResources:
    def blocks_sight(self,pos):
        return False


class ClearEnvironment:
    def visual_conditions(self,minute,pos):
        return ({"visibility":8,"fog":0},SimpleNamespace(ambient_light=65535))


class AlwaysWatching:
    def __init__(self,uid):
        self.uid=uid
    def witnesses(self,pos,minute,settlement_id=""):
        return (self.uid,)
    def visible_from(self,origin,target):
        return True


class PropertyStorageCasingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)

    def _fixture(self):
        cache=MemoryCache()
        env=SimpleNamespace(
            open_water=False,slope=3,flood_risk=2,wetness=40,
            soil_fertility=80,farmland=84,
            resources=SimpleNamespace(stone=72,timber=70,freshwater=66),
            resource_opportunity=74,
        )
        ground=SimpleNamespace(terrain=SimpleNamespace(blocks_sight=False))
        world=SimpleNamespace(
            generator=SimpleNamespace(world_seed=b"property-storage-casing"),
            delta_source=cache,registry=self.registry,
            environment_at=lambda pos:env,tile_at=lambda pos:ground,
        )
        region=RegionBlockPlan(
            uid="casing-region",region_x=0,region_y=0,version=1,
            dominant_biome="grassland",biome_mix={"grassland":20},
            mean_elevation=1,mean_moisture=1,mean_temperature=1,relief=1,
            settlement_present=True,settlement_anchor=(180,180),settlement_score=90,
            settlement_archetype="river_market",control_potential="settled",
            roads=(
                RegionRoadExit("north",180,"road"),
                RegionRoadExit("east",180,"road"),
                RegionRoadExit("south",180,"road"),
                RegionRoadExit("west",180,"road"),
            ),
        )
        region_planner=SimpleNamespace(plan=lambda rx,ry,persist=True:region)
        planner=SettlementSkeletonPlanner(world)
        physical=SettlementPhysicalizationSystem(world,self.registry,region_planner,planner)
        town=SettlementState(
            uid="settlement:casing",name="Sightford",region_x=0,region_y=0,
            x=180,y=180,population=120,culture_id="culture:test",
            religion_id="religion:test",faction_id="faction:test",
            stocks={
                "core:wheat":80,"core:turnip":30,"core:dried_meat":20,
                "core:clean_water":30,"core:soap":12,"core:wood":70,
                "core:stone":50,"core:iron_bloom":16,"core:leather":12,
                "core:herbal_tonic":10,"core:book":6,
            },
            law={"theft":100,"tax":5},
        )
        state=LivingWorldState();state.settlements[town.uid]=town
        for uid,name,occ in (
            ("npc:owner","Mara","merchant"),
            ("npc:guard","Tomas","guard"),
            ("npc:healer","Eda","healer"),
        ):
            state.npcs[uid]=NPCState(
                uid=uid,name=name,age=34,occupation=occ,traits=["patient"],
                x=180,y=180,z=0,settlement_id=town.uid,faction_id=town.faction_id,
                wealth=80,
            )
        physical.sync([town],(0,0),radius=0)
        binder=SettlementPopulationBinder(state,self.registry,b"property-storage-casing",physical)
        binder.bind_settlement(town)
        history=NullHistory()
        civics=CivicsSystem(state,b"property-storage-casing",history)
        civics.attach_settlement_physicalization(physical)
        civics.ensure_settlement(town.uid)
        economy=EconomySystem(state,self.registry,b"property-storage-casing",history)
        economy.update_prices()
        storage=PropertyStorageSystem(state,self.registry,b"property-storage-casing",physical,civics)
        sync=storage.sync_active()
        building=BuildingSystem(state,self.registry)
        building.attach_settlement_physicalization(physical)
        stealth=StealthSystem(
            state,b"property-storage-casing",world,OpenResources(),building,physical,ClearEnvironment()
        )
        casing=CasingSystem(state,physical,civics,storage)
        return state,town,physical,binder,civics,economy,storage,building,stealth,casing,sync

    def test_property_storage_is_stable_owned_and_reserves_real_stock(self):
        state,town,physical,binder,civics,economy,storage,building,stealth,casing,sync=self._fixture()
        containers=[c for c in state.containers.values() if c.kind=="property"]
        self.assertTrue(containers)
        skeleton=physical.skeleton_for(town.uid)
        valid_structures={s.uid for s in skeleton.structures}
        self.assertTrue(all(c.property_id in valid_structures for c in containers))
        self.assertTrue(all(c.owner==civics.owner_for_structure(town.uid,c.property_id) for c in containers))
        self.assertTrue(all(c.source_id in self.registry.structures for c in containers))
        reserved=sum(sum(c.items.values()) for c in containers)
        self.assertGreater(reserved,0)
        stocks_before=dict(town.stocks)
        container_before={c.uid:dict(c.items) for c in containers}
        storage.sync_active()
        self.assertEqual(stocks_before,town.stocks)
        self.assertEqual(container_before,{c.uid:dict(c.items) for c in state.containers.values() if c.kind=="property"})
        self.assertTrue(all(c.seeded_from_settlement for c in containers))

    def test_casing_learns_by_movement_not_by_starting_mode(self):
        state,town,physical,binder,civics,economy,storage,building,stealth,casing,sync=self._fixture()
        skeleton=physical.skeleton_for(town.uid)
        residence=next(s for s in skeleton.structures if s.function=="residence")
        container=storage.for_property(residence.uid)[0]
        ring=sorted(casing._perimeter(residence))
        self.assertTrue(ring)
        # Start at the exterior point farthest from storage so the first click
        # cannot reveal the home's interior inventory.
        sx,sy=max(ring,key=lambda p:abs(p[0]-container.x)+abs(p[1]-container.y))
        start=WorldPos(sx,sy,0)
        ok,msg=casing.start(residence.uid,start,600,stealth)
        self.assertTrue(ok)
        intel=casing.intel_for(residence.uid)
        self.assertEqual(intel.storage_uids,[])
        casing.observe_step(start,600,stealth)
        self.assertGreater(casing.summary(residence.uid)["survey_progress"],0)
        self.assertEqual(intel.storage_uids,[])

        room=physical.room_by_id(container.room_id)
        adjacent=[
            WorldPos(int(x),int(y),0) for x,y in room.cells
            if (int(x),int(y))!=(container.x,container.y)
            and abs(int(x)-container.x)+abs(int(y)-container.y)<=2
        ]
        self.assertTrue(adjacent)
        for p in adjacent:
            casing.observe_step(p,610,stealth)
            if container.uid in intel.storage_uids:
                break
        self.assertIn(container.uid,intel.storage_uids)
        self.assertGreaterEqual(len(intel.room_ids),1)

    def test_repeated_observed_casing_raises_alarm_without_creating_crime(self):
        state,town,physical,binder,civics,economy,storage,building,stealth,casing,sync=self._fixture()
        skeleton=physical.skeleton_for(town.uid)
        residence=next(s for s in skeleton.structures if s.function=="residence")
        owner=state.npcs["npc:owner"]
        town.property_owners[residence.uid]=owner.uid
        state.properties[residence.uid].owner_uid=owner.uid
        watcher=AlwaysWatching(owner.uid)
        ring=sorted(casing._perimeter(residence))
        self.assertGreaterEqual(len(ring),4)
        minute=600
        for session in range(4):
            p=WorldPos(ring[session%len(ring)][0],ring[session%len(ring)][1],0)
            ok,_=casing.start(residence.uid,p,minute,watcher)
            self.assertTrue(ok)
            casing.observe_step(p,minute,watcher)
            casing.stop()
            minute+=20
        intel=casing.intel_for(residence.uid)
        self.assertGreaterEqual(intel.sessions,4)
        self.assertGreaterEqual(intel.suspicion,20)
        self.assertGreaterEqual(intel.alarm_level,1)
        self.assertFalse(state.theft_records)
        self.assertFalse(state.player_bounties)

    def test_storage_theft_uses_real_container_and_sight_witnesses(self):
        state,town,physical,binder,civics,economy,storage,building,stealth,casing,sync=self._fixture()
        container=next(c for c in state.containers.values() if c.kind=="property" and c.items)
        item_id,next_qty=next(iter(container.items.items()))
        guard=state.npcs["npc:guard"]
        state.player_stealth_mode=True
        state.player_casing_property_id=container.property_id
        intel=state.casing_intel.setdefault(
            container.property_id,
            __import__("worldseed.systems.state",fromlist=["CasingIntelState"]).CasingIntelState(
                container.property_id,container.settlement_id,owner_uid=container.owner
            ),
        )
        intel.storage_uids=[container.uid]
        inv=Inventory()
        messages=[]
        harness=SimpleNamespace(
            state=state,registry=self.registry,economy=economy,civics=civics,
            entities=SimpleNamespace(get=lambda actor,typ:inv),
            player_pos=WorldPos(container.x,container.y+1,container.z),
            clock=SimpleNamespace(minute=700),
            stealth=SimpleNamespace(witnesses=lambda pos,minute,settlement_id:(guard.uid,)),
            _command_container=lambda uid:container if uid==container.uid else None,
            _message=messages.append,
        )
        before=container.items[item_id]
        Simulation._steal_container(harness,StealContainerCommand(1,container.uid,item_id,1))
        self.assertEqual(container.items.get(item_id,0),before-1)
        self.assertEqual(inv.count(item_id),1)
        theft=next(reversed(state.theft_records.values()))
        self.assertEqual(theft.property_id,container.property_id)
        self.assertEqual(theft.source_kind,"property_storage")
        self.assertIn(guard.uid,theft.witness_uids)
        self.assertGreater(state.player_crime_heat.get(town.uid,0),0)

    def test_property_storage_and_casing_roundtrip(self):
        state,town,physical,binder,civics,economy,storage,building,stealth,casing,sync=self._fixture()
        container=next(c for c in state.containers.values() if c.kind=="property")
        state.player_casing_property_id=container.property_id
        intel=state.casing_intel.setdefault(
            container.property_id,
            __import__("worldseed.systems.state",fromlist=["CasingIntelState"]).CasingIntelState(
                container.property_id,container.settlement_id,owner_uid=container.owner
            ),
        )
        intel.sessions=3;intel.suspicion=27;intel.alarm_level=1;intel.storage_uids=[container.uid]
        restored=LivingWorldState.from_dict(state.to_dict())
        loaded=next(c for c in restored.containers.values() if c.uid==container.uid)
        self.assertEqual(loaded.property_id,container.property_id)
        self.assertTrue(loaded.seeded_from_settlement)
        self.assertEqual(restored.player_casing_property_id,container.property_id)
        self.assertEqual(restored.casing_intel[container.property_id].suspicion,27)
        self.assertEqual(restored.casing_intel[container.property_id].storage_uids,[container.uid])


if __name__=="__main__":
    unittest.main()
