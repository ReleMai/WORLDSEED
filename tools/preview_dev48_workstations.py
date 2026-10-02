"""Bounded visual QA of six prepared interior profiles and original fixtures.

These are explicit test fixtures, not a claim that a generated village contains
every profession. The tool creates no economic stock and never changes runtime
generation or persisted gameplay interiors.
"""
import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.test_building_interior_profiles import BuildingInteriorProfileTests
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Vitals
from worldseed.entities.store import EntityStore
from worldseed.systems.interior_state import InteriorActor
from worldseed.systems.interiors import InteriorSystem, build_interior, position_clear
from worldseed.systems.state import LivingWorldState
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.world.regional_plan import StructurePiecePlan


STATIONS = (
    ("smithy", "core:forge_piece"),
    ("workshop", "core:carpenter_bench_piece"),
    ("mill", "core:millstone_piece"),
    ("bakery", "core:bakery_oven_piece"),
    ("weavery", "core:loom_piece"),
    ("brewery", "core:brewery_vat_piece"),
)


def main():
    registry = ContentRegistry.load(DATA_DIR)
    fixture = BuildingInteriorProfileTests()
    state = LivingWorldState()
    entities = EntityStore()
    player_id = entities.spawn(preferred_id=1)
    entities.add(player_id, Inventory())
    entities.add(player_id, Vitals())
    sim = SimpleNamespace(state=state, registry=registry, entities=entities, player_id=player_id,
                          player_pos=WorldPos(2, 5, 0), known_npc_ids=lambda: set(), log=[],
                          clock=SimpleNamespace(minute=720, label=lambda: "Prepared profile QA fixture"))
    sim.interiors = InteriorSystem(sim)
    output_dir = Path(__file__).resolve().parents[1] / "artifacts"
    output_dir.mkdir(parents=True, exist_ok=True)
    frames = []
    term = PygameTerminal(1280, 832)
    term.enter()
    try:
        for function, piece_id in STATIONS:
            uid = "building:dev48-qa:" + function
            structure = fixture.structure(function=function, uid=uid)
            original = StructurePiecePlan("fixture:dev48-qa:" + function, uid, piece_id, 1, 1, role="fixture")
            plan = build_interior(structure, fixture.door(uid), pieces=[original])
            assert [f.uid for f in plan.furniture] == [original.uid], "Source fixture identity changed"
            furnishing = plan.furniture[0]
            use_point = sim.interiors.fixture_use_position(plan, furnishing)
            assert use_point and position_clear(plan, *use_point), "Workstation has no usable standing position"
            # Stand beside, rather than directly in front of, the authored
            # station so the tall player sprite cannot hide its silhouette.
            centre = furnishing.x + furnishing.w // 2, furnishing.y + furnishing.h // 2
            candidates = [(centre[0] + dx, centre[1] + dy)
                          for dx, dy in ((1800, 1000), (-1800, 1000), (1800, -1000), (-1800, -1000))]
            point = next((p for p in candidates if position_clear(plan, *p)), use_point)
            state.interiors[plan.uid] = plan
            sim.interiors._remove_actor("player")
            sim.interiors._put_actor("player", InteriorActor(plan.uid, *point))
            path = term._visuals.resolve(term._visuals.ref("interiors", piece_id))
            assert path is not None, "Dedicated station art missing: " + piece_id
            before = state.to_dict()
            term._tile_px = 104
            term.present_game(registry, object(), entities, sim, player_id,
                              f"Prepared profile QA fixture • {function} • one original {piece_id}; no production or stocks")
            assert state.to_dict() == before, "Rendering mutated simulation state"
            assert any(token == "UI_STANCE:aggressive" for _, token in term._pointer_targets)
            ctx = term._interior_context
            centre = ctx["camera"].to_screen(furnishing.x + furnishing.w // 2, furnishing.y + furnishing.h // 2)
            assert ctx["used"].collidepoint(centre), "Station is outside QA viewport"
            output = output_dir / f"dev48-workstation-{function}.png"
            term.pg.image.save(term.screen, str(output))
            frames.append((function, term.screen.copy()))
            print(f"{output} ({plan.layout_id}, {len(plan.rooms)} rooms, dedicated sprite {path.name}; observational)")
        contact = term.pg.Surface((2560, 2616))
        contact.fill((13, 16, 18))
        for index, (function, frame) in enumerate(frames):
            x, y = (index % 2) * 1280, (index // 2) * 872
            label = function.title() + " — prepared profile QA fixture"
            contact.blit(term.title_font.render(label, True, term._theme["accent"]), (x + 18, y + 8))
            contact.blit(frame, (x, y + 40))
        output = output_dir / "dev48-workstation-contact.png"
        term.pg.image.save(contact, str(output))
        print(output)
    finally:
        term.restore()


if __name__ == "__main__":
    main()
