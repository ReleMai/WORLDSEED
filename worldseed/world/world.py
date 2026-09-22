from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, Callable
from worldseed.config import DEFAULT_CACHE_CHUNKS, CHUNK_SIZE, HYDROLOGY_VERSION, HYDROLOGY_MORPHOLOGY_VERSION
from worldseed.content.registry import ContentRegistry, TerrainDef
from worldseed.core.coords import ChunkKey, WorldPos, split_world
from worldseed.world.cache import ChunkCache
from worldseed.world.chunk import Chunk
from worldseed.world.generator import WorldGenerator

class DeltaSource(Protocol):
    def load_chunk_deltas(self,key:ChunkKey)->dict[tuple[int,int],str]:...
@dataclass(frozen=True,slots=True)
class TileView:
    position:WorldPos; terrain_id:str; terrain:TerrainDef
class World:
    def __init__(self,generator:WorldGenerator,registry:ContentRegistry,delta_source:DeltaSource,cache_chunks:int=DEFAULT_CACHE_CHUNKS,auto_hydrology:bool=True)->None:
        self.generator=generator; self.registry=registry; self.delta_source=delta_source; self.dirty_tiles:dict[WorldPos,str]={}; self.revision=0
        if auto_hydrology and self.generator.version>=5 and getattr(self.generator,'hydrology',None) is None:
            from worldseed.world.hydrology import HydrologyGenerator
            hydrology_version=HYDROLOGY_VERSION
            morphology_version=HYDROLOGY_MORPHOLOGY_VERSION
            getter=getattr(delta_source,'get_meta',None)
            if callable(getter):
                try:hydrology_version=int(getter('hydrology_version'))
                except (KeyError,TypeError,ValueError):hydrology_version=1
                try:morphology_version=int(getter('hydrology_morphology_version'))
                except (KeyError,TypeError,ValueError):morphology_version=1
            self.generator.attach_hydrology(HydrologyGenerator(
                self.generator,delta_source,version=hydrology_version,
                morphology_version=morphology_version,
            ))
        self.cache=ChunkCache(cache_chunks,self._load_chunk)
    def _chunk_from_ids(self,key:ChunkKey,terrain_ids)->Chunk|None:
        if terrain_ids is None or len(terrain_ids)!=(CHUNK_SIZE*CHUNK_SIZE):return None
        chunk=Chunk.empty(key)
        try:
            for i,tid in enumerate(terrain_ids):
                if tid is None:return None
                chunk.terrain[i]=self.registry.terrain_index(str(tid))
            return chunk
        except Exception:
            return None
    def _surface_cache_contract(self,key:ChunkKey):
        hydro=getattr(self.generator,'hydrology',None)
        if key.z==0 and self.generator.version>=5 and hydro is not None:
            return (
                int(self.generator.version),
                int(getattr(hydro,'version',1)),
                int(getattr(hydro,'morphology_version',1)),
            )
        return None
    def _load_chunk(self,key:ChunkKey)->Chunk:
        chunk=None
        surface_contract=self._surface_cache_contract(key)
        if surface_contract is not None:
            loader=getattr(self.delta_source,'load_generated_surface_chunk',None)
            if callable(loader):
                chunk=self._chunk_from_ids(key,loader(key,*surface_contract))
        else:
            loader=getattr(self.delta_source,'load_generated_chunk',None)
            if callable(loader):
                chunk=self._chunk_from_ids(key,loader(key,self.generator.version))
        if chunk is None:
            chunk=self.generator.generate_chunk(key)
            # Surface terrain depends on both drainage and morphology contracts,
            # so v5+ surface caches are keyed by all three versions. Underground
            # and pre-hydrology geography retain the older worldgen-only cache.
            terrain_ids=[self.registry.terrain_id(v) for v in chunk.terrain]
            if surface_contract is not None:
                storer=getattr(self.delta_source,'store_generated_surface_chunk',None)
                if callable(storer):storer(key,*surface_contract,terrain_ids)
            else:
                storer=getattr(self.delta_source,'store_generated_chunk',None)
                if callable(storer):storer(key,self.generator.version,terrain_ids)
        for (lx,ly),tid in self.delta_source.load_chunk_deltas(key).items(): chunk.set(lx,ly,self.registry.terrain_index(tid))
        return chunk
    @staticmethod
    def _ordered_chunk_offsets(radius:int):
        r=max(0,int(radius))
        rows=[(dx,dy) for dy in range(-r,r+1) for dx in range(-r,r+1)]
        rows.sort(key=lambda q:(max(abs(q[0]),abs(q[1])),abs(q[0])+abs(q[1]),q[1],q[0]))
        return rows
    def pre_generate(self,center:WorldPos,radius_chunks:int,progress:Callable[[int,int,str],None]|None=None,persist:bool=True)->dict[str,int]:
        """Generate a square surface envelope around ``center`` before play.

        WORLDSEED remains unbounded; this prepares the high-probability early
        exploration area and persists the deterministic base chunks so crossing
        a chunk edge does not invoke the terrain generator in the movement loop.
        """
        center_key,_,_=split_world(center)
        offsets=self._ordered_chunk_offsets(radius_chunks);total=len(offsets)
        # v5 terrain is a projection of hydrology. Prepare the entire requested
        # envelope as one hydrology window before any chunk is generated so
        # adjacent chunks cannot independently invent river seams.
        hydro=getattr(self.generator,'hydrology',None)
        if self.generator.version>=5 and hydro is not None and center.z==0:
            r=max(0,int(radius_chunks))
            x0=(center_key.x-r)*CHUNK_SIZE;y0=(center_key.y-r)*CHUNK_SIZE
            x1=(center_key.x+r+1)*CHUNK_SIZE-1;y1=(center_key.y+r+1)*CHUNK_SIZE-1
            hydro.prepare_world_bounds(x0,y0,x1,y1,persist=persist)
        generated=0;reused=0
        loader=getattr(self.delta_source,'load_generated_chunk',None)
        storer=getattr(self.delta_source,'store_generated_chunk',None)
        for idx,(dx,dy) in enumerate(offsets,1):
            key=ChunkKey(center_key.x+dx,center_key.y+dy,center.z)
            chunk=None
            surface_contract=self._surface_cache_contract(key)
            if surface_contract is not None:
                surface_loader=getattr(self.delta_source,'load_generated_surface_chunk',None)
                if callable(surface_loader):
                    chunk=self._chunk_from_ids(key,surface_loader(key,*surface_contract))
            elif callable(loader):
                chunk=self._chunk_from_ids(key,loader(key,self.generator.version))
            if chunk is None:
                chunk=self.generator.generate_chunk(key);generated+=1
                if persist:
                    terrain_ids=[self.registry.terrain_id(v) for v in chunk.terrain]
                    if surface_contract is not None:
                        surface_storer=getattr(self.delta_source,'store_generated_surface_chunk',None)
                        if callable(surface_storer):surface_storer(key,*surface_contract,terrain_ids)
                    elif callable(storer):
                        storer(key,self.generator.version,terrain_ids)
            else:reused+=1
            # New-world pregeneration has no deltas, but applying them here keeps
            # this method correct if it is reused for an existing world later.
            for (lx,ly),tid in self.delta_source.load_chunk_deltas(key).items():
                chunk.set(lx,ly,self.registry.terrain_index(tid))
            self.cache.put(key,chunk)
            if progress:progress(idx,total,f'chunk {key.x}, {key.y}')
        if persist:
            commit=getattr(self.delta_source,'commit_generated',None)
            if callable(commit):commit()
        # The prepared chunks are now materialized in the LRU/SQLite store; the
        # generator's large interpolation lattice scratch cache no longer buys
        # us anything for this area and can consume tens of MB after a wide pass.
        lattice=getattr(self.generator,'_lattice_cache',None)
        if isinstance(lattice,dict):lattice.clear()
        return {'total':total,'generated':generated,'reused':reused}
    def warm_region(self,center:WorldPos,radius_chunks:int,progress:Callable[[int,int,str],None]|None=None)->None:
        center_key,_,_=split_world(center);offsets=self._ordered_chunk_offsets(radius_chunks);total=len(offsets)
        for idx,(dx,dy) in enumerate(offsets,1):
            key=ChunkKey(center_key.x+dx,center_key.y+dy,center.z);self.cache.get(key)
            if progress:progress(idx,total,f'chunk {key.x}, {key.y}')
    def tile_at(self,pos:WorldPos)->TileView:
        key,lx,ly=split_world(pos); chunk=self.cache.get(key); tid=self.registry.terrain_id(chunk.get(lx,ly)); return TileView(pos,tid,self.registry.terrain(tid))
    def set_terrain(self,pos:WorldPos,terrain_id:str)->None:
        if terrain_id not in self.registry.terrains:raise KeyError(terrain_id)
        key,lx,ly=split_world(pos); chunk=self.cache.get(key); chunk.set(lx,ly,self.registry.terrain_index(terrain_id)); self.dirty_tiles[pos]=terrain_id; self.revision+=1; self.cache.pin(key)
    def is_passable(self,pos:WorldPos)->bool:return self.tile_at(pos).terrain.passable
    def environment_at(self, pos: WorldPos):
        """Read natural site potential without realizing terrain or populations."""
        return self.generator.environment_at(pos)

    def topography_at(self,pos:WorldPos):
        """Read authoritative v8 slope/relief fields without realizing terrain."""
        getter=getattr(self.generator,'topography_at',None)
        return getter(pos) if callable(getter) else None

    def climate_at(self,pos:WorldPos):
        """Read authoritative v8 physical climate without realizing terrain."""
        getter=getattr(self.generator,'climate_at',None)
        return getter(pos) if callable(getter) else None

    def coast_at(self,pos:WorldPos,*,prepared_only:bool=True):
        """Read Phase-5 coastal morphology without generating missing plans."""
        getter=getattr(self.generator,'coast_at',None)
        return getter(pos,prepared_only=prepared_only) if callable(getter) else None

    def hydrology_at(self,pos:WorldPos):
        getter=getattr(self.generator,'hydrology_at',None)
        return getter(pos) if callable(getter) else None
    def current_at(self,pos:WorldPos,*,prepared_only:bool=False):
        getter=getattr(self.generator,'current_at',None)
        return getter(pos,prepared_only=prepared_only) if callable(getter) else None
    def crossing_cost(self,pos:WorldPos)->int:
        surface=self.hydrology_at(pos)
        return int(getattr(surface,'crossing_cost',0) or 0) if surface is not None else 0
    def drain_dirty_tiles(self)->dict[WorldPos,str]:
        out=dict(self.dirty_tiles); self.dirty_tiles.clear()
        for pos in out:self.cache.clear_pin(split_world(pos)[0])
        return out
