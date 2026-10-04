"""Upright static shells; artwork does not discover the ground behind them."""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path

from worldseed.systems.state import pos_key


def shell_cells(shells):
    return {(int(x), int(y), 0): shell for shell in shells for x, y in shell.footprint}


def shell_at_pointer(context, pixel):
    """Resolve painted shells/doors, retaining stable physical door identity."""
    used = context['used']
    if not used.collidepoint(pixel):
        return None
    regions = context.get('shell_hit_regions')
    if regions is not None:
        for kind in ('door', 'body'):
            for region in reversed(regions):
                rect = region['rect']
                if region['kind'] != kind or not rect.collidepoint(pixel):
                    continue
                mask = region.get('mask')
                if mask is None or mask.get_at((pixel[0] - rect.x, pixel[1] - rect.y)):
                    return region['shell'], kind
        # Alpha-transparent pixels must not fall through to a physical floor
        # hit. Tile lookup is only a compatibility path for older callers.
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


def _art_ref(term, shell):
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
    return function, path


def _whole_surface(term, shell, width, height):
    _, path = _art_ref(term, shell)
    # Physical door orientation cannot rotate perspective-painted artwork.
    key = ('whole-building-upright', str(path), width, height)
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
        # Source alpha owns the visible silhouette; plan footprints still own
        # collision. Neither seeing a roof nor painting it discovers terrain.
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


@lru_cache(maxsize=1)
def _anchor_catalog():
    path = Path(__file__).resolve().parents[1] / 'assets' / 'building_shell_anchors.json'
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {'default': {'door_rect': [438, 800, 124, 172]}, 'assets': {}}


def _surface_mask(term, surface):
    cache = getattr(term, '_building_hit_mask_cache', None)
    if cache is None:
        cache = term._building_hit_mask_cache = {}
    key = id(surface)
    entry = cache.get(key)
    if entry is not None and entry[0] is surface:
        return entry[1]
    mask = term.pg.mask.from_surface(surface, 16)
    if len(cache) >= 96:
        cache.clear()
    # Retain the source to prevent an object ID reuse producing a wrong mask.
    cache[key] = (surface, mask)
    return mask


def _facade_door_rect(term, shell, body_rect):
    function, path = _art_ref(term, shell)
    catalog = _anchor_catalog()
    name = path.stem if path is not None else function
    anchor = catalog.get('assets', {}).get(name, catalog.get('assets', {}).get(function, catalog['default']))
    x, y, width, height = anchor['door_rect']
    return term.pg.Rect(body_rect.x + round(body_rect.width * x / 1000),
                        body_rect.y + round(body_rect.height * y / 1000),
                        max(2, round(body_rect.width * width / 1000)),
                        max(3, round(body_rect.height * height / 1000)))


def _door_surface(term, shell, width, height, opened=False):
    material = 'iron' if shell.function in {'barracks', 'watchtower', 'watchhouse', 'guardhouse', 'fortress'} else 'wood'
    if opened and material == 'wood' and term._visuals.ref('building_doors', 'wood_open').paths:
        material = 'wood_open'
    path = term._visuals.resolve(term._visuals.ref('building_doors', material))
    key = (str(path), width, height)
    cache = getattr(term, '_building_door_cache', None)
    if cache is None:
        cache = term._building_door_cache = {}
    if key in cache:
        return cache[key]
    source_cache = term._building_source_cache
    source = source_cache.get(str(path))
    if source is None and path is not None:
        try:
            source = term.pg.image.load(str(path)).convert_alpha()
            if len(source_cache) >= 64:
                source_cache.clear()
            source_cache[str(path)] = source
        except (OSError, term.pg.error):
            pass
    pg = term.pg
    if source is None:
        sprite = pg.Surface((width, height), pg.SRCALPHA)
        pg.draw.rect(sprite, (176, 131, 73), sprite.get_rect(), border_radius=2)
    else:
        # Upright portrait leaves are fitted, not stretched into square tiles.
        # Ignore transparent export padding during this presentation-only fit;
        # the authored PNG and cached source remain unchanged.
        bounds = source.get_bounding_rect(16)
        if bounds.width and bounds.height:
            source = source.subsurface(bounds)
        factor = min(width / source.get_width(), height / source.get_height())
        sprite = pg.transform.smoothscale(source, (max(1, round(source.get_width() * factor)),
                                                  max(1, round(source.get_height() * factor))))
    if len(cache) >= 96:
        cache.clear()
    cache[key] = sprite
    return sprite


def _aligned_body_rect(term, shell, body_rect, used, left, top, size):
    """The painted threshold and stable physical portal share one anchor.

    New plans and explicitly repaired legacy plans face south. Do not move a
    legacy north-facing roof across a street while its repair is unavailable.
    """
    if shell.entrance is None or shell.door_side != 'south':
        return body_rect
    x, y = shell.entrance
    threshold = (used.x + (x - left) * size + size // 2,
                 used.y + (y - top + 1) * size - max(1, size // 10))
    door = _facade_door_rect(term, shell, body_rect)
    return body_rect.move(threshold[0] - door.centerx, threshold[1] - door.bottom)


def _contact_shadow(term, rect, current):
    """Soft ground contact, not a square tile overlay or new world feature."""
    pg = term.pg
    width, height = rect.width, max(6, rect.height // 9)
    cache = getattr(term, '_building_shadow_cache', None)
    if cache is None:
        cache = term._building_shadow_cache = {}
    key = (width, height, current)
    if key not in cache:
        shadow = pg.Surface((width + 8, height + 8), pg.SRCALPHA)
        for inset, alpha in ((0, 12), (3, 20), (6, 28)):
            ellipse = shadow.get_rect().inflate(-inset * 2, -max(0, inset // 2))
            if ellipse.width > 0 and ellipse.height > 0:
                pg.draw.ellipse(shadow, (20, 19, 16, alpha if current else alpha // 2), ellipse)
        if len(cache) >= 96:
            cache.clear()
        cache[key] = shadow
    shadow = cache[key]
    term.screen.blit(shadow, (rect.centerx - shadow.get_width() // 2 + 2,
                              rect.bottom - height // 2 - 5))


def draw_shells(term, shells, used, left, top, size, known, visible, hit_regions=None, door_states=None):
    """Paint complete observed static shells without promoting tile discovery."""
    pg, screen = term.pg, term.screen
    shell_by = shell_cells(shells)
    old_clip = screen.get_clip()
    screen.set_clip(used)
    painted = []
    try:
        for shell in sorted(shells, key=lambda row: (row.bounds[3], row.bounds[0], row.uid)):
            if not any(pos_key(x, y, 0) in known for x, y in shell.footprint):
                continue
            x0, y0, x1, y1 = shell.bounds
            rect = pg.Rect(used.x + (x0 - left) * size, used.y + (y0 - top) * size,
                           (x1 - x0 + 1) * size, (y1 - y0 + 1) * size)
            rect = _aligned_body_rect(term, shell, rect, used, left, top, size)
            if not rect.colliderect(used):
                continue
            surface = _whole_surface(term, shell, rect.width, rect.height)
            current = any(pos_key(x, y, 0) in visible for x, y in shell.footprint)
            _contact_shadow(term, rect, current)
            display = surface
            if not current:
                display = surface.copy()
                display.set_alpha(138)
            screen.blit(display, rect.topleft)
            if hit_regions is not None:
                hit_regions.append({'shell': shell, 'kind': 'body', 'rect': rect,
                                    'mask': _surface_mask(term, surface)})
            painted.append((shell, rect))
        for shell, body_rect in painted:
            if shell.entrance is None or pos_key(*shell.entrance, 0) not in known:
                continue
            key = pos_key(*shell.entrance, 0)
            recess = _facade_door_rect(term, shell, body_rect)
            role = 'facade'
            if shell.door_side != 'south':
                # A few frozen, tightly packed legacy shells cannot gain a
                # south apron without destroying their minimum footprint.
                # Show their real side portal, never an inaccessible painted
                # front door that secretly targets a different world cell.
                x, y = shell.entrance
                recess.midbottom = (used.x + (x - left) * size + size // 2,
                                    used.y + (y - top + 1) * size - max(1, size // 10))
                role = 'physical-side'
            door = (door_states or {}).get(shell.door_uid)
            opened = bool(key in visible and door and (door.forced or
                          (door.answering_npc_uid and door.answered_minute >= door.answer_requested_minute >= 0)))
            sprite = _door_surface(term, shell, recess.width, recess.height, opened)
            rect = sprite.get_rect(midbottom=recess.midbottom)
            display = sprite
            if key not in visible:
                display = sprite.copy()
                display.set_alpha(138)
            screen.blit(display, rect.topleft)
            if hit_regions is not None and rect.colliderect(used):
                hit_regions.append({'shell': shell, 'kind': 'door', 'role': role, 'rect': rect,
                                    'mask': _surface_mask(term, sprite), 'target': shell.entrance})
    finally:
        screen.set_clip(old_clip)
    return shell_by
