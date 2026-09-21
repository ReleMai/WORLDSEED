from __future__ import annotations
from pathlib import Path
import argparse,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from worldseed.persistence.database import WorldDatabase


def main()->int:
    ap=argparse.ArgumentParser();ap.add_argument('save',type=Path);a=ap.parse_args();db=WorldDatabase.open(a.save);state=db.load_sim_state() or {};db.close();rows=[]
    for key,value in state.items():
        if isinstance(value,dict):count=len(value)
        elif isinstance(value,list):count=len(value)
        else:continue
        size=len(json.dumps(value,separators=(',',':'),sort_keys=True).encode())
        rows.append((size,key,count))
    for size,key,count in sorted(rows,reverse=True):print(f'{key:<28} {count:>8} records  {size/1024:>10.1f} KiB')
    return 0
if __name__=='__main__':raise SystemExit(main())
