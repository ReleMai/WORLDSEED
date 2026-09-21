from __future__ import annotations
from pathlib import Path
import argparse, gc, json, statistics, sys, tempfile
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worldseed.app import _load_context
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory
from worldseed.ui.startup import StartSelection


def build_profile():
    return {'attributes':{'strength':5,'agility':5,'endurance':5,'intellect':5,'perception':5,'will':5},
            'skills':{'athletics':0,'survival':0,'foraging':0,'woodcutting':0,'mining':0,'hunting':0,'melee':0,'crafting':0,'medicine':0,'scholarship':0,'persuasion':0,'trading':0,'naturalism':0,'arcana':0},
            'talents':[]}

def scan(sim, radius=14):
    p=sim.player_pos
    cats={'stone':0,'branch':0,'fiber':0,'edible':0,'water':0,'trees':0}
    nearest={k:None for k in cats}
    for y in range(p.y-radius,p.y+radius+1):
        for x in range(p.x-radius,p.x+radius+1):
            q=WorldPos(x,y,p.z);dist=abs(x-p.x)+abs(y-p.y)
            if sim.world.tile_at(q).terrain_id=='core:water':
                cats['water']+=1;nearest['water']=dist if nearest['water'] is None else min(nearest['water'],dist)
            fv=sim.resources.feature_at(q)
            if not fv or fv.stage!='mature':continue
            rd=sim.registry.resources.get(fv.feature_id)
            if not rd:continue
            ys=set(rd.yields)
            pairs=[]
            if 'core:stone' in ys:pairs.append('stone')
            if 'core:stout_branch' in ys:pairs.append('branch')
            if 'core:brush' in ys:pairs.append('fiber')
            if 'tree' in rd.tags:pairs.append('trees')
            if any(sim.registry.items.get(i) and sim.registry.items[i].nutrition>0 for i in ys):pairs.append('edible')
            for k in pairs:
                cats[k]+=1;nearest[k]=dist if nearest[k] is None else min(nearest[k],dist)
    return cats,nearest

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--seeds',type=int,default=20);ap.add_argument('--radius',type=int,default=14);ap.add_argument('--json',action='store_true');a=ap.parse_args()
    rows=[]
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        for i in range(a.seeds):
            seed=f'rc7-balance-{i}'.encode()
            sel=StartSelection(root/f'w{i}.db',True,f'W{i}',seed.hex(),'Tester','custom',build_profile())
            ctx=_load_context(sel,prepare_world=False)
            try:
                inv=ctx.entities.get(ctx.player_id,Inventory)
                cats,nearest=scan(ctx.sim,a.radius)
                rows.append({'seed':i,'spawn':[ctx.sim.player_pos.x,ctx.sim.player_pos.y],'empty':not bool(inv.items),'counts':cats,'nearest':nearest})
            finally:
                ctx.db.close();del ctx;gc.collect()
    weak=[r for r in rows if not (r['counts']['stone'] and r['counts']['branch'] and r['counts']['fiber'])]
    summary={'seeds':a.seeds,'radius':a.radius,'weak_starts':len(weak),'all_empty':all(r['empty'] for r in rows),
             'median_counts':{k:statistics.median([r['counts'][k] for r in rows]) for k in rows[0]['counts']},
             'max_nearest':{k:max([r['nearest'][k] for r in rows if r['nearest'][k] is not None],default=None) for k in rows[0]['nearest']}}
    if a.json:print(json.dumps({'summary':summary,'rows':rows},indent=2,sort_keys=True))
    else:
        print(summary)
        for r in weak:print('WEAK',r)
    return 1 if weak or not summary['all_empty'] else 0
if __name__=='__main__':raise SystemExit(main())
