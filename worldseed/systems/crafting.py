from __future__ import annotations

from worldseed.content.registry import ContentRegistry
from worldseed.entities.components import Inventory
from worldseed.systems.state import LivingWorldState


class CraftingSystem:
    def __init__(self,state:LivingWorldState,registry:ContentRegistry,artifact_system=None,metallurgy=None):self.state=state;self.registry=registry;self.artifact_system=artifact_system;self.metallurgy=metallurgy

    def _discovery_requirements(self, recipe) -> set[str]:
        return set(recipe.discovery_items or recipe.inputs.keys())

    def discovery_requirements(self, recipe) -> set[str]:
        """Return the material clues for a recipe without changing discovery state."""
        return set(self._discovery_requirements(recipe))

    def _discovery_mode(self, recipe) -> str:
        if recipe.discovery_mode:
            return recipe.discovery_mode
        if recipe.knowledge:
            return 'knowledge'
        req=self._discovery_requirements(recipe)
        return 'auto' if len(req)<=1 else 'experiment'

    def sync_discoveries(self, inv:Inventory) -> tuple[list[str],list[str]]:
        """Learn carried material types and any immediately implied recipes.

        New worlds use this discovery layer. Legacy worlds keep the old recipe
        visibility contract until explicitly migrated, preserving old saves.
        """
        if not self.state.player_crafting_discovery_enabled:
            return [],[]
        known_items=set(self.state.player_discovered_items)
        new_items=[]
        for iid,n in sorted(inv.items.items()):
            if n>0 and iid in self.registry.items and iid not in known_items:
                known_items.add(iid);new_items.append(iid)
        if new_items:self.state.player_discovered_items=sorted(known_items)
        known_recipes=set(self.state.player_discovered_recipes);new_recipes=[]
        for r in sorted(self.registry.recipes.values(),key=lambda x:x.id):
            if r.id in known_recipes:continue
            if r.knowledge and r.knowledge not in self.state.player_knowledge:continue
            mode=self._discovery_mode(r);req=self._discovery_requirements(r)
            if mode=='knowledge' or (mode=='auto' and req.issubset(known_items)):
                known_recipes.add(r.id);new_recipes.append(r.id)
        if new_recipes:self.state.player_discovered_recipes=sorted(known_recipes)
        return new_items,new_recipes

    def recipe_is_discovered(self, recipe_id:str) -> bool:
        if not self.state.player_crafting_discovery_enabled:return True
        return recipe_id in set(self.state.player_discovered_recipes)

    def discovered_recipes(self, inv:Inventory|None=None):
        if not self.state.player_crafting_discovery_enabled:
            return list(self.registry.recipes.values())
        known=set(self.state.player_discovered_recipes)
        return [r for r in self.registry.recipes.values() if r.id in known]

    def researchable_recipes(self, inv:Inventory|None=None):
        if not self.state.player_crafting_discovery_enabled:return []
        known_items=set(self.state.player_discovered_items);known=set(self.state.player_discovered_recipes)
        out=[]
        for r in self.registry.recipes.values():
            if r.id in known or self._discovery_mode(r)!='experiment':continue
            if r.knowledge and r.knowledge not in self.state.player_knowledge:continue
            if self._discovery_requirements(r).issubset(known_items):out.append(r)
        return sorted(out,key=lambda r:(r.category,r.name))

    def experiment(self, recipe_id:str, inv:Inventory) -> tuple[bool,str,int]:
        if not self.state.player_crafting_discovery_enabled:
            return False,'This world uses the legacy crafting catalog.',5
        self.sync_discoveries(inv)
        r=self.registry.recipes.get(recipe_id)
        if not r:return False,'Unknown crafting idea.',5
        if self.recipe_is_discovered(recipe_id):return False,f'You already understand {r.name}.',5
        if r not in self.researchable_recipes(inv):return False,'You have not handled enough of the required materials to test that idea.',5
        self.state.player_discovered_recipes=sorted(set(self.state.player_discovered_recipes)|{recipe_id})
        self.state.player_crafting_experiments=max(0,int(self.state.player_crafting_experiments))+1
        minutes=max(10,15+r.difficulty*5)
        return True,f'Through trial and error, you work out how to {r.name.lower()}. The recipe is now discovered.',minutes

    def discovery_tree_rows(self, inv:Inventory|None=None) -> list[tuple[str,str,str]]:
        """Return stable (recipe,status,parents) rows for graphical/terminal UIs."""
        discovered=set(self.state.player_discovered_recipes);known_items=set(self.state.player_discovered_items)
        output_to_recipes={}
        for r in self.registry.recipes.values():
            for iid in r.outputs:output_to_recipes.setdefault(iid,[]).append(r.id)
        rows=[]
        researchable={r.id for r in self.researchable_recipes(inv)} if self.state.player_crafting_discovery_enabled else set()
        for r in sorted(self.registry.recipes.values(),key=lambda q:(q.category,q.name)):
            if not self.state.player_crafting_discovery_enabled:status='known'
            elif r.id in discovered:status='known'
            elif r.id in researchable:status='experiment'
            elif r.knowledge and r.knowledge not in self.state.player_knowledge:status='knowledge'
            else:
                req=self._discovery_requirements(r);status='materials' if req-known_items else 'locked'
            parents=sorted({pid for iid in r.inputs for pid in output_to_recipes.get(iid,[]) if pid!=r.id})
            rows.append((r.id,status,', '.join(parents[:3])))
        return rows
    def _best_quality(self,inv:Inventory,key:str)->int:
        return max((self.registry.items[i].quality(key) for i,n in inv.items.items() if n>0 and i in self.registry.items),default=0)
    def missing_requirements(self,recipe_id:str,inv:Inventory,nearby_structures:set[str])->list[str]:
        r=self.registry.recipes.get(recipe_id);out=[]
        if not r:return ["unknown recipe"]
        if not self.recipe_is_discovered(recipe_id):out.append("recipe not yet discovered")
        if r.knowledge and r.knowledge not in self.state.player_knowledge:out.append(f"knowledge: {r.knowledge}")
        if r.station and r.station not in nearby_structures:out.append(f"station: {self.registry.structures[r.station].name}")
        for iid,n in r.inputs.items():
            if inv.count(iid)<n:out.append(f"{self.registry.items[iid].name} {inv.count(iid)}/{n}")
        for q,need in r.tool_qualities.items():
            have=self._best_quality(inv,q)
            if have<need:out.append(f"{q} quality {have}/{need}")
        return out

    def can_craft(self,recipe_id:str,inv:Inventory,nearby_structures:set[str])->tuple[bool,str]:
        r=self.registry.recipes.get(recipe_id)
        if not r:return False,"Unknown recipe."
        if not self.recipe_is_discovered(recipe_id):return False,"You have not discovered that recipe yet."
        if r.knowledge and r.knowledge not in self.state.player_knowledge:return False,f"You lack knowledge: {r.knowledge}."
        if r.station and r.station not in nearby_structures:return False,f"Requires {self.registry.structures[r.station].name}."
        if not inv.has(r.inputs):return False,"You lack the required materials."
        for quality,need in r.tool_qualities.items():
            have=self._best_quality(inv,quality)
            if have<int(need):return False,f"Requires {quality} quality {need}; your best is {have}."
        if any(inv.count(iid)<n for iid,n in r.catalysts.items()):return False,"You lack a required catalyst."
        if self.metallurgy:
            ok,why=self.metallurgy.can_process(r,inv,"player")
            if not ok:return False,why
        return True,""

    def craft(self,recipe_id:str,inv:Inventory,nearby_structures:set[str],minute:int=0,creator:str="player",skill_level:int=0,work_bonus:int=0)->tuple[bool,str,int]:
        ok,why=self.can_craft(recipe_id,inv,nearby_structures)
        if not ok:return False,why,0
        r=self.registry.recipes[recipe_id];inv.consume(r.inputs)
        meta=self.metallurgy.apply(r,creator,minute) if self.metallurgy else None
        made=[]
        for iid,n in r.outputs.items():
            inv.add(iid,n)
            if self.artifact_system and iid in self.registry.items and any(t in self.registry.items[iid].tags for t in ("weapon","armor","tool")):
                for _ in range(n):
                    made.append(self.artifact_system.create(iid,creator,minute,quality_hint=(meta.quality_hint if meta else None),material_override=(meta.material if meta else None),process_notes=(meta.notes if meta else None)).name)
        suffix=(" Artifact: "+", ".join(made)) if made else ""
        metal=(f" Metal quality {meta.quality_hint}." if meta and meta.quality_hint is not None else "")
        self.sync_discoveries(inv)
        minutes=max(1,r.minutes*max(45,100-skill_level*4-work_bonus)//100)
        return True,f"You complete {r.name}."+metal+suffix,minutes

    def can_craft_design(self,design_id:str,choices:dict[str,str],inv:Inventory,nearby_structures:set[str])->tuple[bool,str]:
        d=self.registry.designs.get(design_id)
        if not d:return False,"Unknown component design."
        if d.knowledge and d.knowledge not in self.state.player_knowledge:return False,f"You lack knowledge: {d.knowledge}."
        if d.station and d.station not in nearby_structures:return False,f"Requires {self.registry.structures[d.station].name}."
        costs={}
        for slot,options in d.components.items():
            choice=choices.get(slot)
            if choice not in options:return False,f"Choose a valid material for {slot}."
            costs[choice]=costs.get(choice,0)+int(options[choice]['qty'])
        if not inv.has(costs):return False,"You lack the selected component materials."
        return True,""

    def craft_design(self,design_id:str,choices:dict[str,str],inv:Inventory,nearby_structures:set[str],minute:int=0,creator:str='player')->tuple[bool,str,int]:
        ok,why=self.can_craft_design(design_id,choices,inv,nearby_structures)
        if not ok:return False,why,0
        d=self.registry.designs[design_id];costs={};components={};quality_rows=[]
        # Determine metadata before consuming the stack counts; metal metadata consumption mirrors each selected unit.
        for slot,choice in choices.items():
            meta=d.components[slot][choice];qty=int(meta['qty']);costs[choice]=costs.get(choice,0)+qty
            if self.metallurgy:
                qmeta=self.metallurgy.consume_component_input(choice,'player')
                q=qmeta.quality_hint or 50;material=qmeta.material or meta['material'];notes=list(qmeta.notes or [])
                # Additional identical units are commodity mass rather than separately treated batches.
                for _ in range(max(0,qty-1)):
                    if choice in self.metallurgy.METAL_ITEMS:self.metallurgy.consume_component_input(choice,'player')
            else:q=50;material=meta['material'];notes=[]
            mat=self.registry.materials.get(material);property_q=(mat.hardness+mat.toughness+(mat.edge if slot in ('blade','head') else 0))//(3 if slot in ('blade','head') else 2) if mat else 50
            q=max(15,min(100,(q+property_q)//2));components[slot]={'input_item':choice,'material':material,'quality':q,'condition':100,'notes':notes};quality_rows.append((q,2 if slot==d.primary_component else 1))
        inv.consume(costs);inv.add(d.output_item,1)
        quality=sum(q*w for q,w in quality_rows)//max(1,sum(w for _,w in quality_rows));primary=components[d.primary_component]['material']
        art=self.artifact_system.create(d.output_item,creator,minute,quality_hint=quality,material_override=primary,process_notes=['component-built'],components_override=components) if self.artifact_system else None
        return True,f"You assemble {d.name} from selected components."+(f" {art.name}, quality {quality}." if art else ""),d.minutes

    def learn(self,fact:str)->None:
        if fact not in self.state.player_knowledge:self.state.player_knowledge.append(fact)
