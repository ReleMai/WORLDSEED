#!/usr/bin/env python3
"""Author the salvage expansion's transparent, item-specific pixel-art icons.

Every icon is drawn from its named physical object: blades, cages, books,
mechanisms, baskets, flowers, garments and biological remains have different
silhouettes. Material masks receive bounded grain/highlights; damage is drawn
on the actual object rather than represented by an interchangeable loot bag.
This offline art tool never imports simulation or consumes gameplay RNG.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "worldseed" / "data"
OUT = ROOT / "worldseed" / "assets" / "sprites" / "items"
SIZE = 64
CLEAR = (0, 0, 0, 0)
PALETTES = {
    "metal": ((39, 48, 54), (113, 128, 138), (222, 229, 225)),
    "iron": ((35, 40, 44), (89, 103, 115), (180, 194, 194)),
    "steel": ((41, 48, 57), (142, 159, 173), (238, 243, 240)),
    "copper": ((83, 42, 28), (180, 101, 60), (248, 179, 103)),
    "bronze": ((77, 57, 32), (163, 129, 64), (239, 205, 126)),
    "brass": ((81, 59, 29), (184, 149, 65), (255, 223, 128)),
    "silver": ((70, 76, 82), (173, 181, 187), (246, 247, 243)),
    "gold": ((108, 70, 18), (208, 159, 38), (255, 225, 101)),
    "wood": ((58, 37, 26), (141, 89, 46), (211, 158, 92)),
    "oak": ((58, 37, 24), (128, 87, 45), (201, 155, 94)),
    "pine": ((68, 43, 28), (175, 121, 60), (236, 188, 108)),
    "cloth": ((46, 56, 53), (133, 155, 119), (221, 224, 171)),
    "linen": ((76, 71, 52), (182, 176, 137), (245, 237, 200)),
    "wool": ((50, 51, 65), (122, 118, 143), (202, 193, 206)),
    "silk": ((68, 39, 49), (159, 79, 95), (234, 172, 174)),
    "leather": ((65, 36, 25), (134, 73, 43), (211, 135, 77)),
    "ceramic": ((70, 35, 24), (166, 78, 40), (238, 147, 78)),
    "glass": ((32, 70, 75), (74, 141, 152), (187, 238, 228)),
    "paper": ((86, 67, 46), (204, 182, 137), (250, 232, 178)),
    "plant": ((29, 60, 29), (83, 136, 58), (176, 205, 99)),
    "bone": ((84, 73, 57), (193, 179, 140), (249, 236, 189)),
    "stone": ((49, 53, 55), (117, 125, 128), (185, 186, 174)),
    "food": ((75, 32, 24), (157, 70, 47), (232, 154, 85)),
    "fish": ((36, 60, 69), (126, 163, 163), (220, 231, 207)),
    "red": ((78, 32, 34), (170, 57, 54), (236, 127, 105)),
    "blue": ((27, 46, 78), (70, 114, 169), (154, 203, 225)),
    "purple": ((62, 39, 74), (132, 77, 153), (212, 156, 219)),
}


def stable_seed(value: str) -> int:
    return int.from_bytes(hashlib.sha256(("worldseed.salvage.art:" + value).encode()).digest()[:8], "big")


class Art:
    def __init__(self, row: dict, family: str):
        self.row = row
        self.name = row["name"].lower()
        self.family = family
        self.rng = random.Random(stable_seed(row["id"]))
        self.image = Image.new("RGBA", (SIZE, SIZE), CLEAR)
        self.d = ImageDraw.Draw(self.image)
        self.d.ellipse((12, 53, 53, 60), fill=(8, 10, 12, 48))
        self.primary = family if family in PALETTES else "wood"
        for key in ("steel", "iron", "copper", "bronze", "brass", "silver", "gold", "oak", "pine", "linen", "wool", "silk"):
            if key in self.name:
                self.primary = key
                break
        self.tint = self.rng.choice(("red", "blue", "purple", "cloth"))

    def material(self, shape: str, points, mat: str | None = None, width: int = 1):
        """Ink an outlined material mask, then light its actual occupied pixels."""
        mat = mat or self.primary
        dark, mid, light = PALETTES[mat]
        mask = Image.new("L", (SIZE, SIZE), 0)
        md = ImageDraw.Draw(mask)
        if shape == "polygon":
            md.polygon(points, fill=255)
        elif shape == "ellipse":
            md.ellipse(points, fill=255)
        elif shape == "rectangle":
            md.rectangle(points, fill=255)
        elif shape == "line":
            md.line(points, fill=255, width=width)
        bbox = mask.getbbox()
        if bbox is None:
            return
        pixels = mask.load()
        paint = Image.new("RGBA", (SIZE, SIZE), CLEAR)
        pp = paint.load()
        x0, y0, x1, y1 = bbox
        for y in range(y0, y1):
            for x in range(x0, x1):
                if not pixels[x, y]:
                    continue
                edge = any(not (0 <= nx < SIZE and 0 <= ny < SIZE) or not pixels[nx, ny]
                           for nx, ny in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)))
                if edge:
                    c = dark
                else:
                    level = max(0.0, min(1.0, .68 - .45*(x-x0)/max(1,x1-x0) - .24*(y-y0)/max(1,y1-y0)))
                    target = light if level > .40 else dark
                    mix = (level-.40)*1.5 if level > .40 else (.40-level)*.55
                    c = tuple(int(a+(b-a)*mix) for a,b in zip(mid,target))
                    # Grain direction belongs to material, not an arbitrary border.
                    grain = self.rng.randrange(-9, 10)
                    if mat in {"wood", "oak", "pine"} and (x + y//10) % 7 == 0:
                        grain -= 16
                    if mat in {"cloth", "linen", "wool", "silk"} and (x%3==0 or y%3==0):
                        grain -= 10
                    c = tuple(max(0,min(255,v+grain)) for v in c)
                pp[x,y] = (*c,255)
        self.image.alpha_composite(paint)
        self.d = ImageDraw.Draw(self.image)

    def poly(self, pts, mat=None): self.material("polygon", pts, mat)
    def box(self, box, mat=None): self.material("rectangle", box, mat)
    def oval(self, box, mat=None): self.material("ellipse", box, mat)
    def rod(self, pts, mat=None, width=5): self.material("line", pts, mat, width)
    def line(self, pts, color, width=1): self.d.line(pts, fill=(*color,255), width=width)
    def hole(self, box): self.d.ellipse(box, fill=CLEAR)
    def rivet(self,x,y):
        self.d.ellipse((x-1,y-1,x+2,y+2),fill=(39,35,25,255))
        self.d.point((x,y),fill=(242,216,148,255))
    def ring(self,box,mat=None,width=4):
        self.oval(box,mat)
        x0,y0,x1,y1=box
        self.hole((x0+width,y0+width,x1-width,y1-width))
    def stripes(self, box, mat="wood", vertical=True, step=7):
        x0,y0,x1,y1=box
        color=PALETTES[mat][0]
        if vertical:
            for x in range(x0+step,x1,step): self.line([(x,y0+1),(x,y1-1)],color)
        else:
            for y in range(y0+step,y1,step): self.line([(x0+1,y),(x1-1,y)],color)
    def stitch(self, points):
        for x,y in points: self.line([(x,y),(x+1,y+2)],(216,175,110))
    def crack(self):
        x=self.rng.randint(25,39);y=self.rng.randint(18,25)
        self.line([(x,y),(x-3,y+6),(x+1,y+10),(x-4,y+15)],(35,32,30),2)
    def leaf(self,x,y,w=8,h=5,mat="plant"):
        self.poly([(x-w,y),(x-2,y-h),(x+w,y-2),(x+2,y+h)],mat)
        self.line([(x-w+2,y),(x+w-2,y-1)],PALETTES[mat][2])
    def stem(self, pts): self.rod(pts,"plant",3)
    def flower(self,x,y,color="purple",size=4):
        for dx,dy in ((-size,0),(size,0),(0,-size),(0,size)):
            self.oval((x+dx-3,y+dy-3,x+dx+3,y+dy+3),color)
        self.oval((x-2,y-2,x+2,y+2),"gold")


def draw_object(a: Art, motif: str):
    """Physical motifs are small authored constructions with honest silhouettes."""
    p=a.primary
    if motif in {"axe", "pick", "hammer", "mallet", "adze", "hoe", "rake", "shovel"}:
        a.rod([(18,55),(38,16)],"wood",7)
        a.line([(21,51),(38,19)],(215,156,91))
        if motif=="axe":
            a.poly([(30,16),(45,9),(55,11),(56,30),(49,34),(33,26)],p)
            a.line([(52,14),(53,28)],PALETTES[p][2],2)
        elif motif=="pick":
            a.poly([(9,25),(24,15),(38,13),(52,17),(58,26),(42,21),(31,22),(13,31)],p)
        elif motif in {"hammer","mallet"}:
            a.poly([(23,10),(48,13),(51,20),(48,27),(23,23),(19,17)],"wood" if motif=="mallet" else p)
            a.box((23,12,28,21),"iron")
        elif motif=="adze": a.poly([(32,15),(47,9),(50,12),(44,29),(38,30)],p)
        elif motif=="hoe": a.poly([(27,15),(43,15),(51,36),(42,40),(34,21)],p)
        elif motif=="rake":
            a.rod([(22,16),(53,26)],"wood",5)
            for x,y in [(25,18),(33,20),(41,23),(49,25)]: a.rod([(x,y),(x-5,y+10)],p,3)
        else:
            a.poly([(29,17),(43,18),(47,30),(35,39),(26,30)],p)
            a.line([(35,20),(35,32)],PALETTES[p][2])
        for x,y in ((29,30),(30,27),(32,24)): a.line([(x-2,y-1),(x+4,y+2)],(191,159,102),2)
    elif motif in {"knife", "chisel", "sword", "spear", "file", "saw", "cleaver"}:
        a.rod([(13,53),(25,40)],"leather",8)
        a.line([(15,50),(21,44)],(215,148,85),2)
        if motif=="knife": a.poly([(23,42),(33,17),(53,8),(42,35),(29,45)],p)
        elif motif=="chisel": a.poly([(24,42),(43,10),(49,13),(32,47)],p)
        elif motif=="sword":
            a.poly([(24,42),(43,9),(50,6),(49,15),(31,45)],p)
            a.rod([(19,35),(35,47)],"bronze",5)
        elif motif=="spear":
            a.rod([(12,54),(43,17)],"wood",4)
            a.poly([(37,20),(52,5),(52,19),(45,29)],p)
        elif motif=="file":
            a.poly([(24,43),(43,14),(49,18),(31,47)],p)
            for y in range(20,39,4): a.line([(42-(y-20)//2,y),(47-(y-20)//2,y+3)],(47,55,58))
        elif motif=="cleaver": a.poly([(23,42),(26,18),(43,8),(55,12),(42,43)],p)
        else:
            a.poly([(23,40),(38,13),(56,21),(37,47)],p)
            for x,y in ((36,18),(42,22),(48,25)): a.poly([(x,y),(x-3,y+6),(x+2,y+5)],"iron")
        a.line([(29,38),(44,16)],PALETTES[p][2],2)
    elif motif in {"pliers", "tongs", "shears", "clamp"}:
        a.rod([(13,53),(33,30),(23,12)],p,6)
        a.rod([(45,52),(33,30),(42,11)],p,6)
        a.rivet(33,30)
        if motif=="shears":
            a.ring((8,42,23,58),"iron",4);a.ring((39,43,54,58),"iron",4)
        elif motif=="clamp":
            a.rod([(23,12),(42,12)],p,5);a.rod([(20,47),(51,47)],"iron",3)
        else:
            a.rod([(12,52),(22,40)],"leather",7);a.rod([(45,51),(38,41)],"leather",7)
    elif motif in {"needle", "awl", "hook", "pins"}:
        if motif=="hook":
            a.ring((15,28,46,54),p,5);a.box((15,10,21,39),p);a.poly([(39,31),(47,28),(45,41)],p)
        else:
            count=3 if motif=="pins" else 1
            for i in range(count):
                a.rod([(15+i*7,54),(43+i*3,10+i*7)],p,3)
                if motif=="needle": a.hole((41,10,43,15))
                if motif=="awl": a.rod([(16,52),(26,39)],"wood",7)
    elif motif in {"gear", "wheel", "pulley", "cog", "millstone"}:
        cx,cy=32,32;r=21
        teeth=10+a.rng.randrange(5)
        pts=[]
        for i in range(teeth*4):
            ang=2*math.pi*i/(teeth*4)
            rr=r if i%4 in (0,1) else r-4
            pts.append((round(cx+rr*math.cos(ang)),round(cy+rr*math.sin(ang))))
        if motif in {"gear","cog"}: a.poly(pts,p)
        else:a.ring((10,10,54,54),p,6)
        if motif!="millstone":
            for i in range(6):
                ang=i*math.pi/3
                a.rod([(32,32),(round(32+16*math.cos(ang)),round(32+16*math.sin(ang)))],p,5)
        a.ring((24,24,40,40),"iron" if motif=="wheel" else p,5)
        if motif=="millstone":
            a.oval((10,10,54,54),"stone");a.hole((27,27,37,37))
            for i in range(8):
                ang=i*math.pi/4;a.line([(round(32+10*math.cos(ang)),round(32+10*math.sin(ang))),(round(32+19*math.cos(ang+.2)),round(32+19*math.sin(ang+.2)))],(66,70,71),2)
    elif motif in {"nuts", "bolts", "nails", "rivets", "hinge", "latch", "key", "lock", "spring", "chain", "buckle", "fittings"}:
        if motif in {"nuts","bolts","nails","rivets"}:
            for x,y,length in ((15,19,29),(35,11,33),(46,31,19)):
                if motif=="nuts":
                    a.poly([(x-7,y+4),(x-4,y-3),(x+4,y-3),(x+8,y+4),(x+4,y+11),(x-4,y+11)],p)
                    a.hole((x-2,y+2,x+3,y+7))
                else:
                    a.rod([(x,y+3),(x-6,y+length)],p,4)
                    a.box((x-5,y-2,x+5,y+4),p)
                    if motif=="bolts":
                        for v in range(y+8,y+length-1,4):a.line([(x-(v-y)//5-2,v),(x-(v-y)//5+2,v+1)],(41,49,55))
        elif motif=="hinge":
            a.poly([(10,17),(29,11),(31,44),(15,52)],p);a.poly([(34,11),(51,17),(51,52),(34,44)],p)
            a.rod([(32,12),(33,46)],"iron",6)
            for x,y in ((17,22),(20,43),(44,24),(44,44)):a.rivet(x,y)
        elif motif=="key":
            a.ring((10,8,31,29),p,5);a.rod([(26,24),(50,49)],p,5)
            a.box((42,36,49,42),p);a.box((47,43,55,49),p)
        elif motif=="lock":
            a.ring((20,9,44,36),"iron",6);a.box((13,29,51,54),p)
            a.oval((29,36,36,43),"iron");a.box((31,40,34,47),"iron")
        elif motif in {"buckle","latch","fittings"}:
            a.ring((12,15,52,48),p,7)
            a.rod([(32,17),(32,47)],p,4);a.rod([(19,32),(42,32)],p,4)
            if motif=="latch":a.rod([(8,48),(53,11)],"iron",6)
        elif motif=="spring":
            for y in range(11,49,6):a.ring((18,y,45,y+13),p,3)
        else:
            for i in range(5):a.ring((12+i*6,8+i*7,29+i*6,29+i*7),p,4)
    elif motif in {"scraps", "plate", "ingot", "wire"}:
        if motif=="wire":
            for i in range(4):a.ring((12+i*2,12+i*3,50-i,48+i*2),p,3)
            a.rod([(47,43),(56,55)],p,3)
        elif motif=="ingot":
            a.poly([(8,36),(43,16),(57,23),(21,49)],p);a.poly([(8,36),(21,49),(21,55),(8,43)],p)
            a.poly([(21,49),(57,23),(55,31),(21,55)],p)
        else:
            a.poly([(9,26),(25,14),(40,19),(32,39),(15,44)],p)
            a.poly([(28,35),(46,24),(57,36),(47,54),(30,51)],p)
            if motif=="plate":a.box((15,17,48,45),p)
    elif motif in {"planks", "handle", "sticks", "spool", "frame", "ladder", "crate", "barrel", "bucket", "chest", "basket", "tray", "table", "stool", "chair", "yoke"}:
        if motif=="planks":
            for i in range(3):a.poly([(8,37+i*5),(42,13+i*5),(54,20+i*5),(21,47+i*5)],p)
        elif motif in {"handle","sticks"}:
            for i in range(3 if motif=="sticks" else 1):
                a.rod([(15+i*8,54),(38+i*6,10+i*5)],p,5 if motif=="sticks" else 9)
            if motif=="handle":a.oval((32,9,43,17),p)
        elif motif=="spool":
            a.box((23,14,43,49),"linen");a.oval((14,7,50,20),p);a.oval((14,44,50,56),p)
            a.stripes((24,19,42,43),"linen",False,3)
        elif motif in {"frame","ladder","yoke"}:
            a.rod([(15,54),(17,10)],p,7);a.rod([(47,54),(45,10)],p,7)
            for y in range(15,54,11):a.rod([(17,y),(46,y)],p,5)
            if motif=="frame":a.rod([(17,52),(46,12)],p,4)
            if motif=="yoke":a.poly([(11,11),(51,11),(54,24),(47,29),(44,19),(20,19),(17,29),(10,24)],p)
        elif motif in {"barrel","bucket","basket"}:
            a.poly([(12,18),(51,18),(46,52),(38,57),(23,57),(16,52)],p)
            a.oval((12,12,51,25),p);a.oval((17,15,46,21),"wood")
            a.stripes((17,26,46,51),p,True,6)
            if motif=="basket":
                a.stripes((17,27,46,51),p,False,5);a.ring((15,4,47,35),p,4)
            else:
                a.rod([(16,30),(49,30)],"iron",4);a.rod([(19,47),(46,47)],"iron",4)
                if motif=="bucket":a.ring((16,6,47,35),"iron",3)
        elif motif in {"crate","chest","tray"}:
            a.poly([(10,22),(41,10),(54,22),(23,34)],p)
            a.poly([(10,22),(23,34),(23,55),(10,44)],p)
            a.poly([(23,34),(54,22),(54,44),(23,55)],p)
            for y in (29,36,43):a.line([(24,y+8),(52,y-4)],PALETTES[p][0])
            a.rod([(25,36),(49,42)],p,5)
            if motif=="chest":a.box((35,29,43,43),"iron");a.rivet(39,38)
            if motif=="tray":a.poly([(13,23),(41,14),(50,23),(23,31)],"paper")
        elif motif in {"table","stool","chair"}:
            a.rod([(15,31),(12,56)],p,5);a.rod([(46,31),(51,54)],p,5);a.rod([(31,37),(31,58)],p,5)
            a.poly([(10,25),(36,16),(54,28),(29,40)],p)
            if motif=="chair":
                a.rod([(16,28),(17,8)],p,5);a.rod([(44,26),(45,8)],p,5);a.box((17,9,45,19),p)
    elif motif in {"rope", "net", "sack", "cloth", "ribbon", "sail", "rug", "banner"}:
        if motif=="rope":
            for i in range(4):a.ring((10+i*4,11+i*4,52-i*3,53-i*3),p,4)
            a.rod([(44,48),(55,57)],p,5)
        elif motif=="net":
            a.poly([(15,11),(48,14),(56,43),(30,55),(9,39)],"linen")
            for x in range(16,50,7):a.line([(x,16),(x+4,43)],(55,54,37),2)
            for y in range(19,48,7):a.line([(14,y),(48,y-3)],(55,54,37),2)
            a.rod([(13,11),(48,13),(55,43),(30,55),(10,39),(13,11)],"wood",3)
        elif motif=="sack":
            a.poly([(22,13),(43,13),(40,22),(50,44),(46,55),(17,55),(12,44),(25,22)],p)
            a.rod([(20,22),(43,22)],"leather",3);a.line([(24,28),(18,43),(23,50)],PALETTES[p][2])
        else:
            pts=[(10,15),(42,10),(54,21),(47,50),(30,57),(12,49)]
            if motif=="ribbon":pts=[(13,7),(25,11),(32,44),(49,53),(42,59),(22,47)]
            if motif=="banner":a.rod([(13,57),(13,8)],"wood",4);pts=[(15,10),(51,12),(48,40),(32,33),(16,39)]
            if motif=="sail":pts=[(14,52),(20,10),(51,49)];a.rod([(18,54),(20,7)],"wood",4)
            a.poly(pts,p)
            for x,y in ((19,22),(27,29),(35,35),(43,43)):a.line([(x-3,y),(x+5,y+3)],PALETTES[p][2])
            if motif=="rug":a.stitch([(x,49) for x in range(15,43,4)])
    elif motif in {"shirt", "coat", "apron", "pants", "boots", "gloves", "hat", "hood", "helmet", "armor", "shield", "belt", "bag", "quiver"}:
        if motif in {"shirt","coat","apron","armor"}:
            a.poly([(22,10),(42,10),(52,22),(46,30),(41,25),(44,55),(20,55),(23,25),(16,30),(10,22)],p)
            a.oval((26,8,38,18),"leather");a.line([(32,19),(32,52)],PALETTES[p][0],2)
            if motif=="apron":a.poly([(23,20),(41,20),(46,56),(18,56)],"linen")
            if motif=="armor":
                for y in range(23,49,7):a.rod([(22,y),(43,y)],"iron",3)
            else:
                a.box((23,33,29,42),p);a.stitch([(23,y) for y in range(34,42,3)])
        elif motif=="pants":
            a.poly([(19,9),(44,9),(47,52),(36,56),(31,30),(28,56),(16,52)],p)
            a.rod([(19,15),(44,15)],"leather",4)
        elif motif=="boots":
            for dx,dy in ((0,0),(19,-7)):
                a.poly([(12+dx,22+dy),(25+dx,22+dy),(24+dx,43+dy),(36+dx,48+dy),(33+dx,55+dy),(11+dx,55+dy)],p)
                a.rod([(13+dx,53+dy),(33+dx,53+dy)],"wood",3)
                a.stitch([(20+dx,y+dy) for y in range(26,40,4)])
        elif motif=="gloves":
            for dx,dy in ((0,0),(23,8)):
                a.poly([(10+dx,44+dy),(11+dx,21+dy),(14+dx,18+dy),(16+dx,30+dy),(18+dx,14+dy),(22+dx,15+dy),(23+dx,31+dy),(29+dx,24+dy),(32+dx,27+dy),(26+dx,43+dy),(24+dx,50+dy),(11+dx,50+dy)],p)
        elif motif in {"hat","hood","helmet"}:
            a.oval((14,10,49,49),p);a.box((10,36,54,46),p)
            if motif in {"hood","helmet"}:a.oval((23,28,42,45),"iron")
            else:a.rod([(14,46),(51,46)],"leather",4)
            if motif=="helmet":a.rod([(32,11),(32,45)],"bronze",4);a.rivet(31,21)
        elif motif=="shield":
            a.poly([(11,13),(31,8),(53,13),(50,37),(32,58),(14,37)],p)
            a.rod([(16,16),(47,48)],"iron",4);a.rod([(49,16),(18,47)],"iron",4);a.oval((25,23,39,38),"iron")
        elif motif=="belt":
            a.ring((8,12,55,53),p,7);a.ring((36,15,53,33),"brass",4)
        else:
            a.poly([(17,22),(45,22),(51,50),(43,57),(19,55),(13,47)],p)
            a.ring((20,8,44,37),p,5);a.box((18,22,44,30),p);a.rivet(31,29)
            if motif=="quiver":a.rod([(24,29),(29,3)],"wood",3);a.rod([(35,29),(43,7)],"wood",3)
    elif motif in {"pot", "jar", "bowl", "cup", "plateware", "bottle", "vial", "flask", "lamp", "lantern", "candle", "mortar", "pipe"}:
        if motif in {"bottle","vial","flask"}:
            a.poly([(24,15),(25,6),(38,6),(40,17),(48,24),(47,51),(42,56),(21,55),(16,49),(17,26)],p)
            a.box((24,5,39,11),"wood")
            a.line([(22,28),(22,46),(26,51)],PALETTES[p][2],2)
            a.box((23,31,40,42),"paper");a.line([(26,35),(37,35)],(97,70,48))
        elif motif in {"pot","jar","mortar"}:
            a.oval((12,21,52,57),p);a.box((18,17,46,32),p);a.oval((15,12,49,24),p)
            a.oval((20,15,44,21),"wood");a.line([(20,29),(18,37)],PALETTES[p][2],2)
            if motif=="mortar":a.rod([(32,32),(48,9)],"stone",7)
            else:a.ring((43,27,58,42),p,4)
        elif motif in {"bowl","cup"}:
            a.poly([(10,25),(53,25),(45,51),(22,52)],p);a.oval((10,17,53,33),p);a.oval((15,21,48,28),"wood")
            if motif=="cup":a.ring((45,28,59,44),p,4)
        elif motif=="plateware":
            a.oval((8,15,56,51),p);a.oval((16,21,48,43),p);a.line([(16,30),(19,25),(33,23)],PALETTES[p][2],2)
        elif motif=="candle":
            a.box((23,20,41,52),"bone");a.oval((23,17,41,25),"bone");a.line([(32,21),(32,13)],(47,37,27),2)
            a.poly([(31,8),(26,15),(33,19),(37,14)],"gold");a.oval((15,50,49,58),p)
        elif motif in {"lamp","lantern"}:
            a.box((19,15,45,47),"glass");a.rod([(17,17),(46,17)],p,5);a.rod([(17,49),(46,49)],p,5)
            a.rod([(18,18),(18,49)],p,4);a.rod([(46,18),(46,49)],p,4)
            a.ring((23,5,41,24),p,3);a.poly([(32,28),(25,40),(35,45),(40,38)],"gold")
        else:
            a.rod([(11,52),(27,39),(29,18),(46,12)],p,9);a.oval((42,8,55,18),p);a.hole((46,11,51,15))
    elif motif in {"book", "pages", "scroll", "map", "card", "brush", "ink", "seal", "instrument", "flute", "bell", "mirror", "comb"}:
        if motif=="book":
            a.poly([(11,13),(29,9),(52,14),(51,52),(31,57),(11,52)],p)
            a.poly([(15,14),(29,13),(29,53),(15,48)],"paper");a.poly([(32,13),(48,17),(48,48),(32,53)],"paper")
            for y in range(21,46,7):a.line([(17,y),(26,y+1)],(105,77,48));a.line([(35,y),(45,y+2)],(105,77,48))
        elif motif in {"pages","map","card","scroll"}:
            a.poly([(12,13),(50,10),(54,49),(17,54)],"paper")
            if motif=="scroll":a.oval((8,8,20,55),"paper");a.oval((45,5,58,50),"paper")
            for y in range(20,45,6):a.line([(23,y),(43,y-1)],(126,97,58))
            if motif=="map":a.line([(20,43),(27,23),(38,31),(45,18)],(107,107,65),2);a.oval((35,27,40,31),"blue")
        elif motif=="brush":
            a.rod([(13,54),(40,22)],"wood",6);a.poly([(35,25),(40,8),(51,7),(56,14),(44,31)],"linen")
            a.rod([(35,28),(45,22)],"iron",5)
        elif motif=="ink":
            a.box((15,29,44,55),"glass");a.oval((15,25,44,36),"iron");a.rod([(38,40),(49,10)],"wood",3)
            a.poly([(42,25),(45,7),(56,10),(52,22)],"bone")
        elif motif=="seal":
            a.rod([(31,15),(31,39)],"wood",12);a.oval((23,8,40,25),"wood");a.oval((14,35,49,53),p)
            a.line([(25,43),(31,48),(39,41)],(235,198,100),2)
        elif motif=="flute":
            a.rod([(10,52),(52,11)],p,8)
            for x,y in ((21,41),(29,34),(37,27),(43,21)):a.oval((x-2,y-2,x+2,y+2),"iron")
        elif motif=="bell":
            a.poly([(25,16),(39,16),(42,38),(54,48),(10,48),(22,37)],p);a.ring((25,8,38,20),p,3);a.oval((27,46,38,54),"iron")
        elif motif=="mirror":
            a.rod([(32,38),(32,56)],p,7);a.oval((12,6,52,44),p);a.oval((17,11,47,39),"silver")
            a.line([(22,15),(37,33)],(244,252,248),3)
        elif motif=="comb":
            a.box((10,15,54,26),p)
            for x in range(12,53,5):a.rod([(x,25),(x,47)],p,3)
        else:
            a.oval((14,27,42,56),p);a.rod([(36,34),(48,9)],"wood",6);a.rod([(46,8),(55,14)],"wood",7)
            a.oval((21,34,34,45),"iron");a.line([(28,51),(49,12)],(232,202,139),2)
    elif motif in {"flower", "leaves", "roots", "mushroom", "bulb", "seedpod", "sap", "bark", "cone", "herbs"}:
        if motif=="mushroom":
            for x,y,h in ((22,44,19),(42,53,24)):
                a.rod([(x,y),(x,y-h)],"bone",6)
                a.poly([(x-12,y-h+2),(x-8,y-h-9),(x+3,y-h-12),(x+13,y-h+2)],p)
                for dx,dy in ((-4,-7),(4,-5),(8,-1)):a.oval((x+dx-1,y-h+dy-1,x+dx+2,y-h+dy+2),"bone")
        elif motif in {"roots","bulb"}:
            a.oval((19,27,44,46),"bone" if motif=="bulb" else "wood")
            for x in range(20,45,6):a.rod([(x,40),(x-4,55),(x-8,58)],"wood",3)
            for x in (20,29,40):a.stem([(31,30),(x,9)]);a.leaf(x,13,5,3)
        elif motif in {"bark","sap"}:
            a.poly([(14,12),(29,8),(49,16),(45,54),(28,58),(11,46)],"wood")
            for x in (18,27,38):a.line([(x,15),(x+2,30),(x-2,47)],(54,38,27),2)
            if motif=="sap":a.oval((24,27,40,47),"gold");a.oval((36,14,43,23),"gold")
        elif motif=="cone":
            a.oval((16,8,48,56),"wood")
            for y in range(14,53,7):
                for x in range(20+(y//7%2)*4,46,8):a.poly([(x,y),(x+7,y),(x+4,y+8)],"pine")
        else:
            stems=3 if motif=="flower" else 5
            for i in range(stems):
                x=14+i*(34//max(1,stems-1));y=12+a.rng.randrange(12)
                a.stem([(32,55),(x,y)])
                a.leaf((32+x)//2,(55+y)//2,7,4)
                if motif=="flower":a.flower(x,y,a.tint)
                elif motif=="seedpod":a.oval((x-4,y-5,x+5,y+7),"paper")
                else:a.leaf(x,y,7,4)
            a.rod([(25,47),(37,47)],"linen",3)
    elif motif in {"skull", "bones", "antler", "horn", "teeth", "claw", "feathers", "shell", "scale", "hide", "fat", "gland", "sinew"}:
        if motif=="skull":
            a.oval((14,8,48,40),"bone");a.poly([(18,30),(45,30),(41,50),(23,54)],"bone")
            a.oval((19,20,28,30),"iron");a.oval((35,20,44,30),"iron");a.poly([(28,34),(36,34),(32,40)],"iron")
            for x in range(23,42,5):a.line([(x,44),(x,50)],(92,77,56),2)
        elif motif=="bones":
            for x,y in ((17,53),(30,48)):
                a.rod([(x,y),(x+19,y-33)],"bone",7);a.oval((x-5,y-5,x+4,y+4),"bone");a.oval((x+16,y-37,x+24,y-29),"bone")
        elif motif in {"antler","horn"}:
            a.rod([(23,54),(34,34),(45,11)],"bone",7)
            if motif=="antler":
                for pts in ([(31,40),(14,30),(13,17)],[(36,30),(29,20),(31,10)],[(40,22),(53,19),(56,10)]):a.rod(pts,"bone",4)
            else:a.poly([(21,54),(31,54),(43,38),(50,15),(45,8),(36,34)],"bone")
        elif motif in {"teeth","claw"}:
            for x,y in ((15,19),(30,11),(43,27)):
                a.poly([(x-4,y),(x+7,y-2),(x+10,y+11),(x+3,y+28),(x,y+9)],"bone")
        elif motif=="feathers":
            for i in range(3):
                x=14+i*11;a.poly([(x,49),(x-5,23),(x+2,8+i*4),(x+9,17),(x+8,32)],"bone" if i!=1 else "cloth")
                a.rod([(x-2,55),(x+3,16)],"paper",2)
        elif motif=="shell":
            a.poly([(31,10),(16,17),(8,31),(15,48),(32,55),(50,47),(57,31),(46,17)],"bone")
            for x in range(13,54,6):a.line([(32,49),(x,23)],(140,111,77))
        elif motif=="scale":
            for i in range(6):
                x=15+(i%3)*12;y=16+(i//3)*21
                a.poly([(x-7,y),(x+7,y),(x+9,y+11),(x,y+18),(x-8,y+10)],p)
        elif motif=="hide":
            a.poly([(17,8),(27,15),(33,7),(39,15),(51,11),(47,29),(56,44),(40,45),(32,58),(25,46),(10,47),(17,29)],"leather")
            a.line([(25,22),(36,19),(42,33),(32,45)],(209,140,86))
        elif motif=="sinew":
            for i in range(6):a.rod([(14+i*5,53),(19+i*4,34),(28+i*3,11)],"bone",3)
            a.rod([(14,40),(47,31)],"leather",3)
        else:
            a.poly([(13,20),(28,10),(47,15),(55,33),(44,51),(25,55),(10,37)],"bone" if motif=="fat" else "red")
            a.line([(19,27),(28,24),(40,31),(41,42)],(234,170,125),3)
    elif motif in {"bread", "meal", "dried_food", "cheese", "meat", "pie", "medicine", "salve", "soap", "charcoal", "powder", "brick", "gem", "ore", "tile", "beads"}:
        if motif in {"medicine","salve","soap"}:
            a.box((14,27,49,53),"ceramic" if motif=="salve" else "bone")
            a.oval((14,21,49,34),"paper");a.oval((22,24,42,30),"plant")
            if motif=="medicine":a.stem([(39,31),(49,10)]);a.leaf(45,15)
        elif motif in {"bread","pie","cheese"}:
            a.oval((9,24,55,53),"paper");a.oval((13,19,51,43),"wood" if motif=="bread" else "gold")
            for x in range(20,46,9):a.line([(x,25),(x-5,34)],(232,183,94),3)
            if motif=="cheese":
                for x,y in ((23,29),(38,32),(30,39)):a.oval((x-2,y-2,x+2,y+2),"wood")
        elif motif=="meal":
            a.oval((8,20,56,54),"wood");a.oval((13,22,51,46),"food")
            for x,y in ((23,30),(35,28),(44,36),(28,41)):a.leaf(x,y,4,3)
        elif motif in {"meat","dried_food"}:
            a.poly([(9,23),(25,14),(43,17),(55,34),(44,49),(22,54),(10,40)],"food")
            for x,y in ((20,27),(29,31),(39,36)):a.line([(x,y),(x+8,y+5)],(244,187,138),2)
            if motif=="dried_food":a.rod([(12,49),(48,23)],"linen",3)
        elif motif in {"brick","tile"}:
            a.poly([(9,30),(39,13),(55,23),(23,44)],p)
            a.poly([(9,30),(23,44),(23,54),(9,42)],p);a.poly([(23,44),(55,23),(55,34),(23,54)],p)
        elif motif=="beads":
            for i in range(8):
                ang=i*math.pi/4;x=round(32+19*math.cos(ang));y=round(32+19*math.sin(ang))
                a.oval((x-5,y-5,x+5,y+5),p);a.hole((x-1,y-1,x+1,y+1))
        else:
            for x,y in ((16,35),(31,25),(44,42)):
                a.poly([(x-8,y),(x-5,y-12),(x+5,y-15),(x+11,y-4),(x+6,y+9),(x-5,y+11)],p)
            if motif=="gem":a.line([(24,30),(30,13),(38,24)],PALETTES[p][2],2)
    else:
        raise ValueError(f"Unrecognized physical motif {motif!r}: {a.row['id']}")


def draw_special(a: Art, motif: str) -> bool:
    p = a.primary
    if motif == "rung":
        a.rod([(9,44),(52,18)],"wood",8)
        a.rod([(15,32),(21,42)],"wood",11);a.rod([(42,17),(48,27)],"wood",11)
    elif motif == "door":
        a.poly([(12,15),(47,8),(53,50),(17,58)],"wood")
        for x in (23,33,43):a.line([(x,15),(x+4,49)],(71,45,27),2)
        a.rod([(17,22),(46,16)],"wood",5);a.rod([(20,48),(49,42)],"wood",5)
        a.box((43,28,48,36),"iron");a.rivet(46,32)
    elif motif == "pebble":
        a.oval((13,22,53,52),"stone");a.line([(19,32),(26,27),(38,27)],(172,180,174),2)
    elif motif == "wedge":
        for x,y in ((12,30),(29,15),(34,36)):
            a.poly([(x,y),(x+18,y-4),(x+7,y+22)],p)
            a.line([(x+3,y+2),(x+7,y+15)],PALETTES[p][2])
    elif motif == "hoof":
        a.poly([(17,14),(29,10),(44,15),(49,40),(44,55),(29,54),(14,48),(13,29)],"bone")
        a.line([(31,18),(29,49)],(80,68,49),3)
        a.line([(18,44),(24,48)],(132,117,83),2)
    elif motif == "carapace":
        a.poly([(14,17),(29,10),(45,15),(54,32),(48,49),(32,56),(14,45),(9,30)],"bronze")
        a.rod([(16,31),(49,31)],"bone",3);a.line([(30,15),(32,49)],(205,176,110),2)
        for x,y in ((17,22),(22,41),(42,20),(45,42)):a.rivet(x,y)
    elif motif == "crossbow_trigger":
        a.poly([(13,18),(43,12),(49,25),(36,34),(23,52),(16,48),(23,31)],"wood")
        a.ring((27,26,46,45),"iron",4);a.rod([(38,27),(33,38)],"iron",3)
        a.rivet(30,23)
    elif motif == "reel":
        a.rod([(14,17),(45,50)],"wood",6)
        a.ring((13,23,43,51),"iron",5);a.oval((20,29,36,46),"copper")
        a.rod([(35,37),(50,37),(53,24)],"iron",4);a.oval((48,18,57,29),"wood")
        a.line([(20,44),(12,56)],(221,204,155),2)
    elif motif == "fishing_rod":
        a.rod([(10,56),(29,34),(52,6)],"wood",4)
        a.rod([(11,55),(24,40)],"leather",7)
        a.ring((20,31,35,46),"brass",4);a.rivet(28,39)
        for x,y in ((31,31),(39,22),(46,13)):a.ring((x-2,y-2,x+3,y+3),"iron",2)
        a.line([(53,8),(54,39),(48,48)],(236,217,166))
        a.ring((43,43,50,51),"bone",2)
        if "spring" in a.name:
            for x,y in ((23,38),(25,35),(27,33)):a.ring((x-3,y-3,x+4,y+4),"steel",2)
        else:a.rod([(28,34),(33,29)],"brass",5)
    elif motif == "float_rig":
        a.line([(13,10),(27,25),(35,41),(46,53)],(221,207,162),2)
        a.oval((19,17,35,35),"bone");a.poly([(27,17),(34,22),(35,30),(27,27)],"red")
        a.rod([(26,12),(27,19)],"wood",3);a.oval((32,37,39,44),"stone")
        a.ring((41,46,52,58),"bone",3);a.rod([(42,43),(42,52)],"bone",3)
    elif motif == "spinner":
        a.rod([(22,13),(43,47)],"silver",3);a.ring((17,6,28,17),"silver",3)
        a.poly([(22,23),(32,16),(42,24),(39,36),(30,42),(23,34)],"copper")
        a.line([(28,23),(35,25),(35,32)],(247,182,103),2)
        a.ring((36,42,49,58),"iron",3);a.rod([(37,38),(37,50)],"iron",3)
        if "articulated" in a.name:
            a.ring((32,34,39,42),"silver",2);a.oval((28,34,33,39),"red")
    elif motif == "trident":
        a.rod([(12,57),(38,27)],"wood",6)
        for x,y in ((28,14),(39,7),(52,14)):
            a.rod([(35,31),(x,y+6)],"iron",4)
            a.poly([(x-3,y+7),(x,y-3),(x+4,y+5)],"steel")
        a.rod([(26,27),(45,23)],"iron",4)
    elif motif == "sling":
        a.rod([(12,12),(22,29),(24,40)],"linen",3)
        a.rod([(50,13),(40,31),(36,40)],"linen",3)
        a.poly([(21,34),(34,30),(43,38),(40,49),(28,56),(17,44)],"leather")
        a.oval((24,36,36,47),"stone");a.stitch([(21,41),(26,50),(36,48)])
        a.ring((8,7,17,16),"linen",2)
    elif motif == "dart":
        a.rod([(11,55),(43,18)],"wood",4)
        a.poly([(36,20),(48,5),(52,11),(43,27)],"bone")
        a.poly([(13,51),(7,43),(14,38),(19,44)],"bone")
        a.poly([(14,51),(22,49),(25,41),(19,45)],"cloth")
        a.rod([(35,25),(41,19)],"leather",5)
    elif motif == "arrow_points":
        for x,y in ((15,29),(31,12),(45,32)):
            a.poly([(x,y-6),(x-7,y+12),(x-3,y+10),(x-2,y+21),(x+3,y+21),(x+4,y+10),(x+9,y+13)],"bone")
            a.line([(x,y),(x,y+10)],(245,232,184))
    elif motif == "bow_limbs":
        for dx,dy in ((0,0),(10,7)):
            a.rod([(10+dx,45+dy),(15+dx,32+dy),(29+dx,22+dy),(35+dx,9+dy),(43+dx,8+dy)],"wood",6)
            a.line([(12+dx,43+dy),(18+dx,31+dy),(31+dx,22+dy),(37+dx,11+dy)],(222,181,106),2)
            a.rod([(11+dx,44+dy),(14+dx,38+dy)],"leather",6)
    elif motif == "frame_saw":
        a.rod([(9,47),(24,11),(54,19),(42,54),(9,47)],"iron",4)
        a.rod([(11,46),(40,53)],"steel",5)
        for x in range(13,39,5):a.poly([(x,49),(x+3,55),(x+5,50)],"steel")
        a.rod([(24,14),(22,27)],"wood",8)
        if "tensioned" in a.name:a.box((37,15,49,24),"brass");a.rivet(44,20)
    elif motif == "auger":
        a.rod([(32,11),(28,50)],"steel",5);a.rod([(13,14),(52,14)],"wood",8)
        for y in range(25,49,5):a.rod([(23,y+4),(34,y-1)],"iron",4)
        a.poly([(25,48),(31,48),(26,58)],"steel")
        a.rivet(32,14)
    elif motif == "plate_set":
        for x,y in ((11,18),(28,11),(24,36),(43,29)):
            a.poly([(x,y),(x+13,y-2),(x+15,y+16),(x+2,y+20)],"iron")
            a.rivet(x+4,y+4);a.rivet(x+10,y+13)
    elif motif == "armor_vest":
        a.poly([(22,10),(42,10),(50,23),(44,28),(42,53),(20,53),(19,28),(12,23)],"leather")
        for y in range(22,47,9):
            for x in (22,30,38):
                a.box((x,y,x+7,y+8),"iron");a.rivet(x+3,y+3)
        a.rod([(20,16),(24,18)],"linen",4);a.rod([(40,17),(44,15)],"linen",4)
    elif motif == "bracers":
        for dx,dy in ((0,0),(24,5)):
            a.poly([(12+dx,13+dy),(29+dx,16+dy),(28+dx,50+dy),(9+dx,47+dy)],"leather")
            for yy in (21,31,41):a.rod([(13+dx,yy+dy),(27+dx,yy+dy+3)],"bone",4)
            a.rod([(11+dx,17+dy),(28+dx,20+dy)],"linen",3)
    elif motif == "buckler":
        a.oval((8,8,56,56),"leather");a.ring((8,8,56,56),"bone",4)
        for x in (21,31,41):a.rod([(x,17),(x,47)],"bone",5)
        a.oval((24,23,41,41),"iron");a.rivet(31,31)
    elif motif == "filter_candle":
        a.box((24,13,40,50),"ceramic");a.oval((24,7,40,19),"ceramic")
        a.oval((20,46,44,56),"ceramic")
        for x,y in ((28,16),(35,21),(29,27),(35,33),(28,39),(35,44)):a.oval((x,y,x+1,y+2),"stone")
        a.hole((28,10,36,14))
    elif motif == "screen":
        a.poly([(8,29),(36,10),(56,28),(29,52)],"linen")
        for y in range(23,42,5):a.line([(16,y+10),(44,y-7)],(72,73,48))
        for x in range(16,44,5):a.line([(x,25),(x+12,37)],(72,73,48))
        a.rod([(8,29),(36,10),(56,28),(29,52),(8,29)],"wood",5)
    elif motif == "net":
        for x in range(15,49,6):a.rod([(x,15),(x+4,43)],"linen",2)
        for y in range(19,44,6):a.rod([(14,y),(49,y-3)],"linen",2)
        a.rod([(13,13),(47,13),(54,42),(31,54),(10,40),(13,13)],"linen",3)
        if "weighted" in a.name or "cast" in a.name:
            for x,y in ((14,39),(27,50),(39,47),(51,40)):a.oval((x-2,y-2,x+2,y+2),"stone")
    elif motif in {"panel", "leather_panel", "paper_panel"}:
        mat="leather" if motif=="leather_panel" else "paper" if motif=="paper_panel" else p
        a.poly([(12,14),(44,9),(53,44),(22,55),(12,49)],mat)
        a.poly([(12,14),(17,12),(25,46),(53,42),(53,48),(23,59)],mat)
        if "reinforced" in a.name or "sealed" in a.name:
            a.rod([(17,18),(43,48)],"leather" if motif=="panel" else "wood",2)
        a.stitch([(19,20),(21,29),(23,38),(29,48),(38,45),(45,42)])
    elif motif == "roving":
        for y in (22,29,36,43):
            a.rod([(12,y+7),(20,y-4),(41,y-6),(52,y+4)],"wool",7)
        a.rod([(28,16),(34,48)],"linen",3)
    elif motif == "felt":
        for dy in (8,4,0):a.poly([(10,24+dy),(38,11+dy),(55,26+dy),(26,46+dy)],"wool")
        a.line([(17,26),(36,17),(45,23)],(187,180,188))
    elif motif == "pulp":
        a.oval((9,22,55,53),"wood");a.oval((13,25,51,47),"linen")
        for i in range(24):
            x=a.rng.randrange(19,46);y=a.rng.randrange(28,43)
            a.line([(x,y),(x+2,y+1)],(139,155,98))
    elif motif == "powder_bowl":
        a.oval((10,29,54,56),"ceramic")
        a.oval((12,27,52,43),p)
        a.poly([(15,34),(25,21),(37,20),(49,34)],p)
        for i in range(26):
            x=a.rng.randrange(22,43);y=a.rng.randrange(26,37)
            a.d.point((x,y),fill=(*PALETTES[p][2],255))
    elif motif == "dumplings":
        a.oval((8,30,56,55),"wood")
        for x,y in ((11,30),(28,23),(32,39)):
            a.oval((x,y-7,x+22,y+11),"paper")
            for dx in (5,10,15):a.line([(x+dx,y-2),(x+dx-2,y+5)],(194,173,124))
    elif motif == "pie":
        a.poly([(9,31),(19,19),(36,17),(54,31),(49,47),(22,52),(10,43)],"paper")
        a.poly([(15,30),(21,23),(35,23),(46,31),(43,41),(25,46),(15,40)],"wood")
        for x,y in ((21,29),(30,28),(38,33)):a.line([(x,y),(x+4,y+8)],(246,224,168),3)
        a.stitch([(15,34),(19,44),(31,48),(43,42),(49,33)])
    elif motif == "broth":
        a.oval((9,25,53,56),"ceramic");a.oval((10,20,53,36),"wood")
        a.ring((4,28,17,41),"ceramic",3);a.ring((46,28,59,41),"ceramic",3)
        for x,y in ((21,26),(33,27),(42,26)):a.leaf(x,y,4,2)
        if "bone" in a.name:a.rod([(24,28),(36,24)],"bone",4)
    elif motif == "sausage":
        for pts in ([(12,23),(20,12),(38,13),(49,24)],[(16,39),(23,27),(43,32),(50,46)]):
            a.rod(pts,"food",9)
        for x,y in ((13,23),(49,24),(16,39),(50,46)):a.rod([(x-3,y-3),(x+3,y+3)],"linen",3)
        a.line([(20,15),(31,15)],(227,148,112),2)
    elif motif == "dressing_pad":
        for dy in (6,3,0):a.poly([(12,22+dy),(40,11+dy),(53,36+dy),(25,51+dy)],"linen")
        for x in (19,27,35):a.line([(x,25),(x+12,40)],(226,215,174))
        a.rod([(31,14),(21,47)],"linen",3)
    elif motif == "needle_lens":
        a.rod([(11,57),(45,10)],"silver",3);a.ring((41,7,49,16),"silver",2)
        a.rod([(27,33),(43,37)],"brass",3)
        a.ring((34,24,56,46),"brass",3);a.oval((38,28,52,42),"glass")
        a.line([(41,30),(48,38)],(217,245,235),2)
    elif motif == "tool_roll":
        a.poly([(8,25),(41,17),(55,44),(17,57)],"leather")
        for x,y in ((18,45),(29,42),(39,38)):
            a.rod([(x,y),(x+9,y-22)],"bone",4)
            a.rod([(x,y),(x+3,y-8)],"wood",6)
        a.rod([(13,47),(47,38)],"leather",4)
    elif motif == "claw_hammer":
        a.rod([(14,56),(37,18)],"wood",7)
        a.poly([(26,13),(41,12),(49,19),(50,26),(44,25),(43,20),(39,20),(36,29),(23,25)],"iron")
        a.box((20,14,28,26),"steel");a.line([(25,16),(38,15)],(192,206,204),2)
    elif motif in {"bent_frame","splint_frame"}:
        if motif=="bent_frame":
            a.rod([(12,50),(10,26),(16,14),(34,9),(48,17),(53,41),(43,54),(12,50)],"wood",6)
            a.line([(14,47),(13,28),(18,17),(34,13),(45,21)],(216,165,100))
        else:
            a.rod([(15,53),(22,10)],"wood",6);a.rod([(40,54),(47,12)],"wood",6)
            for y in (22,43):a.rod([(18,y),(45,y+1)],"linen",5)
            a.ring((28,19,38,28),"leather",3)
    elif motif == "gaiters":
        for dx,dy in ((0,0),(24,5)):
            a.poly([(13+dx,12+dy),(31+dx,13+dy),(27+dx,47+dy),(13+dx,52+dy),(9+dx,42+dy)],"leather")
            a.oval((13+dx,9+dy,31+dx,17+dy),"leather")
            a.oval((17+dx,11+dy,28+dx,14+dy),"wool")
            for yy in (24,35,44):a.rod([(12+dx,yy+dy),(28+dx,yy+dy-2)],"linen",3)
    elif motif == "blade_blank":
        a.poly([(10,46),(17,27),(39,10),(52,15),(45,37),(24,55)],"stone")
        for pts in ([(16,41),(24,29),(27,47)],[(27,25),(40,15),(37,32)],[(30,45),(42,32),(35,48)]):a.poly(pts,"stone")
        a.line([(18,46),(40,18)],(174,185,178),2)
    elif motif == "fork":
        a.rod([(12,56),(36,28)],"wood",6)
        for x,y in ((25,10),(35,8),(44,11),(53,16)):a.rod([(36,30),(x,y+5),(x+3,y)],"iron",4)
    elif motif == "horn_staff":
        a.rod([(16,56),(44,10)],"wood",7)
        a.rod([(16,56),(20,50)],"bone",9);a.rod([(41,16),(44,10)],"bone",8)
        for y in range(30,39,3):a.rod([(28,y),(34,y+3)],"wool",3)
    elif motif == "spinner_blade":
        a.poly([(29,9),(42,12),(52,27),(49,42),(37,54),(24,50),(13,32),(17,17)],"copper")
        a.hole((26,12,32,18));a.line([(25,24),(32,20),(41,31),(39,43)],(237,166,94),2)
    elif motif == "grains":
        a.oval((9,28,55,54),"wood");a.oval((12,26,52,42),"paper")
        for i in range(31):
            x=a.rng.randrange(17,49);y=a.rng.randrange(25,42)
            a.oval((x,y,x+3,y+1),"gold" if "malted" in a.name else "wood")
    elif motif == "herb_sachet":
        a.poly([(20,16),(42,16),(43,29),(51,45),(44,56),(18,55),(12,44),(22,29)],"linen")
        a.rod([(19,25),(43,25)],"leather",3);a.stem([(25,22),(32,7)]);a.leaf(30,12,6,3)
        a.stem([(32,22),(43,10)]);a.leaf(39,15,7,3)
    elif motif == "minced_meat":
        a.oval((9,28,55,55),"wood")
        for i in range(20):
            x=a.rng.randrange(16,45);y=a.rng.randrange(25,43)
            a.poly([(x,y),(x+5,y-3),(x+9,y+3),(x+3,y+7)],"food")
    elif motif == "tallow":
        a.oval((11,26,53,56),"ceramic");a.oval((14,22,50,39),"bone")
        a.line([(20,28),(27,25),(39,29)],(249,235,179),2)
        a.rod([(41,38),(54,13)],"wood",4)
    elif motif == "preserve_jar":
        a.box((15,20,49,49),"glass");a.oval((15,41,49,56),"glass")
        a.oval((15,15,49,28),"glass");a.oval((20,18,44,24),"wood")
        # The visible contents convey the actual preparation at inventory scale.
        if "fruit" in a.name:
            for x,y in ((24,31),(38,30),(30,41),(40,46)):a.oval((x-5,y-4,x+5,y+4),"purple")
        elif "cabbage" in a.name:
            for x,y in ((23,33),(36,32),(26,43),(39,45)):a.leaf(x,y,7,4)
        elif "fish" in a.name:
            for x,y in ((20,32),(29,40),(35,31)):a.poly([(x,y),(x+9,y-3),(x+12,y+4),(x+2,y+7)],"fish")
        elif "root" in a.name:
            for x,y in ((23,32),(34,29),(29,41),(40,43)):a.oval((x-3,y-3,x+4,y+4),"gold")
        else:
            for x,y in ((24,32),(37,34),(28,44)):a.poly([(x-6,y-3),(x+4,y-5),(x+7,y+5),(x-3,y+7)],"food")
        a.line([(18,26),(18,45),(21,50)],(190,235,226),2)
        a.box((14,13,50,19),"wood");a.rod([(15,20),(49,20)],"linen",3)
    elif motif == "drink_bottle":
        a.poly([(24,17),(25,6),(38,6),(40,18),(47,25),(47,50),(40,57),(22,56),(16,49),(17,26)],"glass")
        liquid="purple" if "cordial" in a.name or "orchid" in a.name else "plant" if "herb" in a.name or "kelp" in a.name else "gold"
        a.poly([(20,31),(44,31),(44,49),(39,53),(24,52),(20,47)],liquid)
        a.box((24,5,39,11),"wood");a.line([(22,23),(22,46),(26,50)],(198,241,223),2)
        a.box((24,35,40,46),"paper")
        if liquid=="plant":a.stem([(30,44),(33,37)]);a.leaf(32,40,3,2)
        elif liquid=="purple":a.flower(32,40,"purple",2)
        else:a.rod([(29,43),(33,37)],"wood",2)
        if "beer" in a.name:a.rod([(21,31),(44,31)],"bone",4)
    elif motif == "infusion":
        a.poly([(12,26),(48,26),(44,49),(20,50)],"ceramic")
        a.ring((43,26,58,44),"ceramic",4)
        a.oval((12,19,48,32),"ceramic");a.oval((17,23,44,28),"plant")
        a.stem([(25,24),(20,8)]);a.leaf(19,14,7,3)
        a.oval((13,49,49,55),"ceramic")
    elif motif == "hood":
        a.poly([(16,37),(15,23),(19,13),(31,7),(43,13),(49,26),(46,40),(55,53),(39,58),(25,55),(9,50)],p)
        lining="wool" if "fur" in a.name or "forester" in a.name else "linen"
        a.oval((20,18,44,45),lining);a.hole((24,23,40,41))
        a.rod([(29,46),(26,53)],"linen",2);a.rod([(35,46),(38,52)],"linen",2)
        a.line([(17,42),(21,49)],PALETTES[p][2],2)
    elif motif == "coat":
        a.poly([(23,10),(40,10),(51,21),(56,41),(48,44),(42,29),(45,55),(34,57),(31,41),(27,57),(17,54),(21,28),(13,43),(7,38),(13,20)],p)
        a.poly([(23,12),(30,21),(31,43),(25,38)],"linen")
        a.poly([(40,12),(33,21),(31,43),(39,37)],"linen")
        a.rod([(20,41),(42,41)],"leather",3)
        if "winter" in a.name:
            for x,y in ((14,34),(47,35),(25,14),(35,14)):a.oval((x-4,y-3,x+4,y+3),"wool")
        elif "paper" in a.name:
            for y in (27,33,46,51):a.line([(20,y),(42,y)],(173,149,98))
        else:a.box((20,43,27,51),"leather");a.box((36,43,42,51),"leather")
    elif motif == "armor" and "leather" in a.name:
        a.poly([(22,10),(41,10),(49,21),(43,28),(43,55),(19,55),(21,29),(14,23)],"leather")
        a.poly([(22,22),(31,18),(41,22),(39,39),(31,46),(22,38)],"leather")
        for x,y in ((23,26),(40,26),(23,42),(39,43)):a.rivet(x,y)
        a.rod([(21,48),(41,48)],"leather",4);a.ring((28,44,37,52),"brass",2)
    elif motif == "mittens":
        for dx,dy in ((0,0),(23,7)):
            a.poly([(12+dx,44+dy),(12+dx,20+dy),(17+dx,11+dy),(27+dx,12+dy),(29+dx,23+dy),(35+dx,23+dy),(37+dx,30+dy),(27+dx,39+dy),(26+dx,48+dy)],"leather")
            a.rod([(11+dx,43+dy),(27+dx,45+dy)],"wool",6)
            a.line([(16+dx,23+dy),(16+dx,34+dy)],(198,139,89))
    elif motif == "bread":
        name=a.name
        if "flatbread" in name or "griddle" in name:
            for y in (40,34,28):
                a.oval((10,y,54,y+14),"paper")
                for x in (19,31,43):a.oval((x,y+4,x+3,y+6),"wood")
        elif "hardtack" in name or "crispbread" in name or "rusk" in name:
            for x,y in ((12,27),(29,15),(31,35)):
                a.poly([(x,y),(x+18,y-3),(x+23,y+12),(x+4,y+17)],"paper")
                for dx,dy in ((6,4),(12,2),(9,10),(16,8)):a.oval((x+dx,y+dy,x+dx+1,y+dy+1),"wood")
        elif "bun" in name:
            for x,y in ((11,33),(29,27),(27,41)):
                a.oval((x,y-10,x+23,y+12),"bone")
                for dx in (6,12,17):a.line([(x+12,y-7),(x+dx,y+1)],(190,170,122))
        elif "travel" in name:
            a.poly([(10,28),(41,16),(54,33),(24,50)],"wood")
            a.poly([(10,28),(24,50),(24,56),(10,36)],"wood")
            for i in range(15):
                x=a.rng.randrange(23,43);y=a.rng.randrange(28,40)
                a.line([(x,y),(x+2,y+1)],(224,181,100))
        else:
            a.oval((8,23,56,52),"wood");a.oval((12,18,52,44),"paper")
            for x in range(23,46,9):a.line([(x,22),(x-5,35)],(143,94,43),3)
    elif motif == "pestle":
        a.rod([(15,53),(44,14)],p,9);a.oval((9,45,25,59),p);a.oval((38,8,51,20),p)
        if "grooved" in a.name:
            for y in range(31,49,5):a.line([(22+(47-y)//2,y),(29+(47-y)//2,y+4)],PALETTES[p][0],2)
    elif motif == "bow":
        a.rod([(10,51),(15,38),(27,31),(33,21),(37,9),(49,10)],"wood",5)
        a.line([(10,51),(49,10)],(226,202,142),2)
        a.rod([(21,38),(31,29)],"leather",6)
    elif motif == "plane":
        a.poly([(10,32),(42,13),(55,24),(23,45)],"wood")
        a.poly([(10,32),(23,45),(23,53),(10,42)],"wood")
        a.poly([(23,45),(55,24),(55,35),(23,53)],"wood")
        a.rod([(30,36),(32,16)],"iron",8);a.rod([(35,29),(44,15)],"wood",6)
    elif motif == "driver":
        a.rod([(13,52),(31,32)],"wood",10)
        a.rod([(30,34),(49,13)],"iron",4);a.rod([(45,14),(49,10)],"iron",6)
        a.line([(16,48),(24,38)],(217,151,84))
    elif motif == "mace":
        a.rod([(14,55),(36,28)],"wood",7)
        a.poly([(26,17),(36,8),(47,13),(55,25),(45,37),(31,31)],p)
        a.rod([(28,30),(47,13)],"leather",3)
    elif motif == "coil":
        for y in range(15,43,7):a.ring((15,y,50,y+15),p,4)
        a.rod([(47,21),(53,10)],p,5);a.rod([(18,48),(10,56)],p,5)
    elif motif == "thimble":
        a.poly([(24,12),(38,11),(44,20),(46,49),(18,49),(20,23)],p)
        a.oval((18,43,46,53),p)
        for x,y in ((26,20),(34,20),(23,29),(31,29),(38,29),(26,37),(35,37)):a.oval((x-1,y-1,x+1,y+1),"iron")
    elif motif == "mould":
        a.poly([(10,20),(43,11),(54,21),(24,32)],p)
        a.poly([(10,20),(24,32),(24,55),(10,44)],p)
        a.poly([(24,32),(54,21),(54,44),(24,55)],p)
        a.poly([(24,22),(30,18),(40,20),(44,25),(31,29)],"iron")
    elif motif == "dough":
        a.oval((11,28,55,55),"paper");a.oval((17,20,47,43),"bone")
        a.line([(23,30),(27,27),(35,29)],(242,229,185),2)
    elif motif == "flour":
        a.poly([(18,15),(44,15),(41,25),(50,49),(44,57),(16,55),(12,47),(22,26)],"linen")
        a.oval((19,9,45,24),"paper");a.oval((24,12,40,20),"bone")
        a.stem([(25,45),(33,32)]);a.leaf(29,36,4,2)
    elif motif == "fish":
        a.poly([(8,30),(18,22),(33,18),(45,23),(55,14),(52,30),(57,45),(44,36),(28,39),(15,36)],"fish")
        a.oval((13,27,16,30),"iron");a.line([(22,23),(20,34)],(229,231,191),2)
        a.poly([(28,19),(36,11),(39,23)],"fish");a.poly([(26,38),(35,46),(37,38)],"fish")
    elif motif == "fillet":
        a.poly([(9,28),(28,15),(50,23),(55,40),(36,54),(16,48)],"food")
        for x,y in ((20,26),(28,22),(35,26),(43,30)):a.line([(x,y),(x-6,y+13)],(242,180,149),2)
    elif motif == "spur":
        a.ring((12,12,45,48),p,5)
        a.d.rectangle((23,7,50,22),fill=CLEAR)
        a.rod([(40,38),(52,46)],p,4)
        a.poly([(51,39),(54,43),(60,43),(56,48),(58,54),(51,51),(46,54),(47,48),(44,43),(49,44)],p)
    elif motif == "bracket":
        a.poly([(12,13),(25,13),(25,38),(51,38),(51,51),(12,51)],p)
        for x,y in ((18,20),(18,43),(42,44)):a.rivet(x,y)
    elif motif == "ring":
        a.ring((11,10,53,54),p,7)
    elif motif in {"curtain", "quilt", "runner", "blanket"}:
        points={"curtain":[(13,10),(51,10),(49,55),(13,52)],
                "quilt":[(12,14),(49,11),(54,45),(43,55),(13,50)],
                "runner":[(9,31),(43,9),(55,27),(20,56)],
                "blanket":[(13,10),(45,13),(53,49),(37,56),(14,48)]}[motif]
        a.poly(points,p)
        if motif=="curtain":
            for x in range(17,49,7):a.line([(x,13),(x-2,49)],PALETTES[p][0],2)
            a.rod([(10,8),(54,8)],"wood",3)
        elif motif in {"quilt","blanket"}:
            for x in range(19,46,8):a.line([(x,17),(x+3,47)],PALETTES[p][2])
            for y in range(22,45,8):a.line([(17,y),(47,y+2)],PALETTES[p][2])
        else:
            a.rod([(12,32),(23,48)],"linen",3);a.rod([(41,14),(50,27)],"linen",3)
    elif motif == "bedroll":
        a.poly([(11,21),(36,9),(52,18),(51,43),(27,55),(11,44)],p)
        a.oval((11,20,31,55),p);a.ring((14,25,28,49),"linen",3)
        a.rod([(24,18),(45,43)],"leather",4)
    elif motif == "embroidery":
        a.oval((11,11,53,53),"linen");a.ring((8,8,56,56),"wood",4)
        a.stem([(30,45),(33,24)]);a.leaf(36,36,7,4);a.flower(31,24,"red",4)
        a.rod([(44,39),(58,18)],"steel",2)
    elif motif == "sole":
        a.poly([(25,8),(39,9),(46,18),(42,28),(36,35),(34,49),(27,56),(16,53),(15,44),(22,32),(19,21)],p)
        a.stitch([(x,y) for x,y in ((24,15),(35,15),(38,23),(29,43),(23,49),(22,29))])
    elif motif == "scabbard":
        a.poly([(40,9),(50,16),(23,55),(15,57),(16,46)],p)
        a.rod([(38,10),(48,17)],"iron",5);a.rod([(15,54),(20,57)],"iron",4)
        a.line([(40,20),(20,49)],(209,143,81))
    elif motif == "quiver":
        a.poly([(16,20),(36,13),(49,44),(41,55),(29,55)],p)
        a.rod([(18,21),(35,14)],"wood",4)
        a.rod([(24,27),(22,7)],"wood",3);a.rod([(29,25),(34,5)],"wood",3)
        a.poly([(19,8),(22,2),(27,8)],"bone");a.poly([(30,8),(35,2),(37,11)],"bone")
    elif motif == "muzzle":
        a.ring((10,13,53,51),"leather",6)
        for x in (19,31,43):a.rod([(x,17),(x+4,46)],"leather",4)
        a.rod([(15,31),(49,31)],"leather",4);a.ring((41,8,57,23),"iron",3)
    elif motif == "drum_head":
        a.oval((10,12,54,53),"leather");a.ring((8,10,56,55),"wood",4)
        for x,y in ((13,28),(19,16),(40,16),(51,30),(39,50),(20,48)):a.stitch([(x,y)])
    elif motif == "stopper":
        a.oval((18,11,46,29),"glass")
        a.poly([(21,27),(43,27),(38,52),(26,52)],"glass")
        a.line([(24,17),(23,23),(31,26)],(197,239,230),2)
    elif motif == "pendant":
        a.ring((10,7,52,55),"brass",2);a.ring((28,36,39,47),"brass",3)
        a.poly([(32,42),(22,49),(32,59),(44,50)],"glass")
        a.line([(32,45),(27,49),(33,55)],(227,248,236))
    elif motif == "lens_only":
        a.ring((13,13,50,49),"brass",3);a.oval((16,16,47,46),"glass")
        a.line([(22,18),(38,41)],(212,246,234),3)
    elif motif == "bottle_neck":
        a.poly([(23,9),(38,9),(40,26),(52,37),(45,44),(40,40),(32,45),(29,40),(18,43),(15,37),(22,26)],"glass")
        a.box((22,8,39,15),"glass");a.line([(26,19),(26,29),(21,35)],(198,239,237),2)
    elif motif == "sickle":
        a.rod([(14,53),(22,39)],"wood",8)
        a.ring((17,7,57,48),p,8)
        a.d.polygon([(8,2),(34,2),(34,30),(8,40)],fill=CLEAR)
        a.poly([(43,8),(55,12),(58,23),(47,19)],p)
    elif motif == "horseshoe":
        a.ring((11,8,53,54),p,9)
        a.d.rectangle((23,34,42,61),fill=CLEAR)
        for x,y in ((15,29),(20,17),(43,18),(49,32)):a.rivet(x,y)
    elif motif == "drill":
        a.rod([(15,49),(24,39),(25,15),(40,9),(48,19),(39,33)],"iron",5)
        a.rod([(25,26),(36,34)],"wood",8);a.rod([(39,34),(27,57)],"steel",4)
        for y in range(40,53,4):a.line([(31,y),(37,y-1)],(40,48,51))
    elif motif == "poker":
        a.rod([(12,54),(48,11)],p,5);a.ring((8,46,21,58),p,3)
        a.rod([(43,17),(55,20)],p,4)
    elif motif == "snuffer":
        a.rod([(10,55),(42,23)],p,4);a.poly([(34,25),(39,12),(48,8),(57,19),(46,28)],p)
    elif motif == "grate":
        a.box((10,11,53,54),p)
        for x in range(17,51,9):a.d.rectangle((x,17,x+3,48),fill=CLEAR)
        a.rod([(12,31),(51,31)],p,4)
    elif motif == "compass":
        a.ring((9,9,55,55),"brass",5);a.oval((16,16,48,48),"paper")
        a.poly([(31,17),(38,35),(31,47),(25,30)],"red")
        a.poly([(31,17),(31,34),(25,30)],"iron");a.rivet(31,32)
        for x,y in ((31,20),(43,31),(31,43),(20,31)):a.line([(x,y),(x+2,y)],(53,47,36),2)
    elif motif == "scale_balance":
        a.rod([(32,13),(32,53)],p,6);a.rod([(12,23),(52,16)],p,4)
        a.oval((19,49,46,58),p)
        for x,y in ((15,23),(48,18)):
            a.line([(x,y),(x-9,y+16),(x+8,y+16),(x,y)],(191,177,139))
            a.poly([(x-10,y+16),(x+9,y+16),(x+5,y+24),(x-5,y+24)],p)
    elif motif == "trap":
        a.ring((9,21,55,56),"iron",6);a.rod([(13,49),(20,13),(31,18),(45,12),(52,43)],"steel",5)
        for x in range(18,48,8):a.poly([(x,18),(x+4,26),(x+7,16)],"iron")
        a.box((26,33,42,48),p);a.rivet(32,41)
    elif motif == "bellows":
        a.poly([(10,24),(22,10),(43,17),(52,36),(41,47),(18,39)],"leather")
        for y in range(22,39,5):a.line([(15,y),(44,y+9)],(74,42,29),2)
        a.rod([(10,20),(47,37)],"wood",5);a.rod([(16,35),(39,48)],"wood",5)
        a.rod([(43,38),(58,48)],"metal",7)
    elif motif == "tube":
        a.poly([(8,42),(43,9),(54,15),(20,51)],p)
        a.oval((9,39,25,55),"brass");a.oval((12,43,21,51),"glass")
        a.rod([(35,22),(45,32)],"brass",5)
    elif motif == "pendulum":
        a.rod([(32,10),(32,45)],p,5);a.ring((24,6,40,18),p,4);a.oval((17,36,48,58),"brass")
        a.line([(22,43),(29,39)],(248,211,126),2)
    elif motif == "pane":
        a.poly([(12,12),(45,9),(53,42),(41,54),(10,48)],"glass")
        a.line([(16,15),(36,49)],(183,236,234),2);a.line([(26,13),(46,42)],(168,223,224),2)
    elif motif == "lens":
        a.rod([(45,40),(57,54)],"brass",6);a.ring((8,8,48,47),"brass",4);a.oval((13,13,43,42),"glass")
        a.line([(18,18),(34,36)],(205,245,244),3)
    elif motif == "prism":
        a.poly([(31,7),(8,47),(52,53)],"glass");a.poly([(31,7),(52,53),(56,30)],"blue")
        a.line([(31,14),(14,43),(45,48)],(214,244,233),2)
    elif motif == "funnel":
        a.poly([(8,14),(53,14),(36,38),(36,54),(27,58),(28,37)],p)
        a.oval((8,9,53,20),p);a.oval((13,12,48,16),"glass")
    elif motif == "hourglass":
        a.poly([(19,12),(45,12),(42,25),(34,31),(42,39),(45,52),(19,52),(22,40),(30,31),(22,25)],"glass")
        a.rod([(14,11),(50,11)],"wood",6);a.rod([(14,53),(50,53)],"wood",6)
        a.poly([(21,49),(32,35),(42,49)],"gold");a.line([(32,22),(32,35)],(238,220,145),2)
    elif motif == "float":
        a.oval((13,12,50,50),"glass")
        for x in (21,32,43):a.line([(x,17),(x-4,37),(x+3,48)],(163,130,77),2)
        for y in (24,34,42):a.line([(18,y),(47,y+3)],(163,130,77),2)
        a.rod([(30,48),(36,57)],"linen",3)
    elif motif == "envelope":
        a.poly([(9,18),(49,11),(56,43),(15,53)],"paper")
        a.line([(12,19),(32,36),(50,14)],(117,85,49),2)
        a.oval((28,32,39,44),"red");a.line([(31,37),(36,37)],(236,154,112))
    elif motif == "quill":
        a.rod([(12,57),(46,13)],"paper",3)
        a.poly([(23,38),(21,22),(39,6),(50,8),(52,22),(35,38)],"bone")
        for i in range(5):a.line([(27+i*4,33-i*4),(29+i*4,20-i*2)],(159,139,108))
    elif motif == "spindle":
        a.rod([(14,55),(46,8)],"wood",4);a.oval((18,30,46,48),p)
        a.hole((30,36,34,40));a.rod([(29,30),(39,20)],"linen",5)
    elif motif == "ladle":
        a.rod([(16,55),(39,25)],"wood",5);a.oval((29,9,53,34),p);a.oval((34,13,48,26),"wood")
    elif motif == "shuttle":
        a.poly([(7,35),(14,19),(46,19),(56,35),(45,48),(17,48)],"wood")
        a.box((18,25,44,40),"linen");a.stripes((18,25,44,40),"linen",True,3)
    elif motif == "broom":
        a.rod([(13,54),(42,13)],"wood",5);a.poly([(33,26),(42,6),(54,13),(57,28),(43,35)],"paper")
        for x in range(39,54,4):a.line([(x,12),(x+2,29)],(121,101,56))
        a.rod([(34,26),(46,34)],"linen",3)
    elif motif == "paddle":
        a.rod([(12,55),(34,29)],"wood",5);a.poly([(28,32),(37,11),(45,8),(56,20),(50,28),(34,39)],p)
        a.line([(36,32),(45,18)],(219,165,93))
    elif motif == "beehive_comb":
        a.poly([(15,13),(36,9),(52,22),(48,47),(29,56),(10,39)],"gold")
        for y in range(20,45,8):
            for x in range(18+(y//8%2)*4,45,9):
                a.poly([(x-3,y),(x-1,y-3),(x+3,y-3),(x+5,y),(x+3,y+4),(x-1,y+4)],"wood")
    elif motif == "gourd":
        a.oval((12,29,50,57),"wood");a.oval((24,14,44,36),"paper");a.rod([(32,17),(36,8)],"plant",4)
        a.line([(19,40),(22,49)],(219,170,86),2)
    elif motif == "moss":
        for i in range(18):
            x=a.rng.randrange(11,52);y=a.rng.randrange(22,49)
            a.oval((x-5,y-4,x+5,y+4),"plant");a.line([(x,y),(x+2,y-5)],(166,185,97))
    elif motif == "catkin":
        for x,y in ((16,18),(32,11),(45,21)):
            a.stem([(32,55),(x,y)])
            a.rod([(x,y),(x+3,y+17)],"paper",7)
            for yy in range(y+2,y+16,4):a.line([(x-1,yy),(x+5,yy+1)],(103,97,51))
    elif motif == "galls":
        a.stem([(16,52),(28,31),(44,13)]);a.leaf(38,19,9,5)
        for x,y in ((22,38),(31,30),(39,35)):a.oval((x-6,y-6,x+6,y+6),"wood")
    elif motif == "berries_branch":
        a.stem([(12,55),(32,28),(47,9)])
        for x,y in ((24,37),(39,21),(43,33)):a.leaf(x,y,8,4)
        for x,y in ((20,30),(31,22),(38,39),(48,25)):a.oval((x-4,y-4,x+4,y+4),a.tint)
    elif motif == "reeds":
        for i in range(5):
            x=15+i*8;y=12+a.rng.randrange(9)
            a.stem([(28+i*2,55),(x,y)])
            if i%2==0:a.rod([(x,y),(x,y+12)],"wood",5)
            a.leaf(x-2,y+22,6,3)
    elif motif == "pods":
        for x,y in ((21,17),(39,11),(48,30)):
            a.stem([(31,55),(x,y+9)]);a.poly([(x,y-7),(x-7,y+3),(x-5,y+14),(x+6,y+12),(x+8,y+1)],"paper")
            a.line([(x,y-1),(x,y+9)],(132,101,60))
    elif motif == "rhizome":
        a.rod([(13,43),(26,32),(40,36),(51,20)],"wood",10)
        for x,y in ((20,36),(35,36),(47,25)):
            a.rod([(x,y),(x-3,y+13)],"wood",3);a.stem([(x,y),(x+1,y-18)]);a.leaf(x+4,y-16,7,3)
    elif motif == "lotus":
        a.stem([(29,55),(31,26)]);a.leaf(39,45,14,6)
        for pts in ([(30,31),(12,20),(24,19),(31,26)],[(32,31),(48,17),(36,20)],[(25,31),(25,11),(33,27)],[(32,30),(35,8),(41,19)]):a.poly(pts,"blue")
        a.oval((25,28,37,36),"gold")
    elif motif == "kelp":
        for i in range(4):
            x=17+i*9;a.stem([(31,55),(x,36),(x+3,12)])
            a.poly([(x,43),(x-6,32),(x+1,23),(x-4,15),(x+3,8),(x+7,24),(x+3,39)],"plant")
    elif motif == "wreath":
        a.ring((10,10,54,54),"plant",7)
        for i in range(8):
            ang=i*math.pi/4;x=round(32+19*math.cos(ang));y=round(32+19*math.sin(ang))
            a.leaf(x,y,7,4)
    elif motif == "fur":
        a.poly([(16,19),(24,12),(31,17),(40,10),(48,21),(52,45),(42,52),(29,48),(17,54),(11,38)],"wool")
        for i in range(24):
            x=a.rng.randrange(19,45);y=a.rng.randrange(23,44)
            a.line([(x,y),(x-2,y+5)],(183,173,156))
    elif motif == "whiskers":
        a.oval((15,32,46,53),"leather")
        for i in range(8):a.rod([(22+i*3,41),(9+i*6,10+a.rng.randrange(12))],"bone",2)
    else:
        return False
    return True


# Motif synonyms refer to real shared forms, never a generic loot placeholder.
MOTIF_ALIASES = {"stone_spindle":"spindle", "chalk":"handle", "seeds":"pods"}
# IDs pin the reviewed object choices even when content is regrouped by source.
# A creature's hard parts and fur can move material families without shifting
# every later icon to a different object's silhouette.
MISC_ITEM_MOTIFS = {}
for _motif, _slugs in {
    "hinge": "bent_door_hinge jammed_door_closer",
    "lock": "rusted_padlock",
    "buckle": "broken_buckle",
    "sickle": "cracked_sickle_head",
    "horseshoe": "worn_horseshoe",
    "spur": "discarded_spur",
    "bracket": "bent_wagon_bracket",
    "ring": "split_iron_ring cow_horn_ring",
    "snuffer": "dented_candle_snuffer",
    "drill": "seized_hand_drill damaged_grinding_crank",
    "shears": "snapped_shears",
    "chain": "broken_chain_link",
    "grate": "rusted_stove_grate",
    "latch": "loose_gate_latch broken_wagon_brake",
    "poker": "bent_fire_poker",
    "handle": "cracked_pan_handle worn_rolling_pin broken_cart_axle loose_shield_grip split_chalk_marker",
    "bell": "discarded_harness_bell",
    "gear": "jammed_clockwork_catch jammed_ratchet_wheel bent_loom_ratchet cracked_orrery_arm",
    "sticks": "split_wagon_spoke worn_tent_peg dogwood_stem_bundle dwarf_willow_twigs discarded_tea_stems",
    "rung": "broken_chair_rung broken_ladder_step snapped_broom_shaft",
    "planks": "cracked_barrel_stave split_crate_lid discarded_reed_mat_offcuts",
    "rake": "splintered_rake",
    "shuttle": "broken_loom_shuttle",
    "paddle": "discarded_paddle",
    "door": "warped_cupboard_door loose_window_shutter",
    "spindle": "cracked_spinning_distaff broken_stone_spindle",
    "ladle": "chipped_wooden_ladle",
    "yoke": "discarded_yoke",
    "frame": "split_tool_rack broken_writing_board",
    "apron": "torn_apron",
    "curtain": "threadbare_curtain",
    "bedroll": "frayed_bedroll",
    "sack": "split_grain_sack split_pillowcase molded_hop_sack spoiled_herb_sachet",
    "sail": "worn_sail_patch",
    "embroidery": "tangled_embroidery",
    "hat": "discarded_cap_lining",
    "banner": "torn_banner",
    "quilt": "ragged_quilt",
    "ribbon": "unraveled_scarf discarded_bandolier_lining worn_laundry_strap cracked_sling_strap",
    "runner": "stained_table_runner",
    "boots": "broken_felt_slipper torn_hunting_gaiter",
    "shirt": "frayed_fishing_smock",
    "blanket": "old_saddle_blanket",
    "net": "torn_mosquito_veil",
    "fur": "rabbit_foot_tuft boar_bristle_patch grouse_down_tuft fox_tail_tuft badger_guard_hairs muskrat_fur_clump gull_wing_down sheep_wool_locks",
    "feathers": "turkey_quill_fan heron_pinion_quills chicken_quill_bundle",
    "whiskers": "otter_whisker_bundle seal_whisker_pad",
    "belt": "split_harness_strap discarded_bridle cracked_belt",
    "sole": "worn_boot_sole",
    "scabbard": "broken_scabbard",
    "hide": "cracked_saddle_flap",
    "bag": "torn_leather_pouch broken_satchel_flap",
    "bellows": "old_bellows_skin broken_bellows_valve",
    "gloves": "broken_glove",
    "quiver": "split_quiver_seam",
    "armor": "worn_knee_guard",
    "muzzle": "discarded_muzzle",
    "drum_head": "worn_drum_head",
    "flask": "split_water_bag",
    "sinew": "stalker_tendon_knot",
    "jar": "chipped_crock cracked_honey_jar chipped_salt_cellar cracked_apothecary_jar",
    "tile": "broken_roof_tile broken_kiln_spacer cracked_slate_shingle broken_mosaic_piece loose_gravel_paver",
    "pot": "cracked_jug chipped_chamber_pot broken_flower_pot discarded_crucible split_pine_pitch_pot",
    "plateware": "split_butter_dish cracked_soap_dish split_baking_stone",
    "ink": "shattered_inkpot",
    "lamp": "broken_oil_lamp",
    "bowl": "split_tea_bowl",
    "millstone": "cracked_fermentation_weight chipped_mill_fragment broken_grindstone_rim chipped_sandstone_disc",
    "pipe": "broken_drain_pipe",
    "mortar": "chipped_mortar_bowl",
    "pane": "clouded_window_pane",
    "bottle_neck": "cracked_bottle_neck",
    "lens_only": "broken_spectacle_lens",
    "beads": "chipped_glass_bead",
    "vial": "shattered_perfume_vial",
    "tube": "split_lamp_chimney shattered_measuring_tube split_pump_piston damaged_sighting_tube",
    "hourglass": "broken_hourglass_bulb",
    "mirror": "cracked_mirror_edge",
    "stopper": "chipped_glass_stopper",
    "lantern": "broken_lantern_globe broken_hand_lantern",
    "prism": "clouded_prism",
    "funnel": "split_glass_funnel",
    "seal": "broken_seal_stamp",
    "cup": "chipped_drinking_glass broken_soapstone_cup",
    "float": "cracked_fishing_float",
    "pendant": "broken_glass_pendant",
    "book": "waterlogged_ledger loose_book_binding torn_song_folio old_tax_register split_notebook_cover waterstained_almanac",
    "map": "torn_map_case",
    "envelope": "discarded_letter_bundle broken_seal_envelope",
    "scroll": "molded_scroll_tube frayed_document_roll tattered_charter_copy",
    "pages": "faded_market_notice discarded_account_slip ruined_recipe_leaf",
    "card": "split_wax_tablet discarded_shipping_label",
    "brick": "worn_whetstone cracked_hearth_brick fractured_mortar_block cracked_door_sill",
    "ore": "split_stone_weight chipped_plumb_bob",
    "pestle": "chipped_stone_pestle",
    "wedge": "split_quarry_wedge",
    "pebble": "worn_grinding_pebble",
    "compass": "damaged_survey_compass",
    "reel": "broken_spinning_reel",
    "scale_balance": "cracked_balance_scale",
    "chest": "seized_music_box",
    "trap": "damaged_spring_trap",
    "crossbow_trigger": "broken_crossbow_trigger",
    "pendulum": "seized_clock_pendulum",
    "key": "broken_winding_key",
    "pods": "empty_seed_husk_bundle mildewed_grain_chaff beech_nut_cup dried_teasel_head burdock_burr_cluster milkweed_pod flax_seed_capsule mountain_avens_seedhead",
    "bulb": "dried_onion_skins marsh_amber_bulb",
    "shell": "cracked_nut_shells",
    "dried_food": "old_apple_pressings dried_citrus_peel",
    "powder": "spent_malt_heap old_spice_sweepings",
    "beehive_comb": "broken_beeswax_comb",
    "gourd": "dried_gourd_rind",
    "cloth": "spoiled_flax_bundle",
    "wreath": "crumbled_herb_wreath",
    "leaves": "spent_dye_leaves juniper_bough bog_myrtle_branch marsh_mallow_stems",
    "cone": "resinous_pine_cone alder_cone_cluster",
    "catkin": "birch_catkin_cluster hazel_catkin_spray cotton_grass_tuft",
    "galls": "oak_gall_cluster",
    "sap": "spruce_pitch_knot",
    "bark": "willow_bark_curl",
    "herbs": "silverleaf_sprig sweet_clover_tops moonmint_sprig rock_samphire_stems frost_sage_branch",
    "flower": "ghost_orchid_stem mullein_flower_spike goldenrod_spray saffron_crocus_tuft sea_lavender_spray crimson_stonecrop_crown",
    "roots": "amberroot_crown chicory_root_crown sedge_root_mat sweet_flag_root alpine_sorrel_root",
    "berries_branch": "rose_hip_branch crowberry_stem_mat",
    "rhizome": "sunspice_rhizome water_iris_rhizome",
    "reeds": "cattail_seed_head rush_pith_bundle star_reed_tuft",
    "moss": "peat_moss_clump reindeer_lichen_mat",
    "lotus": "blue_lotus_stalk",
    "kelp": "bladderwrack_holdfast pearl_kelp_knot",
    "antler": "deer_antler_tip",
    "teeth": "elk_tooth_row wolf_fang_pair beaver_incisor_pair",
    "hoof": "moose_hoof_plate",
    "horn": "goat_horn_sheath grazer_horn_chip",
    "claw": "bear_claw_sheath",
    "carapace": "crawler_carapace_plate",
}.items():
    for _slug in _slugs.split():
        if _slug in MISC_ITEM_MOTIFS:
            raise ValueError("Duplicate miscellaneous art choice: " + _slug)
        MISC_ITEM_MOTIFS[_slug] = _motif
COMPONENT_MOTIFS = {
    "wood_pieces":"planks", "metal_scraps":"scraps", "nuts_and_bolts":"bolts",
    "tool_handles":"handle", "plant_scraps":"leaves", "cloth_scraps":"cloth",
    "leather_scraps":"hide", "bone_chips":"bones", "ceramic_shards":"tile",
    "glass_shards":"pane", "copper_wire":"wire", "resin_lumps":"gem",
    "mineral_grit":"ore", "tempered_spring":"spring", "fine_gear":"gear",
    "clear_crystal":"prism", "aromatic_oil":"vial", "tough_fiber":"rope",
    "silver_filament":"wire",
}

CRAFTED_MOTIFS = {
    "iron_tool_blank":"ingot", "iron_adze":"adze", "salvage_driver":"driver",
    "segmented_armor_plates":"scale", "metal_frame_saw":"saw",
    "wooden_dowels":"sticks", "planed_board":"planks", "bentwood_frame":"frame",
    "fitted_grip":"handle", "carpenter_brace":"drill", "wood_plane":"plane",
    "laminated_bow_limbs":"bow", "levered_nutcracker":"pliers",
    "spun_yarn":"spool", "felt_padding":"quilt", "reinforced_cloth":"cloth",
    "padded_coif":"hood", "quilted_jerkin":"shirt", "reinforced_gaiters":"boots",
    "leather_lace":"ribbon", "hide_glue":"jar", "leather_grip_wrap":"ribbon",
    "hardened_leather":"hide", "oiled_leather":"hide", "fur_lined_hood":"hood",
    "mortar_mix":"powder", "grinding_slab":"plate", "flint_hide_scraper":"knife",
    "quarry_sledge":"hammer", "basalt_head_mace":"mace", "crystal_edge_scalpel":"knife",
    "kiln_grog":"scraps", "tempered_clay":"ore", "ceramic_filter_media":"scraps",
    "hardened_ceramic_edge":"knife", "kiln_piercing_spike":"needle",
    "porous_filter_candle":"handle", "malted_grain":"pods",
    "botanical_brewing_sachet":"sack", "soured_root_pickle":"jar",
    "filtered_malt_culture":"jar", "bread_dough":"dough", "sourdough_starter":"jar",
    "unleavened_flatbread":"bread", "twice_baked_rusk":"bread",
    "root_dumplings":"dough", "steam_raised_grain_bun":"bread",
    "seared_game_portions":"meat", "braised_meat":"meal", "potted_meat":"jar",
    "fruit_preserve":"jar", "cabbage_ferment":"jar", "wilted_greens":"leaves",
    "berry_reduction":"bowl", "travel_stew_concentrate":"dried_food",
    "grain_binder_paste":"salve", "cattail_starch":"flour", "flax_meal":"flour",
    "roasted_grain_crumble":"powder", "barley_meal":"flour", "cornmeal":"flour",
    "mushroom_powder":"flour",
    "bean_crispbread":"bread",
    "cured_leather_panel":"hide", "riveted_work_gloves":"gloves",
    "minced_game":"meat", "rendered_tallow":"fat", "horn_laminate":"horn",
    "carved_bone_barb":"hook", "bone_marrow_scoop":"ladle", "hide_fleshing_beam":"planks",
    "sinew_stripper":"shears", "smoked_offal_sausage":"dried_food",
    "copper_spinner_blade":"plate", "float_rig":"float", "jointed_fishing_rod":"handle",
    "spring_tension_fishing_rod":"handle", "split_fish_fillets":"fillet",
    "rack_dried_fish":"fish", "vinegar_preserved_fish":"jar",
    "compost_blend":"moss", "seed_cleaning_screen":"net", "plant_fiber_pulp":"moss",
    "garden_dibber":"handle", "soil_turning_fork":"rake", "pressed_plant_binder":"plate",
    "wool_roving":"fur", "horn_button_set":"beads", "bristle_brush":"brush",
    "pasture_fiber_bundle":"sticks", "fur_felt":"fur", "tallow_dressing":"salve",
    "wool_lined_mitts":"gloves", "horn_shod_staff":"handle", "feather_fletching":"feathers",
    "bone_arrow_point":"knife", "shaft_bundle":"sticks", "fur_grip_pad":"fur",
    "weighted_hide_sling":"rope", "antler_throwing_dart":"spear", "tracker_skinning_set":"knife",
    "timber_wedge":"knife", "pitch_binder":"jar", "hardwood_blank":"planks",
    "bark_felt":"cloth", "splitting_maul":"mallet", "wood_boring_auger":"drill",
    "loggers_mattock":"pick", "washed_ore_fragments":"ore", "polishing_slurry":"bowl",
    "sorted_crystal_faces":"prism", "copper_granules":"scraps", "ore_sifting_screen":"net",
    "iron_splitting_wedges":"knife", "hardened_ore_auger":"drill",
    "crystal_burnisher":"handle", "clean_dressing_pad":"cloth", "bitter_herbal_extract":"vial",
    "marsh_resin_balm":"salve", "filtered_herb_concentrate":"vial",
    "orchid_lotus_essence":"vial", "fitted_splint_frame":"frame", "carbon_pigment":"powder",
    "polished_crystal_lens":"lens_only", "lens_mounted_needle":"needle",
}
CRAFTED_MOTIFS.update({
    "segmented_armor_plates":"plate_set", "iron_lamellar_vest":"armor_vest",
    "metal_frame_saw":"frame_saw", "tensioned_timber_saw":"frame_saw",
    "laminated_bow_limbs":"bow_limbs", "bentwood_frame":"bent_frame",
    "fitted_splint_frame":"splint_frame", "claw_hammer":"claw_hammer",
    "linen_panel":"panel", "canvas_panel":"panel", "reinforced_cloth":"panel",
    "cured_leather_panel":"leather_panel", "hardened_leather":"leather_panel",
    "oiled_leather":"leather_panel", "felt_padding":"felt", "fur_felt":"felt",
    "bark_felt":"felt", "recycled_rag_paper":"pages",
    "pressed_pulp_board":"paper_panel", "sealed_paper_panel":"paper_panel",
    "horn_faced_buckler":"buckler", "layered_hunter_bracers":"bracers",
    "reinforced_gaiters":"gaiters", "wool_roving":"roving",
    "plant_fiber_pulp":"pulp", "porous_filter_candle":"filter_candle",
    "clean_dressing_pad":"dressing_pad", "lens_mounted_needle":"needle_lens",
    "jointed_fishing_rod":"fishing_rod", "spring_tension_fishing_rod":"fishing_rod",
    "float_rig":"float_rig", "copper_spinner_blade":"spinner_blade",
    "articulated_spinner_lure":"spinner", "barbed_fishing_trident":"trident",
    "weighted_hide_sling":"sling", "antler_throwing_dart":"dart",
    "bone_arrow_point":"arrow_points", "tracker_skinning_set":"tool_roll",
    "timber_wedge":"wedge", "iron_splitting_wedges":"wedge",
    "stone_blade_blank":"blade_blank", "wood_boring_auger":"auger",
    "hardened_ore_auger":"auger", "ore_sifting_screen":"screen",
    "seed_cleaning_screen":"screen", "soil_turning_fork":"fork",
    "horn_shod_staff":"horn_staff", "root_dumplings":"dumplings",
    "savory_hand_pie":"pie", "smoked_offal_sausage":"sausage",
    "root_broth":"broth", "bone_stock":"broth", "malted_grain":"grains",
    "carbon_pigment":"powder_bowl", "silverleaf_powder":"powder_bowl",
    "mortar_mix":"powder_bowl", "abrasive_powder":"powder_bowl",
    "botanical_brewing_sachet":"herb_sachet",
    "roasted_grain_crumble":"grains", "minced_game":"minced_meat",
    "rendered_tallow":"tallow", "potted_meat":"preserve_jar",
    "fruit_preserve":"preserve_jar", "cabbage_ferment":"preserve_jar",
    "soured_root_pickle":"preserve_jar", "vinegar_preserved_fish":"preserve_jar",
    "grain_table_beer":"drink_bottle", "brewing_wort":"drink_bottle",
    "grain_vinegar":"drink_bottle", "coastal_kelp_vinegar":"drink_bottle",
    "malt_tonic_drink":"drink_bottle", "spiced_grain_cordial":"drink_bottle",
    "bitter_herbal_extract":"drink_bottle", "filtered_herb_concentrate":"drink_bottle",
    "orchid_lotus_essence":"drink_bottle", "moonmint_infusion":"infusion",
    "frost_sage_brew":"infusion",
    "wool_lined_mitts":"mittens",
})


def crafted_motif(row: dict, recipe: dict) -> str:
    slug=row["id"].split(":",1)[1]
    if slug in CRAFTED_MOTIFS:return CRAFTED_MOTIFS[slug]
    name=row["name"].lower()
    # Specific object nouns precede material names and utility metadata.
    nouns=(("quiver","quiver"),("scabbard","scabbard"),("buckler","shield"),("shield","shield"),
        ("bow","bow"),("spear","spear"),("sword","sword"),("saw","saw"),("knife","knife"),
        ("scalpel","knife"),("chisel","chisel"),("pick","pick"),("hammer","hammer"),
        ("mallet","mallet"),("axe","axe"),("adze","adze"),("rake","rake"),("hoe","hoe"),
        ("shovel","shovel"),("spade","shovel"),("sickle","sickle"),("cleaver","cleaver"),
        ("trident","spear"),("hook","hook"),("rod","handle"),("awl","awl"),("needle","needle"),("shears","shears"),
        ("tongs","tongs"),("pestle","pestle"),("thimble","thimble"),("coil","coil"),
        ("mould","mould"),("crucible","jar"),("bead","beads"),("lure","fish"),
        ("hinge","hinge"),("rivet","rivets"),("wire","wire"),("spring","spring"),
        ("gear","gear"),("sheet","plate"),("blank","knife"),("handle","handle"),
        ("grip","handle"),("dowel","sticks"),("board","planks"),("panel","cloth"),
        ("thread","spool"),("cord","rope"),("line","rope"),("net","net"),("sack","sack"),
        ("gloves","gloves"),("boots","boots"),("hood","hood"),("coif","hood"),("cap","hat"),
        ("vest","armor"),("cuirass","armor"),("jerkin","shirt"),("coat","coat"),
        ("trousers","pants"),("leggings","pants"),("gaiters","boots"),("belt","belt"),
        ("bread","bread"),("loaf","bread"),("cake","bread"),("hardtack","bread"),("bun","bread"),
        ("pie","pie"),("dough","dough"),("flour","flour"),("porridge","meal"),("soup","meal"),
        ("broth","pot"),("stock","pot"),("stew","meal"),("vinegar","bottle"),
        ("infusion","cup"),("beer","bottle"),("brew","bottle"),("drink","cup"),("cordial","vial"),
        ("tonic","vial"),("wort","bottle"),("medicine","medicine"),("salve","salve"),
        ("powder","powder"),("paste","salve"),("oil","vial"),("glue","jar"),
        ("crystal","prism"),("grit","ore"),("chips","bones"),("bark","bark"),
        ("seed","pods"),("cutting","sticks"),("bundle","sticks"),("quill","quill"),
        ("ink","ink"),("book","book"),("paper","pages"),("scroll","scroll"),("map","map"))
    for noun,motif in nouns:
        if any(word in {noun,noun+"s",noun+"es"} for word in name.split()):return motif
    if row.get("category")=="armor":
        return {"head":"helmet","body":"armor","hands":"gloves","legs":"pants"}[row["equip_slot"]]
    raise ValueError(f"Craft needs an authored physical motif: {row['id']} ({recipe['profession']})")


def palette_for_component(slug: str) -> str:
    for token, material in (("silver","silver"),("copper","copper"),("crystal","glass"),("glass","glass"),
                            ("ceramic","ceramic"),("bone","bone"),("leather","leather"),("cloth","linen"),
                            ("plant","plant"),("resin","gold"),("mineral","stone"),("fiber","linen"),
                            ("wood","wood"),("handles","wood"),("oil","glass")):
        if token in slug: return material
    return "steel" if slug in {"tempered_spring","fine_gear"} else "metal"


def finish(a: Art) -> Image.Image:
    """Object-specific wear: holes in torn fabric, chips, cracks and patina."""
    name=a.name
    alpha=a.image.getchannel("A")
    layer=Image.new("RGBA",(SIZE,SIZE),CLEAR)
    ink=ImageDraw.Draw(layer)
    if any(word in name for word in ("cracked","split","fractured","shattered")):
        x=a.rng.randrange(25,38);y=a.rng.randrange(15,25)
        ink.line([(x,y),(x-4,y+7),(x+1,y+12),(x-5,y+23)],fill=(35,30,27,255),width=2)
        ink.line([(x-4,y+7),(x-10,y+9)],fill=(35,30,27,255),width=1)
    if any(word in name for word in ("rusted","seized","jammed","old","worn")) and a.family in {"metal","mixed"}:
        for i in range(18):
            x=a.rng.randrange(14,52);y=a.rng.randrange(13,52)
            ink.rectangle((x,y,x+1,y+1),fill=a.rng.choice(((132,67,37,255),(185,94,44,255),(89,72,52,255))))
    # Restrict wear marks to the existing object, including thin chains/needles.
    layer.putalpha(Image.composite(layer.getchannel("A"),Image.new("L",(SIZE,SIZE),0),alpha))
    a.image.alpha_composite(layer)
    d=ImageDraw.Draw(a.image)
    if any(word in name for word in ("torn","ragged","threadbare","frayed","mildewed","broken","chipped","snapped")):
        occupied=[(x,y) for y in range(18,49) for x in range(13,51) if a.image.getpixel((x,y))[3]==255]
        if occupied:
            x,y=a.rng.choice(occupied)
            if a.family in {"cloth","leather","paper"}:
                d.polygon([(x-3,y-1),(x+2,y-2),(x+4,y+1),(x+1,y+4),(x-3,y+3)],fill=CLEAR)
            else:
                # A chip follows a physical object's nearest horizontal edge.
                while x>2 and a.image.getpixel((x-1,y))[3]==255:x-=1
                d.polygon([(x-2,y-2),(x+4,y),(x+1,y+4),(x-2,y+4)],fill=CLEAR)
    if a.family=="paper":
        # Distinct handwritten annotations describe separate documents.
        for i in range(a.rng.randrange(2,5)):
            x=a.rng.randrange(19,36);y=a.rng.randrange(22,45)
            width=a.rng.randrange(4,12)
            if all(a.image.getpixel((xx,y))[3] for xx in range(x,min(x+width,54))):
                d.line([(x,y),(x+width,y)],fill=(106,76,45,255))
    return a.image


def render(row: dict, family: str, motif: str) -> Image.Image:
    physical_family={"mixed":"metal","provisions":"plant"}.get(family,family)
    if physical_family not in PALETTES:physical_family="wood"
    a=Art(row,physical_family)
    a.family=family
    crafted=row["asset"].startswith("craft_")
    if crafted:
        if row.get("category") in {"tool","weapon"} and motif in {"axe","saw","pick","adze","hoe","shovel","hammer","hook","sickle","spear"}:
            a.primary="stone" if family=="stone" and "iron" not in a.name else "iron"
        elif motif in {"pot","jar","bowl","cup","salve"}:a.primary="ceramic"
        elif motif in {"bottle","vial","flask","prism","lens_only"}:a.primary="glass"
        elif motif=="wedge":a.primary="iron" if "iron" in a.name else "wood"
        elif motif=="powder_bowl":
            a.primary="iron" if "carbon" in a.name else "plant" if "silverleaf" in a.name else "stone"
        elif motif=="felt":a.primary="wool"
        elif motif=="panel":a.primary="linen" if "linen" in a.name else "cloth"
        elif motif in {"ribbon","rope","spool"}:a.primary="leather" if family=="leather" else "linen"
    if not crafted and row.get("category") in {"tool","weapon"} and family in {"cloth","leather","food","glass","plant","paper","fish"}:
        if motif in {"handle","rod","bow","staff"}:a.primary="wood"
        elif motif in {"needle","awl"}:a.primary="bone" if "horn" in a.name or "bone" in a.name else "metal"
        elif motif in {"pestle","hammer","knife","rake","sickle","shovel","hoe"}:a.primary="stone"
    if "horn_button" in row["id"]:a.primary="bone"
    if "ghost_orchid" in row["id"]:a.tint="bone"
    elif "goldenrod" in row["id"] or "mullein" in row["id"] or "saffron" in row["id"]:a.tint="gold"
    elif "crimson" in row["id"] or "rose_hip" in row["id"]:a.tint="red"
    elif "crowberry" in row["id"]:a.tint="purple"
    elif "cotton" in row["id"]:a.primary="bone"
    if crafted and "crystal_edge_scalpel" in row["id"]:a.primary="glass"
    if crafted and motif=="pestle" and family=="food":a.primary="stone"
    if crafted and motif=="gloves":a.primary="leather"
    motif=MOTIF_ALIASES.get(motif,motif)
    if not draw_special(a,motif):draw_object(a,motif)
    if crafted:
        if "quilted" in a.name:
            for y in range(25,50,6):a.line([(23,y),(41,y)],PALETTES[a.primary][2])
            for x in (25,31,37):a.line([(x,25),(x,49)],PALETTES[a.primary][2])
        elif "plated" in a.name and motif=="gloves":
            for dx,dy in ((0,0),(23,8)):
                a.poly([(13+dx,30+dy),(24+dx,32+dy),(24+dx,43+dy),(12+dx,42+dy)],"iron")
                a.rivet(17+dx,37+dy)
        elif "riveted" in a.name and motif=="gloves":
            for x,y in ((15,35),(20,39),(38,43),(44,47)):a.rivet(x,y)
        elif "folding" in a.name and motif=="spear":
            a.rod([(23,44),(28,37)],"iron",7);a.rivet(25,40)
        elif motif=="meal":
            if "mushroom" in a.name:
                for x,y in ((21,31),(36,30),(32,40)):
                    a.rod([(x,y),(x,y+4)],"bone",2);a.oval((x-4,y-3,x+4,y+1),"wood")
            elif "braised" in a.name:
                for x,y in ((21,29),(33,38),(43,32)):a.poly([(x-4,y),(x,y-4),(x+6,y),(x+3,y+5)],"food")
        elif "berry_reduction" in row["id"]:
            a.oval((15,21,48,28),"purple");a.line([(20,23),(35,24)],(220,140,198),2)
        elif motif=="flour":
            # Labels depict the milled source rather than interchangeable marks.
            if "bean" in a.name:a.oval((25,34,38,41),"food")
            elif "mushroom" in a.name:
                a.rod([(31,35),(31,44)],"wood",3);a.oval((25,30,39,37),"wood")
            elif "corn" in a.name:
                a.oval((28,31,35,44),"gold");a.stem([(27,43),(28,36)])
            elif "root" in a.name or "starch" in a.name:
                a.oval((27,35,36,42),"bone");a.stem([(31,36),(34,31)])
    return finish(a)


def contact_sheet(specs: list[tuple[dict,str,str]], path: Path) -> None:
    columns=10;cell_w=144;cell_h=104
    canvas=Image.new("RGB",(columns*cell_w,math.ceil(len(specs)/columns)*cell_h),(26,29,33))
    d=ImageDraw.Draw(canvas)
    try:font=ImageFont.truetype("DejaVuSans.ttf",10)
    except OSError:font=ImageFont.load_default()
    for i,(row,family,motif) in enumerate(specs):
        x=(i%columns)*cell_w;y=(i//columns)*cell_h
        im=Image.open(OUT/(row["asset"]+".png")).convert("RGBA")
        canvas.paste(im,(x+40,y+3),im)
        name=row["name"]
        words=name.split();lines=[""]
        for word in words:
            if len(lines[-1])+len(word)>22:lines.append(word)
            else:lines[-1]+=(" " if lines[-1] else "")+word
        for j,line in enumerate(lines[:2]):d.text((x+4,y+69+j*12),line,fill=(223,223,212),font=font)
        d.text((x+4,y+94),f"{family} / {motif}",fill=(142,156,165),font=font)
    path.parent.mkdir(parents=True,exist_ok=True)
    canvas.save(path,optimize=True)


def register_resource_visuals(manifest: dict, by_id: dict) -> int:
    path=ROOT/"worldseed"/"assets"/"visuals.json"
    visuals=json.loads(path.read_text())
    existing={r["id"] for r in json.loads((DATA/"resources.json").read_text())}
    count=0
    for raw in manifest["misc"]:
        if raw.get("source")!="wild":continue
        iid=raw["item_id"];rid="core:salvage_patch_"+iid.split(":",1)[1]
        if rid not in existing:continue
        visuals.setdefault("resources",{})[rid]="assets/sprites/items/"+by_id[iid]["asset"]+".png"
        count+=1
    path.write_text(json.dumps(visuals,indent=2)+"\n")
    return count


def expansion_specs(manifest: dict, by_id: dict) -> list[tuple[dict,str,str]]:
    art_path=ROOT/"tools"/"salvage_sprite_specs.json"
    authored=json.loads(art_path.read_text())["items"] if art_path.exists() else {}
    specs=[]
    for raw in manifest["misc"]:
        family=raw["art_family"]
        if authored:
            spec=authored[raw["item_id"]]
            if spec["family"]!=family:raise ValueError("Art material family changed: "+raw["item_id"])
            specs.append((by_id[raw["item_id"]],family,spec["motif"]))
            continue
        slug=raw["item_id"].split(":",1)[1]
        if slug not in MISC_ITEM_MOTIFS:raise ValueError("Misc item needs an authored physical motif: "+raw["item_id"])
        specs.append((by_id[raw["item_id"]],family,MISC_ITEM_MOTIFS[slug]))
    for iid in manifest["components"]+manifest["rare_components"]:
        slug=iid.split(":",1)[1]
        if authored:
            spec=authored[iid];specs.append((by_id[iid],spec["family"],spec["motif"]))
        else:specs.append((by_id[iid],palette_for_component(slug),COMPONENT_MOTIFS[slug]))
    covered={row["id"] for row,_,_ in specs}
    for raw in manifest["recipes"]:
        iid=raw["output_item"]
        if iid in covered or raw["art_family"]=="existing":continue
        motif=authored[iid]["motif"] if authored else crafted_motif(by_id[iid],raw)
        specs.append((by_id[iid],raw["art_family"],motif))
        covered.add(iid)
    return specs


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contact-sheet",type=Path,default=Path("/workspace/scratch/salvage_expansion_contact.png"))
    parser.add_argument("--register-resources",action="store_true")
    args=parser.parse_args()
    manifest=json.loads((DATA/"crafting_expansion.json").read_text())
    by_id={r["id"]:r for r in json.loads((DATA/"items.json").read_text())}
    specs=expansion_specs(manifest,by_id)
    OUT.mkdir(parents=True,exist_ok=True)
    hashes=set()
    for row,family,motif in specs:
        image=render(row,family,motif)
        path=OUT/(row["asset"]+".png")
        image.save(path,optimize=True)
        digest=hashlib.sha256(image.tobytes()).digest()
        if digest in hashes:raise ValueError("Duplicate icon: "+row["id"])
        hashes.add(digest)
    contact_sheet(specs,args.contact_sheet)
    print(f"Authored {len(specs)} unique 64px RGBA item sprites; contact sheet: {args.contact_sheet}")
    if args.register_resources:print(f"Registered {register_resource_visuals(manifest,by_id)} harvestable plant visuals")
    return 0


if __name__=="__main__":raise SystemExit(main())
