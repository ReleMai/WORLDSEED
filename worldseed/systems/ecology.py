from __future__ import annotations
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.core.rng import PCG32, derive_seed, hash_u64
from worldseed.systems.state import LivingWorldState, PopulationCohort, CreatureState

ECO_CELL=256
class EcologySystem:
    def __init__(self,state:LivingWorldState,registry:ContentRegistry,seed:bytes,world=None):
        self.state=state;self.registry=registry;self.seed=seed;self.world=world
    def _cell(self,pos:WorldPos)->tuple[int,int]:return pos.x//ECO_CELL,pos.y//ECO_CELL

    def _surface_suitability(self,cx:int,cy:int,sp)->int:
        if not self.world:return 60
        matches=0;climate=0;total=0
        # deterministic 4x4 sampling captures mixed ecotones without scanning the whole cell
        for gy in range(4):
            for gx in range(4):
                x=cx*ECO_CELL+32+gx*64;y=cy*ECO_CELL+32+gy*64;p=WorldPos(x,y,0)
                tid=self.world.tile_at(p).terrain_id.split(':')[-1]
                fields=self.world.generator.sample_fields(p);total+=1
                if tid in sp.habitats or ('forest' in sp.habitats and tid=='berry_thicket'):matches+=1
                if sp.min_temp<=fields.temperature<=sp.max_temp and sp.min_moisture<=fields.moisture<=sp.max_moisture:climate+=1
        habitat=matches*100//max(1,total);clim=climate*100//max(1,total)
        return habitat*3//4+clim//4

    def ensure_cell(self,cx:int,cy:int,z:int=0)->None:
        layer=0 if z>=0 else z
        for sid,sp in self.registry.species.items():
            key=f"{cx},{cy},{layer}:{sid}"
            if key in self.state.cohorts:continue
            rng=PCG32(derive_seed(self.seed,"cohort",cx,cy,layer,sid))
            if layer<0:
                suitability=80 if 'underground' in sp.habitats else 0
            else:
                suitability=0 if 'underground' in sp.habitats else self._surface_suitability(cx,cy,sp)
            if suitability<12 or rng.randbelow(100)>=min(95,35+suitability//2):base=0
            else:
                k=max(1,sp.carrying_capacity*suitability//100)
                base=max(1,k*(20+rng.randbelow(50))//100)
            self.state.cohorts[key]=PopulationCohort(key,cx,cy,sid,base,90,70,0,layer)

    def daily_update(self)->None:
        by_cell={}
        for c in self.state.cohorts.values():by_cell.setdefault((c.region_x,c.region_y,c.z),[]).append(c)
        for cohorts in by_cell.values():
            prey_total=sum(c.count for c in cohorts if self.registry.species[c.species_id].diet=='herbivore')
            omnivore_total=sum(c.count for c in cohorts if self.registry.species[c.species_id].diet=='omnivore')
            predators=[c for c in cohorts if self.registry.species[c.species_id].diet=='carnivore'];predator_demand=sum(c.count for c in predators)*2
            for c in cohorts:
                sp=self.registry.species[c.species_id];n=c.count;k=max(1,sp.carrying_capacity);births=(sp.reproduction*n*max(0,k-n))//(1000*k);deaths=(sp.mortality*n)//1000
                if sp.diet=='herbivore' and prey_total>0:deaths+=min(n,(predator_demand*n)//max(1,prey_total*12))
                if sp.diet=='carnivore' and prey_total+omnivore_total < c.count*3:deaths+=max(0,c.count//12)
                c.count=max(0,min(k*2,n+births-deaths));c.mean_health=max(20,min(100,c.mean_health+(2 if births>=deaths else -2)))
        self.reconcile_materialized()

    def _spawn_position(self,ax:int,ay:int,layer:int,sp,ordinal:int)->tuple[int,int]:
        rng=PCG32(derive_seed(self.seed,'individual',ax,ay,layer,sp.id,ordinal))
        fallback=(ax*ECO_CELL+rng.randbelow(ECO_CELL),ay*ECO_CELL+rng.randbelow(ECO_CELL))
        if not self.world:return fallback
        for attempt in range(28):
            x=ax*ECO_CELL+rng.randbelow(ECO_CELL);y=ay*ECO_CELL+rng.randbelow(ECO_CELL);p=WorldPos(x,y,layer)
            tile=self.world.tile_at(p);tid=tile.terrain_id.split(':')[-1]
            if not tile.terrain.passable:continue
            if layer<0:
                if 'underground' in sp.habitats:return x,y
            else:
                fields=self.world.generator.sample_fields(p)
                habitat_ok=tid in sp.habitats or ('forest' in sp.habitats and tid=='berry_thicket')
                if habitat_ok and sp.min_temp<=fields.temperature<=sp.max_temp and sp.min_moisture<=fields.moisture<=sp.max_moisture:return x,y
        return fallback

    def materialize_near(self,pos:WorldPos,radius_cells:int=0)->None:
        cx,cy=self._cell(pos);layer=0 if pos.z>=0 else pos.z
        for ax in range(cx-radius_cells,cx+radius_cells+1):
            for ay in range(cy-radius_cells,cy+radius_cells+1):
                self.ensure_cell(ax,ay,layer)
                for sid,sp in self.registry.species.items():
                    ck=f"{ax},{ay},{layer}:{sid}";cohort=self.state.cohorts[ck]
                    if cohort.count<=0:continue
                    prefix=f"wild:{ax}:{ay}:{layer}:";existing=[c for c in self.state.creatures.values() if c.species_id==sid and c.uid.startswith(prefix)]
                    target=min(max(1,sp.group_max),4,max(0,cohort.count//max(1,sp.carrying_capacity//5)))
                    for ordinal in range(len(existing),target):
                        x,y=self._spawn_position(ax,ay,layer,sp,ordinal);uid=f"{prefix}{sid}:{ordinal}";self.state.creatures[uid]=CreatureState(uid,sid,x,y,layer,sp.max_hp,cohort_key=ck)

    def reconcile_materialized(self)->None:
        grouped={}
        for c in self.state.creatures.values():
            if c.cohort_key:grouped.setdefault(c.cohort_key,[]).append(c)
        for ck,individuals in grouped.items():
            cohort=self.state.cohorts.get(ck)
            if not cohort:continue
            sp=self.registry.species.get(cohort.species_id)
            if not sp:continue
            target=min(cohort.count,max(1,sp.group_max),4,max(0,cohort.count//max(1,sp.carrying_capacity//5)))
            ordinary=sorted((c for c in individuals if not c.notable),key=lambda c:c.uid,reverse=True);excess=max(0,len(individuals)-target)
            for c in ordinary[:excess]:self.state.creatures.pop(c.uid,None)

    def record_individual_death(self,creature:CreatureState)->None:
        if creature.cohort_key and creature.cohort_key in self.state.cohorts:
            cohort=self.state.cohorts[creature.cohort_key];cohort.count=max(0,cohort.count-1)

    def dematerialize_far(self,player_pos:WorldPos,max_distance:int=420)->None:
        remove=[]
        for uid,c in self.state.creatures.items():
            if c.notable:continue
            # Wounded or actively alarmed animals remain physical for a much
            # larger chase envelope so a hunt cannot erase its target merely
            # because the player crossed an ecology/materialization boundary.
            active=bool(c.wounds) or c.behavior not in ("calm","")
            limit=max_distance*2 if active else max_distance
            if c.z!=player_pos.z or abs(c.x-player_pos.x)+abs(c.y-player_pos.y)>limit:remove.append(uid)
        for uid in remove:self.state.creatures.pop(uid,None)

    def update_local_ai(self,player_pos:WorldPos)->list[str]:
        messages=[]
        for c in self.state.creatures.values():
            if c.z!=player_pos.z or abs(c.x-player_pos.x)>30 or abs(c.y-player_pos.y)>20:continue
            sp=self.registry.species[c.species_id];dist=abs(c.x-player_pos.x)+abs(c.y-player_pos.y)
            if sp.aggression>=50 and dist<8:
                dx=0 if c.x==player_pos.x else (1 if player_pos.x>c.x else -1);dy=0 if c.y==player_pos.y else (1 if player_pos.y>c.y else -1)
                if abs(player_pos.x-c.x)>abs(player_pos.y-c.y):c.x+=dx
                else:c.y+=dy
                if dist<=1:messages.append(c.uid)
            elif sp.aggression<20 and dist<5:
                c.x += -1 if player_pos.x>c.x else 1 if player_pos.x<c.x else 0;c.y += -1 if player_pos.y>c.y else 1 if player_pos.y<c.y else 0
        return messages
