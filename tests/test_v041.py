import tempfile
import unittest
from pathlib import Path

from worldseed.app import MENU_KEYS, _map_key
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Position, Vitals
from worldseed.entities.store import EntityStore
from worldseed.persistence.database import WorldDatabase
from worldseed.sim.commands import EquipCommand, MoveCommand, UnequipCommand
from worldseed.sim.engine import Simulation
from worldseed.systems.state import CreatureState, LivingWorldState, pos_key
from worldseed.world.generator import WorldGenerator
from worldseed.world.world import World


class V041Tests(unittest.TestCase):
    def make_sim(self, seed=b"v041"):
        reg = ContentRegistry.load(DATA_DIR)
        td = tempfile.TemporaryDirectory()
        db = WorldDatabase.create(Path(td.name) / "x.db", "x", seed.hex())
        world = World(WorldGenerator(seed, reg), reg, db)
        entities = EntityStore()
        pid = entities.spawn(preferred_id=1)
        entities.add(pid, Position(WorldPos(0, 0, 0)))
        entities.add(pid, Inventory({
            "core:leather_hood": 1,
            "core:leather_vest": 1,
            "core:leather_bracers": 1,
            "core:leather_leggings": 1,
        }))
        entities.add(pid, Vitals())
        sim = Simulation(world, entities, reg, 0, LivingWorldState(), seed)
        return td, db, reg, world, entities, pid, sim

    def test_d_is_reserved_for_movement(self):
        self.assertNotIn("d", MENU_KEYS)
        cmd = _map_key("d", 1)
        self.assertIsInstance(cmd, MoveCommand)
        self.assertEqual((cmd.dx, cmd.dy), (1, 0))

    def test_equipment_roundtrip(self):
        td, db, reg, world, entities, pid, sim = self.make_sim()
        try:
            inv = entities.get(pid, Inventory)
            sim.execute(EquipCommand(pid, "core:leather_vest"))
            self.assertEqual(sim.state.player_equipment["body"], "core:leather_vest")
            self.assertEqual(inv.count("core:leather_vest"), 0)
            sim.execute(UnequipCommand(pid, "body"))
            self.assertNotIn("body", sim.state.player_equipment)
            self.assertEqual(inv.count("core:leather_vest"), 1)
        finally:
            db.close(); td.cleanup()

    def test_armor_reduces_or_matches_incoming_damage_and_creates_wound(self):
        td, db, reg, world, entities, pid, sim = self.make_sim()
        try:
            creature = CreatureState("test:wolf", "core:wolf", 1, 0, 0, reg.species["core:wolf"].max_hp)
            naked = Vitals()
            sim.state.player_equipment.clear(); sim.state.player_wounds.clear()
            sim.combat.creature_attack_player(creature, naked, 77)
            naked_damage = naked.max_hp - naked.hp

            armored = Vitals()
            sim.state.player_wounds.clear()
            sim.state.player_equipment = {
                "head": "core:leather_hood",
                "body": "core:leather_vest",
                "hands": "core:leather_bracers",
                "legs": "core:leather_leggings",
            }
            sim.combat.creature_attack_player(creature, armored, 77)
            armored_damage = armored.max_hp - armored.hp
            self.assertLessEqual(armored_damage, naked_damage)
            self.assertTrue(sim.state.player_wounds)
            self.assertIn(sim.state.player_wounds[-1]["part"], sim.state.player_body_parts)
        finally:
            db.close(); td.cleanup()

    def test_equipment_and_wounds_survive_state_roundtrip(self):
        state = LivingWorldState()
        state.player_equipment["body"] = "core:leather_vest"
        state.player_body_parts["torso"] = 71
        state.player_wounds.append({"part":"torso","tissue":"muscle","type":"bite","severity":50,"bleeding":2,"fracture":False,"turn":9})
        restored = LivingWorldState.from_dict(state.to_dict())
        self.assertEqual(restored.player_equipment, state.player_equipment)
        self.assertEqual(restored.player_body_parts["torso"], 71)
        self.assertEqual(restored.player_wounds, state.player_wounds)

    def test_death_drops_equipped_items(self):
        td, db, reg, world, entities, pid, sim = self.make_sim()
        try:
            sim.execute(EquipCommand(pid, "core:leather_vest"))
            sim.state.player_wounds.append({"part":"torso","severity":90,"bleeding":9,"fracture":False})
            death_pos = sim.player_pos
            sim._handle_death("test")
            pile = sim.state.ground_piles[pos_key(death_pos.x, death_pos.y, death_pos.z)]
            self.assertEqual(pile.items.get("core:leather_vest"), 1)
            self.assertFalse(sim.state.player_equipment)
            self.assertFalse(sim.state.player_wounds)
        finally:
            db.close(); td.cleanup()


if __name__ == "__main__":
    unittest.main()

class MetallurgyTests(unittest.TestCase):
    def make_sim(self, seed=b"metal"):
        reg = ContentRegistry.load(DATA_DIR)
        td = tempfile.TemporaryDirectory()
        db = WorldDatabase.create(Path(td.name) / "m.db", "m", seed.hex())
        world = World(WorldGenerator(seed, reg), reg, db)
        # Metallurgy requires a dry workshop, independent of worldgen spawn.
        world.set_terrain(WorldPos(0,0,0),'core:grass')
        world.set_terrain(WorldPos(1,0,0),'core:grass')
        entities = EntityStore(); pid = entities.spawn(preferred_id=1)
        entities.add(pid, Position(WorldPos(0,0,0)))
        entities.add(pid, Inventory({"core:iron_ore":8,"core:coal":20,"core:wood":6,"core:hide":6,"core:fiber":6,"core:waterskin":1}))
        entities.add(pid, Vitals())
        state = LivingWorldState(); state.player_knowledge += ["tech:smelting","tech:steelmaking"]
        sim = Simulation(world, entities, reg, 0, state, seed)
        sim.state.structures[pos_key(1,0,0)] = __import__('worldseed.systems.state',fromlist=['StructureInstance']).StructureInstance('core:forge',1,0,0)
        return td, db, reg, world, entities, pid, sim

    def test_metal_process_chain_and_quality(self):
        from worldseed.sim.commands import CraftCommand
        td, db, reg, world, entities, pid, sim = self.make_sim()
        try:
            sim.execute(CraftCommand(pid,'core:iron_bloom'))
            self.assertTrue(sim.metallurgy.batches('player','core:iron_bloom'))
            sim.execute(CraftCommand(pid,'core:steel_billet'))
            batches=sim.metallurgy.batches('player','core:steel_billet');self.assertEqual(len(batches),1)
            self.assertGreaterEqual(batches[0].temperature_c,700)
            sim.execute(CraftCommand(pid,'core:quench_steel'))
            batch=sim.metallurgy.batches('player','core:steel_billet')[0]
            self.assertIn('quenched',batch.treatments)
            sim.execute(CraftCommand(pid,'core:temper_steel'))
            batch=sim.metallurgy.batches('player','core:steel_billet')[0]
            self.assertIn('tempered',batch.treatments)
            q=batch.quality
            sim.execute(CraftCommand(pid,'core:steel_sword'))
            arts=[a for a in sim.state.artifacts.values() if a.base_item=='core:steel_sword']
            self.assertEqual(len(arts),1)
            self.assertGreaterEqual(arts[0].quality,max(20,q-5))
            self.assertIn('metallurgy',arts[0].components)
        finally:
            db.close(); td.cleanup()

    def test_metal_batches_roundtrip(self):
        td, db, reg, world, entities, pid, sim = self.make_sim()
        try:
            from worldseed.sim.commands import CraftCommand
            sim.execute(CraftCommand(pid,'core:iron_bloom'))
            restored=LivingWorldState.from_dict(sim.state.to_dict())
            self.assertEqual(len(restored.metal_batches),1)
            a=next(iter(sim.state.metal_batches.values()));b=next(iter(restored.metal_batches.values()))
            self.assertEqual((a.item_id,a.quality,a.carbon_permille),(b.item_id,b.quality,b.carbon_permille))
        finally:
            db.close(); td.cleanup()

class StorageAndSoilTests(unittest.TestCase):
    def make_sim(self, seed=b"storage-soil"):
        reg=ContentRegistry.load(DATA_DIR);td=tempfile.TemporaryDirectory();db=WorldDatabase.create(Path(td.name)/'s.db','s',seed.hex());world=World(WorldGenerator(seed,reg),reg,db);e=EntityStore();pid=e.spawn(preferred_id=1);e.add(pid,Position(WorldPos(0,0,0)));e.add(pid,Inventory({'core:wood':20,'core:fiber':10,'core:stone':10,'core:bone_meal':2,'core:wheat_seed':2,'core:digging_stick':1}));e.add(pid,Vitals());sim=Simulation(world,e,reg,0,LivingWorldState(),seed);return td,db,reg,world,e,pid,sim
    def test_container_store_take_and_dismantle_spill(self):
        from worldseed.sim.commands import BuildCommand,StoreCommand,TakeFromContainerCommand,DismantleCommand
        td,db,reg,world,e,pid,sim=self.make_sim()
        try:
            sim.execute(BuildCommand(pid,'core:wood_chest',1,0));c=sim.building.nearby_container(sim.player_pos);self.assertIsNotNone(c)
            wood_before=e.get(pid,Inventory).count('core:wood');sim.execute(StoreCommand(pid,'core:wood',1));self.assertEqual(c.items.get('core:wood'),1);self.assertEqual(e.get(pid,Inventory).count('core:wood'),wood_before-1)
            sim.execute(TakeFromContainerCommand(pid,'core:wood',1));self.assertNotIn('core:wood',c.items)
            sim.execute(StoreCommand(pid,'core:wood',1));sim.execute(DismantleCommand(pid,1,0));self.assertFalse(sim.state.containers);pile=sim.state.ground_piles[pos_key(1,0,0)];self.assertGreaterEqual(pile.items.get('core:wood',0),1)
        finally:db.close();td.cleanup()
    def test_soil_fertilizer_and_crop_rotation_pressure(self):
        from worldseed.sim.commands import FertilizeCommand
        td,db,reg,world,e,pid,sim=self.make_sim()
        try:
            # force current tile to cultivable soil so test is seed-independent
            sim.world.set_terrain(sim.player_pos,'core:grass');sim.till();key=pos_key(0,0,0);soil=sim.state.soils[key];soil.nitrogen=20;soil.phosphorus=20;soil.potassium=20;soil.disease_pressure=30
            sim.execute(FertilizeCommand(pid));self.assertGreater(soil.phosphorus,20);self.assertLess(soil.disease_pressure,30)
            soil.last_crop_id='core:wheat';sim._plant(__import__('worldseed.sim.commands',fromlist=['PlantCommand']).PlantCommand(pid,'core:wheat'));self.assertGreater(sim.state.crops[key].disease,0)
        finally:db.close();td.cleanup()
    def test_container_and_soil_roundtrip(self):
        state=LivingWorldState();from worldseed.systems.state import ContainerState,SoilState
        state.containers['1,2,0']=ContainerState('c',1,2,0,'player',1000,2000,{'core:stone':1});state.soils['0,0,0']=SoilState(0,0,0,33,44,55,66,7,'core:wheat')
        restored=LivingWorldState.from_dict(state.to_dict());self.assertEqual(restored.containers['1,2,0'].items['core:stone'],1);self.assertEqual(restored.soils['0,0,0'].potassium,55)

class RoofTests(unittest.TestCase):
    def make_sim(self,seed=b'roof'):
        reg=ContentRegistry.load(DATA_DIR);td=tempfile.TemporaryDirectory();db=WorldDatabase.create(Path(td.name)/'r.db','r',seed.hex());world=World(WorldGenerator(seed,reg),reg,db);e=EntityStore();pid=e.spawn(preferred_id=1);e.add(pid,Position(WorldPos(0,0,0)));e.add(pid,Inventory({'core:wood':100,'core:stone':100,'core:fiber':50}));e.add(pid,Vitals());sim=Simulation(world,e,reg,0,LivingWorldState(),seed);return td,db,reg,e,pid,sim
    def test_roof_can_share_tile_with_support_and_remains_stable(self):
        td,db,reg,e,pid,sim=self.make_sim()
        try:
            inv=e.get(pid,Inventory);ok,_=sim.building.place('core:stone_pillar',WorldPos(1,0,0),inv);self.assertTrue(ok);ok,_=sim.building.place('core:stone_roof',WorldPos(1,0,0),inv);self.assertTrue(ok);self.assertIsNotNone(sim.building.structure_at(WorldPos(1,0,0)));self.assertIsNotNone(sim.building.roof_at(WorldPos(1,0,0)))
            cond=sim.building.roof_at(WorldPos(1,0,0)).condition
            for _ in range(20):sim.building.hourly_update()
            self.assertGreaterEqual(sim.building.roof_at(WorldPos(1,0,0)).condition,cond)
        finally:db.close();td.cleanup()
    def test_unsupported_heavy_roof_collapses(self):
        td,db,reg,e,pid,sim=self.make_sim()
        try:
            inv=e.get(pid,Inventory);ok,_=sim.building.place('core:stone_roof',WorldPos(5,5,0),inv);self.assertTrue(ok)
            collapsed=[]
            for _ in range(20):collapsed += sim.building.hourly_update()
            self.assertIsNone(sim.building.roof_at(WorldPos(5,5,0)));self.assertTrue(collapsed)
        finally:db.close();td.cleanup()

class DungeonRuntimeTests(unittest.TestCase):
    def make_sim(self,seed=b'dungeon-runtime'):
        reg=ContentRegistry.load(DATA_DIR);td=tempfile.TemporaryDirectory();db=WorldDatabase.create(Path(td.name)/'d.db','d',seed.hex());world=World(WorldGenerator(seed,reg),reg,db);e=EntityStore();pid=e.spawn(preferred_id=1);e.add(pid,Position(WorldPos(0,0,-1)));e.add(pid,Inventory({}));e.add(pid,Vitals());sim=Simulation(world,e,reg,0,LivingWorldState(),seed);return td,db,reg,world,e,pid,sim
    def find_site_with(self,sim,feature):
        from worldseed.core.coords import ChunkKey
        for z in (-1,-2,-3):
            for x in range(-30,31):
                for y in range(-30,31):
                    key=ChunkKey(x,y,z)
                    if sim.world.generator.sites.has_site(key):
                        f=sim.world.generator.sites.runtime_features(key)
                        if f.get(feature):return key,f
        self.fail(f'no site with {feature}')
    def test_site_activation_spawns_persistent_occupants_and_loot(self):
        td,db,reg,world,e,pid,sim=self.make_sim()
        try:
            key,features=self.find_site_with(sim,'occupants');lx,ly=features['occupants'][0];pos=WorldPos(key.x*32+lx,key.y*32+ly,key.z);site=sim.dungeons.activate_at(pos,100)
            self.assertIsNotNone(site);self.assertTrue(site.occupant_uids);self.assertTrue(all(uid in sim.state.creatures for uid in site.occupant_uids));self.assertTrue(site.loot_seeded)
            again=sim.dungeons.activate_at(pos,200);self.assertEqual(site.uid,again.uid);self.assertEqual(site.occupant_uids,again.occupant_uids)
        finally:db.close();td.cleanup()
    def test_lock_requires_tool_or_key_and_stays_open(self):
        td,db,reg,world,e,pid,sim=self.make_sim()
        try:
            key,features=self.find_site_with(sim,'locks');pos0=WorldPos(key.x*32+features['occupants'][0][0],key.y*32+features['occupants'][0][1],key.z);site=sim.dungeons.activate_at(pos0,100);pk=next(k for k,v in site.locks.items() if v);x,y,z=(int(v) for v in pk.split(','));target=WorldPos(x,y,z);inv=e.get(pid,Inventory)
            ok,_=sim.dungeons.try_unlock(target,inv,100);self.assertFalse(ok);inv.add('core:ancient_key',1);ok,_=sim.dungeons.try_unlock(target,inv,101);self.assertTrue(ok);self.assertFalse(sim.dungeons.is_locked(target))
        finally:db.close();td.cleanup()
    def test_trap_is_one_shot_and_creates_player_wound(self):
        td,db,reg,world,e,pid,sim=self.make_sim()
        try:
            key,features=self.find_site_with(sim,'traps');base=features['occupants'][0] if features['occupants'] else features['loot'][0];site=sim.dungeons.activate_at(WorldPos(key.x*32+base[0],key.y*32+base[1],key.z),100);pk=next(k for k,v in site.traps.items() if v);x,y,z=(int(v) for v in pk.split(','));target=WorldPos(x,y,z);v=e.get(pid,Vitals);msg=sim.dungeons.trigger_trap(target,v,9);self.assertIsNotNone(msg);self.assertTrue(sim.state.player_wounds);hp=v.hp;self.assertIsNone(sim.dungeons.trigger_trap(target,v,10));self.assertEqual(v.hp,hp)
        finally:db.close();td.cleanup()
    def test_site_clears_when_persistent_occupants_die(self):
        td,db,reg,world,e,pid,sim=self.make_sim()
        try:
            key,features=self.find_site_with(sim,'occupants');lx,ly=features['occupants'][0];site=sim.dungeons.activate_at(WorldPos(key.x*32+lx,key.y*32+ly,key.z),100)
            for uid in list(site.occupant_uids):sim.state.creatures.pop(uid,None)
            cleared=sim.dungeons.update_cleared(200);self.assertIn(site.uid,cleared);self.assertTrue(site.cleared);self.assertTrue(any(ev.event_type=='site_cleared' for ev in sim.state.history))
        finally:db.close();td.cleanup()

class EconomyHardeningTests(unittest.TestCase):
    def setUp(self):
        from worldseed.systems.history import HistorySystem
        from worldseed.systems.generation import ProceduralSocietyGenerator
        self.reg=ContentRegistry.load(DATA_DIR);self.seed=b'econ-hardening';self.state=LivingWorldState();self.history=HistorySystem(self.state);self.gen=ProceduralSocietyGenerator(self.seed,self.reg)
        made=[]
        for rx in range(-6,7):
            for ry in range(-6,7):
                g=self.gen.settlement_for_cell(rx,ry)
                if g:
                    s,npcs,c,r,f=g;self.state.cultures.setdefault(c.uid,c);self.state.religions.setdefault(r.uid,r);self.state.factions.setdefault(f.uid,f);self.state.settlements[s.uid]=s
                    for n in npcs:self.state.npcs[n.uid]=n
                    made.append(s)
                    if len(made)>=3:break
            if len(made)>=3:break
        self.assertGreaterEqual(len(made),2);self.towns=made
    def test_labor_reservations_and_process_graph(self):
        from worldseed.systems.economy import EconomySystem, TARGET
        econ=EconomySystem(self.state,self.reg,self.seed,self.history);t=self.towns[0];t.population=120;t.knowledge.append('tech:smelting')
        for g,target in TARGET.items():t.stocks[g]=target*3
        t.stocks['core:iron_bloom']=0;t.stocks['core:iron_ore']=80;t.stocks['core:coal']=50
        before_ore=t.stocks['core:iron_ore'];econ.daily_update(1440)
        reservations=[r for r in self.state.labor_reservations.values() if r.settlement_id==t.uid and r.assigned_day==1]
        self.assertTrue(reservations);self.assertTrue(t.labor_pool);self.assertGreater(t.stocks.get('core:iron_bloom',0),0);self.assertTrue(any(r.process_id=='core:iron_smelt' and r.workers>0 for r in reservations))
    def test_trade_route_and_caravan_carries_value(self):
        from worldseed.systems.economy import EconomySystem, TARGET
        econ=EconomySystem(self.state,self.reg,self.seed,self.history);a,b=self.towns[:2]
        # Force nearby pair if procedural picks are distant.
        b.region_x,b.region_y=a.region_x+1,a.region_y
        a.stocks['core:wood']=300;b.stocks['core:wood']=0;a.wealth=b.wealth=2000
        econ.update_prices();econ._ensure_routes(1440);econ._create_caravans(1440)
        routes=[r for r in self.state.trade_routes.values() if r.origin==a.uid and r.destination==b.uid]
        self.assertTrue(routes)
        cs=[c for c in self.state.caravans.values() if c.origin==a.uid and c.destination==b.uid]
        self.assertTrue(cs);c=cs[0];self.assertGreater(c.cargo_value,0);self.assertTrue(c.route_id)
        econ.process_caravans(c.arrive_minute)
        self.assertIn(c.status,('arrived','lost'))
        if c.status=='arrived':self.assertGreaterEqual(routes[0].traffic,1)
    def test_property_rent_budget_and_housing(self):
        from worldseed.systems.civics import CivicsSystem
        civ=CivicsSystem(self.state,self.seed,self.history);t=self.towns[0];t.buildings['house']=6;t.wealth=500
        civ.ensure_settlement(t.uid);homes=[p for p in self.state.properties.values() if p.settlement_id==t.uid and p.kind=='home'];self.assertTrue(homes);self.assertGreater(t.housing_capacity,0)
        residents=[n for n in self.state.npcs.values() if n.settlement_id==t.uid and n.alive]
        if len(residents)>=2:
            h=homes[0];h.owner_uid=residents[0].uid;h.occupants=[residents[0].uid,residents[1].uid];residents[1].wealth=40;before=residents[1].wealth;civ.monthly_update(30*1440);self.assertLess(residents[1].wealth,before)
        self.assertIn('maintenance',t.budget)
    def test_migration_cohort_moves_population_and_named_representatives(self):
        from worldseed.systems.civics import CivicsSystem
        from worldseed.systems.migration import MigrationSystem
        civ=CivicsSystem(self.state,self.seed,self.history);mig=MigrationSystem(self.state,self.seed,self.history);o,d=self.towns[:2]
        o.population=100;o.food_stress=95;o.wealth=10;d.population=30;d.food_stress=0;d.buildings['house']=30
        civ.ensure_settlement(o.uid);civ.ensure_settlement(d.uid);d.housing_capacity=max(d.housing_capacity,150)
        created=None
        for month in range(1,30):
            mig.monthly_update(month*30*1440)
            cs=[c for c in self.state.migration_cohorts.values() if c.origin==o.uid and c.status=='traveling']
            if cs:created=cs[0];break
        self.assertIsNotNone(created);dest_before=d.population;mig.process(created.arrive_minute);self.assertEqual(created.status,'arrived');self.assertGreaterEqual(d.population,dest_before+1)
        for uid in created.npc_uids:
            self.assertEqual(self.state.npcs[uid].settlement_id,d.uid)
    def test_war_consumes_manpower_and_supply_without_negative_state(self):
        from worldseed.systems.factions import FactionSystem
        a,b=self.towns[:2];fa=self.state.factions[a.faction_id];fb=self.state.factions[b.faction_id]
        if fa.uid==fb.uid:
            # make a separate faction for the second town from a distant generated region.
            for s in self.towns[2:]:
                if s.faction_id!=fa.uid:b=s;fb=self.state.factions[b.faction_id];break
        if fa.uid==fb.uid:self.skipTest('procedural setup produced one faction')
        a.faction_id=fa.uid;b.faction_id=fb.uid;fa.at_war=[fb.uid];fb.at_war=[fa.uid];a.population=b.population=160;a.stocks['core:wheat']=b.stocks['core:wheat']=200;a.stocks['core:iron_bloom']=b.stocks['core:iron_bloom']=20
        system=FactionSystem(self.state,self.seed,self.history)
        for m in range(1,13):system.monthly_update(m*30*1440)
        self.assertGreaterEqual(fa.manpower,0);self.assertGreaterEqual(fb.manpower,0);self.assertGreaterEqual(fa.military_supply,0);self.assertGreaterEqual(fb.military_supply,0)
        self.assertTrue(any(e.event_type in ('battle','raid','peace') for e in self.state.history))
    def test_new_civic_state_roundtrip(self):
        from worldseed.systems.civics import CivicsSystem
        from worldseed.systems.economy import EconomySystem
        civ=CivicsSystem(self.state,self.seed,self.history);econ=EconomySystem(self.state,self.reg,self.seed,self.history);t=self.towns[0];civ.ensure_settlement(t.uid);econ.daily_update(1440)
        raw=self.state.to_dict();rest=LivingWorldState.from_dict(raw);self.assertEqual(rest.properties.keys(),self.state.properties.keys());self.assertEqual(rest.labor_reservations.keys(),self.state.labor_reservations.keys());self.assertEqual(rest.trade_routes.keys(),self.state.trade_routes.keys())

class IdentityHistoryTests(unittest.TestCase):
    def setUp(self):
        from worldseed.systems.history import HistorySystem
        from worldseed.systems.generation import ProceduralSocietyGenerator
        self.reg=ContentRegistry.load(DATA_DIR);self.seed=b'identity-history';self.state=LivingWorldState();self.history=HistorySystem(self.state);gen=ProceduralSocietyGenerator(self.seed,self.reg)
        for rx in range(-5,6):
            for ry in range(-5,6):
                g=gen.settlement_for_cell(rx,ry)
                if g:
                    s,npcs,c,r,f=g;self.state.cultures[c.uid]=c;self.state.religions[r.uid]=r;self.state.factions[f.uid]=f;self.state.settlements[s.uid]=s
                    for n in npcs:self.state.npcs[n.uid]=n
                    self.town=s;self.faction=f;return
        self.fail('no generated settlement')
    def test_governance_creates_office_claim_and_successor(self):
        from worldseed.systems.governance import GovernanceSystem
        gov=GovernanceSystem(self.state,self.seed,self.history);gov.monthly_update(30*1440);office=self.state.offices[f'office:{self.faction.uid}:ruler'];self.assertTrue(office.holder_uid);self.assertTrue(any(c.claimant_id==self.faction.uid and c.target_id==self.town.uid for c in self.state.claims.values()))
        old=office.holder_uid;self.state.npcs[old].alive=False;gov.monthly_update(60*1440);self.assertNotEqual(self.state.offices[office.uid].holder_uid,old);self.assertIn(old,self.state.offices[office.uid].previous_holders)
    def test_family_death_creates_linked_grave(self):
        from worldseed.systems.family import FamilySystem
        from worldseed.systems.governance import GovernanceSystem
        gov=GovernanceSystem(self.state,self.seed,self.history);gov.monthly_update(30*1440);ruler=self.state.npcs[self.state.offices[f'office:{self.faction.uid}:ruler'].holder_uid];ruler.age=130
        fam=FamilySystem(self.state,self.seed,self.history);found=False
        for m in range(2,80):
            fam.monthly_update(m*30*1440)
            if not ruler.alive:found=True;break
        self.assertTrue(found);grave=self.state.graves.get(f'grave:{ruler.uid}');self.assertIsNotNone(grave);self.assertEqual(grave.person_uid,ruler.uid);self.assertEqual(grave.grave_type,'tomb')
    def test_artifact_provenance_transfers(self):
        from worldseed.systems.artifacts import ArtifactSystem
        art=ArtifactSystem(self.state,self.reg,self.seed);a=art.create('core:iron_sword','Tester',100);art.transfer_uid(a.uid,self.town.uid,200,'gifted');art.transfer_uid(a.uid,'player',300,'recovered');self.assertEqual(a.owner,'player');self.assertEqual(len(a.provenance),3);self.assertEqual(a.provenance[-1]['from'],self.town.uid)
    def test_identity_state_roundtrip(self):
        from worldseed.systems.governance import GovernanceSystem
        gov=GovernanceSystem(self.state,self.seed,self.history);gov.monthly_update(30*1440);raw=self.state.to_dict();rest=LivingWorldState.from_dict(raw);self.assertEqual(rest.offices.keys(),self.state.offices.keys());self.assertEqual(rest.claims.keys(),self.state.claims.keys())

class KnowledgeReligionDepthTests(unittest.TestCase):
    def setUp(self):
        from worldseed.systems.history import HistorySystem
        from worldseed.systems.generation import ProceduralSocietyGenerator
        self.reg=ContentRegistry.load(DATA_DIR);self.seed=b'knowledge-religion';self.state=LivingWorldState();self.history=HistorySystem(self.state);gen=ProceduralSocietyGenerator(self.seed,self.reg)
        for rx in range(-6,7):
            for ry in range(-6,7):
                g=gen.settlement_for_cell(rx,ry)
                if g:
                    s,npcs,c,r,f=g;self.state.cultures[c.uid]=c;self.state.religions[r.uid]=r;self.state.factions[f.uid]=f;self.state.settlements[s.uid]=s
                    for n in npcs:self.state.npcs[n.uid]=n
                    self.town=s;return
        self.fail('no settlement')
    def test_institutions_assign_language_religion_and_library(self):
        from worldseed.systems.institutions import InstitutionSystem
        # Guarantee one scholar to seed an archive.
        n=next(iter(self.state.npcs.values()));n.occupation='scholar'
        inst=InstitutionSystem(self.state,self.seed,self.history);inst.ensure_settlement(self.town.uid)
        self.assertTrue(any(l.settlement_id==self.town.uid for l in self.state.libraries.values()));self.assertTrue(any(i.settlement_id==self.town.uid for i in self.state.religious_institutions.values()))
        self.assertEqual(n.culture_id,self.town.culture_id);self.assertEqual(n.religion_id,self.town.religion_id);self.assertEqual(n.language_fluency[self.town.culture_id],100);self.assertGreater(n.literacy,0)
    def test_discovery_respects_prerequisites_and_creates_physical_book(self):
        from worldseed.systems.institutions import InstitutionSystem
        from worldseed.systems.knowledge import KnowledgeSystem
        n=next(iter(self.state.npcs.values()));n.occupation='scholar';self.town.knowledge=['knowledge:literacy','tech:smelting','tech:mining','knowledge:agriculture','knowledge:herbalism']
        inst=InstitutionSystem(self.state,self.seed,self.history);inst.ensure_settlement(self.town.uid);know=KnowledgeSystem(self.state,self.seed,self.history)
        # Drive enough deterministic days that a discovery occurs.
        before=set(self.town.knowledge)
        for day in range(1,1000):
            know.daily_update(day*1440)
            if self.state.books:break
        new=set(self.town.knowledge)-before;self.assertTrue(new);self.assertTrue(self.state.books)
        book=next(iter(self.state.books.values()));self.assertTrue(book.language_id);lib=next(iter(self.state.libraries.values()));self.assertIn(book.uid,lib.book_uids)
    def test_library_copy_consumes_parchment(self):
        from worldseed.systems.institutions import InstitutionSystem
        from worldseed.systems.knowledge import KnowledgeSystem
        n=next(iter(self.state.npcs.values()));n.occupation='scholar';self.town.knowledge=['knowledge:literacy'];self.town.stocks['core:parchment']=5
        inst=InstitutionSystem(self.state,self.seed,self.history);inst.ensure_settlement(self.town.uid);know=KnowledgeSystem(self.state,self.seed,self.history);book=know._author_book(self.town,n,'knowledge:literacy',1);before=self.town.stocks['core:parchment']
        know.daily_update(10*1440);self.assertLess(self.town.stocks['core:parchment'],before);self.assertGreaterEqual(len(self.state.books),2)
    def test_institution_state_roundtrip(self):
        from worldseed.systems.institutions import InstitutionSystem
        n=next(iter(self.state.npcs.values()));n.occupation='scholar';InstitutionSystem(self.state,self.seed,self.history).ensure_settlement(self.town.uid);rest=LivingWorldState.from_dict(self.state.to_dict());self.assertEqual(rest.libraries.keys(),self.state.libraries.keys());self.assertEqual(rest.religious_institutions.keys(),self.state.religious_institutions.keys());self.assertEqual(rest.npcs[n.uid].language_fluency,self.state.npcs[n.uid].language_fluency)

class MagicDepthTests(unittest.TestCase):
    def setUp(self):
        from worldseed.systems.history import HistorySystem
        from worldseed.systems.magic import MagicSystem
        from worldseed.systems.state import MagicLaw, CultureState, ReligionState, SettlementState
        self.state=LivingWorldState();self.seed=b'magic-depth';self.history=HistorySystem(self.state)
        self.state.magic_laws={'magic:ember:shape':MagicLaw('magic:ember:shape','ember','shape','core:coal',10,4,True,'any','',35,'ember',False)}
        self.state.cultures['culture:0']=CultureState('culture:0','Testfolk',['scholarship'],'short',[],'metal',{'sun':'sol'})
        self.state.religions['religion:0']=ReligionState('religion:0','Way of Test','Test','craft','none','forge blessing','stag') if False else ReligionState('religion:0','Way of Test','Test',['craft'],'none','forge blessing','stag')
        self.state.settlements['s']=SettlementState('s','Teston',0,0,0,0,40,'culture:0','religion:0','f',stocks={'core:coal':20},buildings={'house':10})
        self.magic=MagicSystem(self.state,self.seed,self.history,None)
    def test_experiment_creates_spell_ast_and_cast_contamination(self):
        from worldseed.entities.components import Inventory, Vitals
        inv=Inventory({'core:coal':2});v=Vitals();msg=self.magic.experiment('ember','shape',inv,v,10);self.assertIn('Discovery',msg);self.assertIn('spell:magic:ember:shape',self.state.spells)
        msg,effects=self.magic.cast('magic:ember:shape',v,WorldPos(1,2,0),20,inv,{'soil'});self.assertTrue(effects);self.assertIn('1,2,0',self.state.arcane_contamination);self.assertEqual(self.state.spells['spell:magic:ember:shape'].cast_count,1)
    def test_constraint_blocks_wrong_time_and_terrain(self):
        from worldseed.entities.components import Inventory, Vitals
        law=self.state.magic_laws['magic:ember:shape'];law.time_constraint='night';law.terrain_constraint='underground';self.state.player_knowledge.append('knowledge:magic:ember:shape');v=Vitals();inv=Inventory({'core:coal':1})
        msg,e=self.magic.cast(law.uid,v,WorldPos(0,0,0),12*60,inv,set());self.assertFalse(e);self.assertIn('night',msg.lower())
        msg,e=self.magic.cast(law.uid,v,WorldPos(0,0,0),23*60,inv,set());self.assertFalse(e);self.assertIn('below',msg.lower())
    def test_ritual_generation_execution_and_myth(self):
        from worldseed.entities.components import Inventory, Vitals
        self.magic.ensure_traditions();self.magic.ensure_rituals();self.assertTrue(self.state.rituals);r=next(iter(self.state.rituals.values()));inv=Inventory(dict(r.catalysts));v=Vitals();msg,effects,duration=self.magic.perform_ritual(r.uid,inv,v,WorldPos(0,0,0),100,True,r.min_participants);self.assertTrue(effects);self.assertGreater(duration,0);self.assertEqual(r.performed_count,1);self.assertTrue(self.state.myths)
    def test_magic_state_roundtrip(self):
        self.magic.ensure_traditions();self.magic.ensure_rituals();rest=LivingWorldState.from_dict(self.state.to_dict());self.assertEqual(rest.rituals.keys(),self.state.rituals.keys());self.assertEqual(rest.magic_traditions.keys(),self.state.magic_traditions.keys())

class ComponentItemTests(unittest.TestCase):
    def setUp(self):
        from worldseed.systems.artifacts import ArtifactSystem
        from worldseed.systems.metallurgy import MetallurgySystem
        from worldseed.systems.crafting import CraftingSystem
        self.reg=ContentRegistry.load(DATA_DIR);self.state=LivingWorldState();self.seed=b'component-items';self.state.player_knowledge+=['tech:smelting','tech:steelmaking'];self.art=ArtifactSystem(self.state,self.reg,self.seed);self.met=MetallurgySystem(self.state,self.reg,self.seed);self.craft=CraftingSystem(self.state,self.reg,self.art,self.met)
    def test_component_design_builds_persistent_component_graph(self):
        inv=Inventory({'core:iron_bloom':1,'core:wood':1,'core:hide':1});self.met._create_batch('core:iron_bloom','player','core:iron',2000,25,3,80,75,1,['test'])
        ok,msg,minutes=self.craft.craft_design('core:modular_sword',{'blade':'core:iron_bloom','grip':'core:wood','wrapping':'core:hide'},inv,{'core:forge'},100,'player');self.assertTrue(ok);self.assertEqual(inv.count('core:crafted_sword'),1);a=self.art.best_owned('core:crafted_sword');self.assertIsNotNone(a);self.assertEqual(a.components['blade']['material'],'core:iron');self.assertIn('grip',a.components)
    def test_durable_condition_temperature_contamination_roundtrip(self):
        a=self.art.create('core:iron_sword','maker',1);a.condition=73;a.temperature_c=99;a.contamination=18;rest=LivingWorldState.from_dict(self.state.to_dict());b=rest.artifacts[a.uid];self.assertEqual((b.condition,b.temperature_c,b.contamination),(73,99,18))
    def test_wear_reduces_effective_quality_and_can_break_item(self):
        a=self.art.create('core:iron_sword','maker',1,quality_hint=80);q=self.art.effective_quality(a);self.art.wear(a.base_item,'player',40,2,'test');self.assertLess(self.art.effective_quality(a),q);self.art.wear(a.base_item,'player',100,3,'test');self.assertEqual(a.owner,'destroyed')
    def test_equipped_specific_artifact_persists(self):
        a=self.art.create('core:iron_helmet','maker',1);self.state.player_equipment['head']='core:iron_helmet';self.state.player_equipped_artifacts['head']=a.uid;rest=LivingWorldState.from_dict(self.state.to_dict());self.assertEqual(rest.player_equipped_artifacts['head'],a.uid)
