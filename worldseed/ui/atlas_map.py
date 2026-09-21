"""Mouse-first exact terrain atlas. This module never calls world generation."""
from dataclasses import dataclass
import json
from pathlib import Path
import textwrap

from worldseed.config import CHUNK_SIZE
from worldseed.world.atlas import read_atlas

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


def draw_atlas(term, sim):
    pg, screen = term.pg, term.screen
    if screen is None:
        return
    if not hasattr(term, '_atlas_controls'):
        begin_atlas(term, sim)
    state = term._atlas_controls
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
    capacity = max(1, (side.height-245)//44)
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
    by = side.bottom-158
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
    screen.set_clip(pg.Rect(sx,by+36,width,76))
    try:
        for i, line in enumerate(textwrap.wrap(details, max(12,width//max(1,term.small_font.size('M')[0])))):
            label(line, sx, by+36+i*line_h, term._theme['muted'])
    finally:
        screen.set_clip(old_clip)
    term._button((sx,side.bottom-38,width,28), 'Back to world', 'ESC')
    pg.display.flip()
