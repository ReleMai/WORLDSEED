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
    @staticmethod
    def _culture_style(culture: CultureState, archetype: str) -> str:
        material = {
            "wood": "timber halls",
            "stone": "stone compounds",
            "metal": "iron-trimmed workshops",
            "fiber": "wattle-and-thatch homes",
        }.get(culture.material_style, f"{culture.material_style} vernacular")
        if "trade" in culture.values:
            form = "market-facing streets"
        elif "ancestry" in culture.values:
            form = "ancestral compounds"
        elif "stewardship" in culture.values:
            form = "green commons"
        elif "order" in culture.values:
            form = "formal civic lanes"
        elif "freedom" in culture.values:
            form = "scattered freeholds"
        else:
            form = "workshop lanes"
        return f"{material}; {form}; {archetype.replace('_', ' ')} tradition"

    @staticmethod
    def _founding_trait(archetype: str, regional_role: str) -> str:
        if regional_role == "regional_seat":
            return "seat-town grown around civic roads and regional exchange"
        if archetype == "river_market":
            return "crossing-market founded where transport and freshwater meet"
        if archetype == "mining":
            return "quarry-road settlement built around stone and ore access"
        if archetype == "forest":
            return "woodland clearing linked to logging tracks"
        if archetype == "fishing":
            return "waterside landing organized around fish and storage"
        if archetype == "agrarian":
            return "field village centered on fertile working land"
        return "frontier hold controlling a useful route or defensible site"

    def faction_for_region(self,rx:int,ry:int,culture:CultureState)->FactionState:
        if self.region_planner is not None and int(getattr(self.region_planner, "version", 0)) >= 4:
            faction_seed = self.region_planner.civilization.faction_seed_for_region(rx, ry)
            seat_culture = self.culture_for_region(faction_seed.seat_region_x, faction_seed.seat_region_y)
            rng=PCG32(derive_seed(self.seed,"faction-domain",faction_seed.domain_x,faction_seed.domain_y))
            laws=dict(faction_seed.laws)
            return FactionState(
                uid=faction_seed.uid,
                name=faction_seed.name,
                culture_id=seat_culture.uid,
                treasury=1400+rng.randbelow(2200),
                power=55+rng.randbelow(55),
                laws=laws,
                tradition=faction_seed.tradition,
                seat_region_x=faction_seed.seat_region_x,
                seat_region_y=faction_seed.seat_region_y,
                motto=faction_seed.motto,
            )
        rng=PCG32(derive_seed(self.seed,"faction",rx//2,ry//2)); uid=f"faction:{rx//2}:{ry//2}"
        law={"theft":rng.randbelow(80)+20,"assault":rng.randbelow(80)+20,"trespass":rng.randbelow(60)+10,"tax":rng.randbelow(15)+5}
        return FactionState(uid,f"{culture.name} {rng.choice(['League','March','Compact','Clans','Dominion','Freeholds'])}",culture.uid,1000+rng.randbelow(2500),40+rng.randbelow(60),{},[],law)

    def settlement_for_cell(self,rx:int,ry:int)->tuple[SettlementState,list[NPCState],CultureState,ReligionState,FactionState] | None:
        region_plan = None
        if self.region_planner is not None:
            region_plan = self.region_planner.plan(rx, ry, persist=True)
            if not region_plan.settlement_present:
                return None
        elif derive_seed(self.seed,"settlement-presence",rx,ry)%100 >= 42:
            return None

        c=self.culture_for_region(rx,ry); r=self.religion_for_region(rx,ry,c.uid); f=self.faction_for_region(rx,ry,c)
        rng=PCG32(derive_seed(self.seed,"settlement",rx,ry))
        if region_plan is None or region_plan.settlement_anchor is None:
            x=rx*512+64+rng.randbelow(384); y=ry*512+64+rng.randbelow(384)
            archetype="frontier"; regional_role="frontier_hold"
        else:
            x,y=region_plan.settlement_anchor
            archetype=region_plan.settlement_archetype
            if int(getattr(self.region_planner, "version", 0)) >= 4:
                civ=self.region_planner.civilization.potential(rx,ry)
                regional_role=civ.regional_role
            else:
                regional_role="legacy_settlement"

        if self.region_planner is not None and int(getattr(self.region_planner, "version", 0)) >= 4:
            pop=self.region_planner.civilization.population_for_region(rx,ry)
            building_authority="derived"
            buildings={}
        else:
            pop=25+rng.randbelow(110)
            building_authority="legacy"
            buildings={"house":max(5,pop//6),"farm":max(2,pop//12)}

        uid=f"settlement:{rx}:{ry}"
        stocks={"core:wheat":60+rng.randbelow(160),"core:turnip":30+rng.randbelow(100),"core:wood":30+rng.randbelow(80),"core:stone":25+rng.randbelow(70),"core:iron_ore":rng.randbelow(35),"core:coal":rng.randbelow(30),"core:wheat_seed":15+rng.randbelow(25),"core:turnip_seed":10+rng.randbelow(20),"core:medicinal_herb":2+rng.randbelow(9),"core:herbal_tonic":rng.randbelow(5),"core:soap":2+rng.randbelow(8)}
        style=self._culture_style(c,archetype)
        s=SettlementState(
            uid=uid,name=place_name(rng),region_x=rx,region_y=ry,x=x,y=y,population=pop,
            culture_id=c.uid,religion_id=r.uid,faction_id=f.uid,wealth=500+rng.randbelow(1000),
            stocks=stocks,prices={},buildings=buildings,food_stress=0,law=dict(f.laws),
            knowledge=["craft:stoneworking","craft:leatherwork"],
            building_authority=building_authority,archetype=archetype,regional_role=regional_role,
            culture_style=style,founding_trait=self._founding_trait(archetype,regional_role),
        )
        npcs=[]
        for i in range(min(12,max(4,pop//10))):
            nr=PCG32(derive_seed(self.seed,"npc",uid,i)); traits=[]
            while len(traits)<2:
                t=nr.choice(TRAITS)
                if t not in traits:traits.append(t)
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
