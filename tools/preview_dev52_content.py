"""Bounded Dev52 artwork and production-rendered fixture previews.

This is offline visual QA, not a live game playtest. Assets are presentation
only; deterministic settlement preparation precedes observational screenshots.
"""
from __future__ import annotations

import argparse
import math
import os
from pathlib import Path
import sys
import textwrap
from types import SimpleNamespace

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from PIL import Image, ImageDraw, ImageFont

from tests import test_dev50_interior_storage as fixtures
from worldseed.entities.components import Inventory, Vitals
from worldseed.entities.store import EntityStore
from worldseed.presentation.visuals import VisualRegistry
from worldseed.systems.building_variants import catalog as building_catalog
from worldseed.systems.interior_furnishing import furniture_variant_catalog
from worldseed.systems.interior_state import InteriorActor
from worldseed.systems.interior_state import InteriorPlan
from worldseed.systems.building_shells import BuildingShell
from worldseed.systems.state import pos_key
from worldseed.ui.exterior_view import draw_shells
from worldseed.systems.interiors import position_clear
from worldseed.ui.pygame_terminal import PygameTerminal


def asset_groups(visuals):
    buildings = [(row['name'], visuals.resolve(visuals.ref('building_shells', row['id'])))
                 for row in building_catalog()]
    furniture = [(row['name'], visuals.resolve(visuals.ref('interiors', row['id'])))
                 for row in furniture_variant_catalog()]
    materials = sorted({row[key] for row in building_catalog() for key in ('floor', 'wall')})
    tiles = [(uid.split(':', 1)[-1].replace('_', ' ').title(),
              visuals.resolve(visuals.ref('interior_textures', uid))) for uid in materials]
    assert (len(buildings), len(furniture), len(tiles)) == (30, 20, 10)
    return buildings, furniture, tiles


def contact_sheet(rows, path, columns=6):
    width, height, heading = 232, 210, 30
    image = Image.new('RGB', (columns * width, math.ceil(len(rows) / columns) * height + heading), (17, 24, 25))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=15)
    draw.text((10, 7), path.stem.replace('-', ' ').upper(), fill=(229, 186, 89), font=font)
    for index, (name, source_path) in enumerate(rows):
        x, y = index % columns * width, heading + index // columns * height
        for ty in range(y + 3, y + 170, 16):
            for tx in range(x + 4, x + width - 4, 16):
                shade = (43, 50, 50) if ((tx - x) // 16 + (ty - y) // 16) % 2 else (33, 40, 41)
                draw.rectangle((tx, ty, min(tx + 15, x + width - 5), min(ty + 15, y + 169)), fill=shade)
        if source_path is None or not source_path.is_file():
            raise FileNotFoundError(str(source_path) + ': ' + name)
        with Image.open(source_path) as source:
            source = source.convert('RGBA')
            bounds = source.getchannel('A').getbbox()
            if bounds:
                source = source.crop(bounds)
            source.thumbnail((width - 22, 158), Image.Resampling.LANCZOS)
            image.paste(source, (x + (width - source.width) // 2, y + 7 + (158 - source.height) // 2), source)
        for line, label in enumerate(textwrap.wrap(name, width=26)[:2]):
            draw.text((x + 7, y + 177 + line * 16), label, fill=(222, 222, 208), font=font)
    image.save(path)
    print(path)


def production_interiors(output_dir):
    fixtures.InteriorStorageTests.setUpClass()
    sim, town, _ = fixtures.InteriorStorageTests().fixture()
    sim.clock = SimpleNamespace(label=lambda: 'Y1 Spring 4, 12:00', minute=720)
    sim.introduced_npc_ids = lambda: set()
    sim.log = []
    entities = EntityStore(); pid = entities.spawn(preferred_id=1)
    entities.add(pid, Inventory()); entities.add(pid, Vitals())
    term = PygameTerminal(1280, 832)
    term.enter(); term._tile_px = 32
    try:
        structures = sim.settlement_physicalization.skeleton_for(town.uid).structures
        for function in ('residence', 'inn', 'market', 'smithy', 'workshop'):
            structure = next((s for s in structures if s.function == function), None)
            if structure is None:
                print(function + ': not present in the deterministic fixture; no building was invented')
                continue
            plan = sim.interiors.prepare_workplace(structure.uid)
            floors = sorted((floor for floor in sim.state.interiors.values() if floor.building_id == structure.uid),
                            key=lambda floor: floor.floor_index)
            for floor in floors:
                # QA overview zoom only: large workshop plans should fit in a
                # single screenshot without changing the game's camera rules.
                term._tile_px = max(16, min(32, int(min(820000 / floor.width, 530000 / floor.height))))
                candidates = [(floor.width // 2 + dx, floor.height // 2 + dy)
                              for dy in (0, 1000, -1000, 2000) for dx in (0, 1000, -1000)]
                x, y = next((point for point in candidates if position_clear(floor, *point)),
                            (floor.entry_x, floor.entry_y))
                sim.interiors._remove_actor('player')
                sim.interiors._put_actor('player', InteriorActor(floor.uid, x, y))
                before = sim.state.to_dict()
                term.present_game(sim.registry, object(), entities, sim, pid)
                assert sim.state.to_dict() == before, 'Rendering changed authoritative state'
                output = output_dir / f'{function}-floor-{floor.floor_index + 1}.png'
                term.pg.image.save(term.screen, str(output))
                print(f'{output}: {floor.variant_id}, {len(floor.rooms)} rooms, {len(floor.furniture)} fittings')
    finally:
        term.restore()


def production_exteriors(output_dir):
    """Door overlays rendered at their measured threshold; cyan is a QA guide."""
    term = PygameTerminal(1440, 1200)
    term.enter()
    try:
        pg = term.pg
        term.screen.fill((38, 43, 39))
        term.screen.blit(term.font.render('DEV52 - real facade doors; cyan marks physical threshold', True,
                                         (227, 193, 110)), (15, 10))
        footprint = tuple((x, y) for y in range(6) for x in range(6))
        known = {pos_key(x, y, 0) for x, y in footprint}
        for index, variant in enumerate(building_catalog()):
            x, y = index % 6 * 240, 55 + index // 6 * 225
            used = pg.Rect(x + 16, y + 3, 208, 180)
            shell = BuildingShell('preview:' + variant['asset'], 'qa', variant['function'], 'core:house',
                                  footprint, (3, 5), 'door:qa', 0, 'rectangle', (0, 0, 5, 5))
            plan = InteriorPlan('interior:' + shell.uid, shell.uid, shell.door_uid, 3, 5, 0,
                                12000, 12000, variant_id=variant['id'])
            before = plan.to_dict()
            hits = []
            draw_shells(term, (shell,), used, -1, -1, 22, known, known, hit_regions=hits,
                        interior_plans={plan.uid: plan})
            assert plan.to_dict() == before, 'Exterior rendering changed state'
            door = next(row for row in hits if row['kind'] == 'door')
            px, py = door['rect'].midbottom
            pg.draw.line(term.screen, (83, 200, 193), (px - 4, py + 3), (px + 4, py + 3), 2)
            label = term.small_font.render(variant['name'], True, (229, 218, 191))
            term.screen.blit(label, (x + 8, y + 186))
        output = output_dir / 'production-facade-doors-30.png'
        pg.image.save(term.screen, str(output))
        print(output)
    finally:
        term.restore()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--section', choices=('all', 'buildings', 'furniture', 'tiles', 'interiors', 'exteriors'),
                        action='append', help='Preview finished asset groups while other groups are being authored.')
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    sections = set(args.section or ('all',))
    groups = asset_groups(VisualRegistry.load_default())
    for section, name, rows in zip(('buildings', 'furniture', 'tiles'),
                                   ('buildings-30', 'furniture-20', 'interior-tiles-10'), groups):
        if 'all' in sections or section in sections:
            contact_sheet(rows, args.output_dir / (name + '.png'))
    if 'all' in sections:
        contact_sheet([row for group in groups for row in group], args.output_dir / 'all-dev52-assets-60.png')
    if 'all' in sections or 'interiors' in sections:
        production_interiors(args.output_dir)
    if 'all' in sections or 'exteriors' in sections:
        production_exteriors(args.output_dir)


if __name__ == '__main__':
    main()
