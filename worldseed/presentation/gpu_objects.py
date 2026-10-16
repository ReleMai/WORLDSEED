"""Detached, bounded live-object art for the primary GPU scene.

Capture reads prepared local state only. The caller supplies the exact cells
admitted by sight, floor and privacy authority; discovery memory never admits
live objects. These records carry no inventory contents, owner names or locks,
and create neither gameplay targets nor collision.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from worldseed.core.coords import WorldPos
from worldseed.systems.state import pos_key
from .worldspace import VisualLayer, WorldFoot, WorldVisualInstance

MAX_PREPARED_OBJECTS = 1024
MAX_OBJECT_VIEW_CELLS = 8192


def gpu_resource_style(content_id, definition=None, visuals=None):
    """Human-relative GPU art sizes, independent of harvest/collision authority.

    The legacy catalog includes illustrative cache icons rather than measured
    object sizes. Preserve its atlas metadata while fitting loose materials
    below knee height and vegetation by its existing content tags. A mod may
    supply explicit ``gpu_width`` / ``gpu_height`` art dimensions.
    """
    if visuals is None:
        from .visuals import VisualRegistry
        visuals = VisualRegistry.load_default()
    style = dict(visuals.resource_style(content_id))
    tags = set(getattr(definition, 'tags', ()))
    if 'tree' in tags:
        width, height = (1.05, 2.8) if 'conifer' in tags else (1.15, 2.45)
    elif 'natural_container' in tags:
        width, height = (.90, .65) if 'rock_cache' not in tags else (.75, .48)
    elif 'branch' in tags:
        width, height = .72, .48
    elif 'rock' in tags or 'stone' in tags:
        width, height = ((.95, 1.05) if getattr(definition, 'blocks_movement', False)
                         else (.46, .38))
    elif 'bush' in tags:
        width, height = .85, 1.05
    elif 'mushroom' in tags or 'bait' in tags:
        width, height = .55, .38
    elif 'grain' in tags or 'wetland' in tags:
        width, height = .78, 1.0
    elif 'soil' in tags or 'clay' in tags:
        width, height = .85, .28
    else:
        width, height = .70, .66
    style['width'] = style.get('gpu_width', width)
    style['height'] = style.get('gpu_height', height)
    return style


def object_geometry(kind, *, ground=False):
    """Shared live/last-seen art geometry; never a physical collider."""
    if kind == 'roof': return 1., 1., VisualLayer.OVERHEAD
    if ground: return 1., 1., VisualLayer.LOW_DETAIL
    width, height = {
        'pile': (.45, .30), 'crop': (.70, .80),
        'container': (.80, .62), 'carcass': (1., .55),
        'sign': (.65, .24), 'home': (.65, .24),
        'settlement_piece': (.95, 1.),
    }.get(kind, (1.1, 1.1))
    return width, height, VisualLayer.GROUNDED


@dataclass(frozen=True, slots=True)
class PreparedObject:
    uid: str
    kind: str
    content_id: str
    foot: WorldFoot
    width: float = 1.25
    height: float = 1.25
    layer: VisualLayer = VisualLayer.GROUNDED
    variant: int = 0
    category: str = ''
    material: str = ''
    tags: tuple[str, ...] = ()

    def __post_init__(self):
        if (not self.uid or not self.kind or not self.content_id
                or not isinstance(self.foot, WorldFoot)
                or not isinstance(self.tags, tuple)
                or type(self.variant) is not int):
            raise ValueError('detached explicit object identity required')
        # Reuse the renderer's finite geometry validation; never physical cells.
        self.instance()

    def instance(self):
        return WorldVisualInstance('object:'+self.uid, self.content_id, self.foot,
            self.width, self.height, self.height, self.layer)


def _bounds(camera):
    from .gpu_scene_bridge import cell_bounds
    return cell_bounds(camera)


def capture_roofs(sim, camera, visible_cells):
    """Copy opaque public roof art without admitting any underlying cell.

    ``visible_cells`` is the bounded viewport's exact currently visible xyz
    tuples. The live producer keeps these separate from floor/prop admission.
    """
    if len(visible_cells) > MAX_OBJECT_VIEW_CELLS:
        raise ValueError('GPU roof sight exceeds bounded cell budget')
    left, top, right, bottom = _bounds(camera)
    rows = []
    for x, y, z in sorted(visible_cells, key=lambda c: (c[2], c[1], c[0])):
        if z != camera.center.z or not (left <= x < right and top <= y < bottom):
            continue
        roof = sim.state.roofs.get(pos_key(x, y, z))
        if roof is None or roof.condition <= 0:
            continue
        if len(rows) >= MAX_PREPARED_OBJECTS:
            raise ValueError('GPU prepared roof budget exceeded')
        rows.append(PreparedObject(f'roof:{z}:{x}:{y}', 'roof', str(roof.structure_id),
                    WorldFoot(x+.5, y+.999, z), 1., 1., VisualLayer.OVERHEAD))
    return tuple(rows)


def capture_objects(sim, current_cells, camera):
    """Copy authorized resident props with exact cell and local bucket reads.

    No fallback scans are permitted when an optional collection lacks its
    simulation-maintained spatial index. Player roofs are included only when
    the caller separately admits their public exterior cells. Roofed contents
    are always suppressed by this producer as an additional privacy guard.
    """
    if len(current_cells) > MAX_OBJECT_VIEW_CELLS:
        raise ValueError('GPU object sight exceeds bounded cell budget')
    left, top, right, bottom = _bounds(camera)
    z = camera.center.z
    admitted = frozenset(cell for cell in current_cells
                        if cell[2] == z and left <= cell[0] < right and top <= cell[1] < bottom)
    rows = []
    public_cells = set(admitted)

    def add(row):
        if len(rows) >= MAX_PREPARED_OBJECTS:
            raise ValueError('GPU prepared object budget exceeded')
        rows.append(row)

    def placed(kind, content, cell, *, uid=None, **kwargs):
        x, y, rz = cell
        width, height, layer = object_geometry(kind,
            ground=kwargs.get('layer') is VisualLayer.LOW_DETAIL)
        kwargs.update(width=width, height=height, layer=layer)
        add(PreparedObject(uid or f'{kind}:{rz}:{x}:{y}', kind, str(content),
                           WorldFoot(x+.5, y+.999, rz), **kwargs))

    for cell in sorted(admitted, key=lambda c: (c[2], c[1], c[0])):
        token = pos_key(*cell)
        roof = sim.state.roofs.get(token)
        if roof is not None and roof.condition > 0:
            placed('roof', roof.structure_id, cell, width=1., height=1., layer=VisualLayer.OVERHEAD)
            public_cells.discard(cell)
            continue
        if z == 0:
            physical = sim.settlement_physicalization.cell_at(WorldPos(*cell))
            if physical is not None:
                # An admitted public shell exterior never authorizes room props.
                closed = bool(physical.room_id or physical.roof_piece_id)
                for slot in ('ground_piece_id', 'structure_piece_id', 'fixture_piece_id'):
                    if closed and (slot != 'structure_piece_id'
                            or physical.structure_piece_role in {'partition', 'interior_door'}):
                        continue
                    piece_id = getattr(physical, slot)
                    piece = sim.registry.settlement_pieces.get(piece_id)
                    if piece is None:
                        continue
                    ground = piece.category in {'floor', 'road'} or piece.layer == 'ground'
                    placed('settlement_piece', piece_id, cell, uid=f'piece:{slot}:{token}',
                        width=1. if ground else .95, height=1. if ground else 1.,
                        layer=VisualLayer.LOW_DETAIL if ground else VisualLayer.GROUNDED,
                        category=piece.category, material=piece.material,
                        tags=tuple(sorted(set(piece.tags) | set(piece.room_tags))))
                if closed:
                    public_cells.discard(cell)
                    continue
        structure = sim.state.structures.get(token)
        if structure is not None and structure.condition > 0:
            definition = sim.registry.structures.get(structure.structure_id)
            tags = tuple(getattr(definition, 'tags', ()))
            ground = bool(set(tags) & {'floor', 'bridge'})
            placed('structure', structure.structure_id, cell,
                    width=1. if ground else 1.25, height=1. if ground else 1.25,
                    layer=VisualLayer.LOW_DETAIL if ground else VisualLayer.GROUNDED)
        container = sim.state.containers.get(token)
        if (container is not None and container.condition > 0
                and not container.interior_space_id and structure is None):
            # Only the vessel's external art identity is copied, never goods.
            placed('container', container.source_id or 'core:wood_chest', cell,
                uid='container:'+container.uid, category=str(container.profile_id),
                width=1.15, height=.95)
        pile = sim.state.ground_piles.get(token)
        if pile is not None and pile.items:
            # One visible item is enough to communicate a loose pile. Preserve
            # insertion order without sorting/copying a potentially huge stash.
            first = next((item for item, amount in pile.items.items() if amount > 0), None)
            if first is not None:
                placed('pile', first, cell, width=.7, height=.6)
        crop = sim.state.crops.get(token)
        if crop is not None and crop.health > 0:
            placed('crop', crop.crop_id, cell,
                variant=2 if crop.mature else (1 if crop.growth >= 45 else 0),
                width=1.1, height=1.1)

    # UID-keyed records cannot be found with a tile .get. The prepared spatial
    # maps are the only supported source; plain test dictionaries fail closed.
    hunt_skill = max(sim.player_skill('hunting'), sim.player_skill('survival'))
    for collection, kind in (('carcasses', 'carcass'), ('animal_signs', 'sign'), ('animal_homes', 'home')):
        query = getattr(getattr(sim.state, collection), 'near_rect', None)
        if not callable(query):
            continue
        for value in query(left, top, right-1, bottom-1, z):
            cell = (value.x, value.y, value.z)
            if cell not in public_cells:
                continue
            roof = sim.state.roofs.get(pos_key(*cell))
            if roof is not None and roof.condition > 0:
                continue
            if kind == 'home' and not value.discovered:
                continue
            if kind == 'sign' and value.strength+hunt_skill*8 < 52:
                continue
            content = value.kind if kind in {'home', 'sign'} else value.species_id
            placed(kind, content, cell, uid=kind+':'+value.uid,
                width=.75 if kind != 'carcass' else 1.,
                height=.3 if kind != 'carcass' else .55)
    return tuple(rows)


def object_instances(objects):
    if len(objects) > MAX_PREPARED_OBJECTS:
        raise ValueError('GPU prepared object budget exceeded')
    if any(not isinstance(row, PreparedObject) for row in objects):
        raise ValueError('GPU object projection needs detached rows')
    return tuple(row.instance() for row in objects)


def _visuals(materials):
    from .visuals import VisualRegistry
    catalog = getattr(materials, '_visuals', None)
    if catalog is None:
        catalog = VisualRegistry.load_default()
        # Production caches the immutable catalog; lightweight test services
        # need only their asset method and may use slots.
        if hasattr(materials, '_visuals'):
            materials._visuals = catalog
    return catalog


def _piece(row):
    return SimpleNamespace(id=row.content_id, category=row.category, material=row.material,
                           tags=row.tags, room_tags=(), layer='ground' if row.layer is VisualLayer.LOW_DETAIL else 'structure')


def object_source(materials, row):
    """Resolve existing game artwork without any simulation reference."""
    visuals = _visuals(materials)
    if row.kind == 'settlement_piece':
        # Share authored legacy fixture art and pure yard drawing. The tiny
        # source surface is one static prop, never a composed world frame.
        from worldseed.ui.pygame_terminal import PygameTerminal
        piece = _piece(row)
        yard_tags = {'clutter', 'yard', 'trade_sign', 'well', 'woodpile', 'ore_pile',
                     'coal_bin', 'haystack', 'grain_sacks', 'barrel', 'smoke_rack', 'chopping_block'}
        if (yard_tags.intersection(row.tags) and hasattr(materials, 'pg')
                and hasattr(materials, '_read')):
            def load():
                pg = materials.pg
                surface = pg.Surface((96, 96), pg.SRCALPHA)
                painter = SimpleNamespace(pg=pg, screen=surface)
                if PygameTerminal._draw_settlement_yard_piece(painter, piece, surface.get_rect()):
                    return ('gpu:yard:'+row.content_id, 1, pg.image.tobytes(surface, 'RGBA'), 96, 96)
                return None
            yard = materials._read(('gpu-yard', row.content_id), load)
            if yard is not None:
                return yard
        resolver = SimpleNamespace(_visuals=visuals)
        path = (visuals.settlement_material_path(row.category, row.material, row.tags, row.content_id)
                or PygameTerminal._settlement_piece_sprite_path(resolver, piece))
    elif row.kind in {'structure', 'roof'}:
        path = visuals.resolve(visuals.ref('structures', row.content_id))
    elif row.kind == 'container':
        path = (visuals.resolve(visuals.ref('containers', row.category))
                or visuals.resolve(visuals.ref('structures', row.content_id)))
    elif row.kind in {'pile', 'crop', 'carcass'}:
        table = {'pile': 'items', 'crop': 'crops', 'carcass': 'species'}[row.kind]
        path = visuals.resolve(visuals.ref(table, row.content_id), row.variant)
    elif row.kind in {'sign', 'home'}:
        return _marker_source(materials, row)
    else:
        return None
    path = path or visuals.special('unknown')
    return materials.asset(path) if path is not None else None


def _marker_source(materials, row):
    if not hasattr(materials, 'pg') or not hasattr(materials, '_read'):
        return None
    def load():
        pg = materials.pg
        surface = pg.Surface((64, 32), pg.SRCALPHA)
        if row.kind == 'home':
            pg.draw.ellipse(surface, (24, 20, 17), (7, 10, 50, 18))
            pg.draw.arc(surface, (103, 82, 58), (4, 2, 56, 28), 0., 3.14159, 4)
        else:
            color = (145, 55, 47) if row.content_id == 'blood' else (174, 145, 99)
            pg.draw.ellipse(surface, color, (5, 5, 20, 8))
            pg.draw.ellipse(surface, color, (32, 16, 20, 8))
        return ('gpu:'+row.kind+':'+row.content_id, 1, pg.image.tobytes(surface, 'RGBA'), 64, 32)
    return materials._read(('gpu-marker', row.kind, row.content_id), load)


def resource_source(materials, instance):
    """Non-layered resource art, including the existing natural-cache atlas."""
    visuals = _visuals(materials)
    x, y, _z = instance.foot.cell
    variant = ((x*73856093) ^ (y*19349663)) & 0x7fffffff
    style = visuals.resource_style(instance.content_id)
    atlas = visuals.resource_atlas_path(instance.content_id)
    if atlas is not None and hasattr(materials, 'pg') and hasattr(materials, '_read'):
        columns, size, row = (int(style.get('atlas_columns', 1)), int(style.get('atlas_frame', 128)), int(style.get('atlas_row', 0)))
        if not (1 <= columns <= 64 and 1 <= size <= 512 and 0 <= row < 64):
            raise ValueError('resource atlas exceeds bounded art metadata')
        variant %= min(columns, max(1, int(style.get('variants', columns))))
        def load():
            pg = materials.pg
            source = pg.image.load(str(atlas))
            rect = pg.Rect(variant*size, row*size, size, size)
            if not source.get_rect().contains(rect):
                raise ValueError('resource atlas frame outside source image')
            surface = source.subsurface(rect)
            return (f'gpu:resource:{instance.content_id}:{variant}', 1,
                    pg.image.tobytes(surface, 'RGBA'), size, size)
        return materials._read(('gpu-resource', instance.content_id, variant), load)
    path = visuals.resolve(visuals.ref('resources', instance.content_id), variant) or visuals.special('unknown')
    return materials.asset(path) if path is not None else None
