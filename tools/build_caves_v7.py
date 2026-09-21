"""Build deterministic authored-style cave/ore textures for WORLDSEED v7."""
from __future__ import annotations
from pathlib import Path
import math, random
from PIL import Image, ImageDraw, ImageFilter

ROOT=Path(__file__).resolve().parents[1]
TERR=ROOT/'worldseed/assets/sprites/terrain'
ITEM=ROOT/'worldseed/assets/sprites/items'
TERR.mkdir(parents=True,exist_ok=True);ITEM.mkdir(parents=True,exist_ok=True)
SIZE=96

def _noise(seed, base, spread, n=180):
    rnd=random.Random(seed);im=Image.new('RGB',(SIZE,SIZE),base);px=im.load()
    for y in range(SIZE):
        for x in range(SIZE):
            v=rnd.randint(-spread,spread)
            px[x,y]=tuple(max(0,min(255,c+v)) for c in base)
    return im.filter(ImageFilter.GaussianBlur(.35))

def cave_mouth(seed:int)->Image.Image:
    rnd=random.Random(seed)
    # Cave mouths are transparent contextual overlays. The renderer lays this
    # rocky opening over the most representative neighboring ground texture,
    # so a grassland cave does not arrive with a square gray floor and a desert
    # cave does not carry a grass-colored baked background.
    im=Image.new('RGBA',(SIZE,SIZE),(0,0,0,0))
    d=ImageDraw.Draw(im,'RGBA')
    # irregular recessed opening, viewed top-down with a rocky overhang lip
    cx=48+rnd.randint(-4,4);cy=53+rnd.randint(-3,3);rx=27+rnd.randint(-3,3);ry=22+rnd.randint(-3,3)
    # broken talus ring; partial alpha lets the local biome texture show through
    for _ in range(34):
        a=rnd.uniform(0,math.tau);dist=rnd.uniform(rx*.82,rx+12)
        x=cx+math.cos(a)*dist;y=cy+math.sin(a)*dist*.78;r=rnd.randint(2,7)
        c=rnd.choice([(122,117,101,190),(72,75,70,210),(145,129,98,155),(94,94,84,205)])
        d.ellipse((x-r,y-r,x+r,y+r),fill=c)
    pts=[]
    for i in range(32):
        a=math.tau*i/32
        wobble=1+rnd.uniform(-.12,.12)
        pts.append((cx+math.cos(a)*rx*wobble,cy+math.sin(a)*ry*wobble))
    d.polygon(pts,fill=(8,10,10,255))
    # Keep the cavity visually deep without artificial contour rings. A soft
    # off-center darkness and a tiny reflected rim are enough at gameplay size.
    d.ellipse((cx-rx*.62,cy-ry*.48,cx+rx*.48,cy+ry*.58),fill=(2,4,4,255))
    d.arc((cx-rx*.72,cy-ry*.68,cx+rx*.72,cy+ry*.66),198,332,fill=(38,42,39,150),width=2)
    # thick upper stone lip / exposed cliff face
    lip=[]
    for i in range(18):
        a=math.pi+math.pi*i/17
        wobble=1+rnd.uniform(-.09,.09)
        lip.append((cx+math.cos(a)*(rx+7)*wobble,cy+math.sin(a)*(ry+7)*wobble))
    for i in range(17,-1,-1):
        a=math.pi+math.pi*i/17
        lip.append((cx+math.cos(a)*(rx-2),cy+math.sin(a)*(ry-2)))
    d.polygon(lip,fill=(56,58,53,235))
    for _ in range(20):
        x=cx+rnd.randint(-rx,rx);y=cy-rnd.randint(ry//2,ry+8);r=rnd.randint(1,4)
        d.ellipse((x-r,y-r,x+r,y+r),fill=rnd.choice([(126,119,93,130),(91,93,82,170),(46,49,45,180)]))
    # vegetation fringe, restrained
    for _ in range(18):
        a=rnd.uniform(0,math.tau);dist=rnd.uniform(rx+6,rx+16)
        x=cx+math.cos(a)*dist;y=cy+math.sin(a)*dist*.8
        d.line((x,y,x+rnd.uniform(-3,3),y-rnd.uniform(3,8)),fill=(74,93,49,125),width=1)
    return im

def rock_tile(seed:int,kind:str)->Image.Image:
    palette={
        'wall':((66,68,64),(116,113,101)),
        'iron':((65,65,61),(150,89,67)),
        'coal':((51,52,49),(26,27,25)),
        'aquifer':((61,67,66),(63,126,151)),
        'copper':((70,69,61),(84,139,101)),
    }
    base,accent=palette[kind];rnd=random.Random(13000+seed*17+len(kind));im=_noise(12000+seed,base,11);d=ImageDraw.Draw(im,'RGBA')
    # fractured rock polygons
    for _ in range(34):
        x=rnd.randint(-5,95);y=rnd.randint(-5,95);r=rnd.randint(3,12)
        pts=[]
        for i in range(rnd.randint(5,8)):
            a=math.tau*i/rnd.randint(5,8);rr=r*rnd.uniform(.6,1.25);pts.append((x+math.cos(a)*rr,y+math.sin(a)*rr))
        d.line(pts+[pts[0]],fill=(25,28,27,80),width=1)
    if kind!='wall':
        # coherent vein/seam rather than dots
        y=rnd.randint(18,78);points=[]
        for x in range(-8,105,8):
            y+=rnd.randint(-5,5);points.append((x,y))
        width=7 if kind=='coal' else 4
        d.line(points,fill=(*accent,185),width=width)
        d.line(points,fill=(*tuple(min(255,c+35) for c in accent),130),width=max(1,width//3))
        if kind in {'aquifer','copper'}:
            for x,y in points[1:-1:2]:
                r=rnd.randint(2,5);d.ellipse((x-r,y-r,x+r,y+r),fill=(*accent,110))
    return im

def item_icon(seed:int,kind:str)->Image.Image:
    rnd=random.Random(seed);im=Image.new('RGBA',(96,96),(0,0,0,0));d=ImageDraw.Draw(im,'RGBA')
    if kind=='ore':
        pts=[(19,59),(29,32),(53,22),(77,36),(80,61),(61,77),(34,73)]
        d.polygon(pts,fill=(76,73,64,255),outline=(35,37,34,255))
        for _ in range(16):
            x=rnd.randint(28,71);y=rnd.randint(31,68);r=rnd.randint(2,5)
            d.ellipse((x-r,y-r,x+r,y+r),fill=rnd.choice([(71,137,91,235),(116,92,58,220),(53,105,76,230)]))
    else:
        d.rounded_rectangle((19,36,77,66),8,fill=(174,93,50,255),outline=(91,48,29,255),width=3)
        d.polygon([(23,38),(73,38),(66,30),(31,30)],fill=(205,124,72,245))
        d.line((29,51,68,51),fill=(230,148,92,150),width=2)
    return im

def main():
    mouth=[]
    for i in range(8):
        p=TERR/f'v7_cave_mouth_{i:02d}.png';cave_mouth(i).save(p);mouth.append(p)
    groups={}
    for kind,prefix in [('wall','v7_cave_wall'),('iron','v7_iron_vein'),('coal','v7_coal_seam'),('aquifer','v7_aquifer'),('copper','v7_copper_vein')]:
        groups[kind]=[]
        for i in range(6):
            p=TERR/f'{prefix}_{i:02d}.png';rock_tile(i,kind).save(p);groups[kind].append(p)
    item_icon(1,'ore').save(ITEM/'copper_ore.png')
    item_icon(2,'ingot').save(ITEM/'copper_ingot.png')
    print('built',len(mouth)+sum(map(len,groups.values()))+2,'cave v7 assets')

if __name__=='__main__':main()
