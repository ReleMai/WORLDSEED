"""Resource contact, authoritative pickup conservation and duration regressions."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tools.reference_scene_fixtures import build_fixture
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Position, Vitals
from worldseed.sim.commands import GatherCommand, MoveCommand, PickupCommand
from worldseed.sim.engine import TickResult
from worldseed.systems.free_movement import update_npcs_free, update_player_free
from worldseed.systems.resources import (
    ACTOR_FOOT_RADIUS, RESOURCE_FOOT_X, RESOURCE_FOOT_Y, TREE_TRUNK_RADIUS,
    ResourceSystem,
)
from worldseed.systems.state import GroundPile, LivingWorldState, NPCState, pos_key


class ResourceCircleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)

    def setUp(self):
        self.state=LivingWorldState(clock_minute=720)
        world=SimpleNamespace(delta_source=None,tile_at=lambda p:SimpleNamespace(
            terrain_id="core:grass",terrain=self.registry.terrains["core:grass"]))
        self.system=ResourceSystem(self.state,self.registry,b"resource-contact",world)
        self.features={(0,0,0):"core:oak_tree"}
        self.system._base_feature=lambda p,minute=None:self.features.get((p.x,p.y,p.z))

    def test_open_tree_tile_edges_and_round_contact_are_distinct(self):
        s=self.system
        self.assertTrue(s.blocks_movement(WorldPos(0,0)))
        self.assertEqual(s.motion_fraction(-.1,.45,.9,.45,0),1.0)
        self.assertEqual(s.motion_fraction(.1,.15,.9,.15,0),1.0)
        fraction=s.motion_fraction(.1,.95,.9,.95,0)
        self.assertAlmostEqual(.1+.8*fraction,
            RESOURCE_FOOT_X-TREE_TRUNK_RADIUS-ACTOR_FOOT_RADIUS,places=4)
        # The projection's established grounded contact point is authoritative.
        self.assertEqual((RESOURCE_FOOT_X,RESOURCE_FOOT_Y),(.5,.95))

    def test_sprint_sweep_cannot_tunnel_even_with_clear_endpoints(self):
        self.assertLess(self.system.motion_fraction(.1,.95,.9,.95,0),1.0)
        self.assertLess(self.system.motion_fraction(.9,.95,.1,.95,0),1.0)
        self.assertEqual(self.system.motion_fraction(.1,.4,.9,.4,0),1.0)

    def test_regrown_embedded_actor_can_escape_without_going_deeper(self):
        self.assertEqual(self.system.motion_fraction(.55,.95,.9,.95,0),1.0)
        self.assertEqual(self.system.motion_fraction(.55,.95,.5,.95,0),0.0)

    def test_harvested_tree_stages_remove_trunk_without_moving_identity(self):
        pos=WorldPos(0,0)
        self.state.resource_depletion[pos_key(0,0,0)]=self.state.clock_minute
        self.assertEqual(self.system.feature_at(pos).stage,"stump")
        self.assertIsNone(self.system.trunk_radius(pos))
        self.assertEqual(self.system.motion_fraction(.1,.95,.9,.95,0),1.0)
        self.state.clock_minute+=50*1440
        self.assertEqual(self.system.feature_at(pos).stage,"sapling")
        self.assertIsNone(self.system.trunk_radius(pos))
        self.assertEqual(self.system.feature_at(pos).feature_id,"core:oak_tree")

    def test_non_tree_solid_keeps_full_cell_authority(self):
        self.features[(0,0,0)]="core:surface_boulder"
        self.assertTrue(self.system.blocks_movement(WorldPos(0,0)))
        self.assertIsNone(self.system.trunk_radius(WorldPos(0,0)))

    def test_contact_queries_are_local_and_observational(self):
        before=self.state.to_dict()
        original=self.system.trunk_radius
        queried=[]
        def query(pos):
            queried.append(pos)
            return original(pos)
        self.system.trunk_radius=query
        self.system.motion_fraction(.2,.95,.56,.95,0)
        self.assertLessEqual(len(queried),9)
        self.assertEqual(self.state.to_dict(),before)

    def test_instant_collection_depletes_once_at_same_clock_minute(self):
        self.features[(0,0,0)]="core:fallen_branches"
        inv=Inventory()
        first=self.system.harvest(WorldPos(0,0),inv,720)
        carried=dict(inv.items)
        second=self.system.harvest(WorldPos(0,0),inv,720)
        self.assertTrue(first[0]);self.assertEqual(first[2],0)
        self.assertNotIn("Work time",first[1])
        self.assertFalse(second[0]);self.assertEqual(second[2],0);self.assertEqual(second[3],{})
        self.assertEqual(inv.items,carried)
        self.assertEqual(self.state.resource_depletion,{"0,0,0":720})

    def test_work_resources_retain_time_and_tool_requirements(self):
        inv=Inventory()
        for fid in ("core:oak_tree","core:surface_boulder","core:clay_bank"):
            with self.subTest(fid=fid):
                self.features[(0,0,0)]=fid
                self.state.resource_depletion.clear()
                with patch.object(self.system,"_best_tool",return_value=1):
                    ok,_,minutes,_=self.system.harvest(WorldPos(0,0),inv,720)
                self.assertTrue(ok);self.assertGreater(minutes,0)


class AuthoritativeResourceCommandTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)

    def setUp(self):
        directory=self.enterContext(tempfile.TemporaryDirectory())
        fixture=build_fixture("camp",self.registry,Path(directory),width=640,height=480,zoom=28)
        self.addCleanup(fixture.close)
        self.sim=fixture.sim
        self.origin=self.sim.player_pos
        self.features={}
        self.sim.resources._base_feature=lambda p,minute=None:self.features.get((p.x,p.y,p.z))

    def test_tree_tile_edge_traversal_stops_at_trunk_and_keeps_legacy_step_blocked(self):
        sim=self.sim;p=self.origin;tree=p.moved(1,0)
        self.features[(tree.x,tree.y,tree.z)]="core:oak_tree"
        sim._move(MoveCommand(sim.player_id,1,0),TickResult())
        self.assertEqual(sim.player_pos,p)
        sim.state.player_fx=.95;sim.state.player_fy=.45
        update_player_free(sim,.1,1,0,False)
        self.assertEqual(sim.player_pos,tree)
        # Move to the trunk's x center above its grounded base, then south.
        sim.state.player_fx=.5;sim.state.player_fy=.45
        for _ in range(8):update_player_free(sim,.1,0,1,True)
        self.assertEqual(sim.player_pos,tree)
        self.assertAlmostEqual(sim.state.player_fy,.65,places=4)
        # A diagonal input slides around the circular edge without felling it.
        for _ in range(8):update_player_free(sim,.1,1,1,False)
        self.assertGreater(sim.player_pos.x+sim.state.player_fx,tree.x+.9)
        self.assertFalse(sim.state.resource_depletion)

    def test_non_tree_obstacle_still_blocks_continuous_entry(self):
        sim=self.sim;p=self.origin;rock=p.moved(1,0)
        self.features[(rock.x,rock.y,rock.z)]="core:surface_boulder"
        sim.state.player_fx=.95
        update_player_free(sim,.1,1,0,False)
        self.assertEqual(sim.player_pos,p)

    def test_npc_waypoints_and_interpolation_share_resource_authority(self):
        sim=self.sim;p=self.origin
        tree=p.moved(1,0);self.features[(tree.x,tree.y,0)]="core:oak_tree"
        npc=NPCState("npc:trunk-test","Walker",30,"farmer",[],tree.x,tree.y,0,"","",
            fx=.5,fy=.45,tasks=[{"kind":"move","x":tree.x,"y":tree.y+1,
                                 "_local_path":[[tree.x,tree.y+1]]}])
        sim.state.npcs[npc.uid]=npc;sim.npcs.rebuild_spatial_index()
        self.assertFalse(sim.npcs.movement_passable(npc,tree,sim.clock.minute))
        sim.npcs.continuous_motion_enabled=True
        before=(sim.clock.minute,sim.turn)
        for _ in range(20):
            update_npcs_free(sim,.1)
            distance=((npc.x+npc.fx-(tree.x+RESOURCE_FOOT_X))**2+
                      (npc.y+npc.fy-(tree.y+RESOURCE_FOOT_Y))**2)**.5
            self.assertGreaterEqual(distance,TREE_TRUNK_RADIUS+ACTOR_FOOT_RADIUS-1e-6)
        self.assertEqual((npc.x,npc.y),(tree.x,tree.y+1))
        self.assertFalse(npc.tasks)
        self.assertEqual((sim.clock.minute,sim.turn),before)

    def test_loaded_same_cell_npc_detours_south_deterministically_without_new_path(self):
        sim=self.sim;p=self.origin
        self.features[(p.x,p.y,0)]="core:oak_tree"
        traces=[]
        for _ in range(2):
            # Reconstruct a legacy saved actor with its existing center route.
            original=NPCState("npc:loaded-tree","Loaded",30,"farmer",[],p.x,p.y,0,"","",
                fx=.5,fy=.5,tasks=[{"kind":"move","x":p.x,"y":p.y+1,
                                   "_local_path":[[p.x,p.y+1]]}])
            saved=LivingWorldState();saved.npcs[original.uid]=original
            npc=LivingWorldState.from_dict(saved.to_dict()).npcs[original.uid]
            sim.state.npcs[npc.uid]=npc;sim.npcs.rebuild_spatial_index()
            sim.npcs.continuous_motion_enabled=True
            trace=[]
            for tick in range(20):
                update_npcs_free(sim,.1)
                trace.append((npc.x+npc.fx,npc.y+npc.fy))
                if not npc.tasks:break
                self.assertIn("_local_path",npc.tasks[0])
            self.assertLess(tick,19,"same-cell trunk must not create a replan loop")
            self.assertEqual((npc.x,npc.y),(p.x,p.y+1))
            self.assertFalse(npc.tasks)
            traces.append(trace)
            sim.state.npcs.pop(npc.uid);sim.npcs.rebuild_spatial_index()
        self.assertEqual(traces[0],traces[1])
        self.assertFalse(sim.state.resource_depletion)

    def test_pickup_and_forage_skip_progress_time_and_unclocked_world_ticks(self):
        sim=self.sim;p=self.origin;inv=sim.entities.get(sim.player_id,Inventory)
        start_minute=sim.clock.minute;start_turn=sim.turn
        vitals=asdict(sim.entities.get(sim.player_id,Vitals))
        sim.state.ground_piles[pos_key(p.x,p.y,p.z)]=GroundPile(p.x,p.y,p.z,{"core:stone":2})
        self.features[(p.x,p.y,p.z)]="core:nettle_patch"
        old_stone=inv.count("core:stone")
        sim._action_progress_callback=Mock(side_effect=AssertionError("instant pickup started a timer"))
        with patch.object(sim,"_advance_time",side_effect=AssertionError("instant pickup advanced time")), \
             patch.object(sim,"_post_action",side_effect=AssertionError("instant pickup ticked the world")):
            sim.execute(PickupCommand(sim.player_id))
            sim.execute(GatherCommand(sim.player_id))
            # The same-minute repeat cannot create a second harvest.
            carried=dict(inv.items)
            sim.execute(GatherCommand(sim.player_id))
            self.assertEqual(inv.items,carried)
        self.assertEqual(inv.count("core:stone"),old_stone+2)
        self.assertNotIn(pos_key(p.x,p.y,p.z),sim.state.ground_piles)
        self.assertEqual((sim.clock.minute,sim.turn),(start_minute,start_turn))
        self.assertEqual(asdict(sim.entities.get(sim.player_id,Vitals)),vitals)
        self.assertEqual(sim.state.resource_depletion[pos_key(p.x,p.y,p.z)],start_minute)
        sim._action_progress_callback.assert_not_called()

    def test_combat_pickup_still_commits_one_authoritative_exchange(self):
        sim=self.sim;p=self.origin
        sim.state.ground_piles[pos_key(p.x,p.y,p.z)]=GroundPile(p.x,p.y,p.z,{"core:stone":1})
        start_turn=sim.turn
        with patch.object(sim,"combat_active",return_value=True), \
             patch.object(sim,"_advance_time") as advance,patch.object(sim,"_post_action") as post:
            sim.execute(PickupCommand(sim.player_id))
        advance.assert_called_once_with(1)
        post.assert_called_once_with(allow_hostile_attacks=True)
        self.assertEqual(sim.turn,start_turn+1)


if __name__=="__main__":
    unittest.main()
