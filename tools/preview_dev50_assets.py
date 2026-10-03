"""Render the production cutouts and connected fences for visual review."""
import argparse
import os
from pathlib import Path

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.ui.fence_view import fence_surface
from worldseed.ui.interior_view import _furniture_sprite
from worldseed.ui.pygame_terminal import PygameTerminal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    term = PygameTerminal(1800, 1200)
    term.enter()
    try:
        pg = term.pg
        term.screen.fill((44, 48, 42))
        names = ('household_chest', 'wardrobe', 'pantry_cabinet', 'inn_barrel', 'armory_locker',
                 'tool_chest', 'supply_crate', 'grain_bin', 'medicine_cabinet', 'archive_bookcase')
        for i, name in enumerate(names):
            rect = pg.Rect(35 + i % 5 * 355, 45 + i // 5 * 350, 275, 270)
            path = term._visuals.resolve(term._visuals.ref('containers', 'core:' + name))
            sprite = _furniture_sprite(term, path, rect)
            term.screen.blit(sprite, sprite.get_rect(midbottom=rect.midbottom))
            label = term.font.render(name.replace('_', ' ').title(), True, (224, 207, 168))
            term.screen.blit(label, (rect.x, rect.bottom + 18))
        registry = ContentRegistry.load(DATA_DIR)
        piece = registry.settlement_pieces['core:dev43_field_fence_piece']
        for i, bits in enumerate((2, 10, 10, 12)):
            term.screen.blit(fence_surface(term, piece, 100, bits), (90 + i * 100, 850))
        for i, bits in enumerate((1, 5, 9)):
            term.screen.blit(fence_surface(term, piece, 100, bits), (390, 950 + i * 70))
        gate = registry.settlement_pieces['core:animal_pen_gate_piece']
        term.screen.blit(fence_surface(term, gate, 100, 10), (250, 850))
        for i in (0, 1):
            path = term._visuals.resolve(term._visuals.ref('species', 'core:chicken'), i)
            rect = pg.Rect(800 + i * 440, 850, 320, 256)
            sprite = _furniture_sprite(term, path, rect)
            term.screen.blit(sprite, sprite.get_rect(center=rect.center))
        output = args.output_dir / 'storage-fences-chickens.png'
        pg.image.save(term.screen, str(output))
        print(output)
    finally:
        term.restore()


if __name__ == '__main__':
    main()
