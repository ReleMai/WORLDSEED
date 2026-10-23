"""Crafting ingredients come from reachable world resources and real vessels."""
from types import SimpleNamespace
import unittest

from worldseed.app import _action_palette
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Position
from worldseed.entities.store import EntityStore
from worldseed.sim.commands import CollectWaterCommand
from worldseed.sim.engine import Simulation
from worldseed.systems.state import LivingWorldState
from worldseed.ui.navigation import ACTION_WORK


class CraftingWaterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.registry=ContentRegistry.load(DATA_DIR)

    def make(self,tags=('water_source','freshwater'),well=False,fire=True,items=None):
        sim=Simulation.__new__(Simulation)
        sim.registry=self.registry;sim.entities=EntityStore();pid=sim.entities.spawn(preferred_id=1)
        sim.entities.add(pid,Position(WorldPos(0,0,0)))
        sim.entities.add(pid,Inventory(items if items is not None else {'core:clay_pot':1}))
        sim.world=SimpleNamespace(tile_at=lambda pos:SimpleNamespace(terrain=SimpleNamespace(tags=tags)))
        sim.state=LivingWorldState()
        sim.clock=SimpleNamespace(minute=480)
        sim.environment=SimpleNamespace(weather=SimpleNamespace(at=lambda *_:{'rain':0,'wind_speed':0}))
        sim.settlement_physicalization=SimpleNamespace(piece_def_at=lambda pos:SimpleNamespace(tags=('well',)) if well else None)
        sim._player_station_ids=lambda:{'core:campfire'} if fire else set()
        sim.log=[];sim.turn=0
        return sim,sim.entities.get(pid,Inventory)

    def test_rejected_collection_command_leaves_time_and_turn_unchanged(self):
        sim,inv=self.make(tags=('surface',))
        sim.debug=SimpleNamespace(event=lambda *args,**kwargs:None)
        sim.clock=SimpleNamespace(minute=480);sim.combat_active=lambda:False
        before=dict(inv.items)
        sim.execute(CollectWaterCommand(1))
        self.assertEqual((sim.turn,sim.clock.minute,inv.items),(0,480,before))
        sim.execute(CollectWaterCommand(2))
        self.assertEqual((sim.turn,sim.clock.minute,inv.items),(0,480,before))

    def test_boiling_consumes_time_and_retains_the_real_pot(self):
        sim,inv=self.make()
        self.assertEqual(sim._collect_water(CollectWaterCommand(1)),20)
        self.assertEqual(inv.items,{'core:clay_pot':1,'core:clean_water':1})

    def test_surface_water_requires_fresh_source_fire_and_pot(self):
        for kwargs in ({'tags':('water','saltwater')},{'tags':('water','brackish')},
                       {'tags':('surface',)},{'fire':False},{'items':{'core:wooden_bowl':1}},
                       {'items':{}},{'items':{'core:wood':1}}):
            with self.subTest(kwargs=kwargs):
                sim,inv=self.make(**kwargs);before=dict(inv.items)
                self.assertEqual(sim._collect_water(CollectWaterCommand(1)),0)
                self.assertEqual(inv.items,before)

    def test_real_well_allows_a_reusable_bowl_without_fire(self):
        sim,inv=self.make(tags=('surface',),well=True,fire=False,items={'core:wooden_bowl':1})
        self.assertEqual(sim._collect_water(CollectWaterCommand(1)),5)
        self.assertEqual(inv.items,{'core:wooden_bowl':1,'core:clean_water':1})

    def test_destroyed_well_does_not_supply_water(self):
        sim,inv=self.make(tags=('surface',),well=True,fire=False,items={'core:wooden_bowl':1})
        sim.settlement_physicalization.structure_at=lambda pos:SimpleNamespace(destroyed=True)
        self.assertEqual(sim._collect_water(CollectWaterCommand(1)),0)
        self.assertNotIn('core:clean_water',inv.items)
        self.assertIn('well',self.registry.settlement_pieces['core:village_well_piece'].tags)

    def test_work_action_dispatches_the_collection_command(self):
        commands=[]
        sim=SimpleNamespace(execute=commands.append,log=[])
        ctx=SimpleNamespace(sim=sim,player_id=1)
        class Term:
            def __init__(self):self.keys=iter(('DOWN','DOWN','\r','DOWN','\r'))
            def size(self):return 100,30
            def present(self,text):pass
            def read_key(self):return next(self.keys)
        self.assertIn('collect_water',dict(ACTION_WORK))
        _action_palette(ctx,Term())
        self.assertEqual(commands,[CollectWaterCommand(1)])


if __name__=='__main__':unittest.main()
