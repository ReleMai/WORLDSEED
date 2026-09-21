import tempfile
import unittest
from pathlib import Path

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Position, Vitals
from worldseed.entities.store import EntityStore
from worldseed.persistence.database import WorldDatabase
from worldseed.sim.engine import Simulation
from worldseed.systems.pathfinding import HierarchicalPathfinder
from worldseed.systems.state import CaravanState, LivingWorldState
from worldseed.ui.screens import health_screen
from worldseed.world.generator import WorldGenerator
from worldseed.world.world import World


class V100Tests(unittest.TestCase):
    def make_sim(self, seed=b"v100"):
        reg=ContentRegistry.load(DATA_DIR)
        td=tempfile.TemporaryDirectory()
        db=WorldDatabase.create(Path(td.name)/"world.db","world",seed.hex())
        world=World(WorldGenerator(seed,reg),reg,db)
        entities=EntityStore();pid=entities.spawn(preferred_id=1)
        entities.add(pid,Position(WorldPos(0,0,0)))
        entities.add(pid,Inventory({"core:copper_coin":100,"core:herbal_tonic":2}))
        entities.add(pid,Vitals())
        sim=Simulation(world,entities,reg,0,LivingWorldState(),seed)
        return td,db,reg,world,entities,pid,sim

    def test_disease_content_loaded(self):
        reg=ContentRegistry.load(DATA_DIR)
        self.assertIn("core:red_fever",reg.diseases)
        self.assertIn("airborne",reg.diseases["core:red_fever"].transmissions)
        self.assertGreater(reg.diseases["core:ashen_pox"].mortality_permille,reg.diseases["core:marsh_ague"].mortality_permille)

    def test_outbreak_progression_sets_policy_and_history(self):
        td,db,reg,world,e,pid,sim=self.make_sim(b"epi-policy")
        try:
            town=next(iter(sim.state.settlements.values()))
            town.population=max(60,town.population);town.housing_capacity=max(1,town.population//2);town.homeless=max(10,town.population//3)
            row=sim.disease.seed_outbreak(town.uid,"core:red_fever",1440,initial=max(20,town.population//2),source="test")
            self.assertIsNotNone(row)
            sim.disease.daily_update(2*1440)
            self.assertIn(town.health_policy,{"restricted","quarantine"})
            self.assertGreater(town.quarantine_level,0)
            self.assertTrue(row.trend)
            self.assertTrue(any(x.event_type in {"disease_outbreak","health_policy"} for x in sim.state.history))
        finally:db.close();td.cleanup()

    def test_named_infection_progresses_and_immunity_roundtrip(self):
        td,db,reg,world,e,pid,sim=self.make_sim(b"epi-named")
        try:
            town=next(iter(sim.state.settlements.values()))
            npc=next(n for n in sim.state.npcs.values() if n.settlement_id==town.uid)
            uid=sim.disease.expose_npc(npc.uid,"core:grey_flux",0,"test")
            self.assertIsNotNone(uid)
            disease=reg.diseases["core:grey_flux"]
            sim.disease._advance_named_infections((disease.incubation_hours+1)*60)
            self.assertEqual(sim.state.infections[uid].stage,"symptomatic")
            sim.state.infections[uid].treated=True
            sim.disease._advance_named_infections((disease.incubation_hours+disease.illness_hours+2)*60)
            self.assertNotIn(uid,npc.infections)
            self.assertGreater(npc.immunities.get(disease.id,0),0)
            restored=LivingWorldState.from_dict(sim.state.to_dict())
            self.assertEqual(restored.npcs[npc.uid].immunities,npc.immunities)
        finally:db.close();td.cleanup()

    def test_caravan_can_seed_destination_outbreak(self):
        td,db,reg,world,e,pid,sim=self.make_sim(b"epi-caravan")
        try:
            sim._ensure_nearby_world(WorldPos(700,0,0))
            towns=sorted(sim.state.settlements.values(),key=lambda t:t.uid)
            self.assertGreaterEqual(len(towns),2)
            a,b=towns[0],towns[1]
            cid="caravan:pathogen-test"
            sim.state.caravans[cid]=CaravanState(cid,a.uid,b.uid,{},0,0,10,"arrived",pathogen_load={"core:red_fever":8})
            sim.disease.daily_update(1440)
            self.assertTrue(any(d.settlement_id==b.uid and d.disease_id=="core:red_fever" for d in sim.state.diseases.values()))
            self.assertFalse(sim.state.caravans[cid].pathogen_load)
        finally:db.close();td.cleanup()

    def test_player_infection_treatment_and_ui_are_persistent_observational(self):
        td,db,reg,world,e,pid,sim=self.make_sim(b"epi-player")
        try:
            uid=sim.disease.expose_player("core:red_fever",0,"test")
            disease=reg.diseases["core:red_fever"]
            sim.state.infections[uid].exposed_minute=-(disease.incubation_hours+2)*60
            vit=e.get(pid,Vitals);msgs=sim.disease.tick_player(60,vit)
            self.assertEqual(sim.state.infections[uid].stage,"symptomatic")
            inv=e.get(pid,Inventory);before=inv.count("core:herbal_tonic")
            msg=sim.disease.treat_player(inv,60)
            self.assertIn("tonic",msg.lower());self.assertEqual(inv.count("core:herbal_tonic"),before-1)
            self.assertTrue(sim.state.infections[uid].treated)
            before_state=sim.state.to_dict();text=health_screen(sim);after_state=sim.state.to_dict()
            self.assertEqual(before_state,after_state);self.assertIn("HEALTH",text);self.assertIn("Red Fever",text)
        finally:db.close();td.cleanup()

    def test_three_level_route_has_region_and_chunk_corridor(self):
        td,db,reg,world,e,pid,sim=self.make_sim(b"route-three-level")
        try:
            sim._ensure_nearby_world(WorldPos(700,0,0));sim.economy.daily_update(1440)
            route=next(iter(sim.state.trade_routes.values()))
            self.assertTrue(route.waypoints)
            self.assertTrue(route.chunk_waypoints)
            a=sim.state.settlements[route.origin];b=sim.state.settlements[route.destination]
            pf=HierarchicalPathfinder(sim.state,sim.seed)
            full=pf.full_route_between_settlements(a.uid,b.uid)
            self.assertEqual(full["chunks"],[tuple(int(v) for v in x.split(',')) for x in route.chunk_waypoints])
            self.assertEqual(full["regional"].regions[0],(a.region_x,a.region_y))
        finally:db.close();td.cleanup()

    def test_safe_offline_disease_cannot_kill_named_person(self):
        td,db,reg,world,e,pid,sim=self.make_sim(b"epi-safe")
        try:
            town=next(iter(sim.state.settlements.values()));npc=next(n for n in sim.state.npcs.values() if n.settlement_id==town.uid)
            uid=sim.disease.expose_npc(npc.uid,"core:ashen_pox",sim.clock.minute,"test")
            inf=sim.state.infections[uid];d=reg.diseases[inf.disease_id]
            inf.exposed_minute=sim.clock.minute-(d.incubation_hours+24)*60;inf.severity=100;npc.hp=1
            sim.advance_offline(2*1440,"safe")
            self.assertTrue(npc.alive);self.assertGreaterEqual(npc.hp,1)
        finally:db.close();td.cleanup()

    def test_quarantine_reduces_trade_capacity(self):
        td,db,reg,world,e,pid,sim=self.make_sim(b"epi-tradeoff")
        try:
            sim._ensure_nearby_world(WorldPos(700,0,0));sim.economy.daily_update(1440)
            route=next(iter(sim.state.trade_routes.values()));origin=sim.state.settlements[route.origin]
            before=route.capacity;origin.quarantine_level=80
            # Force full route refresh by month boundary.
            sim.economy._ensure_routes(30*1440)
            after=sim.state.trade_routes[route.uid].capacity
            self.assertLess(after,before)
        finally:db.close();td.cleanup()

    def test_resolved_infections_compact_after_retention_window(self):
        td,db,reg,world,e,pid,sim=self.make_sim(b"epi-compact")
        try:
            town=next(iter(sim.state.settlements.values()))
            npc=next(n for n in sim.state.npcs.values() if n.settlement_id==town.uid)
            uid=sim.disease.expose_npc(npc.uid,"core:red_fever",0,"test")
            inf=sim.state.infections[uid]
            inf.stage="recovered";inf.recovered_minute=1440
            npc.infections=[x for x in npc.infections if x!=uid]
            sim.disease._compact_infections(32*1440)
            self.assertNotIn(uid,sim.state.infections)
        finally:db.close();td.cleanup()

    def test_soak_validation_rejects_impossible_epidemic_reference(self):
        td,db,reg,world,e,pid,sim=self.make_sim(b"epi-validate")
        try:
            town=next(iter(sim.state.settlements.values()))
            row=sim.disease.seed_outbreak(town.uid,"core:red_fever",1440,initial=2,source="test")
            raw=sim.state.to_dict();raw["diseases"][f"outbreak:{town.uid}:core:red_fever"]["settlement_id"]="settlement:missing"
            from worldseed.persistence.validation import validate_sim_state
            issues=validate_sim_state(raw)
            self.assertTrue(any("orphan disease settlement" in issue for issue in issues))
        finally:db.close();td.cleanup()


if __name__ == "__main__":
    unittest.main()
