"""Exact, bounded cartographic read model. Never generates or realizes the world.

Source precedence is identical to local tiles: loaded chunk > persisted base
plus saved deltas. Dirty edits win. Missing base remains unknown, not a guessed
biome. Region discovery reveals available terrain, never hidden POI records.
"""
from dataclasses import dataclass, field
from worldseed.config import CHUNK_SIZE
from worldseed.core.coords import ChunkKey, WorldPos, split_world
from worldseed.world.region_blocks import REGION_SIZE, region_coords


@dataclass(frozen=True)
class AtlasMarker:
    uid: str
    kind: str
    name: str
    x: int
    y: int
    z: int = 0
    detail: str = ''


@dataclass
class AtlasSnapshot:
    left: int
    top: int
    span: int
    chunks: dict = field(default_factory=dict)
    markers: tuple = ()

    def contains(self, x, y):
        return self.left <= x < self.left+self.span and self.top <= y < self.top+self.span

    def terrain_at(self, x, y):
        if not self.contains(x, y):
            return None
        key, lx, ly = split_world(WorldPos(x, y, 0))
        values = self.chunks.get(key)
        return values[ly*CHUNK_SIZE+lx] if values else None


def _discovered_cells_in_view(sim, view: AtlasSnapshot):
    """Group only actually discovered surface cells by chunk.

    Simulation keeps a runtime per-chunk discovery index, so atlas panning cost
    grows with chunks in the requested view rather than with the entire lifetime
    exploration history.
    """
    grouped={}
    indexed=getattr(sim,'discovered_surface_cells_by_chunk',None)
    if indexed is not None:
        min_cx,max_cx=view.left//CHUNK_SIZE,(view.left+view.span-1)//CHUNK_SIZE
        min_cy,max_cy=view.top//CHUNK_SIZE,(view.top+view.span-1)//CHUNK_SIZE
        for (cx,cy),indices in indexed.items():
            if min_cx<=cx<=max_cx and min_cy<=cy<=max_cy:
                grouped[ChunkKey(cx,cy,0)]=set(indices)
    else:
        for token in sim.discovered_tiles_set:
            try:x,y,z=map(int,token.split(','))
            except (ValueError,TypeError,AttributeError):continue
            if z!=0 or not view.contains(x,y):continue
            key,lx,ly=split_world(WorldPos(x,y,0))
            grouped.setdefault(key,set()).add(ly*CHUNK_SIZE+lx)
    p=sim.player_pos
    if p.z==0 and view.contains(p.x,p.y):
        key,lx,ly=split_world(p);grouped.setdefault(key,set()).add(ly*CHUNK_SIZE+lx)
    return grouped


def _stored_surface_chunk(world, key):
    """Read the persisted base under the same version contract as local terrain."""
    chunk = world.cache.peek(key)
    if chunk is not None:
        return [world.registry.terrain_id(i) for i in chunk.terrain]

    contract = getattr(world, '_surface_cache_contract', lambda _k: None)(key)
    if contract is not None:
        loader = getattr(world.delta_source, 'load_generated_surface_chunk', None)
        base = loader(key, *contract) if callable(loader) else None
        if base is not None:
            return list(base)

    loader = getattr(world.delta_source, 'load_generated_chunk', None)
    base = loader(key, world.generator.version) if callable(loader) else None
    return list(base) if base is not None else None


def read_atlas(sim, center=None, span=512):
    """Exact bounded map of discovered cells only; never generates terrain.

    Local tiles and atlas pixels now share the same versioned surface-cache
    authority. Panning cost scales with explored cells in view rather than with
    every chunk of an entire discovered 512-cell region.
    """
    span = max(128, min(2048, int(span)))
    cx, cy = center or (sim.player_pos.x, sim.player_pos.y)
    view = AtlasSnapshot(int(cx)-span//2, int(cy)-span//2, span)
    world = sim.world
    discovered = _discovered_cells_in_view(sim, view)

    for key, indices in discovered.items():
        base = _stored_surface_chunk(world, key)
        if base is None or len(base) != CHUNK_SIZE*CHUNK_SIZE:
            continue
        values = [None]*(CHUNK_SIZE*CHUNK_SIZE)
        for i in indices:
            values[i]=base[i]
        deltas=world.delta_source.load_chunk_deltas(key)
        for (lx,ly),tid in deltas.items():
            idx=ly*CHUNK_SIZE+lx
            if idx in indices:
                values[idx]=tid
        view.chunks[key]=values

    for pos, tid in world.dirty_tiles.items():
        key, lx, ly = split_world(pos)
        if pos.z == 0 and key in view.chunks:
            idx=ly*CHUNK_SIZE+lx
            if idx in discovered.get(key,()):
                view.chunks[key][idx] = tid

    markers = []
    for town in sim.known_settlements():
        if view.contains(town.x, town.y):
            # Presentation size class, not a new settlement authority.
            kind = 'city' if town.population >= 1000 else 'village'
            markers.append(AtlasMarker(town.uid, kind, town.name, town.x, town.y,
                                       detail=f'{kind.title()} | population {town.population}'))
    for uid in sorted(sim.known_site_ids()):
        site = sim.state.dungeon_sites.get(uid)
        if site is None:
            continue
        x, y = site.chunk_x*CHUNK_SIZE+CHUNK_SIZE//2, site.chunk_y*CHUNK_SIZE+CHUNK_SIZE//2
        if view.contains(x, y):
            info = world.generator.sites.info(ChunkKey(site.chunk_x, site.chunk_y, site.z))
            kind = info.site_type if info else 'fortress'
            markers.append(AtlasMarker(uid, kind, site.name, x, y, site.z,
                f'Known site | depth {site.z} | approximate chunk center'))
    # Camps are real campfires / shelters; no fabricated NPC camps.
    camp_cells = set()
    for key, structure in sorted(sim.state.structures.items()):
        if structure.z != 0 or structure.condition <= 0 or not view.contains(structure.x, structure.y):
            continue
        definition = world.registry.structures.get(structure.structure_id)
        if not definition or not (structure.structure_id == 'core:campfire' or 'shelter' in definition.tags):
            continue
        if structure.owner != 'player' and f'{structure.x},{structure.y},0' not in sim.discovered_tiles_set:
            continue
        cluster = (structure.x//8, structure.y//8)
        if cluster in camp_cells:
            continue
        camp_cells.add(cluster)
        markers.append(AtlasMarker('camp:'+str(key), 'camp', definition.name, structure.x, structure.y,
                                   detail='Known camp structure'))
    for token in sorted(sim.discovered_tiles_set):
        try:
            x, y, z = map(int, token.split(','))
        except (ValueError, TypeError, AttributeError):
            continue
        if z == 0 and view.terrain_at(x, y) == 'core:cave_mouth':
            markers.append(AtlasMarker('cave:'+token, 'cave', 'Cave entrance', x, y, detail='Observed surface entrance'))
    view.markers = tuple(sorted(markers, key=lambda m: (m.kind, m.name, m.uid)))
    return view
