from __future__ import annotations
from dataclasses import dataclass
from worldseed.config import CHUNK_SIZE, WORLDGEN_VERSION, COAST_MORPHOLOGY_VERSION
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import ChunkKey, WorldPos, chunk_origin
from worldseed.core.rng import hash_u64
from worldseed.world.chunk import Chunk
from worldseed.systems.sites import SiteGenerator

Q=65535
@dataclass(frozen=True,slots=True)
class WorldFields:
    elevation:int; moisture:int; temperature:int; fertility:int

@dataclass(frozen=True,slots=True)
class SurfaceCurrent:
    kind:str='none'
    dx:int=0
    dy:int=0
    speed:int=0

    @property
    def flowing(self)->bool:
        return bool(self.speed>0 and (self.dx or self.dy))

    @property
    def heading(self)->str:
        if self.dx==0 and self.dy<0:return 'north'
        if self.dx>0 and self.dy<0:return 'northeast'
        if self.dx>0 and self.dy==0:return 'east'
        if self.dx>0 and self.dy>0:return 'southeast'
        if self.dx==0 and self.dy>0:return 'south'
        if self.dx<0 and self.dy>0:return 'southwest'
        if self.dx<0 and self.dy==0:return 'west'
        if self.dx<0 and self.dy<0:return 'northwest'
        return 'still'

    @property
    def strength_band(self)->str:
        if self.speed>=72:return 'strong'
        if self.speed>=42:return 'moderate'
        if self.speed>0:return 'gentle'
        return 'still'

def _smooth_q(t:int)->int:
    t2=(t*t)//Q; t3=(t2*t)//Q; return max(0,min(Q,3*t2-2*t3))
def _lerp_q(a:int,b:int,t:int)->int: return a+((b-a)*t)//Q

class WorldGenerator:
    def __init__(self,world_seed:bytes,registry:ContentRegistry,version:int|None=None)->None:
        self.world_seed=world_seed; self.registry=registry; self.version=int(WORLDGEN_VERSION if version is None else version); self.sites=SiteGenerator(world_seed)
        self.coast_morphology_version=int(COAST_MORPHOLOGY_VERSION if self.version>=8 else 0)
        self._lattice_cache={}
        # WORLDGEN v8 geological/topographic read models. They are authoritative
        # for v8 worlds (the current new-world default); v1-v7 keep frozen fields.
        from worldseed.world.landforms import LandformSampler
        from worldseed.world.topography import TopographySampler
        from worldseed.world.climate_v8 import ClimateV8Sampler
        self.landforms_v8 = LandformSampler(self.world_seed)
        self.topography_v8 = TopographySampler(
            lambda x,y: self.landforms_v8.sample(x,y).elevation
        )
        self.climate_v8 = ClimateV8Sampler(
            self.world_seed, self.landforms_v8, self.topography_v8
        )
        from worldseed.world.coast_v8 import CoastV8Sampler
        self.coast_v8 = CoastV8Sampler(self)
        from worldseed.world.coastal_mouths import CoastalMouths
        self.coastal_mouths = CoastalMouths(self)
        # RC14 Phase 3 attaches a HydrologyGenerator after database/opening state
        # exists. Keeping the dependency injected avoids making rendering or
        # content code an authority over physical geography.
        self.hydrology=None
        from worldseed.world.environmental_fields import EnvironmentalFieldSampler
        self.environmental_fields = EnvironmentalFieldSampler(self)
        self.caves = None
        if self.version >= 8:
            from worldseed.world.caves import CaveGeneratorV8
            self.caves = CaveGeneratorV8(
                self.world_seed, self.sample_fields, self._value_noise,
                self.landforms_v8.sample, self.topography_v8.sample,
            )
        elif self.version >= 7:
            from worldseed.world.caves import CaveGeneratorV7
            self.caves = CaveGeneratorV7(self.world_seed, self.sample_fields, self._value_noise)
    def _lattice_value(self,namespace:str,ix:int,iy:int)->int:
        key=(namespace,ix,iy)
        if key in self._lattice_cache:return self._lattice_cache[key]
        # v5 deliberately builds on the approved v4 continental/climate field
        # instead of re-rolling every biome merely because rivers were added.
        # Legacy <=3 contracts remain exact and v4 fingerprints are unchanged.
        field_version=4 if self.version>=4 else self.version
        value=hash_u64(self.world_seed,namespace,field_version,ix,iy)&0xFFFF
        if len(self._lattice_cache)>=65536:self._lattice_cache.clear()
        self._lattice_cache[key]=value
        return value
    def _value_noise(self,namespace:str,x:int,y:int,period:int)->int:
        ix=x//period; iy=y//period; rx=x%period; ry=y%period
        tx=_smooth_q((rx*Q)//period); ty=_smooth_q((ry*Q)//period)
        a=_lerp_q(self._lattice_value(namespace,ix,iy),self._lattice_value(namespace,ix+1,iy),tx)
        b=_lerp_q(self._lattice_value(namespace,ix,iy+1),self._lattice_value(namespace,ix+1,iy+1),tx)
        return _lerp_q(a,b,ty)
    def _fractal(self,namespace:str,x:int,y:int)->int:
        # v1-v3 field frequencies are part of the legacy generator contract.
        a=self._value_noise(namespace+":macro",x,y,96); b=self._value_noise(namespace+":mid",x,y,32); c=self._value_noise(namespace+":fine",x,y,12)
        return (a*5+b*3+c*2)//10

    def _regional_field(self,namespace:str,x:int,y:int,macro:int,meso:int,local:int,weights:tuple[int,int,int])->int:
        """Continuous multi-scale field used by generator v4+.

        Climate changes much more slowly than individual terrain cells.  Keeping
        elevation, moisture and temperature on different spatial frequencies
        produces broad biome regions with soft ecotones instead of salt-and-
        pepper forest/grass transitions.  Integer arithmetic preserves exact
        cross-platform determinism.
        """
        a=self._value_noise(namespace+":continental",x,y,macro)
        b=self._value_noise(namespace+":regional",x,y,meso)
        c=self._value_noise(namespace+":local",x,y,local)
        total=sum(weights)
        return (a*weights[0]+b*weights[1]+c*weights[2])//max(1,total)

    def sample_fields(self,pos:WorldPos)->WorldFields:
        if self.version <= 3:
            elevation=self._fractal("elevation",pos.x,pos.y)
            moisture=self._fractal("moisture",pos.x+14037,pos.y-8811)
            climate=self._fractal("temperature",pos.x-41003,pos.y+9237)
        elif self.version <= 7:
            # Frozen v4-v7 field contract. Hydrology, oceans and caves were added
            # in later versions without re-rolling these continental/climate
            # fields, so legacy saves keep their exact established geography.
            elevation=self._regional_field("elevation4",pos.x,pos.y,384,128,40,(6,3,1))
            moisture=self._regional_field("moisture4",pos.x+14037,pos.y-8811,640,224,72,(7,2,1))
            climate=self._regional_field("temperature4",pos.x-41003,pos.y+9237,768,256,96,(7,2,1))
        else:
            # WORLDGEN v8 Phase 3: geography now drives climate. Geological
            # elevation, latitude bands, maritime influence, prevailing winds,
            # orographic lift and leeward rain shadows feed these fields.
            elevation=self.landforms_v8.sample(pos.x,pos.y).elevation
            physical_climate=self.climate_v8.sample(pos.x,pos.y)
            moisture=physical_climate.precipitation_potential
            climate=physical_climate.mean_temperature
        if self.version>=8:
            # ClimateV8 already applies elevation lapse cooling.
            seasonal_base=max(0,min(Q,climate))
        else:
            seasonal_base=max(0,min(Q,climate-max(0,elevation-42000)//2))
        fertility=max(0,min(Q,(moisture*3+(Q-abs(seasonal_base-36000))*2)//5))
        return WorldFields(elevation,moisture,seasonal_base,fertility)

    def prototype_landform_at(self, x:int, y:int):
        """Read WORLDGEN v8 geology without requiring a v8 authoritative world."""
        return self.landforms_v8.sample(int(x), int(y))

    def landform_at(self,pos:WorldPos):
        """Return authoritative v8 landform context, or None for legacy worlds."""
        if self.version < 8 or pos.z != 0:
            return None
        return self.landforms_v8.sample(pos.x,pos.y)

    def topography_at(self,pos:WorldPos):
        """Return v8 slope/relief derivatives without realizing a chunk."""
        if self.version < 8 or pos.z != 0:
            return None
        return self.topography_v8.sample(pos)

    def climate_at(self,pos:WorldPos):
        """Return authoritative v8 physical climate, or None for legacy worlds."""
        if self.version < 8 or pos.z != 0:
            return None
        return self.climate_v8.sample(pos.x,pos.y)

    def coast_at(self,pos:WorldPos,*,prepared_only:bool=True):
        """Return Phase-5 coastal morphology without changing terrain authority."""
        if self.version < 8 or pos.z != 0:
            return None
        return self.coast_v8.sample(pos,prepared_only=prepared_only)

    def set_coast_morphology_version(self,version:int)->None:
        """Pin shoreline materialization to the save's recorded contract."""
        self.coast_morphology_version=max(0,int(version))

    def _phase5_coast_terrain(self,pos:WorldPos,fields:WorldFields)->str|None:
        """Project Phase-5 coast fields into terrain for coast version 1+.

        Version 0 is the Dev32/legacy v8 shoreline contract.  New worlds use
        version 1, while old saves remain visually stable until explicitly
        migrated by a future migration tool.
        """
        if self.version<8 or self.coast_morphology_version<=0:
            return None
        coast=self.coast_v8.materialization_at(pos,fields)
        if coast is None:
            return None
        if coast.ocean:
            return {
                'intertidal':'core:ocean_wade',
                'shallow':'core:ocean_shallow',
                'shelf':'core:ocean_shelf',
                'deep':'core:ocean_deep',
            }.get(coast.shelf_class,'core:ocean_deep')

        # Do not paint the entire 64-cell analysis band as shoreline.  Hard
        # shore materials occupy the immediate edge; depositional flats/marsh
        # can extend somewhat farther inland where the physical fields support it.
        d=int(coast.coast_distance)
        if d<=20 and coast.marsh_potential>=76:
            return 'core:salt_marsh'
        if d<=14 and coast.tidal_flat_potential>=70:
            return 'core:tidal_flat'
        if d<=8:
            if coast.coast_kind=='cliff':
                return 'core:coastal_cliff'
            if coast.coast_kind in {'headland','rocky'} or coast.shore_material=='rock':
                return 'core:rocky_shore'
            if coast.shore_material=='gravel':
                return 'core:coastal_gravel'
            return 'core:shore'
        return None

    def _connector_span(self,x:int,y:int)->int:
        """Depth of one sparse, coherent natural vertical connector.

        v7 delegates to terrain-aware cave entrance planning. v3-v6 retain the
        older 8x8 contract exactly so existing saves never move their mouths.
        """
        if self.version >= 7 and self.caves is not None:
            return self.caves.connector_span(x,y)
        cell=8;cx=x//cell;cy=y//cell
        if hash_u64(self.world_seed,"cave-column-cell",cx,cy)%14 != 0:return 0
        ox=hash_u64(self.world_seed,"cave-column-x",cx,cy)%cell
        oy=hash_u64(self.world_seed,"cave-column-y",cx,cy)%cell
        if (x,y)!=(cx*cell+ox,cy*cell+oy):return 0
        if self.sample_fields(WorldPos(x,y,0)).elevation < 26500:return 0
        return 1 + (hash_u64(self.world_seed,"cave-column-depth",x,y)%4)

    def has_connector(self,pos:WorldPos)->bool:
        span=self._connector_span(pos.x,pos.y)
        return span>0 and 0 >= pos.z >= -span

    def _near_connector_chamber(self,pos:WorldPos)->bool:
        if self.version >= 7 and self.caves is not None:
            return self.caves.near_entrance_chamber(pos)
        if pos.z>=0:return False
        for dy in range(-2,3):
            for dx in range(-2,3):
                if abs(dx)+abs(dy)<=2:
                    span=self._connector_span(pos.x-dx,pos.y-dy)
                    if span and -span<=pos.z<=-1:return True
        return False

    def _surface_terrain_base(self,pos:WorldPos)->str:
        f=self.sample_fields(pos); e,m,t=f.elevation,f.moisture,f.temperature
        # Generator v2 preserves RC4 geography exactly for existing saves.
        # Generator v3+ uses reciprocal connector columns so every surface
        # entrance has a traversable underground continuation.
        if self.version <= 2:
            if e>=26500 and (hash_u64(self.world_seed,"cave-mouth",pos.x//3,pos.y//3)%997)==0:return "core:cave_mouth"
        elif e>=26500 and self._connector_span(pos.x,pos.y)>0:
            return "core:cave_mouth"
        if self.version>=8 and self.coast_morphology_version>0:
            coast_terrain=self._phase5_coast_terrain(pos,f)
            if coast_terrain is not None:
                return coast_terrain
        if self.version >= 6 and e < 26500:
            # Local slope converts the sea-level height difference to an
            # approximate horizontal shelf distance, preserving continents.
            ex=self.sample_fields(WorldPos(pos.x+2,pos.y,0)).elevation-self.sample_fields(WorldPos(pos.x-2,pos.y,0)).elevation
            ey=self.sample_fields(WorldPos(pos.x,pos.y+2,0)).elevation-self.sample_fields(WorldPos(pos.x,pos.y-2,0)).elevation
            slope=max(24,(abs(ex)+abs(ey))//4)
            distance=(23800-e)*100//slope
            if e >= 23800:
                return 'core:shore' if -distance < 300 else 'core:sand'
            if distance < 300:return 'core:ocean_wade'
            if distance < 1200:return 'core:ocean_shallow'
            if distance < 2800:return 'core:ocean_shelf'
            return 'core:ocean_deep'
        if e<23800:return "core:water"
        if e<26500:return "core:sand"
        if e>52500:return "core:rock"
        if t<15000:return "core:tundra"
        if self.version <= 3:
            if m>39000 and 17000<t<56000:
                if (hash_u64(self.world_seed,"berries",pos.x,pos.y)%37)==0:return "core:berry_thicket"
                return "core:forest"
            if m<17000 and t>39000:return "core:scrub"
            return "core:grass"
        # v4 biome classification is climate-first. Resource overlays provide
        # bushes/trees, so biome identity no longer flickers because one cell
        # happened to roll a berry-thicket decoration.
        if m<17500 and t>36000:return "core:scrub"
        if m>42500 and 16500<t<56500:return "core:forest"
        # Soft forest ecotone: only the wetter side of this continuous band is
        # forest. Because m is a broad field this creates coherent margins.
        if m>37500 and 19500<t<53500 and f.fertility>39000:return "core:forest"
        return "core:grass"

    def attach_hydrology(self, planner)->None:
        self.hydrology=planner

    def environment_at(self, pos: WorldPos):
        return self.environmental_fields.at(pos)

    def hydrology_at(self,pos:WorldPos):
        if self.version < 5 or pos.z != 0 or self.hydrology is None:
            return None
        return self.hydrology.surface_at(pos)

    @staticmethod
    def _sign(v:int)->int:
        return -1 if v<0 else 1 if v>0 else 0

    def _river_current_at(self,pos:WorldPos,*,prepared_only:bool=False):
        hydro=self.hydrology
        if hydro is None or pos.z!=0:return None
        if prepared_only:
            domain=hydro.cached_domain(*hydro.domain_for_world(pos.x,pos.y))
        else:
            domain=hydro.load_or_generate(*hydro.domain_for_world(pos.x,pos.y), persist=False)
        if domain is None:return None
        spacing=domain.lattice_spacing; node_x=pos.x//spacing; node_y=pos.y//spacing
        best=None
        for gy in range(node_y-2,node_y+3):
            for gx in range(node_x-2,node_x+3):
                idx=domain.global_index(gx,gy)
                if idx is None: continue
                cls=int(domain.river_class[idx]); target=int(domain.flow_to[idx])
                if cls<=0 or target<0: continue
                tx,ty=domain.global_node_xy(target)
                acc=int(domain.accumulation[idx])
                if int(getattr(domain,'version',1))>=2 and len(getattr(domain,'channel_gradient',()))==domain.width*domain.height:
                    gradient=int(domain.channel_gradient[idx])
                    upstream=hydro._upstream_river_count(domain,idx)
                    fp=int(domain.floodplain_strength[idx])
                    primary,secondary,width,_=hydro._channel_paths(
                        gx,gy,tx,ty,gradient,cls,acc,fp,upstream
                    )
                    if not (
                        hydro._polyline_contains(pos.x,pos.y,primary,width)
                        or (secondary and hydro._polyline_contains(pos.x,pos.y,secondary,width))
                    ):
                        continue
                else:
                    ax,ay=gx*spacing,gy*spacing; bx,by=tx*spacing,ty*spacing
                    mx,my=hydro._meander_midpoint(gx,gy,tx,ty)
                    width=2 if cls==1 else 4 if cls==2 else 7
                    if not (hydro._segment_contains(pos.x,pos.y,ax,ay,mx,my,width) or hydro._segment_contains(pos.x,pos.y,mx,my,bx,by,width)):
                        continue
                row=(cls,acc,idx,gx,gy,tx,ty)
                if best is None or row[:2]>best[:2]: best=row
        if best is None:return None
        cls,acc,idx,gx,gy,tx,ty=best
        dx=self._sign(tx-gx); dy=self._sign(ty-gy)
        speed=max(18,min(96,18+cls*19+min(24,acc//320)))
        return SurfaceCurrent(kind='river',dx=dx,dy=dy,speed=speed)

    def _ocean_current_at(self,pos:WorldPos):
        # Deterministic vector field for large-scale marine circulation.
        # Using a curl-like noise field avoids static water without making the
        # renderer or simulation invent tile-by-tile random behavior.
        sample=lambda x,y:self._value_noise('ocean-current-v1',x,y,192)
        curl_x=sample(pos.x,pos.y+96)-sample(pos.x,pos.y-96)
        curl_y=sample(pos.x+96,pos.y)-sample(pos.x-96,pos.y)
        dx=-curl_x; dy=curl_y
        # Broad zonal bias keeps open ocean moving in coherent bands.
        zonal=self._value_noise('ocean-current-zonal-v1',0,pos.y+17011,768)-32768
        meridional=self._value_noise('ocean-current-meridional-v1',pos.x-9017,0,896)-32768
        dx += zonal//5
        dy += meridional//7
        # Near coasts, rotate part of the flow alongshore so shallows/estuaries
        # feel connected to the shoreline rather than like still pools.
        sea_level=23800
        land_e=int(self.sample_fields(WorldPos(pos.x+24,pos.y,0)).elevation>=sea_level)
        land_w=int(self.sample_fields(WorldPos(pos.x-24,pos.y,0)).elevation>=sea_level)
        land_s=int(self.sample_fields(WorldPos(pos.x,pos.y+24,0)).elevation>=sea_level)
        land_n=int(self.sample_fields(WorldPos(pos.x,pos.y-24,0)).elevation>=sea_level)
        nx,ny=land_e-land_w, land_s-land_n
        if nx or ny:
            orient=1 if self._value_noise('ocean-current-coast-turn-v1',pos.x,pos.y,384)>=32768 else -1
            dx += (-ny)*orient*9000
            dy += nx*orient*9000
        sdx=self._sign(dx); sdy=self._sign(dy)
        speed=max(20,min(84,20+abs(dx)//7000+abs(dy)//7000 + (10 if (nx or ny) else 0)))
        return SurfaceCurrent(kind='ocean_shore' if (nx or ny) else 'ocean', dx=sdx, dy=sdy, speed=speed)

    def current_at(self,pos:WorldPos,*,prepared_only:bool=False):
        if pos.z!=0:return None
        if self.version>=8 and self.coast_morphology_version>=2 and self.hydrology is not None:
            domain=self.hydrology.cached_domain(*self.hydrology.domain_for_world(pos.x,pos.y))
            mouth=self.coastal_mouths.at(pos,domain,prepared_only=prepared_only)
            if mouth and 'estuary' in mouth[0] and mouth[2]>=0:
                _,plan,index=mouth
                path=((plan.primary,)+plan.branches)[index]
                return SurfaceCurrent('estuary',self._sign(path[-1][0]-path[0][0]),self._sign(path[-1][1]-path[0][1]),max(18,min(65,18+plan.branch_discharge[index]//80)))
        if self.version>=6 and self._surface_terrain_base(pos) in {'core:ocean_shelf','core:ocean_deep'}:
            return self._ocean_current_at(pos)
        surface=None
        if self.version>=5 and self.hydrology is not None:
            surface=self.hydrology.surface_at(pos, prepared_only=prepared_only)
        if surface and int(getattr(surface,'river_class',0) or 0)>0:
            current=self._river_current_at(pos,prepared_only=prepared_only)
            if current is not None:return current
        if self.sample_fields(pos).elevation < 23800:
            return self._ocean_current_at(pos)
        return None

    def _surface_terrain(self,pos:WorldPos)->str:
        base=self._surface_terrain_base(pos)
        if self.version < 5 or self.hydrology is None:
            return base
        # Preserve special entrances and existing ocean. Hydrology modifies the
        # terrestrial surface around them, not unrelated vertical/site state.
        if base in {"core:cave_mouth","core:water"}:
            return base
        surface=self.hydrology.surface_at(pos)
        if self.version>=8 and self.coast_morphology_version>=2 and surface.terrain_override in {'core:estuary_shallow','core:estuary_deep','core:tidal_flat','core:shore'}:
            return surface.terrain_override or base
        if self.version >= 6:
            if base.startswith('core:ocean_'):
                # River mouths inherit drainage geometry; salinity mixing is
                # bounded to the nearshore band, not a discovery-based effect.
                if surface.river_class and base in {'core:ocean_wade','core:ocean_shallow'}:
                    return 'core:estuary_shallow' if base=='core:ocean_wade' else 'core:estuary_deep'
                return base
            if base == 'core:shore' and not surface.river_class:
                return base
            if surface.river_class and self.sample_fields(pos).elevation < 24500:
                return 'core:estuary_shallow' if surface.river_depth_class==1 else 'core:estuary_deep'
        return surface.terrain_override or base

    def _underground_terrain(self,pos:WorldPos)->str:
        depth=abs(pos.z)
        if self.version >= 7 and self.caves is not None:
            return self.caves.terrain_at(pos)
        if self.version <= 2:
            # Exact legacy RC4 shaft rule.  Kept behind the generator-version
            # boundary so loading an old save never relocates caves/shafts.
            if hash_u64(self.world_seed,"shaft",pos.x,pos.y)%701==0:return "core:shaft"
        else:
            # Natural connectors are reciprocal across z-levels. The nearby
            # landing chamber is forced open so descent never lands in stone.
            if self.has_connector(pos):return "core:shaft"
            if self._near_connector_chamber(pos):return "core:cave_floor"
        macro=self._value_noise(f"cave:{depth}:macro",pos.x,pos.y,28)
        fine=self._value_noise(f"cave:{depth}:fine",pos.x+depth*101,pos.y-depth*79,9)
        open_score=(macro*3+fine*2)//5
        if open_score<31000:
            aq=hash_u64(self.world_seed,"aquifer",pos.x//2,pos.y//2,pos.z)%1000
            if depth>1 and aq<18:return "core:aquifer"
            ore=hash_u64(self.world_seed,"ore",pos.x,pos.y,pos.z)%1000
            iron_chance=min(140,35+depth*8); coal_chance=min(180,55+depth*9)
            if ore<iron_chance:return "core:iron_vein"
            if ore<iron_chance+coal_chance:return "core:coal_seam"
            return "core:cave_wall"
        return "core:cave_floor"
    def terrain_at(self,pos:WorldPos)->str:
        return self._surface_terrain(pos) if pos.z>=0 else self._underground_terrain(pos)
    def generate_chunk(self,key:ChunkKey)->Chunk:
        chunk=Chunk.empty(key); origin=chunk_origin(key)
        for ly in range(CHUNK_SIZE):
            for lx in range(CHUNK_SIZE):
                pos=WorldPos(origin.x+lx,origin.y+ly,key.z)
                chunk.set(lx,ly,self.registry.terrain_index(self.terrain_at(pos)))
        self.sites.overlay(key,chunk,self.registry)
        if self.version>=3 and key.z<0:
            # Historical-site overlays are content, not topology authority.
            # Re-apply protected natural connector columns/chambers so a ruin
            # can surround a cave shaft but can never sever vertical travel.
            for ly in range(CHUNK_SIZE):
                for lx in range(CHUNK_SIZE):
                    pos=WorldPos(origin.x+lx,origin.y+ly,key.z)
                    if self.has_connector(pos):chunk.set(lx,ly,self.registry.terrain_index("core:shaft"))
                    elif self._near_connector_chamber(pos):chunk.set(lx,ly,self.registry.terrain_index("core:cave_floor"))
        return chunk
