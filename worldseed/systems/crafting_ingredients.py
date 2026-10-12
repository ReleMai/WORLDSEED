"""Read-only, deterministic allocation for exact and tagged recipe ingredients."""
from collections import deque


def token_matches(token, item_id, registry):
    if not token.startswith('tag:'):
        return token == item_id
    item=registry.items.get(item_id)
    return item is not None and token[4:] in item.tags


def signature_matches(signature, samples, registry, *, partial=False):
    """Match physical samples to at most five clue slots without double use."""
    if len(samples)>len(signature) or (not partial and len(samples)!=len(signature)):
        return False
    options=[tuple(index for index,token in enumerate(signature)
                   if token_matches(token,iid,registry)) for iid in samples]
    options.sort(key=lambda row:(len(row),row))
    def assign(index,used):
        if index==len(options):return True
        return any(assign(index+1,used|{slot}) for slot in options[index] if slot not in used)
    return assign(0,set())


def allocate_tag_inputs(recipe, inv, registry, *, preference="auto"):
    """Reserve exact inputs/catalysts, then solve overlapping tag demands.

    The small bipartite flow graph uses carried item types and authored tags;
    it never examines world state. Residual edges allow a broad requirement to
    release scarce material to a narrower one, avoiding greedy false failures.
    """
    if not recipe.input_tags:return {}
    remaining={iid:max(0,int(count)-int(recipe.inputs.get(iid,0))-int(recipe.catalysts.get(iid,0)))
               for iid,count in inv.items.items() if count>0 and iid in registry.items}
    source=('source','');sink=('sink','');edges={};capacity={}
    def link(left,right,amount):
        edges.setdefault(left,[]).append(right);edges.setdefault(right,[]).append(left)
        capacity[left,right]=int(amount);capacity[right,left]=0
    tags=sorted(recipe.input_tags)
    units=getattr(recipe,"input_units",{})
    def priority(iid):
        item=registry.items[iid]
        if preference=="recovered":return (0 if item.crafting_source=="recovered" else 1,item.crafting_quality,item.base_value,iid)
        if preference=="refined":return (0 if item.crafting_source=="refined" else 1,-item.crafting_quality,item.base_value,iid)
        if getattr(recipe,"material_quality",False):return (-item.crafting_quality,item.base_value,iid)
        return (item.base_value,iid)
    for iid in sorted(remaining,key=priority):
        if remaining[iid]<=0:continue
        matches=[tag for tag in tags if tag in registry.items[iid].tags]
        if not matches:continue
        supply=remaining[iid]*int(units.get(iid,1))
        node=('item',iid);link(source,node,supply)
        for tag in matches:link(node,('tag',tag),supply)
    for tag in tags:link(('tag',tag),sink,recipe.input_tags[tag])
    while True:
        parent={source:None};pending=deque([source])
        while pending and sink not in parent:
            node=pending.popleft()
            for other in edges.get(node,()):
                if other not in parent and capacity[node,other]>0:
                    parent[other]=node;pending.append(other)
        if sink not in parent:break
        amount=None;node=sink
        while parent[node] is not None:
            previous=parent[node];value=capacity[previous,node]
            amount=value if amount is None else min(amount,value);node=previous
        node=sink
        while parent[node] is not None:
            previous=parent[node];capacity[previous,node]-=amount;capacity[node,previous]+=amount;node=previous
    allocation={tag:{} for tag in tags}
    for tag in tags:
        for node in edges.get(('tag',tag),()):
            if node[0]=='item' and capacity.get((('tag',tag),node),0)>0:
                allocation[tag][node[1]]=capacity[('tag',tag),node]
    return allocation

def resolve_recipe_inputs(recipe, stocks, registry, batches=1, *, preference="auto"):
    """Shared deterministic exact/tag allocation; reserve catalysts, never consume."""
    from types import SimpleNamespace
    batches=int(batches)
    if batches<1:return {}
    exact={iid:int(n)*batches for iid,n in recipe.inputs.items()}
    catalysts={iid:int(n) for iid,n in recipe.catalysts.items()}
    available={iid:int(n) for iid,n in stocks.items() if int(n)>0}
    if any(available.get(iid,0)<qty+catalysts.get(iid,0) for iid,qty in exact.items()):return None
    if any(available.get(iid,0)<qty for iid,qty in catalysts.items()):return None
    if not recipe.input_tags:return exact
    scaled=SimpleNamespace(inputs=exact,catalysts=catalysts,input_tags={tag:int(n)*batches for tag,n in recipe.input_tags.items()},input_units=getattr(recipe,"input_units",{}),material_quality=getattr(recipe,"material_quality",False))
    assigned=allocate_tag_inputs(scaled,SimpleNamespace(items=available),registry,preference=preference)
    if any(sum(assigned.get(tag,{}).values())!=qty for tag,qty in scaled.input_tags.items()):return None
    # One physical piece may supply several compatible roles. Round once after
    # summing all its assigned material units, so no piece is counted twice.
    equivalent={}
    for choices in assigned.values():
        for iid,n in choices.items():equivalent[iid]=equivalent.get(iid,0)+n
    costs=dict(exact)
    for iid,n in equivalent.items():
        units=getattr(recipe,"input_units",{}).get(iid,1)
        costs[iid]=costs.get(iid,0)+(n+units-1)//units
    return costs


def max_recipe_batches(recipe,stocks,registry,limit):
    """Find maximal feasible batches with logarithmic tagged allocations."""
    low,high=0,max(0,int(limit))
    while low<high:
        mid=(low+high+1)//2
        if resolve_recipe_inputs(recipe,stocks,registry,mid) is not None:low=mid
        else:high=mid-1
    return low
