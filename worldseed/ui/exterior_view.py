"""Whole-building artwork projected onto stable prepared shell footprints.

Sprites are decoration, never collision or identity authority. Discovery clips
every footprint cell separately, so seeing one corner does not reveal a house.
"""
from __future__ import annotations

from worldseed.systems.state import pos_key


def shell_cells(shells):
    return {(int(x), int(y), 0): shell for shell in shells for x, y in shell.footprint}


def shell_at_pointer(context, pixel):
    """Read only this frame's discovery-filtered presentation hit model."""
    used = context['used']
    if not used.collidepoint(pixel):
        return None
    size = context['tile_px']
    x = context['left'] + (pixel[0] - used.x) // size
    y = context['top'] + (pixel[1] - used.y) // size
    key = (x, y, context['z'])
    if pos_key(*key) not in context['known']:
        return None
    shell = context.get('shell_by', {}).get(key)
    if shell is None:
        return None
    return shell, 'door' if shell.entrance is not None and (x, y) == tuple(shell.entrance) else 'body'


def _whole_surface(term, shell, width, height):
    function = shell.function
    if function == 'residence':
        variants = [name for name in ('residence', 'residence_2', 'residence_3', 'residence_4', 'residence_5', 'residence_6')
                    if term._visuals.ref('building_shells', name).paths]
        if variants:
            function = variants[term._stable_variant(shell.uid, len(variants))]
    ref = term._visuals.ref('building_shells', function)
    if not ref.paths:
        ref = term._visuals.ref('building_shells', 'core:' + shell.function)
    path = term._visuals.resolve(ref, term._stable_variant(shell.uid, len(ref.paths)))
    orientation = str(getattr(shell, 'door_side', getattr(shell, 'orientation', 'south')))
    angle = {'south': 0, 'north': 180, 'east': 90, 'west': -90}.get(orientation, 0)
    key = ('whole-building', str(path), orientation, width, height)
    cache = getattr(term, '_building_surface_cache', None)
    if cache is None:
        cache = term._building_surface_cache = {}
    if key in cache:
        return cache[key]
    pg = term.pg
    source_cache = getattr(term, '_building_source_cache', None)
    if source_cache is None:
        source_cache = term._building_source_cache = {}
    source = source_cache.get(str(path))
    if source is None and path is not None:
        try:
            source = pg.image.load(str(path)).convert_alpha()
            if len(source_cache) >= 64:
                source_cache.clear()
            source_cache[str(path)] = source
        except (OSError, pg.error):
            source = None
    surface = pg.Surface((width, height), pg.SRCALPHA)
    if source is not None:
        # Art fills the plan bounds; shape clipping is exclusively the stable
        # footprint mask rather than transparency-derived collision.
        if angle:
            source = pg.transform.rotate(source, angle)
        surface.blit(pg.transform.smoothscale(source, (width, height)), (0, 0))
    else:
        # Explicit missing-art fallback stays a single closed shell, never the
        # old wall/floor puzzle or a borrowed building type.
        pg.draw.rect(surface, (98, 73, 49), surface.get_rect(), border_radius=max(2, width // 20))
        pg.draw.rect(surface, (161, 128, 83), surface.get_rect(), max(1, width // 40))
        label = term.small_font.render(shell.function.replace('_', ' ').title(), True, (235, 213, 174))
        surface.blit(label, label.get_rect(center=surface.get_rect().center))
    if len(cache) >= 96:
        cache.clear()
    cache[key] = surface
    return surface


def draw_shells(term, shells, used, left, top, size, known, visible):
    """Paint bounded prepared shells, then separately selectable entrances."""
    pg, screen = term.pg, term.screen
    shell_by = shell_cells(shells)
    old_clip = screen.get_clip()
    screen.set_clip(used)
    try:
        for shell in sorted(shells, key=lambda row: (row.bounds[3], row.bounds[0], row.uid)):
            if not any(pos_key(x, y, 0) in known for x, y in shell.footprint):
                continue
            x0, y0, x1, y1 = shell.bounds
            width, height = (x1 - x0 + 1) * size, (y1 - y0 + 1) * size
            surface = _whole_surface(term, shell, width, height)
            remembered = None
            for x, y in shell.footprint:
                key = pos_key(x, y, 0)
                if key not in known:
                    continue
                dest = pg.Rect(used.x + (x - left) * size, used.y + (y - top) * size, size, size)
                if not dest.colliderect(used):
                    continue
                source = pg.Rect((x - x0) * size, (y - y0) * size, size, size)
                if key in visible:
                    screen.blit(surface, dest, source)
                else:
                    if remembered is None:
                        remembered = surface.copy()
                        remembered.set_alpha(138)
                    screen.blit(remembered, dest, source)
        for shell in shells:
            if shell.entrance is None:
                continue
            x, y = shell.entrance
            key = pos_key(x, y, 0)
            if key not in known:
                continue
            rect = pg.Rect(used.x + (x - left) * size, used.y + (y - top) * size, size, size)
            if not rect.colliderect(used):
                continue
            material = 'iron' if shell.function in {'barracks', 'watchtower', 'watchhouse', 'guardhouse', 'fortress'} else 'wood'
            path = term._visuals.resolve(term._visuals.ref('building_doors', material))
            sprite = term._load_sprite(path, size, size, smooth=True)
            if sprite is not None:
                angle = {'south': 0, 'north': 180, 'east': 90, 'west': -90}.get(str(getattr(shell, 'door_side', getattr(shell, 'orientation', 'south'))), 0)
                door_cache = getattr(term, '_building_door_cache', None)
                if door_cache is None:
                    door_cache = term._building_door_cache = {}
                cache_key = (str(path), size, angle)
                if cache_key not in door_cache:
                    if len(door_cache) >= 96:
                        door_cache.clear()
                    door_cache[cache_key] = pg.transform.rotate(sprite, angle) if angle else sprite
                sprite = door_cache[cache_key]
                if key not in visible:
                    sprite = sprite.copy()
                    sprite.set_alpha(138)
                screen.blit(sprite, sprite.get_rect(center=rect.center))
            else:
                pg.draw.rect(screen, (176, 131, 73) if key in visible else (97, 76, 48), rect.inflate(-max(2, size // 4), -max(2, size // 5)), border_radius=2)
    finally:
        screen.set_clip(old_clip)
    return shell_by
