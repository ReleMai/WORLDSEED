"""Dev45 physical farm layouts and real named-farmer execution."""
import unittest
import subprocess
import sys
import tempfile
from collections import deque
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

from tests import test_dev43_settlement_diversity as settlement_fixtures
from tests import test_phase4_professions as profession_fixtures
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.persistence.database import WorldDatabase
from worldseed.core.coords import WorldPos
from worldseed.systems.farm_compounds import farm_compound, starting_farm_seeds, terrain_crop_ids
from worldseed.systems.ai import NPCSystem
from worldseed.systems.generation import ProceduralSocietyGenerator
from worldseed.systems.physicalization import SettlementPhysicalizationSystem
from worldseed.systems.settlement_planner import SettlementSkeleton, SettlementSkeletonPlanner
from worldseed.systems.settlement_population import SettlementPopulationBinder
from worldseed.systems.state import CropPlot, LivingWorldState, NPCState, SettlementState, pos_key
from worldseed.world.region_blocks import RegionBlockPlan, RegionRoadExit


class MemoryCache:
    def __init__(self):
        self.rows = {}
    def load_generated_settlement_plan(self, uid, version):
        return self.rows.get((uid,version))
    def store_generated_settlement_plan(self, uid, version, data):
        self.rows[(uid,version)] = data
    def load_physical_plan_deltas(self, *args):
        return []
    def commit_generated(self):
        pass


class FarmCompoundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    def world(self, version=10, cache=None):
        return SimpleNamespace(
            generator=SimpleNamespace(world_seed=b"dev45-farms"),
            delta_source=cache or settlement_fixtures.Cache(), registry=self.registry,
            settlement_plan_version=version,
            environment_at=lambda pos: settlement_fixtures.Env(),
        )

    def region(self):
        return RegionBlockPlan(
            uid="region:farms",region_x=0,region_y=0,version=1,
            dominant_biome="grassland",biome_mix={"grassland":25},
            mean_elevation=1,mean_moisture=1,mean_temperature=1,relief=1,
            settlement_present=True,settlement_anchor=(180,180),settlement_score=88,
            settlement_archetype="agrarian",control_potential="settled",
            roads=(RegionRoadExit("north",180,"road"),RegionRoadExit("east",180,"road")),
        )

    def skeleton(self, version=10, population=45):
        return SettlementSkeletonPlanner(self.world(version)).plan(
            self.region(),"settlement:farms",population,persist=False,
        )

    def physical(self,skeleton):
        physical=SettlementPhysicalizationSystem(self.world(),self.registry,None,None)
        physical._skeletons[skeleton.plan.settlement_id]=skeleton
        physical._index_skeleton(skeleton.plan.settlement_id,skeleton)
        return physical

    def test_connected_large_compound_has_external_service_court(self):
        layout=farm_compound((40,40),(0,1),"village")
        self.assertGreater(len(layout.extent),1000)
        self.assertFalse(layout.extent & layout.court)
        seen={layout.gate};queue=deque(seen)
        while queue:
            x,y=queue.popleft()
            for dx,dy in ((0,1),(0,-1),(1,0),(-1,0)):
                p=(x+dx,y+dy)
                if p in layout.extent and p not in seen:seen.add(p);queue.append(p)
        self.assertEqual(set(layout.extent),seen)
        self.assertEqual(layout.extent,set().union(*map(set,layout.fields)) | (set(layout.lane)&layout.extent))

    def test_v9_geometry_matches_pre_dev45_committed_golden(self):
        self.assertEqual("6b788c6301d371d75f3cbe35035c937d9ee4c29f",self.skeleton(9).fingerprint)

    def test_plan_fields_share_outer_fence_and_barn_never_overlaps(self):
        skeleton=self.skeleton()
        fields=[p for p in skeleton.parcels if p.purpose=="field"]
        self.assertEqual(4,len(fields))
        self.assertEqual(set(skeleton.plan.crop_ids),{p.crop_id for p in fields})
        self.assertGreater(sum(len(p.cells) for p in fields),1000)
        farm=next(s for s in skeleton.structures if s.function=="farm_field")
        barn=next(s for s in skeleton.structures if s.function=="barn")
        self.assertFalse(set(farm.footprint)&set(barn.footprint))
        extent=set(farm.footprint)
        boundary={p for p in extent if any((p[0]+dx,p[1]+dy) not in extent for dx,dy in ((0,1),(0,-1),(1,0),(-1,0)))}
        fence={(p.x,p.y) for p in skeleton.pieces if p.role in {"field_fence","field_gate"}}
        self.assertEqual(boundary,fence)
        self.assertEqual(1,sum(p.role=="field_gate" for p in skeleton.pieces))
        self.assertTrue(any(farm.entrance in road.polyline for road in skeleton.roads))
        self.assertTrue(any(abs(barn.entrance[0]-x)+abs(barn.entrance[1]-y)<=1 for road in skeleton.roads for x,y in road.polyline))
        self.assertFalse(any(p.piece_id=="core:farm_shed_piece" and (p.x,p.y) in extent for p in skeleton.pieces))
        self.assertTrue(any(p.piece_id=="core:farm_shed_piece" and p.structure_plan_id==barn.uid for p in skeleton.pieces))

    def test_fences_materialize_and_fields_exclude_lanes_and_obstacles(self):
        skeleton=self.skeleton();physical=self.physical(skeleton)
        blocked=next(p for p in skeleton.pieces if p.role=="field_fence")
        gate=next(p for p in skeleton.pieces if p.role=="field_gate")
        self.assertFalse(physical.passable(WorldPos(blocked.x,blocked.y,0),True))
        self.assertTrue(physical.passable(WorldPos(gate.x,gate.y,0),True))
        professions=profession_fixtures.Phase4ProfessionTests()
        professions.registry=self.registry
        _,town,_,_,_,_,_,_,system,_=professions.make("farmer","core:field_wheat")
        system.physicalization=physical;town.uid=skeleton.plan.settlement_id
        cells=set(system._field_cells(town,"core:wheat"))
        self.assertTrue(cells)
        self.assertNotIn((gate.x,gate.y),cells)
        self.assertNotIn((blocked.x,blocked.y),cells)
        self.assertFalse(cells & {p for road in skeleton.roads for p in road.polyline})
        allowed=set().union(*(set(p.cells) for p in skeleton.parcels if p.crop_id=="core:wheat"))
        self.assertTrue(cells <= allowed)

    def test_farm_gate_and_barn_have_real_traversable_connection(self):
        skeleton=self.skeleton();physical=self.physical(skeleton)
        barn=next(s for s in skeleton.structures if s.function=="barn")
        farm=next(s for s in skeleton.structures if s.function=="farm_field")
        start=barn.entrance;target=farm.entrance
        seen={start};queue=deque(seen)
        while queue and target not in seen:
            x,y=queue.popleft()
            for dx,dy in ((0,1),(0,-1),(1,0),(-1,0)):
                p=(x+dx,y+dy)
                if p in seen or abs(p[0]-target[0])+abs(p[1]-target[1])>90:continue
                if physical.passable(WorldPos(*p,0),True):seen.add(p);queue.append(p)
        self.assertIn(target,seen)

    def test_seed_capital_is_redistributed_without_extra_goods(self):
        stocks={"core:wheat_seed":25,"core:turnip_seed":20,"core:wood":8}
        crops=terrain_crop_ids(settlement_fixtures.Env(),self.registry)
        starting_farm_seeds(stocks,crops,self.registry)
        self.assertEqual(45,sum(qty for iid,qty in stocks.items() if iid.endswith("_seed")))
        self.assertEqual(8,stocks["core:wood"])
        self.assertTrue(all(stocks[self.registry.crops[crop].seed_item]>0 for crop in crops))

    def test_new_town_seeds_follow_terrain_without_changing_legacy_draws(self):
        def generated(version):
            planner=SimpleNamespace(version=version,world=self.world(version),plan=lambda *a,**kw:self.region())
            return ProceduralSocietyGenerator(b"dev45-seed-capital",self.registry,planner).settlement_for_cell(0,0)
        legacy=generated(9);current=generated(10)
        seed_total=lambda town:sum(qty for iid,qty in town.stocks.items() if iid.endswith("_seed"))
        self.assertEqual(seed_total(legacy[0]),seed_total(current[0]))
        self.assertEqual(legacy[0].name,current[0].name)
        self.assertEqual([asdict(n) for n in legacy[1]],[asdict(n) for n in current[1]])
        self.assertTrue(current[0].stocks["core:corn_seed"])
        self.assertNotIn("core:corn_seed",legacy[0].stocks)

    def test_generation_order_cache_round_trip_and_rebuild_are_identical(self):
        cache=MemoryCache();world=self.world(cache=cache);planner=SettlementSkeletonPlanner(world)
        first=planner.plan(self.region(),"settlement:farms",45,persist=True)
        reloaded=SettlementSkeletonPlanner(world)
        reloaded._generate=lambda *a,**kw:self.fail("Cache hit must not generate")
        self.assertEqual(first.fingerprint,reloaded.plan(self.region(),"settlement:farms",45).fingerprint)
        self.assertEqual(first.to_dict(),SettlementSkeleton.from_dict(first.to_dict()).to_dict())
        cache.rows.clear()
        other=SettlementSkeletonPlanner(world)
        other.plan(self.region(),"settlement:other",75,persist=False)
        self.assertEqual(first.fingerprint,other.plan(self.region(),"settlement:farms",45,persist=False).fingerprint)

    def test_database_reload_cache_rebuild_preserves_deltas_and_save_integrity(self):
        with tempfile.TemporaryDirectory(prefix="worldseed-dev45-farm-") as directory:
            path=Path(directory)/"farm.db"
            db=WorldDatabase.create(path,"Farm regression",b"dev45-farms".hex())
            try:
                world=self.world(cache=db)
                first=SettlementSkeletonPlanner(world).plan(self.region(),"settlement:farms",45)
                barn=next(s for s in first.structures if s.function=="barn")
                db.store_physical_plan_delta(barn.uid,"structure",1,{"destroyed":True})
                db.connection.execute("DELETE FROM generated_settlement_plans WHERE settlement_uid=?",("settlement:farms",))
                db.commit_generated()
                rebuilt=SettlementSkeletonPlanner(world).plan(self.region(),"settlement:farms",45)
                self.assertEqual(first.fingerprint,rebuilt.fingerprint)
                self.assertEqual({"destroyed":True},db.load_physical_plan_delta(barn.uid)["payload"])
                state=LivingWorldState();state.crops[pos_key(180,180,0)]=CropPlot("core:wheat",180,180,0,20)
                db.save_state(turn=1,tile_deltas={},player_id=1,position=WorldPos(180,180,0),inventory={},sim_state=state.to_dict())
                self.assertEqual([],db.verify())
            finally:
                db.close()
            result=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/"tools"/"verify_save.py"),str(path)],capture_output=True,text=True,timeout=15)
            self.assertEqual(0,result.returncode,result.stdout+result.stderr)
            self.assertIn("Save integrity: OK",result.stdout)

    def test_dry_site_gate_rejects_water_without_unbounded_search(self):
        world=self.world();world.environment_at=lambda pos:SimpleNamespace(open_water=True,slope=0,flood_risk=0)
        planner=SettlementSkeletonPlanner(world)
        self.assertIsNone(planner._large_farm_layout((180,180),(200,180),(90,90,270,270),"village",set(),4))
        self.assertLessEqual(len(planner._env_cache),12)

    def test_named_farmer_binds_to_room_backed_barn_not_empty_field(self):
        skeleton=self.skeleton();physical=self.physical(skeleton)
        state=LivingWorldState()
        town=SettlementState("settlement:farms","Farm",0,0,180,180,45,"culture:test","religion:test","faction:test")
        state.settlements[town.uid]=town
        npc=NPCState("npc:farmer","Farmer",30,"farmer",[],180,180,0,town.uid,town.faction_id)
        npc.workplace_id=next(s.uid for s in skeleton.structures if s.function=="farm_field")
        state.npcs[npc.uid]=npc
        SettlementPopulationBinder(state,self.registry,b"dev45",physical).bind_settlement(town)
        self.assertEqual("barn",physical.structure_by_id(npc.workplace_id).function)
        self.assertTrue(npc.work_room_id)


class FarmerExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)

    def fixture(self):
        helper=profession_fixtures.Phase4ProfessionTests();helper.registry=self.registry
        return helper.make("farmer","core:field_wheat")

    def test_healthy_crop_does_not_starve_new_planting_and_workers_share_field(self):
        state,town,npc,_,_,activities,_,_,system,storage=self.fixture()
        state.crops[pos_key(8,8,0)]=CropPlot("core:wheat",8,8,0,0,moisture=80,health=100)
        storage.items["core:wheat_seed"]=3
        first=system.plan_work(npc,town,20)
        activity=next(t for t in first if t.get("kind")=="activity")
        self.assertEqual("plant",activity["farm_action"])
        npc2=NPCState("npc:second","Second",30,"farmer",[],0,0,0,town.uid,town.faction_id)
        npc2.workplace_id=npc.workplace_id;npc2.work_assignment_day=0;npc2.assigned_process_id="core:field_wheat"
        state.npcs[npc2.uid]=npc2
        second=system.plan_work(npc2,town,20)
        other=next(t for t in second if t.get("kind")=="activity")
        self.assertNotEqual(activity["reservation_uid"],other["reservation_uid"])
        first_row=state.activity_reservations[activity["reservation_uid"]]
        other_row=state.activity_reservations[other["reservation_uid"]]
        self.assertNotEqual((first_row.use_x,first_row.use_y),(other_row.use_x,other_row.use_y))
        npc.inventory["core:wheat_seed"]=1
        self.assertTrue(system.complete_farm(npc,town,activity,50))
        self.assertEqual(0,npc.inventory.get("core:wheat_seed",0))
        restored=LivingWorldState.from_dict(state.to_dict())
        self.assertEqual(state.crops.keys(),restored.crops.keys())

    def test_stressed_crop_is_tended_and_pens_are_not_fields(self):
        state,town,npc,_,physical,_,_,_,system,storage=self.fixture()
        physical._skeleton.parcels.append(SimpleNamespace(uid="pen",kind="farm",purpose="animal_pen",cells=[(0,0)]))
        state.crops[pos_key(8,8,0)]=CropPlot("core:wheat",8,8,0,0,moisture=25)
        self.assertNotIn((0,0),system._field_cells(town))
        activity=next(t for t in system.plan_work(npc,town,20) if t.get("kind")=="activity")
        self.assertEqual("tend",activity["farm_action"])

    def test_harvest_returns_replanting_seed_into_real_storage(self):
        state,town,npc,_,_,_,_,_,system,storage=self.fixture()
        state.crops[pos_key(8,8,0)]=CropPlot("core:wheat",8,8,0,0,mature=True)
        tasks=system.plan_work(npc,town,20)
        activity=next(t for t in tasks if t.get("kind")=="activity")
        self.assertTrue(system.complete_farm(npc,town,activity,40))
        self.assertGreater(npc.inventory.get("core:wheat_seed",0),0)
        self.assertIn("core:wheat_seed",tasks[-1]["items"])
        npc.x,npc.y=storage.x,storage.y
        self.assertTrue(system.deposit(npc,town,tasks[-1],50))
        self.assertGreater(storage.items["core:wheat_seed"],0)

    def test_stationary_player_ticks_move_farmer_and_plant_multiple_real_crops(self):
        state,town,npc,world,physical,activities,_,_,system,storage=self.fixture()
        storage.items["core:wheat_seed"]=3
        ai=NPCSystem(state,b"dev45-farmer-ticks",SimpleNamespace(record=lambda *a,**kw:None),world=world,building=physical)
        ai.attach_activity_system(activities);ai.attach_profession_system(system)
        npc.tasks=system.plan_work(npc,town,540)
        positions=set()
        player=WorldPos(0,0,0)
        # Allow two real round trips plus their planting durations, not a
        # teleport or a render-frame work shortcut.
        for minute in range(540,711,5):
            ai.tick_update(minute,player)
            positions.add((npc.x,npc.y))
        self.assertGreaterEqual(len(state.crops),2)
        self.assertGreater(len(positions),3)
        self.assertEqual(3,len(state.crops)+storage.items.get("core:wheat_seed",0)+npc.inventory.get("core:wheat_seed",0))


if __name__=="__main__":
    unittest.main()
