"""Outdoor migration conserves inventories and sends saved workers indoors."""
from types import SimpleNamespace
import unittest

from tests import test_dev50_interior_storage as fixtures
from tests import test_interior_work as work_fixtures
from tests import test_workplace_logistics as logistics_fixtures
from worldseed.systems.state import ContainerState, LivingWorldState, pos_key


class IndoorBuildingStorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.InteriorStorageTests.setUpClass()
        work_fixtures.InteriorWorkshopTests.setUpClass()
        logistics_fixtures.WorkplaceLogisticsTests.setUpClass()

    def test_all_enclosed_property_stores_are_indoor_and_frontage_is_clear(self):
        sim,town,storage=fixtures.InteriorStorageTests().fixture()
        structures=sim.settlement_physicalization.skeleton_for(town.uid).structures
        tested=0
        for structure in structures:
            if not structure.enclosed:continue
            containers=storage.for_property(structure.uid)
            for c in containers:
                self.assertEqual(c.interior_space_id,'interior:'+structure.uid)
                self.assertIs(sim.state.containers['indoor-storage:'+c.uid],c)
            if containers:
                frontage=sim.settlement_physicalization.frontage_for(structure.uid)
                self.assertIsNone(sim.building.container_at(frontage))
                self.assertTrue(sim.building.passable(frontage,True))
                tested+=1
        self.assertGreater(tested,10)

    def test_legacy_crate_and_ore_bin_move_without_stock_lock_or_identity_loss(self):
        sim,town,storage=fixtures.InteriorStorageTests().fixture()
        structure=next(s for s in sim.settlement_physicalization.skeleton_for(town.uid).structures if s.function=='smithy')
        c=next(c for c in storage.for_property(structure.uid) if c.uid=='property-storage:'+structure.uid)
        frontage=sim.settlement_physicalization.frontage_for(structure.uid)
        del sim.state.containers['indoor-storage:'+c.uid]
        c.interior_space_id=c.interior_furniture_uid='';c.x,c.y,c.z=frontage.x,frontage.y,frontage.z
        c.picked=True;c.locked=False;c.last_tampered_minute=42;c.keyholder_uids=['npc:guest']
        sim.state.containers[pos_key(c.x,c.y,c.z)]=c
        oldbin=ContainerState('mining-house-storage:'+structure.uid,c.x+1,c.y,0,'old-owner',320000,180000,
            {'core:iron_ore':5},kind='workplace',property_id=structure.uid,settlement_id=town.uid)
        sim.state.containers[pos_key(oldbin.x,oldbin.y,0)]=oldbin
        goods={r.uid:dict(r.items) for r in sim.state.containers.values()};stocks=dict(town.stocks)
        self.assertFalse(sim.building.passable(frontage,True))
        storage.sync_active()
        self.assertTrue(sim.building.passable(frontage,True))
        self.assertEqual(goods,{r.uid:dict(r.items) for r in sim.state.containers.values()})
        self.assertEqual(town.stocks,stocks)
        self.assertIs(sim.state.containers['indoor-storage:'+oldbin.uid],oldbin)
        self.assertEqual(oldbin.owner,'old-owner')
        self.assertTrue(c.picked);self.assertFalse(c.locked);self.assertEqual(c.last_tampered_minute,42)
        self.assertIn('npc:guest',c.keyholder_uids)
        sim.interiors.prepare_workplace(structure.uid)
        self.assertTrue(c.interior_furniture_uid);self.assertTrue(oldbin.interior_furniture_uid)
        saved=sim.state.to_dict();storage.sync_active()
        self.assertEqual(sim.state.to_dict(),saved)
        self.assertEqual(LivingWorldState.from_dict(saved).to_dict(),saved)

    def test_saved_outdoor_cargo_task_redirects_and_delivers_inside(self):
        sim,town,npc,workshop,activities,professions,c=work_fixtures.InteriorWorkshopTests().fixture()
        npc.inventory={'core:iron_bloom':1}
        before=c.items.get('core:iron_bloom',0)
        npc.tasks=[dict(kind='move',x=c.x-5,y=c.y,container_uid=c.uid,storage_task=True),
                   dict(kind='perform',action='profession_deposit',container_uid=c.uid,items=['core:iron_bloom'],storage_task=True)]
        self.assertTrue(professions.storage_access.repair_indoor_route(npc))
        self.assertIn('interior_storage_door_uid',npc.tasks[0])
        for minute in range(605,1600,5):
            sim.clock.minute=minute;sim.interiors.tick_update(minute)
            if npc.uid not in sim.state.interior_actors:sim.npcs.execute_tick(npc,town,minute,sim.player_pos)
            if c.items.get('core:iron_bloom',0)>before:break
        self.assertEqual(c.items.get('core:iron_bloom',0),before+1,npc.tasks)
        self.assertEqual(npc.inventory.get('core:iron_bloom',0),0)

    def test_indoor_workplace_logistics_retains_inputs_and_requires_pickup_reach(self):
        state,town,npc,c,economy,logistics,proc=logistics_fixtures.WorkplaceLogisticsTests().fixture(
            occupation='carpenter',process_id='core:logging',items={'core:wood':5},stocks={},workers=1)
        c.interior_space_id='interior:'+npc.workplace_id
        reached=[False]
        logistics.storage_access=SimpleNamespace(
            transfer_tasks=lambda *a:[dict(kind='move',storage_task=True,container_uid=c.uid,interior_storage_door_uid='door'),
                                      dict(kind='perform',action='workplace_pickup',storage_task=True,container_uid=c.uid)],
            in_reach=lambda *a:reached[0])
        self.assertIs(logistics._storage_for_property(npc.workplace_id),c)
        economy._run_process(town,proc,1,1,1440)
        shipment=next(iter(state.workplace_shipments.values()))
        self.assertEqual(c.items['core:wood']+shipment.quantity,8)
        self.assertFalse(logistics.pickup_shipment(shipment.uid,npc.uid,1450))
        reached[0]=True
        self.assertTrue(logistics.pickup_shipment(shipment.uid,npc.uid,1455))
        self.assertTrue(any(t.get('interior_storage_door_uid') for t in npc.tasks))


if __name__=='__main__':unittest.main()
