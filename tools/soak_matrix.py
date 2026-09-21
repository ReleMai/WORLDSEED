from __future__ import annotations
from pathlib import Path
import argparse
import json
import sys
import tempfile
import time
import tracemalloc
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.canonical import canonical_hash
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory,Position,Vitals
from worldseed.entities.store import EntityStore
from worldseed.persistence.database import WorldDatabase
from worldseed.sim.engine import Simulation
from worldseed.systems.state import LivingWorldState
from worldseed.world.generator import WorldGenerator
from worldseed.world.world import World

DAYS_PER_YEAR=120


def make_sim(seed:bytes,root:Path):
    reg=ContentRegistry.load(DATA_DIR);db=WorldDatabase.create(root/'soak.db','soak',seed.hex());world=World(WorldGenerator(seed,reg),reg,db);e=EntityStore();pid=e.spawn(preferred_id=1);e.add(pid,Position(WorldPos(0,0,0)));e.add(pid,Inventory());e.add(pid,Vitals());sim=Simulation(world,e,reg,0,LivingWorldState(),seed);return db,sim


def invariants(sim:Simulation)->list[str]:
    errors=[]
    if any(c.count<0 for c in sim.state.cohorts.values()):errors.append('negative cohort')
    if any(s.population<0 for s in sim.state.settlements.values()):errors.append('negative settlement population')
    if any(n.wealth<0 for n in sim.state.npcs.values()):errors.append('negative NPC wealth')
    if any(v<0 for s in sim.state.settlements.values() for v in s.stocks.values()):errors.append('negative settlement stock')
    if any(p.condition<0 for p in sim.state.properties.values()):errors.append('negative property condition')
    if any(r.danger<0 or r.danger>100 for r in sim.state.trade_routes.values()):errors.append('route danger out of bounds')
    for npc in sim.state.npcs.values():
        if npc.spouse_uid and npc.spouse_uid not in sim.state.npcs:errors.append(f'orphan spouse {npc.uid}')
        if npc.settlement_id and npc.settlement_id not in sim.state.settlements:errors.append(f'orphan settlement {npc.uid}')
    for office in sim.state.offices.values():
        if office.holder_uid and office.holder_uid not in sim.state.npcs:errors.append(f'orphan office holder {office.uid}')
    # Health / epidemiology invariants. Aggregate outbreaks are bounded by the
    # living settlement population; individual infections must reference a live
    # host record or the active player infection list.
    for outbreak in sim.state.diseases.values():
        if min(outbreak.infected,outbreak.recovered,outbreak.deaths,outbreak.immune)<0:errors.append(f'negative disease count {outbreak.disease_id}')
        if not 0<=outbreak.severity<=100 or not 0<=outbreak.contagiousness<=100:errors.append(f'disease metric out of bounds {outbreak.disease_id}')
        town=sim.state.settlements.get(outbreak.settlement_id)
        if outbreak.settlement_id and town is None:errors.append(f'orphan disease settlement {outbreak.settlement_id}')
        elif town is not None and outbreak.infected>town.population:errors.append(f'outbreak exceeds settlement population {outbreak.settlement_id}')
    active_player=set(sim.state.player_infections)
    for uid,inf in sim.state.infections.items():
        if inf.host_type=='npc' and inf.host_id not in sim.state.npcs:errors.append(f'orphan infection host {uid}')
        if inf.host_type=='player' and inf.stage not in {'recovered','fatal'} and uid not in active_player:errors.append(f'unreferenced player infection {uid}')
        if inf.severity<0 or inf.viral_load<0:errors.append(f'negative infection metric {uid}')
    for npc in sim.state.npcs.values():
        for uid in npc.infections:
            if uid not in sim.state.infections:errors.append(f'orphan NPC infection {npc.uid}->{uid}')
    for caravan in sim.state.caravans.values():
        if any(v<0 for v in caravan.pathogen_load.values()):errors.append(f'negative caravan pathogen load {caravan.uid}')
    for cohort in sim.state.migration_cohorts.values():
        if any(v<0 for v in cohort.pathogen_load.values()):errors.append(f'negative migration pathogen load {cohort.uid}')
    return sorted(set(errors))


def run_one(seed_text:str,years:int,policy:str='full',trace_memory:bool=False)->dict:
    seed=seed_text.encode();days=years*DAYS_PER_YEAR
    with tempfile.TemporaryDirectory() as td:
        db,sim=make_sim(seed,Path(td))
        if trace_memory:tracemalloc.start()
        start=time.perf_counter();summary=sim.advance_offline(days*1440,policy);elapsed=time.perf_counter()-start
        peak=0
        if trace_memory:
            _,peak=tracemalloc.get_traced_memory();tracemalloc.stop()
        state_dict=sim.state.to_dict();state_bytes=len(json.dumps(state_dict,separators=(',',':'),sort_keys=True).encode('utf-8'))
        errs=invariants(sim);digest=canonical_hash(state_dict);result={
            'seed':seed_text,'years':years,'days':days,'seconds':round(elapsed,3),'state_mb':round(state_bytes/1024/1024,2),'hash':digest,
            'settlements':len(sim.state.settlements),'realized_regions':len(sim.state.realized_regions),'npcs':len(sim.state.npcs),'cohorts':len(sim.state.cohorts),'creatures':len(sim.state.creatures),
            'live_history':len(sim.state.history),'archive_buckets':len(sim.state.history_archive),'routes':len(sim.state.trade_routes),'properties':len(sim.state.properties),
            'summary':summary,'errors':errs,
        }
        if trace_memory:result['peak_mb']=round(peak/1024/1024,2)
        db.close();return result


def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('--years',type=int,default=25);ap.add_argument('--seeds',type=int,default=4);ap.add_argument('--prefix',default='matrix');ap.add_argument('--policy',choices=['safe','full'],default='full');ap.add_argument('--json',action='store_true');ap.add_argument('--trace-memory',action='store_true',help='Enable tracemalloc (slow; best for shorter runs).');a=ap.parse_args();results=[]
    for i in range(a.seeds):
        row=run_one(f'{a.prefix}-{i}',a.years,a.policy,a.trace_memory);results.append(row);print(json.dumps(row,sort_keys=True) if a.json else row)
    failed=any(r['errors'] for r in results);return 1 if failed else 0

if __name__=='__main__':raise SystemExit(main())
