from __future__ import annotations

from worldseed.core.rng import PCG32, derive_seed, hash_u64
from worldseed.systems.history import HistorySystem
from worldseed.systems.names import person_name
from worldseed.systems.state import LibraryState, LivingWorldState, KnowledgeSchoolState, ReligionState, ReligiousInstitutionState

FOCI=("craft","agriculture","medicine","natural_philosophy","history")
SCHISM_DOMAINS=("mercy","flame","sea","ancestors","dreams","law","stars")


class InstitutionSystem:
    """Material institutions that anchor knowledge and religion in settlements."""

    def __init__(self,state:LivingWorldState,seed:bytes,history:HistorySystem)->None:
        self.state=state;self.seed=seed;self.history=history

    def ensure_settlement(self,settlement_id:str)->None:
        town=self.state.settlements.get(settlement_id)
        if not town:return
        culture=self.state.cultures.get(town.culture_id)
        for npc in self.state.npcs.values():
            if not npc.alive or npc.settlement_id!=town.uid:continue
            if not npc.culture_id:npc.culture_id=town.culture_id
            if not npc.religion_id:npc.religion_id=town.religion_id
            if town.culture_id not in npc.language_fluency:npc.language_fluency[town.culture_id]=100
            if npc.literacy<=0:
                base=70 if npc.occupation in ("scholar","priest") else 45 if npc.occupation in ("merchant","healer","smith") else 10
                if culture and "scholarship" in culture.values:base+=15
                npc.literacy=min(100,base+int(hash_u64(self.seed,"literacy",npc.uid)%16))
        scholars=[n for n in self.state.npcs.values() if n.alive and n.settlement_id==town.uid and n.occupation=='scholar']
        if scholars or "knowledge:literacy" in town.knowledge:
            lid=f"library:{town.uid}"
            if lid not in self.state.libraries:
                self.state.libraries[lid]=LibraryState(lid,town.uid,f"{town.name} Archive",[],max(20,20+len(scholars)*15),100)
                if getattr(town,"building_authority","legacy")=="legacy":
                    town.buildings['library']=town.buildings.get('library',0)+1
                self.history.record('institution',f'{town.name} established {self.state.libraries[lid].name}.',self.state.clock_minute,town.region_x,town.region_y,[town.uid,lid],salience=20)
        if scholars:
            sid=f"school:{town.uid}:0"
            if sid not in self.state.knowledge_schools:
                focus=FOCI[hash_u64(self.seed,"school-focus",town.uid)%len(FOCI)]
                self.state.knowledge_schools[sid]=KnowledgeSchoolState(sid,town.uid,f"{town.name} School of {focus.replace('_',' ').title()}",focus,[n.uid for n in scholars[:4]],10)
        priests=[n for n in self.state.npcs.values() if n.alive and n.settlement_id==town.uid and n.occupation=='priest']
        if not priests:
            # Do not destroy the settlement's only scholar merely to fill a priest role.
            residents=[n for n in self.state.npcs.values() if n.alive and n.settlement_id==town.uid]
            candidates=[n for n in residents if n.occupation=='healer' or ('traditional' in n.traits and n.occupation!='scholar')]
            if not candidates and len(scholars)>1:candidates=scholars[1:]
            if candidates:
                p=sorted(candidates,key=lambda n:n.uid)[0];p.occupation='priest';priests=[p]
        iid=f"temple:{town.uid}:{town.religion_id}"
        if town.religion_id and iid not in self.state.religious_institutions:
            religion=self.state.religions.get(town.religion_id);name=f"Shrine of {religion.deity}" if religion else f"Shrine of {town.name}"
            self.state.religious_institutions[iid]=ReligiousInstitutionState(iid,town.uid,town.religion_id,name,[p.uid for p in priests],min(90,25+len(priests)*10+town.population//10),town.x,town.y,0,'orthodox')
            if getattr(town,"building_authority","legacy")=="legacy":
                town.buildings['shrine']=town.buildings.get('shrine',0)+1

    def library_for_settlement(self,settlement_id:str)->LibraryState|None:
        return next((l for l in self.state.libraries.values() if l.settlement_id==settlement_id),None)

    def monthly_update(self,minute:int)->None:
        month=minute//(30*1440)
        for town in self.state.settlements.values():
            self.ensure_settlement(town.uid)
            residents=[n for n in self.state.npcs.values() if n.alive and n.settlement_id==town.uid]
            faith_counts={}
            for n in residents:faith_counts[n.religion_id]=faith_counts.get(n.religion_id,0)+1
            minority=sum(v for k,v in faith_counts.items() if k and k!=town.religion_id)
            town.religious_tension=max(0,min(100,minority*8 + town.food_stress//3 + (12 if self.state.factions.get(town.faction_id) and self.state.factions[town.faction_id].at_war else 0)))
            institution=next((i for i in self.state.religious_institutions.values() if i.settlement_id==town.uid and i.religion_id==town.religion_id),None)
            if institution:
                institution.influence=max(10,min(100,institution.influence + len(institution.priest_uids)-town.religious_tension//25))
            # Conversion is slow, individual and personality-sensitive.
            for n in residents:
                if not n.religion_id or n.religion_id==town.religion_id:continue
                resistance=45 + (30 if 'traditional' in n.traits else 0) - (15 if 'curious' in n.traits else 0)
                pressure=(institution.influence if institution else 20)-resistance
                if pressure>0 and hash_u64(self.seed,'conversion',n.uid,town.uid,month)%100<min(40,pressure):
                    old=n.religion_id;n.religion_id=town.religion_id
                    self.history.record('conversion',f'{n.name} adopted the dominant faith of {town.name}.',minute,town.region_x,town.region_y,[n.uid,old,town.religion_id],salience=12)
            # High tension can produce a deterministic local schism rather than a random flavor event.
            if town.religious_tension>=70 and hash_u64(self.seed,'schism',town.uid,month)%100<8:
                self._create_schism(town,minute,month)

    def _create_schism(self,town,minute:int,month:int)->None:
        base=self.state.religions.get(town.religion_id)
        if not base:return
        uid=f"religion:schism:{town.uid}:{month}"
        if uid in self.state.religions:return
        extra=SCHISM_DOMAINS[hash_u64(self.seed,'schism-domain',uid)%len(SCHISM_DOMAINS)]
        domains=list(dict.fromkeys(base.domains+[extra]))[:3]
        rel=ReligionState(uid,f"Reformed {base.name}",base.deity,domains,base.taboo,f"reformed {base.ritual}",base.sacred_animal)
        self.state.religions[uid]=rel
        iid=f"temple:{town.uid}:{uid}";dissenters=[]
        candidates=sorted((n for n in self.state.npcs.values() if n.alive and n.settlement_id==town.uid and ('curious' in n.traits or 'ambitious' in n.traits)),key=lambda n:n.uid)
        for n in candidates[:max(1,len(candidates)//3)]:n.religion_id=uid;dissenters.append(n.uid)
        self.state.religious_institutions[iid]=ReligiousInstitutionState(iid,town.uid,uid,f"Reformed Hall of {base.deity}",dissenters[:2],20,town.x+2,town.y,0,'reformist')
        town.religious_tension=min(100,town.religious_tension+15)
        self.history.record('schism',f'A reform movement split from {base.name} in {town.name}.',minute,town.region_x,town.region_y,[town.uid,base.uid,uid]+dissenters[:3],salience=55)
