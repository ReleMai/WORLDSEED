from __future__ import annotations

import copy
from types import SimpleNamespace
import unittest

from tests import test_property_storage_casing as storage_fixtures
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory
from worldseed.persistence.validation import validate_sim_state
from worldseed.sim.commands import TakeFromContainerCommand, StoreCommand
from worldseed.sim.engine import Simulation
from worldseed.systems.container_profiles import catalog, parse_catalog, validate_catalog
from worldseed.systems.interior_state import InteriorActor, InteriorPlan, InteriorRect, InteriorRoom
from worldseed.systems.interior_storage import bind_storage
from worldseed.systems.interiors import InteriorSystem, exit_reachable, position_clear
from worldseed.systems.state import ContainerState, LivingWorldState, SettlementState, pos_key


class InteriorStorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)
        storage_fixtures.PropertyStorageCasingTests.setUpClass()

    def fixture(self):
        base,security=storage_fixtures.PropertyStorageCasingTests()._security_fixture()
        state,town,physical,_,_,_,storage,building,_,_,_=base
        sim=SimpleNamespace(state=state,registry=self.registry,settlement_physicalization=physical,
                            property_security=security,property_storage=storage,building=building)
        sim.interiors=InteriorSystem(sim)
        return sim,town,storage

    def test_storage_profiles_and_tabletop_reference_distinct_real_content(self):
        profiles,buildings=catalog()
        self.assertEqual(len(profiles),11)
        self.assertIn('core:tabletop',profiles)
        self.assertEqual(len({p.name for p in profiles.values()}),len(profiles))
        for profile in profiles.values():
            self.assertIn(profile.piece_id,self.registry.settlement_pieces)
            self.assertIn(profile.source_id,self.registry.structures)
            self.assertTrue(set(profile.loot)<=set(self.registry.items))
        for building in buildings.values():
            self.assertTrue(set(building.stock)<=set(self.registry.items))
        self.assertTrue(any(p.lock_level==0 for p in profiles.values()))
        self.assertTrue(any(p.lock_level>0 for p in profiles.values()))
        validate_catalog(self.registry)

    def test_invalid_profile_capacity_and_unknown_style_rejected(self):
        from pathlib import Path
        import json
        raw=json.loads((Path(DATA_DIR)/'container_profiles.json').read_text(encoding='utf-8'))
        broken=copy.deepcopy(raw);broken['profiles'][0]['capacity_mass_g']=-1
        with self.assertRaises(ValueError):parse_catalog(broken)
        broken=copy.deepcopy(raw);broken['buildings']['residence']['primary']='core:missing'
        with self.assertRaises(ValueError):parse_catalog(broken)

    def test_every_building_storage_reserves_real_goods_once(self):
        sim,town,storage=self.fixture()
        before={iid:town.stocks.get(iid,0)+sum(c.items.get(iid,0) for c in sim.state.containers.values())
                for iid in self.registry.items}
        containers_before={c.uid:dict(c.items) for c in sim.state.containers.values()}
        for _ in range(3):storage.sync_active()
        self.assertEqual(containers_before,{c.uid:dict(c.items) for c in sim.state.containers.values()})
        after={iid:town.stocks.get(iid,0)+sum(c.items.get(iid,0) for c in sim.state.containers.values())
               for iid in self.registry.items}
        self.assertEqual(before,after)
        clinic=next(s for s in sim.settlement_physicalization.skeleton_for(town.uid).structures if s.function=='clinic')
        containers=storage.for_property(clinic.uid)
        self.assertEqual(containers[0].profile_id,'core:supply_crate')
        cabinet=next(c for c in containers if c.profile_id=='core:medicine_cabinet')
        self.assertEqual(cabinet.interior_space_id,'interior:'+clinic.uid)
        self.assertNotEqual(sim.state.containers.get(pos_key(cabinet.x,cabinet.y,cabinet.z)),cabinet)
        self.assertIsNone(sim.building.container_at(WorldPos(cabinet.x,cabinet.y,cabinet.z)))

    def test_all_styles_bind_reachable_unique_furniture_without_loot_copy(self):
        profiles,_=catalog()
        plan=InteriorPlan('interior:storage-test','storage-test','door:storage-test',0,0,0,24000,20000,
                          entry_x=12000,entry_y=18000,
                          rooms=[InteriorRoom('room:store','Store',InteriorRect(250,250,23500,19000))])
        containers=[ContainerState('container:'+uid,0,0,0,'npc:owner',p.capacity_mass_g,p.capacity_volume_ml,
                                   {'core:wood':2},kind='property',property_id=plan.building_id,
                                   profile_id=uid,interior_space_id=plan.uid,
                                   interior_furniture_uid='storage-furniture:container:'+uid)
                    for uid,p in profiles.items()]
        before={c.uid:dict(c.items) for c in containers}
        bound=bind_storage(plan,containers)
        self.assertEqual(len(bound),len(profiles))
        self.assertEqual(len(plan.furniture),len(profiles))
        self.assertEqual(len({c.interior_furniture_uid for c in containers}),len(profiles))
        self.assertTrue(position_clear(plan,plan.entry_x,plan.entry_y))
        self.assertTrue(exit_reachable(plan,plan.entry_x,plan.entry_y))
        saved=plan.to_dict();bind_storage(plan,list(reversed(containers)))
        self.assertEqual(plan.to_dict(),saved)
        self.assertEqual({c.uid:dict(c.items) for c in containers},before)

    def test_legacy_storage_addition_never_overlaps_player_or_resident(self):
        plan=InteriorPlan('interior:occupied','occupied','door:occupied',0,0,0,12000,11000,
                          entry_x=6000,entry_y=10000,
                          rooms=[InteriorRoom('room:occupied','Store',InteriorRect(250,250,11500,10250))])
        # These are the first two placement candidates. The first actor stands
        # just outside the furniture's nominal rectangle, but their body radius
        # overlaps it; the second stands in the middle of the next candidate.
        player=InteriorActor(plan.uid,600,1050)
        resident=InteriorActor(plan.uid,2550,1000)
        elsewhere=InteriorActor('interior:other',12000,20000)
        container=ContainerState('container:occupied',0,0,0,'npc:owner',90000,140000,
                                 {'core:wood':3},kind='property',property_id=plan.building_id,
                                 profile_id='core:household_chest',interior_space_id=plan.uid,
                                 interior_furniture_uid='storage-furniture:container:occupied')
        state=LivingWorldState()
        state.interiors[plan.uid]=plan
        state.interior_actors={'player':player,'npc:resident':resident,'npc:elsewhere':elsewhere}
        state.containers['indoor-storage:'+container.uid]=container
        system=InteriorSystem(SimpleNamespace(state=state))
        positions={uid:(actor.x,actor.y) for uid,actor in state.interior_actors.items()}
        system._bind_storage(plan)
        self.assertEqual(len(plan.furniture),1)
        self.assertGreaterEqual(plan.furniture[0].x,3675)
        for actor in (player,resident):
            self.assertTrue(position_clear(plan,actor.x,actor.y))
            self.assertTrue(exit_reachable(plan,actor.x,actor.y))
        self.assertEqual(positions,{uid:(actor.x,actor.y) for uid,actor in state.interior_actors.items()})
        self.assertEqual(container.items,{'core:wood':3})
        first=plan.to_dict();system._bind_storage(plan)
        self.assertEqual(plan.to_dict(),first)

    def test_occupied_room_keeps_pending_inventory_indoors_until_vacancy(self):
        plan=InteriorPlan('interior:full','full','door:full',0,0,0,3000,5000,
                          entry_x=1500,entry_y=4000,
                          rooms=[InteriorRoom('room:full','Store',InteriorRect(250,250,2200,2400))])
        actor=InteriorActor(plan.uid,900,950)
        container=ContainerState('container:full',0,0,0,'npc:owner',90000,140000,
                                 {'core:wood':3},kind='property',property_id=plan.building_id,
                                 profile_id='core:household_chest',interior_space_id=plan.uid,
                                 interior_furniture_uid='storage-furniture:container:full')
        state=LivingWorldState();state.interiors[plan.uid]=plan
        state.interior_actors={'player':actor};state.containers['indoor-storage:'+container.uid]=container
        town=SettlementState('town:full','Fullford',0,0,0,0,2,'','','',stocks={'core:wood':7})
        state.settlements[town.uid]=town
        stocks_before=dict(town.stocks)
        sim=SimpleNamespace(state=state);system=InteriorSystem(sim)
        system._bind_storage(plan)
        self.assertFalse(plan.furniture)
        self.assertEqual(container.interior_space_id,plan.uid)
        self.assertEqual(container.interior_furniture_uid,'')
        self.assertFalse(system.container_in_reach(container.uid))
        self.assertIsNone(system.container_for_furniture(''))
        self.assertEqual(validate_sim_state(state.to_dict()),[])
        restored=LivingWorldState.from_dict(state.to_dict())
        self.assertEqual(restored.to_dict(),state.to_dict())
        # Vacancy is noticed only on an explicit preparation/sync, not hover.
        actor.x,actor.y=plan.entry_x,plan.entry_y
        self.assertFalse(system.container_in_reach(container.uid))
        system._bind_storage(plan)
        self.assertEqual(len(plan.furniture),1)
        self.assertEqual(container.interior_furniture_uid,plan.furniture[0].uid)
        self.assertEqual(container.items,{'core:wood':3})
        self.assertEqual(town.stocks,stocks_before)
        self.assertEqual(validate_sim_state(state.to_dict()),[])
        raw=restored.to_dict();raw['interiors']={};raw['interior_actors']={}
        self.assertIn('pending interior storage has no prepared space: container:full',validate_sim_state(raw))

    def test_current_space_reach_walls_and_real_inventory_transfer(self):
        sim,town,storage=self.fixture()
        house=next(s for s in sim.settlement_physicalization.skeleton_for(town.uid).structures if s.function=='residence')
        plan=sim.interiors.prepare_workplace(house.uid)
        container=next(c for c in storage.for_property(house.uid) if c.profile_id=='core:pantry_cabinet')
        furniture=next(f for f in plan.furniture if f.uid==container.interior_furniture_uid)
        use=sim.interiors.fixture_use_position(plan,furniture)
        self.assertIsNotNone(use)
        actor=InteriorActor(plan.uid,*use);sim.interiors._put_actor('player',actor)
        before=sim.state.to_dict()
        self.assertIs(sim.interiors.container_for_furniture(furniture.uid),container)
        self.assertTrue(sim.interiors.container_in_reach(container.uid))
        self.assertEqual(sim.state.to_dict(),before)
        inv=Inventory();container.owner='player';container.items={'core:wheat':3}
        sim.entities=SimpleNamespace(get=lambda *_:inv);sim.player_pos=WorldPos(*house.entrance)
        messages=[];sim._message=messages.append
        sim._command_container=lambda uid:Simulation._command_container(sim,uid)
        Simulation._take_container(sim,TakeFromContainerCommand(1,'core:wheat',2,container.uid))
        self.assertEqual(inv.count('core:wheat'),2);self.assertEqual(container.items['core:wheat'],1)
        Simulation._store(sim,StoreCommand(1,'core:wheat',1,container.uid))
        self.assertEqual(inv.count('core:wheat'),1);self.assertEqual(container.items['core:wheat'],2)
        actor.space_id='interior:other'
        self.assertIsNone(sim._command_container(container.uid))
        actor.space_id=plan.uid;actor.x=plan.entry_x;actor.y=plan.entry_y
        self.assertFalse(sim.interiors.container_in_reach(container.uid))
        actor.x,actor.y=use
        plan.walls.append(InteriorRect(furniture.x-300,furniture.y-300,furniture.w+600,150))
        actor.x=furniture.x+furniture.w//2;actor.y=furniture.y-500
        self.assertFalse(sim.interiors.container_in_reach(container.uid))

    def test_save_roundtrip_and_legacy_defaults_preserve_storage(self):
        sim,town,storage=self.fixture()
        for structure in sim.settlement_physicalization.skeleton_for(town.uid).structures:
            if structure.enclosed:sim.interiors.prepare_workplace(structure.uid)
        raw=sim.state.to_dict();restored=LivingWorldState.from_dict(raw)
        self.assertEqual(restored.to_dict(),raw)
        self.assertFalse([issue for issue in validate_sim_state(raw) if 'storage' in issue],validate_sim_state(raw))
        container=next(c for c in restored.containers.values() if c.interior_space_id)
        container.picked=True;container.locked=False;container.last_tampered_minute=99
        # Removing additive keys is the schema-3 legacy path, not a geography migration.
        old=container.__class__(**{k:v for k,v in next(iter(raw['containers'].values())).items()
                                 if k not in {'profile_id','interior_space_id','interior_furniture_uid'}})
        self.assertEqual(old.interior_space_id,'')
        self.assertEqual(old.profile_id,'')

    def test_legacy_cabinet_migration_preserves_loot_and_picked_lock(self):
        sim,town,storage=self.fixture()
        house=next(s for s in sim.settlement_physicalization.skeleton_for(town.uid).structures if s.function=='residence')
        container=next(c for c in storage.for_property(house.uid) if c.uid=='property-storage:'+house.uid)
        old_key=next(k for k,c in sim.state.containers.items() if c is container)
        sim.state.containers.pop(old_key)
        container.profile_id='';container.interior_space_id='';container.interior_furniture_uid=''
        container.picked=True;container.locked=False;container.last_tampered_minute=123
        container.items={'core:wood':3};sim.state.containers[pos_key(container.x,container.y,container.z)]=container
        stocks_before=dict(town.stocks)
        storage.sync_active()
        self.assertIs(storage.by_id(container.uid),container)
        self.assertEqual(container.items,{'core:wood':3})
        self.assertEqual(town.stocks,stocks_before)
        self.assertTrue(container.picked);self.assertFalse(container.locked)
        self.assertEqual(container.last_tampered_minute,123)
        self.assertEqual(container.interior_space_id,'interior:'+house.uid)
        self.assertIs(sim.state.containers['indoor-storage:'+container.uid],container)
        storage.sync_active()
        self.assertFalse(container.locked)

    def test_representative_storage_sqlite_roundtrip_and_cli_verification(self):
        import tempfile
        from pathlib import Path
        import subprocess
        import sys
        from worldseed.persistence.database import WorldDatabase
        sim,town,storage=self.fixture()
        house=next(s for s in sim.settlement_physicalization.skeleton_for(town.uid).structures if s.function=='residence')
        plan=sim.interiors.prepare_workplace(house.uid)
        state=LivingWorldState()
        # A prepared home owns linked floors. A representative save must keep
        # both ends of every stair instead of constructing an orphan binding.
        state.interiors.update({uid:floor for uid,floor in sim.state.interiors.items()
                                if floor.building_id==house.uid})
        self.assertIn(plan.uid,state.interiors)
        self.assertTrue(all(stair.target_space_id in state.interiors
                            for floor in state.interiors.values() for stair in floor.stairs))
        for container in storage.for_property(house.uid):
            state.containers['indoor-storage:'+container.uid]=container
        with tempfile.TemporaryDirectory(prefix='worldseed-storage-save-') as folder:
            path=Path(folder)/'indoor-storage.db'
            db=WorldDatabase.create(path,'Indoor storage proof','ab'*32)
            try:
                db.save_state(turn=1,tile_deltas={},player_id=1,position=WorldPos(0,0),inventory={},sim_state=state.to_dict())
                self.assertEqual(db.verify(),[])
            finally:db.close()
            db=WorldDatabase.open(path)
            try:self.assertEqual(LivingWorldState.from_dict(db.load_sim_state()).to_dict(),state.to_dict())
            finally:db.close()
            proof=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'tools'/'verify_save.py'),str(path)],
                                 capture_output=True,text=True,timeout=30)
            self.assertEqual(proof.returncode,0,proof.stdout+proof.stderr)
            self.assertIn('Save integrity: OK',proof.stdout)
            print(proof.stdout.strip())


if __name__=='__main__':unittest.main()
