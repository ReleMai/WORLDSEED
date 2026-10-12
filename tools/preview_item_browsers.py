#!/usr/bin/env python3
"""Render realistic inventory/crafting browser fixtures without starting a world."""
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
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.ui.widgets import MenuRow


def inventory_fixture(registry):
    """Use real content/icons, including the catalogue's longest item names."""
    longest = sorted(registry.items.values(), key=lambda item: (-len(item.name), item.id))[:8]
    preferred = [registry.items[key] for key in (
        'core:wood', 'core:stone', 'core:bark', 'core:iron_ore', 'core:iron_ingot',
        'core:bread', 'core:apple', 'core:water', 'core:iron_pickaxe', 'core:iron_axe',
    ) if key in registry.items]
    unique = {}
    for item in longest + preferred + list(registry.items.values()):
        unique.setdefault(item.id, item)
        if len(unique) >= 120:
            break
    items = {}
    for index, item in enumerate(unique.values()):
        items[item.id] = {
            'name': item.name, 'count': 1 + (index * 7) % 28, 'category': item.category,
            'unit_mass_kg': item.mass_g / 1000, 'unit_volume_l': item.volume_ml / 1000,
            'description': item.description or 'A carried item, available for use, storage or crafting.',
            'detail_lines': ['Material: ' + (item.material or 'Mixed materials'),
                             'Quality: sound', 'Stored in: backpack',
                             'Ingredients and quantities remain authoritative in the simulation.'],
            'can_use': bool(item.nutrition or item.hydration),
            'use_label': 'Eat' if item.nutrition else 'Drink' if item.hydration else 'Use',
        }
    selected = next(iter(items))
    data = {
        'items': items, 'selected_item_id': selected, 'selected_key': selected,
        'total_mass_kg': sum(item['unit_mass_kg'] * item['count'] for item in items.values()),
        'total_volume_l': sum(item['unit_volume_l'] * item['count'] for item in items.values()),
        'stack_count': len(items), 'item_count': sum(item['count'] for item in items.values()),
        'active_filter': 'all', 'filter_categories': sorted({item['category'] for item in items.values()}),
        'action_amount': 1, 'near_storage': True,
    }
    return [MenuRow(key, value['name']) for key, value in items.items()], data


def crafting_fixture(registry):
    """Recipes expose actual output sprites, materials and long explanations."""
    candidates = sorted(registry.recipes.values(), key=lambda recipe: (-len(recipe.inputs), -len(recipe.name), recipe.id))[:36]
    recipes = {}
    for index, recipe in enumerate(candidates):
        def name(item_id):
            return registry.items[item_id].name if item_id in registry.items else item_id
        recipes[recipe.id] = {
            'name': recipe.name, 'minutes': recipe.minutes, 'skill': recipe.skill,
            'difficulty': recipe.difficulty, 'station': recipe.station,
            'description': recipe.description or 'Combine these materials at the required workplace. Produces the listed items using carried inventory.',
            'outputs': [{'id': key, 'name': name(key), 'qty': qty} for key, qty in recipe.outputs.items()],
            'inputs': [{'id': key, 'name': name(key), 'need': qty, 'have': qty if index % 3 else max(0, qty - 1)} for key, qty in recipe.inputs.items()],
            'ready': bool(index % 3), 'new': index % 5 == 0,
            'missing': [] if index % 3 else ['Additional carried materials are required.'],
        }
    selected = next(iter(recipes))
    categories = sorted({recipe.category for recipe in registry.recipes.values()})
    data = {'recipes': recipes, 'selected_key': selected, 'categories': categories,
            'category': registry.recipes[selected].category,
            'category_page': categories.index(registry.recipes[selected].category) // 6,
            'new_categories': categories[:2]}
    return [MenuRow(key, value['name']) for key, value in recipes.items()], data


def render_previews(output):
    registry = ContentRegistry.load(DATA_DIR)
    output.mkdir(parents=True, exist_ok=True)
    for label, panel_size in (('standard', (900, 620)), ('minimum', (640, 440))):
        # Crafting's supported minimum is wider/taller than the inventory.
        for presentation, fixture in (('inventory_unified', inventory_fixture), ('crafting_unified', crafting_fixture)):
            pw, ph = panel_size if presentation == 'inventory_unified' or label == 'standard' else (740, 500)
            term = PygameTerminal(pw + 32, ph + 32)
            term.enter()
            try:
                term.screen.fill((10, 17, 19))
                panel_id = 'crafting' if presentation == 'crafting_unified' else presentation
                term._floating_panels[panel_id] = {'x': 16, 'y': 16, 'w': pw, 'h': ph}
                rows, data = fixture(registry)
                capacity = term.menu_page_size(presentation)
                term.present_feature_menu(presentation, presentation, rows[:capacity], 0,
                                          total=len(rows), data=data)
                target = output / f'{presentation.removesuffix("_unified")}-{label}.png'
                term.pg.image.save(term.screen, str(target))
                print(target)
            finally:
                term.restore()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('artifacts/ui-browser-preview'))
    render_previews(parser.parse_args().output)
