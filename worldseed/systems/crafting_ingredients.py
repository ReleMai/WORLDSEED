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


def allocate_tag_inputs(recipe, inv, registry):
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
    for iid in sorted(remaining,key=lambda key:(registry.items[key].base_value,key)):
        if remaining[iid]<=0:continue
        matches=[tag for tag in tags if tag in registry.items[iid].tags]
        if not matches:continue
        node=('item',iid);link(source,node,remaining[iid])
        for tag in matches:link(node,('tag',tag),remaining[iid])
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
