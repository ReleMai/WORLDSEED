from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.world.generator import WorldGenerator
from worldseed.world.hydrology import HydrologyGenerator, audit_window_seams

PALETTE={
    'core:grass':(92,128,68),'core:forest':(48,92,56),'core:scrub':(124,112,68),
    'core:tundra':(146,158,151),'core:rock':(110,108,103),'core:sand':(176,158,105),
    'core:water':(39,83,132),'core:river':(38,92,155),'core:river_shallow':(65,126,174),
    'core:wetland':(66,109,83),'core:floodplain':(112,143,78),'core:cave_mouth':(70,67,62),
}

def _chunk(kind:bytes,payload:bytes)->bytes:
    return struct.pack('>I',len(payload))+kind+payload+struct.pack('>I',zlib.crc32(kind+payload)&0xffffffff)

def write_png(path:Path,w:int,h:int,rgb:bytes)->None:
    scan=b''.join(b'\x00'+rgb[y*w*3:(y+1)*w*3] for y in range(h))
    out=b'\x89PNG\r\n\x1a\n'+_chunk(b'IHDR',struct.pack('>IIBBBBB',w,h,8,2,0,0,0))+_chunk(b'IDAT',zlib.compress(scan,9))+_chunk(b'IEND',b'')
    path.write_bytes(out)

def main()->int:
    ap=argparse.ArgumentParser(description='Audit RC14 Phase-3 v5 physical hydrology projection.')
    ap.add_argument('--seed',default='rc14-golden-00')
    ap.add_argument('--radius',type=int,default=256)
    ap.add_argument('--out-dir',type=Path,default=Path('artifacts/phase3'))
    args=ap.parse_args()
    reg=ContentRegistry.load(DATA_DIR);gen=WorldGenerator(args.seed.encode(),reg,version=5);hydro=HydrologyGenerator(gen)
    r=max(64,args.radius);min_dx,max_dx,min_dy,max_dy=hydro.domains_for_world_bounds(-r,-r,r-1,r-1)
    domains=hydro.prepare_window(min_dx,max_dx,min_dy,max_dy,persist=False);gen.attach_hydrology(hydro)
    seam_issues=audit_window_seams(domains)
    counts={};crossing={};rgb=bytearray();w=h=r*2
    for y in range(-r,r):
        for x in range(-r,r):
            p=WorldPos(x,y,0);tid=gen.terrain_at(p);counts[tid]=counts.get(tid,0)+1
            hs=hydro.surface_at(p)
            if hs.crossing_cost:crossing[str(hs.crossing_cost)]=crossing.get(str(hs.crossing_cost),0)+1
            rgb.extend(PALETTE.get(tid,(90,95,84)))
    args.out_dir.mkdir(parents=True,exist_ok=True);png=args.out_dir/f'{args.seed}_v5.png';write_png(png,w,h,bytes(rgb))
    physical=sum(counts.get(k,0) for k in ('core:river','core:river_shallow','core:wetland','core:floodplain'))
    report={'seed':args.seed,'window_domains':[[d.domain_x,d.domain_y] for d in domains], 'seam_issues':seam_issues,
            'cells':w*h,'terrain_counts':dict(sorted(counts.items())),'physical_hydrology_cells':physical,
            'physical_hydrology_fraction':physical/(w*h),'crossing_cost_counts':crossing,'png':str(png)}
    out=args.out_dir/f'{args.seed}_v5.json';out.write_text(json.dumps(report,indent=2,sort_keys=True),encoding='utf-8')
    print(json.dumps(report,indent=2,sort_keys=True))
    bad=bool(seam_issues) or not counts.get('core:river_shallow',0) or physical/(w*h)>.45
    return 1 if bad else 0

if __name__=='__main__':raise SystemExit(main())
