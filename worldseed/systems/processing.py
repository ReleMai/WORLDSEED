from __future__ import annotations
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory
from worldseed.systems.state import LivingWorldState, CarcassState, ProcessingJobState, GroundPile, pos_key

class ProcessingSystem:
    def __init__(self,state:LivingWorldState,registry:ContentRegistry,building):self.state=state;self.registry=registry;self.building=building

    def nearby_carcasses(self,pos:WorldPos,radius:int=1)->list[CarcassState]:
        return sorted([c for c in self.state.carcasses.values() if c.z==pos.z and abs(c.x-pos.x)+abs(c.y-pos.y)<=radius],key=lambda c:(abs(c.x-pos.x)+abs(c.y-pos.y),c.uid))

    def _tool_quality(self,inv:Inventory,key:str)->int:
        return max([self.registry.items[i].quality(key) for i,n in inv.items.items() if n>0 and i in self.registry.items]+[0])

    def process_carcass(self,uid:str,action:str,inv:Inventory,hunting_skill:int,minute:int)->tuple[bool,str,int]:
        c=self.state.carcasses.get(uid)
        if not c:return False,"That carcass is gone.",0
        sp=self.registry.species.get(c.species_id)
        if not sp:return False,"Unknown carcass.",0
        profile=dict(sp.carcass) or {'core:raw_game_meat':max(1,sp.mass_kg//12),'core:fresh_hide':1 if sp.mass_kg>=3 else 0,'core:bone':max(1,sp.mass_kg//25),'core:animal_fat':max(0,sp.mass_kg//30),'core:offal':max(1,sp.mass_kg//35),'core:sinew':1 if sp.mass_kg>=8 else 0}
        # A carcass is a time-sensitive resource. Cooling buys time, but in the current
        # human-scale model exposed carcasses lose usable quality steadily after death.
        age_hours=max(0,(minute-c.killed_minute)//60)
        age_penalty=max(0,age_hours-2)*2 + max(0,age_hours-24)*3
        effective_quality=max(0,c.quality-age_penalty)
        if effective_quality<=10:
            return False,f"The {sp.name.lower()} carcass has spoiled beyond safe processing.",0
        table_bonus=10 if any(s.structure_id=='core:butcher_table' and s.z==c.z and abs(s.x-c.x)+abs(s.y-c.y)<=2 for s in self.state.structures.values()) else 0
        if action=='recover':
            if not c.embedded_items:return False,"There are no recoverable projectiles in the carcass.",0
            recovered=dict(c.embedded_items);c.embedded_items.clear()
            for iid,n in recovered.items():
                if iid in self.registry.items and n>0:inv.add(iid,n)
            text=', '.join(f'{n} {self.registry.items[i].name.lower()}' for i,n in recovered.items() if i in self.registry.items) or 'nothing useful'
            return True,f"You extract {text} from the carcass.",4
        if action=='anatomy':
            if not c.anatomy_condition:return False,"This carcass has no detailed anatomy record to harvest.",0
            q=max(self._tool_quality(inv,'butcher'),self._tool_quality(inv,'cut'))
            if q<1:return False,"You need a cutting or butchering tool to recover organs and specialized parts.",0
            recovered={};notes=[];damaged=[]
            for name,condition in sorted(c.anatomy_condition.items()):
                if name in c.harvested_anatomy:continue
                meta=sp.anatomy.get(name,{})
                harvest=str(meta.get("harvest","offal"))
                if harvest=="none":
                    c.harvested_anatomy.append(name);continue
                mass=max(1,int(c.anatomy_mass_g.get(name,0)))
                effective=max(0,min(100,int(condition)+hunting_skill*2+q*3+table_bonus//2))
                c.harvested_anatomy.append(name)
                if effective<25:
                    damaged.append(name.replace('_',' '));continue
                item_id={"offal":"core:offal","bone":"core:bone","sinew":"core:sinew","feather":"core:feather"}.get(harvest)
                if not item_id or item_id not in self.registry.items:continue
                item_mass=max(1,int(self.registry.items[item_id].mass_g))
                usable=max(1,mass*effective//100)
                units=max(1,(usable+item_mass-1)//item_mass)
                inv.add(item_id,units);recovered[item_id]=recovered.get(item_id,0)+units
                size="tiny" if mass<80 else "small" if mass<250 else "medium" if mass<800 else "large" if mass<2500 else "massive"
                rarity=int(meta.get("rarity",50));rarity_label="notable" if rarity>=75 else "uncommon" if rarity>=60 else "common"
                notes.append(f"{size} {name.replace('_',' ')} ({mass} g, {rarity_label}, {effective}% usable)")
            if not recovered and not notes:
                return False,"No recoverable anatomy remains.",0
            output=', '.join(f'{n} {self.registry.items[i].name.lower()}' for i,n in recovered.items()) or 'no usable material'
            detail='; '.join(notes[:7])
            spoil=f" Damaged beyond recovery: {', '.join(damaged[:5])}." if damaged else ""
            return True,f"You recover the animal's anatomy: {detail}. Yield: {output}.{spoil}",max(12,38-hunting_skill-q*2-table_bonus//3)
        if action=='skin':
            if c.skinned:return False,"The carcass has already been skinned.",0
            q=self._tool_quality(inv,'skin')
            if q<1:return False,"You need a sharp skinning tool.",0
            c.skinned=True;c.processed_by='player';base=profile.get('core:fresh_hide',0)
            if c.hide_ruined:base=max(0,base//2)
            yield_n=max(0,base*(60+min(40,effective_quality//3+hunting_skill*2+q*4+table_bonus))//100)
            if yield_n:inv.add('core:fresh_hide',yield_n)
            return True,f"You skin the {sp.name.lower()} and recover {yield_n} fresh hide." if yield_n else f"You skin the {sp.name.lower()}, but the hide is too damaged to save.",max(12,35-hunting_skill-q*2-table_bonus//3)
        if action=='butcher':
            if c.butchered:return False,"The carcass has already been butchered.",0
            q=max(self._tool_quality(inv,'butcher'),self._tool_quality(inv,'cut'))
            if q<1:return False,"You need a cutting or butchering tool.",0
            if not c.skinned:c.hide_ruined=True
            c.butchered=True;c.processed_by='player';outputs={};quality=max(20,min(120,effective_quality+hunting_skill*2+q*4+table_bonus))
            for iid,n in profile.items():
                if iid in ('core:fresh_hide','core:bone','core:sinew'):continue
                # Detailed anatomy is recovered through the anatomy action so
                # named organs are not duplicated as generic offal.
                if iid=='core:offal' and c.anatomy_condition:continue
                got=max(0,n*quality//100)
                if got:inv.add(iid,got);outputs[iid]=got
            text=', '.join(f'{n} {self.registry.items[i].name.lower()}' for i,n in outputs.items()) or 'little usable meat'
            return True,f"You butcher the {sp.name.lower()} and recover {text}." + (" Working before skinning damages the hide." if c.hide_ruined and not c.skinned else ""),max(18,55-hunting_skill*2-q*2-table_bonus//2)
        if action=='debone':
            if c.deboned:return False,"The carcass has already been deboned.",0
            if not c.butchered:return False,"Butcher the carcass before deboning it.",0
            q=self._tool_quality(inv,'cut')
            if q<1:return False,"You need a cutting tool to debone the carcass.",0
            c.deboned=True;outs={}
            for iid,n in list(c.embedded_items.items()):
                if iid in self.registry.items and n>0:inv.add(iid,n);outs[iid]=outs.get(iid,0)+n
            c.embedded_items.clear()
            for iid in ('core:bone','core:sinew'):
                n=profile.get(iid,0)
                if n:inv.add(iid,n);outs[iid]=n
            self.state.carcasses.pop(uid,None)
            return True,"You debone the remaining carcass: "+(', '.join(f'{n} {self.registry.items[i].name.lower()}' for i,n in outs.items()) or 'little remains')+'.',max(10,30-hunting_skill-q)
        return False,"Unknown carcass process.",0

    def _station(self,pos:WorldPos,structure_id:str):
        rows=[s for s in self.state.structures.values() if s.structure_id==structure_id and s.z==pos.z and abs(s.x-pos.x)+abs(s.y-pos.y)<=2]
        return min(rows,key=lambda s:abs(s.x-pos.x)+abs(s.y-pos.y),default=None)

    def start_job(self,process_id:str,pos:WorldPos,inv:Inventory,minute:int)->tuple[bool,str,int]:
        specs={
            'dry_meat':('core:drying_rack',{'core:raw_game_meat':2},{'core:dried_meat':2},12*60,'meat dries in the moving air'),
            'dry_small_game':('core:drying_rack',{'core:raw_small_game':2},{'core:dried_meat':1},10*60,'small cuts dry quickly'),
            'dry_hide':('core:drying_rack',{'core:scraped_hide':1},{'core:rawhide':1},12*60,'the scraped hide dries stiff'),
            'tan_hide':('core:tanning_frame',{'core:scraped_hide':1,'core:bark':2},{'core:leather':1},24*60,'tannins preserve the hide into leather'),
        }
        if process_id not in specs:return False,"Unknown processing job.",0
        station_id,inputs,outputs,duration,note=specs[process_id];station=self._station(pos,station_id)
        if not station:return False,f"You need a nearby {self.registry.structures[station_id].name.lower()}.",0
        if not inv.has(inputs):return False,"You lack the materials for that process.",0
        inv.consume(inputs);uid=self.state.uid('job');key=pos_key(station.x,station.y,station.z);self.state.processing_jobs[uid]=ProcessingJobState(uid,process_id,key,'player',minute,minute+duration,dict(inputs),dict(outputs),'working',note)
        return True,f"You set the {self.registry.structures[station_id].name.lower()} to work; {note}.",10

    def complete_due(self,minute:int)->list[str]:
        messages=[]
        for uid,job in list(self.state.processing_jobs.items()):
            if job.status!='working' or minute<job.complete_minute:continue
            try:x,y,z=(int(v) for v in job.station_key.split(','))
            except Exception:x=y=z=0
            pile=self.state.ground_piles.setdefault(job.station_key,GroundPile(x,y,z,{}))
            for iid,n in job.outputs.items():pile.items[iid]=pile.items.get(iid,0)+n
            job.status='complete';messages.append(f"A {job.process_id.replace('_',' ')} job finishes at your station.")
        # keep a small ledger of finished jobs instead of unbounded records
        done=[u for u,j in self.state.processing_jobs.items() if j.status=='complete']
        for u in done[:-30]:self.state.processing_jobs.pop(u,None)
        return messages
