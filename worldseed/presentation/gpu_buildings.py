"""W3 closed exterior shells from detached, cell-authorized physical plans.

These sprites carry no residents, rooms, contents or collision authority. Roofs
remain opaque; an open painted door never admits an interior or grants access.
Only exact currently seen shell cells may receive pixels or a door marker.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import blake2b

from worldseed.systems.building_shells import BuildingShell
from .gl_worldspace import SpriteCommand
from .worldspace import WorldFoot

MAX_PREPARED_BUILDINGS = 64
MAX_BUILDING_CELLS = 1024
MAX_BUILDING_EXTENT = 64
BUILDING_TEXTURE_EDGE = 512


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
        # Door pixels are clipped to the actual threshold even when the source
        # facade's painted recess is taller or a side entrance is selected.
        dx, dy, dz = row.door.cell
        px, py = camera.to_screen(WorldFoot(dx, dy, dz))
        result.append(SpriteCommand('building-door:'+row.door.uid, *art.door,
            bounds, ((px, py, px+camera.scale, py+camera.scale),)))
    return tuple(result)


def load_building_art(materials, row):
    """Fit authored source art once, reusing the legacy pure geometry contract.

    Surfaces here contain one small static building/door, never a composed world
    frame. Their RGBA bytes share the material service's existing bounded LRU.
    """
    from .visuals import VisualRegistry
    from worldseed.systems.building_variants import building_variant
    from worldseed.ui.exterior_view import _door_anchor, _fit_geometry

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
    geometry = (str(path), shell.function, shell.bounds, shell.entrance, shell.footprint)
    digest = blake2b(repr(geometry).encode('utf-8'), digest_size=12).hexdigest()

    def body_loader():
        source = pg.image.load(str(path)) if path is not None else None
        surface = pg.Surface((width, height), pg.SRCALPHA)
        axes, door = _fit_geometry(shell, width, height, source, _door_anchor(function, path))
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
            door_rect = ((dx-left+.2)/columns, (dy-top+.25)/rows, .6/columns, .7/rows)
    return BuildingArt(body, door_source, door_rect)
