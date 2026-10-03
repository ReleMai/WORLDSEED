"""Audit access migration on a SQLite backup, never the user's original save."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from unittest.mock import patch

if __package__ in (None, ""):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from tools.audit_settlement_layouts import inspect_skeleton
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.canonical import canonical_hash
from worldseed.persistence.database import WorldDatabase
from worldseed.systems.settlement_access import prepare_access_repairs
from worldseed.systems.settlement_planner import SettlementSkeleton
from worldseed.world.generator import WorldGenerator
from worldseed.world.hydrology import HydrologyGenerator
from worldseed.world.world import World


def audit_copy(source, target, settlement_id=None):
    source=Path(source).resolve();target=Path(target).resolve()
    if source==target:raise ValueError("Audit copy must not be the original save")
    if target.exists():raise ValueError("Audit copy target already exists")
    target.parent.mkdir(parents=True,exist_ok=True)
    original=sqlite3.connect(source.as_uri()+"?mode=ro",uri=True)
    copied=sqlite3.connect(target)
    try:original.backup(copied)
    finally:copied.close();original.close()
    db=WorldDatabase.open(target)
    try:
        registry=ContentRegistry.load(DATA_DIR)
        generator=WorldGenerator(bytes.fromhex(db.get_meta("world_seed")),registry,version=int(db.get_meta("worldgen_version")))
        world=World(generator,registry,db)
        plans=db.connection.execute("SELECT settlement_uid,plan_version FROM generated_settlement_plans ORDER BY settlement_uid,plan_version").fetchall()
        cases=[]
        with patch.object(HydrologyGenerator,"generate",side_effect=AssertionError("Audit must not generate drainage")):
            for row in plans:
                if settlement_id and row["settlement_uid"]!=settlement_id:continue
                if len(cases)>=25:break
                base=SettlementSkeleton.from_dict(db.load_generated_settlement_plan(row["settlement_uid"],row["plan_version"]))
                before=canonical_hash(base.to_dict())
                repaired=prepare_access_repairs(base,world,registry)
                remaining=[]
                for s in repaired.structures:
                    if s.enclosed and not s.destroyed and s.entrance is not None:
                        x,y=s.entrance
                        if (x,y+1) in set(map(tuple,s.footprint)):remaining.append(s.uid)
                delta=db.load_physical_plan_delta(base.plan.uid)
                cases.append({"settlement_id":row["settlement_uid"],"version":row["plan_version"],
                    "entrances_moved":len(delta["payload"]["entrances"]) if delta and delta["plan_kind"]=="settlement_access" else 0,
                    "wall_aprons":len(delta["payload"].get("footprints",{})) if delta and delta["plan_kind"]=="settlement_access" else 0,
                    "before_road_cells":sum(len(r.polyline) for r in base.roads),
                    "after_road_cells":sum(len(r.polyline) for r in repaired.roads),
                    "remaining_non_south_doors":remaining,
                    "base_cache_unchanged":before==canonical_hash(SettlementSkeleton.from_dict(db.load_generated_settlement_plan(row["settlement_uid"],row["plan_version"])).to_dict()),
                    "failures":inspect_skeleton(world,registry,repaired)})
        errors=db.verify()
        return {"mode":"copied-playtest-save","original_opened_read_only":True,"copy":str(target),"cases":cases,
                "save_verifier":errors,"ok":bool(cases) and not errors and all(not c["failures"] and not c["remaining_non_south_doors"] and c["base_cache_unchanged"] for c in cases)}
    finally:db.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("save",type=Path)
    parser.add_argument("--copy-path",type=Path)
    parser.add_argument("--settlement")
    args=parser.parse_args()
    if args.copy_path:result=audit_copy(args.save,args.copy_path,args.settlement)
    else:
        with tempfile.TemporaryDirectory(prefix="worldseed-access-audit-") as directory:
            result=audit_copy(args.save,Path(directory)/"audit.db",args.settlement)
    print(json.dumps(result,sort_keys=True))
    return 0 if result["ok"] else 1


if __name__=="__main__":raise SystemExit(main())
