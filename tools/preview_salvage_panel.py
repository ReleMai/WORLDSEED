#!/usr/bin/env python3
"""Preview populated, active, completed and empty consolidated salvage panels."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from types import SimpleNamespace

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.entities.components import Inventory
from worldseed.systems.crafting import CraftingSystem
from worldseed.systems.salvaging import SalvagingSystem
from worldseed.systems.state import LivingWorldState
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.ui.salvage_panel import salvage_panel_data
from worldseed.ui.widgets import MenuRow


def fixture(registry, mode):
    state = LivingWorldState(player_crafting_discovery_enabled=True)
    sources = list(registry.salvage)[:36]
    inv = Inventory({iid: 3 for iid in sources} if mode != 'empty' else {})
    system = SalvagingSystem(state, registry)
    sim = SimpleNamespace(state=state, salvaging=system, crafting=CraftingSystem(state, registry),
                          player_skill=lambda key: state.player_skills.get(key, 0))
    ctx = SimpleNamespace(sim=sim, registry=registry)
    source = sources[0]
    for quality, need in registry.salvage[source].tool_qualities.items():
        tool = next(item for item in registry.items.values() if item.quality(quality) >= need)
        inv.add(tool.id, 2)
    result = None
    if mode in {'session', 'result'}:
        ok, message, _ = system.begin(source, inv, b'salvage-preview')
        if not ok:
            raise RuntimeError(message)
        system.act('inspect', inv, b'salvage-preview')
        if mode == 'result':
            while system.session_view():
                action = system._stage(state.player_salvage_session, registry.salvage[source])['correct']
                system.act(action, inv, b'salvage-preview')
            result = state.player_salvage_log[-1]
    data = salvage_panel_data(ctx, inv, result=result)
    data['selected_key'] = source
    rows = [MenuRow(iid, row['name']) for iid, row in data['items'].items()]
    if not rows:
        rows = [MenuRow('__empty__', 'No salvageable items in your pack')]
    return rows, data


def render_previews(output):
    registry = ContentRegistry.load(DATA_DIR)
    output.mkdir(parents=True, exist_ok=True)
    for label, size in (('minimum', (740, 500)), ('standard', (900, 620))):
        for mode in ('populated', 'session', 'result', 'empty'):
            term = PygameTerminal(size[0] + 32, size[1] + 32)
            term.enter()
            try:
                term.screen.fill((10, 17, 19))
                term._floating_panels['crafting'] = {'x': 16, 'y': 16, 'w': size[0], 'h': size[1]}
                rows, data = fixture(registry, mode)
                capacity = term.menu_page_size('salvaging_unified')
                term.present_feature_menu('salvaging_unified', 'SALVAGING', rows[:capacity], 0,
                                          total=len(rows), data=data)
                path = output / f'salvage-{mode}-{label}.png'
                term.pg.image.save(term.screen, str(path))
                print(path)
            finally:
                term.restore()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('artifacts/ui-browser-preview'))
    render_previews(parser.parse_args().output)
