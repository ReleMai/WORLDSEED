from __future__ import annotations
from worldseed.core.rng import hash_u64, PCG32, derive_seed
from worldseed.systems.state import LivingWorldState, NPCState, GraveState
from worldseed.systems.names import person_name
from worldseed.systems.history import HistorySystem

class FamilySystem:
    def __init__(self,state:LivingWorldState,seed:bytes,history:HistorySystem):
        self.state=state;self.seed=seed;self.history=history
        # Optional transient locator maintained by the owning simulation.
        self.npc_index=None

    def ensure_settlement_identity(self,settlement_id:str)->None:
        town=self.state.settlements.get(settlement_id)
        if not town:return
        residents=sorted(
            (n for n in self.state.npcs.values() if n.alive and n.settlement_id==settlement_id),
            key=lambda n:(-n.age,n.uid),
        )
        if not residents:return
        lineage_count=max(1,min(4,(len(residents)+2)//3))
        ambitions={
            "farmer":"secure harvests","herder":"grow the herd","miner":"find a rich vein",
            "smith":"master the forge","carpenter":"build lasting work","healer":"keep people healthy",
            "merchant":"build a reliable trade","guard":"keep the settlement safe",
            "scholar":"preserve useful knowledge","priest":"serve the local faith",
            "hunter":"provide for the settlement","child":"grow into a place in the household",
        }
        wants_by_trait={
            "greedy":"greater wealth","ambitious":"higher standing","curious":"new knowledge",
            "traditional":"family continuity","kind":"close relationships","cautious":"security",
            "brave":"respect","patient":"stable work","suspicious":"trusted allies","stoic":"self reliance",
        }
        for order,npc in enumerate(residents):
            if not npc.lineage_uid:
                # Age-sorted round-robin keeps lineages deterministic while
                # ensuring represented generations can actually share ancestry.
                idx=order%lineage_count
                npc.lineage_uid=f"lineage:{town.uid}:{idx}"
            if not npc.family_uid:npc.family_uid=npc.lineage_uid+":household"
            if not npc.backstory:
                upbringing=("farm household","craft household","market household","religious household","frontier household")[
                    int(hash_u64(self.seed,"upbringing",npc.uid)%5)
                ]
                event=("hard winter","successful harvest","local feud","long caravan visit","serious illness","new workshop opening")[
                    int(hash_u64(self.seed,"formative-event",npc.uid)%6)
                ]
                npc.backstory={
                    "birthplace":town.name,
                    "upbringing":upbringing,
                    "formative_event":event,
                    "ambition":ambitions.get(npc.occupation,"make a stable life"),
                }
            if not npc.wants:
                wants=[ambitions.get(npc.occupation,"stability")]
                for trait in npc.traits:
                    want=wants_by_trait.get(trait)
                    if want and want not in wants:wants.append(want)
                npc.wants=wants[:3]
            defaults={"social":20,"safety":15,"health":max(0,100-npc.hp),"faith":10,"learning":10,"purpose":20}
            for key,value in defaults.items():npc.needs.setdefault(key,value)

        # Seed plausible existing kin across lineage groups. This only links
        # represented people; aggregate residents remain aggregate.
        by_lineage={}
        for npc in residents:by_lineage.setdefault(npc.lineage_uid,[]).append(npc)
        for members in by_lineage.values():
            members.sort(key=lambda n:(-n.age,n.uid))
            for older in members:
                for younger in members:
                    if older.uid==younger.uid or older.age-younger.age<18:continue
                    if len(younger.parents)>=2:continue
                    if older.uid not in younger.parents:
                        younger.parents.append(older.uid);older.children.append(younger.uid)
                        younger.kinship[older.uid]="parent";older.kinship[younger.uid]="child"
                        self._kin_relation(older,younger,35,45,30)
                    break
            singles=[n for n in members if n.age>=22 and not n.spouse_uid]
            for i in range(0,len(singles)-1,2):
                a,b=singles[i],singles[i+1]
                if abs(a.age-b.age)>15 or hash_u64(self.seed,"existing-spouse",a.uid,b.uid)%100>=45:continue
                a.spouse_uid=b.uid;b.spouse_uid=a.uid
                a.kinship[b.uid]="spouse";b.kinship[a.uid]="spouse"
                self._kin_relation(a,b,45,50,35)

    @staticmethod
    def _kin_relation(a:NPCState,b:NPCState,affection:int,trust:int,obligation:int)->None:
        for left,right in ((a,b),(b,a)):
            rel=left.relationships.setdefault(right.uid,{"affection":0,"trust":0,"fear":0,"respect":0,"obligation":0,"familiarity":0})
            rel["affection"]=max(rel["affection"],affection);rel["trust"]=max(rel["trust"],trust)
            rel["obligation"]=max(rel["obligation"],obligation);rel["familiarity"]=max(rel["familiarity"],60)
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
                    a.spouse_uid=b.uid;b.spouse_uid=a.uid;a.kinship[b.uid]="spouse";b.kinship[a.uid]="spouse";self._kin_relation(a,b,35,35,15)
                    self.history.record('marriage',f'{a.name} and {b.name} married in {town.name}.',minute,town.region_x,town.region_y,[a.uid,b.uid],salience=18)
            couples=[];seen=set()
            for a in adults:
                if a.spouse_uid and a.uid not in seen and a.spouse_uid in self.state.npcs:
                    b=self.state.npcs[a.spouse_uid];couples.append((a,b));seen|={a.uid,b.uid}
            for a,b in couples:
                if len(a.children)>=4:continue
                if hash_u64(self.seed,'birth',a.uid,b.uid,month)%100<5 and town.food_stress<65:
                    rng=PCG32(derive_seed(self.seed,'child',a.uid,b.uid,month));uid=self.state.uid('npc');child=NPCState(uid,person_name(rng),0,'child',[],town.x+rng.randbelow(7)-3,town.y+rng.randbelow(7)-3,0,town.uid,town.faction_id,wealth=0,parents=[a.uid,b.uid],family_uid=a.family_uid or b.family_uid,lineage_uid=a.lineage_uid or b.lineage_uid,kinship={a.uid:"parent",b.uid:"parent"},backstory={"birthplace":town.name,"upbringing":"family household","formative_event":"none yet","ambition":"grow into a place in the household"},needs={"social":5,"safety":5,"health":0,"faith":5,"learning":5,"purpose":5},wants=["family security"]);a.children.append(uid);b.children.append(uid);a.kinship[uid]="child";b.kinship[uid]="child";self._kin_relation(a,child,45,55,50);self._kin_relation(b,child,45,55,50);self.state.npcs[uid]=child;town.population+=1
                    if self.npc_index is not None:self.npc_index(child)
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
                if self.npc_index is not None:self.npc_index(n)
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
