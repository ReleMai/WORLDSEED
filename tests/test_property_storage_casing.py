import unittest
from types import SimpleNamespace

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory
from worldseed.sim.commands import StealContainerCommand, TakeFromContainerCommand
from worldseed.sim.engine import Simulation
from worldseed.systems.building import BuildingSystem
from worldseed.systems.civics import CivicsSystem
from worldseed.systems.economy import EconomySystem
from worldseed.systems.law import LawSystem
from worldseed.systems.physicalization import SettlementPhysicalizationSystem
from worldseed.systems.property_intrusion import CasingSystem, PhysicalKeySystem, PropertySecuritySystem, PropertyStorageSystem
from worldseed.systems.settlement_planner import SettlementSkeletonPlanner
from worldseed.systems.settlement_population import SettlementPopulationBinder
from worldseed.systems.state import CasingIntelState, LivingWorldState, NPCState, SettlementState
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

    def _security_fixture(self):
        base=self._fixture()
        state,town,physical,binder,civics,economy,storage,building,stealth,casing,sync=base
        security=PropertySecuritySystem(
            state,self.registry,b"property-storage-casing",physical,civics
        )
        security.sync_active()
        casing.security=security
        return base,security

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
        self.assertTrue(all(c.lock_level>0 and c.locked for c in containers))

    def test_prepared_workshop_retains_reachable_service_storage_and_real_goods(self):
        from worldseed.systems.interiors import InteriorSystem
        base,security=self._security_fixture()
        state,town,physical,_,_,_,storage,building,_,_,_=base
        workshop=next(s for s in physical.skeleton_for(town.uid).structures if s.function=="smithy")
        container=storage.for_property(workshop.uid)[0]
        frontage=physical.frontage_for(workshop.uid)
        stocks_before=dict(town.stocks)
        contents_before={c.uid:dict(c.items) for c in state.containers.values()}
        location_before=(container.x,container.y,container.z)
        sim=SimpleNamespace(state=state,registry=self.registry,settlement_physicalization=physical,property_security=security)
        sim.interiors=InteriorSystem(sim)
        plan=sim.interiors.prepare_workplace(workshop.uid)
        self.assertIsNotNone(plan)
        storage.sync_active()
        self.assertEqual(town.stocks,stocks_before)
        self.assertEqual({c.uid:dict(c.items) for c in state.containers.values()},contents_before)
        self.assertIs(storage.by_id(container.uid),container)
        self.assertEqual((container.x,container.y,container.z),location_before)
        self.assertFalse(physical.shell_blocks(WorldPos(*location_before)))
        inv=Inventory();messages=[]
        harness=SimpleNamespace(state=state,settlement_physicalization=physical,building=building,
            property_storage=storage,player_pos=frontage,entities=SimpleNamespace(get=lambda *_:inv),_message=messages.append)
        harness._command_container=lambda uid:Simulation._command_container(harness,uid)
        self.assertIs(harness._command_container(container.uid),container)
        item,quantity=next(iter(container.items.items()))
        # Reachability does not bypass the original container's ownership.
        container.locked=False
        Simulation._take_container(harness,TakeFromContainerCommand(1,item,1,container.uid))
        self.assertIn("private",messages[-1])
        self.assertEqual(container.items[item],quantity)
        self.assertEqual(inv.count(item),0)
        container.access="public"
        Simulation._take_container(harness,TakeFromContainerCommand(1,item,1,container.uid))
        self.assertEqual(container.items.get(item,0)+inv.count(item),quantity)
        self.assertEqual(inv.count(item),1)
        self.assertEqual(town.stocks,stocks_before)

    def test_household_storage_command_cannot_reach_through_solid_shell(self):
        from worldseed.systems.interiors import InteriorSystem
        base,security=self._security_fixture()
        state,town,physical,_,_,_,storage,building,_,_,_=base
        house=next(s for s in physical.skeleton_for(town.uid).structures if s.function=="residence")
        container=storage.for_property(house.uid)[0]
        sim=SimpleNamespace(state=state,registry=self.registry,settlement_physicalization=physical,property_security=security)
        sim.interiors=InteriorSystem(sim)
        self.assertIsNotNone(sim.interiors.prepare_workplace(house.uid))
        self.assertTrue(physical.shell_blocks(WorldPos(container.x,container.y,container.z)))
        messages=[];inv=Inventory()
        harness=SimpleNamespace(state=state,settlement_physicalization=physical,building=building,
            interiors=sim.interiors,player_pos=WorldPos(container.x,container.y+1,container.z),
            entities=SimpleNamespace(get=lambda *_:inv),_message=messages.append,
            debug=SimpleNamespace(event=lambda *_args,**_kwargs:None),turn=0,clock=SimpleNamespace(minute=700))
        self.assertIsNone(Simulation._command_container(harness,container.uid))
        stocks_before=dict(town.stocks);contents_before=dict(container.items)
        item=next(iter(container.items))
        Simulation.execute(harness,TakeFromContainerCommand(1,item,1,container.uid))
        self.assertIn("separate building space",messages[-1])
        self.assertEqual(container.items,contents_before)
        self.assertEqual(town.stocks,stocks_before)
        self.assertEqual(inv.count(item),0)
        self.assertEqual(harness.turn,0)

    def test_property_container_lockpick_and_keyholder_state_persist(self):
        state,town,physical,binder,civics,economy,storage,building,stealth,casing,sync=self._fixture()
        container=next(c for c in state.containers.values() if c.kind=="property")
        self.assertTrue(storage.blocks_actor(container,"player"))
        self.assertTrue(storage.grant_keyholder(container.uid,"npc:guest"))
        self.assertFalse(storage.blocks_actor(container,"npc:guest"))
        from worldseed.entities.components import Inventory
        picks=Inventory({"core:lockpick":1})
        ok,msg,cost=storage.attempt_lockpick(container.uid,Inventory(),99,20,20)
        self.assertFalse(ok);self.assertEqual(msg,"You need a lockpick.");self.assertEqual(cost,0)
        opened=False
        for minute in range(100,140):
            ok,msg,cost=storage.attempt_lockpick(container.uid,picks,minute,20,20)
            if ok:opened=True;break
        self.assertTrue(opened);self.assertTrue(container.picked);self.assertFalse(container.locked)
        storage.sync_active();self.assertFalse(container.locked)
        restored=LivingWorldState.from_dict(state.to_dict())
        saved=next(c for c in restored.containers.values() if c.uid==container.uid)
        self.assertTrue(saved.picked);self.assertFalse(saved.locked);self.assertIn("npc:guest",saved.keyholder_uids)

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

        # The old room cells are now a solid exterior shell. Walking around
        # the public perimeter reveals frontage, not the separate interior.
        for x,y in ring:
            p=WorldPos(x,y,0)
            if not physical.passable(p,True):
                continue
            casing.observe_step(p,610,stealth)
        self.assertTrue(intel.entrance_known)
        self.assertTrue(intel.surveyed_cells)
        self.assertNotIn(container.uid,intel.storage_uids)
        self.assertEqual(intel.room_ids,[])

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
        item_id,_=next(iter(container.items.items()))
        guard=state.npcs["npc:guard"]
        state.player_stealth_mode=True
        state.player_casing_property_id=container.property_id
        intel=state.casing_intel.setdefault(
            container.property_id,
            CasingIntelState(container.property_id,container.settlement_id,owner_uid=container.owner),
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
        container.locked=False;container.picked=True
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
            CasingIntelState(container.property_id,container.settlement_id,owner_uid=container.owner),
        )
        intel.sessions=3;intel.suspicion=27;intel.alarm_level=1;intel.storage_uids=[container.uid]
        restored=LivingWorldState.from_dict(state.to_dict())
        loaded=next(c for c in restored.containers.values() if c.uid==container.uid)
        self.assertEqual(loaded.property_id,container.property_id)
        self.assertTrue(loaded.seeded_from_settlement)
        self.assertEqual(restored.player_casing_property_id,container.property_id)
        self.assertEqual(restored.casing_intel[container.property_id].suspicion,27)
        self.assertEqual(restored.casing_intel[container.property_id].storage_uids,[container.uid])



    def test_generated_doors_have_stable_permissions_and_locks(self):
        base,security=self._security_fixture()
        state,town,physical,binder,civics,economy,storage,building,stealth,casing,sync=base
        skeleton=physical.skeleton_for(town.uid)
        residence=next(s for s in skeleton.structures if s.function=="residence")
        entrance=next(d for d in security.doors_for_property(residence.uid) if d.role=="entrance")
        self.assertEqual(entrance.access,"private")
        self.assertTrue(entrance.locked)
        self.assertGreater(entrance.lock_level,0)
        self.assertEqual(physical.door_at(WorldPos(entrance.x,entrance.y,0)).structure_piece_uid,entrance.uid)
        entrance.locked=False;entrance.picked=True
        security.sync_active()
        self.assertFalse(state.door_security[entrance.uid].locked)
        self.assertTrue(state.door_security[entrance.uid].picked)
        public=[
            d for d in state.door_security.values()
            if d.role=="entrance" and security._function(d.property_id) in security.PUBLIC_ENTRANCES
        ]
        self.assertTrue(public)
        self.assertTrue(all(d.access=="public" and not d.locked for d in public))


    def test_actor_access_uses_home_work_and_explicit_keyholder_authority(self):
        base,security=self._security_fixture()
        state,town,physical,binder,civics,economy,storage,building,stealth,casing,sync=base
        resident=next(n for n in state.npcs.values() if n.home_id)
        residence=physical.structure_by_id(resident.home_id)
        self.assertIsNotNone(residence)
        door=next(d for d in security.doors_for_property(residence.uid) if d.role=="entrance")
        stranger=next(n for n in state.npcs.values() if n.uid!=resident.uid and n.home_id!=residence.uid)
        pos=WorldPos(door.x,door.y,door.z)
        self.assertTrue(door.locked)
        self.assertTrue(security.authorized_actor(door,resident.uid))
        self.assertFalse(security.blocks_actor(pos,resident.uid,23*60))
        self.assertFalse(security.authorized_actor(door,stranger.uid))
        self.assertTrue(security.blocks_actor(pos,stranger.uid,23*60))
        self.assertTrue(security.blocks_player(pos))
        self.assertGreater(security.grant_keyholder(residence.uid,"player"),0)
        self.assertTrue(security.authorized_player(door))
        self.assertFalse(security.blocks_player(pos))
        restored=LivingWorldState.from_dict(state.to_dict())
        self.assertIn("player",restored.door_security[door.uid].keyholder_uids)

    def test_workplace_schedule_locks_only_intact_unpicked_work_doors(self):
        base,security=self._security_fixture()
        state,town,physical,binder,civics,economy,storage,building,stealth,casing,sync=base
        skeleton=physical.skeleton_for(town.uid)
        workplace=next(
            s for s in skeleton.structures
            if s.function in security.WORK_OPEN_HOURS and security.doors_for_property(s.uid)
        )
        door=next(d for d in security.doors_for_property(workplace.uid) if d.role=="entrance")
        worker=state.npcs["npc:owner"]
        worker.workplace_id=workplace.uid
        pos=WorldPos(door.x,door.y,door.z)
        security.update_scheduled_locks(23*60)
        self.assertTrue(door.locked)
        self.assertTrue(door.schedule_locked)
        self.assertGreater(door.lock_level,0)
        self.assertTrue(security.authorized_actor(door,worker.uid))
        self.assertFalse(security.blocks_actor(pos,worker.uid,23*60))
        self.assertTrue(security.blocks_player(pos))
        public=next(
            d for d in state.door_security.values()
            if d.role=="entrance" and security._function(d.property_id) in security.PUBLIC_OPEN_HOURS
        )
        self.assertTrue(public.locked)
        self.assertTrue(public.schedule_locked)
        self.assertGreater(public.lock_level,0)
        self.assertTrue(security.blocks_player(WorldPos(public.x,public.y,public.z)))
        security.update_scheduled_locks(10*60)
        self.assertFalse(door.locked)
        self.assertFalse(door.schedule_locked)
        security.update_scheduled_locks(23*60)
        self.assertTrue(door.locked)
        door.locked=False;door.picked=True;door.schedule_locked=False
        security.update_scheduled_locks(23*60+60)
        self.assertFalse(door.locked)
        self.assertFalse(door.schedule_locked)

    def test_casing_discovers_door_and_lock_only_when_physically_observed(self):
        base,security=self._security_fixture()
        state,town,physical,binder,civics,economy,storage,building,stealth,casing,sync=base
        skeleton=physical.skeleton_for(town.uid)
        residence=next(s for s in skeleton.structures if s.function=="residence")
        door=next(d for d in security.doors_for_property(residence.uid) if d.role=="entrance")
        ring=sorted(casing._perimeter(residence))
        far=max(ring,key=lambda p:abs(p[0]-door.x)+abs(p[1]-door.y))
        ok,_=casing.start(residence.uid,WorldPos(far[0],far[1],0),600,stealth)
        self.assertTrue(ok)
        casing.observe_step(WorldPos(far[0],far[1],0),600,stealth)
        intel=casing.intel_for(residence.uid)
        self.assertNotIn(door.uid,intel.lock_uids)
        adjacent=[
            WorldPos(door.x+dx,door.y+dy,0)
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1))
            if (door.x+dx,door.y+dy) not in set(residence.footprint)
        ]
        self.assertTrue(adjacent)
        casing.observe_step(adjacent[0],610,stealth)
        self.assertIn(door.uid,intel.door_uids)
        self.assertIn(door.uid,intel.lock_uids)

    def test_lock_tampering_and_forced_entry_create_security_not_theft(self):
        base,security=self._security_fixture()
        state,town,physical,binder,civics,economy,storage,building,stealth,casing,sync=base
        residence=next(
            s for s in physical.skeleton_for(town.uid).structures if s.function=="residence"
        )
        door=next(d for d in security.doors_for_property(residence.uid) if d.role=="entrance")
        watcher=AlwaysWatching("npc:guard")
        inv=Inventory({"core:lockpick":1,"core:stone_hammer":1})
        adjacent=WorldPos(door.x+1,door.y,0)
        security.attempt_lockpick(door.uid,inv,adjacent,700,watcher,skill=2,agility=6)
        self.assertTrue(any(row.kind=="lock_tampering" for row in state.security_incidents.values()))
        self.assertFalse(state.theft_records)
        self.assertGreater(state.player_crime_heat.get(town.uid,0),0)
        door.locked=True;door.forced=False;door.condition=18
        ok,msg,minutes,noise=security.force_entry(
            door.uid,inv,adjacent,710,watcher,strength=7
        )
        self.assertTrue(ok)
        self.assertTrue(door.forced)
        self.assertFalse(door.locked)
        self.assertGreater(noise,0)
        self.assertTrue(any(row.kind=="forced_entry" for row in state.security_incidents.values()))

    def test_trespass_warning_escalates_to_guard_search(self):
        base,security=self._security_fixture()
        state,town,physical,binder,civics,economy,storage,building,stealth,casing,sync=base
        residence=next(
            s for s in physical.skeleton_for(town.uid).structures if s.function=="residence"
        )
        door=next(d for d in security.doors_for_property(residence.uid) if d.role=="entrance")
        door.locked=False;door.picked=True
        footprint=set(residence.footprint)
        exterior=next(
            WorldPos(door.x+dx,door.y+dy,0)
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1))
            if (door.x+dx,door.y+dy) not in footprint
        )
        watcher=AlwaysWatching("npc:guard")
        messages=security.note_player_step(exterior,WorldPos(door.x,door.y,0),720,watcher)
        self.assertEqual(state.player_trespass_property_id,residence.uid)
        self.assertTrue(state.trespass_states[residence.uid].active)
        first=security.update_response(WorldPos(door.x,door.y,0),721,watcher)
        second=security.update_response(WorldPos(door.x,door.y,0),722,watcher)
        self.assertTrue(any("orders you out" in row for row in first))
        self.assertTrue(any("active search" in row for row in second))
        self.assertGreaterEqual(state.trespass_states[residence.uid].search_level,2)
        guard=state.npcs["npc:guard"]
        self.assertEqual(guard.goal,"guard")
        self.assertTrue(guard.tasks)

    def test_security_state_roundtrips_and_law_can_resolve_witnessed_intrusion(self):
        base,security=self._security_fixture()
        state,town,physical,binder,civics,economy,storage,building,stealth,casing,sync=base
        residence=next(
            s for s in physical.skeleton_for(town.uid).structures if s.function=="residence"
        )
        door=next(d for d in security.doors_for_property(residence.uid) if d.role=="entrance")
        state.player_trespass_property_id=residence.uid
        security._incident(door,"forced_entry",800,("npc:guard",),14)
        restored=LivingWorldState.from_dict(state.to_dict())
        self.assertIn(door.uid,restored.door_security)
        self.assertEqual(restored.player_trespass_property_id,residence.uid)
        self.assertTrue(restored.security_incidents)
        history=NullHistory();law=LawSystem(restored,b"property-storage-casing",history)
        for day in range(1,40):
            law.daily_update(800+day*1440)
            if all(row.resolved for row in restored.security_incidents.values()):
                break
        self.assertTrue(all(row.resolved for row in restored.security_incidents.values()))
        self.assertGreater(restored.player_bounties.get(town.uid,0),0)

    def test_physical_keys_unlock_transfer_duplicate_and_roundtrip(self):
        base,security=self._security_fixture();state,town,physical,binder,civics,economy,storage,building,stealth,casing,sync=base
        keys=PhysicalKeySystem(state,b"property-storage-casing");storage.keys=keys;security.keys=keys
        container=next(c for c in state.containers.values() if c.kind=="property" and c.locked);key=keys.ensure_key(container,"player","Household key",120)
        self.assertFalse(storage.blocks_actor(container,"player"));self.assertTrue(storage.blocks_actor(container,"npc:guest"))
        copy=keys.duplicate(key.uid,"player",121);self.assertEqual(copy.lock_uid,key.lock_uid);self.assertEqual(copy.copied_from_uid,key.uid)
        self.assertTrue(keys.transfer(copy.uid,"player","npc:guest"));self.assertFalse(storage.blocks_actor(container,"npc:guest"))
        door=next(d for d in state.door_security.values() if d.locked);door_key=keys.ensure_key(door,"player","Door key",122)
        self.assertFalse(security.blocks_actor(WorldPos(door.x,door.y,door.z),"player"))
        restored=LivingWorldState.from_dict(state.to_dict());self.assertEqual(restored.physical_keys[key.uid].lock_uid,key.lock_uid);self.assertEqual(restored.physical_keys[copy.uid].owner_uid,"npc:guest");self.assertEqual(restored.physical_keys[door_key.uid].owner_uid,"player")

    def test_key_lock_controls_and_picked_lock_safety(self):
        base,security=self._security_fixture();state,town,physical,binder,civics,economy,storage,building,stealth,casing,sync=base
        keys=PhysicalKeySystem(state,b"property-storage-casing");storage.keys=keys;security.keys=keys
        container=next(c for c in state.containers.values() if c.kind=="property" and c.locked);keys.ensure_key(container,"player","Chest key",1)
        ok,msg=storage.set_locked_with_key(container.uid,"player",False);self.assertTrue(ok);self.assertFalse(container.locked)
        ok,msg=storage.set_locked_with_key(container.uid,"player",True);self.assertTrue(ok);self.assertTrue(container.locked)
        container.locked=False;container.picked=True;ok,msg=storage.set_locked_with_key(container.uid,"player",True);self.assertFalse(ok);self.assertFalse(container.locked)
        door=next(d for d in state.door_security.values() if d.locked);keys.ensure_key(door,"player","Door key",2)
        ok,msg=security.set_locked_with_key(door.uid,"player",False);self.assertTrue(ok);self.assertFalse(door.locked);self.assertFalse(door.schedule_locked)
        ok,msg=security.set_locked_with_key(door.uid,"npc:stranger",True);self.assertFalse(ok);self.assertFalse(door.locked)

if __name__=="__main__":
    unittest.main()
