from __future__ import annotations

from worldseed.core.coords import WorldPos
from worldseed.core.rng import PCG32, derive_seed, hash_u64
from worldseed.entities.components import Inventory, Vitals
from worldseed.systems.history import HistorySystem
from worldseed.systems.state import (
    ArcaneContaminationState, LivingWorldState, MagicTraditionState, MythState,
    RitualState, SpellState, pos_key,
)

SOURCE_NAMES={"ember":"Ember","tide":"Tide","stone":"Stone","gale":"Gale","bloom":"Bloom","shade":"Shade","star":"Star","blood":"Blood"}
FORM_NAMES={"project":"Projection","bind":"Binding","mend":"Mending","reveal":"Revelation","ward":"Warding","shape":"Shaping"}
DOMAIN_MAGIC={
    "harvest":("bloom","shape","fertility_blessing"),"storms":("gale","shape","rain_call"),"rivers":("tide","shape","rain_call"),
    "war":("ember","ward","battle_ward"),"justice":("star","reveal","truth_rite"),"knowledge":("star","reveal","revelation"),
    "death":("shade","bind","ancestor_rite"),"wilds":("bloom","mend","wild_blessing"),"craft":("stone","bind","forge_blessing"),
    "hearth":("ember","ward","hearth_ward"),
}


class MagicSystem:
    def __init__(self,state:LivingWorldState,seed:bytes,history:HistorySystem|None=None,environment=None):
        self.state=state;self.seed=seed;self.history=history;self.environment=environment

    def ensure_traditions(self)->None:
        for culture in self.state.cultures.values():
            uid=f"tradition:{culture.uid}"
            if uid in self.state.magic_traditions:continue
            rng=PCG32(derive_seed(self.seed,"magic-tradition",culture.uid));sources=[];forms=[]
            all_sources=("ember","tide","stone","gale","bloom","shade","star","blood");all_forms=("project","bind","mend","reveal","ward","shape")
            while len(sources)<2:
                x=rng.choice(all_sources)
                if x not in sources:sources.append(x)
            while len(forms)<2:
                x=rng.choice(all_forms)
                if x not in forms:forms.append(x)
            taboo=rng.choice([x for x in all_sources if x not in sources])
            laws=[l.uid for l in self.state.magic_laws.values() if l.source in sources and l.form in forms]
            self.state.magic_traditions[uid]=MagicTraditionState(uid,culture.uid,f"{culture.name} {rng.choice(['Mysteries','Art','Way','Canon','Lore'])}",sources,forms,taboo,laws)

    def ensure_rituals(self)->None:
        self.ensure_traditions()
        for religion in self.state.religions.values():
            uid=f"ritual:{religion.uid}:major"
            if uid in self.state.rituals:continue
            domain=next((d for d in religion.domains if d in DOMAIN_MAGIC),religion.domains[0] if religion.domains else "knowledge")
            source,form,effect=DOMAIN_MAGIC.get(domain,("star","reveal","revelation"))
            laws=[l for l in self.state.magic_laws.values() if l.source==source and l.form==form]
            if not laws:laws=[l for l in self.state.magic_laws.values() if l.source==source] or list(self.state.magic_laws.values())[:1]
            if not laws:continue
            law=laws[0];cats={law.catalyst:2};duration=120+law.potency*30
            self.state.rituals[uid]=RitualState(uid,religion.uid,f"{religion.deity}'s {religion.ritual.title()}",[law.uid],cats,duration,2,"shrine",effect,0)

    def experiment(self,source:str,form:str,inv:Inventory,vitals:Vitals,minute:int)->str:
        law=next((x for x in self.state.magic_laws.values() if x.source==source and x.form==form),None)
        if not law:return f"The {source} refuses to take the form of {form}."
        if inv.count(law.catalyst)<=0:return f"The attempt needs a catalyst: {law.catalyst}."
        if vitals.stamina<law.stamina_cost:return "You lack the stamina to sustain the experiment."
        inv.remove(law.catalyst,1);vitals.stamina-=law.stamina_cost
        fact=f"knowledge:{law.uid}"
        if fact not in self.state.player_knowledge:self.state.player_knowledge.append(fact)
        spell_uid=f"spell:{law.uid}"
        if spell_uid not in self.state.spells:
            ast={"op":"invoke","source":law.source,"child":{"op":"form","form":law.form,"potency":law.potency},"constraints":{"time":law.time_constraint,"terrain":law.terrain_constraint}}
            self.state.spells[spell_uid]=SpellState(spell_uid,law.uid,f"{SOURCE_NAMES.get(law.source,law.source.title())} {FORM_NAMES.get(law.form,law.form.title())}",ast,minute,0)
        return f"Discovery: {source.title()} may be shaped as {form}. You learned {law.uid}."

    def _constraint_failure(self,law,pos:WorldPos,minute:int,terrain_tags:set[str])->str|None:
        hour=(minute//60)%24;t=law.time_constraint
        if t=="day" and not 6<=hour<18:return "This law answers only during daylight."
        if t=="night" and 6<=hour<18:return "This law answers only at night."
        if t=="dawn" and not 5<=hour<8:return "This law requires the threshold of dawn."
        if t=="dusk" and not 17<=hour<20:return "This law requires the threshold of dusk."
        c=law.terrain_constraint
        if c=="surface" and pos.z!=0:return "This law requires open surface earth."
        if c=="underground" and pos.z>=0:return "This law requires the world below."
        if c and c not in ("surface","underground") and c not in terrain_tags:return f"This law requires terrain attuned to {c}."
        return None

    def cast(self,law_uid:str,vitals:Vitals,pos:WorldPos,minute:int,inv:Inventory|None=None,terrain_tags:set[str]|None=None)->tuple[str,dict]:
        law=self.state.magic_laws.get(law_uid)
        if not law:return "That law does not exist in this world.",{}
        if f"knowledge:{law_uid}" not in self.state.player_knowledge:return "You have not discovered that magical law.",{}
        failure=self._constraint_failure(law,pos,minute,terrain_tags or set())
        if failure:return failure,{}
        if vitals.stamina<law.stamina_cost:return "You are too exhausted to shape the law.",{}
        if law.consumes_catalyst and inv is not None and inv.count(law.catalyst)<=0:return f"Casting requires {law.catalyst} as a consumed focus.",{}
        if law.consumes_catalyst and inv is not None:inv.remove(law.catalyst,1)
        vitals.stamina-=law.stamina_cost
        spell=self.state.spells.get(f"spell:{law_uid}")
        if spell:spell.cast_count+=1
        intensity=max(1,law.potency*5+law.instability//3);self._contaminate(pos,law.contamination,intensity,law.uid,minute)
        effects={"potency":law.potency,"form":law.form,"source":law.source,"x":pos.x,"y":pos.y,"z":pos.z,"instability":law.instability}
        if law.form=="mend":vitals.hp=min(vitals.max_hp,vitals.hp+law.potency*5);vitals.pain=max(0,vitals.pain-law.potency*4)
        elif law.form=="ward":vitals.stamina=min(100,vitals.stamina+law.potency*2)
        event=None
        if self.history and (law.potency>=4 or law.instability>=50):
            event=self.history.record("magic",f"A visible working of {law.source} through {law.form} altered the world.",minute,pos.x//512,pos.y//512,[law.uid],salience=35+law.potency*5)
            self._maybe_myth(event.uid,law.uid,pos,minute)
        return f"You invoke {law.source} through {law.form}.",effects

    def perform_ritual(self,ritual_uid:str,inv:Inventory,vitals:Vitals,pos:WorldPos,minute:int,near_shrine:bool,participants:int=1)->tuple[str,dict,int]:
        ritual=self.state.rituals.get(ritual_uid)
        if not ritual:return "That ritual is unknown in this world.",{},0
        if ritual.location=="shrine" and not near_shrine:return "This rite must be performed at a consecrated shrine.",{},0
        if participants<ritual.min_participants:return f"The rite requires at least {ritual.min_participants} participants.",{},0
        for iid,n in ritual.catalysts.items():
            if inv.count(iid)<n:return f"The rite lacks {n} {iid}.",{},0
        total_stamina=15+5*len(ritual.law_uids)
        if vitals.stamina<total_stamina:return "You are too exhausted to complete the rite.",{},0
        for iid,n in ritual.catalysts.items():inv.remove(iid,n)
        vitals.stamina-=total_stamina;ritual.performed_count+=1
        for law_uid in ritual.law_uids:
            law=self.state.magic_laws.get(law_uid)
            if law:self._contaminate(pos,law.contamination,max(10,law.potency*4),law_uid,minute)
        effects={"ritual_effect":ritual.effect,"potency":sum(self.state.magic_laws[x].potency for x in ritual.law_uids if x in self.state.magic_laws),"religion_id":ritual.religion_id}
        event_uid=""
        if self.history:
            ev=self.history.record("ritual",f"The ritual {ritual.name} was performed.",minute,pos.x//512,pos.y//512,[ritual.uid,ritual.religion_id],salience=55);event_uid=ev.uid
        self._maybe_myth(event_uid,ritual.uid,pos,minute,force=True)
        return f"You complete {ritual.name}.",effects,ritual.duration_minutes

    def _contaminate(self,pos:WorldPos,kind:str,intensity:int,law_uid:str,minute:int)->None:
        key=pos_key(pos.x,pos.y,pos.z);cell=self.state.arcane_contamination.get(key)
        if cell and cell.kind==kind:cell.intensity=min(255,cell.intensity+intensity);cell.last_minute=minute;cell.source_law=law_uid
        else:self.state.arcane_contamination[key]=ArcaneContaminationState(pos.x,pos.y,pos.z,kind,min(255,intensity),law_uid,minute)

    def hourly_update(self,minute:int)->None:
        # Bounded local aftermath. Magic modifies existing systems instead of creating a second physics engine.
        for key,cell in list(self.state.arcane_contamination.items()):
            cell.intensity=max(0,cell.intensity-1);cell.last_minute=minute
            p=WorldPos(cell.x,cell.y,cell.z)
            if cell.kind=="ember" and cell.intensity>65 and self.environment and hash_u64(self.seed,"arcane-fire",key,minute//60)%100<8:self.environment.ignite(p,min(90,cell.intensity//2))
            elif cell.kind=="tide" and cell.intensity>55 and self.environment:self.environment.add_water(p,min(180,cell.intensity))
            elif cell.kind=="bloom":
                for crop in self.state.crops.values():
                    if crop.z==cell.z and abs(crop.x-cell.x)+abs(crop.y-cell.y)<=2:crop.health=min(100,crop.health+1);crop.growth=min(100,crop.growth+1)
            elif cell.kind=="shade":
                for crop in self.state.crops.values():
                    if crop.z==cell.z and abs(crop.x-cell.x)+abs(crop.y-cell.y)<=2:crop.disease=min(100,crop.disease+1)
            if cell.intensity>=100 and hash_u64(self.seed,"arcane-spread",key,minute//60)%100<12 and len(self.state.arcane_contamination)<5000:
                dirs=((1,0),(-1,0),(0,1),(0,-1));dx,dy=dirs[hash_u64(self.seed,"arcane-dir",key,minute//60)%4];np=WorldPos(cell.x+dx,cell.y+dy,cell.z);self._contaminate(np,cell.kind,max(5,cell.intensity//5),cell.source_law,minute)
            if cell.intensity<=0:self.state.arcane_contamination.pop(key,None)

    def _maybe_myth(self,event_uid:str,subject_uid:str,pos:WorldPos,minute:int,force:bool=False)->None:
        town=min(self.state.settlements.values(),key=lambda s:abs(s.x-pos.x)+abs(s.y-pos.y),default=None)
        if not town or abs(town.x-pos.x)+abs(town.y-pos.y)>900:return
        if not force and hash_u64(self.seed,"myth",subject_uid,event_uid)%100>=35:return
        existing=next((m for m in self.state.myths.values() if m.origin_event_uid==event_uid and event_uid),None)
        if existing:existing.adherents+=1;return
        uid=self.state.uid("myth");culture=self.state.cultures.get(town.culture_id);word=culture.lexicon.get('sun','Light').title() if culture else 'Light';belief=f"The people of {town.name} remember the working as a sign that unseen laws answer mortal action."
        self.state.myths[uid]=MythState(uid,town.culture_id,f"The {word} Sign",event_uid,subject_uid,belief,minute,max(1,town.population//20))
