from __future__ import annotations
from pathlib import Path
import json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from worldseed.persistence.database import WorldDatabase
from worldseed.systems.state import LivingWorldState

def main():
    if len(sys.argv)!=2:print('Usage: python tools/world_inspector.py saves/world.db');return 2
    db=WorldDatabase.open(Path(sys.argv[1]))
    try:
        state=LivingWorldState.from_dict(db.load_sim_state());print(f"World: {db.get_meta('world_name')}");print(f"Engine: {db.get_meta('engine_version')} schema={db.get_meta('save_schema')} worldgen={db.get_meta('worldgen_version')}");print(f"Turn: {db.get_meta('turn')} clock_minute={state.clock_minute}")
        print(f"Settlements: {len(state.settlements)}  NPCs: {len(state.npcs)}  Cohorts: {len(state.cohorts)}  Creatures: {len(state.creatures)}")
        print(f"History: {len(state.history)}  Artifacts: {len(state.artifacts)}  Books: {len(state.books)}  Caravans: {len(state.caravans)}")
        print(f"Structures: {len(state.structures)}  Crops: {len(state.crops)}  Fires: {len(state.fires)}  Fluids: {len(state.fluids)}")
        if state.history:
            print('\nRecent history:')
            for e in state.history[-15:]:print(f" {e.minute:>10} [{e.event_type}] {e.summary}")
        return 0
    finally:db.close()
if __name__=='__main__':raise SystemExit(main())
