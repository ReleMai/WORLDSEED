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


def discovered_regions(sim):
    regions = set()
    for token in sim.discovered_tiles_set:
        try:
            x, y, z = map(int, token.split(','))
        except (ValueError, TypeError, AttributeError):
            continue
        if z == 0:
            regions.add(region_coords(x, y))
    if sim.player_pos.z == 0:
        regions.add(region_coords(sim.player_pos.x, sim.player_pos.y))
    return regions


def read_atlas(sim, center=None, span=512):
    """At most 65x65 chunk probes; no cache loads, writes, RNG or planner calls.

    All generator versions use their stored tiles. New/modded terrain IDs are
    retained verbatim. The atlas intentionally never reconstructs missing base
    on an inspection path (important for legacy hydrology compatibility).
    """
    span = max(128, min(2048, int(span)))
    cx, cy = center or (sim.player_pos.x, sim.player_pos.y)
    view = AtlasSnapshot(int(cx)-span//2, int(cy)-span//2, span)
    world = sim.world
    regions = discovered_regions(sim)
    for ky in range(view.top//CHUNK_SIZE, (view.top+span-1)//CHUNK_SIZE+1):
        for kx in range(view.left//CHUNK_SIZE, (view.left+span-1)//CHUNK_SIZE+1):
            if region_coords(kx*CHUNK_SIZE, ky*CHUNK_SIZE) not in regions:
                continue
            key = ChunkKey(kx, ky, 0)
            chunk = world.cache.peek(key)
            if chunk is not None:
                values = [world.registry.terrain_id(i) for i in chunk.terrain]
            else:
                loader = getattr(world.delta_source, 'load_generated_chunk', None)
                base = loader(key, world.generator.version) if callable(loader) else None
                if base is None or len(base) != CHUNK_SIZE*CHUNK_SIZE:
                    continue
                values = list(base)
                for (lx, ly), tid in world.delta_source.load_chunk_deltas(key).items():
                    if 0 <= lx < CHUNK_SIZE and 0 <= ly < CHUNK_SIZE:
                        values[ly*CHUNK_SIZE+lx] = tid
            view.chunks[key] = values
    for pos, tid in world.dirty_tiles.items():
        key, lx, ly = split_world(pos)
        if pos.z == 0 and key in view.chunks:
            view.chunks[key][ly*CHUNK_SIZE+lx] = tid
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
