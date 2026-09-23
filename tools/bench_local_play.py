"""Temporary-world startup, movement and 2560x1392 SDL rendering benchmark.

--baseline-landforms REF loads only that Git revision's geological sampler for
an apples-to-apples cache comparison; --coast-version pins identical geography.
No player saves are opened. Timings are hardware-dependent, not release gates.
"""
import argparse,json,os,sys,tempfile,time,subprocess,types
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('SDL_VIDEODRIVER','dummy');os.environ.setdefault('SDL_AUDIODRIVER','dummy')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--baseline-landforms');parser.add_argument('--coast-version',type=int,default=2)
    args=parser.parse_args()
    if args.baseline_landforms:
        import worldseed.world.landforms as landforms
        source=subprocess.check_output(['git','show',args.baseline_landforms+':worldseed/world/landforms.py'],text=True)
        module=types.ModuleType('landforms_benchmark_baseline');sys.modules[module.__name__]=module
        exec(compile(source,'landforms_benchmark_baseline.py','exec'),module.__dict__)
        landforms.LandformSampler=module.LandformSampler
    from worldseed.config import DATA_DIR
    from worldseed.content.registry import ContentRegistry
    from worldseed.core.coords import WorldPos
    from worldseed.entities.components import Inventory,Position,Vitals
    from worldseed.entities.store import EntityStore
    from worldseed.persistence.database import WorldDatabase
    from worldseed.sim.engine import Simulation
    from worldseed.sim.commands import MoveCommand
    from worldseed.systems.state import LivingWorldState
    from worldseed.world.generator import WorldGenerator
    from worldseed.world.world import World
    from worldseed.ui.pygame_terminal import PygameTerminal
    reg=ContentRegistry.load(DATA_DIR);seed=b'pygame-dev4'
    with tempfile.TemporaryDirectory() as td:
        db=WorldDatabase.create(Path(td)/'bench.db','bench',seed.hex());term=None
        try:
            db.set_meta('coast_morphology_version',args.coast_version)
            world=World(WorldGenerator(seed,reg),reg,db)
            entities=EntityStore();pid=entities.spawn(preferred_id=1);pos=WorldPos(0,0,0)
            entities.add(pid,Position(pos));entities.add(pid,Inventory());entities.add(pid,Vitals())
            start=time.perf_counter();sim=Simulation(world,entities,reg,0,LivingWorldState(),seed)
            startup=time.perf_counter()-start
            term=PygameTerminal();term.enter();term._resize(2560,1392)
            term.present_game(reg,world,entities,sim,pid)
            start=time.perf_counter()
            for _ in range(30):term.present_game(reg,world,entities,sim,pid)
            render=(time.perf_counter()-start)*1000/30
            pair=None
            for y in range(6):
                for x in range(6):
                    a=WorldPos(x,y,0);b=a.moved(1,0)
                    if all(world.is_passable(p) and not sim.resources.blocks_movement(p) for p in (a,b)):
                        pair=(a,b);break
                if pair:break
            move=None
            if pair:
                entities.get(pid,Position).value=pair[0];sim._discover(pair[0])
                start=time.perf_counter()
                for _ in range(20):sim.execute(MoveCommand(pid,1,0));sim.execute(MoveCommand(pid,-1,0))
                move=(time.perf_counter()-start)*1000/40
            print(json.dumps({'startup_seconds':round(startup,3),'warm_frame_ms':round(render,3),
                              'movement_ms':round(move,3) if move is not None else None,
                              'coast_version':args.coast_version,'baseline_landforms':args.baseline_landforms}))
        finally:
            if term:term.restore()
            db.close()

if __name__=='__main__':main()
