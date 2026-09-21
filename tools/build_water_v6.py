"""Deterministic native water materials: smooth fields, restrained caustics.

Rebuilds Dev15 assets without external services. This extends the existing
code-authored terrain system; no random image processing or runtime noise.
"""
from pathlib import Path
import math,json
from PIL import Image, ImageDraw
ROOT=Path(__file__).resolve().parents[1]
STYLES={
'ocean_wade':((113,173,163),12),'ocean_shallow':((48,139,149),7),
'ocean_shelf':((27,100,127),3),'ocean_deep':((16,58,88),2),
'estuary_mix':((104,142,127),8),'estuary_deep':((53,103,103),4),
'freshwater_shallow':((104,151,142),10),'freshwater_deep':((37,92,110),3),
'stream':((131,161,144),12),'rapids':((68,123,133),7),
'shore':((158,149,114),3),'riverbank':((158,146,117),4)}
def material(key,variant,size=128):
 base,caustics=STYLES[key];im=Image.new('RGB',(size,size));px=im.load()
 for y in range(size):
  for x in range(size):
   u=x/(size-1)*math.tau;v=y/(size-1)*math.tau
   # All fields are periodic. Very small variant changes prevent patchwork.
   f=2.2*math.sin(u+0.35*math.sin(v))+1.6*math.cos(v*2+0.25*math.sin(u))
   f+=0.6*math.sin(5*u+math.sin(3*v))
   phase=variant*0.04
   c=max(0,math.cos(3*u+math.sin(2*v)+phase)*math.cos(2*v+math.sin(u)))**12*caustics
   if key in ('shore','riverbank'):
    c=(math.sin(39*u+17*v)*math.sin(31*v-11*u))*4
   px[x,y]=tuple(max(0,min(255,round(t+f+c))) for t in base)
 return im

def main():
 path=ROOT/'worldseed/assets/visuals.json';manifest=json.loads(path.read_text());out=ROOT/'worldseed/assets/sprites/terrain'
 for key in STYLES:
  paths=[]
  for v in range(10):
   name=f'v6_{key}_{v:02}.png';material(key,v).save(out/name);paths.append('assets/sprites/terrain/'+name)
  manifest['terrain'][('core:' if key in ('shore','riverbank') else 'render:')+key]=paths
 from worldseed.presentation.local_terrain import PHYSICAL_WATER_DISPLAY
 for key,value in PHYSICAL_WATER_DISPLAY.items():manifest['terrain'][key]=manifest['terrain'][value]
 # Legacy rivers adopt the cleaner materials without changing their geography.
 manifest['terrain']['core:river']=manifest['terrain']['render:freshwater_deep']
 manifest['terrain']['core:river_shallow']=manifest['terrain']['render:freshwater_shallow']
 path.write_text(json.dumps(manifest,indent=2)+'\n')
if __name__=='__main__':main()
