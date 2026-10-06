"""Offline real-renderer preview of worst padded/off-centre building exports."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worldseed.config import DATA_DIR
from worldseed.systems.building_shells import BuildingShell
from worldseed.systems.state import pos_key
from worldseed.ui.exterior_view import draw_shells
from worldseed.ui.pygame_terminal import PygameTerminal


ASSETS = (
    ('residence_3', 'dev47'), ('residence_5', 'dev47'), ('slate_townhouse', 'dev52'),
    ('scribes_archive', 'dev52'), ('reed_cottage', 'dev52'), ('stone_garrison', 'dev52'),
)


def preview(output: Path):
    output.mkdir(parents=True, exist_ok=True)
    with patch.dict(os.environ, {'SDL_VIDEODRIVER': 'dummy', 'SDL_AUDIODRIVER': 'dummy'}):
        term = PygameTerminal(1280, 832)
        term.enter()
        try:
            pg, size = term.pg, 28
            for marked in (False, True):
                term.screen.fill((31, 44, 34))
                used = pg.Rect(10, 10, 1260, 800)
                for index, (name, family) in enumerate(ASSETS):
                    x, y = 2 + (index % 3) * 14, 2 + (index // 3) * 12
                    footprint = tuple((xx, yy) for yy in range(y, y + 5) for xx in range(x, x + 6))
                    shell = BuildingShell('preview:' + name, 'preview:town', 'residence', 'core:house',
                                          footprint, (x + 2, y + 4), 'door:' + name, 0, 'rectangular',
                                          (x, y, x + 5, y + 4))
                    known = {pos_key(xx, yy, 0) for xx, yy in footprint}
                    physical = pg.Rect(used.x + x * size, used.y + y * size, 6 * size, 5 * size)
                    # Ground path surrounds the same stable physical extent;
                    # no rendered roof or copied asset invents collision.
                    pg.draw.rect(term.screen, (97, 77, 50), physical.inflate(size * 2, size * 2), size)
                    path = Path(DATA_DIR).parent / f'assets/sprites/buildings/{family}/{name}.png'
                    hits = []
                    with patch('worldseed.ui.exterior_view._art_ref', return_value=(name, path)):
                        draw_shells(term, (shell,), used, 0, 0, size, known, known, hit_regions=hits)
                    term.screen.blit(term.small_font.render(name.replace('_', ' ').title(), True, (238, 222, 185)),
                                     (physical.x - 20, physical.y - 36))
                    if marked:
                        pg.draw.rect(term.screen, (70, 220, 155), physical, 1)
                        door = next(row['rect'] for row in hits if row['kind'] == 'door')
                        pg.draw.rect(term.screen, (245, 199, 75), door, 1)
                        pg.draw.circle(term.screen, (245, 199, 75), door.midbottom, 3)
                        term.screen.blit(term.small_font.render('Green: physical bounds / Gold: stable door', True, (210, 210, 195)),
                                         (physical.x - 20, physical.bottom + 45))
                target = output / ('footprint_diagnostics.png' if marked else 'fitted_exteriors.png')
                pg.image.save(term.screen, str(target))
                print(target)
        finally:
            term.restore()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    preview(parser.parse_args().output)
