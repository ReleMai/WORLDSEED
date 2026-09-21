from __future__ import annotations
from pathlib import Path
import argparse
import sqlite3
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from worldseed.persistence.database import WorldDatabase


def main()->int:
    ap=argparse.ArgumentParser(description='Inspect rotating WORLDSEED backups and optionally restore one.')
    ap.add_argument('save',type=Path);ap.add_argument('--restore',type=int,choices=(1,2,3));a=ap.parse_args();save=a.save;backup_dir=save.parent/'backups';candidates=[]
    for i in (1,2,3):
        p=backup_dir/f'{save.stem}.bak{i}.db'
        if p.exists():
            con=sqlite3.connect(p)
            try:row=con.execute('PRAGMA integrity_check').fetchone();ok=bool(row and row[0]=='ok')
            finally:con.close()
            candidates.append((i,p,ok))
            print(f'backup {i}: {p} integrity={"ok" if ok else "FAILED"}')
    if a.restore:
        match=next((p for i,p,ok in candidates if i==a.restore and ok),None)
        if not match:print('Requested backup is unavailable or invalid.');return 2
        WorldDatabase.restore_backup(match,save);print(f'Restored {match} -> {save}')
    return 0

if __name__=='__main__':raise SystemExit(main())
