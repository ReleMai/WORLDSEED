from __future__ import annotations
from pathlib import Path
import sys,time,tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from worldseed.config import DATA_DIR
from worldseed.app import _find_spawn
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory,Position,Vitals
from worldseed.entities.store import EntityStore
from worldseed.persistence.database import WorldDatabase
from worldseed.sim.commands import MoveCommand
from worldseed.sim.engine import Simulation
from worldseed.systems.state import LivingWorldState
from worldseed.ui.renderer import Renderer
from worldseed.world.generator import WorldGenerator
from worldseed.world.world import World


def main():
    seed=b'movement-benchmark';reg=ContentRegistry.load(DATA_DIR)
    with tempfile.TemporaryDirectory() as td:
        db=WorldDatabase.create(Path(td)/'bench.db','bench',seed.hex());world=World(WorldGenerator(seed,reg),reg,db)
        e=EntityStore();pid=e.spawn(preferred_id=1);e.add(pid,Position(WorldPos(0,0,0)));e.add(pid,Inventory({'core:cooked_meat':20}));e.add(pid,Vitals())
        sim=Simulation(world,e,reg,0,LivingWorldState(),seed);renderer=Renderer(reg,use_color=False)
        center=_find_spawn(world,'wanderer',sim.resources)
        pair=None
        for radius in range(0,41):
            for y in range(center.y-radius,center.y+radius+1):
                for x in range(center.x-radius,center.x+radius+1):
                    if radius and max(abs(x-center.x),abs(y-center.y))!=radius:continue
                    a=WorldPos(x,y,0);b=WorldPos(x+1,y,0)
                    if world.is_passable(a) and world.is_passable(b) and not sim.resources.blocks_movement(a) and not sim.resources.blocks_movement(b):pair=(a,b);break
                if pair:break
            if pair:break
        if not pair:raise SystemExit('no passable benchmark pair')
        e.get(pid,Position).value=pair[0];sim._discover(pair[0]);renderer.render(world,e,sim,pid,100,30)
        # warm caches / nearby state
        for _ in range(10):sim.execute(MoveCommand(pid,1,0));sim.execute(MoveCommand(pid,-1,0))
        n=400;start=time.perf_counter()
        for _ in range(n//2):sim.execute(MoveCommand(pid,1,0));sim.execute(MoveCommand(pid,-1,0))
        move_s=time.perf_counter()-start
        start=time.perf_counter()
        for _ in range(n//2):
            sim.execute(MoveCommand(pid,1,0));renderer.render(world,e,sim,pid,100,30)
            sim.execute(MoveCommand(pid,-1,0));renderer.render(world,e,sim,pid,100,30)
        render_s=time.perf_counter()-start
        print({'steps':n,'move_ms':round(move_s*1000/n,3),'move_plus_render_ms':round(render_s*1000/n,3),'camera':renderer._camera})
        db.close()

if __name__=='__main__':main()
