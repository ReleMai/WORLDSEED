"""Convert immutable last-observed appearances into detached GPU records.

The optional old-save basemap reader consumes persisted generated BASE chunks
only. It never consumes resident chunks (which include current hidden deltas),
saved/dirty deltas, public/private props or raw generation. Positive base reads
share a bounded per-world weak cache; a per-capture miss cache permits later
normal world preparation to fill previously absent base rows.
"""
from collections import OrderedDict
from weakref import WeakKeyDictionary

from worldseed.config import CHUNK_SIZE
from worldseed.core.coords import WorldPos, split_world
from .gpu_objects import PreparedObject, object_geometry
from .worldspace import WorldFoot

BASE_MEMORY_CHUNK_LIMIT = 128
_base_chunks = WeakKeyDictionary()


def legacy_base_terrain(world, cell, capture_chunks):
    """Return one already-generated base cell for old discovery-only saves.

    The caller must authorize exact discovery membership first. The cache key
    uses all pinned physical projection versions, exactly like World loading;
    an active surface contract never falls back to an incompatible old cache.
    This read does not promote a cell into persistent appearance knowledge.
    """
    key,lx,ly = split_world(WorldPos(*cell))
    contract = world._surface_cache_contract(key)
    version_key = (key,contract if contract is not None else (world.generator.version,))
    if version_key not in capture_chunks:
        cached = _base_chunks.setdefault(world,OrderedDict())
        base = cached.get(version_key)
        if base is not None:
            cached.move_to_end(version_key)
        else:
            if contract is not None:
                loader = getattr(world.delta_source,'load_generated_surface_chunk',None)
                base = loader(key,*contract) if callable(loader) else None
            else:
                loader = getattr(world.delta_source,'load_generated_chunk',None)
                base = loader(key,world.generator.version) if callable(loader) else None
            if base is not None and len(base) == CHUNK_SIZE*CHUNK_SIZE:
                base = tuple(base)
                cached[version_key] = base
                cached.move_to_end(version_key)
                while len(cached) > BASE_MEMORY_CHUNK_LIMIT:
                    cached.popitem(last=False)
            else:
                base = None
        capture_chunks[version_key] = base
    base = capture_chunks[version_key]
    terrain_id = base[ly*CHUNK_SIZE+lx] if base is not None else None
    return terrain_id if terrain_id in world.registry.terrains else None


def remembered_object(cell, appearance):
    x,y,z = cell
    width,height,layer = object_geometry(appearance.kind,ground=appearance.ground)
    return PreparedObject(appearance.uid,appearance.kind,appearance.content_id,
        WorldFoot(x+.5,y+.999,z),width,height,layer,appearance.variant,
        appearance.category,appearance.material,appearance.tags)
