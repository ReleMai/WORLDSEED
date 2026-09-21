#!/usr/bin/env python3
"""Audit WORLDGEN v8 physical climate, rain shadows and dynamic weather."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.systems.environment import WeatherSystem
from worldseed.world.generator import WorldGenerator

DEFAULT_SEEDS = tuple(f"v8-climate-{i:02d}" for i in range(6))


def summarize(values):
    values = sorted(int(v) for v in values)
    if not values:
        return {"min":0,"mean":0,"p95":0,"max":0}
    return {
        "min":values[0],
        "mean":sum(values)//len(values),
        "p95":values[min(len(values)-1,len(values)*95//100)],
        "max":values[-1],
    }


def audit_seed(registry, seed_text: str, radius: int, spacing: int) -> dict:
    seed = seed_text.encode("utf-8")
    gen = WorldGenerator(seed, registry, version=8)
    temps=[];rainfall=[];maritime=[];lift=[];shadow=[];humidity=[]
    wet_side=[];dry_side=[]
    for y in range(-radius,radius+1,spacing):
        for x in range(-radius,radius+1,spacing):
            row=gen.climate_at(WorldPos(x,y,0))
            temps.append(row.mean_temperature)
            rainfall.append(row.precipitation_potential)
            maritime.append(row.maritime_influence)
            lift.append(row.orographic_lift)
            shadow.append(row.rain_shadow)
            humidity.append(row.humidity)
            if row.orographic_lift>=12000:wet_side.append(row.precipitation_potential)
            if row.rain_shadow>=12000:dry_side.append(row.precipitation_potential)

    weather=WeatherSystem(seed,gen)
    kinds={}
    wetness=[]
    rain_samples=[]
    for minute in range(0,7*1440,120):
        w=weather.at(minute,0,0)
        kinds[w["kind"]]=kinds.get(w["kind"],0)+1
        wetness.append(w["wetness"])
        rain_samples.append(w["rain"])

    return {
        "seed":seed_text,
        "temperature":summarize(temps),
        "precipitation":summarize(rainfall),
        "humidity":summarize(humidity),
        "maritime":summarize(maritime),
        "orographic_lift":summarize(lift),
        "rain_shadow":summarize(shadow),
        "mean_precip_high_lift":sum(wet_side)//max(1,len(wet_side)),
        "mean_precip_high_shadow":sum(dry_side)//max(1,len(dry_side)),
        "weather_kinds":dict(sorted(kinds.items())),
        "weather_wetness":summarize(wetness),
        "weather_rain":summarize(rain_samples),
    }


def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--seed",action="append",dest="seeds")
    ap.add_argument("--radius",type=int,default=8192)
    ap.add_argument("--spacing",type=int,default=256)
    ap.add_argument("--out",type=Path,default=Path("v8_climate_audit.json"))
    args=ap.parse_args()
    registry=ContentRegistry.load(DATA_DIR)
    rows=[audit_seed(registry,s,max(2048,args.radius),max(64,args.spacing)) for s in tuple(args.seeds or DEFAULT_SEEDS)]
    payload={"worldgen_version":8,"results":rows}
    args.out.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    for row in rows:
        print(
            f"{row['seed']}: precip={row['precipitation']['mean']} "
            f"lift={row['orographic_lift']['p95']} shadow={row['rain_shadow']['p95']} "
            f"weather={row['weather_kinds']}"
        )
    print(f"wrote {args.out}")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
