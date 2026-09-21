import json
import tempfile
import unittest
from pathlib import Path

from worldseed.config import DATA_DIR
from worldseed.content.mods import ModError, ModManager
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Position, Vitals
from worldseed.entities.store import EntityStore
from worldseed.persistence.database import WorldDatabase
from worldseed.sim.engine import Simulation
from worldseed.systems.lod import TIER_A, TIER_B, TIER_C, TIER_D
from worldseed.systems.pathfinding import HierarchicalPathfinder
from worldseed.systems.state import LivingWorldState, NPCState, CaravanState
from worldseed.ui.screens import economy_screen, ecology_screen, simulation_screen, world_screen, npc_detail_screen, route_detail_screen, faction_detail_screen, artifact_detail_screen, book_detail_screen, dungeon_detail_screen, event_detail_screen, grave_detail_screen, alerts_screen
from worldseed.ui.alerts import world_alerts
from worldseed.world.generator import WorldGenerator
from worldseed.world.world import World


class V090Tests(unittest.TestCase):
    def make_sim(self, seed=b"v090"):
        reg=ContentRegistry.load(DATA_DIR)
        td=tempfile.TemporaryDirectory()
        db=WorldDatabase.create(Path(td.name)/"world.db","world",seed.hex())
        world=World(WorldGenerator(seed,reg),reg,db)
        entities=EntityStore();pid=entities.spawn(preferred_id=1)
        entities.add(pid,Position(WorldPos(0,0,0)));entities.add(pid,Inventory({"core:copper_coin":30}));entities.add(pid,Vitals())
        sim=Simulation(world,entities,reg,0,LivingWorldState(),seed)
        return td,db,reg,world,entities,pid,sim

    def test_explicit_lod_tiers(self):
        td,db,reg,world,e,pid,sim=self.make_sim()
        try:
            p=WorldPos(0,0,0)
            self.assertEqual(sim.lod.tier(p,10,10,0),TIER_A)
            self.assertEqual(sim.lod.tier(p,100,0,0),TIER_B)
            self.assertEqual(sim.lod.tier(p,700,0,0),TIER_C)
            self.assertEqual(sim.lod.tier(p,3000,0,0),TIER_D)
        finally:db.close();td.cleanup()

    def test_offline_safe_advances_boundaries_without_named_mortality(self):
        td,db,reg,world,e,pid,sim=self.make_sim()
        try:
            # Make one named person obviously vulnerable to ordinary mortality;
            # SAFE offline progression must not run FamilySystem mortality.
            town=next(iter(sim.state.settlements.values()))
            npc=next((n for n in sim.state.npcs.values() if n.settlement_id==town.uid),None)
            if npc is None:
                npc=NPCState("npc:test","Test Elder",120,"farmer",[],town.x,town.y,0,town.uid,town.faction_id)
                sim.state.npcs[npc.uid]=npc
            npc.age=120
            start=sim.clock.minute
            summary=sim.advance_offline(35*1440,"safe")
            self.assertEqual(sim.clock.minute,start+35*1440)
            self.assertGreaterEqual(summary["days"],35)
            self.assertGreaterEqual(summary["months"],1)
            self.assertTrue(sim.state.npcs[npc.uid].alive)
            self.assertEqual(sim.state.last_offline_minutes,35*1440)
        finally:db.close();td.cleanup()

    def test_offline_processes_logistics_created_mid_jump(self):
        td,db,reg,world,e,pid,sim=self.make_sim(b"offline-logistics")
        try:
            # Realize enough towns for an origin/destination pair.  The caravan
            # is deliberately created by the first daily update, after the LOD
            # system has already calculated the initial boundary list.
            sim._ensure_nearby_world(WorldPos(700,0,0))
            towns=sorted(sim.state.settlements.values(),key=lambda t:t.uid)
            self.assertGreaterEqual(len(towns),2)
            origin,dest=towns[0],towns[1]
            good="core:wood"
            before=dest.stocks.get(good,0)
            original=sim.economy.daily_update
            created={"done":False}
            def wrapped(minute):
                original(minute)
                if not created["done"]:
                    uid="caravan:test-offline-new"
                    sim.state.caravans[uid]=CaravanState(uid=uid,origin=origin.uid,destination=dest.uid,goods={good:7},wealth=0,depart_minute=minute,arrive_minute=minute+300,status="traveling",route_id="",cargo_value=7,guards=100)
                    created["done"]=True
            sim.economy.daily_update=wrapped
            summary=sim.advance_offline(2*1440,"safe")
            self.assertTrue(created["done"])
            caravan=sim.state.caravans["caravan:test-offline-new"]
            self.assertEqual(caravan.status,"arrived")
            self.assertGreaterEqual(dest.stocks.get(good,0),before+7)
            self.assertGreaterEqual(summary["arrivals"],1)
        finally:db.close();td.cleanup()

    def test_hierarchical_path_is_deterministic(self):
        state=LivingWorldState();pf=HierarchicalPathfinder(state,b"routes")
        a=pf.regional_path((0,0),(7,-5));b=pf.regional_path((0,0),(7,-5))
        self.assertEqual(a,b)
        self.assertEqual(a.regions[0],(0,0));self.assertEqual(a.regions[-1],(7,-5))
        self.assertGreater(a.travel_minutes,0)

    def test_market_history_is_bounded_and_roundtrips(self):
        td,db,reg,world,e,pid,sim=self.make_sim(b"market-history")
        try:
            town=next(iter(sim.state.settlements.values()))
            for day in range(1,150):sim.economy.daily_update(day*1440)
            self.assertTrue(town.market_history)
            self.assertTrue(all(len(rows)<=120 for rows in town.market_history.values()))
            restored=LivingWorldState.from_dict(sim.state.to_dict())
            self.assertEqual(restored.settlements[town.uid].market_history,town.market_history)
        finally:db.close();td.cleanup()

    def test_trade_graph_is_sparse_and_bounded(self):
        td,db,reg,world,e,pid,sim=self.make_sim(b"sparse-routes")
        try:
            # Realize several macro-regions.  A complete directed graph would
            # grow N*(N-1); WORLDSEED intentionally bounds persistent partners.
            for x in (0,700,1400,2100):
                for y in (0,700):sim._ensure_nearby_world(WorldPos(x,y,0))
            sim.economy.update_prices();sim.economy._ensure_routes(30*1440)
            n=len(sim.state.settlements)
            self.assertLessEqual(len(sim.state.trade_routes),n*6)
            outbound={}
            for r in sim.state.trade_routes.values():outbound[r.origin]=outbound.get(r.origin,0)+1
            self.assertTrue(all(v<=6 for v in outbound.values()))
        finally:db.close();td.cleanup()

    def test_trade_routes_store_macro_waypoints(self):
        td,db,reg,world,e,pid,sim=self.make_sim(b"route-world")
        try:
            # Ensure a wider realized society then run a daily economy update.
            sim._ensure_nearby_world(WorldPos(700,0,0));sim.economy.daily_update(1440)
            routes=list(sim.state.trade_routes.values())
            self.assertTrue(routes)
            self.assertTrue(any(r.waypoints and r.travel_minutes>0 for r in routes))
        finally:db.close();td.cleanup()

    def test_rotating_backup_is_valid(self):
        td,db,reg,world,e,pid,sim=self.make_sim(b"backup")
        try:
            p=e.get(pid,Position).value
            db.save_state(turn=1,tile_deltas={},player_id=pid,position=p,inventory=e.get(pid,Inventory).items,vitals={"hp":100,"max_hp":100,"hunger":0,"thirst":0,"stamina":100,"body_temp":50,"pain":0,"blood":100},sim_state=sim.state.to_dict())
            backup=db.backup(3)
            self.assertTrue(backup.exists())
            probe=WorldDatabase.open(backup)
            try:self.assertEqual(probe.verify(),[])
            finally:probe.close()
        finally:db.close();td.cleanup()

    def test_save_verifier_detects_cross_record_corruption(self):
        td,db,reg,world,e,pid,sim=self.make_sim(b"verify-cross-record")
        try:
            p=e.get(pid,Position).value
            raw=sim.state.to_dict()
            # Inject a clearly invalid persistent NPC reference and route bound.
            town=next(iter(raw["settlements"]))
            raw["npcs"]["npc:corrupt"]={"uid":"npc:corrupt","name":"Broken Ref","age":30,"occupation":"farmer","traits":[],"x":0,"y":0,"z":0,"settlement_id":"settlement:missing","faction_id":"","hp":100,"hunger":0,"thirst":0,"rest":0,"wealth":20,"goal":"work","goal_score":0,"memories":[],"relationships":{},"knowledge":[],"spouse_uid":"npc:missing","parents":[],"children":[],"tasks":[],"home_id":"","workplace_id":"","property_id":"","employer_id":"","culture_id":"","religion_id":"","literacy":0,"language_fluency":{},"alive":True}
            db.save_state(turn=1,tile_deltas={},player_id=pid,position=p,inventory=e.get(pid,Inventory).items,vitals={"hp":100,"max_hp":100,"hunger":0,"thirst":0,"stamina":100,"body_temp":50,"pain":0,"blood":100},sim_state=raw)
            issues=db.verify()
            self.assertTrue(any("orphan NPC settlement" in x for x in issues))
            self.assertTrue(any("orphan NPC spouse" in x for x in issues))
        finally:db.close();td.cleanup()

    def test_restore_backup_recovers_corrupted_target(self):
        td,db,reg,world,e,pid,sim=self.make_sim(b"restore-backup")
        path=db.path
        try:
            p=e.get(pid,Position).value
            db.save_state(turn=9,tile_deltas={},player_id=pid,position=p,inventory=e.get(pid,Inventory).items,vitals={"hp":100,"max_hp":100,"hunger":0,"thirst":0,"stamina":100,"body_temp":50,"pain":0,"blood":100},sim_state=sim.state.to_dict())
            backup=db.backup(3)
            db.close()
            path.write_bytes(b"not a sqlite database")
            WorldDatabase.restore_backup(backup,path)
            recovered=WorldDatabase.open(path)
            try:
                self.assertEqual(recovered.verify(),[])
                self.assertEqual(int(recovered.get_meta("turn")),9)
            finally:recovered.close()
            db=None
        finally:
            if db is not None:
                try:db.close()
                except Exception:pass
            td.cleanup()

    def test_mod_data_directory_extends_registry_and_duplicate_fails(self):
        with tempfile.TemporaryDirectory() as td:
            data=Path(td)/"data";data.mkdir()
            (data/"items.json").write_text(json.dumps([{
                "id":"testmod:amber_shard","name":"Amber Shard","mass_g":12,"volume_ml":5,"base_value":17,"tags":["gem"]
            }]),encoding="utf-8")
            reg=ContentRegistry.load(DATA_DIR,[data])
            self.assertIn("testmod:amber_shard",reg.items)
            self.assertEqual(reg.items["testmod:amber_shard"].base_value,17)
            (data/"items.json").write_text(json.dumps([{
                "id":"core:wood","name":"Collision","mass_g":1,"volume_ml":1
            }]),encoding="utf-8")
            with self.assertRaises(ValueError):ContentRegistry.load(DATA_DIR,[data])

    def test_mod_dependency_resolution_and_cycle_detection(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            for mid,deps in (("base",[]),("addon",["base"]),("final",["addon"])):
                d=root/mid;d.mkdir();(d/"manifest.json").write_text(json.dumps({"id":mid,"version":"1.0","dependencies":deps}),encoding="utf-8")
            manager=ModManager(root)
            self.assertEqual([m.id for m in manager.resolve()],["base","addon","final"])
            (root/"base"/"manifest.json").write_text(json.dumps({"id":"base","version":"1.0","dependencies":["final"]}),encoding="utf-8")
            manager=ModManager(root)
            with self.assertRaises(ModError):manager.resolve()

    def test_dense_information_screens_are_observational(self):
        td,db,reg,world,e,pid,sim=self.make_sim(b"ui")
        try:
            before=sim.state.to_dict()
            outputs=[world_screen(sim),economy_screen(sim),ecology_screen(sim),simulation_screen(sim)]
            after=sim.state.to_dict()
            self.assertEqual(before,after)
            self.assertTrue(all("+" in text and "|" in text for text in outputs))
            self.assertIn("SIMULATION FIDELITY",outputs[-1])
        finally:db.close();td.cleanup()

    def test_alerts_are_derived_and_observational(self):
        td,db,reg,world,e,pid,sim=self.make_sim(b"alerts-ui")
        try:
            before=sim.state.to_dict();v=e.get(pid,Vitals);v.thirst=95
            # State snapshot after the deliberate fixture mutation; generating
            # alerts must not add persistent records of its own.
            before=sim.state.to_dict();rows=world_alerts(sim);text=alerts_screen(sim);after=sim.state.to_dict()
            self.assertEqual(before,after);self.assertTrue(any(a.category=='survival' for a in rows));self.assertIn('ALERTS / WORLD INBOX',text)
        finally:db.close();td.cleanup()

    def test_world_ledger_detail_screens_are_observational(self):
        td,db,reg,world,e,pid,sim=self.make_sim(b"ledger-ui")
        try:
            sim._ensure_nearby_world(WorldPos(700,0,0));sim.economy.daily_update(1440)
            before=sim.state.to_dict();outputs=[]
            npc=next(iter(sim.state.npcs),None);route=next(iter(sim.state.trade_routes),None);faction=next(iter(sim.state.factions),None);event=sim.state.history[-1].uid if sim.state.history else None
            if npc:outputs.append(npc_detail_screen(sim,npc))
            if route:outputs.append(route_detail_screen(sim,route))
            if faction:outputs.append(faction_detail_screen(sim,faction))
            if event:outputs.append(event_detail_screen(sim,event))
            after=sim.state.to_dict()
            self.assertEqual(before,after)
            self.assertTrue(outputs)
            self.assertTrue(all('+' in text and '|' in text for text in outputs))
        finally:db.close();td.cleanup()

    def test_materialized_kill_reconciles_cohort_population(self):
        td,db,reg,world,e,pid,sim=self.make_sim(b"eco-reconcile")
        try:
            sim.ecology.materialize_near(sim.player_pos,0)
            ordinary=next((c for c in sim.state.creatures.values() if c.cohort_key),None)
            if ordinary is None:
                self.skipTest("seed produced no materialized wildlife")
            before=sim.state.cohorts[ordinary.cohort_key].count
            ordinary.hp=0
            sim.combat.tick_wounds()
            self.assertEqual(sim.state.cohorts[ordinary.cohort_key].count,max(0,before-1))
        finally:db.close();td.cleanup()

    def test_dematerialization_preserves_authoritative_cohort_count(self):
        td,db,reg,world,e,pid,sim=self.make_sim(b"eco-dematerialize")
        try:
            sim.ecology.materialize_near(sim.player_pos,0)
            counts={k:c.count for k,c in sim.state.cohorts.items()}
            sim.ecology.dematerialize_far(WorldPos(10000,10000,0),10)
            self.assertEqual(counts,{k:c.count for k,c in sim.state.cohorts.items()})
        finally:db.close();td.cleanup()

    def test_history_compaction_preserves_legends_and_archives_mundane_events(self):
        state=LivingWorldState()
        from worldseed.systems.history import HistorySystem
        h=HistorySystem(state)
        for i in range(6205):h.record("trade",f"trade {i}",i*60,salience=5)
        legend=h.record("dragonfall","A dragon fell.",6206*60,salience=90)
        # Force another compaction boundary after the legend exists.
        for i in range(100):h.record("weather",f"weather {i}",(6300+i)*60,salience=2)
        self.assertTrue(state.history_archive)
        self.assertLessEqual(len(state.history),6100)
        self.assertIn(legend.uid,{e.uid for e in state.history})

    def test_unrealized_regions_remain_tier_e_potential(self):
        td,db,reg,world,e,pid,sim=self.make_sim(b"tier-e-frontier")
        try:
            # Simulation initialization realizes only the 3x3 macro neighborhood.
            initial_regions=set(sim.state.realized_regions)
            initial_ids=set(sim.state.settlements)
            self.assertTrue(initial_regions)
            town=next(iter(sim.state.settlements.values()))
            town.population=500;town.food_stress=0
            # Many founding attempts may occur, but none may instantiate a town
            # outside explicitly realized macro-regions.
            for month in range(1,240):sim.settlement_lifecycle.monthly_update(month*30*1440)
            for t in sim.state.settlements.values():
                self.assertIn(f"{t.region_x},{t.region_y}",set(sim.state.realized_regions))
            # The set of realized regions itself must not expand from off-screen
            # settlement reproduction.
            self.assertEqual(initial_regions,set(sim.state.realized_regions))
        finally:db.close();td.cleanup()

    def test_state_roundtrip_keeps_v090_settings_and_archive(self):
        state=LivingWorldState();state.offline_policy="full";state.last_offline_minutes=1234;state.ui_color=False;state.history_archive["Y1:trade"]={"year":1,"event_type":"trade","count":99};state.realized_regions=["0,0","1,0"]
        restored=LivingWorldState.from_dict(state.to_dict())
        self.assertEqual(restored.offline_policy,"full");self.assertEqual(restored.last_offline_minutes,1234);self.assertFalse(restored.ui_color);self.assertEqual(restored.history_archive["Y1:trade"]["count"],99);self.assertEqual(restored.realized_regions,["0,0","1,0"])


if __name__=="__main__":unittest.main()
