"""Blueprint command tests; no graphics or procedural world generation."""
import unittest
from types import SimpleNamespace
from worldseed.core.coords import WorldPos
from worldseed.systems.homestead_blueprints import HomesteadBlueprintService, catalog, footprint, doorway, progress

class Inventory:
    def __init__(self,items=None):self.items=dict(items or {})
    def count(self,i):return self.items.get(i,0)
    def add(self,i,n):self.items[i]=self.count(i)+n
    def remove(self,i,n):
        if self.count(i)<n:return False
        self.items[i]-=n;return True

class HomesteadBlueprintTests(unittest.TestCase):
    def setUp(self):
        self.sim=SimpleNamespace(
            state=SimpleNamespace(homesteads={},uid=lambda prefix:"home:1",crops={},creatures={},npcs={}),
            player_pos=WorldPos(-1,-1,0),
            world=SimpleNamespace(tile_at=lambda p:SimpleNamespace(terrain=SimpleNamespace(passable=True,tags=()))),
            building=SimpleNamespace(passable=lambda p,w:True,container_at=lambda p:None),
            resources=SimpleNamespace(blocks_movement=lambda p:False),
            settlement_physicalization=SimpleNamespace(cell_at=lambda p:None))
        self.system=HomesteadBlueprintService(self.sim)
    def test_marker_reserves_footprint_without_spending(self):
        self.assertTrue(self.system.place("log_cabin_01",0,0)[0])
        self.assertEqual(len(footprint(self.sim.state.homesteads["home:1"])),9)
        self.assertEqual(self.sim.state.homesteads["home:1"]["stored"],{})
        self.assertFalse(self.system.place("log_cabin_01",0,0)[0])
    def test_rotated_door_access(self):
        for direction in range(4):
            site={"home_id":"log_cabin","style_id":"log_cabin_01","x":0,"y":0,"z":0,"orientation":direction}
            inside,outside=doorway(site)
            self.assertIn(inside,footprint(site))
            self.assertNotIn(outside,footprint(site))
    def test_partial_deposits_stages_and_full_build(self):
        self.assertTrue(self.system.place("log_cabin_01",0,0)[0])
        inv=Inventory({"core:wood":7})
        self.assertTrue(self.system.deposit("home:1","core:wood",2,inv)[0])
        self.assertEqual(inv.count("core:wood"),5)
        self.assertFalse(self.system.advance("home:1")[0])
        for iid,n in catalog()[0]["log_cabin"]["materials"].items():
            inv.add(iid,n+10)
            self.assertTrue(self.system.deposit("home:1",iid,n,inv)[0])
        self.assertEqual(sum(max(0,n-h) for h,n in progress(self.sim.state.homesteads["home:1"]).values()),0)
        for _ in range(4):self.assertTrue(self.system.advance("home:1")[0])
        self.assertEqual(self.sim.state.homesteads["home:1"]["stage"],4)
        self.assertFalse(self.system.cancel("home:1",inv)[0])
    def test_cancel_returns_materials(self):
        self.assertTrue(self.system.place("log_cabin_01",0,0)[0])
        inv=Inventory({"core:wood":4})
        self.assertTrue(self.system.deposit("home:1","core:wood",2,inv)[0])
        self.assertTrue(self.system.cancel("home:1",inv)[0])
        self.assertEqual(inv.count("core:wood"),4)
        self.assertEqual(self.sim.state.homesteads,{})
    def test_occupied_site_rejected(self):
        self.sim.resources.blocks_movement=lambda p:(p.x,p.y)==(1,1)
        self.assertFalse(self.system.place("log_cabin_01",0,0)[0])

if __name__=="__main__":unittest.main()
