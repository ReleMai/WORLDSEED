from __future__ import annotations

from collections import Counter
from worldseed.content.registry import ContentRegistry
from worldseed.core.rng import hash_u64
from worldseed.entities.components import Inventory
from worldseed.systems.state import LivingWorldState
from worldseed.systems.crafting_ingredients import allocate_tag_inputs, resolve_recipe_inputs, signature_matches, token_matches


class CraftingSystem:
    def __init__(self,state:LivingWorldState,registry:ContentRegistry,artifact_system=None,metallurgy=None):self.state=state;self.registry=registry;self.artifact_system=artifact_system;self.metallurgy=metallurgy

    def discovery_signature(self, recipe) -> tuple[str, ...]:
        """Return the 1-5 exact-item or tag clue slots for one recipe.

        Crafting cost and discovery clues are deliberately separate. Most simple
        recipes use their full input stack. Larger recipes author discovery_items
        so the experiment grid never requires more than five physical samples.
        Repeated ids are significant quantities.
        """
        if recipe.discovery_items or recipe.discovery_tags:
            return tuple(recipe.discovery_items)+tuple("tag:"+tag for tag in recipe.discovery_tags)
        out=[]
        for iid,n in sorted(recipe.inputs.items()):
            out.extend([str(iid)]*max(0,int(n)))
        for tag,n in sorted(recipe.input_tags.items()):out.extend(["tag:"+tag]*int(n))
        return tuple(out)

    def discovery_matches(self,recipe,items,*,partial=False)->bool:
        return signature_matches(self.discovery_signature(recipe),tuple(items),self.registry,partial=partial)

    def discovery_examples(self,recipe)->tuple[str,...]:
        """Concrete carried samples for audits and authors, including tag clues."""
        return tuple(next(iid for iid in sorted(self.registry.items) if token_matches(token,iid,self.registry))
                     for token in self.discovery_signature(recipe))

    def recipe_uses_item(self,recipe,item_id:str)->bool:
        return item_id in recipe.inputs or item_id in recipe.catalysts or any(
            token_matches("tag:"+tag,item_id,self.registry) for tag in recipe.input_tags)

    def ingredient_rows(self,recipe,inv:Inventory,*,preference="auto")->list[dict]:
        allocation=allocate_tag_inputs(recipe,inv,self.registry,preference=preference)
        rows=[{"id":iid,"name":self.registry.items[iid].name,"need":n,
               "have":max(0,inv.count(iid)-recipe.catalysts.get(iid,0))} for iid,n in recipe.inputs.items()]
        for tag,need in sorted(recipe.input_tags.items()):
            options=[{"id":iid,"name":item.name,"have":inv.count(iid),"quality":item.crafting_quality,"source":item.crafting_source,"units":recipe.input_units.get(iid,1)} for iid,item in sorted(self.registry.items.items()) if tag in item.tags]
            rows.append({"id":"tag:"+tag,"name":"Any "+tag.replace("_"," "),"tag":tag,"need":need,
                         "have":sum(allocation[tag].values()),"options":options,"allocated":allocation[tag],"unit_label":"material units" if recipe.input_units else "items"})
        return rows

    def resolve_inputs(self,recipe,inv:Inventory,*,preference="auto")->dict[str,int]|None:
        return resolve_recipe_inputs(recipe,inv.items,self.registry,preference=preference)

    def preview(self,recipe_or_id,inv:Inventory,*,preference="auto",skill_level=0,work_bonus=0)->dict:
        """The exact materials and deterministic grade used by the command path."""
        from worldseed.systems.crafting_quality import ingredient_quality,output_preview
        recipe=self.registry.recipes.get(recipe_or_id) if isinstance(recipe_or_id,str) else recipe_or_id
        if recipe is None:return {}
        costs=self.resolve_inputs(recipe,inv,preference=preference)
        data={"preference":preference,"consumed":costs,"material_quality_enabled":recipe.material_quality,
              "material_quality":None,"source_label":"", "outputs":[]}
        if costs is None:return data
        material=ingredient_quality(self.state,self.registry,costs,preference=preference,metallurgy=self.metallurgy)
        data['artifact_uids']=material['artifact_uids']
        if recipe.material_quality:
            data.update(material)
            data["outputs"]=output_preview(recipe,self.registry,material,skill_level=skill_level,work_bonus=work_bonus)
        else:
            data["outputs"]=[{"id":iid,"name":self.registry.items[iid].name,"qty":qty,"quality":None,"benefits":[],"material":self.registry.items[iid].material}
                             for iid,qty in recipe.outputs.items()]
        return data

    def _discovery_requirements(self, recipe) -> set[str]:
        return set(self.discovery_signature(recipe))

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
        # Handling an item reveals its identity, not a predetermined recipe.
        # Previously learned recipes remain recorded on existing saves.
        return new_items,[]

    def recipe_pool_for_item(self,item_id:str):
        """Catalog-backed outcomes for which this item is an actual experiment clue."""
        return sorted((r for r in self.registry.recipes.values()
                       if any(token_matches(token,item_id,self.registry) for token in self.discovery_signature(r))),key=lambda r:r.id)

    def pot_candidates(self,items:tuple[str,...],inv:Inventory):
        """Read-only recipes that could result from the placed quantities."""
        counts=Counter(items)
        if not self.state.player_crafting_discovery_enabled or not 1<=len(items)<=5:
            return []
        if any(i not in self.registry.items or inv.count(i)<n for i,n in counts.items()):
            return []
        known=set(self.state.player_discovered_recipes)
        return sorted((r for r in self.registry.recipes.values()
            if r.id not in known
            and (not r.knowledge or r.knowledge in self.state.player_knowledge)
            and self.discovery_matches(r,items)
            and self.discovery_signature(r)),key=lambda r:r.id)

    def combine_in_pot(self,items:tuple[str,...],inv:Inventory,world_seed:bytes,minute:int=0) -> tuple[bool,str,int]:
        """Consume a valid experiment and select one catalog result reproducibly."""
        if not self.state.player_crafting_discovery_enabled:
            return False,'This world uses the legacy crafting catalog.',5
        counts=Counter(items)
        if not 1<=len(items)<=5 or any(i not in self.registry.items or inv.count(i)<n for i,n in counts.items()):
            return False,'Place 1–5 items you actually carry in the experiment grid.',5
        candidates=self.pot_candidates(items,inv)
        if not candidates:
            return False,'These materials reveal no new recipe. Try another combination.',5
        attempt=max(0,int(self.state.player_crafting_experiments))
        choice=hash_u64(world_seed,'crafting.discovery_pot.v1',attempt,*sorted(items))%len(candidates)
        recipe=candidates[choice]
        inv.consume(dict(counts))
        from worldseed.systems.crafting_quality import retire_consumed_artifacts
        retire_consumed_artifacts(self.state,self.registry,counts,minute=minute,reason='Used in crafting experiment')
        if self.metallurgy:self.metallurgy.consume_inputs(dict(counts),'player')
        self.state.player_discovered_recipes=sorted(set(self.state.player_discovered_recipes)|{recipe.id})
        self.state.player_unseen_recipes=sorted(set(self.state.player_unseen_recipes)|{recipe.id})
        self.state.player_crafting_experiments=attempt+1
        self.state.player_crafting_log.append({"recipe_id":recipe.id,"minute":int(minute),"ingredients":list(items)})
        self.state.player_crafting_log=self.state.player_crafting_log[-80:]
        # Experiment rewards are deliberately weaker than normal crafting.
        # A successful recipe produces one prototype per distinct output.
        samples=[]
        for iid,n in sorted(recipe.outputs.items()):
            if n<=0 or iid not in self.registry.items:continue
            inv.add(iid,1)
            samples.append(self.registry.items[iid].name)
            if self.artifact_system is not None:
                self.artifact_system.create(iid,"experiment",minute,owner="player",experimental=True)
        self.sync_discoveries(inv)
        detail=", ".join(samples) if samples else "no physical sample"
        return True,f'You discover {recipe.name}! Experimental, lower-quality prototype received: {detail}. Recipe learned.',max(10,15+recipe.difficulty*5)

    def recipe_is_discovered(self, recipe_id:str) -> bool:
        if not self.state.player_crafting_discovery_enabled:return True
        return recipe_id in set(self.state.player_discovered_recipes)

    def discovered_recipes(self, inv:Inventory|None=None):
        if not self.state.player_crafting_discovery_enabled:
            return list(self.registry.recipes.values())
        known=set(self.state.player_discovered_recipes)
        return [r for r in self.registry.recipes.values() if r.id in known]

    def researchable_recipes(self, inv:Inventory|None=None):
        # Legacy caller compatibility: the pot owns discovery choice and must
        # not reveal a named list of experiments before a combination is made.
        return []

    def experiment(self, recipe_id:str, inv:Inventory) -> tuple[bool,str,int]:
        return False,'Combine carried materials in the experiment grid to learn recipes.',5

    def discovery_tree_rows(self, inv:Inventory|None=None) -> list[tuple[str,str,str]]:
        """Return stable (recipe,status,parents) rows for graphical/terminal UIs."""
        discovered=set(self.state.player_discovered_recipes);known_items=set(self.state.player_discovered_items)
        output_to_recipes={}
        for r in self.registry.recipes.values():
            for iid in r.outputs:output_to_recipes.setdefault(iid,[]).append(r.id)
        rows=[]
        for r in sorted(self.registry.recipes.values(),key=lambda q:(q.category,q.name)):
            if not self.state.player_crafting_discovery_enabled:status='known'
            elif r.id in discovered:status='known'
            elif r.knowledge and r.knowledge not in self.state.player_knowledge:status='knowledge'
            else:
                missing=any(not any(token_matches(token,iid,self.registry) for iid in known_items) for token in self.discovery_signature(r))
                status='materials' if missing else 'locked'
            parents=sorted({pid for iid in output_to_recipes if self.recipe_uses_item(r,iid) for pid in output_to_recipes[iid] if pid!=r.id})
            rows.append((r.id,status,', '.join(parents[:3])))
        return rows
    def _best_quality(self,inv:Inventory,key:str)->int:
        return max((self.registry.items[i].quality(key) for i,n in inv.items.items() if n>0 and i in self.registry.items),default=0)
    def missing_requirements(self,recipe_id:str,inv:Inventory,nearby_structures:set[str],*,preference="auto")->list[str]:
        r=self.registry.recipes.get(recipe_id);out=[]
        if not r:return ["unknown recipe"]
        if not self.recipe_is_discovered(recipe_id):out.append("recipe not yet discovered")
        if r.knowledge and r.knowledge not in self.state.player_knowledge:out.append(f"knowledge: {r.knowledge}")
        if r.station and r.station not in nearby_structures:out.append(f"station: {self.registry.structures[r.station].name}")
        for row in self.ingredient_rows(r,inv,preference=preference):
            if row["have"]<row["need"]:out.append(f'{row["name"]} {row["have"]}/{row["need"]}')
        for iid,n in r.catalysts.items():
            if inv.count(iid)<n:out.append(f"{self.registry.items[iid].name} catalyst {inv.count(iid)}/{n}")
        for q,need in r.tool_qualities.items():
            have=self._best_quality(inv,q)
            if have<need:out.append(f"{q} quality {have}/{need}")
        if self.metallurgy:
            ok,reason=self.metallurgy.can_process(r,inv,'player')
            if not ok:out.append(reason)
        return out

    def can_craft(self,recipe_id:str,inv:Inventory,nearby_structures:set[str],*,preference="auto")->tuple[bool,str]:
        r=self.registry.recipes.get(recipe_id)
        if not r:return False,"Unknown recipe."
        if not self.recipe_is_discovered(recipe_id):return False,"You have not discovered that recipe yet."
        if r.knowledge and r.knowledge not in self.state.player_knowledge:return False,f"You lack knowledge: {r.knowledge}."
        if r.station and r.station not in nearby_structures:return False,f"Requires {self.registry.structures[r.station].name}."
        if self.resolve_inputs(r,inv,preference=preference) is None:return False,"You lack the required materials or reserved catalyst quantities."
        for quality,need in r.tool_qualities.items():
            have=self._best_quality(inv,quality)
            if have<int(need):return False,f"Requires {quality} quality {need}; your best is {have}."
        if any(inv.count(iid)<n for iid,n in r.catalysts.items()):return False,"You lack a required catalyst."
        if self.metallurgy:
            ok,why=self.metallurgy.can_process(r,inv,"player")
            if not ok:return False,why
        return True,""

    def craft(self,recipe_id:str,inv:Inventory,nearby_structures:set[str],minute:int=0,creator:str="player",skill_level:int=0,work_bonus:int=0,*,preference:str="auto")->tuple[bool,str,int]:
        if preference not in {"auto","refined","recovered"}:return False,"Choose a valid material preference.",0
        ok,why=self.can_craft(recipe_id,inv,nearby_structures,preference=preference)
        if not ok:return False,why,0
        r=self.registry.recipes[recipe_id]
        preview=self.preview(r,inv,preference=preference,skill_level=skill_level,work_bonus=work_bonus)
        costs=preview['consumed']
        if costs is None or not inv.consume(costs):return False,"Materials changed before crafting.",0
        from worldseed.systems.crafting_quality import retire_consumed_artifacts
        retire_consumed_artifacts(self.state,self.registry,costs,minute=minute,
                                  reason=f'Used in {r.name}',artifact_uids=preview.get('artifact_uids',()))
        meta=self.metallurgy.apply(r,creator,minute,consumed_inputs=costs) if self.metallurgy else None
        made=[]
        for iid,n in r.outputs.items():
            inv.add(iid,n)
            if self.artifact_system and iid in self.registry.items and (r.material_quality or any(t in self.registry.items[iid].tags for t in ("weapon","armor","tool"))):
                for _ in range(n):
                    if r.material_quality:
                        output=next(row for row in preview['outputs'] if row['id']==iid)
                        components={'body':{'material':output['material'],'quality':output['quality'],'condition':100},
                                    'crafting':{'quality_version':1,'recipe_id':r.id,'material_quality':preview['material_quality'],
                                                'source':preview['source'],'ingredients':preview['ingredients']}}
                        made.append(self.artifact_system.create(iid,creator,minute,quality_hint=output['quality'],material_override=output['material'],components_override=components,process_notes=(meta.notes if meta else None)).name)
                    else:
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
        inv.consume(costs)
        from worldseed.systems.crafting_quality import retire_consumed_artifacts
        retire_consumed_artifacts(self.state,self.registry,costs,minute=minute,reason=f'Used in {d.name}')
        inv.add(d.output_item,1)
        quality=sum(q*w for q,w in quality_rows)//max(1,sum(w for _,w in quality_rows));primary=components[d.primary_component]['material']
        art=self.artifact_system.create(d.output_item,creator,minute,quality_hint=quality,material_override=primary,process_notes=['component-built'],components_override=components) if self.artifact_system else None
        return True,f"You assemble {d.name} from selected components."+(f" {art.name}, quality {quality}." if art else ""),d.minutes

    def learn(self,fact:str)->None:
        if fact not in self.state.player_knowledge:self.state.player_knowledge.append(fact)
