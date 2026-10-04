"""Production-rendered indoor QA from a deterministic settlement test fixture.

Not a live playtest. Preparation is explicit; each rendered frame must be
observational. Output is external and never used as simulation authority.
"""
import argparse
import os
from pathlib import Path
import sys
from types import SimpleNamespace

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from tests import test_dev50_interior_storage as fixtures
from worldseed.entities.components import Inventory, Vitals
from worldseed.entities.store import EntityStore
from worldseed.systems.interior_state import InteriorActor
from worldseed.systems.interiors import position_clear
from worldseed.ui.pygame_terminal import PygameTerminal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    fixtures.InteriorStorageTests.setUpClass()
    sim, town, _ = fixtures.InteriorStorageTests().fixture()
    sim.clock = SimpleNamespace(label=lambda: 'Y1 Spring 4, 12:00', minute=720)
    sim.introduced_npc_ids = lambda: set()
    sim.log = []
    entities = EntityStore()
    pid = entities.spawn(preferred_id=1)
    entities.add(pid, Inventory())
    entities.add(pid, Vitals())
    term = PygameTerminal(1280, 832)
    term.enter()
    term._tile_px = 32
    try:
        structures = sim.settlement_physicalization.skeleton_for(town.uid).structures
        for function in ('residence', 'inn', 'market'):
            structure = next(s for s in structures if s.function == function)
            plan = sim.interiors.prepare_workplace(structure.uid)
            floors = [plan] + [f for f in sim.state.interiors.values()
                               if f.building_id == structure.uid and f.floor_index]
            for floor in sorted(floors, key=lambda p: p.floor_index):
                positions = [(floor.width // 2 + dx, floor.height // 2 + dy)
                             for dy in (0, 1000, -1000, 2000) for dx in (0, 1000, -1000)]
                x, y = next((p for p in positions if position_clear(floor, *p)), (floor.entry_x, floor.entry_y))
                sim.interiors._remove_actor('player')
                sim.interiors._put_actor('player', InteriorActor(floor.uid, x, y))
                before = sim.state.to_dict()
                term.present_game(sim.registry, object(), entities, sim, pid)
                assert sim.state.to_dict() == before, 'Rendering changed authoritative state'
                output = args.output_dir / f'{function}-floor-{floor.floor_index + 1}.png'
                term.pg.image.save(term.screen, str(output))
                print(f'{output}: {len(floor.rooms)} rooms, {len(floor.furniture)} fittings, {len(floor.stairs)} stairs')
    finally:
        term.restore()


if __name__ == '__main__':
    main()
