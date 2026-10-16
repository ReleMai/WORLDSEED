"""Persistent last-observed exterior appearances, never a second world authority.

Only gameplay discovery writes this store. Sparse 32-cell buckets support local
reads without scanning explored history. Each observed cell owns one current
record (no history); shared shell revisions are reference-counted and discarded
when their last observed cell is replaced. Growth is bounded by explored cells,
with at most twelve static prop appearances per cell and bounded shell geometry.
No actors, names, inventories, light sources or detection state are retained.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import blake2b
import json

from worldseed.core.coords import WorldPos
from worldseed.systems.building_shells import BuildingShell

MEMORY_VERSION = 1
BUCKET_EDGE = 32
MAX_OBSERVED_CELLS = 8192
MAX_CELL_OBJECTS = 12
MAX_SHELL_CELLS = 1024
MAX_SHELL_EXTENT = 64


@dataclass(frozen=True, slots=True)
class RememberedObject:
    uid: str
    kind: str
    content_id: str
    variant: int = 0
    category: str = ''
    material: str = ''
    tags: tuple[str, ...] = ()
    ground: bool = False


@dataclass(frozen=True, slots=True)
class RememberedCell:
    terrain_id: str = ''
    resource: tuple[str, str] | None = None
    objects: tuple[RememberedObject, ...] = ()
    shell_key: str = ''
    door: tuple[str, bool] | None = None


@dataclass(frozen=True, slots=True)
class RememberedShell:
    shell: BuildingShell
    variant_id: str = ''

    def to_row(self):
        s = self.shell
        return [s.uid, s.settlement_id, s.function, s.content_id,
                [list(c) for c in s.footprint], list(s.entrance) if s.entrance else None,
                s.door_uid, s.orientation, s.building_form, list(s.bounds), self.variant_id]

    @classmethod
    def from_row(cls, row):
        uid, settlement, function, content, cells, entrance, door, orientation, form, bounds, variant = row
        if (not isinstance(cells, list) or not 0 < len(cells) <= MAX_SHELL_CELLS
                or len(bounds) != 4 or not 0 < bounds[2]-bounds[0]+1 <= MAX_SHELL_EXTENT
                or not 0 < bounds[3]-bounds[1]+1 <= MAX_SHELL_EXTENT):
            raise ValueError('exterior memory shell exceeds bounded geometry')
        footprint = tuple((int(x), int(y)) for x, y in cells)
        if any(not (bounds[0] <= x <= bounds[2] and bounds[1] <= y <= bounds[3]) for x,y in footprint):
            raise ValueError('exterior memory shell outside bounds')
        return cls(BuildingShell(str(uid), str(settlement), str(function), str(content),
            footprint, tuple(map(int, entrance)) if entrance is not None else None,
            str(door), int(orientation), str(form), tuple(map(int, bounds))), str(variant))


class ExteriorMemory:
    def __init__(self):
        self._chunks: dict[tuple[int, int, int], dict[int, RememberedCell]] = {}
        self._shells: dict[str, RememberedShell] = {}
        self._refs: dict[str, int] = {}

    @staticmethod
    def _address(cell):
        x, y, z = cell
        return (x//BUCKET_EDGE, y//BUCKET_EDGE, z), (y%BUCKET_EDGE)*BUCKET_EDGE+x%BUCKET_EDGE

    def get(self, cell):
        bucket, index = self._address(cell)
        return self._chunks.get(bucket, {}).get(index)

    def shell(self, key):
        return self._shells.get(key)

    def remember(self, cell, appearance, shell=None):
        if not isinstance(appearance, RememberedCell) or len(appearance.objects) > MAX_CELL_OBJECTS:
            raise ValueError('bounded exterior cell appearance required')
        if appearance.shell_key and shell is None and appearance.shell_key not in self._shells:
            raise ValueError('missing observed exterior shell')
        if shell is None and appearance.shell_key:
            shell = self._shells[appearance.shell_key]
        bucket, index = self._address(cell)
        table = self._chunks.setdefault(bucket, {})
        old = table.get(index)
        if old == appearance:
            return
        if old is not None and old.shell_key:
            key = old.shell_key
            self._refs[key] -= 1
            if self._refs[key] == 0:
                del self._refs[key]
                del self._shells[key]
        table[index] = appearance
        if appearance.shell_key:
            key = appearance.shell_key
            if shell is not None:
                self._shells[key] = shell
            self._refs[key] = self._refs.get(key, 0)+1

    def to_dict(self):
        chunks = {}
        for (cx,cy,z), cells in sorted(self._chunks.items()):
            chunks[f'{cx},{cy},{z}'] = [[index, row.terrain_id,
                list(row.resource) if row.resource else None,
                [[o.uid,o.kind,o.content_id,o.variant,o.category,o.material,list(o.tags),o.ground] for o in row.objects],
                row.shell_key, list(row.door) if row.door else None]
                for index,row in sorted(cells.items())]
        return {'version': MEMORY_VERSION, 'chunks': chunks,
                'shells': {key: row.to_row() for key,row in sorted(self._shells.items())}}

    @classmethod
    def from_dict(cls, raw):
        result = cls()
        if raw is None:
            return result
        if (not isinstance(raw, dict) or type(raw.get('version')) is not int
                or raw.get('version') != MEMORY_VERSION):
            raise ValueError('unsupported exterior memory format')
        if not isinstance(raw.get('shells',{}),dict) or not isinstance(raw.get('chunks',{}),dict):
            raise ValueError('invalid exterior memory spatial tables')
        shells = {key: RememberedShell.from_row(row) for key,row in raw.get('shells',{}).items()}
        for token, rows in raw.get('chunks',{}).items():
            cx,cy,z = map(int,token.split(','))
            if not isinstance(rows,list) or len(rows) > BUCKET_EDGE**2:
                raise ValueError('exterior memory chunk exceeds bounded cells')
            indexes = set()
            for index,terrain,resource,objects,shell_key,door in rows:
                if type(index) is not int or not 0 <= index < BUCKET_EDGE**2 or index in indexes:
                    raise ValueError('invalid exterior memory cell index')
                indexes.add(index)
                if len(objects) > MAX_CELL_OBJECTS:
                    raise ValueError('exterior memory cell exceeds object budget')
                props = tuple(RememberedObject(str(uid),str(kind),str(content),int(variant),str(category),
                    str(material),tuple(map(str,tags)),bool(ground)) for uid,kind,content,variant,category,material,tags,ground in objects)
                feature = tuple(map(str,resource)) if resource else None
                if feature is not None and len(feature) != 2:
                    raise ValueError('invalid remembered resource appearance')
                value = RememberedCell(str(terrain),feature,props,str(shell_key),
                    (str(door[0]),bool(door[1])) if door else None)
                result.remember((cx*BUCKET_EDGE+index%BUCKET_EDGE,
                    cy*BUCKET_EDGE+index//BUCKET_EDGE,z),value,shells.get(shell_key))
        return result


def _shell_revision(sim, shell):
    if not isinstance(shell, BuildingShell):
        return None
    left,top,right,bottom = shell.bounds
    if (not 0 < len(shell.footprint) <= MAX_SHELL_CELLS
            or not 0 < right-left+1 <= MAX_SHELL_EXTENT
            or not 0 < bottom-top+1 <= MAX_SHELL_EXTENT):
        return None
    plan = sim.state.interiors.get('interior:'+shell.uid)
    appearance = RememberedShell(shell, str(getattr(plan,'variant_id','')))
    key = blake2b(json.dumps(appearance.to_row(),separators=(',',':')).encode(),digest_size=16).hexdigest()
    return key,appearance


def observe_exterior(sim, visible_cells):
    """Refresh exact cells witnessed by gameplay LOS, using prepared state only.

    Call after natural container materialization. Hidden cells are never queried
    or refreshed; missing prepared tiles preserve old memory rather than erase
    it. Closed roofs/shells admit their public exteriors and no underlying props.
    """
    if len(visible_cells) > MAX_OBSERVED_CELLS:
        raise ValueError('exterior observation exceeds bounded sight budget')
    memory = sim.state.exterior_memory
    if not isinstance(memory, ExteriorMemory):
        raise ValueError('simulation exterior memory must be initialized')
    physical = sim.settlement_physicalization
    shell_revisions = {}
    for cell in sorted(visible_cells,key=lambda c:(c[2],c[1],c[0])):
        x,y,z = cell
        token = f'{x},{y},{z}'
        pos = WorldPos(x,y,z)
        roof = sim.state.roofs.get(token)
        if roof is not None and roof.condition > 0:
            memory.remember(cell,RememberedCell(objects=(RememberedObject(
                f'roof:{z}:{x}:{y}','roof',str(roof.structure_id)),)))
            continue
        shell = physical.shell_at(pos) if z == 0 else None
        if shell is not None:
            if shell.uid not in shell_revisions:
                shell_revisions[shell.uid] = _shell_revision(sim,shell)
            revision = shell_revisions[shell.uid]
            if revision is None:
                memory.remember(cell,RememberedCell())
                continue
            key,appearance = revision
            door = None
            if shell.entrance == (x,y) and shell.door_uid:
                state = sim.state.door_security.get(shell.door_uid)
                opened = bool(state and (state.forced or (state.answering_npc_uid
                    and state.answered_minute >= state.answer_requested_minute >= 0)))
                door = (shell.door_uid,opened)
            memory.remember(cell,RememberedCell(shell_key=key,door=door),appearance)
            continue
        physical_cell = physical.cell_at(pos) if z == 0 else None
        if physical_cell is not None and (physical_cell.room_id or physical_cell.roof_piece_id):
            memory.remember(cell,RememberedCell())
            continue
        tile = sim.world.prepared_tile_at(pos)
        if tile is None:
            continue
        feature = sim.resources.prepared_feature_at(pos,sim.clock.minute)
        resource = ((str(feature.feature_id),str(feature.stage))
                    if feature is not None and feature.stage != 'depleted' else None)
        objects = []
        def add(kind,content,uid=None,**kwargs):
            objects.append(RememberedObject(uid or f'{kind}:{z}:{x}:{y}',kind,str(content),**kwargs))
        if physical_cell is not None:
            for slot in ('ground_piece_id','structure_piece_id','fixture_piece_id'):
                piece_id = getattr(physical_cell,slot)
                piece = sim.registry.settlement_pieces.get(piece_id)
                if piece is not None:
                    add('settlement_piece',piece_id,f'piece:{slot}:{token}',category=piece.category,
                        material=piece.material,tags=tuple(sorted(set(piece.tags)|set(piece.room_tags))),
                        ground=piece.category in {'floor','road'} or piece.layer == 'ground')
        structure = sim.state.structures.get(token)
        if structure is not None and structure.condition > 0:
            definition = sim.registry.structures.get(structure.structure_id)
            tags = tuple(getattr(definition,'tags',()))
            add('structure',structure.structure_id,tags=tags,ground=bool(set(tags)&{'floor','bridge'}))
        container = sim.state.containers.get(token)
        if (container is not None and container.condition > 0
                and not container.interior_space_id and structure is None):
            add('container',container.source_id or 'core:wood_chest','container:'+container.uid,
                category=str(container.profile_id))
        pile = sim.state.ground_piles.get(token)
        if pile is not None:
            first = next((item for item,amount in pile.items.items() if amount > 0),None)
            if first is not None:
                add('pile',first)
        crop = sim.state.crops.get(token)
        if crop is not None and crop.health > 0:
            add('crop',crop.crop_id,variant=2 if crop.mature else (1 if crop.growth >= 45 else 0))
        memory.remember(cell,RememberedCell(str(tile.terrain_id),resource,tuple(objects)))
