"""Observational continuous-space interior presentation.

The transform uses fixed-point simulation coordinates. Texture repetition is
only decoration: it does not supply furniture positions or collision cells.
"""
from __future__ import annotations

from dataclasses import dataclass

from worldseed.entities.components import Vitals


@dataclass(frozen=True, slots=True)
class InteriorCamera:
    left: float
    top: float
    scale: float
    screen_x: int
    screen_y: int

    def to_screen(self, x: int, y: int) -> tuple[int, int]:
        return (round(self.screen_x + (x - self.left) * self.scale),
                round(self.screen_y + (y - self.top) * self.scale))

    def to_units(self, x: int, y: int) -> tuple[int, int]:
        return (round(self.left + (x - self.screen_x) / self.scale),
                round(self.top + (y - self.screen_y) / self.scale))


def pointer_units(term, point) -> tuple[int, int] | None:
    """Convert a pointer report without snapping or consulting world terrain."""
    ctx = getattr(term, '_interior_context', None)
    if ctx and ctx['used'].collidepoint(point):
        x, y = ctx['camera'].to_units(*point)
        if 0 <= x < ctx['plan'].width and 0 <= y < ctx['plan'].height:
            return x, y
    return None


def pointer_object(term, point):
    """Select the painted object, not the grid or the furniture's tiny base.

    Render-only silhouettes resolve to stable IDs. Commands still validate the
    real collision footprint, distance and intervening walls.
    """
    ctx = getattr(term, '_interior_context', None)
    if not ctx or not ctx['used'].collidepoint(point):
        return None
    for region in reversed(ctx.get('object_regions', ())):
        base, art = region['base'], region['rect']
        if base.collidepoint(point):
            return region
        if art.collidepoint(point):
            mask = region.get('mask')
            if mask is None or mask.get_at((point[0] - art.x, point[1] - art.y)):
                return region
        # Small cutouts remain selectable at zoom-out without broad invisible
        # targets masking an adjacent object or a wall.
        if art.width < 18 or art.height < 18:
            if art.inflate(6, 6).collidepoint(point):
                return region
    return None


def refresh_hover(term, *, update_display: bool = True) -> None:
    ctx = getattr(term, '_interior_context', None)
    if not ctx or term._input_mode != 'world':
        return
    point = pointer_units(term, term._last_mouse)
    region = pointer_object(term, term._last_mouse)
    furniture = region['object'] if region else None
    uid = region['uid'] if region else None
    if uid == ctx.get('hover_uid'):
        return
    used = ctx['used']
    term.screen.blit(ctx['snapshot'], used.topleft)
    ctx['hover_uid'] = uid
    if furniture:
        rect = region['rect'].union(region['base'])
        old_clip = term.screen.get_clip()
        term.screen.set_clip(used)
        try:
            term.pg.draw.rect(term.screen, term._theme['accent'], rect, 2, border_radius=3)
            if region['kind'] == 'stairs':
                name = 'Stairs ' + furniture.direction
                hint = 'Right-click to change floors'
            else:
                piece = ctx['registry'].settlement_pieces.get(furniture.piece_id)
                container = getattr(ctx['sim'].interiors, 'container_for_furniture', lambda uid: None)(furniture.uid)
                name = container.name if container else (piece.name if piece else furniture.piece_id.split(':')[-1].replace('_', ' ').title())
                hint = 'Right-click to interact or move'
            term._draw_hover_tooltip([name, hint], rect.topright, used)
        finally:
            term.screen.set_clip(old_clip)
    if update_display:
        term.pg.display.update(used)


def _rect(term, camera, rect):
    x, y = camera.to_screen(rect.x, rect.y)
    return term.pg.Rect(x, y, max(1, round(rect.w * camera.scale)),
                        max(1, round(rect.h * camera.scale)))


def _texture(term, rect, visual_id, *, tile_size=96, fallback=(103, 76, 48)):
    path = term._visuals.resolve(term._visuals.ref('interior_textures', visual_id))
    if path is None:
        path = term._visuals.resolve(term._visuals.ref('interiors', visual_id))
    surface = term._load_sprite(path, tile_size, tile_size, smooth=True)
    term.pg.draw.rect(term.screen, fallback, rect)
    if surface:
        old_clip = term.screen.get_clip()
        term.screen.set_clip(rect.clip(old_clip))
        try:
            for y in range(rect.top, rect.bottom, surface.get_height()):
                for x in range(rect.left, rect.right, surface.get_width()):
                    term.screen.blit(surface, (x, y))
        finally:
            term.screen.set_clip(old_clip)


def _furniture_sprite(term, path, rect):
    """Aspect-fit the authored silhouette without changing furniture collision."""
    if path is None:
        return None
    cache = getattr(term, '_interior_art_sources', None)
    if cache is None:
        cache = term._interior_art_sources = {}
    key = str(path)
    if key not in cache:
        try:
            source = term.pg.image.load(key).convert_alpha()
            bounds = source.get_bounding_rect(min_alpha=1)
            source = source.subsurface(bounds).copy() if bounds.width and bounds.height else None
        except (OSError, term.pg.error):
            source = None
        if len(cache) >= 96:
            cache.pop(next(iter(cache)))
        cache[key] = source
    source = cache[key]
    if source is None:
        return None
    ratio = min(rect.width / source.get_width(), rect.height / source.get_height())
    size = (max(1, round(source.get_width() * ratio)), max(1, round(source.get_height() * ratio)))
    scaled = getattr(term, '_interior_art_scaled', None)
    if scaled is None:
        scaled = term._interior_art_scaled = {}
    scale_key = (key, size)
    if scale_key not in scaled:
        if len(scaled) >= 128:
            scaled.clear()
        scaled[scale_key] = term.pg.transform.smoothscale(source, size)
    return scaled[scale_key]


def furniture_art_rect(term, camera, furniture):
    """Ground footprint and upright sprite height are separate authorities."""
    from worldseed.systems.interior_furnishing import furniture_visual
    style = furniture_visual(furniture.piece_id)
    base = _rect(term, camera, furniture)
    canvas = base.copy()
    canvas.height = max(1, round(base.height * style['height_ratio']))
    canvas.midbottom = base.midbottom
    return base, canvas


def _register_object(term, regions, obj, kind, base, sprite, position):
    rect = sprite.get_rect(topleft=position) if sprite else base
    regions.append({'kind': kind, 'uid': obj.uid, 'object': obj, 'base': base,
                    'rect': rect, 'mask': term.pg.mask.from_surface(sprite, 16) if sprite else None})


def _draw_furniture_shadow(term, base):
    """Soft contact shadow at the feet, never an opaque collision rectangle."""
    size = (max(2, round(base.width * .9)), max(3, min(12, round(base.height * .24))))
    cache = getattr(term, '_interior_contact_shadows', None)
    if cache is None:
        cache = term._interior_contact_shadows = {}
    if size not in cache:
        if len(cache) >= 64:
            cache.clear()
        surface = term.pg.Surface(size, term.pg.SRCALPHA)
        for inset, alpha in ((0, 18), (1, 28), (2, 40)):
            rect = surface.get_rect().inflate(-inset * 2, -inset)
            if rect.width > 0 and rect.height > 0:
                term.pg.draw.ellipse(surface, (20, 15, 10, alpha), rect)
        cache[size] = surface
    term.screen.blit(cache[size], (base.centerx - size[0] // 2, base.bottom - size[1] // 2))


def _draw_actor(term, sim, camera, uid, actor):
    x, y = camera.to_screen(actor.x, actor.y)
    npc = sim.state.npcs.get(uid) if uid != 'player' else None
    if uid == 'player':
        path = term._visuals.player_path(getattr(sim.state, 'player_sex', 'male'),
                                        getattr(sim.state, 'player_sprite_index', 0))
    else:
        path = term._npc_sprite_path(npc) if npc else None
    size = term._tile_px
    sprite = term._load_sprite(path, size, round(size * 1.6), smooth=True)
    term.pg.draw.ellipse(term.screen, (41, 31, 23), (x - size // 4, y - 3, size // 2, 7))
    if sprite:
        term.screen.blit(sprite, (x - sprite.get_width() // 2, y - sprite.get_height()))
    else:
        term.pg.draw.circle(term.screen, term._theme['accent'] if uid == 'player' else term._theme['good'], (x, y), max(3, size // 4))


def draw_interior(term, registry, sim, entities, player_id, message='') -> None:
    """Draw one prepared plan only; never query exterior spatial systems."""
    plan = sim.interiors.current_plan()
    player = sim.interiors.player_presence()
    if plan is None or player is None:
        return
    pg, screen, th = term.pg, term.screen, term._theme
    term._drawing_target = False
    term._combat_targeting = False
    ox, oy, ow, oh = term._draw_chrome('WORLDSEED // INTERIOR')
    sidebar = max(1, min(330, ow // 3))
    footer = max(1, min(130, oh // 4))
    horizontal_gap = min(10, max(0, ow // 16))
    vertical_gap = min(8, max(0, oh // 16))
    used = pg.Rect(ox, oy, max(1, ow - sidebar - horizontal_gap), max(1, oh - footer - vertical_gap))
    side = pg.Rect(used.right + horizontal_gap, oy, sidebar, oh)
    foot = pg.Rect(ox, used.bottom + vertical_gap, used.width, footer)
    for rect in (used, side, foot):
        pg.draw.rect(screen, th['panel2'], rect, border_radius=3)
        pg.draw.rect(screen, th['edge'], rect, 1, border_radius=3)
    scale = term._tile_px / 1000.0
    # Continuous camera origin follows sub-tile positions without snapping.
    camera = InteriorCamera(player.x - used.width / (2 * scale),
                            player.y - used.height / (2 * scale), scale, used.x, used.y)
    object_regions = []
    actors = sorted(sim.interiors.actors_in_space(player.space_id), key=lambda row: (row[1].y, row[0]))
    actor_index = 0
    old_clip = screen.get_clip()
    screen.set_clip(used)
    try:
        screen.fill((12, 14, 15), used)
        floor = pg.Rect(*camera.to_screen(0, 0), max(1, round(plan.width * scale)),
                        max(1, round(plan.height * scale)))
        materials = {key: getattr(plan, key, '') for key in ('floor_material', 'wall_material')}
        floor_id, wall_id = term._visuals.interior_materials(getattr(plan, 'function', 'residence'), **materials)
        _texture(term, floor, floor_id, tile_size=max(48, term._tile_px * 4))
        for room in plan.rooms:
            rect = _rect(term, camera, room.rect)
            room_floor, _ = term._visuals.interior_materials(getattr(plan, 'function', 'residence'), room.name, **materials)
            if room_floor != floor_id:
                _texture(term, rect, room_floor, tile_size=max(48, term._tile_px * 4))
            label = term.small_font.render(term._fit_ui_text(room.name, term.small_font, max(1, rect.width - 18)),
                                           True, (193, 172, 137))
            if rect.width > 40 and rect.height > 28:
                screen.blit(label, (rect.x + 9, rect.y + 7))
        for wall in plan.walls:
            rect = _rect(term, camera, wall)
            pg.draw.rect(screen, (34, 30, 27), rect.move(3, 4))
            _texture(term, rect, wall_id, tile_size=48, fallback=(153, 139, 112))
            pg.draw.rect(screen, (74, 65, 53), rect, 1)
        if getattr(plan, 'floor_index', 0) == 0:
            portal = camera.to_screen(plan.entry_x, plan.entry_y)
            doorway = pg.Rect(0, 0, max(12, round(1100 * scale)), max(18, round(1700 * scale)))
            doorway.midbottom = camera.to_screen(plan.entry_x, plan.height - 300)
            path = term._visuals.resolve(term._visuals.ref('building_doors', 'wood_open'))
            sprite = _furniture_sprite(term, path, doorway)
            if sprite:
                screen.blit(sprite, sprite.get_rect(midbottom=doorway.midbottom))
            pg.draw.circle(screen, th['accent'], portal, max(5, term._tile_px // 3), 2)
            screen.blit(term.small_font.render('EXIT', True, th['accent']), (portal[0] + 9, portal[1] - 8))
        for stair in getattr(plan, 'stairs', ()):
            rect = _rect(term, camera, stair)
            path = term._visuals.resolve(term._visuals.ref('interior_stairs', stair.direction))
            sprite = _furniture_sprite(term, path, rect)
            position = (rect.centerx - sprite.get_width() // 2, rect.bottom - sprite.get_height()) if sprite else rect.topleft
            if sprite:
                screen.blit(sprite, position)
            _register_object(term, object_regions, stair, 'stairs', rect, sprite, position)
            screen.blit(term.small_font.render(stair.direction.upper(), True, th['accent']), (rect.x, rect.bottom + 2))
        from worldseed.systems.interior_furnishing import furniture_visual, furniture_base_piece
        for furniture in sorted(plan.furniture, key=lambda f: (not furniture_visual(f.piece_id)['flat'], f.y + f.h, f.x, f.uid)):
            if not furniture_visual(furniture.piece_id)['flat']:
                while actor_index < len(actors) and actors[actor_index][1].y <= furniture.y + furniture.h:
                    _draw_actor(term, sim, camera, *actors[actor_index])
                    actor_index += 1
            rect, canvas = furniture_art_rect(term, camera, furniture)
            if not canvas.colliderect(used):
                continue
            piece = registry.settlement_pieces.get(furniture.piece_id)
            path = term._visuals.resolve(term._visuals.ref('interiors', furniture.piece_id))
            container = getattr(sim.interiors, 'container_for_furniture', lambda uid: None)(furniture.uid)
            if container is not None and furniture_base_piece(furniture.piece_id) == furniture.piece_id:
                path = term._visuals.resolve(term._visuals.ref('containers', container.profile_id)) or path
            # Exact authored furniture IDs prevent the old generic grey/black
            # block stand-ins. Existing workshop art is resolved by its real
            # piece ID only; legacy clutter uses the same native prop art as
            # the exterior, before truly unknown coverage becomes a glyph.
            if path is None:
                path = term._visuals.resolve(term._visuals.ref('settlement_pieces', furniture.piece_id))
            sprite = _furniture_sprite(term, path, canvas)
            if getattr(furniture, 'solid', True):
                _draw_furniture_shadow(term, rect)
            if sprite:
                position = (rect.centerx - sprite.get_width() // 2, rect.bottom - sprite.get_height())
                screen.blit(sprite, position)
            elif not term._draw_settlement_yard_piece(piece, rect):
                # Explicit glyph fallback preserves usability without inventing
                # a simulation object or silently borrowing another item's art.
                pg.draw.rect(screen, (132, 99, 63), rect, border_radius=3)
                glyph = term.small_font.render(getattr(piece, 'glyph', '?'), True, th['text'])
                screen.blit(glyph, glyph.get_rect(center=rect.center))
            _register_object(term, object_regions, furniture, 'furniture', rect, sprite,
                             position if sprite else rect.topleft)
        for pile in getattr(plan, 'piles', ()):
            if not pile.items:
                continue
            x, y = camera.to_screen(pile.x, pile.y)
            item_id = next(iter(pile.items))
            path = term._visuals.resolve(term._visuals.ref('items', item_id))
            sprite = term._load_sprite(path, term._tile_px, term._tile_px, smooth=True)
            if sprite:
                screen.blit(sprite, (x - sprite.get_width() // 2, y - sprite.get_height() // 2))
        for uid, actor in actors[actor_index:]:
            _draw_actor(term, sim, camera, uid, actor)
    finally:
        screen.set_clip(old_clip)
    old_clip = screen.get_clip()
    screen.set_clip(pg.Rect(side.x+6,side.y+6,max(1,side.width-12),max(1,side.height-58)))
    try:
        tx, ty = side.x + 14, side.y + 12
        def text(value, color=None, gap=22):
            nonlocal ty
            fitted = term._fit_ui_text(str(value), term.small_font, side.width - 28)
            screen.blit(term.small_font.render(fitted, True, color or th['text']), (tx, ty))
            ty += gap
        text(getattr(sim.state, 'player_name', 'Wanderer'), th['accent'], 28)
        text(plan.name, th['accent'])
        if getattr(plan, 'floor_count', 1) > 1:
            text(f'Floor {plan.floor_index + 1} / {plan.floor_count}', th['accent'])
        text(sim.clock.label(), th['muted'])
        text(f'Inside: {player.x / 1000:.2f}, {player.y / 1000:.2f}', th['muted'])
        vit = entities.try_get(player_id, Vitals) or Vitals()
        text(f'Health {vit.hp}/{vit.max_hp} • Stamina {vit.stamina}')
        if getattr(sim.state,'player_trespass_property_id','') and getattr(sim.state,'player_trespass_property_id','')==getattr(plan,'building_id',''):
            text('TRESPASSING',th['danger'])
        if getattr(sim.state,'player_stealth_mode',False) and getattr(sim,'stealth',None):
            snap=sim.stealth.snapshot(sim.player_pos,sim.clock.minute)
            text('Stealth: noticed' if snap.get('seen_by') else 'Stealth: unseen',th['muted'])
        text('FREE MOVEMENT', th['accent'], 26)
        text('WASD / arrows: walk', th['muted'])
        text('Right-click objects, stairs or exit', th['muted'])
        if getattr(term, '_interior_placing', None):
            text('Left-click to place furniture', th['good'])
        text('ROOMS', th['accent'], 25)
        for room in plan.rooms:
            text(room.name, th['muted'])
        known = sim.introduced_npc_ids()
        for uid, actor in actors:
            if uid == 'player':
                continue
            npc = sim.state.npcs.get(uid)
            if npc is not None:
                text((npc.name if uid in known else 'Stranger') + ': ' + actor.action.replace('_', ' '), th['muted'])
    finally:
        screen.set_clip(old_clip)
    term._draw_stance_buttons(pg.Rect(side.x+2,max(side.y+2,side.bottom-42),max(1,side.width-4),29),
                             getattr(sim.state,'player_hunting_stance','normal'))
    term._draw_footer(foot, message or 'Right-click furnishings to interact. Interior movement is not tile-bound.', sim)
    term._hover_context = None
    term._hover_map_snapshot = None
    term._weather_animation_context = None
    term._weather_static_snapshot = None
    term._water_animation_cells = []
    term._interior_context = {'used': used, 'camera': camera, 'plan': plan, 'sim': sim,
                              'registry': registry, 'snapshot': screen.subsurface(used).copy(),
                              'hover_uid': None, 'object_regions': object_regions}
    refresh_hover(term, update_display=False)
    pg.display.flip()
    term.clock.tick(120)
