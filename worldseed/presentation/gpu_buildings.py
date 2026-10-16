"""W3 closed exterior shells from detached, cell-authorized physical plans.

These sprites carry no residents, rooms, contents or collision authority. Roofs
remain opaque; an open painted door never admits an interior or grants access.
Only exact currently seen shell cells may receive pixels or a door marker.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import blake2b
from math import ceil, floor

from worldseed.systems.building_shells import BuildingShell
from .gl_worldspace import SpriteCommand
from .worldspace import WorldFoot

MAX_PREPARED_BUILDINGS = 64
MAX_BUILDING_CELLS = 1024
MAX_BUILDING_EXTENT = 64
BUILDING_TEXTURE_EDGE = 512
BUILDING_FIT_REVISION = 2


@dataclass(frozen=True, slots=True)
class PreparedBuildingDoor:
    uid: str
    cell: tuple[int, int, int]
    opened: bool = False

    def __post_init__(self):
        if (not self.uid or not isinstance(self.cell, tuple) or len(self.cell) != 3
                or any(type(v) is not int for v in self.cell)
                or type(self.opened) is not bool):
            raise ValueError('explicit detached building door required')


@dataclass(frozen=True, slots=True)
class PreparedBuildingShell:
    shell: BuildingShell
    visible_cells: frozenset[tuple[int, int, int]]
    variant_id: str = ''
    door: PreparedBuildingDoor | None = None

    def __post_init__(self):
        shell = self.shell
        if not isinstance(shell, BuildingShell) or not shell.uid:
            raise ValueError('authoritative exterior shell required')
        left, top, right, bottom = shell.bounds
        if (not 0 < len(shell.footprint) <= MAX_BUILDING_CELLS
                or not 0 < right-left+1 <= MAX_BUILDING_EXTENT
                or not 0 < bottom-top+1 <= MAX_BUILDING_EXTENT):
            raise ValueError('building exceeds bounded exterior geometry')
        if (not isinstance(self.visible_cells, frozenset)
                or not self.visible_cells
                or not self.visible_cells <= frozenset((x, y, 0) for x, y in shell.footprint)):
            raise ValueError('building sight must use exact physical exterior cells')
        if self.door is not None and (self.door.cell not in self.visible_cells
                or self.door.uid != shell.door_uid
                or self.door.cell[:2] != shell.entrance):
            raise ValueError('building door requires its currently seen physical threshold')


@dataclass(frozen=True, slots=True)
class BuildingArt:
    """Small immutable source textures and normalized facade-door placement."""
    body: tuple
    door: tuple | None
    door_rect: tuple[float, float, float, float]


def _fit_building_geometry(shell, width, height, source, anchor):
    """Fit a facade to physical cells with a consistent human-sized doorway.

    Export padding and the source painter's door size are not world units.
    Nine source bands keep the recess and leaf together while fixing the
    facade opening to a human-sized threshold. Roof/body pixels still cover
    the immutable physical extent; no saved plan or collider is resized.
    """
    if source is None:
        sw = sh = 1000
        left, top, right, bottom = 0, 0, sw, sh
    else:
        sw, sh = source.get_size()
        box = source.get_bounding_rect(16)
        left, top, right, bottom = ((box.left, box.top, box.right, box.bottom)
            if box.width and box.height else (0, 0, sw, sh))
    ax, ay, aw, ah = anchor
    # A tiny source/fallback still has a valid full-body mapping.
    if min(right-left, bottom-top, width, height) < 4:
        return ((left, right), (top, bottom), (0, width), (0, height)), (0, 0, width, height)
    sx0 = max(left+1, min(right-2, round(ax*sw/1000)))
    sx1 = max(sx0+1, min(right-1, round((ax+aw)*sw/1000)))
    sy0 = max(top+1, min(bottom-2, round(ay*sh/1000)))
    sy1 = max(sy0+1, min(bottom-1, round((ay+ah)*sh/1000)))
    columns, rows = shell.bounds[2]-shell.bounds[0]+1, shell.bounds[3]-shell.bounds[1]+1
    cell_w, cell_h = width/columns, height/rows
    if shell.entrance is not None and shell.door_side == 'south':
        center = (shell.entrance[0]-shell.bounds[0]+.5)*cell_w
        baseline = (shell.entrance[1]-shell.bounds[1]+1-.08)*cell_h
    else:
        center, baseline = width/2, height-.08*cell_h
    # Visible player art is about 1.45 world cells tall. The opening must admit
    # that visual scale even though its authoritative entrance is one cell.
    target_h = max(2, min(round(1.55*cell_h), height-2))
    target_w = max(2, min(round(.72*cell_w), width-2))
    tx0 = max(1, min(width-target_w-1, round(center-target_w/2)))
    ty1 = max(target_h+1, min(height-1, round(baseline)))
    ty0 = ty1-target_h
    return ((left, sx0, sx1, right), (top, sy0, sy1, bottom),
            (0, tx0, tx0+target_w, width), (0, ty0, ty1, height)), (tx0, ty0, target_w, target_h)


@dataclass(frozen=True, slots=True)
class _PaintedBuildingMask:
    """Lazy pointer-only sample of the exact command, without a screen bitmap."""
    command: SpriteCommand
    origin: tuple[int, int]

    def get_at(self, point):
        command = self.command
        px, py = self.origin[0]+point[0], self.origin[1]+point[1]
        x, y = px+.5, py+.5
        x0, y0, x1, y1 = command.bounds
        if not x0 <= x < x1 or not y0 <= y < y1:
            return 0
        # Match pixel_clip's fragment-center admission exactly. Rounding both
        # edges inward would leave painted fractional boundary pixels unclickable.
        if not any(a <= x < c and b <= y < d
                   for a, b, c, d in command.clip_rects):
            return 0
        # GL uses clamped bilinear filtering. Sample that same source alpha,
        # so transparent roof corners never become rectangular click targets.
        u = (x-x0)*command.image_w/(x1-x0)-.5
        v = (y-y0)*command.image_h/(y1-y0)-.5
        ix, iy = floor(u), floor(v)
        fx, fy = u-ix, v-iy
        def alpha(tx, ty):
            tx = max(0, min(command.image_w-1, tx))
            ty = max(0, min(command.image_h-1, ty))
            return command.rgba[(ty*command.image_w+tx)*4+3]
        above = alpha(ix, iy)*(1-fx)+alpha(ix+1, iy)*fx
        below = alpha(ix, iy+1)*(1-fx)+alpha(ix+1, iy+1)*fx
        return int(((1-fy)*above+fy*below)*command.opacity >= 16)


def building_hit_regions(buildings, commands, pg, viewport):
    """Use already drawn, sight-clipped pixels for exterior pointer admission.

    Shared shell_at_pointer gives door regions priority. Rectangles accelerate
    the query only; their source alpha and exact sight clips decide the hit.
    This reads no world state and does not create physical collision geometry.
    """
    if len(buildings) > MAX_PREPARED_BUILDINGS:
        raise ValueError('GPU building budget exceeded')
    shells = {'building:'+row.shell.uid: (row.shell, 'body') for row in buildings}
    shells.update({'building-door:'+row.door.uid: (row.shell, 'door')
                   for row in buildings if row.door is not None})
    regions = []
    for command in commands:
        entry = shells.get(command.visual_id)
        if entry is None:
            continue
        shell, kind = entry
        x0, y0, x1, y1 = command.bounds
        rect = pg.Rect(floor(x0), floor(y0), ceil(x1)-floor(x0), ceil(y1)-floor(y0)).clip(viewport)
        if not rect.width or not rect.height:
            continue
        regions.append({'kind': kind, 'rect': rect, 'shell': shell,
            'target': shell.entrance if kind == 'door' else None,
            'mask': _PaintedBuildingMask(command, rect.topleft)})
    return regions


def building_sort_keys(buildings):
    """Keys compatible with worldspace.visual_sort_key's grounded depth plane."""
    result = {}
    for row in buildings:
        left, _top, right, bottom = row.shell.bounds
        key = (30, bottom+1., 0., (left+right+1)/2., 30)
        result['building:'+row.shell.uid] = (*key, 'building:'+row.shell.uid)
        # Keep independent door art immediately above its closed shell.
        result['building-door:'+row.shell.door_uid] = (*key, 'building:'+row.shell.uid+'~door')
    return result


def _art(materials, row):
    supplied = getattr(materials, 'building', None)
    return supplied(row) if supplied is not None else load_building_art(materials, row)


def building_commands(buildings, camera, materials):
    """Project only public exteriors; drawing cannot ask the simulation for data."""
    if len(buildings) > MAX_PREPARED_BUILDINGS:
        raise ValueError('GPU building budget exceeded')
    result = []
    for row in sorted(buildings, key=lambda r: (r.shell.bounds[3], r.shell.bounds[0], r.shell.uid)):
        if camera.center.z != 0:
            continue
        art = _art(materials, row)
        left, top, right, bottom = row.shell.bounds
        x0, y0 = camera.to_screen(WorldFoot(left, top, 0))
        x1, y1 = camera.to_screen(WorldFoot(right+1, bottom+1, 0))
        clips = []
        for x, y, z in sorted(row.visible_cells, key=lambda c: (c[1], c[0])):
            px, py = camera.to_screen(WorldFoot(x, y, z))
            if px+camera.scale > 0 and py+camera.scale > 0 and px < camera.width_px and py < camera.height_px:
                clips.append((px, py, px+camera.scale, py+camera.scale))
        if not clips:
            continue
        result.append(SpriteCommand('building:'+row.shell.uid, *art.body,
                                    (x0, y0, x1, y1), tuple(clips)))
        if row.door is None or art.door is None:
            continue
        rx, ry, rw, rh = art.door_rect
        bounds = (x0+rx*(x1-x0), y0+ry*(y1-y0),
                  x0+(rx+rw)*(x1-x0), y0+(ry+rh)*(y1-y0))
        # A human-sized upright leaf can extend above its physical threshold.
        # Admit it only through currently seen occupied shell cells, never a
        # roof bounding box or a remembered/hidden neighboring cell. Door state
        # itself was copied only when the exact physical threshold was seen.
        door_clips = tuple(rect for rect in clips if rect[0] < bounds[2]
            and rect[2] > bounds[0] and rect[1] < bounds[3] and rect[3] > bounds[1])
        result.append(SpriteCommand('building-door:'+row.door.uid, *art.door,
            bounds, door_clips))
    return tuple(result)


def load_building_art(materials, row):
    """Fit authored source art once to the GPU's uniform physical-cell scale.

    Surfaces here contain one small static building/door, never a composed world
    frame. Their RGBA bytes share the material service's existing bounded LRU.
    """
    from .visuals import VisualRegistry
    from worldseed.systems.building_variants import building_variant
    from worldseed.ui.exterior_view import _door_anchor

    if materials._visuals is None:
        materials._visuals = VisualRegistry.load_default()
    visuals, pg, shell = materials._visuals, materials.pg, row.shell
    variant = building_variant(shell, variant_id=row.variant_id)
    names = ((variant['id'], variant['asset']) if variant else ()) + (shell.function, 'core:'+shell.function)
    path = None
    function = shell.function
    for name in names:
        ref = visuals.ref('building_shells', name)
        if ref.paths:
            function, path = name, visuals.resolve(ref)
            break
    left, top, right, bottom = shell.bounds
    columns, rows = right-left+1, bottom-top+1
    scale = min(48., BUILDING_TEXTURE_EDGE/max(columns, rows))
    width, height = max(2, round(columns*scale)), max(3, round(rows*scale))
    geometry = (BUILDING_FIT_REVISION, str(path), shell.function, shell.bounds, shell.entrance, shell.footprint)
    digest = blake2b(repr(geometry).encode('utf-8'), digest_size=12).hexdigest()

    def body_loader():
        source = pg.image.load(str(path)) if path is not None else None
        surface = pg.Surface((width, height), pg.SRCALPHA)
        axes, door = _fit_building_geometry(shell, width, height, source, _door_anchor(function, path))
        if source is None:
            # Missing art still closes the physical shell, with no private label.
            surface.fill((98, 73, 49, 255))
            pg.draw.rect(surface, (161, 128, 83, 255), surface.get_rect(), max(1, width//40))
        else:
            sx, sy, tx, ty = axes
            for yi in range(len(sy)-1):
                for xi in range(len(sx)-1):
                    src = pg.Rect(sx[xi], sy[yi], sx[xi+1]-sx[xi], sy[yi+1]-sy[yi])
                    dst = pg.Rect(tx[xi], ty[yi], tx[xi+1]-tx[xi], ty[yi+1]-ty[yi])
                    if src.width and src.height and dst.width and dst.height:
                        surface.blit(pg.transform.smoothscale(source.subsurface(src), dst.size), dst.topleft)
        # Keep courtyards/walkable cutouts transparent without creating geometry.
        occupied = set(shell.footprint)
        for gy in range(rows):
            for gx in range(columns):
                if (left+gx, top+gy) not in occupied:
                    a, b = gx*width//columns, (gx+1)*width//columns
                    c, d = gy*height//rows, (gy+1)*height//rows
                    surface.fill((0, 0, 0, 0), (a, c, b-a, d-c))
        rect = tuple(value/size for value, size in zip(door, (width, height, width, height)))
        return (('gpu:building:'+digest, 1, pg.image.tobytes(surface, 'RGBA'), width, height), rect)

    body, door_rect = materials._read(('gpu-building', digest), body_loader)
    door_source = None
    if row.door is not None:
        material = 'iron' if shell.function in {'barracks', 'watchtower', 'watchhouse', 'guardhouse', 'fortress'} else 'wood'
        if row.door.opened and material == 'wood' and visuals.ref('building_doors', 'wood_open').paths:
            material = 'wood_open'
        door_path = visuals.resolve(visuals.ref('building_doors', material))
        def door_loader():
            if door_path is None:
                surf = pg.Surface((12, 20), pg.SRCALPHA)
                surf.fill((176, 131, 73, 255))
            else:
                surf = pg.image.load(str(door_path))
                bounds = surf.get_bounding_rect(16)
                if bounds.width and bounds.height:
                    surf = surf.subsurface(bounds)
                factor = min(1., 128/max(surf.get_size()))
                if factor < 1:
                    surf = pg.transform.smoothscale(surf, (max(1, round(surf.get_width()*factor)), max(1, round(surf.get_height()*factor))))
            return ('gpu:building-door:'+material, 1, pg.image.tobytes(surf, 'RGBA'), *surf.get_size())
        door_source = materials._read(('gpu-building-door', str(door_path), material), door_loader)
        if shell.door_side != 'south':
            dx, dy = shell.entrance
            door_rect = ((dx-left+.26)/columns, (dy-top+.10)/rows, .48/columns, .82/rows)
    return BuildingArt(body, door_source, door_rect)
