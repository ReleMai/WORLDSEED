from __future__ import annotations
from dataclasses import dataclass
from collections import OrderedDict
from worldseed.config import RESOURCEGEN_VERSION, CHUNK_SIZE, RESOURCE_CHUNK_CACHE_LIMIT
from worldseed.core.coords import WorldPos, ChunkKey, split_world
from worldseed.core.rng import hash_u64
from worldseed.core.clock import SEASONS, DAYS_PER_SEASON
from worldseed.entities.components import Inventory
from worldseed.systems.state import LivingWorldState, pos_key

@dataclass(frozen=True, slots=True)
class FeatureView:
    feature_id: str
    stage: str = "mature"

class ResourceSystem:
    """Deterministic habitat-aware resource layer with persistent depletion.

    Ground terrain remains authoritative. Natural resources are overlays selected
    from data definitions using terrain, moisture, temperature, season and patch
    clustering. This keeps trees/forage/stone from rewriting the underlying biome.
    """
    def __init__(self,state:LivingWorldState,registry,world_seed:bytes,world,version:int|None=None):
        self.state=state; self.registry=registry; self.seed=world_seed; self.world=world
        self.settlement_overlay=None
        self.version=int(getattr(world,"resourcegen_version",RESOURCEGEN_VERSION) if version is None else version)
        self.revision=0
        self._raw_cache={}
        self._structural_cache={}
        self._feature_chunk_cache:OrderedDict[tuple[int,int,str],tuple[str|None,...]]=OrderedDict()
        self._feature_chunk_misses:set[tuple[int,int,str]]=set()
        self._feature_chunk_limit=max(16,int(RESOURCE_CHUNK_CACHE_LIMIT))
        self.by_terrain={}
        for f in registry.resources.values():
            # Expansion flora begins with resourcegen v5. Excluding these rows
            # before any weighted choice preserves every legacy v1-v4 cell.
            if self.version<5 and 'salvage_expansion' in f.tags:continue
            for t in (f.terrains or tuple(registry.terrains)):
                self.by_terrain.setdefault(t,[]).append(f)
        for rows in self.by_terrain.values(): rows.sort(key=lambda f:f.id)

    def attach_settlement_physicalization(self,overlay)->None:
        """Bind the active physical settlement plan as a read-time blocker.

        Prepared natural-resource chunks remain deterministic cache data; this
        only suppresses their materialization/interaction where civilization
        owns the physical space.
        """
        self.settlement_overlay=overlay

    def _season(self,minute:int|None=None)->str:
        m=self.state.clock_minute if minute is None else minute
        day=(m//1440)%(DAYS_PER_SEASON*4)
        return SEASONS[(day//DAYS_PER_SEASON)%4]

    def _cache_feature_chunk(self,key:tuple[int,int,str],values:tuple[str|None,...])->None:
        self._feature_chunk_cache[key]=values;self._feature_chunk_cache.move_to_end(key)
        self._feature_chunk_misses.discard(key)
        while len(self._feature_chunk_cache)>self._feature_chunk_limit:
            self._feature_chunk_cache.popitem(last=False)
    def _load_prepared_feature_chunk(self,cx:int,cy:int,season:str)->tuple[str|None,...]|None:
        key=(cx,cy,season)
        cached=self._feature_chunk_cache.get(key)
        if cached is not None:
            self._feature_chunk_cache.move_to_end(key);return cached
        if key in self._feature_chunk_misses:return None
        loader=getattr(self.world.delta_source,'load_generated_resource_chunk',None)
        if callable(loader):
            values=loader(ChunkKey(cx,cy,0),self.version,season)
            if values is not None and len(values)==CHUNK_SIZE*CHUNK_SIZE:
                values=tuple(values);self._cache_feature_chunk(key,values);return values
        self._feature_chunk_misses.add(key);return None
    def _build_feature_chunk(self,cx:int,cy:int,season:str)->tuple[str|None,...]:
        x0=cx*CHUNK_SIZE;y0=cy*CHUNK_SIZE;values=[]
        for ly in range(CHUNK_SIZE):
            y=y0+ly
            for lx in range(CHUNK_SIZE):
                x=x0+lx;tid=self.world.tile_at(WorldPos(x,y,0)).terrain_id
                values.append(self._raw_feature(x,y,tid,season))
        return tuple(values)
    @staticmethod
    def _ordered_chunk_offsets(radius:int):
        r=max(0,int(radius));rows=[(dx,dy) for dy in range(-r,r+1) for dx in range(-r,r+1)]
        rows.sort(key=lambda q:(max(abs(q[0]),abs(q[1])),abs(q[0])+abs(q[1]),q[1],q[0]));return rows
    def pre_generate(self,center:WorldPos,radius_chunks:int,progress=None,persist:bool=True)->dict[str,int]:
        """Prepare current-season natural-resource placement around a spawn.

        The prepared map stores only deterministic base placement. Depletion,
        regrowth, buildings, crops and soil remain live simulation overlays.
        """
        center_key,_,_=split_world(center);season=self._season();offsets=self._ordered_chunk_offsets(radius_chunks);total=len(offsets)
        generated=0;reused=0;storer=getattr(self.world.delta_source,'store_generated_resource_chunk',None)
        for idx,(dx,dy) in enumerate(offsets,1):
            cx,cy=center_key.x+dx,center_key.y+dy;key=(cx,cy,season)
            values=self._load_prepared_feature_chunk(cx,cy,season)
            if values is None:
                values=self._build_feature_chunk(cx,cy,season);generated+=1;self._cache_feature_chunk(key,values)
                if persist and callable(storer):storer(ChunkKey(cx,cy,0),self.version,season,values)
            else:reused+=1
            if progress:progress(idx,total,f'chunk {cx}, {cy}')
        if persist:
            commit=getattr(self.world.delta_source,'commit_generated',None)
            if callable(commit):commit()
        # Per-cell candidate caches are build scratch space. Prepared chunk maps
        # are the compact runtime representation, so release the much larger
        # scratch dictionaries before gameplay begins.
        self._raw_cache.clear();self._structural_cache.clear()
        return {'total':total,'generated':generated,'reused':reused}
    def _base_feature(self,pos:WorldPos,minute:int|None=None)->str|None:
        if pos.z != 0:return None
        if self.settlement_overlay is not None and self.settlement_overlay.clears_natural_feature(pos):
            return None
        key=pos_key(pos.x,pos.y,pos.z)
        if key in self.state.structures or key in self.state.containers or key in self.state.crops or key in self.state.soils:
            return None
        tid=self.world.tile_at(pos).terrain_id;season=self._season(minute)
        ck, lx, ly=split_world(pos);prepared=self._load_prepared_feature_chunk(ck.x,ck.y,season)
        fid=prepared[ly*CHUNK_SIZE+lx] if prepared is not None else self._raw_feature(pos.x,pos.y,tid,season)
        # Preserve prepared resourcegen v5 chunks and existing feature choices.
        # Only empty resource cells gain a deterministic shoreline reed patch.
        if fid is None:
            fid=self._shoreline_reed(pos,tid)
        if not fid:return None
        f=self.registry.resources.get(fid)
        if not f:return None
        # A player-authored terrain delta can invalidate the original prepared
        # surface (for example excavating a cave mouth). Keep the prepared data
        # immutable and simply suppress incompatible placement at read time.
        if f.terrains and tid not in f.terrains:return None
        return fid

    def _shoreline_reed(self,pos:WorldPos,tid:str)->str|None:
        """Readable reed patches on freshwater shores, wetlands and nearby grass.

        Earlier v5 reads offered reeds mainly on shallow river water and
        gated them behind a high climate moisture threshold. Bank habitats
        count as wet even if the broad climate sample is relatively dry.
        """
        if self.version<5 or "core:reed_bed" not in self.registry.resources:
            return None
        chance={
            "core:riverbank":520,"core:wetland":480,
            "core:floodplain":280,"core:river_shallow":300,
            "core:grass":230,
        }.get(tid,0)
        if not chance:return None
        if hash_u64(self.seed,"shore-reed-patch-v2",pos.x//6,pos.y//6)%1000>=740:
            return None
        if hash_u64(self.seed,"shore-reed-cell-v2",pos.x,pos.y)%1000>=chance:
            return None
        if tid=="core:grass":
            nearby={"core:riverbank","core:wetland","core:floodplain",
                    "core:river_shallow"}
            if not any(self.world.tile_at(WorldPos(pos.x+dx,pos.y+dy,0)).terrain_id in nearby
                       for dx,dy in ((1,0),(-1,0),(0,1),(0,-1))):
                return None
        fields=self.world.generator.sample_fields(pos)
        reed=self.registry.resources["core:reed_bed"]
        return reed.id if reed.min_temp<=fields.temperature<=reed.max_temp else None

    def _eligible_rows(self,x:int,y:int,tid:str,season:str):
        rows=self.by_terrain.get(tid,())
        if not rows:return (),None
        fields=self.world.generator.sample_fields(WorldPos(x,y,0))
        eligible=[]
        for f in rows:
            if 'salvage_expansion' in f.tags:
                rarity=5 if 'rare_flora' in f.tags else 28 if 'uncommon_flora' in f.tags else 120
                if hash_u64(self.seed,'salvage-flora-rarity',self.version,f.id,x,y)%1000>=rarity:continue
            if f.seasons and season not in f.seasons:continue
            if not (f.min_temp <= fields.temperature <= f.max_temp):continue
            if not (f.min_moisture <= fields.moisture <= f.max_moisture):continue
            eligible.append(f)
        return tuple(eligible),fields

    @staticmethod
    def _is_structural(f)->bool:
        return bool(f.blocks_movement or "tree" in f.tags or "boulder" in f.tags or "natural_container" in f.tags)

    def _structural_budget(self,tid:str,fields)->int:
        # Per-thousand chance before minimum-distance thinning.  The biome tile
        # itself communicates forest/rock identity; blocking props are accents,
        # not a second wall layer laid over every cell.
        base={
            "core:forest":100, "core:berry_thicket":85, "core:grass":50,
            "core:scrub":40, "core:tundra":28, "core:rock":92, "core:sand":12,
        }.get(tid,35)
        if fields is None:return base
        if tid in {"core:forest","core:grass","core:berry_thicket"}:
            # Wetter/fertile country supports denser stands without letting any
            # local patch become an impassable tree carpet.
            bonus=max(-35,min(55,(fields.moisture-33000)//420 + (fields.fertility-33000)//650))
            base+=bonus
        return max(8,min(300,base))

    def _ground_budget(self,tid:str,fields)->int:
        # Ground forage should read as discoverable pockets rather than a
        # collectible overlay on nearly every other tile. Structural scenery
        # has its own budget; this budget is only for loose/harvestable ground
        # resources such as branches, stones, herbs, berries and clay.
        base={
            "core:forest":155, "core:berry_thicket":185, "core:grass":125,
            "core:scrub":108, "core:tundra":72, "core:rock":92, "core:sand":55,
        }.get(tid,78)
        if fields is not None and tid in {"core:forest","core:grass","core:scrub"}:
            base+=max(-35,min(55,(fields.fertility-32000)//500))
        return max(24,min(240,base))

    def _weighted_pick(self,rows,x:int,y:int,kind:str):
        if not rows:return None
        best=None
        for f in rows:
            # Data density remains the relative species/resource preference, but
            # no longer acts as an independent placement roll for every feature.
            patch=max(1,int(f.patch_scale))
            patch_roll=hash_u64(self.seed,"resource3-patch",self.version,f.id,x//patch,y//patch)%1000
            affinity=max(1,int(f.density)+max(0,520-int(patch_roll))//3)
            raw=hash_u64(self.seed,"resource3-choice",self.version,kind,x,y,f.id)%1_000_000
            score=raw//affinity
            candidate=(score,f.id,f)
            if best is None or candidate[:2]<best[:2]:best=candidate
        return None if best is None else best[2]

    def _structural_candidate(self,x:int,y:int,tid:str,season:str):
        key=(x,y,tid,season)
        if key in self._structural_cache:return self._structural_cache[key]
        value=self._structural_candidate_uncached(x,y,tid,season)
        if len(self._structural_cache)>=131072:self._structural_cache.clear()
        self._structural_cache[key]=value
        return value

    def _structural_candidate_uncached(self,x:int,y:int,tid:str,season:str):
        eligible,fields=self._eligible_rows(x,y,tid,season)
        rows=tuple(f for f in eligible if self._is_structural(f))
        if not rows:return None
        budget=self._structural_budget(tid,fields)
        gate=hash_u64(self.seed,"resource3-struct-gate",self.version,x,y)%1000
        if gate>=budget:return None
        return self._weighted_pick(rows,x,y,"struct")

    def _structural_spaced(self,x:int,y:int,tid:str,season:str,f)->bool:
        # Never consume a terrain bottleneck with an optional natural prop.
        # Water/cliffs/cave mouths define topology; trees and boulders should
        # decorate that topology rather than accidentally sever it.
        if tid == "core:cave_mouth":return False
        passable_neighbors=0
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
            np=WorldPos(x+dx,y+dy,0); nt=self.world.tile_at(np)
            if nt.terrain_id == "core:cave_mouth":return False
            if nt.terrain.passable:passable_neighbors+=1
        if passable_neighbors <= 2:return False
        # Deterministic Matérn-style thinning: among cardinally adjacent blocker
        # candidates only the lowest priority survives.  This guarantees that
        # trees/boulders cannot form solid orthogonal walls while retaining
        # irregular diagonals, groves and rocky clusters.
        priority=hash_u64(self.seed,"resource3-struct-priority",self.version,x,y)
        for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
            nx,ny=x+dx,y+dy
            ntid=self.world.tile_at(WorldPos(nx,ny,0)).terrain_id
            nf=self._structural_candidate(nx,ny,ntid,season)
            if nf is None:continue
            np=hash_u64(self.seed,"resource3-struct-priority",self.version,nx,ny)
            if (np,nx,ny)<(priority,x,y):return False
        return True

    def _raw_feature(self,x:int,y:int,tid:str,season:str)->str|None:
        key=(x,y,tid,season)
        if key in self._raw_cache:return self._raw_cache[key]
        value=self._raw_feature_uncached(x,y,tid,season)
        if len(self._raw_cache)>=131072:self._raw_cache.clear()
        self._raw_cache[key]=value
        return value

    def _raw_feature_uncached(self,x:int,y:int,tid:str,season:str)->str|None:
        rows=self.by_terrain.get(tid,())
        if not rows:return None
        # Preserve resourcegen v1/v2 exactly for worlds explicitly pinned to an
        # older resource-generation version. New RC10 worlds and migrated RC9
        # saves use v3's biome budget + spacing model.
        if self.version <= 2:
            fields=self.world.generator.sample_fields(WorldPos(x,y,0))
            candidates=[]
            for f in rows:
                if f.seasons and season not in f.seasons:continue
                if not (f.min_temp <= fields.temperature <= f.max_temp):continue
                if not (f.min_moisture <= fields.moisture <= f.max_moisture):continue
                patch=max(1,f.patch_scale)
                grove=hash_u64(self.seed,"resource-patch",self.version,f.id,x//patch,y//patch)%1000
                local=hash_u64(self.seed,"resource-local",self.version,f.id,x,y)%1000
                threshold=min(930,max(0,f.density + max(0,430-int(grove))//2))
                if local < threshold:
                    score=hash_u64(self.seed,"resource-choice",self.version,x,y,f.id)%100000
                    structural=0 if self._is_structural(f) else 1
                    candidates.append((structural,score,f.id))
            return min(candidates)[2] if candidates else None

        eligible,fields=self._eligible_rows(x,y,tid,season)
        if not eligible:return None
        structural=self._structural_candidate(x,y,tid,season)
        if structural is not None and self._structural_spaced(x,y,tid,season,structural):
            return structural.id

        ground=tuple(f for f in eligible if not self._is_structural(f))
        if not ground:return None
        budget=self._ground_budget(tid,fields)
        # Broad patchiness makes forage occur in readable ecological pockets,
        # while a separate local roll prevents every cell in a rich patch from
        # receiving an overlay.
        patch=hash_u64(self.seed,"resource3-ground-patch",self.version,x//6,y//6)%1000
        local=hash_u64(self.seed,"resource3-ground-gate",self.version,x,y)%1000
        # Rich patches remain visibly rewarding, but most ground is left clear.
        # This preserves exploration/readability without making the world bare.
        threshold=max(12,min(330,budget + (115 if patch<220 else 30 if patch<470 else -60)))
        if local>=threshold:return None
        picked=self._weighted_pick(ground,x,y,"ground")
        return picked.id if picked else None

    def feature_at(self,pos:WorldPos,minute:int|None=None)->FeatureView|None:
        fid=self._base_feature(pos,minute)
        if not fid:return None
        return self._feature_view(fid,pos,minute)

    def prepared_feature_at(self,pos:WorldPos,minute:int|None=None)->FeatureView|None:
        """Observe only an already resident, prepared natural-feature cell.

        This never loads terrain/resource chunks, generates missing placement,
        changes LRU/miss caches or derives shoreline reeds from empty cells.
        Such reeds remain omitted until explicitly prepared by the simulation.
        Existing structures, containers, crops, soils and settlement clearing
        retain the same suppression authority as normal gameplay queries.
        """
        if pos.z!=0:return None
        if self.settlement_overlay is not None and self.settlement_overlay.clears_natural_feature(pos):
            return None
        pk=pos_key(pos.x,pos.y,pos.z)
        if pk in self.state.structures or pk in self.state.containers or pk in self.state.crops or pk in self.state.soils:
            return None
        tile=self.world.prepared_tile_at(pos)
        if tile is None:return None
        key,lx,ly=split_world(pos)
        values=self._feature_chunk_cache.get((key.x,key.y,self._season(minute)))
        if values is None:return None
        fid=values[ly*CHUNK_SIZE+lx]
        if not fid:return None
        definition=self.registry.resources.get(fid)
        if definition is None or (definition.terrains and tile.terrain_id not in definition.terrains):
            return None
        return self._feature_view(fid,pos,minute)

    def _feature_view(self,fid:str,pos:WorldPos,minute:int|None=None)->FeatureView|None:
        """Shared authoritative depletion/regrowth projection; no mutation."""
        minute=self.state.clock_minute if minute is None else minute
        harvested=self.state.resource_depletion.get(pos_key(pos.x,pos.y,pos.z))
        if harvested is None:return FeatureView(fid,"mature")
        f=self.registry.resources.get(fid)
        if not f:return None
        elapsed=max(0,minute-int(harvested))
        if "tree" in f.tags:
            if elapsed < 45*1440:return FeatureView(fid,"stump")
            if f.regrow_days and elapsed < f.regrow_days*1440:return FeatureView(fid,"sapling")
            return FeatureView(fid,"mature")
        if f.regrow_days and elapsed >= f.regrow_days*1440:return FeatureView(fid,"mature")
        return FeatureView(fid,"depleted")

    def is_harvestable(self,pos:WorldPos)->bool:
        fv=self.feature_at(pos)
        if fv and fv.stage=="mature":
            f=self.registry.resources.get(fv.feature_id)
            if f and "natural_container" in f.tags:return False
            return True
        t=self.world.tile_at(pos).terrain
        return pos.z<0 and bool(t.gather_item and t.gather_amount>0 and t.depleted_to)

    def blocks_movement(self,pos:WorldPos)->bool:
        fv=self.feature_at(pos)
        if not fv or fv.stage!="mature":return False
        f=self.registry.resources.get(fv.feature_id);return bool(f and f.blocks_movement)

    def blocks_sight(self,pos:WorldPos)->bool:
        fv=self.feature_at(pos)
        if not fv or fv.stage!="mature":return False
        f=self.registry.resources.get(fv.feature_id);return bool(f and f.blocks_sight)

    def description(self,pos:WorldPos)->str:
        fv=self.feature_at(pos)
        if fv:
            f=self.registry.resources.get(fv.feature_id)
            if f:
                if fv.stage=="stump":return f"Stump of {f.name.lower()}"
                if fv.stage=="sapling":return f"Young {f.name.lower()}"
                if fv.stage=="depleted":return f"Spent {f.name.lower()}"
                return f.name
        return self.world.tile_at(pos).terrain.name

    @staticmethod
    def _quality_name(tag:str)->str:
        return {"axe":"chop","pick":"mine","knife":"cut"}.get(tag,tag)

    @classmethod
    def _best_tool(cls,inv:Inventory,registry,tag:str|None)->int:
        if not tag:return 999
        quality=cls._quality_name(tag);best=0
        for iid,n in inv.items.items():
            item=registry.items.get(iid)
            if n>0 and item:
                best=max(best,item.quality(quality))
                if tag in item.tags:best=max(best,item.tool_power or 1)
        return best

    def tool_power(self,inv:Inventory,tag:str)->int:return self._best_tool(inv,self.registry,tag)

    def harvest(self,pos:WorldPos,inv:Inventory,minute:int)->tuple[bool,str,int,dict[str,int]]:
        fv=self.feature_at(pos,minute)
        if fv and fv.stage=="mature":
            f=self.registry.resources[fv.feature_id]
            if "natural_container" in f.tags:
                return False,f"Open, move, or break apart the {f.name.lower()} instead.",5,{}
            tool=self._best_tool(inv,self.registry,f.required_tool_tag)
            reed_bed=fv.feature_id=="core:reed_bed"
            # A knife/shears improve reed gathering but are not mandatory.
            reed_cutter=self._best_tool(inv,self.registry,"knife") if reed_bed else 0
            if tool < f.required_tool_power:
                need=f.required_tool_tag or "tool"
                return False,f"You need a suitable {need} to harvest the {f.name.lower()}.",5,{}
            tags=set(f.tags);skill_name='woodcutting' if 'tree' in tags else 'mining' if ('rock' in tags or 'ore' in tags or f.required_tool_tag=='pick') else 'foraging'
            skill=int(self.state.player_skills.get(skill_name,0));talent_bonus=1 if (skill_name=='woodcutting' and 'woodsman' in self.state.player_talents) or (skill_name=='mining' and 'stonewise' in self.state.player_talents) else 0
            out={}
            for iid,(lo,hi) in f.yields.items():
                span=max(1,hi-lo+1);amount=lo+(hash_u64(self.seed,"resource-yield",self.version,pos.x,pos.y,pos.z,iid)%span)
                if f.required_tool_tag and tool>=3:amount+=1
                if reed_bed and reed_cutter>0:amount+=1+min(2,reed_cutter//3)
                amount+=skill//5+talent_bonus
                inv.add(iid,amount);out[iid]=amount
            self.state.resource_depletion[pos_key(pos.x,pos.y,pos.z)]=minute
            self.revision+=1
            pretty=", ".join(f"{n} {self.registry.items[i].name.lower()}" for i,n in out.items())
            effort=max(30,100-skill*5-(min(35,reed_cutter*12) if reed_bed else 0))
            minutes=max(3,f.minutes*effort//100)
            detail=f" (foraging {skill}, cutter {reed_cutter})" if reed_bed else ""
            return True,f"You harvest {f.name.lower()}: {pretty}. Work time: {minutes} game minutes{detail}.",minutes,out
        t=self.world.tile_at(pos).terrain
        if pos.z<0 and t.gather_item and t.gather_amount>0 and t.depleted_to:
            tool=self._best_tool(inv,self.registry,"pick")
            if ("ore" in t.tags or "rock" in t.tags) and tool<1:return False,"You need a pick or mining tool to break this rock.",5,{}
            skill=int(self.state.player_skills.get('mining',0));talent=1 if 'stonewise' in self.state.player_talents else 0
            amount=t.gather_amount+(1 if tool>=4 and "ore" in t.tags else 0)+skill//5+talent
            inv.add(t.gather_item,amount);self.world.set_terrain(pos,t.depleted_to)
            minutes=max(8,25*max(45,100-skill*6)//100)
            return True,f"You mine {amount} {self.registry.items[t.gather_item].name.lower()} from the wall.",minutes,{t.gather_item:amount}
        return False,"There is nothing harvestable there.",5,{}

    def cleanup_regrown(self,minute:int)->None:
        remove=[]
        for key,when in self.state.resource_depletion.items():
            try:x,y,z=(int(q) for q in key.split(','))
            except Exception:continue
            fv=self.feature_at(WorldPos(x,y,z),minute)
            if fv and fv.stage=="mature" and minute>when:remove.append(key)
        for key in remove:self.state.resource_depletion.pop(key,None)
        if remove:self.revision+=1
