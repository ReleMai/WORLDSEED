from __future__ import annotations

import json, math, random, re
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'worldseed' / 'data'
OUT = ROOT / 'worldseed' / 'assets' / 'sprites'
MANIFEST = ROOT / 'worldseed' / 'assets' / 'visuals.json'

S=32
TRAN=(0,0,0,0)

def sid(cid:str)->str: return cid.split(':',1)[-1]
def seed_for(text:str)->int:
    h=2166136261
    for ch in text.encode('utf-8'):
        h ^= ch; h=(h*16777619)&0xffffffff
    return h

def img(size=(S,S), bg=TRAN): return Image.new('RGBA', size, bg)
def px(draw, xy, fill): draw.rectangle(xy, fill=fill)
def line(draw, pts, fill, width=2): draw.line(pts, fill=fill, width=width)
def poly(draw, pts, fill, outline=None): draw.polygon(pts, fill=fill, outline=outline)
def ellipse(draw, xy, fill, outline=None): draw.ellipse(xy, fill=fill, outline=outline)
def noise(draw, rng, box, colors, count, size=1):
    x0,y0,x1,y1=box
    for _ in range(count):
        x=rng.randint(x0,x1); y=rng.randint(y0,y1); c=rng.choice(colors)
        draw.rectangle((x,y,x+size,y+size),fill=c)

def save(im:Image.Image, path:Path): path.parent.mkdir(parents=True,exist_ok=True); im.save(path,optimize=True)

def draw_shadow(d,cx=16,cy=27,rx=10,ry=3): ellipse(d,(cx-rx,cy-ry,cx+rx,cy+ry),(0,0,0,70))

def item_sprite(it):
    name=it['name'].lower(); cat=it.get('category','misc'); tags=set(it.get('tags',[])); rng=random.Random(seed_for(it['id']))
    im=img(); d=ImageDraw.Draw(im); draw_shadow(d)
    # palette
    wood=(111,72,42,255); wood2=(157,106,61,255); stone=(111,116,118,255); stone2=(169,172,164,255)
    iron=(92,101,108,255); steel=(157,170,177,255); leather=(125,75,43,255); bone=(221,212,174,255)
    green=(63,119,61,255); red=(148,52,45,255); gold=(181,137,42,255)
    if 'axe' in name:
        line(d,[(12,28),(19,7)],wood2,4); poly(d,[(16,8),(26,5),(27,12),(20,15)],stone2,(70,74,76,255)); line(d,[(18,8),(24,7)],(225,225,216,255),1)
    elif 'pick' in name:
        line(d,[(15,29),(18,9)],wood2,4); poly(d,[(5,10),(18,6),(29,10),(27,13),(18,10),(7,14)],steel if 'steel' in name else iron,(48,54,59,255))
    elif 'hammer' in name:
        line(d,[(15,29),(17,12)],wood2,4); px(d,(8,7,25,14),stone2); px(d,(9,8,24,10),(190,191,181,255))
    elif 'knife' in name or 'flake' in name:
        poly(d,[(7,24),(17,7),(27,5),(22,15),(13,26)],stone2,(66,70,70,255)); line(d,[(8,25),(14,21)],wood2,4)
    elif 'sword' in name:
        line(d,[(9,28),(23,6)],steel if 'steel' in name else iron,4); line(d,[(13,20),(22,25)],gold,3); line(d,[(8,29),(13,22)],wood,4)
    elif 'spear' in name:
        line(d,[(7,28),(24,8)],wood2,3); poly(d,[(23,10),(29,3),(27,13)],stone2,(70,70,70,255))
    elif 'bow' in name:
        d.arc((5,3,27,30),270,90,fill=wood2,width=3); line(d,[(17,5),(17,28)],(211,198,160,255),1); line(d,[(16,16),(27,16)],stone2,2); poly(d,[(27,16),(23,13),(23,19)],stone2)
    elif 'sling' in name:
        d.arc((5,5,25,24),205,335,fill=(170,142,90,255),width=2); line(d,[(8,19),(4,28)],(170,142,90,255),2); line(d,[(22,19),(28,28)],(170,142,90,255),2); ellipse(d,(12,12,19,18),leather)
    elif 'arrow' in name:
        line(d,[(5,26),(26,6)],wood2,2); poly(d,[(26,6),(21,7),(25,11)],stone2); poly(d,[(7,24),(5,18),(10,22)],(198,185,142,255))
    elif 'stone' in name or it['id'].endswith('stone'):
        poly(d,[(7,22),(10,12),(18,8),(26,13),(24,24),(16,27)],stone,(54,58,60,255)); noise(d,rng,(11,12,23,23),[(145,149,148,255),(84,88,90,255)],8,1)
    elif 'log' in name or 'branch' in name or 'club' in name or 'digging stick' in name:
        line(d,[(7,27),(25,7)],wood2,6); line(d,[(9,25),(23,8)],(91,56,35,255),1); line(d,[(19,13),(27,12)],wood,3)
    elif 'hide' in name or 'leather' in name or 'rawhide' in name:
        poly(d,[(7,8),(13,10),(16,5),(20,10),(27,8),(25,16),(28,23),(20,25),(16,29),(12,25),(5,23),(8,16)], leather if 'leather' in name else (158,110,71,255),(83,52,35,255)); noise(d,rng,(10,11,23,22),[(187,139,91,255),(113,73,47,255)],10)
    elif 'bone' in name or 'awl' in name or 'needle' in name:
        line(d,[(9,25),(23,8)],bone,4); ellipse(d,(5,21,12,28),bone); ellipse(d,(20,4,27,11),bone)
    elif 'cord' in name or 'fiber' in name or 'sinew' in name:
        d.arc((6,6,27,27),10,330,fill=(183,157,105,255),width=3); d.arc((10,10,23,23),0,300,fill=(129,101,65,255),width=2)
    elif 'coin' in name:
        ellipse(d,(7,7,25,25),(174,101,49,255),(94,51,28,255)); ellipse(d,(10,10,22,22),(202,130,68,255)); line(d,[(13,16),(20,16)],(111,66,34,255),2)
    elif 'book' in name:
        px(d,(6,7,25,26),(102,49,37,255)); px(d,(9,8,24,25),(211,198,154,255)); line(d,[(15,8),(15,25)],(126,94,66,255),1); line(d,[(11,12),(14,12)],(75,63,50,255),1); line(d,[(17,12),(22,12)],(75,63,50,255),1)
    elif 'waterskin' in name:
        poly(d,[(12,6),(20,6),(23,12),(25,25),(17,29),(8,24),(10,12)],leather,(72,43,29,255)); line(d,[(13,6),(19,6)],(196,157,92,255),2)
    elif 'pot' in name or 'bowl' in name:
        poly(d,[(7,13),(25,13),(22,25),(10,25)],(148,79,49,255) if 'clay' in name else wood2,(78,47,33,255)); d.arc((8,9,24,17),0,180,fill=(217,161,103,255),width=2)
    elif 'helmet' in name or 'hood' in name:
        d.pieslice((7,6,25,26),180,360,fill=steel if 'steel' in name else (iron if 'iron' in name else leather),outline=(55,55,55,255)); px(d,(7,15,25,21),steel if 'steel' in name else (iron if 'iron' in name else leather)); px(d,(12,17,20,22),(0,0,0,0))
    elif 'vest' in name or 'bracers' in name or 'leggings' in name or 'buckler' in name:
        if 'buckler' in name:
            ellipse(d,(6,6,26,26),leather,(62,39,25,255)); ellipse(d,(12,12,20,20),iron); line(d,[(9,10),(23,23)],(97,60,35,255),2)
        else:
            poly(d,[(10,7),(22,7),(26,13),(22,27),(10,27),(6,13)],leather,(70,43,29,255)); line(d,[(16,8),(16,26)],(89,51,31,255),1)
    elif cat in {'seed'} or 'seed' in name:
        poly(d,[(8,10),(24,10),(26,25),(16,29),(6,25)],(153,120,72,255),(83,61,39,255)); line(d,[(10,11),(22,11)],(220,192,123,255),2); noise(d,rng,(10,15,22,24),[(211,177,92,255),(124,95,45,255)],10)
    elif cat in {'food','herb'} or 'food' in tags:
        if any(w in name for w in ['berry','berries','rasp','strawber']):
            for i in range(8):
                x=rng.randint(8,23); y=rng.randint(10,24); ellipse(d,(x-2,y-2,x+2,y+2),rng.choice([(64,69,126,255),(143,39,58,255),(189,47,74,255)]))
            line(d,[(16,10),(18,5)],green,2)
        elif any(w in name for w in ['meat','offal','poultry','fat']):
            poly(d,[(7,18),(10,10),(20,8),(27,15),(24,24),(14,27)],(160,65,59,255) if 'fat' not in name else (225,202,144,255),(91,43,39,255)); noise(d,rng,(11,12,23,22),[(196,89,79,255),(118,49,45,255)],7)
        elif 'mushroom' in name or 'morel' in name or 'bolete' in name:
            line(d,[(16,25),(16,14)],(219,204,164,255),4); d.pieslice((7,7,25,19),180,360,fill=(147,92,58,255)); noise(d,rng,(9,8,23,13),[(188,128,76,255),(100,62,44,255)],8)
        elif any(w in name for w in ['carrot','onion','turnip','cattail']):
            poly(d,[(13,12),(21,12),(19,27),(15,28)],(201,111,46,255) if 'carrot' in name else (202,186,139,255),(90,75,51,255)); line(d,[(17,12),(12,5)],green,2); line(d,[(17,12),(22,5)],green,2)
        else:
            for i in range(5): line(d,[(16,25),(rng.randint(8,24),rng.randint(6,18))],green,3)
            ellipse(d,(11,9,20,18),(91,151,71,255))
    elif 'ore' in name or 'bloom' in name or 'billet' in name or 'coal' in name:
        poly(d,[(7,22),(9,11),(18,7),(27,14),(23,26),(13,27)],(65,65,69,255) if 'coal' in name else iron,(40,42,44,255)); noise(d,rng,(10,10,24,23),[(196,113,64,255),(139,64,44,255)] if 'ore' in name else [(196,205,210,255),(100,109,114,255)],10)
    elif 'relic' in name or 'key' in name:
        ellipse(d,(7,8,17,18),gold,(90,67,24,255)); line(d,[(15,16),(26,27)],gold,4); line(d,[(22,23),(26,20)],gold,2); line(d,[(24,25),(28,22)],gold,2)
    elif 'bandage' in name or 'soap' in name or 'tonic' in name or 'water' in name:
        if 'bandage' in name:
            px(d,(7,11,25,23),(224,219,196,255)); line(d,[(8,14),(24,20)],(183,174,151,255),2)
        elif 'soap' in name:
            px(d,(8,10,24,24),(213,206,160,255)); ellipse(d,(11,8,17,13),(237,244,239,180)); ellipse(d,(17,6,23,12),(237,244,239,180))
        else:
            px(d,(11,8,21,26),(84,133,147,255)); px(d,(13,5,19,9),(92,75,53,255)); px(d,(13,13,19,22),(94,169,179,180))
    else:
        # deterministic object bundle fallback, still visually non-empty
        poly(d,[(8,24),(10,10),(16,6),(24,11),(26,23),(17,28)],rng.choice([wood2,stone2,leather,green]),(62,62,62,255)); noise(d,rng,(11,10,23,23),[(230,210,160,255),(82,65,54,255)],6)
    return im

def terrain_sprite(t):
    rng=random.Random(seed_for(t['id'])); im=img((32,32),(34,45,33,255)); d=ImageDraw.Draw(im); name=t['name'].lower(); tid=t['id']
    if 'water' in name:
        d.rectangle((0,0,31,31),fill=(40,86,117,255));
        for y in range(4,32,7):
            off=rng.randint(-3,3); line(d,[(2+off,y),(11+off,y),(15+off,y-1)],(86,139,164,255),1)
    elif 'sand' in name:
        d.rectangle((0,0,31,31),fill=(178,157,105,255)); noise(d,rng,(0,0,31,31),[(151,130,83,255),(207,187,128,255)],35)
    elif 'tundra' in name:
        d.rectangle((0,0,31,31),fill=(108,118,101,255)); noise(d,rng,(0,0,31,31),[(157,164,146,255),(80,92,79,255)],30)
    elif 'grass' in name or 'forest' in name or 'thicket' in name or 'scrub' in name:
        base=(62,102,52,255) if 'grass' in name else ((45,72,43,255) if 'forest' in name else (83,83,48,255))
        d.rectangle((0,0,31,31),fill=base); noise(d,rng,(0,0,31,31),[(77,121,61,255),(37,78,41,255),(111,101,57,255)],42)
        for _ in range(7):
            x=rng.randrange(2,30); y=rng.randrange(4,31); line(d,[(x,y),(x+rng.choice([-1,0,1]),y-3)],(90,137,67,255),1)
    elif 'rock' in name or 'wall' in name or 'vein' in name or 'seam' in name or 'aquifer' in name:
        base=(71,73,73,255) if 'wall' not in name else (54,57,58,255); d.rectangle((0,0,31,31),fill=base)
        for _ in range(12):
            x=rng.randrange(0,28); y=rng.randrange(0,28); poly(d,[(x,y),(x+4,y-1),(x+6,y+3),(x+2,y+5)],(88,91,92,255),(42,44,45,255))
        if 'iron' in name: noise(d,rng,(0,0,31,31),[(151,71,49,255),(189,99,61,255)],18,1)
        if 'coal' in name: noise(d,rng,(0,0,31,31),[(20,20,22,255),(35,35,38,255)],22,1)
        if 'aquifer' in name: noise(d,rng,(0,0,31,31),[(52,100,124,255),(76,125,145,255)],18,1)
    elif 'cave floor' in name:
        d.rectangle((0,0,31,31),fill=(61,58,53,255)); noise(d,rng,(0,0,31,31),[(77,72,64,255),(43,42,40,255)],30)
    elif 'mouth' in name or 'shaft' in name:
        d.rectangle((0,0,31,31),fill=(73,79,62,255)); ellipse(d,(5,5,27,27),(18,20,20,255),(104,99,79,255)); ellipse(d,(9,9,23,24),(4,6,7,255))
    elif 'tilled' in name:
        d.rectangle((0,0,31,31),fill=(83,60,39,255));
        for x in range(3,32,6): line(d,[(x,0),(x,31)],(109,78,48,255),2)
    elif 'masonry' in name or 'ruin' in name or 'cache' in name:
        d.rectangle((0,0,31,31),fill=(79,75,67,255));
        for y in range(0,32,8):
            line(d,[(0,y),(31,y)],(49,47,43,255),1)
            for x in range((y//8%2)*8,32,16): line(d,[(x,y),(x,y+8)],(49,47,43,255),1)
        if 'cache' in name: px(d,(10,11,22,22),(137,101,48,255)); line(d,[(10,15),(22,15)],(205,157,66,255),2)
    else:
        d.rectangle((0,0,31,31),fill=(75,85,67,255)); noise(d,rng,(0,0,31,31),[(95,105,80,255),(55,65,54,255)],35)
    return im

def resource_sprite(r):
    rng=random.Random(seed_for(r['id'])); im=img((48,56)); d=ImageDraw.Draw(im); name=r['name'].lower(); tags=set(r.get('tags',[])); draw_shadow(d,24,49,13,3)
    if 'tree' in tags:
        trunk=(104,66,41,255); px(d,(20,27,28,50),trunk); line(d,[(24,30),(14,19)],trunk,4); line(d,[(25,32),(35,19)],trunk,4)
        if 'pine' in name:
            for y,w in [(8,12),(15,17),(23,21),(31,23)]: poly(d,[(24,y-8),(24-w,y+7),(24+w,y+7)],(44+rng.randint(-5,5),88+rng.randint(-5,5),52,255),(28,61,37,255))
        else:
            base=(74,116,57,255) if 'willow' not in name else (72,126,72,255)
            for _ in range(18 if 'willow' not in name else 22):
                x=rng.randint(8,39); y=rng.randint(5,30); rr=rng.randint(5,9); ellipse(d,(x-rr,y-rr,x+rr,y+rr),(max(20,base[0]+rng.randint(-16,16)),max(30,base[1]+rng.randint(-18,18)),max(20,base[2]+rng.randint(-12,12)),255))
            if 'birch' in name: px(d,(21,28,27,50),(205,199,170,255)); noise(d,rng,(21,30,27,48),[(65,63,55,255)],8)
            if 'willow' in name:
                for x in [10,15,31,36]: line(d,[(x,18),(x+rng.randint(-2,2),43)],(62,116,66,255),2)
    elif 'bush' in tags or 'food' in tags or 'herb' in tags or 'living' in tags:
        for _ in range(9):
            x=rng.randint(10,38); y=rng.randint(22,44); line(d,[(24,48),(x,y)],(53,102,54,255),2); ellipse(d,(x-4,y-3,x+4,y+3),(74,132,64,255))
        if 'blueberry' in name or 'raspberry' in name or 'strawberry' in name:
            fruit=(62,67,137,255) if 'blue' in name else (174,47,64,255)
            for _ in range(12):
                x=rng.randint(10,39); y=rng.randint(19,42); ellipse(d,(x-2,y-2,x+2,y+2),fruit)
        if 'mushroom' in name or 'morel' in name or 'bolete' in name:
            for i in range(5):
                x=10+i*7+rng.randint(-2,2); line(d,[(x,47),(x,37)],(211,196,156,255),3); d.pieslice((x-5,31,x+5,40),180,360,fill=(142,83,52,255))
        if 'grain' in name or 'cattail' in name or 'reed' in name:
            for i in range(11):
                x=5+i*4+rng.randint(-1,1); h=rng.randint(20,38); line(d,[(x,49),(x,h)],(116,139,68,255),2); 
                if 'cattail' in name: px(d,(x-1,h,x+1,h+8),(102,67,42,255))
                elif 'grain' in name: px(d,(x-1,h-2,x+1,h+5),(181,155,75,255))
    elif 'clay' in tags:
        poly(d,[(8,46),(11,30),(24,24),(39,30),(42,46)],(130,80,57,255),(75,52,42,255)); noise(d,rng,(12,29,38,44),[(160,99,70,255),(101,63,49,255)],18)
    elif 'branch' in tags:
        for i in range(4): line(d,[(9+i*4,45),(35+i*2,24+rng.randint(-3,3))],(120,76,43,255),3)
    elif 'stone' in tags:
        for i in range(6):
            x=8+i*6+rng.randint(-2,2); y=43-rng.randint(0,5); poly(d,[(x-4,y),(x,y-7),(x+5,y-3),(x+4,y+4),(x-3,y+4)],(117,121,119,255),(60,64,64,255))
    else:
        poly(d,[(7,46),(10,29),(23,22),(40,31),(41,46)],(101,101,95,255),(55,55,54,255))
    return im

def structure_sprite(s):
    rng=random.Random(seed_for(s['id'])); im=img((48,48)); d=ImageDraw.Draw(im); name=s['name'].lower(); uses=set(s.get('uses',[])); tags=set(s.get('tags',[])); draw_shadow(d,24,42,15,3)
    wood=(128,81,45,255); wood2=(172,117,66,255); stone=(119,119,112,255); dark=(67,54,43,255)
    if 'wall' in name or 'windbreak' in name:
        mat=stone if 'stone' in name else wood; px(d,(5,12,43,38),mat); 
        for y in range(14,38,8): line(d,[(5,y),(43,y)],dark,1)
        if 'stone' in name:
            for x in range(8,43,10): line(d,[(x,12),(x-4 if (x//10)%2 else x+3,38)],(79,79,75,255),1)
    elif 'floor' in name or 'roof' in name or 'bridge' in name:
        mat=stone if 'stone' in name else wood; px(d,(4,9,44,40),mat); 
        for x in range(7,44,7): line(d,[(x,10),(x,39)],dark,1)
        line(d,[(4,10),(44,10)],(202,149,87,255) if mat==wood else (155,155,147,255),2)
    elif 'door' in name:
        px(d,(11,5,37,43),wood); line(d,[(15,9),(33,9),(33,39),(15,39),(15,9)],(71,47,32,255),2); ellipse(d,(29,23,32,26),(210,172,73,255))
    elif 'fire' in tags or 'campfire' in name or 'hearth' in name:
        for x,y in [(11,36),(18,39),(26,39),(33,36)]: ellipse(d,(x-5,y-3,x+5,y+3),stone,(58,58,56,255))
        line(d,[(15,34),(32,25)],wood,5); line(d,[(33,34),(17,25)],wood,5)
        poly(d,[(24,31),(17,24),(22,13),(27,22),(31,10),(34,27)],(226,112,41,255)); poly(d,[(25,28),(21,23),(25,17),(29,25)],(255,196,61,255))
    elif 'bed' in tags or 'sleep' in uses:
        px(d,(6,11,42,38),wood); px(d,(9,14,39,35),(121,138,92,255) if 'reed' in name else (142,96,73,255)); px(d,(10,14,20,21),(207,194,154,255)); line(d,[(7,38),(7,44)],dark,3); line(d,[(41,38),(41,44)],dark,3)
    elif 'container' in tags or 'storage' in uses:
        if 'basket' in name:
            d.ellipse((8,15,40,38),fill=(159,112,60,255),outline=dark,width=2); 
            for y in range(20,36,5): line(d,[(10,y),(38,y)],(92,61,39,255),1)
        else:
            px(d,(7,15,41,39),wood); px(d,(7,12,41,20),wood2); line(d,[(24,13),(24,39)],dark,2); px(d,(21,23,27,28),(192,151,57,255))
    elif 'rack' in name or 'frame' in name:
        line(d,[(9,42),(14,8)],wood,4); line(d,[(39,42),(34,8)],wood,4); line(d,[(13,12),(35,12)],wood2,4); line(d,[(11,34),(37,34)],wood2,3)
        if 'tanning' in name: poly(d,[(17,15),(31,15),(34,31),(14,31)],(144,95,59,255),(76,49,34,255));
        else:
            for x in [17,24,31]: line(d,[(x,15),(x,31)],(159,74,64,255),3)
    elif 'table' in name or 'work' in name or 'bench' in name:
        px(d,(6,14,42,27),wood2); line(d,[(10,27),(10,43)],dark,4); line(d,[(38,27),(38,43)],dark,4); noise(d,rng,(9,16,39,24),[(98,58,36,255),(198,139,78,255)],12)
    elif 'forge' in name:
        px(d,(7,16,41,40),stone); px(d,(12,20,36,35),(49,42,38,255)); poly(d,[(24,34),(18,27),(23,20),(29,29),(33,22),(35,35)],(223,86,39,255)); px(d,(31,10,37,20),(73,73,70,255))
    elif 'shelter' in tags or 'lean' in name:
        poly(d,[(6,38),(24,7),(43,38)],(113,92,48,255),(69,57,37,255));
        for x in range(10,42,6): line(d,[(24,9),(x,38)],(151,124,68,255),2)
    elif 'support' in tags or 'pillar' in name or 'beam' in name:
        mat=stone if 'stone' in name else wood; px(d,(19,5,29,43),mat); line(d,[(17,7),(31,7)],dark,3); line(d,[(17,41),(31,41)],dark,3)
    else:
        px(d,(8,10,40,40),wood); noise(d,rng,(10,12,38,38),[(184,125,70,255),(86,54,36,255)],12)
    return im

def animal_sprite(sp, variant=0):
    name=sp['name'].lower(); rng=random.Random(seed_for(sp['id'])+variant*977); im=img((56,48)); d=ImageDraw.Draw(im); draw_shadow(d,28,41,16,3)
    palettes={
      'rabbit':[(153,136,110),(188,181,166),(118,103,87),(207,195,172)],
      'hare':[(145,129,103),(199,195,181),(105,98,88),(171,153,119)],
      'deer':[(143,92,55),(174,118,68),(114,79,54),(194,147,92)],
      'elk':[(128,85,52),(151,103,61),(104,75,54),(169,119,71)],
      'moose':[(92,69,52),(112,83,59),(75,61,52),(129,94,62)],
      'boar':[(92,73,62),(112,85,68),(71,62,57),(128,98,74)],
      'turkey':[(72,65,55),(97,78,60),(54,51,48),(116,86,65)],
      'grouse':[(106,87,65),(127,104,74),(82,73,61),(145,115,81)],
      'goat':[(160,158,146),(199,194,174),(126,121,110),(179,166,139)],
      'fox':[(180,82,39),(196,99,47),(155,67,35),(207,119,63)],
      'wolf':[(110,114,112),(143,145,139),(77,84,85),(164,154,137)],
      'bear':[(92,63,44),(114,77,51),(70,52,42),(131,89,56)],
      'badger':[(102,101,94),(126,122,110),(82,84,81),(143,135,118)],
    }
    key=next((k for k in palettes if k in name),'wolf'); base=palettes[key][variant%4]; fur=(*base,255); dark=(max(20,base[0]-45),max(20,base[1]-45),max(20,base[2]-45),255); light=(min(240,base[0]+45),min(240,base[1]+45),min(240,base[2]+45),255)
    if 'turkey' in name or 'grouse' in name:
        ellipse(d,(15,18,39,38),fur,dark); ellipse(d,(33,14,43,24),fur,dark); line(d,[(36,36),(34,43)],dark,2); line(d,[(28,36),(26,43)],dark,2); poly(d,[(14,23),(4,15),(9,32)],dark); ellipse(d,(39,18,41,20),(16,16,14,255))
    elif 'rabbit' in name or 'hare' in name:
        ellipse(d,(13,20,38,39),fur,dark); ellipse(d,(33,15,45,27),fur,dark); poly(d,[(36,17),(36,3),(40,16)],fur,dark); poly(d,[(41,17),(45,2),(45,18)],fur,dark); ellipse(d,(40,19,42,21),(20,20,18,255)); ellipse(d,(9,28,17,36),light)
    elif 'bear' in name:
        ellipse(d,(8,14,40,39),fur,dark); ellipse(d,(34,15,49,30),fur,dark); ellipse(d,(36,11,41,17),fur); ellipse(d,(44,12,49,18),fur); line(d,[(15,35),(14,43)],dark,4); line(d,[(32,35),(33,43)],dark,4); ellipse(d,(45,22,48,25),(20,18,16,255))
    elif 'boar' in name:
        ellipse(d,(9,18,40,38),fur,dark); poly(d,[(38,21),(50,25),(41,31)],fur,dark); line(d,[(47,26),(52,24)],light,2); line(d,[(47,28),(52,30)],light,2); line(d,[(15,35),(14,43)],dark,3); line(d,[(34,35),(35,43)],dark,3)
    elif 'deer' in name or 'elk' in name or 'moose' in name or 'goat' in name:
        ellipse(d,(10,19,37,37),fur,dark); poly(d,[(34,22),(38,10),(46,11),(48,23),(42,28)],fur,dark); line(d,[(15,34),(14,44)],dark,3); line(d,[(31,34),(32,44)],dark,3)
        if 'goat' in name:
            d.arc((36,3,44,13),170,350,fill=dark,width=2); d.arc((42,3,50,13),190,10,fill=dark,width=2)
        else:
            for x in [39,45]: line(d,[(x,12),(x+rng.choice([-3,3]),3)],dark,2); line(d,[(x,7),(x+rng.choice([-5,5]),5)],dark,1)
        ellipse(d,(44,15,46,17),(16,16,14,255))
    elif any(k in name for k in ['crawler','grazer','stalker']):
        if 'crawler' in name:
            ellipse(d,(10,18,42,36),(78,92,78,255),(39,50,42,255));
            for x in range(12,42,6): line(d,[(x,31),(x-6,42)],(48,61,51,255),2); line(d,[(x,31),(x+6,42)],(48,61,51,255),2)
        elif 'grazer' in name:
            ellipse(d,(8,16,42,39),(107,118,92,255),(54,63,51,255)); poly(d,[(38,18),(49,14),(46,28)],(93,105,81,255)); line(d,[(15,35),(13,44)],(55,62,51,255),3); line(d,[(35,35),(36,44)],(55,62,51,255),3)
        else:
            ellipse(d,(8,19,40,36),(74,74,84,255),(33,34,41,255)); poly(d,[(37,20),(50,16),(47,31)],(74,74,84,255)); line(d,[(16,34),(10,44)],(37,37,45,255),3); line(d,[(34,34),(40,44)],(37,37,45,255),3); ellipse(d,(44,20,47,23),(179,45,56,255))
    else: # wolf/fox/badger
        ellipse(d,(9,19,38,37),fur,dark); poly(d,[(35,22),(43,11),(50,21),(46,30)],fur,dark); poly(d,[(39,14),(40,6),(44,13)],dark); line(d,[(15,34),(13,43)],dark,3); line(d,[(32,34),(34,43)],dark,3); line(d,[(10,25),(2,17)],fur,5); ellipse(d,(45,20,48,23),(18,18,16,255))
        if 'badger' in name: line(d,[(39,13),(47,27)],light,3)
        if 'fox' in name: line(d,[(7,24),(1,18)],light,2)
    # subtle per-variant markings
    if variant%2: noise(d,rng,(12,18,38,34),[light,dark],5)
    return im

def npc_sprite(idx:int):
    rng=random.Random(5000+idx); im=img((32,48)); d=ImageDraw.Draw(im); draw_shadow(d,16,43,7,2)
    skin_pal=[(238,198,160),(205,156,116),(165,112,79),(112,72,52),(83,54,43),(229,183,137)]
    hair_pal=[(45,31,24),(92,57,35),(154,103,54),(211,187,139),(58,53,48),(122,42,32)]
    cloth_pal=[(65,91,116),(103,74,112),(92,111,67),(131,77,59),(80,90,81),(126,105,57),(55,104,99),(119,83,46)]
    skin=(*skin_pal[idx%len(skin_pal)],255); hair=(*hair_pal[(idx//2)%len(hair_pal)],255); cloth=(*cloth_pal[(idx//3)%len(cloth_pal)],255); pants=(*cloth_pal[(idx//5+3)%len(cloth_pal)],255)
    # legs/boots
    px(d,(10,31,14,42),pants); px(d,(18,31,22,42),pants); px(d,(9,41,14,45),(51,42,35,255)); px(d,(18,41,23,45),(51,42,35,255))
    # torso, arms, hands
    poly(d,[(9,18),(23,18),(25,33),(7,33)],cloth,(40,43,44,255)); line(d,[(9,21),(4,31)],cloth,4); line(d,[(23,21),(28,31)],cloth,4); ellipse(d,(2,29,7,34),skin); ellipse(d,(25,29,30,34),skin)
    # head
    ellipse(d,(9,6,23,20),skin,(65,48,40,255));
    # hair varieties
    style=idx%6
    if style==0: d.pieslice((8,4,24,17),180,360,fill=hair)
    elif style==1: px(d,(8,5,24,10),hair); px(d,(8,8,11,17),hair)
    elif style==2:
        for x in range(9,24,3): line(d,[(x,8),(x+rng.randint(-2,2),3)],hair,2)
    elif style==3: d.arc((8,4,24,20),180,360,fill=hair,width=4)
    elif style==4: px(d,(9,4,23,9),hair); line(d,[(22,8),(26,17)],hair,3)
    else: px(d,(10,5,22,8),hair)
    # face/readability
    px(d,(12,12,13,13),(31,28,25,255)); px(d,(19,12,20,13),(31,28,25,255));
    # accent sash/belt
    line(d,[(8,28),(24,28)],(176,137,65,255) if idx%4==0 else (65,51,43,255),2)
    return im

def crop_sprite(crop, stage=2):
    rng=random.Random(seed_for(crop["id"])+stage*313)
    im=img((32,40)); d=ImageDraw.Draw(im); draw_shadow(d,16,35,8,2)
    name=crop["name"].lower(); green=(71,129,62,255); green2=(102,157,75,255); gold=(181,151,70,255)
    h=[12,21,31][max(0,min(2,stage))]
    for x in (9,14,19,24):
        line(d,[(x,34),(x+rng.choice([-1,0,1]),34-h)],green if x%2 else green2,2)
        if stage>=1:
            line(d,[(x,25),(x-4,21)],green2,2); line(d,[(x,22),(x+4,18)],green2,2)
        if stage==2:
            if any(k in name for k in ['wheat','barley','flax']):
                px(d,(x-2,5,x+2,13),gold)
            elif 'beans' in name:
                ellipse(d,(x-3,12,x+3,20),(84,142,73,255))
            elif 'cabbage' in name:
                ellipse(d,(x-5,16,x+5,27),(86,139,70,255))
            elif any(k in name for k in ['carrot','turnip','onion']):
                poly(d,[(x-3,25),(x+3,25),(x+1,34),(x-1,34)],(201,116,52,255) if 'carrot' in name else (184,165,120,255))
    return im

def make_preview(paths, out):
    ims=[]
    for p in paths:
        try: ims.append(Image.open(p).convert('RGBA'))
        except: pass
    cell=64; cols=8; rows=math.ceil(len(ims)/cols); sheet=Image.new('RGBA',(cols*cell,rows*cell),(22,24,25,255))
    for i,im0 in enumerate(ims):
        im0.thumbnail((58,58),Image.Resampling.NEAREST); x=(i%cols)*cell+(cell-im0.width)//2; y=(i//cols)*cell+(cell-im0.height)//2; sheet.alpha_composite(im0,(x,y))
    save(sheet,out)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    items=json.load(open(DATA/'items.json',encoding='utf-8')); terrain=json.load(open(DATA/'terrain.json',encoding='utf-8')); resources=json.load(open(DATA/'resources.json',encoding='utf-8')); structures=json.load(open(DATA/'structures.json',encoding='utf-8')); species=json.load(open(DATA/'species.json',encoding='utf-8')); crops=json.load(open(DATA/'crops.json',encoding='utf-8'))
    manifest={'version':1,'tile_px':32,'items':{},'terrain':{},'resources':{},'structures':{},'species':{},'crops':{},'npc_variants':[],'procedural_species':[],'special':{}}
    preview=[]
    for it in items:
        p=OUT/'items'/f'{sid(it["id"])}.png'; save(item_sprite(it),p); manifest['items'][it['id']]=str(p.relative_to(ROOT/'worldseed')).replace('\\','/'); preview.append(p)
    for t in terrain:
        p=OUT/'terrain'/f'{sid(t["id"])}.png'; save(terrain_sprite(t),p); manifest['terrain'][t['id']]=str(p.relative_to(ROOT/'worldseed')).replace('\\','/'); preview.append(p)
    for r in resources:
        p=OUT/'resources'/f'{sid(r["id"])}.png'; save(resource_sprite(r),p); manifest['resources'][r['id']]=str(p.relative_to(ROOT/'worldseed')).replace('\\','/'); preview.append(p)
    for s in structures:
        p=OUT/'structures'/f'{sid(s["id"])}.png'; save(structure_sprite(s),p); manifest['structures'][s['id']]=str(p.relative_to(ROOT/'worldseed')).replace('\\','/'); preview.append(p)
    for crop in crops:
        arr=[]
        for stage in range(3):
            p=OUT/'crops'/sid(crop['id'])/f'stage_{stage}.png'; save(crop_sprite(crop,stage),p); arr.append(str(p.relative_to(ROOT/'worldseed')).replace('\\','/')); preview.append(p)
        manifest['crops'][crop['id']]=arr
    for sp in species:
        arr=[]
        for v in range(4):
            p=OUT/'species'/sid(sp['id'])/f'variant_{v}.png'; save(animal_sprite(sp,v),p); arr.append(str(p.relative_to(ROOT/'worldseed')).replace('\\','/')); preview.append(p)
        manifest['species'][sp['id']]=arr
    pseudo_names=['Ash Grazer','Thorn Runner','Mire Stalker','Stone Hulk','Frost Horn','Dusk Crawler','Ember Fang','Moss Lurker']
    for i,name in enumerate(pseudo_names):
        fake={'id':f'procedural:{i}','name':name}
        p=OUT/'species'/'procedural'/f'variant_{i}.png'; save(animal_sprite(fake,i%4),p); manifest['procedural_species'].append(str(p.relative_to(ROOT/'worldseed')).replace('\\','/')); preview.append(p)
    for i in range(32):
        p=OUT/'npc'/f'variant_{i:02d}.png'; save(npc_sprite(i),p); manifest['npc_variants'].append(str(p.relative_to(ROOT/'worldseed')).replace('\\','/')); preview.append(p)
    # player marker and cursor
    p=OUT/'special'/'player.png'; save(npc_sprite(31),p); manifest['special']['player']=str(p.relative_to(ROOT/'worldseed')).replace('\\','/')
    cur=img((32,32)); d=ImageDraw.Draw(cur); line(d,[(2,8),(2,2),(8,2)],(241,205,70,255),2); line(d,[(24,2),(30,2),(30,8)],(241,205,70,255),2); line(d,[(2,24),(2,30),(8,30)],(241,205,70,255),2); line(d,[(24,30),(30,30),(30,24)],(241,205,70,255),2); p2=OUT/'special'/'cursor.png'; save(cur,p2); manifest['special']['cursor']=str(p2.relative_to(ROOT/'worldseed')).replace('\\','/')
    fog=Image.new('RGBA',(32,32),(9,12,14,255)); noise(ImageDraw.Draw(fog),random.Random(9),(0,0,31,31),[(14,18,20,255),(6,8,10,255)],28); p3=OUT/'special'/'unknown.png'; save(fog,p3); manifest['special']['unknown']=str(p3.relative_to(ROOT/'worldseed')).replace('\\','/')
    MANIFEST.parent.mkdir(parents=True,exist_ok=True); MANIFEST.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    make_preview(preview[:96], ROOT/'worldseed'/'assets'/'sprite_preview.png')
    print(f"generated items={len(items)} terrain={len(terrain)} resources={len(resources)} structures={len(structures)} species={len(species)*4} crops={len(crops)*3} procedural=8 npc=32")

if __name__=='__main__': main()
