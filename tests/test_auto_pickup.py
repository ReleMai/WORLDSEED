"""Bounded click-to-pickup, no hidden-cell routing or fictitious inventory."""
from __future__ import annotations
from types import SimpleNamespace as NS
from unittest import TestCase
from worldseed.core.coords import WorldPos
from worldseed.sim.commands import MoveCommand, PickupCommand
from worldseed.systems.state import pos_key
from worldseed.ui.auto_pickup import execute_visible_pickup


class FakeSim:
    def __init__(self):
        self.player_pos=WorldPos(0,0,0)
        self.visible_tiles_set={pos_key(x,y,0) for x in range(-2,8) for y in range(-2,8)}
        self.registry=NS(terrains={'core:grass':NS(passable=True)})
        self.world=NS(prepared_tile_at=lambda p:NS(terrain_id='core:grass'))
        self.settlement_physicalization=NS(shell_at=lambda p:None,clears_natural_feature=lambda p:False)
        self.resources=NS(blocks_movement=lambda p:False)
        self.building=NS(passable=lambda p,w:True)
        self.property_security=NS(blocks_player=lambda p:False)
        self.environment=NS(fluid_passable=lambda p:True)
        self.interiors=NS(player_presence=lambda:None)
        self.state=NS(ground_piles={})
        self.calls=[]
        self.fight=False

    def combat_active(self):
        return self.fight

    def execute(self,command):
        self.calls.append(command)
        if isinstance(command,MoveCommand):
            self.player_pos=self.player_pos.moved(command.dx,command.dy)
        if isinstance(command,PickupCommand):
            pos=self.player_pos.moved(command.dx,command.dy)
            pile=self.state.ground_piles[pos_key(pos.x,pos.y,pos.z)]
            if command.item_id:pile.items.pop(command.item_id,None)
            else:pile.items.clear()


class AutoPickupTests(TestCase):
    def test_distant_visible_pile_walks_then_collects(self):
        sim=FakeSim()
        sim.state.ground_piles[pos_key(4,1,0)]=NS(items={'core:stone':3})
        msg=execute_visible_pickup(sim,1,WorldPos(4,1,0))
        self.assertIn('Collected from 1',msg)
        self.assertTrue(any(isinstance(cmd,MoveCommand) for cmd in sim.calls))
        self.assertIsInstance(sim.calls[-1],PickupCommand)
        self.assertLessEqual(abs(4-sim.player_pos.x)+abs(1-sim.player_pos.y),1)

    def test_nearby_same_type_leaves_unrelated_goods_untouched(self):
        sim=FakeSim()
        for x in (2,3,4):
            sim.state.ground_piles[pos_key(x,0,0)]=NS(items={'core:stone':2,'core:wood':1})
        msg=execute_visible_pickup(sim,1,WorldPos(2,0,0),item_id='core:stone',nearby=True)
        self.assertIn('Collected from 3',msg)
        self.assertTrue(all(p.items.get('core:wood')==1 for p in sim.state.ground_piles.values()))

    def test_unknown_target_rejected_without_movement(self):
        sim=FakeSim()
        sim.visible_tiles_set.discard(pos_key(3,0,0))
        sim.state.ground_piles[pos_key(3,0,0)]=NS(items={'core:stone':1})
        self.assertIn('in sight',execute_visible_pickup(sim,1,WorldPos(3,0,0)))
        self.assertFalse(sim.calls)

    def test_blocked_path_never_pulls_items_through_wall(self):
        sim=FakeSim()
        sim.world.prepared_tile_at=lambda p:None
        sim.state.ground_piles[pos_key(4,0,0)]=NS(items={'core:stone':1})
        self.assertIn('No safe visible path',execute_visible_pickup(sim,1,WorldPos(4,0,0)))
        self.assertFalse(sim.calls)
