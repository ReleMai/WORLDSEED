from __future__ import annotations
import json, math
from pathlib import Path
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
AS=ROOT/'worldseed'/'assets'
SP=AS/'sprites'
OUT=AS/'atlases'; OUT.mkdir(parents=True,exist_ok=True)
CELL=64

def build(name, entries):
    entries=list(entries); cols=16; rows=max(1,math.ceil(len(entries)/cols))
    sheet=Image.new('RGBA',(cols*CELL,rows*CELL),(0,0,0,0)); idx={}
    for i,(key,path) in enumerate(entries):
        im=Image.open(path).convert('RGBA'); im.thumbnail((60,60),Image.Resampling.NEAREST)
        cx=(i%cols)*CELL; cy=(i//cols)*CELL
        x=cx+(CELL-im.width)//2; y=cy+(CELL-im.height)//2
        sheet.alpha_composite(im,(x,y)); idx[key]={'cell':[i%cols,i//cols],'rect':[cx,cy,CELL,CELL]}
    p=OUT/f'{name}.png'; sheet.save(p,optimize=True); return idx

manifest=json.loads((AS/'visuals.json').read_text())
index={'cell_px':CELL,'atlases':{}}
for kind in ['items','terrain','resources','structures','crops']:
    entries=[]
    for cid,raw in manifest[kind].items():
        if isinstance(raw,list):
            for n,path in enumerate(raw): entries.append((f'{cid}#{n}',ROOT/'worldseed'/path))
        else:
            entries.append((cid,ROOT/'worldseed'/raw))
    index['atlases'][kind]={'image':f'assets/atlases/{kind}.png','entries':build(kind,entries)}
sp=[]
for cid,paths in manifest['species'].items():
    for n,path in enumerate(paths): sp.append((f'{cid}#{n}',ROOT/'worldseed'/path))
index['atlases']['species']={'image':'assets/atlases/species.png','entries':build('species',sp)}
npc=[(f'npc#{n}',ROOT/'worldseed'/p) for n,p in enumerate(manifest['npc_variants'])]
index['atlases']['npc']={'image':'assets/atlases/npc.png','entries':build('npc',npc)}
(AS/'atlas_index.json').write_text(json.dumps(index,indent=2),encoding='utf-8')
print('built atlases:', ', '.join(index['atlases']))
