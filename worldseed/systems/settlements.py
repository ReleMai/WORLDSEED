from __future__ import annotations
from worldseed.core.rng import PCG32, derive_seed, hash_u64
from worldseed.systems.state import LivingWorldState, SettlementState
from worldseed.systems.names import place_name
from worldseed.systems.history import HistorySystem

class SettlementLifecycleSystem:
    def __init__(self,state:LivingWorldState,seed:bytes,history:HistorySystem):self.state=state;self.seed=seed;self.history=history
    def monthly_update(self,minute:int)->None:
        month=minute//(30*1440)
        for s in list(self.state.settlements.values()):
            if s.population<=5 or (s.food_stress>=100 and s.population<15):
                self.history.record('collapse',f'{s.name} ceased to function as a permanent settlement.',minute,s.region_x,s.region_y,[s.uid],salience=75)
                # inhabitants are marked migrant rather than deleted from history.
                for n in self.state.npcs.values():
                    if n.settlement_id==s.uid and n.alive:n.occupation='migrant';n.goal='migrate'
                s.population=max(0,s.population);s.buildings['ruins']=sum(s.buildings.values());s.buildings['house']=0;s.food_stress=100
                continue
            # large, stable settlements can seed a daughter settlement in an adjacent unrealized region.
            if s.population>=180 and s.food_stress<25 and hash_u64(self.seed,'found-colony',s.uid,month)%100<12:
                dirs=((1,0),(-1,0),(0,1),(0,-1));dx,dy=dirs[hash_u64(self.seed,'colony-dir',s.uid,month)%4];rx,ry=s.region_x+dx,s.region_y+dy
                uid=f'settlement:{rx}:{ry}'
                # Tier E is deterministic potential only.  Do not recursively
                # instantiate civilization into infinite unvisited space merely
                # because a realized settlement is prosperous.  Exploration (or
                # an explicit future macrohistory realization) promotes regions.
                realized=f'{rx},{ry}' in set(self.state.realized_regions)
                if realized and uid not in self.state.settlements:
                    rng=PCG32(derive_seed(self.seed,'colony',s.uid,month));pop=max(12,s.population//10);s.population-=pop
                    child=SettlementState(uid,place_name(rng),rx,ry,rx*512+96+rng.randbelow(320),ry*512+96+rng.randbelow(320),pop,s.culture_id,s.religion_id,s.faction_id,120,{'core:wheat':40,'core:wood':20,'core:stone':15,'core:wheat_seed':10}, {}, {'house':max(2,pop//6),'farm':2},15,dict(s.law),list(s.knowledge))
                    self.state.settlements[uid]=child;self.history.record('foundation',f'Settlers from {s.name} founded {child.name}.',minute,rx,ry,[s.uid,child.uid],salience=60)
