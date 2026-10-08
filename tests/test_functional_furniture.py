"""One inventory per real furnishing, with conserved goods and useful storage."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests import test_dev50_interior_storage as storage_fixtures
from tests import test_interior_workstation_ui as workstation_fixtures
from worldseed.app import _interior_context_menu
from worldseed.persistence.validation import validate_sim_state
from worldseed.systems.furniture_storage import catalog, materialize_storage, storage_function
from worldseed.systems.interior_storage import bind_storage
from worldseed.systems.interior_state import InteriorFurniture, InteriorPlan
from worldseed.systems.npc_home_storage import NPCStorageAccess
from worldseed.systems.physical_goods import SettlementPhysicalGoodsSystem
from worldseed.systems.state import ContainerState, LivingWorldState


class FunctionalFurnitureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        storage_fixtures.InteriorStorageTests.setUpClass()
        cls.registry=storage_fixtures.InteriorStorageTests.registry

    def fixture(self):
        sim,town,storage=storage_fixtures.InteriorStorageTests().fixture()
        house=next(s for s in sim.settlement_physicalization.skeleton_for(town.uid).structures
                   if s.function=='residence')
        return sim,town,storage,house

    def test_preparation_adds_empty_storage_on_each_floor_without_minting_goods(self):
        sim,town,storage,house=self.fixture()
        goods={c.uid:dict(c.items) for c in sim.state.containers.values()}
        stocks=dict(town.stocks)
        plan=sim.interiors.prepare_workplace(house.uid)
        floors=[p for p in sim.state.interiors.values() if p.building_id==house.uid]
        self.assertGreater(len(floors),1)
        for floor in floors:
            eligible=[f for f in floor.furniture if storage_function(f.piece_id)]
            self.assertTrue(eligible)
            for f in eligible:
                matches=[c for c in sim.state.containers.values() if c.interior_furniture_uid==f.uid]
                self.assertEqual(len(matches),1,f.uid)
                self.assertEqual(matches[0].interior_space_id,floor.uid)
        for c in sim.state.containers.values():
            self.assertEqual(c.items,goods.get(c.uid,{}))
        self.assertEqual(town.stocks,stocks)
        before=sim.state.to_dict()
        sim.interiors.prepare_workplace(house.uid)
        storage.sync_active()
        self.assertEqual(sim.state.to_dict(),before)
        self.assertFalse([i for i in validate_sim_state(before) if 'storage' in i])

    def test_all_catalog_pieces_and_variants_use_existing_content_and_real_capacities(self):
        for piece,rule in catalog().items():
            self.assertIn(piece,self.registry.settlement_pieces)
            self.assertGreater(rule['mass_g'],0)
            self.assertGreater(rule['volume_ml'],0)
        self.assertEqual(storage_function('core:painted_wardrobe_piece'),storage_function('core:wardrobe_piece'))
        self.assertEqual(storage_function('core:wicker_hamper_piece')['profile'],'core:grain_bin')
        self.assertIsNone(storage_function('core:bed_piece'))

    def test_saved_and_repositioned_furniture_keeps_inventory_lock_and_identity(self):
        plan=InteriorPlan('interior:home','home','door:home',0,0,0,12000,12000,
                          furniture=[InteriorFurniture('desk','core:writing_desk_piece',1000,1000,1200,800)])
        state=LivingWorldState();state.interiors[plan.uid]=plan
        geometry=plan.to_dict()
        materialize_storage(state,plan,self.registry)
        self.assertEqual(plan.to_dict(),geometry)
        c=next(iter(state.containers.values()))
        c.items={'core:wood':2};c.locked=False;c.picked=True;c.last_tampered_minute=60
        restored=LivingWorldState.from_dict(state.to_dict())
        p=restored.interiors[plan.uid];p.furniture[0].x+=1000
        before=restored.to_dict();materialize_storage(restored,p,self.registry);bind_storage(p,restored.containers.values())
        self.assertEqual(restored.to_dict(),before)
        self.assertEqual(len(restored.containers),1)

    def test_duplicate_inventory_binding_is_repaired_without_copying_goods(self):
        plan=InteriorPlan('interior:home','home','door:home',0,0,0,12000,12000,
            furniture=[InteriorFurniture('chest:a','core:house_chest_piece',1000,1000,1200,800),
                       InteriorFurniture('chest:b','core:house_chest_piece',4000,1000,1200,800)])
        state=LivingWorldState();state.interiors[plan.uid]=plan
        for uid,qty in [('a',2),('b',3)]:
            state.containers['indoor-storage:'+uid]=ContainerState(uid,0,0,0,'owner',90000,140000,
                {'core:wood':qty},profile_id='core:household_chest',property_id='home',
                interior_space_id=plan.uid,interior_furniture_uid='chest:a')
        self.assertTrue(any('duplicate interior storage furnishing' in i for i in validate_sim_state(state.to_dict())))
        bind_storage(plan,state.containers.values())
        self.assertEqual(len({c.interior_furniture_uid for c in state.containers.values()}),2)
        self.assertEqual(sum(c.items['core:wood'] for c in state.containers.values()),5)
        self.assertFalse([i for i in validate_sim_state(state.to_dict()) if 'storage' in i])

    def test_home_storage_prefers_pantry_clothes_and_work_goods_and_handles_full_container(self):
        state=LivingWorldState()
        for profile in ('household_chest','pantry_cabinet','wardrobe'):
            c=ContainerState(profile,0,0,0,'npc',100000,100000,profile_id='core:'+profile,
                             property_id='home',settlement_id='town')
            state.containers[profile]=c
        goods=SettlementPhysicalGoodsSystem(state,self.registry)
        access=NPCStorageAccess(state,None,None,None,goods)
        npc=SimpleNamespace(home_id='home',settlement_id='town')
        for item,expected in [('core:bread','pantry_cabinet'),('core:woven_cloth','wardrobe'),('core:wood','household_chest')]:
            self.assertEqual(access.home_storage(npc,(item,)).uid,expected)
        state.containers['pantry_cabinet'].capacity_volume_ml=0
        self.assertNotEqual(access.home_storage(npc,('core:bread',)).uid,'pantry_cabinet')

    def test_workbench_keeps_crafting_and_storage_actions_observational(self):
        workstation_fixtures.InteriorWorkstationUITests.setUpClass()
        sim,plan,f,inv,messages=workstation_fixtures.InteriorWorkstationUITests().fixture('core:carpenter_bench_piece')
        materialize_storage(sim.state,plan,self.registry);sim.interiors._bind_storage(plan)
        sim.property_storage=SimpleNamespace(blocks_actor=lambda *_:False)
        ctx=SimpleNamespace(sim=sim,entities=sim.entities,player_id=sim.player_id)
        before=sim.state.to_dict()
        with patch('worldseed.app._select',return_value=None) as select:
            _interior_context_menu(ctx,object(),1500,1500)
        rows=dict(select.call_args.args[2])
        self.assertIn('open_storage',rows);self.assertIn('use',rows)
        self.assertEqual(sim.state.to_dict(),before)

    def test_desk_storage_uses_real_player_transfers_and_capacity(self):
        from worldseed.core.coords import WorldPos
        from worldseed.entities.components import Inventory
        from worldseed.sim.engine import Simulation
        from worldseed.sim.commands import StoreCommand, TakeFromContainerCommand
        from worldseed.systems.interior_state import InteriorActor
        sim,town,storage,house=self.fixture()
        sim.interiors.prepare_workplace(house.uid)
        c=next(c for c in storage.for_property(house.uid) if c.uid.startswith('furniture-storage:')
               and storage_function(next(f.piece_id for f in sim.state.interiors[c.interior_space_id].furniture
                                         if f.uid==c.interior_furniture_uid))['volume_ml']<=40000)
        plan=sim.state.interiors[c.interior_space_id]
        f=next(f for f in plan.furniture if f.uid==c.interior_furniture_uid)
        sim.interiors._put_actor('player',InteriorActor(plan.uid,*sim.interiors.fixture_use_position(plan,f)))
        c.owner='player';c.items={}
        inv=Inventory({'core:wood':2})
        sim.entities=SimpleNamespace(get=lambda *_:inv);sim.player_pos=WorldPos(*house.entrance)
        sim._message=lambda _:None;sim._command_container=lambda uid:Simulation._command_container(sim,uid)
        Simulation._store(sim,StoreCommand(1,'core:wood',1,c.uid))
        self.assertEqual(c.items,{'core:wood':1});self.assertEqual(inv.count('core:wood'),1)
        c.capacity_volume_ml=0
        Simulation._store(sim,StoreCommand(1,'core:wood',1,c.uid))
        self.assertEqual(c.items,{'core:wood':1});self.assertEqual(inv.count('core:wood'),1)
        Simulation._take_container(sim,TakeFromContainerCommand(1,'core:wood',1,c.uid))
        self.assertEqual(inv.count('core:wood'),2);self.assertEqual(c.items.get('core:wood',0),0)

    def test_refreshed_home_sprites_have_real_alpha_and_unique_files(self):
        from PIL import Image
        from worldseed.presentation.visuals import VisualRegistry
        visuals=VisualRegistry.load_default();paths=[]
        for profile in ('household_chest','pantry_cabinet','wardrobe'):
            path=visuals.resolve(visuals.ref('containers','core:'+profile));paths.append(path)
            self.assertIn('dev57',str(path))
            with Image.open(path) as image:
                self.assertEqual(image.mode,'RGBA')
                low,high=image.getchannel('A').getextrema()
                self.assertEqual(low,0);self.assertGreater(high,240)
        self.assertEqual(len(set(paths)),3)


if __name__=='__main__':unittest.main()
