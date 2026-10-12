from __future__ import annotations

from copy import deepcopy

from worldseed.content.registry import ContentRegistry
from worldseed.core.rng import PCG32, derive_seed
from worldseed.systems.state import ArtifactState, LivingWorldState

EPITHETS=['Wayfarer','Red Edge','Oathkeeper','Deep Song','Ashen Hand','River Star','Last Light','Stone Memory','Winter Fang','Hollow Voice']


def crafting_effects(item,quality:int)->dict:
    """Expose the same marked-gear effects used by combat, wear and markets."""
    effects=ArtifactSystem.effects_for_quality(item,quality)
    damage=effects['damage_percent']/100
    armor=effects['armor_percent']/100
    durability=effects['durability_percent']/100
    value=effects['value_percent']/100
    benefits=[]
    if item.weapon_damage:benefits.append(f'Damage ×{damage:.2f}')
    if item.armor:benefits.append(f'Armor ×{armor:.2f}')
    benefits.extend([f'Durability ×{durability:.2f}',f'Trade value ×{value:.2f}'])
    return {**effects,'damage_multiplier':damage,'armor_multiplier':armor,
            'wear_multiplier':1/durability,'value_multiplier':value,'benefits':benefits}


class ArtifactSystem:
    def __init__(self,state:LivingWorldState,registry:ContentRegistry,seed:bytes):self.state=state;self.registry=registry;self.seed=seed

    def create(self,base_item:str,creator:str,minute:int,quality_hint:int|None=None,material_override:str|None=None,process_notes:list[str]|None=None,owner:str='player',components_override:dict|None=None,experimental:bool=False)->ArtifactState:
        item=self.registry.items[base_item];material=material_override or item.material;mat=self.registry.materials.get(material) if material else None;rng=PCG32(derive_seed(self.seed,'artifact',base_item,creator,minute,len(self.state.artifacts)))
        crafted = isinstance(components_override, dict) and isinstance(components_override.get('crafting'), dict) and components_override['crafting'].get('quality_version') == 1
        if crafted and quality_hint is not None and not experimental:
            # Material recipes already resolved their exact deterministic quality.
            quality = max(0, min(100, int(quality_hint)))
        elif experimental:
            quality=8+rng.randbelow(13)
        elif quality_hint is None:quality=max(20,min(98,45+rng.randbelow(45)+(5 if mat and mat.toughness>70 else 0)))
        else:quality=max(20,min(99,quality_hint-5+rng.randbelow(11)))
        uid=self.state.uid('artifact')
        name=f'Experimental {item.name}' if experimental else f'{item.name} of {rng.choice(EPITHETS)}'
        if components_override is not None:components=deepcopy(components_override)
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
        matches=self.trade_candidates(base_item,from_owner)
        if not matches:return None
        return self.transfer_uid(matches[0].uid,to_owner,minute,reason)

    def transfer_uid(self,uid:str,to_owner:str,minute:int,reason:str)->ArtifactState|None:
        a=self.state.artifacts.get(uid)
        if not a:return None
        old=a.owner;a.owner=to_owner;a.history.append(f'{reason} at minute {minute}.');a.provenance.append({'minute':minute,'from':old,'to':to_owner,'reason':reason});return a

    @staticmethod
    def material_quality_enabled(artifact:ArtifactState)->bool:
        metadata=artifact.components.get('crafting')
        return isinstance(metadata,dict) and metadata.get('quality_version')==1

    @staticmethod
    def effects_for_quality(item,quality:int)->dict[str,int]:
        """Observational effects for newly material-crafted gear, relative to q50."""
        quality=max(0,min(100,int(quality)))
        effective=max(5,quality)
        durability=50+quality
        return {'quality':quality,
                'damage_percent':effective*2 if item.weapon_damage else 100,
                'armor_percent':effective*2 if item.armor else 100,
                'durability_percent':durability,
                'wear_rate_percent':(10000+durability//2)//durability,
                'value_percent':50+effective}

    def describe_effects(self,artifact:ArtifactState)->dict[str,int]:
        item=self.registry.items[artifact.base_item]
        effects=self.effects_for_quality(item,self.effective_quality(artifact))
        if self.material_quality_enabled(artifact):
            effects['durability_percent']=50+max(0,min(100,artifact.quality))
            effects['wear_rate_percent']=(10000+effects['durability_percent']//2)//effects['durability_percent']
        else:
            # Existing saves retain their old durability and commodity value.
            effects.update(durability_percent=100,wear_rate_percent=100,value_percent=100)
        return effects

    def condition_loss(self,artifact:ArtifactState,amount:int)->int:
        """Convert physical wear into condition loss without rounding away small hits."""
        amount=max(0,int(amount))
        if not amount or not self.material_quality_enabled(artifact):return amount
        metadata=artifact.components['crafting']
        durability=50+max(0,min(100,artifact.quality))
        remainder=max(0,min(durability-1,int(metadata.get('wear_remainder',0))))
        loss,metadata['wear_remainder']=divmod(amount*100+remainder,durability)
        return loss

    def trade_candidates(self,base_item:str,owner:str)->list[ArtifactState]:
        """The same stable instance order is used by quotes and transfers."""
        equipped=set(self.state.player_equipped_artifacts.values()) if owner=='player' else set()
        return sorted((a for a in self.state.artifacts.values()
                       if a.base_item==base_item and a.owner==owner and a.condition>0 and a.uid not in equipped),
                      key=lambda a:a.uid)

    def trade_quote(self,base_item:str,owner:str,amount:int,unit_price:int)->tuple[int,tuple[str,...]]:
        """Quote exactly the instances transferred; remaining stack units are commodities."""
        amount=max(0,int(amount));unit_price=max(1,int(unit_price))
        candidates=self.trade_candidates(base_item,owner)[:amount]
        total=unit_price*(amount-len(candidates))
        for artifact in candidates:
            percent=self.describe_effects(artifact)['value_percent']
            total+=max(1,unit_price*percent//100)
        return total,tuple(artifact.uid for artifact in candidates)

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
        loss=self.condition_loss(a,amount)
        a.condition=max(0,a.condition-loss);a.history.append(f'Condition {a.condition}% after {reason} at minute {minute}.')
        for v in a.components.values():
            if isinstance(v,dict) and 'condition' in v:v['condition']=max(0,int(v['condition'])-max(0,loss//2))
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


def transfer_inventory_metadata(state, registry, items, from_owner, to_owner, minute, reason):
    """Move only existing instances beside a physical stock transfer, never synthesize them."""
    artifacts = ArtifactSystem(state, registry, b'')
    for iid, amount in items.items():
        amount = max(0, int(amount))
        for artifact in artifacts.trade_candidates(iid, from_owner)[:amount]:
            artifacts.transfer_uid(artifact.uid, to_owner, minute, reason)
        # Ground and storage transfers preserve exact batches; acquiring generic
        # stock here must not use the market-only representative batch fallback.
        batches = sorted((batch for batch in state.metal_batches.values()
                          if batch.item_id == iid and batch.owner == from_owner),
                         key=lambda batch: (batch.quality, batch.uid))
        for batch in batches[:amount]:
            batch.owner = to_owner


def available_inventory_quantity(state, inventory, item_id):
    """Reserve protected instances while respecting gear already outside stack inventory."""
    physical_slots = sum(iid == item_id for iid in state.player_equipment.values())
    equipped = set(state.player_equipped_artifacts.values())
    protected = sum(artifact.uid in equipped and artifact.base_item == item_id
                    and artifact.owner == 'player' and artifact.condition > 0
                    for artifact in state.artifacts.values())
    return max(0, inventory.count(item_id) - max(0, protected - physical_slots))
