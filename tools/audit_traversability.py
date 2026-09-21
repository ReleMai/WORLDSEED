from __future__ import annotations

import argparse
import gc
import json
import statistics
import tempfile
from collections import deque
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worldseed.app import _load_context
from worldseed.core.coords import WorldPos
from worldseed.ui.startup import StartSelection


def _profile():
    return {
        'attributes': {'strength': 5, 'agility': 5, 'endurance': 5, 'intellect': 5, 'perception': 5, 'will': 5},
        'skills': {k: 0 for k in ('athletics','survival','foraging','woodcutting','mining','hunting','melee','crafting','medicine','scholarship','persuasion','trading','naturalism','arcana')},
        'talents': [],
    }


def audit(sim, radius: int = 25) -> dict:
    p = sim.player_pos
    terrain_open = set()
    walkable = set()
    blockers = set()
    for y in range(p.y-radius, p.y+radius+1):
        for x in range(p.x-radius, p.x+radius+1):
            q = WorldPos(x,y,p.z)
            if not sim.world.is_passable(q):
                continue
            terrain_open.add((x,y))
            if sim.resources.blocks_movement(q):
                blockers.add((x,y))
            else:
                walkable.add((x,y))

    start=(p.x,p.y)
    reached=set()
    if start in walkable:
        dq=deque([start]);reached.add(start)
        while dq:
            x,y=dq.popleft()
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                n=(x+dx,y+dy)
                if n in walkable and n not in reached:
                    reached.add(n);dq.append(n)

    adjacent_blocker_pairs=0
    for x,y in blockers:
        if (x+1,y) in blockers: adjacent_blocker_pairs+=1
        if (x,y+1) in blockers: adjacent_blocker_pairs+=1

    return {
        'spawn':[p.x,p.y,p.z],
        'terrain_open':len(terrain_open),
        'walkable':len(walkable),
        'blockers':len(blockers),
        'reachable':len(reached),
        'walkable_retention': (len(walkable)/len(terrain_open)) if terrain_open else 0.0,
        'resource_connectivity': (len(reached)/len(walkable)) if walkable else 0.0,
        'blocker_occupancy': (len(blockers)/len(terrain_open)) if terrain_open else 1.0,
        'adjacent_blocker_pairs': adjacent_blocker_pairs,
    }


def main() -> int:
    ap=argparse.ArgumentParser(description='Audit WORLDSEED surface traversability after natural-resource placement.')
    ap.add_argument('--seeds',type=int,default=10)
    ap.add_argument('--radius',type=int,default=25)
    ap.add_argument('--json',action='store_true')
    a=ap.parse_args()
    rows=[]
    with tempfile.TemporaryDirectory() as td:
        root=Path(td)
        for i in range(a.seeds):
            seed=f'rc10-traverse-{i}'.encode()
            sel=StartSelection(root/f'w{i}.db',True,f'Traverse {i}',seed.hex(),'Tester','custom',_profile())
            ctx=_load_context(sel,prepare_world=False)
            try:rows.append(audit(ctx.sim,a.radius))
            finally:
                ctx.db.close();del ctx;gc.collect()
    summary={
        'seeds':a.seeds,'radius':a.radius,
        'min_resource_connectivity':min(r['resource_connectivity'] for r in rows),
        'median_resource_connectivity':statistics.median(r['resource_connectivity'] for r in rows),
        'min_walkable_retention':min(r['walkable_retention'] for r in rows),
        'max_blocker_occupancy':max(r['blocker_occupancy'] for r in rows),
        'adjacent_blocker_pairs':sum(r['adjacent_blocker_pairs'] for r in rows),
    }
    if a.json:print(json.dumps({'summary':summary,'rows':rows},indent=2,sort_keys=True))
    else:
        print(summary)
        for i,r in enumerate(rows):print(i,r)
    # Terrain itself may partition islands/coasts, but optional resource blockers
    # must not materially fragment local walkable space.
    bad=[r for r in rows if r['resource_connectivity'] < .97 or r['walkable_retention'] < .82 or r['adjacent_blocker_pairs']]
    return 1 if bad else 0


if __name__=='__main__':raise SystemExit(main())
