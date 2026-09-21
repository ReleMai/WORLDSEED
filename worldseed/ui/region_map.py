"""Dev5 strategic view of existing regional plans, never local tile generation."""
from dataclasses import dataclass
from worldseed.presentation.regional_terrain import RegionalTerrainAssets

from worldseed.ui.layout import regional_grid
from worldseed.world.region_blocks import CARDINALS, REGION_SIZE, region_coords


UNKNOWN_COLOR = (17, 21, 23)
UNAVAILABLE_COLOR = (45, 47, 48)
ROAD_COLOR = (171, 145, 94)
WATER_COLOR = (56, 105, 126)
CURRENT_COLOR = (171, 223, 235)
NEIGHBOR_OFFSETS = {
    'north': (0, -1), 'south': (0, 1), 'west': (-1, 0), 'east': (1, 0),
    'northwest': (-1, -1), 'northeast': (1, -1), 'southwest': (-1, 1), 'southeast': (1, 1),
}

CURRENT_VECTORS = {
    'north': (0, -1), 'northeast': (1, -1), 'east': (1, 0), 'southeast': (1, 1),
    'south': (0, 1), 'southwest': (-1, 1), 'west': (-1, 0), 'northwest': (-1, -1),
}

@dataclass
class RegionalView:
    center: tuple[int, int]
    discovered: set
    plans: dict
    towns: tuple


def regional_view(sim, cols, rows):
    """Read only discovered regions in a bounded window around the player."""
    p = sim.player_pos
    center = region_coords(p.x, p.y)
    cx, cy = center

    def visible(rx, ry):
        return abs(rx - cx) <= cols // 2 and abs(ry - cy) <= rows // 2

    discovered = set()
    for token in sim.discovered_tiles_set:
        try:
            x, y, z = map(int, token.split(','))
        except (TypeError, ValueError):
            continue
        coords = region_coords(x, y)
        if z == 0 and visible(*coords):
            discovered.add(coords)
    if p.z == 0:
        discovered.add(center)
    plans = {coords: sim.region_planner.read_prepared(*coords)
             for coords in sorted(discovered)}
    towns = tuple(town for town in sim.known_settlements()
                  if (town.region_x, town.region_y) in discovered)
    return RegionalView(center, discovered, plans, towns)


def edge_point(rect, direction, offset):
    """Use a shared boundary, not each rectangle's last interior pixel.

    Adjacent regions then meet at exactly the same pixel for the same 0..511
    exit offset, including negative world coordinates.
    """
    fraction = max(0, min(REGION_SIZE - 1, offset)) / REGION_SIZE
    if direction == 'north':
        return rect.left + round(fraction * rect.width), rect.top
    if direction == 'south':
        return rect.left + round(fraction * rect.width), rect.bottom
    if direction == 'west':
        return rect.left, rect.top + round(fraction * rect.height)
    return rect.right, rect.top + round(fraction * rect.height)


def _draw_current_arrow(pg, screen, color, x: int, y: int, dx: int, dy: int, scale: int = 8):
    if not (dx or dy):
        return
    mag = max(1, abs(dx) + abs(dy))
    ux, uy = dx / mag, dy / mag
    ex, ey = x + int(round(ux * scale)), y + int(round(uy * scale))
    lx, ly = x - int(round(uy * max(2, scale // 3))), y + int(round(ux * max(2, scale // 3)))
    rx, ry = x + int(round(uy * max(2, scale // 3))), y - int(round(ux * max(2, scale // 3)))
    pg.draw.line(screen, color, (x, y), (ex, ey), 2)
    pg.draw.line(screen, color, (ex, ey), (lx, ly), 2)
    pg.draw.line(screen, color, (ex, ey), (rx, ry), 2)


def draw_region_map(term, sim):
    pg, screen = term.pg, term.screen
    if screen is None:
        return
    ox, oy, ow, oh = term._draw_chrome('WORLDSEED // REGION MAP')
    side_w = min(290, ow // 3)
    area = pg.Rect(ox, oy, ow - side_w - 12, oh)
    side = pg.Rect(area.right + 12, oy, side_w, oh)
    pg.draw.rect(screen, (10, 13, 15), area)
    pg.draw.rect(screen, term._theme['panel2'], side)
    pg.draw.rect(screen, term._theme['edge'], area, 1)
    cols, rows, cell, ix, iy = regional_grid(max(1, area.width - 24), max(1, area.height - 60))
    grid = pg.Rect(area.x + 12 + ix, area.y + 44 + iy, cols * cell, rows * cell)
    view = regional_view(sim, cols, rows)
    if term._regional_terrain_assets is None:
        term._regional_terrain_assets = RegionalTerrainAssets(pg)
    cx, cy = view.center

    def rect_for(rx, ry):
        return pg.Rect(grid.x + (rx - cx + cols // 2) * cell,
                       grid.y + (ry - cy + rows // 2) * cell, cell, cell)

    def world_point(x, y, rect):
        return (rect.x + round((x % REGION_SIZE) / REGION_SIZE * cell),
                rect.y + round((y % REGION_SIZE) / REGION_SIZE * cell))

    old_clip = screen.get_clip()
    screen.set_clip(area.inflate(-2, -2))
    try:
        for ry in range(cy - rows // 2, cy + rows // 2 + 1):
            for rx in range(cx - cols // 2, cx + cols // 2 + 1):
                rect = rect_for(rx, ry)
                plan = view.plans.get((rx, ry))
                color = UNKNOWN_COLOR
                if (rx, ry) in view.discovered:
                    color = UNAVAILABLE_COLOR
                pg.draw.rect(screen, color, rect)
                if plan:
                    neighbors = {
                        direction: view.plans.get((rx + dx, ry + dy))
                        for direction, (dx, dy) in NEIGHBOR_OFFSETS.items()
                    }
                    asset = term._regional_terrain_assets.surface(plan, cell, neighbors=neighbors)
                    if asset.get_size() != rect.size:
                        asset = pg.transform.smoothscale(asset, rect.size)
                    screen.blit(asset, rect.topleft)
                pg.draw.rect(screen, (38, 45, 45), rect, 1)
        # These are strategic connections from the Dev5 plan. Exact physical
        # corridors/crossings remain Dev6 work, not invented local geography.
        for water_layer in (True, False):
            for (rx, ry), plan in view.plans.items():
                if plan is None:
                    continue
                rect = rect_for(rx, ry)
                origin = rect.center
                if not water_layer and plan.settlement_anchor:
                    origin = world_point(*plan.settlement_anchor, rect)
                exits = plan.waters if water_layer else plan.roads
                for connection in exits:
                    dx, dy = CARDINALS[connection.direction]
                    if view.plans.get((rx + dx, ry + dy)) is None:
                        continue
                    endpoint = edge_point(rect, connection.direction, connection.offset)
                    width = max(2, min(5, connection.river_class + 1)) if water_layer else (3 if connection.road_class == 'road' else 2)
                    pg.draw.line(screen, WATER_COLOR if water_layer else ROAD_COLOR, origin, endpoint, width)
                    if water_layer:
                        flow_dx, flow_dy = CURRENT_VECTORS.get(getattr(connection, 'current_heading', ''), (0, 0))
                        mid_x = (origin[0] + endpoint[0]) // 2
                        mid_y = (origin[1] + endpoint[1]) // 2
                        arrow_scale = max(5, min(11, 4 + int(getattr(connection, 'current_strength', 0) or 0) // 18))
                        _draw_current_arrow(pg, screen, CURRENT_COLOR, mid_x, mid_y, flow_dx, flow_dy, arrow_scale)
        visited = sim.visited_settlement_ids()
        for town in view.towns:
            rect = rect_for(town.region_x, town.region_y)
            pt = world_point(town.x, town.y, rect)
            pg.draw.circle(screen, (224, 205, 149), pt, 6 if town.uid in visited else 4)
        current_rect = rect_for(cx, cy)
        pg.draw.rect(screen, term._theme['accent'], current_rect.inflate(-4, -4), 2)
        pg.draw.circle(screen, term._theme['accent'], world_point(sim.player_pos.x, sim.player_pos.y, current_rect), 4)
        screen.blit(term.font.render('DISCOVERED REGIONS', True, term._theme['text']), (area.x + 12, area.y + 12))
    finally:
        screen.set_clip(old_clip)

    current = view.plans.get(view.center)
    lines = [('CURRENT REGION', term._theme['accent']), (f'{cx}, {cy}', None),
             ('512 x 512 cells per block', None), ('', None)]
    if current:
        lines += [(current.dominant_biome.replace('_', ' ').title(), None),
                  (', '.join(current.wilderness_tags[:3]) or 'Mixed terrain', None)]
        water_notes=[]
        for entry in getattr(current, 'waters', ())[:3]:
            kind='Coast' if getattr(entry, 'water_kind', 'river')=='ocean' else 'River'
            water_notes.append(f"{kind} {entry.direction}: {getattr(entry,'current_heading','still')} {getattr(entry,'current_strength',0)}")
        if water_notes:
            lines += [('Water currents', term._theme['accent'])] + [(note, None) for note in water_notes]
    else:
        lines += [('Terrain not yet charted', None)]
    for town in view.towns:
        if (town.region_x, town.region_y) == view.center:
            lines += [(town.name, None), ('Visited settlement' if town.uid in visited else 'Known settlement', None)]
    lines += [('', None), ('LEGEND', term._theme['accent']),
              ('Art: biome and climate', None), ('Ridges: rugged relief', None),
              ('Gold line: road / trail', None), ('Blue: rivers / coasts', None),
              ('Cyan arrow: current direction', None), ('Dot: known settlement', None),
              ('Outline: current region', None), ('Dark: undiscovered region', None)]
    if any(plan is None for plan in view.plans.values()):
        lines += [('Gray: terrain not charted', None)]
    if sim.player_pos.z != 0:
        lines += [('Surface above your position', None)]
    # Wrap inside the sidebar and keep the close controls pinned below it.
    import textwrap
    screen.set_clip(side)
    try:
        y = side.y + 16
        char_width = max(1, term.small_font.size('M')[0])
        wrap_width = max(1, (side.width - 20) // char_width)
        step = term.small_font.get_linesize() + 4
        for text, color in lines:
            for fragment in textwrap.wrap(text, wrap_width) or ['']:
                if y + step > side.bottom - 40:
                    break
                screen.blit(term.small_font.render(fragment, True, color or term._theme['text']), (side.x + 10, y))
                y += step
        screen.blit(term.small_font.render('M / Esc / Enter closes map', True, term._theme['muted']),
                    (side.x + 10, side.bottom - 28))
    finally:
        screen.set_clip(old_clip)
    term._button((side.x+10,side.bottom-38,side.width-20,30),'Back to world','ESC')
    pg.display.flip()
