"""Headless QA using an authoritative generated household and its real portal."""
import os
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.test_property_storage_casing import PropertyStorageCasingTests
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Vitals
from worldseed.entities.store import EntityStore
from worldseed.systems.interiors import InteriorSystem, position_clear
from worldseed.ui.pygame_terminal import PygameTerminal


def main():
    PropertyStorageCasingTests.setUpClass()
    fixture = PropertyStorageCasingTests()
    base, security = fixture._security_fixture()
    state, town, physical, *_ = base
    npc = next(n for n in state.npcs.values() if n.home_id and any(d.role == 'entrance' for d in security.doors_for_property(n.home_id)))
    door = next(d for d in security.doors_for_property(npc.home_id) if d.role == 'entrance')
    # The QA household has admitted the visitor. Its generated ownership,
    # portal identity, rooms, furniture and economic state stay authoritative.
    door.locked = False
    entities = EntityStore()
    player_id = entities.spawn(preferred_id=1)
    entities.add(player_id, Inventory())
    entities.add(player_id, Vitals())
    sim = SimpleNamespace(state=state, registry=fixture.registry,
                          player_pos=WorldPos(door.x, door.y, door.z),
                          player_id=player_id, entities=entities,
                          settlement_physicalization=physical, property_security=security,
                          clock=SimpleNamespace(minute=1320, label=lambda: 'Y1 Spring 2, 22:00'),
                          known_npc_ids=lambda: {npc.uid}, log=[])
    sim.interiors = InteriorSystem(sim)
    result = sim.interiors.enter(door.uid)
    plan = sim.interiors.current_plan()
    assert plan is not None, result
    npc.x, npc.y, npc.z = door.x, door.y, door.z
    assert sim.interiors.enter_npc(npc, door.uid)
    player = sim.interiors.player_presence()
    resident = state.interior_actors[npc.uid]
    room = plan.rooms[1]
    candidates = [(room.rect.x + 1400 + dx, room.rect.y + room.rect.h // 2 + dy)
                  for dy in (0, 500, -500) for dx in (0, 400, 800)]
    x, y = next((x, y) for x, y in candidates if position_clear(plan, x, y))
    player.x, player.y = x, y
    x, y = next((x, y) for x, y in reversed(candidates) if position_clear(plan, x, y))
    resident.x, resident.y, resident.action = x, y, 'checking_home'
    before = state.to_dict()
    term = PygameTerminal(1440, 1000)
    term.enter()
    term._tile_px = 56
    output = Path('artifacts/dev46-interior-preview.png')
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        term.present_game(fixture.registry, object(), entities, sim, player_id,
                          'Free interior movement • independent rooms • furniture placed between outdoor tile coordinates')
        assert state.to_dict() == before, 'Rendering mutated simulation state'
        term.pg.image.save(term.screen, str(output))
        print(f'{output.resolve()}\nBuilding {plan.building_id}; {len(plan.rooms)} rooms, {len(plan.furniture)} original fixtures; observational render passed')
    finally:
        term.restore()


if __name__ == '__main__':
    main()
