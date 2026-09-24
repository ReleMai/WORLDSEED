import os
os.environ.setdefault("SDL_VIDEODRIVER","dummy")
os.environ.setdefault("SDL_AUDIODRIVER","dummy")

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Position, Vitals
from worldseed.entities.store import EntityStore
from worldseed.persistence.database import WorldDatabase
from worldseed.sim.engine import Simulation
from worldseed.systems.ai import NPCSystem
from worldseed.systems.building import BuildingSystem
from worldseed.systems.physicalization import SettlementPhysicalizationSystem
from worldseed.systems.settlement_planner import SettlementSkeletonPlanner
from worldseed.systems.state import LivingWorldState, NPCState, SettlementState
from worldseed.systems.stealth import StealthSystem
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.world.generator import WorldGenerator
from worldseed.world.region_blocks import RegionBlockPlan, RegionRoadExit
from worldseed.world.world import World


class MemoryCache:
    def __init__(self):
        self.rows={}
    def load_generated_settlement_plan(self,*args):
        return self.rows.get(tuple(args))
    def store_generated_settlement_plan(self,*args):
        self.rows[(args[0],args[1])]=args[2]
    def commit_generated(self):
        pass


class OpenResources:
    def blocks_sight(self,pos):
        return False


class ClearEnvironment:
    def visual_conditions(self,minute,pos):
        return ({"visibility":8,"fog":0},SimpleNamespace(ambient_light=65535))


class NullHistory:
    def record(self,*args,**kwargs):
        pass


class BuildingStealthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry=ContentRegistry.load(DATA_DIR)

    def _physical_fixture(self):
        env=SimpleNamespace(
            open_water=False,slope=3,flood_risk=2,wetness=40,
            soil_fertility=78,farmland=82,
            resources=SimpleNamespace(stone=70,timber=70,freshwater=65),
            resource_opportunity=72,
        )
        ground=SimpleNamespace(terrain=SimpleNamespace(blocks_sight=False))
        world=SimpleNamespace(
            generator=SimpleNamespace(world_seed=b"stealth-building"),
            delta_source=MemoryCache(),registry=self.registry,
            environment_at=lambda pos:env,
            tile_at=lambda pos:ground,
        )
        region=RegionBlockPlan(
            uid="stealth-region",region_x=0,region_y=0,version=1,
            dominant_biome="grassland",biome_mix={"grassland":20},
            mean_elevation=1,mean_moisture=1,mean_temperature=1,relief=1,
            settlement_present=True,settlement_anchor=(180,180),settlement_score=90,
            settlement_archetype="river_market",control_potential="settled",
            roads=(
                RegionRoadExit("north",180,"road"),
                RegionRoadExit("east",180,"road"),
                RegionRoadExit("south",180,"road"),
                RegionRoadExit("west",180,"road"),
            ),
        )
        planner=SettlementSkeletonPlanner(world)
        region_planner=SimpleNamespace(plan=lambda rx,ry,persist=True:region)
        physical=SettlementPhysicalizationSystem(world,self.registry,region_planner,planner)
        town=SettlementState(
            uid="settlement:stealth",name="Sightford",region_x=0,region_y=0,
            x=180,y=180,population=90,culture_id="culture:test",
            religion_id="religion:test",faction_id="faction:test",
        )
        state=LivingWorldState();state.settlements[town.uid]=town
        physical.sync([town],(0,0),radius=0)
        building=BuildingSystem(state,self.registry)
        building.attach_settlement_physicalization(physical)
        stealth=StealthSystem(
            state,b"stealth-building",world,OpenResources(),building,physical,ClearEnvironment()
        )
        return state,town,physical,stealth

    def test_generated_building_wall_clips_visual_cone(self):
        state,town,physical,stealth=self._physical_fixture()
        skeleton=physical.skeleton_for(town.uid)
        structure=next(s for s in skeleton.structures if s.enclosed and s.room_ids)
        room_cells=set()
        for room in skeleton.rooms:
            if room.structure_plan_id==structure.uid:
                room_cells.update(room.cells)
        footprint=set(structure.footprint)
        wall_cells=[
            (p.x,p.y) for p in skeleton.pieces
            if p.structure_plan_id==structure.uid and p.role=="wall"
        ]
        chosen=None
        for wx,wy in wall_cells:
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                inside=(wx+dx,wy+dy);outside=(wx-dx,wy-dy)
                if inside in room_cells and outside not in footprint:
                    chosen=((wx,wy),inside,outside,(dx,dy));break
            if chosen:break
        self.assertIsNotNone(chosen,"expected a shell wall with interior and exterior neighbors")
        wall,inside,outside,facing=chosen
        npc=NPCState(
            uid="npc:watcher",name="Watcher",age=30,occupation="guard",traits=[],
            x=outside[0],y=outside[1],z=0,settlement_id=town.uid,faction_id=town.faction_id,
            facing_dx=facing[0],facing_dy=facing[1],
        )
        state.npcs[npc.uid]=npc
        self.assertTrue(stealth.building.blocks_sight(WorldPos(wall[0],wall[1],0)))
        self.assertFalse(stealth.can_see(npc,WorldPos(inside[0],inside[1],0),600))
        snap=stealth.snapshot(WorldPos(inside[0],inside[1],0),600,active=True)
        self.assertNotIn(npc.uid,snap["seen_by"])
        watched={(c["x"],c["y"]) for c in snap["cells"] if npc.uid in c["observer_uids"]}
        self.assertNotIn(inside,watched)

    def test_facing_cone_controls_witnesses_and_stealth_reduces_noise(self):
        state=LivingWorldState()
        state.player_skills["stealth"]=6
        ground=SimpleNamespace(terrain=SimpleNamespace(blocks_sight=False))
        world=SimpleNamespace(tile_at=lambda pos:ground)
        physical=SimpleNamespace(
            clears_natural_feature=lambda pos:False,
            cell_at=lambda pos:None,
        )
        building=SimpleNamespace(blocks_sight=lambda pos:False)
        system=StealthSystem(
            state,b"cone-test",world,OpenResources(),building,physical,ClearEnvironment()
        )
        front=NPCState(
            uid="front",name="Front",age=30,occupation="guard",traits=[],
            x=0,y=-4,z=0,settlement_id="town",faction_id="f",
            facing_dx=0,facing_dy=1,
        )
        away=NPCState(
            uid="away",name="Away",age=30,occupation="guard",traits=[],
            x=2,y=0,z=0,settlement_id="town",faction_id="f",
            facing_dx=1,facing_dy=0,
        )
        state.npcs={front.uid:front,away.uid:away}
        player=WorldPos(0,0,0)
        self.assertTrue(system.can_see(front,player,600))
        self.assertFalse(system.can_see(away,player,600))
        self.assertEqual(system.witnesses(player,600,"town"),("front",))
        self.assertLess(system.movement_noise(20),20)

    def test_npc_facing_follows_actual_movement(self):
        npc=NPCState(
            uid="npc:mover",name="Mover",age=25,occupation="merchant",traits=[],
            x=4,y=4,z=0,settlement_id="town",faction_id="f",
        )
        npc.x=3;npc.y=5
        NPCSystem._face_step(npc,4,4)
        self.assertEqual((npc.facing_dx,npc.facing_dy),(-1,1))

    def test_stealth_state_roundtrips(self):
        state=LivingWorldState()
        state.player_stealth_mode=True
        state.player_skills["stealth"]=4
        npc=NPCState(
            uid="npc:a",name="A",age=20,occupation="guard",traits=[],
            x=0,y=0,z=0,settlement_id="town",faction_id="f",
            facing_dx=-1,facing_dy=0,
        )
        state.npcs[npc.uid]=npc
        restored=LivingWorldState.from_dict(state.to_dict())
        self.assertTrue(restored.player_stealth_mode)
        self.assertEqual(restored.player_skills["stealth"],4)
        self.assertEqual((restored.npcs[npc.uid].facing_dx,restored.npcs[npc.uid].facing_dy),(-1,0))


@unittest.skipUnless(PygameTerminal.available(),"pygame optional")
class StealthConeRenderTests(unittest.TestCase):
    def test_visual_cone_overlay_changes_world_view_without_mutating_simulation(self):
        reg=ContentRegistry.load(DATA_DIR);seed=b"stealth-render"
        with tempfile.TemporaryDirectory() as td:
            db=WorldDatabase.create(Path(td)/"stealth.db","stealth",seed.hex())
            world=World(WorldGenerator(seed,reg),reg,db)
            entities=EntityStore();pid=entities.spawn(preferred_id=1)
            pos=WorldPos(0,0,0)
            entities.add(pid,Position(pos));entities.add(pid,Inventory());entities.add(pid,Vitals())
            state=LivingWorldState();state.player_stealth_mode=True
            sim=Simulation(world,entities,reg,0,state,seed)
            before=sim.state.to_dict()
            overlay={
                "active":True,
                "cells":(
                    {"x":0,"y":-1,"z":0,"observer_uids":("npc:watch",),"alert":True},
                    {"x":0,"y":0,"z":0,"observer_uids":("npc:watch",),"alert":True},
                ),
                "observers":(
                    {"uid":"npc:watch","x":0,"y":-2,"z":0,"facing_dx":0,"facing_dy":1,"range":8,"sees_player":True},
                ),
                "seen_by":("npc:watch",),"structure_id":"","room_id":"",
            }
            sim.state.npcs["npc:watch"]=NPCState(
                uid="npc:watch",name="Watcher",age=30,occupation="guard",traits=[],
                x=0,y=-2,z=0,settlement_id="",faction_id="",facing_dx=0,facing_dy=1,
            )
            term=PygameTerminal();term.enter()
            try:
                term._resize(800,520)
                term.present_game(reg,world,entities,sim,pid,stealth_overlay=None)
                baseline=term.pg.image.tobytes(term.screen,"RGB")
                term.present_game(reg,world,entities,sim,pid,stealth_overlay=overlay)
                shown=term.pg.image.tobytes(term.screen,"RGB")
                self.assertNotEqual(baseline,shown)
                self.assertIn((0,-1,0),term._hover_context["stealth_by"])
                self.assertEqual(sim.state.to_dict(),before | {"npcs":sim.state.to_dict()["npcs"]})
            finally:
                term.restore();db.close()


if __name__=="__main__":
    unittest.main()
