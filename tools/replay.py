from __future__ import annotations
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import argparse,json,tempfile
from dataclasses import asdict
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.canonical import canonical_hash
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory,Position,Vitals
from worldseed.entities.store import EntityStore
from worldseed.persistence.database import WorldDatabase
from worldseed.sim.commands import MoveCommand,GatherCommand,WaitCommand
from worldseed.sim.engine import Simulation
from worldseed.systems.state import LivingWorldState
from worldseed.world.generator import WorldGenerator
from worldseed.world.world import World

def run(seed_text:str,commands:list[list])->str:
    reg=ContentRegistry.load(DATA_DIR);seed=seed_text.encode();seed_hex=seed.hex()
    with tempfile.TemporaryDirectory() as td:
        db=WorldDatabase.create(Path(td)/'r.db','replay',seed_hex);world=World(WorldGenerator(seed,reg),reg,db);e=EntityStore();pid=e.spawn(preferred_id=1);e.add(pid,Position(WorldPos(0,0,0)));e.add(pid,Inventory());e.add(pid,Vitals());sim=Simulation(world,e,reg,0,LivingWorldState(),seed)
        for row in commands:
            if row[0]=='move':sim.execute(MoveCommand(pid,int(row[1]),int(row[2])))
            elif row[0]=='gather':sim.execute(GatherCommand(pid))
            elif row[0]=='wait':sim.execute(WaitCommand(pid,int(row[1]) if len(row)>1 else 10))
        payload={'turn':sim.turn,'pos':asdict(e.get(pid,Position).value),'inventory':e.get(pid,Inventory).items,'vitals':asdict(e.get(pid,Vitals)),'state':sim.state.to_dict(),'deltas':{f'{p.x},{p.y},{p.z}':v for p,v in world.dirty_tiles.items()}}
        db.close();return canonical_hash(payload)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('fixture');args=ap.parse_args();raw=json.loads(Path(args.fixture).read_text());print(run(raw['seed'],raw['commands']))
if __name__=='__main__':main()
