"""Mouse-first exact terrain atlas. This module never calls world generation."""
from dataclasses import dataclass
import json
from pathlib import Path
import textwrap

from worldseed.config import CHUNK_SIZE
from worldseed.world.atlas import read_atlas
from worldseed.world.settlement_atlas import build_settlement_atlas

UNKNOWN = (17, 21, 23)


@dataclass
class AtlasControls:
    center: tuple
    span: int = 512
    page: int = 0
    selected: str = ''
    snapshot: object = None
    raster: object = None
    inspected: tuple | None = None
    detail: object = None
    detail_inspected: tuple | None = None
    detail_notice: str = ''


@dataclass(frozen=True)
class SettlementDetailData:
    town: object
    skeleton: object
    snapshot: object


LAND_USE_COLORS = {
    'residential': (70, 76, 68),
    'civic': (96, 80, 55),
    'farm': (67, 88, 57),
    'industrial': (91, 66, 54),
    'pasture': (77, 91, 63),
    'reserve': (55, 62, 58),
}
ROAD_COLOR = (172, 144, 91)
BUILDING_COLOR = (154, 151, 139)
ROOM_COLOR = (103, 112, 105)
ENTRANCE_COLOR = (219, 188, 118)


def _prepared_settlement_skeleton(sim, settlement_id):
    physical = getattr(sim, 'settlement_physicalization', None)
    if physical is not None:
        getter = getattr(physical, 'skeleton_for', None)
        if callable(getter):
            skeleton = getter(settlement_id)
            if skeleton is not None:
                return skeleton
    planner = getattr(sim, 'settlement_planner', None)
    reader = getattr(planner, 'read_prepared', None)
    if callable(reader):
        return reader(settlement_id)
    return None


def read_prepared_settlement_detail(sim, settlement_id):
    """Read one already-prepared settlement plan without generating anything."""
    skeleton = _prepared_settlement_skeleton(sim, settlement_id)
    if skeleton is None:
        return None
    town = getattr(getattr(sim, 'state', None), 'settlements', {}).get(settlement_id)
    if town is None:
        town = next((row for row in sim.known_settlements() if row.uid == settlement_id), None)
    if town is None:
        return None
    snapshot = build_settlement_atlas(
        skeleton.plan,
        roads=skeleton.roads,
        parcels=skeleton.parcels,
        structures=skeleton.structures,
        rooms=skeleton.rooms,
        margin=4,
    )
    return SettlementDetailData(town, skeleton, snapshot)


class AtlasArt:
    def __init__(self, pg):
        self.pg = pg
        root = Path(__file__).resolve().parents[1] / 'assets'
        self.styles = json.loads((root / 'atlas_styles.json').read_text())
        sheet = pg.image.load(str(root / 'atlas_poi.png')).convert_alpha()
        self.icons = {}
        w, h = sheet.get_size()
        for i, kind in enumerate(self.styles['icons']):
            x, y = i % 3, i // 3
            rect = pg.Rect(x*w//3, y*h//3, (x+1)*w//3-x*w//3, (y+1)*h//3-y*h//3)
            icon = sheet.subsurface(rect)
            bounds = icon.get_bounding_rect(min_alpha=16)
            if bounds.width and bounds.height:
                icon = icon.subsurface(bounds)
            self.icons[kind] = pg.transform.smoothscale(icon, (36, 36))

    def color(self, tid, registry):
        if tid in self.styles['terrain']:
            return tuple(self.styles['terrain'][tid])
        definition = registry.terrains.get(tid)
        if definition:
            for tag, color in self.styles['tag_fallback'].items():
                if tag in definition.tags:
                    return tuple(color)
        return tuple(self.styles['fallback'])

    def raster(self, view, registry):
        # At native scale terrain remains exact. At distant LOD, categorical
        # reduction replaces raw color averaging: thin rivers stay coherent
        # without acquiring thick floodplain/riverbank "intestine" halos.
        size = min(512, view.span)
        step = max(1, view.span // size)
        buckets = {}
        palette = {}
        transition_ids = {'core:riverbank','core:floodplain'}
        for key, values in view.chunks.items():
            for i, tid in enumerate(values):
                x = key.x*CHUNK_SIZE+i % CHUNK_SIZE-view.left
                y = key.y*CHUNK_SIZE+i // CHUNK_SIZE-view.top
                if tid is None or not (0 <= x < view.span and 0 <= y < view.span):
                    continue
                pixel=(x//step,y//step)
                buckets.setdefault(pixel,[]).append(tid)
                if tid not in palette:
                    palette[tid]=self.color(tid,registry)

        surface=self.pg.Surface((size,size));surface.fill(UNKNOWN)
        for pixel,tids in buckets.items():
            if step==1:
                chosen=tids[-1]
            else:
                counts={}
                water=[]
                for tid in tids:
                    counts[tid]=counts.get(tid,0)+1
                    definition=registry.terrains.get(tid)
                    if definition and 'water' in definition.tags:
                        water.append(tid)
                if water and len(water)*4>=len(tids):
                    # Water wins once it occupies at least a quarter of the
                    # sample bucket; pick the dominant water class only.
                    wc={}
                    for tid in water:wc[tid]=wc.get(tid,0)+1
                    chosen=max(wc,key=lambda t:(wc[t],t))
                else:
                    # Narrow bank/floodplain ribbons should not dominate a
                    # distant pixel when ordinary land is also present.
                    land=[tid for tid in tids if tid not in transition_ids]
                    pool=land or tids
                    pc={}
                    for tid in pool:pc[tid]=pc.get(tid,0)+1
                    chosen=max(pc,key=lambda t:(pc[t],t))
            surface.set_at(pixel,palette[chosen])
        return surface


def begin_atlas(term, sim):
    term._atlas_controls = AtlasControls((sim.player_pos.x, sim.player_pos.y))
    term._atlas_dragging = False
    term._atlas_drag_moved = False


def atlas_input(term, sim, token):
    state = term._atlas_controls

    if token.startswith('ATLAS_DETAIL_OPEN:'):
        uid = token[len('ATLAS_DETAIL_OPEN:'):]
        detail = read_prepared_settlement_detail(sim, uid)
        if detail is not None:
            state.detail = detail
            state.detail_inspected = None
            state.detail_notice = ''
            term._atlas_dragging = False
        else:
            state.detail_notice = 'Detailed plan is not prepared for this settlement yet.'
        return True
    if token == 'ATLAS_DETAIL_BACK':
        state.detail = None
        state.detail_inspected = None
        state.detail_notice = ''
        return True
    if state.detail is not None:
        if token == 'ATLAS_DETAIL_INSPECT':
            rect = getattr(term, '_settlement_detail_rect', None)
            if rect is None:
                return True
            mx, my = term._last_mouse
            if rect.collidepoint(mx, my):
                snap = state.detail.snapshot
                rx = max(0, min(rect.width - 1, mx - rect.x))
                ry = max(0, min(rect.height - 1, my - rect.y))
                x = snap.left + rx * snap.width // max(1, rect.width)
                y = snap.top + ry * snap.height // max(1, rect.height)
                state.detail_inspected = (min(snap.right, x), min(snap.bottom, y))
            return True
        return token in ('RESIZE','PGUP','PGDN','UP','DOWN','LEFT','RIGHT','HOME')

    if token == 'ATLAS:drag_start':
        term._atlas_dragging=True
        term._atlas_drag_moved=False
        return True
    if token.startswith('ATLAS:drag:'):
        _,_,sx,sy=token.split(':',3)
        dx,dy=int(sx),int(sy)
        rect=term._atlas_rect
        if dx or dy:
            term._atlas_drag_moved=True
            state.center=(
                state.center[0]-dx*state.span//max(1,rect.width),
                state.center[1]-dy*state.span//max(1,rect.height),
            )
            state.snapshot=state.raster=None
            state.inspected=None;state.selected=''
        return True
    if token == 'ATLAS:drag_end':
        term._atlas_dragging=False
        return True
    if token == 'ATLAS_INSPECT':
        rect = term._atlas_rect
        mx, my = term._last_mouse
        if rect.collidepoint(mx, my):
            view = state.snapshot
            state.inspected = (view.left+(mx-rect.x)*view.span//rect.width,
                               view.top+(my-rect.y)*view.span//rect.height)
            state.selected = ''
        return True
    aliases = {'PGUP': 'ATLAS:in', 'PGDN': 'ATLAS:out',
               'UP': 'ATLAS:north', 'DOWN': 'ATLAS:south',
               'LEFT': 'ATLAS:west', 'RIGHT': 'ATLAS:east'}
    token = aliases.get(token, token)
    if token.startswith('ATLAS_POI:'):
        state.selected = token.split(':', 1)[1]
        state.inspected = None
        state.detail_notice = ''
        return True
    if not token.startswith('ATLAS:'):
        return token == 'RESIZE'
    action = token.split(':', 1)[1]
    if action in ('prev', 'next'):
        state.page = max(0, state.page + (-1 if action == 'prev' else 1))
        return True
    if action in ('in', 'out'):
        state.span = max(128, min(2048, state.span//2 if action == 'in' else state.span*2))
    elif action == 'home':
        state.center = (sim.player_pos.x, sim.player_pos.y)
    elif action in ('north', 'south', 'east', 'west'):
        dx, dy = {'north': (0,-1), 'south': (0,1), 'east': (1,0), 'west': (-1,0)}[action]
        state.center = (state.center[0]+dx*state.span//2, state.center[1]+dy*state.span//2)
    else:
        return False
    state.snapshot = state.raster = None
    state.page = 0
    return True



def _humanize(value):
    return str(value or '').replace('_',' ').strip().title()


def _draw_settlement_detail(term, sim, state):
    pg, screen = term.pg, term.screen
    detail = state.detail
    snap = detail.snapshot
    skeleton = detail.skeleton
    town = detail.town

    ox, oy, ow, oh = term._draw_chrome('WORLDSEED // SETTLEMENT MAP')
    term._set_input_mode('ui')
    side_w = max(278, min(336, ow//3))
    map_area = pg.Rect(ox, oy, ow-side_w-12, oh)
    side = pg.Rect(map_area.right+12, oy, side_w, oh)
    pg.draw.rect(screen, (12,15,17), map_area, border_radius=4)
    pg.draw.rect(screen, term._theme['edge'], map_area, 1, border_radius=4)
    pg.draw.rect(screen, term._theme['panel2'], side, border_radius=5)
    pg.draw.rect(screen, term._theme['edge'], side, 1, border_radius=5)

    def fit(text, font, width):
        fn = getattr(term, '_fit_ui_text', None)
        return fn(text, font, width) if callable(fn) else str(text)

    def label(text, x, y, color=None, font=None):
        font = font or term.small_font
        screen.blit(font.render(str(text), True, color or term._theme['text']), (x,y))

    rank = _humanize(getattr(skeleton.plan, 'rank', 'settlement'))
    archetype = _humanize(getattr(skeleton.plan, 'archetype', ''))
    label(fit(town.name, term.title_font, map_area.width-30), map_area.x+14, map_area.y+10,
          term._theme['text'], term.title_font)
    subtitle = f'{rank}  •  {archetype}  •  Population {int(getattr(town, "population", 0))}'
    label(fit(subtitle, term.small_font, map_area.width-30), map_area.x+14, map_area.y+39,
          term._theme['muted'])

    canvas = pg.Rect(map_area.x+14, map_area.y+70, map_area.width-28, map_area.height-104)
    pg.draw.rect(screen, (16,19,20), canvas, border_radius=3)
    pg.draw.rect(screen, term._theme['edge'], canvas, 1, border_radius=3)

    scale = min(
        max(1, canvas.width-16)/max(1, snap.width),
        max(1, canvas.height-16)/max(1, snap.height),
    )
    map_w = max(1, min(canvas.width-16, int(round(snap.width*scale))))
    map_h = max(1, min(canvas.height-16, int(round(snap.height*scale))))
    detail_rect = pg.Rect(
        canvas.centerx-map_w//2,
        canvas.centery-map_h//2,
        map_w,
        map_h,
    )
    term._settlement_detail_rect = detail_rect
    term._ui_target(detail_rect, 'ATLAS_DETAIL_INSPECT')
    pg.draw.rect(screen, (20,24,24), detail_rect)

    def cell_rect(x, y):
        x0 = detail_rect.x + (int(x)-snap.left)*detail_rect.width//max(1,snap.width)
        x1 = detail_rect.x + (int(x)-snap.left+1)*detail_rect.width//max(1,snap.width)
        y0 = detail_rect.y + (int(y)-snap.top)*detail_rect.height//max(1,snap.height)
        y1 = detail_rect.y + (int(y)-snap.top+1)*detail_rect.height//max(1,snap.height)
        return pg.Rect(x0, y0, max(1,x1-x0), max(1,y1-y0))

    for cell in snap.cells.values():
        rect = cell_rect(cell.x, cell.y)
        if cell.land_use:
            pg.draw.rect(screen, LAND_USE_COLORS.get(cell.land_use, LAND_USE_COLORS['reserve']), rect)
        if cell.road_ids:
            inner = rect.inflate(-max(0,rect.width//4), -max(0,rect.height//4))
            if inner.width < 1 or inner.height < 1:
                inner = rect
            pg.draw.rect(screen, ROAD_COLOR, inner)
        if cell.structure_id:
            pg.draw.rect(screen, BUILDING_COLOR, rect)
        if cell.room_id and rect.width >= 4 and rect.height >= 4:
            inner = rect.inflate(-2,-2)
            if inner.width > 0 and inner.height > 0:
                pg.draw.rect(screen, ROOM_COLOR, inner)
        if cell.entrance:
            cx, cy = rect.center
            radius = max(1, min(3, min(rect.width,rect.height)//3))
            pg.draw.circle(screen, ENTRANCE_COLOR, (cx,cy), radius)

    labels_drawn = []
    building_by_uid = {row.uid: row for row in skeleton.structures}
    for kind, name, x, y in snap.labels:
        if kind != 'building':
            continue
        cell = snap.cell_at(x,y)
        structure = building_by_uid.get(cell.structure_id) if cell else None
        if structure is None or structure.function == 'residence':
            continue
        px = detail_rect.x + (x-snap.left)*detail_rect.width//max(1,snap.width)
        py = detail_rect.y + (y-snap.top)*detail_rect.height//max(1,snap.height)
        text = _humanize(structure.function or name)
        surf = term.small_font.render(text, True, (235,231,214))
        rect = surf.get_rect(midbottom=(px,py-3))
        rect.clamp_ip(detail_rect)
        if any(rect.colliderect(old.inflate(5,3)) for old in labels_drawn):
            continue
        shade = rect.inflate(6,4)
        pg.draw.rect(screen, (22,25,24), shade, border_radius=3)
        screen.blit(surf, rect)
        labels_drawn.append(rect)
        if len(labels_drawn) >= 10:
            break

    inspected_cell = None
    if state.detail_inspected is not None:
        ix, iy = state.detail_inspected
        if snap.contains(ix,iy):
            inspected_cell = snap.cell_at(ix,iy)
            pg.draw.rect(screen, term._theme['accent'], cell_rect(ix,iy), 2)
            if inspected_cell and inspected_cell.structure_id:
                selected_rooms = [
                    row for row in skeleton.rooms
                    if row.structure_plan_id == inspected_cell.structure_id and row.cells
                ]
                for room in selected_rooms:
                    xs=[p[0] for p in room.cells];ys=[p[1] for p in room.cells]
                    rx=sum(xs)//len(xs);ry=sum(ys)//len(ys)
                    px=detail_rect.x+(rx-snap.left)*detail_rect.width//max(1,snap.width)
                    py=detail_rect.y+(ry-snap.top)*detail_rect.height//max(1,snap.height)
                    surf=term.small_font.render(_humanize(room.kind),True,(238,235,221))
                    box=surf.get_rect(center=(px,py))
                    box.clamp_ip(detail_rect)
                    bg=box.inflate(6,4)
                    pg.draw.rect(screen,(36,40,38),bg,border_radius=3)
                    screen.blit(surf,box)

    p = sim.player_pos
    if p.z == 0 and snap.contains(p.x,p.y):
        rect = cell_rect(p.x,p.y)
        pg.draw.circle(screen, (245,218,131), rect.center,
                       max(2,min(5,min(rect.width,rect.height)//2)), 2)

    pg.draw.rect(screen, term._theme['edge_hi'], detail_rect, 1)
    label('Click a cell for land use, building and room details.',
          map_area.x+14, map_area.bottom-25, term._theme['muted'])

    sx, sy = side.x+12, side.y+12
    width = side.width-24
    label('OVERVIEW', sx, sy, term._theme['accent'])
    sy += 24

    residences = sum(1 for row in skeleton.structures if row.function == 'residence' and not row.destroyed)
    workplaces = sum(1 for row in skeleton.structures if row.function != 'residence' and not row.destroyed)
    fields = sum(1 for row in skeleton.parcels if row.kind == 'farm')
    rooms = len(skeleton.rooms)
    metrics = (
        ('Homes', str(residences)),
        ('Work buildings', str(workplaces)),
        ('Fields', str(fields)),
        ('Rooms', str(rooms)),
    )
    gap=6; card_w=(width-gap)//2; card_h=48
    for i,(title,value) in enumerate(metrics):
        rect=pg.Rect(sx+(i%2)*(card_w+gap),sy+(i//2)*(card_h+gap),card_w,card_h)
        pg.draw.rect(screen,(34,39,40),rect,border_radius=5)
        pg.draw.rect(screen,term._theme['edge'],rect,1,border_radius=5)
        label(title,rect.x+8,rect.y+5,term._theme['muted'])
        label(value,rect.x+8,rect.y+23,term._theme['text'],term.font)
    sy += card_h*2+gap+16

    label('LAND USE', sx, sy, term._theme['accent'])
    sy += 22
    legend = (
        ('Residential','residential'),('Civic','civic'),
        ('Farms','farm'),('Industrial','industrial'),
    )
    legend_w=(width-gap)//2
    for i,(title,key) in enumerate(legend):
        lx=sx+(i%2)*(legend_w+gap);ly=sy+(i//2)*24
        swatch=pg.Rect(lx,ly+3,13,13)
        pg.draw.rect(screen,LAND_USE_COLORS[key],swatch)
        pg.draw.rect(screen,term._theme['edge_hi'],swatch,1)
        label(title,lx+20,ly,term._theme['muted'])
    sy += 58

    label('INSPECT', sx, sy, term._theme['accent'])
    sy += 22
    inspect_bottom = side.bottom-58
    old_clip = screen.get_clip()
    screen.set_clip(pg.Rect(sx,sy,width,max(1,inspect_bottom-sy)))
    try:
        if state.detail_inspected is None:
            lines=['Select a cell on the plan.']
        else:
            ix,iy=state.detail_inspected
            lines=[f'Cell {ix}, {iy}']
            cell=inspected_cell
            if cell is None:
                lines.append('No planned use.')
            else:
                if cell.land_use:
                    lines.append(f'Land use: {_humanize(cell.land_use)}')
                if cell.parcel_purpose:
                    lines.append(f'Purpose: {_humanize(cell.parcel_purpose)}')
                if cell.road_ids:
                    lines.append('Road access')
                if cell.building_type:
                    lines.append(f'Building: {_humanize(cell.building_type)}')
                if cell.structure_function and _humanize(cell.structure_function) != _humanize(cell.building_type):
                    lines.append(f'Function: {_humanize(cell.structure_function)}')
                if cell.room_kind:
                    lines.append(f'Room: {_humanize(cell.room_kind)}')
                if cell.entrance:
                    lines.append('Entrance')
        line_h=term.small_font.get_linesize()+3
        for i,line in enumerate(lines[:7]):
            label(fit(line,term.small_font,width),sx,sy+i*line_h,
                  term._theme['text'] if i==0 else term._theme['muted'])
    finally:
        screen.set_clip(old_clip)

    term._button((sx,side.bottom-40,width,28),'Back to atlas','ATLAS_DETAIL_BACK')
    pg.display.flip()


def draw_atlas(term, sim):
    pg, screen = term.pg, term.screen
    if screen is None:
        return
    if not hasattr(term, '_atlas_controls'):
        begin_atlas(term, sim)
    state = term._atlas_controls
    if state.detail is not None:
        _draw_settlement_detail(term, sim, state)
        return
    if not hasattr(term, '_atlas_art'):
        term._atlas_art = AtlasArt(pg)
    art = term._atlas_art
    if state.snapshot is None:
        state.snapshot = read_atlas(sim, state.center, state.span)
        state.raster = art.raster(state.snapshot, sim.world.registry)
    view = state.snapshot
    ox, oy, ow, oh = term._draw_chrome('WORLDSEED // TERRAIN ATLAS')
    term._set_input_mode('ui')
    side_w = min(310, ow//3)
    area = pg.Rect(ox, oy, ow-side_w-12, oh)
    side = pg.Rect(area.right+12, oy, side_w, oh)
    pg.draw.rect(screen, term._theme['panel2'], side, border_radius=5)
    size = max(1, min(area.width-16, area.height-116))
    map_rect = pg.Rect(area.centerx-size//2, area.y+36, size, size)
    term._atlas_rect = map_rect
    term._ui_target(map_rect, 'ATLAS_DRAG_ZONE')
    screen.blit(pg.transform.scale(state.raster, map_rect.size), map_rect)
    pg.draw.rect(screen, term._theme['edge_hi'], map_rect, 1)

    def label(text, x, y, color=None):
        screen.blit(term.small_font.render(text, True, color or term._theme['text']), (x,y))

    label(f'SURFACE SURVEY  /  {view.span} x {view.span} cells', area.x+8, area.y+8, term._theme['accent'])
    old_clip = screen.get_clip()
    screen.set_clip(map_rect)
    try:
        # Grid uses exact world boundaries; hidden terrain stays unpainted.
        for x in range((view.left//512+1)*512, view.left+view.span, 512):
            px = map_rect.x+(x-view.left)*size//view.span
            pg.draw.line(screen, (79,87,78), (px,map_rect.top), (px,map_rect.bottom))
        for y in range((view.top//512+1)*512, view.top+view.span, 512):
            py = map_rect.y+(y-view.top)*size//view.span
            pg.draw.line(screen, (79,87,78), (map_rect.left,py), (map_rect.right,py))
        # One visible icon per screen bucket; every POI remains in the pageable
        # list, so dense villages/caves never hide entries from inspection.
        occupied = set()
        for marker in view.markers:
            px = map_rect.x+(marker.x-view.left)*size//view.span
            py = map_rect.y+(marker.y-view.top)*size//view.span
            bucket = (px//30, py//30)
            if bucket in occupied and marker.uid != state.selected:
                continue
            occupied.add(bucket)
            rect = pg.Rect(px-18, py-30, 36, 36)
            rect.clamp_ip(map_rect)
            screen.blit(art.icons.get(marker.kind, art.icons['fortress']), rect)
            pg.draw.circle(screen, term._theme['accent'], (px,py), 2)
            term._ui_target(rect.clip(map_rect), 'ATLAS_POI:'+marker.uid)
            if marker.uid == state.selected:
                pg.draw.rect(screen, term._theme['accent'], rect, 1)
        p = sim.player_pos
        if view.contains(p.x, p.y):
            px = map_rect.x+(p.x-view.left)*size//view.span
            py = map_rect.y+(p.y-view.top)*size//view.span
            pg.draw.circle(screen, (15,20,21), (px,py), 7)
            pg.draw.circle(screen, (245,218,131), (px,py), 5, 2)
            pg.draw.line(screen, (245,218,131), (px-9,py), (px+9,py))
            pg.draw.line(screen, (245,218,131), (px,py-9), (px,py+9))
    finally:
        screen.set_clip(old_clip)
    # Mouse-first navigation: drag the map, wheel to zoom. Keep only a small
    # recenter affordance instead of seven directional buttons.
    label('Drag map  •  Mouse wheel zooms  •  Click to inspect', area.x+8, map_rect.bottom+12, term._theme['muted'])
    term._button((area.right-170,map_rect.bottom+8,160,28),'Center on player','ATLAS:home')

    sx, sy = side.x+12, side.y+12
    width = side.width-24
    label('KNOWN PLACES', sx, sy, term._theme['accent'])
    label(f'Center: {state.center[0]}, {state.center[1]}', sx, sy+24)
    label('Drag: pan  |  Wheel: zoom', sx, sy+46, term._theme['muted'])
    line_h = term.small_font.get_linesize()+3
    capacity = max(1, (side.height-280)//44)
    pages = max(1, (len(view.markers)+capacity-1)//capacity)
    state.page = min(state.page, pages-1)
    start = state.page*capacity
    y = sy+76
    for marker in view.markers[start:start+capacity]:
        term._button((sx+40,y,width-40,40), marker.name, 'ATLAS_POI:'+marker.uid)
        screen.blit(art.icons.get(marker.kind,art.icons['fortress']), (sx+2,y+2))
        term._ui_target((sx,y,40,40), 'ATLAS_POI:'+marker.uid)
        y += 44
    if not view.markers:
        label('No known places in this view.', sx, y, term._theme['muted'])
    by = side.bottom-196
    term._button((sx,by,width//2-3,28), f'Prev {state.page+1}/{pages}', 'ATLAS:prev')
    term._button((sx+width//2+3,by,width//2-3,28), 'Next', 'ATLAS:next')
    selected = next((m for m in view.markers if m.uid == state.selected), None)
    details = (f'{"Approx. " if selected.z else ""}{selected.x}, {selected.y}, z={selected.z} | {selected.kind.title()}. {selected.name}: {selected.detail}' if selected else
               'Terrain uses local tiles. Dark areas: uncharted or not prepared. Crosshair: you. Icons: known places.')
    if state.inspected:
        x, y = state.inspected
        tid = view.terrain_at(x,y)
        definition = sim.world.registry.terrains.get(tid)
        details = f'{x}, {y}: {definition.name if definition else (tid or "Uncharted / not prepared")}. Click terrain to inspect exact cells.'
    screen.set_clip(pg.Rect(sx,by+36,width,70))
    try:
        for i, line in enumerate(textwrap.wrap(details, max(12,width//max(1,term.small_font.size('M')[0])))):
            label(line, sx, by+36+i*line_h, term._theme['muted'])
    finally:
        screen.set_clip(old_clip)

    if selected and selected.kind in ('village','city'):
        prepared = _prepared_settlement_skeleton(sim, selected.uid)
        if prepared is not None:
            term._button((sx,side.bottom-74,width,28),'Open settlement plan',
                         'ATLAS_DETAIL_OPEN:'+selected.uid)
        else:
            label('Detailed plan not prepared.', sx, side.bottom-70, term._theme['muted'])
    elif state.detail_notice:
        label(state.detail_notice, sx, side.bottom-70, term._theme['muted'])
    term._button((sx,side.bottom-38,width,28), 'Back to world', 'ESC')
    pg.display.flip()
