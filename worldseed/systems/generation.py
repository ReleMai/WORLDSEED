from __future__ import annotations
from worldseed.content.registry import ContentRegistry
from worldseed.core.rng import PCG32, derive_seed, hash_u64
from worldseed.systems.names import culture_name, place_name, person_name, DEITIES
from worldseed.systems.state import CultureState, ReligionState, FactionState, SettlementState, NPCState, MagicLaw

VALUES=["stewardship","honor","trade","craft","scholarship","war","hospitality","ancestry","freedom","order"]
TABOOS=["oathbreaking","grave robbery","waste of food","killing sacred beasts","refusing hospitality","burning old trees","bloodshed in temples"]
DOMAINS=["harvest","storms","war","hearth","death","craft","rivers","knowledge","wilds","justice"]
RITUALS=["first-rain feast","ancestor vigil","forge blessing","river offering","winter lanterns","oath circle","harvest procession"]
OCCUPATIONS=["farmer","hunter","miner","smith","carpenter","healer","merchant","guard","scholar","herder","priest"]

def specialize_occupation(base:str,settlement_uid:str,index:int)->str:
    """Add Phase-4 specializations without changing the legacy RNG draw order."""
    base=str(base)
    token=int(hash_u64(b"worldseed-profession-v1",settlement_uid,int(index),base)%100)
    if base=="carpenter" and token<58:
        return "lumberjack"
    if base=="farmer" and token<16:
        return "cook"
    return base

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
        # Preserve the pre-v4 RNG draw order for existing culture fields;
        # flavor fields consume only subsequent draws.
        naming_style=rng.choice(["short","compound","ancestral"])
        taboo=rng.choice(TABOOS)
        craft=rng.choice(["wood","stone","metal","fiber"])
        architecture={"wood":"timber_courtyard","stone":"stone_lane","metal":"fortified_workyard","fiber":"wattle_common"}[craft]
        morphology=rng.choice(["organic","crossroads","courtyard","linear"])
        public_space=rng.choice(["common","market_green","shrine_square","meeting_hall"])
        colors=[]
        while len(colors)<2:
            color=rng.choice(["ochre","river-blue","pine-green","ash-grey","iron-red","cream","charcoal"])
            if color not in colors:colors.append(color)
        return CultureState(uid,cname,vals,naming_style,[taboo],craft,lex,
                            architecture,morphology,public_space,colors)
    def religion_for_region(self,rx:int,ry:int,culture_id:str)->ReligionState:
        rng=PCG32(derive_seed(self.seed,"religion",rx//4,ry//4,culture_id)); domains=[]
        while len(domains)<2:
            d=rng.choice(DOMAINS)
            if d not in domains:domains.append(d)
        deity=rng.choice(DEITIES); uid=f"religion:{rx//4}:{ry//4}"
        return ReligionState(uid,f"Way of {deity}",deity,domains,rng.choice(TABOOS),rng.choice(RITUALS),rng.choice(["hawk","wolf","stag","raven","boar","serpent"]))
    def faction_for_region(self,rx:int,ry:int,culture:CultureState)->FactionState:
        fx,fy=rx//2,ry//2
        rng=PCG32(derive_seed(self.seed,"faction",fx,fy)); uid=f"faction:{fx}:{fy}"
        candidates=[]
        if self.region_planner is not None:
            for cy in range(fy*2,fy*2+2):
                for cx in range(fx*2,fx*2+2):
                    plan=self.region_planner.plan(cx,cy,persist=True)
                    candidates.append((int(plan.settlement_score),int(getattr(plan,"route_value",0)),cy,cx,plan))
        seat_plan=max(candidates,key=lambda row:(row[0],row[1],-row[2],-row[3]))[-1] if candidates else None
        archetype={
            "river_market":"river_league","mining":"iron_march","forest":"greenward",
            "fishing":"tide_freeholds","agrarian":"granary_compact","frontier":"border_march",
        }.get(getattr(seat_plan,"settlement_archetype",""),"regional_power")
        suffix={
            "river_league":"League","iron_march":"March","greenward":"Wardens",
            "tide_freeholds":"Freeholds","granary_compact":"Compact","border_march":"March",
            "regional_power":"Dominion",
        }[archetype]
        laws={"theft":rng.randbelow(80)+20,"assault":rng.randbelow(80)+20,"trespass":rng.randbelow(60)+10,"tax":rng.randbelow(15)+5}
        if archetype=="river_league":laws["tax"]=max(5,laws["tax"]-3)
        elif archetype=="iron_march":laws["assault"]=min(100,laws["assault"]+12)
        elif archetype=="greenward":laws["trespass"]=min(100,laws["trespass"]+14)
        seat_region=f"{seat_plan.region_x},{seat_plan.region_y}" if seat_plan is not None else f"{fx*2},{fy*2}"
        prominence=min(100,35+(int(seat_plan.settlement_score) if seat_plan else 30)//2+(int(getattr(seat_plan,"route_value",0)) if seat_plan else 20)//3)
        banner=rng.choice(["split-field","river-chevron","sun-disc","tower-and-road","tree-knot","hammer-stripe"])
        doctrine={
            "river_league":"protect crossings and keep trade moving",
            "iron_march":"control ore, roads and fortified uplands",
            "greenward":"hold timberlands and guarded commons",
            "tide_freeholds":"bind waterfront settlements through exchange",
            "granary_compact":"secure farmland, stores and market roads",
            "border_march":"fortify frontier routes and daughter settlements",
            "regional_power":"bind nearby settlements through roads and law",
        }[archetype]
        return FactionState(uid,f"{culture.name} {suffix}",culture.uid,1000+rng.randbelow(2500),40+rng.randbelow(60),{},[],laws,
                            archetype=archetype,seat_region=seat_region,banner_style=banner,doctrine=doctrine,prominence=prominence)
    def settlement_for_cell(self,rx:int,ry:int)->tuple[SettlementState,list[NPCState],CultureState,ReligionState,FactionState] | None:
        plan=None
        if self.region_planner is not None:
            plan=self.region_planner.plan(rx,ry,persist=True)
            if not plan.settlement_present:return None
        elif derive_seed(self.seed,"settlement-presence",rx,ry)%100 >= 42:
            # Legacy/fallback callers without the regional physical planner keep
            # the historical contract; active v4 worlds never use this branch.
            return None
        c=self.culture_for_region(rx,ry); r=self.religion_for_region(rx,ry,c.uid); f=self.faction_for_region(rx,ry,c)
        rng=PCG32(derive_seed(self.seed,"settlement",rx,ry))
        anchor=plan.settlement_anchor if plan is not None else None
        if anchor is None:
            x=rx*512+64+rng.randbelow(384); y=ry*512+64+rng.randbelow(384)
        else:
            x,y=anchor
        uid=f"settlement:{rx}:{ry}"; pop=25+rng.randbelow(110)
        stocks={"core:wheat":60+rng.randbelow(160),"core:turnip":30+rng.randbelow(100),"core:wood":30+rng.randbelow(80),"core:stone":25+rng.randbelow(70),"core:iron_ore":rng.randbelow(35),"core:coal":rng.randbelow(30),"core:wheat_seed":15+rng.randbelow(25),"core:turnip_seed":10+rng.randbelow(20),"core:medicinal_herb":2+rng.randbelow(9),"core:herbal_tonic":rng.randbelow(5),"core:soap":2+rng.randbelow(8)}
        # Physical settlement plans own buildings/capacity. This dictionary is
        # derived after physical planning and starts empty.
        s=SettlementState(uid,place_name(rng),rx,ry,x,y,pop,c.uid,r.uid,f.uid,500+rng.randbelow(1000),stocks,{}, {},0,dict(f.laws),["craft:stoneworking","craft:leatherwork"])
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
            base_occ=nr.choice(OCCUPATIONS);occ=specialize_occupation(base_occ,uid,i)
            npcs.append(NPCState(f"npc:{uid}:{i}",person_name(nr),18+nr.randbelow(48),occ,traits,x,y,0,uid,f.uid,wealth=10+nr.randbelow(60)))
        return s,npcs,c,r,f

    def representatives_for_settlement(self,s:SettlementState,count:int|None=None)->list[NPCState]:
        count=count or min(12,max(4,s.population//10))
        out=[]
        for i in range(count):
            nr=PCG32(derive_seed(self.seed,"npc-representative",s.uid,i));traits=[]
            while len(traits)<2:
                t=nr.choice(TRAITS)
                if t not in traits:traits.append(t)
            base_occ=nr.choice(OCCUPATIONS);occ=specialize_occupation(base_occ,s.uid,i)
            out.append(NPCState(f"npc:{s.uid}:r{i}",person_name(nr),18+nr.randbelow(48),occ,traits,s.x,s.y,0,s.uid,s.faction_id,wealth=10+nr.randbelow(60)))
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
