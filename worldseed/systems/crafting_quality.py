"""Read-only ingredient provenance and deterministic output grades."""
from worldseed.systems.artifacts import crafting_effects


def ingredient_quality(state, registry, costs, *, owner='player', preference='auto', metallurgy=None):
    rows=[]
    consumed_artifacts=[]
    for iid, count in sorted(costs.items()):
        item=registry.items[iid]
        equipped=set(state.player_equipped_artifacts.values()) if owner=='player' else set()
        artifacts=[a for a in state.artifacts.values() if a.base_item==iid and a.owner==owner and a.condition>0 and a.uid not in equipped]
        artifacts.sort(key=lambda a: ((a.quality*a.condition//100) * (1 if preference=='recovered' else -1), a.uid))
        tracked=artifacts[:count]
        for artifact in tracked:
            grade=max(0,min(100,artifact.quality*artifact.condition//100))
            source=artifact.components.get('crafting',{}).get('source',item.crafting_source)
            rows.append({'id':iid,'name':item.name,'qty':1,'quality':grade,'source':source,
                         'mass_g':max(1,item.mass_g),'material':artifact.material})
            consumed_artifacts.append(artifact.uid)
        remaining=count-len(tracked)
        if metallurgy is not None and iid in metallurgy.METAL_ITEMS:
            batches=list(reversed(metallurgy.batches(owner,iid)))[:remaining]
            for batch in batches:
                rows.append({'id':iid,'name':item.name,'qty':1,'quality':batch.quality,
                             'source':item.crafting_source,'mass_g':max(1,item.mass_g),'material':batch.material})
            generic=remaining-len(batches)
            if generic:
                rows.append({'id':iid,'name':item.name,'qty':generic,'quality':50,
                             'source':item.crafting_source,'mass_g':max(1,item.mass_g),'material':item.material or 'unknown'})
        elif remaining:
            rows.append({'id':iid,'name':item.name,'qty':remaining,'quality':item.crafting_quality,
                         'source':item.crafting_source,'mass_g':max(1,item.mass_g),'material':item.material or 'unknown'})
    weight=sum(row['mass_g']*row['qty'] for row in rows)
    grade=sum(row['quality']*row['mass_g']*row['qty'] for row in rows)//max(1,weight)
    sources={row['source'] for row in rows if row['source']}
    source=next(iter(sources)) if len(sources)==1 else ('mixed' if sources else '')
    labels={'recovered':'Recovered parts','refined':'Refined stock','raw':'Raw material','mixed':'Mixed materials','':'Ordinary materials'}
    dominant=max(rows,key=lambda row:(row['mass_g']*row['qty'],row['id']),default={})
    return {'material_quality':grade,'source':source,'source_label':labels.get(source,'Mixed materials'),
            'ingredients':rows,'artifact_uids':consumed_artifacts,'material':dominant.get('material','unknown')}


def output_preview(recipe, registry, material, *, skill_level=0, work_bonus=0):
    grade=max(5,min(99,material['material_quality']+min(12,max(0,int(skill_level))*2)+min(8,max(0,int(work_bonus)))))
    outputs=[]
    for iid,qty in recipe.outputs.items():
        item=registry.items[iid]
        effects=crafting_effects(item,grade)
        # The blade/head/body retains its material family even when a heavy haft dominates total input mass.
        metals={'core:iron','core:steel','core:copper','core:bronze'}
        primary=[row for row in material['ingredients'] if row['material']==item.material
                 or (item.material in metals and row['material'] in metals)]
        primary_row=max(primary,key=lambda row:(row['mass_g']*row['qty'],row['id']),default={})
        output_material=primary_row.get('material',item.material or material['material'])
        outputs.append({'id':iid,'name':item.name,'qty':qty,'quality':grade,
                        'material':output_material,'benefits':effects['benefits'],**{key:value for key,value in effects.items() if key!='benefits'}})
    return outputs


def retire_consumed_artifacts(state, registry, costs, *, owner='player', minute=0,
                              reason='Consumed', artifact_uids=None):
    """Retire exact spent instances; commodity metadata never outlives its stock."""
    remaining = {iid: max(0, int(amount)) for iid, amount in costs.items()}
    equipped = set(state.player_equipped_artifacts.values()) if owner == 'player' else set()
    if artifact_uids is None:
        rows = sorted(state.artifacts.values(), key=lambda artifact: (-artifact.quality, artifact.uid))
    else:
        rows = [state.artifacts[uid] for uid in artifact_uids if uid in state.artifacts]
    retired = []
    for artifact in rows:
        iid = artifact.base_item
        if (artifact.owner != owner or artifact.uid in equipped or artifact.condition <= 0
                or remaining.get(iid, 0) <= 0):
            continue
        remaining[iid] -= 1
        retired.append(artifact.uid)
        item = registry.items.get(iid)
        durable = item is not None and (item.weapon_damage or item.equip_slot
                                       or any(tag in item.tags for tag in ('weapon', 'armor', 'tool')))
        if durable:
            artifact.owner = 'consumed'
            artifact.history.append(f'{reason} at minute {minute}.')
            artifact.provenance.append({'minute': minute, 'from': owner, 'to': 'consumed', 'reason': reason})
        else:
            state.artifacts.pop(artifact.uid, None)
    return tuple(retired)
