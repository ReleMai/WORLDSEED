from copy import deepcopy
from types import SimpleNamespace
import unittest

from tests import test_phase4_professions as profession_fixtures
from worldseed.core.coords import WorldPos
from worldseed.systems.ai import NPCSystem
from worldseed.systems.economy import EconomySystem
from worldseed.systems.household_economy import HouseholdEconomySystem
from worldseed.systems.npc_commerce import NPCCommerceSystem
from worldseed.systems.npc_home_storage import NPCStorageAccess
from worldseed.systems.state import ContainerState, LivingWorldState, NPCState


class NPCProductionEconomyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        profession_fixtures.Phase4ProfessionTests.setUpClass()
        cls.registry=profession_fixtures.Phase4ProfessionTests.registry

    def fixture(self, occupation='lumberjack', process='core:logging', piece=None):
        rows=profession_fixtures.Phase4ProfessionTests().make(occupation,process,piece_id=piece)
        state,town,npc,world,physical,activities,goods,resources,professions,storage=rows
        history=SimpleNamespace(record=lambda *a,**k:None)
        economy=EconomySystem(state,self.registry,b'chain',history)
        access=NPCStorageAccess(state,world,physical,None,goods)
        commerce=NPCCommerceSystem(state,self.registry,economy,goods,physical,access)
        ai=NPCSystem(state,b'chain',history,world)
        ai.attach_activity_system(activities);ai.attach_profession_system(professions)
        ai.commerce=commerce;ai.storage_access=access
        professions.storage_access=access;professions.commerce=commerce
        home=ContainerState('home-store',-5,5,0,npc.uid,500000,500000,
                            kind='property',property_id=npc.home_id,settlement_id=town.uid)
        state.containers['home']=home
        town.wealth=10000;town.stocks={}
        npc.wealth=200;npc.hunger=npc.thirst=npc.rest=0
        return SimpleNamespace(state=state,town=town,npc=npc,world=world,physical=physical,
                               activities=activities,goods=goods,professions=professions,
                               commerce=commerce,access=access,ai=ai,home=home,economy=economy)

    def test_autonomous_tree_home_sale_carpenter_purchase_craft_home_sale(self):
        f=self.fixture()
        crafter=NPCState('npc:carpenter','Carpenter',30,'carpenter',[],0,0,0,f.town.uid,'',
                         home_id='home:carpenter',workplace_id='work:carpenter',wealth=200,
                         work_assignment_day=0,assigned_process_id='core:woodcraft')
        crafter.hunger=crafter.thirst=crafter.rest=0
        f.state.npcs[crafter.uid]=crafter
        f.ai._index_npc(crafter)
        f.physical._skeleton.pieces.append(profession_fixtures.fixture_piece('bench','core:carpenter_bench_piece',crafter.workplace_id,8,3))
        home=ContainerState('carpenter-home',9,6,0,crafter.uid,500000,500000,
                            kind='property',property_id=crafter.home_id,settlement_id=f.town.uid)
        f.state.containers['carpenter-home']=home
        cash=f.town.wealth+sum(n.wealth for n in f.state.npcs.values())
        positions=set();seen_cargo=False;seen_stored=False
        for minute in range(600,1400,5):
            f.ai.tick_update(minute,WorldPos(0,0,0))
            positions.add((f.npc.x,f.npc.y))
            seen_cargo |= f.npc.inventory.get('core:wood',0)>0
            seen_stored |= f.home.items.get('core:wood',0)>2
            if f.town.stocks.get('core:wooden_bowl',0)>0:break
        self.assertGreater(f.town.stocks.get('core:wooden_bowl',0),0,[(n.uid,n.tasks) for n in f.state.npcs.values()])
        self.assertTrue(seen_cargo);self.assertTrue(seen_stored);self.assertGreater(len(positions),3)
        self.assertIn('5,0,0',f.state.resource_depletion)
        transactions=list(f.state.market_transactions.values())
        self.assertTrue(any(t.actor_uid==f.npc.uid and t.kind=='npc_output_sale' for t in transactions))
        self.assertTrue(any(t.actor_uid==crafter.uid and t.kind=='npc_input_purchase' for t in transactions))
        self.assertTrue(any(t.actor_uid==crafter.uid and t.kind=='npc_output_sale' for t in transactions))
        self.assertTrue(any(t.container_uid==home.uid and t.direction=='deposit' for t in f.state.physical_goods_transfers.values()))
        self.assertEqual(cash,f.town.wealth+sum(n.wealth for n in f.state.npcs.values()))
        # Wood has one owner; only the carpenter's recorded batches consume it.
        extracted=sum(t.items.get('core:wood',0) for t in f.state.physical_goods_transfers.values()
                      if t.source_kind=='profession_output' and t.actor_uid==f.npc.uid)
        wood=f.town.stocks.get('core:wood',0)+sum(c.items.get('core:wood',0) for c in f.state.containers.values())+sum(n.inventory.get('core:wood',0) for n in f.state.npcs.values())
        bowls=f.town.stocks.get('core:wooden_bowl',0)+sum(c.items.get('core:wooden_bowl',0) for c in f.state.containers.values())+sum(n.inventory.get('core:wooden_bowl',0) for n in f.state.npcs.values())
        self.assertEqual(extracted,wood+bowls)

    def test_paid_buy_is_at_market_atomic_and_cannot_repeat_after_roundtrip(self):
        f=self.fixture('carpenter','core:woodcraft','core:carpenter_bench_piece')
        f.town.stocks={'core:wood':3}
        task=f.commerce.plan_inputs(f.npc,f.town,{'core:wood':1},600)[-1]
        cash=f.npc.wealth+f.town.wealth
        f.npc.x=20
        self.assertFalse(f.commerce.execute(f.npc,f.town,task,605))
        self.assertEqual(f.town.stocks['core:wood'],3)
        f.npc.x=0
        self.assertTrue(f.commerce.execute(f.npc,f.town,task,610))
        f.npc.tasks=[task]
        restored=LivingWorldState.from_dict(f.state.to_dict())
        saved=restored.npcs[f.npc.uid]
        self.assertEqual(saved.inventory,{'core:wood':1})
        f.commerce.state=restored
        self.assertFalse(f.commerce.execute(saved,restored.settlements[f.town.uid],saved.tasks[0],615))
        self.assertEqual(cash,saved.wealth+restored.settlements[f.town.uid].wealth)

    def test_failed_purchase_keeps_cash_goods_and_cancels_dependent_work(self):
        f=self.fixture();f.town.stocks={'core:wood':1}
        task={'action':'commerce_buy','items':{'core:wood':1}}
        f.npc.wealth=0;f.npc.tasks=[{'kind':'activity'}]
        self.assertFalse(f.commerce.execute(f.npc,f.town,task,600))
        self.assertEqual(f.town.stocks,{'core:wood':1});self.assertFalse(f.npc.inventory)
        self.assertEqual(f.npc.wealth,0);self.assertFalse(f.npc.tasks)

    def test_private_neighbour_stock_is_not_a_free_input(self):
        f=self.fixture();f.home.property_id='neighbour';f.home.items={'core:wood':10}
        self.assertIsNone(f.commerce.plan_inputs(f.npc,f.town,{'core:wood':1},600))
        self.assertFalse(f.professions.withdraw(f.npc,f.town,{'container_uid':f.home.uid,'items':{'core:wood':1}},600))
        self.assertEqual(f.home.items,{'core:wood':10})

    def test_reserves_full_storage_and_cashless_market_keep_goods(self):
        f=self.fixture();f.home.items={'core:wood':2,'core:wheat_seed':4,'core:bread':2}
        self.assertEqual(f.commerce.plan_surplus(f.npc,f.town,f.home.items,600),[])
        f.home.items={'core:wood':10};f.town.wealth=0
        self.assertEqual(f.commerce.plan_surplus(f.npc,f.town,f.home.items,600),[])
        f.npc.inventory={'core:wood':3};f.npc.x,f.npc.y=-5,4
        f.home.capacity_mass_g=0
        self.assertFalse(f.professions.deposit(f.npc,f.town,{'container_uid':f.home.uid,'items':['core:wood']},610))
        self.assertEqual(f.npc.inventory,{'core:wood':3})

    def test_household_consumes_bread_roast_and_smoked_fish(self):
        for item in ('core:bread','core:cooked_meat','core:smoked_fish'):
            with self.subTest(item=item):
                f=self.fixture();f.npc.family_uid='family';f.home.items={item:2}
                households=HouseholdEconomySystem(f.state,b'foods',self.registry,f.economy)
                h=households.sync()[0]
                households._consume_food(h,1440)
                self.assertEqual(h.food_shortage,0);self.assertEqual(f.home.items[item],1)

    def test_transfer_audit_is_bounded_and_does_not_own_cargo(self):
        f=self.fixture();f.home.items={'core:wood':1}
        for minute in range(600):
            f.goods.withdraw(f.npc,f.home,minute,items={'core:wood':1})
            f.goods.deposit(f.npc,f.home,minute,items={'core:wood':1})
        self.assertLessEqual(len(f.state.physical_goods_transfers),1000)
        self.assertEqual(f.home.items,{'core:wood':1});self.assertFalse(f.npc.inventory)

    def test_household_physically_carries_market_food_home_before_consumption(self):
        from worldseed.persistence.validation import validate_sim_state
        f=self.fixture();f.npc.family_uid='family';f.town.stocks={'core:bread':4}
        system=HouseholdEconomySystem(f.state,b'house',self.registry,f.economy)
        system.storage_access=f.access;system.commerce=f.commerce
        system.active_carrier=lambda npc:True
        f.ai.attach_households(system)
        h=system.sync()[0]
        cash=f.town.wealth+f.npc.wealth
        self.assertEqual(system._queue_purchase(h,'core:bread',2,600),2)
        d=next(iter(f.state.household_deliveries.values()))
        self.assertTrue(d.physical_cargo)
        self.assertEqual(f.town.stocks['core:bread'],2)
        f.ai.execute_tick(f.npc,f.town,605,WorldPos(0,0,0))
        f.ai.execute_tick(f.npc,f.town,610,WorldPos(0,0,0))
        self.assertEqual(d.status,'carried');self.assertEqual(f.npc.inventory['core:bread'],2)
        self.assertEqual(system.process_overdue(10000),0)
        self.assertEqual(f.home.items.get('core:bread',0),0)
        saved=LivingWorldState.from_dict(f.state.to_dict())
        self.assertTrue(saved.household_deliveries[d.uid].physical_cargo)
        broken=deepcopy(saved.to_dict());broken['npcs'][f.npc.uid]['inventory']={}
        self.assertIn(f'household delivery exceeds carried inventory: {f.npc.uid}:core:bread',validate_sim_state(broken))
        for minute in range(615,900,5):
            f.ai.execute_tick(f.npc,f.town,minute,WorldPos(0,0,0))
            if d.status=='delivered':break
        self.assertEqual(d.status,'delivered');self.assertEqual(f.home.items['core:bread'],2)
        self.assertEqual(f.npc.inventory.get('core:bread',0),0)
        self.assertEqual(cash,f.town.wealth+f.npc.wealth)
        system._consume_food(h,1440)
        self.assertEqual(f.home.items['core:bread'],1)
        raw=f.state.to_dict();raw['household_deliveries'][d.uid].pop('physical_cargo')
        self.assertFalse(LivingWorldState.from_dict(raw).household_deliveries[d.uid].physical_cargo)

    def test_in_flight_trade_and_delivery_save_passes_verifier(self):
        import subprocess,sys,tempfile
        from pathlib import Path
        from worldseed.persistence.database import WorldDatabase
        f=self.fixture();f.town.faction_id='';f.npc.faction_id=''
        f.home.items={'core:wood':6}
        f.npc.tasks=f.commerce.plan_surplus(f.npc,f.town,['core:wood'],600)
        self.assertTrue(f.npc.tasks)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'npc-production.db'
            db=WorldDatabase.create(path,'NPC Production',b'npc-production'.hex())
            try:db.save_state(turn=0,tile_deltas={},player_id=1,position=WorldPos(0,0,0),inventory={},sim_state=f.state.to_dict())
            finally:db.close()
            result=subprocess.run([sys.executable,'tools/verify_save.py',str(path)],capture_output=True,text=True,timeout=25)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)


class InteriorHomeCargoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests.test_interior_work import InteriorWorkshopTests
        InteriorWorkshopTests.setUpClass()

    def test_worker_walks_from_workshop_into_assigned_home_and_deposits(self):
        from tests.test_interior_work import InteriorWorkshopTests
        sim,town,npc,workshop,activities,professions,_=InteriorWorkshopTests().fixture()
        access=NPCStorageAccess(sim.state,sim.world,sim.settlement_physicalization,sim.interiors,professions.goods)
        sim.npcs.storage_access=access;professions.storage_access=access
        plan=sim.interiors.prepare_workplace(npc.home_id)
        self.assertIsNotNone(plan)
        homes=[c for c in sim.state.containers.values() if c.property_id==npc.home_id and c.interior_space_id]
        self.assertTrue(homes)
        container=homes[0];before=container.items.get('core:iron_bloom',0)
        npc.inventory={'core:iron_bloom':1}
        npc.tasks=access.transfer_tasks(npc,container,'profession_deposit',['core:iron_bloom'])
        self.assertTrue(npc.tasks)
        positions=set()
        for minute in range(605,2400,5):
            sim.clock.minute=minute
            sim.interiors.tick_update(minute)
            actor=sim.state.interior_actors.get(npc.uid)
            if actor:positions.add((actor.space_id,actor.x,actor.y))
            else:sim.npcs.execute_tick(npc,town,minute,sim.player_pos)
            if container.items.get('core:iron_bloom',0)>before:break
        self.assertEqual(container.items.get('core:iron_bloom',0),before+1,npc.tasks)
        self.assertFalse(npc.inventory)
        self.assertGreater(len(positions),3)
        restored=LivingWorldState.from_dict(sim.state.to_dict())
        self.assertEqual(restored.npcs[npc.uid].inventory,{})

    def test_real_smith_workshop_home_and_market_cycle(self):
        from tests.test_interior_work import InteriorWorkshopTests
        sim,town,npc,workshop,activities,professions,storage=InteriorWorkshopTests().fixture()
        economy=EconomySystem(sim.state,sim.registry,sim.seed,SimpleNamespace(record=lambda *a,**k:None))
        access=NPCStorageAccess(sim.state,sim.world,sim.settlement_physicalization,sim.interiors,professions.goods)
        commerce=NPCCommerceSystem(sim.state,sim.registry,economy,professions.goods,sim.settlement_physicalization,access)
        for system in (sim.npcs,professions):system.storage_access=access;system.commerce=commerce
        for c in sim.state.containers.values():c.items.pop('core:iron_bloom',None)
        sim.interiors.prepare_workplace(npc.home_id)
        home=access.home_storage(npc,('core:iron_bloom',))
        self.assertIsNotNone(home)
        town.stocks['core:iron_bloom']=0;town.wealth=1000
        npc.tasks=professions.plan_work(npc,town,600)
        for minute in range(605,3000,5):
            sim.clock.minute=minute;sim.interiors.tick_update(minute)
            if npc.uid not in sim.state.interior_actors:
                sim.npcs.execute_tick(npc,town,minute,sim.player_pos)
            if town.stocks['core:iron_bloom']:break
        self.assertEqual(town.stocks['core:iron_bloom'],1,npc.tasks)
        deposits=[r for r in sim.state.physical_goods_transfers.values() if r.direction=='deposit' and r.items.get('core:iron_bloom')]
        self.assertTrue(any(r.container_uid==home.uid for r in deposits))
