from __future__ import annotations
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import argparse,tempfile,time
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory,Position,Vitals
from worldseed.entities.store import EntityStore
from worldseed.persistence.database import WorldDatabase
from worldseed.sim.commands import WaitCommand
from worldseed.sim.engine import Simulation
from worldseed.systems.state import LivingWorldState
from worldseed.world.generator import WorldGenerator
from worldseed.world.world import World

def run(seed:bytes,days:int):
    reg=ContentRegistry.load(DATA_DIR)
    with tempfile.TemporaryDirectory() as td:
        db=WorldDatabase.create(Path(td)/'s.db','soak',seed.hex());world=World(WorldGenerator(seed,reg),reg,db);e=EntityStore();pid=e.spawn(preferred_id=1);e.add(pid,Position(WorldPos(0,0,0)));e.add(pid,Inventory());e.add(pid,Vitals());sim=Simulation(world,e,reg,0,LivingWorldState(),seed)
        start=time.perf_counter();sim.execute(WaitCommand(pid,days*1440));elapsed=time.perf_counter()-start
        errors=[]
        if any(c.count<0 for c in sim.state.cohorts.values()):errors.append('negative cohort')
        if any(s.population<0 for s in sim.state.settlements.values()):errors.append('negative settlement population')
        if any(n.wealth<0 for n in sim.state.npcs.values()):errors.append('negative NPC wealth')
        if any(v<0 for s in sim.state.settlements.values() for v in s.stocks.values()):errors.append('negative settlement stock')
        print({'days':days,'seconds':round(elapsed,3),'settlements':len(sim.state.settlements),'npcs':len(sim.state.npcs),'events':len(sim.state.history),'cohorts':len(sim.state.cohorts),'errors':errors})
        db.close();return errors
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--days',type=int,default=365);ap.add_argument('--seed',default='soak');a=ap.parse_args();raise SystemExit(bool(run(a.seed.encode(),a.days)))
