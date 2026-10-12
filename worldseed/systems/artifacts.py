from __future__ import annotations

from worldseed.content.registry import ContentRegistry
from worldseed.core.rng import PCG32, derive_seed
from worldseed.systems.state import ArtifactState, LivingWorldState

EPITHETS=['Wayfarer','Red Edge','Oathkeeper','Deep Song','Ashen Hand','River Star','Last Light','Stone Memory','Winter Fang','Hollow Voice']


class ArtifactSystem:
    def __init__(self,state:LivingWorldState,registry:ContentRegistry,seed:bytes):self.state=state;self.registry=registry;self.seed=seed

    def create(self,base_item:str,creator:str,minute:int,quality_hint:int|None=None,material_override:str|None=None,process_notes:list[str]|None=None,owner:str='player',components_override:dict|None=None,experimental:bool=False)->ArtifactState:
        item=self.registry.items[base_item];material=material_override or item.material;mat=self.registry.materials.get(material) if material else None;rng=PCG32(derive_seed(self.seed,'artifact',base_item,creator,minute,len(self.state.artifacts)))
        if experimental:
            quality=8+rng.randbelow(13)
        elif quality_hint is None:quality=max(20,min(98,45+rng.randbelow(45)+(5 if mat and mat.toughness>70 else 0)))
        else:quality=max(20,min(99,quality_hint-5+rng.randbelow(11)))
        uid=self.state.uid('artifact')
        name=f'Experimental {item.name}' if experimental else f'{item.name} of {rng.choice(EPITHETS)}'
        if components_override is not None:components=components_override
        elif 'sword' in base_item:components={'blade':{'material':material or 'unknown','quality':quality,'condition':100},'guard':{'material':'core:iron','quality':max(20,quality-8),'condition':100},'grip':{'material':'core:wood','quality':max(20,quality-12),'condition':100},'wrapping':{'material':'core:leather','quality':max(20,quality-10),'condition':100}}
        elif 'pick' in base_item:components={'head':{'material':material or 'unknown','quality':quality,'condition':100},'haft':{'material':'core:wood','quality':max(20,quality-10),'condition':100},'binding':{'material':'core:fiber','quality':max(20,quality-15),'condition':100}}
        else:components={'body':{'material':material or 'unknown','quality':quality,'condition':100}}
        if process_notes:components['metallurgy']={'notes':list(process_notes),'quality_input':quality_hint or quality}
        a=ArtifactState(uid,name,base_item,material or 'unknown',quality,creator,minute,owner,[f'Experimental prototype at minute {minute}.' if experimental else f'Forged at minute {minute}.'],components,[{'minute':minute,'from':'','to':owner,'reason':'created','holder':creator}],100,20,0)
        self.state.artifacts[uid]=a;return a

    def ensure_for_owner(self,base_item:str,owner:str,minute:int,creator:str='unknown maker')->ArtifactState:
        rows=sorted((a for a in self.state.artifacts.values() if a.base_item==base_item and a.owner==owner and a.condition>0),key=lambda a:(-a.condition,-a.quality,a.uid))
        if rows:return rows[0]
        # Legacy/market stack items become individual durable instances lazily.
        return self.create(base_item,creator,minute,quality_hint=50,owner=owner)

    def transfer_one(self,base_item:str,from_owner:str,to_owner:str,minute:int,reason:str)->ArtifactState|None:
        matches=sorted((a for a in self.state.artifacts.values() if a.base_item==base_item and a.owner==from_owner and a.condition>0),key=lambda a:a.uid)
        if not matches:return None
        artifact=matches[0];artifact.owner=to_owner;artifact.history.append(f'{reason} at minute {minute}.');artifact.provenance.append({'minute':minute,'from':from_owner,'to':to_owner,'reason':reason});return artifact

    def transfer_uid(self,uid:str,to_owner:str,minute:int,reason:str)->ArtifactState|None:
        a=self.state.artifacts.get(uid)
        if not a:return None
        old=a.owner;a.owner=to_owner;a.history.append(f'{reason} at minute {minute}.');a.provenance.append({'minute':minute,'from':old,'to':to_owner,'reason':reason});return a

    def effective_quality(self,a:ArtifactState)->int:
        component_q=[int(v.get('quality',a.quality)) for k,v in a.components.items() if isinstance(v,dict) and 'material' in v]
        comp=sum(component_q)//len(component_q) if component_q else a.quality
        contamination_penalty=min(35,a.contamination//5)
        return max(5,min(120,((a.quality+comp)//2)*max(10,a.condition)//100-contamination_penalty))

    def best_owned(self,base_item:str,owner:str='player')->ArtifactState|None:
        rows=[a for a in self.state.artifacts.values() if a.base_item==base_item and a.owner==owner and a.condition>0]
        return max(rows,key=lambda a:(self.effective_quality(a),a.condition,a.uid),default=None)

    def best_quality(self,base_item:str,owner:str='player')->int:
        a=self.best_owned(base_item,owner);return self.effective_quality(a) if a else 50

    def wear(self,base_item:str,owner:str,amount:int,minute:int,reason:str='use')->ArtifactState|None:
        a=self.best_owned(base_item,owner)
        if not a:return None
        a.condition=max(0,a.condition-max(0,amount));a.history.append(f'Condition {a.condition}% after {reason} at minute {minute}.')
        for v in a.components.values():
            if isinstance(v,dict) and 'condition' in v:v['condition']=max(0,int(v['condition'])-max(0,amount//2))
        if a.condition<=0:a.provenance.append({'minute':minute,'from':owner,'to':'destroyed','reason':'broken'});a.owner='destroyed'
        return a

    def tick_environment(self,owner:str,ambient_c:int,contamination:int=0)->None:
        for a in self.state.artifacts.values():
            if a.owner!=owner or a.condition<=0:continue
            if a.temperature_c<ambient_c:a.temperature_c=min(ambient_c,a.temperature_c+5)
            elif a.temperature_c>ambient_c:a.temperature_c=max(ambient_c,a.temperature_c-5)
            if contamination:a.contamination=min(255,a.contamination+max(1,contamination//30))
            elif a.contamination:a.contamination=max(0,a.contamination-1)

    def describe_owner(self,owner:str='player')->list[str]:
        out=[]
        for a in sorted((x for x in self.state.artifacts.values() if x.owner==owner),key=lambda x:x.uid):
            out.append(f'{a.name}: q{self.effective_quality(a)} cond {a.condition}% {a.temperature_c}C contam {a.contamination}')
        return out
