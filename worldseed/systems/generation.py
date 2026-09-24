from __future__ import annotations
from worldseed.content.registry import ContentRegistry
from worldseed.core.rng import PCG32, derive_seed
from worldseed.systems.names import culture_name, place_name, person_name, DEITIES
from worldseed.systems.state import CultureState, ReligionState, FactionState, SettlementState, NPCState, MagicLaw

VALUES=["stewardship","honor","trade","craft","scholarship","war","hospitality","ancestry","freedom","order"]
TABOOS=["oathbreaking","grave robbery","waste of food","killing sacred beasts","refusing hospitality","burning old trees","bloodshed in temples"]
DOMAINS=["harvest","storms","war","hearth","death","craft","rivers","knowledge","wilds","justice"]
RITUALS=["first-rain feast","ancestor vigil","forge blessing","river offering","winter lanterns","oath circle","harvest procession"]
OCCUPATIONS=["farmer","hunter","miner","smith","carpenter","healer","merchant","guard","scholar","herder","priest"]
TRAITS=["patient","greedy","brave","cautious","curious","traditional","kind","ambitious","suspicious","stoic"]

class ProceduralSocietyGenerator:
    def __init__(self,world_seed:bytes,registry:ContentRegistry,region_planner=None):
        self.seed=world_seed; self.registry=registry; self.region_planner=region_planner
    def culture_for_region(self,rx:int,ry:int)->CultureState:
        rng=PCG32(derive_seed(self.seed,"culture",rx//3,ry//3))
        uid=f"culture:{rx//3}:{ry//3}"; vals=[]
        while len(vals)<3:
            v=rng.choice(VALUES)
            if v not in vals: vals.append(v)
        
        cname=culture_name(rng); syll=["ka","ve","or","en","thal","mir","sa","dor","ul","ra","ni","esh"]
        lex={concept:"".join(rng.choice(syll) for _ in range(2+rng.randbelow(2))) for concept in ("water","fire","king","home","death","iron","sun","river")}
        return CultureState(uid,cname,vals,rng.choice(["short","compound","ancestral"]),[rng.choice(TABOOS)],rng.choice(["wood","stone","metal","fiber"]),lex)
    def religion_for_region(self,rx:int,ry:int,culture_id:str)->ReligionState:
        rng=PCG32(derive_seed(self.seed,"religion",rx//4,ry//4,culture_id)); domains=[]
        while len(domains)<2:
            d=rng.choice(DOMAINS)
            if d not in domains:domains.append(d)
        deity=rng.choice(DEITIES); uid=f"religion:{rx//4}:{ry//4}"
        return ReligionState(uid,f"Way of {deity}",deity,domains,rng.choice(TABOOS),rng.choice(RITUALS),rng.choice(["hawk","wolf","stag","raven","boar","serpent"]))
    def faction_for_region(self,rx:int,ry:int,culture:CultureState)->FactionState:
        rng=PCG32(derive_seed(self.seed,"faction",rx//2,ry//2)); uid=f"faction:{rx//2}:{ry//2}"
        law={"theft":rng.randbelow(80)+20,"assault":rng.randbelow(80)+20,"trespass":rng.randbelow(60)+10,"tax":rng.randbelow(15)+5}
        return FactionState(uid,f"{culture.name} {rng.choice(['League','March','Compact','Clans','Dominion','Freeholds'])}",culture.uid,1000+rng.randbelow(2500),40+rng.randbelow(60),{},[],law)
    def settlement_for_cell(self,rx:int,ry:int)->tuple[SettlementState,list[NPCState],CultureState,ReligionState,FactionState] | None:
        # roughly one settlement per 3x3 regions
        if derive_seed(self.seed,"settlement-presence",rx,ry)%100 >= 42:return None
        c=self.culture_for_region(rx,ry); r=self.religion_for_region(rx,ry,c.uid); f=self.faction_for_region(rx,ry,c)
        rng=PCG32(derive_seed(self.seed,"settlement",rx,ry))
        anchor=None
        if self.region_planner is not None:
            plan=self.region_planner.plan(rx,ry,persist=True)
            anchor=plan.settlement_anchor
        if anchor is None:
            x=rx*512+64+rng.randbelow(384); y=ry*512+64+rng.randbelow(384)
        else:
            x,y=anchor
        uid=f"settlement:{rx}:{ry}"; pop=25+rng.randbelow(110)
        stocks={"core:wheat":60+rng.randbelow(160),"core:turnip":30+rng.randbelow(100),"core:wood":30+rng.randbelow(80),"core:stone":25+rng.randbelow(70),"core:iron_ore":rng.randbelow(35),"core:coal":rng.randbelow(30),"core:wheat_seed":15+rng.randbelow(25),"core:turnip_seed":10+rng.randbelow(20),"core:medicinal_herb":2+rng.randbelow(9),"core:herbal_tonic":rng.randbelow(5),"core:soap":2+rng.randbelow(8)}
        s=SettlementState(uid,place_name(rng),rx,ry,x,y,pop,c.uid,r.uid,f.uid,500+rng.randbelow(1000),stocks,{}, {"house":max(5,pop//6),"farm":max(2,pop//12)},0,dict(f.laws),["craft:stoneworking","craft:leatherwork"])
        npcs=[]
        for i in range(min(12,max(4,pop//10))):
            nr=PCG32(derive_seed(self.seed,"npc",uid,i)); traits=[]
            while len(traits)<2:
                t=nr.choice(TRAITS)
                if t not in traits:traits.append(t)
            # Local positions are assigned from the authoritative physical plan
            # once the settlement is active. Until then representatives stay at
            # the settlement anchor instead of being scattered into arbitrary
            # walls, water, or resource cells.
            npcs.append(NPCState(f"npc:{uid}:{i}",person_name(nr),18+nr.randbelow(48),nr.choice(OCCUPATIONS),traits,x,y,0,uid,f.uid,wealth=10+nr.randbelow(60)))
        return s,npcs,c,r,f

    def representatives_for_settlement(self,s:SettlementState,count:int|None=None)->list[NPCState]:
        count=count or min(12,max(4,s.population//10))
        out=[]
        for i in range(count):
            nr=PCG32(derive_seed(self.seed,"npc-representative",s.uid,i));traits=[]
            while len(traits)<2:
                t=nr.choice(TRAITS)
                if t not in traits:traits.append(t)
            out.append(NPCState(f"npc:{s.uid}:r{i}",person_name(nr),18+nr.randbelow(48),nr.choice(OCCUPATIONS),traits,s.x,s.y,0,s.uid,s.faction_id,wealth=10+nr.randbelow(60)))
        return out

class MagicGenerator:
    SOURCES=("ember","tide","stone","gale","bloom","shade","star","blood")
    FORMS=("project","bind","mend","reveal","ward","shape")
    CATALYSTS=("core:coal","core:stone","core:berries","core:bone","core:iron_bloom","core:relic")
    def __init__(self,seed:bytes):self.seed=seed
    def laws(self)->dict[str,MagicLaw]:
        out={}
        for s in self.SOURCES:
            for f in self.FORMS:
                rng=PCG32(derive_seed(self.seed,"magic-law",s,f))
                if rng.randbelow(100)<42:
                    uid=f"magic:{s}:{f}"
                    time_constraint=rng.choice(("any","any","day","night","dawn","dusk"))
                    terrain_constraint=rng.choice(("","","surface","underground","water","forest"))
                    instability=5+rng.randbelow(61)
                    out[uid]=MagicLaw(uid,s,f,rng.choice(self.CATALYSTS),10+rng.randbelow(25),1+rng.randbelow(5),True,time_constraint,terrain_constraint,instability,s,rng.randbelow(100)<35)
        return out
