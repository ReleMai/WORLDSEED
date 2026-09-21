from __future__ import annotations
from worldseed.core.rng import hash_u64, PCG32, derive_seed
from worldseed.systems.state import LivingWorldState, NPCState, GraveState
from worldseed.systems.names import person_name
from worldseed.systems.history import HistorySystem

class FamilySystem:
    def __init__(self,state:LivingWorldState,seed:bytes,history:HistorySystem):self.state=state;self.seed=seed;self.history=history
    def monthly_update(self,minute:int)->None:
        # Age everyone approximately once per game-year at month boundary.
        month=minute//(30*1440)
        if month%4==0:
            for n in self.state.npcs.values():
                if n.alive:n.age+=1
        for town in self.state.settlements.values():
            adults=[n for n in self.state.npcs.values() if n.alive and n.settlement_id==town.uid and 18<=n.age<=55]
            singles=[n for n in adults if not n.spouse_uid]
            # deterministic marriages; relationship becomes explicit kinship rather than flavor.
            for i in range(0,len(singles)-1,2):
                a,b=singles[i],singles[i+1]
                if hash_u64(self.seed,'marriage',a.uid,b.uid,month)%100<8:
                    a.spouse_uid=b.uid;b.spouse_uid=a.uid;a.relationships.setdefault(b.uid,{"affection":35,"trust":35,"fear":0,"respect":15,"obligation":15,"familiarity":50});b.relationships.setdefault(a.uid,{"affection":35,"trust":35,"fear":0,"respect":15,"obligation":15,"familiarity":50})
                    self.history.record('marriage',f'{a.name} and {b.name} married in {town.name}.',minute,town.region_x,town.region_y,[a.uid,b.uid],salience=18)
            couples=[];seen=set()
            for a in adults:
                if a.spouse_uid and a.uid not in seen and a.spouse_uid in self.state.npcs:
                    b=self.state.npcs[a.spouse_uid];couples.append((a,b));seen|={a.uid,b.uid}
            for a,b in couples:
                if len(a.children)>=4:continue
                if hash_u64(self.seed,'birth',a.uid,b.uid,month)%100<5 and town.food_stress<65:
                    rng=PCG32(derive_seed(self.seed,'child',a.uid,b.uid,month));uid=self.state.uid('npc');child=NPCState(uid,person_name(rng),0,'child',[],town.x+rng.randbelow(7)-3,town.y+rng.randbelow(7)-3,0,town.uid,town.faction_id,wealth=0,parents=[a.uid,b.uid]);a.children.append(uid);b.children.append(uid);self.state.npcs[uid]=child;town.population+=1
                    self.history.record('birth',f'{child.name} was born in {town.name}.',minute,town.region_x,town.region_y,[uid,a.uid,b.uid],salience=10)
        self._mortality(minute)
    def _mortality(self,minute:int)->None:
        month=minute//(30*1440)
        for n in list(self.state.npcs.values()):
            if not n.alive:continue
            age_risk=max(0,n.age-65)*2
            town=self.state.settlements.get(n.settlement_id);disease_risk=10 if town and any(d.region_x==town.region_x and d.region_y==town.region_y and d.infected>0 for d in self.state.diseases.values()) else 0
            if hash_u64(self.seed,'npc-death',n.uid,month)%1000 < age_risk+disease_risk:
                n.alive=False
                heirs=[self.state.npcs[c] for c in n.children if c in self.state.npcs and self.state.npcs[c].alive]
                if not heirs and n.spouse_uid in self.state.npcs and self.state.npcs[n.spouse_uid].alive:heirs=[self.state.npcs[n.spouse_uid]]
                if heirs:
                    share=n.wealth//len(heirs)
                    for h in heirs:h.wealth+=share
                if town:town.population=max(1,town.population-1)
                if n.uid not in (g.person_uid for g in self.state.graves.values()):
                    gx=(town.x if town else n.x)+int(hash_u64(self.seed,'grave-x',n.uid)%9)-4;gy=(town.y if town else n.y)+int(hash_u64(self.seed,'grave-y',n.uid)%9)-4
                    notable=any(o.holder_uid==n.uid or n.uid in o.previous_holders for o in self.state.offices.values())
                    gtype='tomb' if notable else 'grave';gid=f'grave:{n.uid}';epitaph=f'{n.name}, {n.occupation}, died aged {n.age}'
                    self.state.graves[gid]=GraveState(gid,n.uid,n.name,gx,gy,0,minute,gtype,epitaph)
                self.history.record('death',f'{n.name} died at age {n.age}.',minute,town.region_x if town else 0,town.region_y if town else 0,[n.uid],salience=50 if any(o.holder_uid==n.uid for o in self.state.offices.values()) else (30 if n.occupation=='scholar' else 16))
