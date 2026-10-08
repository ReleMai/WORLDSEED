"""Upright static shells; artwork does not discover the ground behind them."""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path

from worldseed.systems.state import pos_key
from worldseed.systems.building_variants import building_variant


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


def _art_ref(term, shell, interior_plans=None):
    # O(1) observation of the existing ground plan freezes inhabited facades
    # even when a later content update adds more choices to the style catalog.
    saved = (interior_plans or {}).get('interior:' + shell.uid)
    variant = building_variant(shell, variant_id=str(getattr(saved, 'variant_id', '')))
    if variant is not None:
        for visual_id in (variant['id'], variant['asset']):
            ref = term._visuals.ref('building_shells', visual_id)
            if ref.paths:
                return variant['asset'], term._visuals.resolve(ref)
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


def _surface_key(function, path, shell, width, height):
    entrance = (shell.entrance[0] - shell.bounds[0], shell.entrance[1] - shell.bounds[1]) if shell.entrance else None
    grid = (shell.bounds[2] - shell.bounds[0] + 1, shell.bounds[3] - shell.bounds[1] + 1)
    return ('whole-building-ground-fit', function, shell.function, str(path), width, height,
            grid, entrance, shell.door_side,
            tuple((x-shell.bounds[0],y-shell.bounds[1]) for x,y in shell.footprint))


def _whole_surface(term, shell, width, height, interior_plans=None):
    function, path = _art_ref(term, shell, interior_plans)
    # Physical door orientation cannot rotate perspective-painted artwork.
    key = _surface_key(function, path, shell, width, height)
    cache = getattr(term, '_building_surface_cache', None)
    if cache is None:
        cache = term._building_surface_cache = {}
    if key in cache:
        return cache[key][0]
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
        # Export padding is not building geometry. Fit its visible bounds to
        # the immutable physical extent, rather than shifting a whole padded
        # PNG to line up its door (which left invisible blocked street tiles).
        axes, fitted_door = _fit_geometry(shell, width, height, source,
                                          _door_anchor(function, path))
        sx, sy, tx, ty = axes
        for yi in range(len(sy) - 1):
            for xi in range(len(sx) - 1):
                src = pg.Rect(sx[xi], sy[yi], sx[xi + 1] - sx[xi], sy[yi + 1] - sy[yi])
                dst = pg.Rect(tx[xi], ty[yi], tx[xi + 1] - tx[xi], ty[yi + 1] - ty[yi])
                if src.width and src.height and dst.width and dst.height:
                    surface.blit(pg.transform.smoothscale(source.subsurface(src), dst.size), dst.topleft)
    else:
        # Explicit missing-art fallback stays a single closed shell, never the
        # old wall/floor puzzle or a borrowed building type.
        pg.draw.rect(surface, (98, 73, 49), surface.get_rect(), border_radius=max(2, width // 20))
        pg.draw.rect(surface, (161, 128, 83), surface.get_rect(), max(1, width // 40))
        label = term.small_font.render(shell.function.replace('_', ' ').title(), True, (235, 213, 174))
        surface.blit(label, label.get_rect(center=surface.get_rect().center))
        _, fitted_door = _fit_geometry(shell, width, height, None,
                                       _door_anchor(function, path))
    # Bounding boxes are not collision geometry. Clear cutouts/courtyards so
    # their walkable ground cannot look or select like a solid building body.
    columns=shell.bounds[2]-shell.bounds[0]+1
    rows=shell.bounds[3]-shell.bounds[1]+1
    cells=set(shell.footprint)
    if len(cells)<columns*rows:
        for gy in range(rows):
            for gx in range(columns):
                if (shell.bounds[0]+gx,shell.bounds[1]+gy) not in cells:
                    x0,x1=gx*width//columns,(gx+1)*width//columns
                    y0,y1=gy*height//rows,(gy+1)*height//rows
                    surface.fill((0,0,0,0),(x0,y0,x1-x0,y1-y0))
    if len(cache) >= 96:
        cache.clear()
    # Geometry and fitted pixels have one lifetime. Source-cache eviction can
    # never pair an existing fitted roof with a default/full-canvas door fit.
    cache[key] = (surface, fitted_door)
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


def _door_anchor(function, path):
    catalog = _anchor_catalog()
    name = path.stem if path is not None else function
    return catalog.get('assets', {}).get(name, catalog.get('assets', {}).get(function, catalog['default']))['door_rect']


def _mapped_axis(value, source, target):
    value = min(source[-1], max(source[0], value))
    for index in range(len(source) - 1):
        if value <= source[index + 1]:
            fraction = (value - source[index]) / max(1, source[index + 1] - source[index])
            return round(target[index] + fraction * (target[index + 1] - target[index]))
    return target[-1]


def _fit_geometry(shell, width, height, source, anchor):
    """Shared pixel fit for roof art and its independent selectable doorway.

    The physical footprint and door never move. A centre doorway band keeps
    the painted recess and selectable leaf aligned; side bands fit the full
    upright facade around it. Alpha remains pointer-only, never collision data.
    """
    if source is None:
        sw, sh = 1000, 1000
        bounds = (0, 0, sw, sh)
    else:
        sw, sh = source.get_size()
        box = source.get_bounding_rect(16)
        bounds = (box.left, box.top, box.right, box.bottom) if box.width and box.height else (0, 0, sw, sh)
    left, top, right, bottom = bounds
    ax, ay, aw, ah = anchor
    door_bottom = (ay + ah) * sh / 1000
    sx, sy, tx, ty = (left, right), (top, bottom), (0, width), (0, height)
    target_x = None
    if shell.entrance is not None and shell.door_side == 'south' and right - left > 2 and bottom - top > 1:
        size = max(1, width // (shell.bounds[2] - shell.bounds[0] + 1))
        target_x = (shell.entrance[0] - shell.bounds[0]) * size + size // 2
        target_bottom = (shell.entrance[1] - shell.bounds[1] + 1) * size - max(1, size // 10)
        target_x = max(1, min(width - 1, target_x))
        target_bottom = max(1, min(height - 1, target_bottom))
        sy = (top, max(top + 1, min(bottom - 1, round(door_bottom))), bottom)
        ty = (0, target_bottom, height)
        dy0 = _mapped_axis(ay * sh / 1000, sy, ty)
        recess_height = max(3, target_bottom - dy0)
        # Scale the opening from its vertical fit, not the padded canvas width.
        # Narrow townhouse exports must not acquire a two-tile-wide doorway.
        opening_width = max(2, round(aw * sw * recess_height / max(1, ah * sh)))
        opening_width = min(opening_width, max(2, 2 * min(target_x, width - target_x) - 1))
        source_left = max(left + 1, min(right - 2, round(ax * sw / 1000)))
        source_right = max(source_left + 1, min(right - 1, round((ax + aw) * sw / 1000)))
        target_left = target_x - opening_width // 2
        sx = (left, source_left, source_right, right)
        tx = (0, target_left, target_left + opening_width, width)
    dx0 = _mapped_axis(ax * sw / 1000, sx, tx)
    dx1 = _mapped_axis((ax + aw) * sw / 1000, sx, tx)
    dy0 = _mapped_axis(ay * sh / 1000, sy, ty)
    dy1 = _mapped_axis(door_bottom, sy, ty)
    door_width, door_height = max(2, dx1 - dx0), max(3, dy1 - dy0)
    if target_x is not None:
        # This is the very same centre band used to paint the original recess,
        # not a separately re-centred leaf over an asymmetrically scaled hole.
        dx0, door_width = tx[1], tx[2] - tx[1]
        dy1 = ty[1]
    return (sx, sy, tx, ty), (dx0, dy1 - door_height, door_width, door_height)


def _facade_door_rect(term, shell, body_rect, interior_plans=None):
    function, path = _art_ref(term, shell, interior_plans)
    key = _surface_key(function, path, shell, body_rect.width, body_rect.height)
    cache = getattr(term, '_building_surface_cache', {})
    if key not in cache:
        _whole_surface(term, shell, body_rect.width, body_rect.height, interior_plans)
        cache = term._building_surface_cache
    x, y, width, height = cache[key][1]
    return term.pg.Rect(body_rect.x + x, body_rect.y + y, width, height)


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


def draw_shells(term, shells, used, left, top, size, known, visible, hit_regions=None, door_states=None, interior_plans=None):
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
            if not rect.colliderect(used):
                continue
            surface = _whole_surface(term, shell, rect.width, rect.height, interior_plans)
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
            recess = _facade_door_rect(term, shell, body_rect, interior_plans)
            role = 'facade'
            if shell.door_side != 'south':
                # A few frozen, tightly packed legacy shells cannot gain a
                # south apron without destroying their minimum footprint.
                # Show their real side portal, never an inaccessible painted
                # front door that secretly targets a different world cell.
                x, y = shell.entrance
                # A side portal belongs to its real threshold tile; a tall
                # front-door fit must not spill across the neighbour's path.
                scale=min(1,(size-max(1,size//10))/max(1,recess.height),(size-2)/max(1,recess.width))
                recess.size=(max(2,round(recess.width*scale)),max(3,round(recess.height*scale)))
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
