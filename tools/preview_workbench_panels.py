#!/usr/bin/env python3
"""Render discovery/workshop empty and populated fixtures without advancing a world."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import sys

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.systems.workshops import WORKSHOP_PROFILES, profile_dict, recipes_for_station
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.ui.widgets import MenuRow
from tools.preview_item_browsers import crafting_fixture, inventory_fixture


def recipe_record(registry, recipe, ready=True):
    return {'id': recipe.id, 'name': recipe.name, 'minutes': recipe.minutes, 'skill': recipe.skill,
            'difficulty': recipe.difficulty, 'station': recipe.station, 'description': recipe.description,
            'outputs': [{'id': key, 'name': registry.items[key].name, 'qty': qty} for key, qty in recipe.outputs.items()],
            'inputs': [{'id': key, 'name': registry.items[key].name, 'need': qty, 'have': qty if ready else 0}
                       for key, qty in recipe.inputs.items()],
            'ready': ready, 'missing': [] if ready else ['Additional carried materials are required.']}


def discovery_fixture(registry):
    rows, inventory = inventory_fixture(registry)
    entries = {row.key: dict(inventory['items'][row.key], pool_count=8, known_recipes=['Plant cordage'],
                            tags=list(registry.items[row.key].tags)) for row in rows}
    _, crafting = crafting_fixture(registry)
    history = [dict(recipe, id=key) for key, recipe in crafting['recipes'].items()]
    latest = recipe_record(registry, registry.recipes['core:plant_cordage'])
    history.insert(0, latest)
    placed = ('core:brush', 'core:brush')
    if 'core:brush' in registry.items:
        brush = registry.items['core:brush']
        entries[brush.id] = {'name': brush.name, 'count': 8, 'pool_count': 8,
                             'known_recipes': [latest['name']], 'tags': list(brush.tags)}
        rows = [MenuRow(brush.id, brush.name)] + [row for row in rows if row.key != brush.id]
    return rows, {'items': entries, 'selected_items': placed, 'mix_state': 'green', 'known_exact': [],
                  'latest_result': latest, 'learned_history': history, 'learned_count': len(history)}


def workshop_fixture(registry):
    profiles = [profile_dict(profile) for profile in WORKSHOP_PROFILES.values()]
    profile = profiles[0]
    profiles[0]['short_title'] = 'Blacksmith'
    recipes = {recipe.id: recipe_record(registry, recipe, index % 3 != 0)
               for index, recipe in enumerate(recipes_for_station(registry, profile['station_id']))}
    rows = [MenuRow(key, recipe['name']) for key, recipe in recipes.items()]
    first_ready = next((row.key for row in rows if recipes[row.key]['ready']), rows[0].key)
    return rows, {'recipes': recipes, 'known_count': len(rows), 'locked_count': 0,
                  'profile': profile, 'station_id': profile['station_id'], 'station_page': 0,
                  'stations': profiles, 'selected_key': first_ready}


def render_previews(output):
    registry = ContentRegistry.load(DATA_DIR)
    output.mkdir(parents=True, exist_ok=True)
    for label, (width, height) in (('minimum', (740, 500)), ('standard', (900, 620))):
        for presentation, fixture in (('discovery_pot', discovery_fixture), ('workshop_station', workshop_fixture)):
            for state in ('empty', 'populated'):
                term = PygameTerminal(width + 32, height + 32)
                term.enter()
                try:
                    term.screen.fill((10, 17, 19))
                    term._floating_panels['crafting'] = {'x': 16, 'y': 16, 'w': width, 'h': height}
                    rows, data = fixture(registry) if state == 'populated' else ([], {})
                    capacity = term.menu_page_size(presentation)
                    term.present_feature_menu(presentation, presentation, rows[:capacity], 0, total=len(rows), data=data)
                    target = output / f'{presentation}-{state}-{label}.png'
                    term.pg.image.save(term.screen, str(target))
                    print(target)
                finally:
                    term.restore()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('artifacts/workbench-preview'))
    render_previews(parser.parse_args().output)
