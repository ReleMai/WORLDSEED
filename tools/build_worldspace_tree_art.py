"""Deterministic, source-controlled 2.5D oak/pine layered tree artwork.

Usage: python -m tools.build_worldspace_tree_art --output-dir worldseed/assets/sprites/worldspace/trees
The builder is source provenance; output RGBA PNGs are checked into WORLDSEED.
PIL is an asset build-time dependency only, never a runtime requirement.
"""
from __future__ import annotations

import argparse
from base64 import b85encode
from io import BytesIO
from zipfile import ZipFile,ZipInfo,ZIP_DEFLATED
from hashlib import sha256
import json
from math import cos, sin, pi
from pathlib import Path
from random import Random
from PIL import Image, ImageDraw, ImageFilter

SIZE = 384
SCHEMA_VERSION = 1
PALETTES = {
    ('oak','summer'): ('#15352a','#27543a','#49754a','#87a165','#c2b57f'),
    ('oak','spring'): ('#24533d','#3e8156','#77a66d','#b4c983','#d3cb8c'),
    ('oak','autumn'): ('#66362a','#96502f','#c1773a','#dea953','#e6c77a'),
    ('oak','winter'): ('#45505a','#656d73','#939b9f','#c7c9ca','#eff2ee'),
    ('pine','summer'): ('#142e2e','#23433e','#315d4c','#4c7965','#86a17a'),
    ('pine','spring'): ('#213d35','#315b42','#578367','#85ac8c','#b0c1a0'),
    ('pine','autumn'): ('#223830','#3c5440','#5b7750','#80925c','#b49d66'),
    ('pine','winter'): ('#26363b','#394d51','#65767b','#9caead','#e5eff0'),
}

def rgb(value):
    value=value.lstrip('#')
    return tuple(int(value[k:k+2],16) for k in (0,2,4))

def col(rgb3,alpha=255):
    return (*rgb3,alpha)

def mix(a,b,t):
    return tuple(round(a[i]*(1-t)+b[i]*t) for i in range(3))

def oval(draw,x,y,rx,ry,color):
    draw.ellipse((round(x-rx),round(y-ry),round(x+rx),round(y+ry)),fill=color)

def branch_path(d,p1,p2,thickness,main_color,highlight):
    d.line((p1,p2),fill=main_color,width=thickness,joint='curve')
    d.line(((p1[0]-thickness//5,p1[1]),(p2[0]-thickness//5,p2[1])),fill=highlight,width=max(1,thickness//7))

def trunk(species):
    im=Image.new('RGBA',(SIZE,SIZE))
    d=ImageDraw.Draw(im)
    rng=Random(4021 if species=='oak' else 8091)
    dark=rgb('#352b25' if species=='oak' else '#342e29')
    bark=rgb('#675041' if species=='oak' else '#605349')
    bright=rgb('#a08463' if species=='oak' else '#938370')
    # Ground-foot anchor at (192, 369), reflected in manifest.
    foot=369
    w=47 if species=='oak' else 32
    top=85 if species=='oak' else 54
    polygon=[(192-w//2,foot-7),(189-w*.43,221),(188-w*.40,top),
             (199+w*.30,top+10),(199+w*.33,230),(192+w//2,foot-8),
             (201,foot-4),(192,foot)]
    d.polygon(polygon,fill=col(dark))
    d.polygon([(186-w*.27,foot-9),(181-w*.23,240),(187-w*.24,top+8),
               (196,top+11),(198,230),(193,foot-5)],fill=col(bark))
    # Roots spread but collision stays at original cell and tree center.
    for side in (-1,1):
        for j in range(3):
            ex=192+side*(35+20*j)
            ey=foot-7+rng.randint(-5,3)
            points=[(192+side*(w//4),foot-24),(192+side*(26+7*j),foot-12),(ex,ey)]
            d.line(points,fill=col(dark),width=max(3,10-j*2),joint='curve')
            d.line(points,fill=col(bark,230),width=max(2,5-j),joint='curve')
    # Characteristically spreading oak branches versus whorled pine branches.
    if species=='oak':
        for k in range(9):
            y=120+k*19
            spread=rng.randint(33,85) * (1 if k%2 else -1)
            bwidth=max(4,17-k)
            branch_path(d,(190+(2 if k%2 else -3),y+40),(192+spread,y-44),
                        bwidth,col(dark),col(bright,160))
    else:
        for k in range(11):
            y=90+k*20
            spread=(25+k*4)*(1 if k%2 else -1)
            branch_path(d,(192,y+15),(192+spread,y-19),6,col(dark),col(bark,180))
    # Small bark scars and fissures create recognizable grain at high dpi.
    for k in range(98):
        y=rng.randint(top+18,foot-19)
        center=192 + round(4*sin(y*.063))
        x=center+rng.randint(-w//3,w//3)
        h=rng.randint(5,19)
        ink=col(dark, rng.randint(85,180)) if k%3 else col(bright,rng.randint(60,150))
        d.line((x,y,x+rng.randint(-4,4),min(foot-12,y+h)),fill=ink,width=rng.randint(1,3))
    # Pine tree trunk has sparse twig outlines in winter.
    return im

def crown_oak(season):
    rng=Random(132485 + ['spring','summer','autumn','winter'].index(season)*913)
    im=Image.new('RGBA',(SIZE,SIZE))
    d=ImageDraw.Draw(im)
    p=[rgb(s) for s in PALETTES[('oak',season)]]
    # A set of overlapping coherent foliage masses with an irregular perimeter.
    masses=[(194,154,121,71),(126,170,78,78),(261,172,80,73),
            (184,99,89,79),(105,118,66,58),(284,120,60,60),
            (148,215,76,55),(239,218,79,56)]
    for i,(x,y,rx,ry) in enumerate(masses):
        oval(d,x+4,y+6,rx,ry,col(p[0],210))
        oval(d,x-3,y-3,max(4,rx-9),max(4,ry-10),col(p[1],238))
    # Individually edged leaf clusters. Shadows gather toward bottom, sunlit tips toward top-left.
    for k in range(1260):
        x=rng.randint(24,361);y=rng.randint(30,275)
        if im.getpixel((x,y))[3] < 90: continue
        tone=0 if y>213 and rng.random()<.45 else rng.choices([1,2,3,4],[14,35,35,16])[0]
        rad=rng.randint(2,9)
        leaf_tint=mix(p[tone],p[min(4,tone+1)],rng.random()*.35)
        oval(d,x,y,rad*1.1,rad*.55,col(leaf_tint,rng.randint(165,248)))
        if k%8==0:
            d.line((x-rad*.8,y-1,x+rad*.85,y-2),fill=col(p[4],rng.randint(65,165)),width=1)
    if season=='winter':
        # Bare bough network under a thin snow-dusted crown, not a green summer tree.
        snow=col((225,232,232),194)
        for k in range(48):
            x=rng.randint(80,302);y=rng.randint(54,242)
            if im.getpixel((x,y))[3]<60: continue
            oval(d,x,y, rng.randint(3,10),rng.randint(1,4),snow)
    return im

def crown_pine(season):
    rng=Random(71244+['spring','summer','autumn','winter'].index(season)*131)
    im=Image.new('RGBA',(SIZE,SIZE))
    d=ImageDraw.Draw(im)
    p=[rgb(s) for s in PALETTES[('pine',season)]]
    # Concentric north-up evergreen branch whorls make pine silhouette distinct.
    for level in range(7):
        cy=263-level*32
        half=max(25,141-level*17)
        tip=cy-(26+level*2)
        dark=col(p[0],252)
        mid=col(p[1],255)
        sun=col(p[min(4,2+int(level/3))],230)
        d.polygon([(192,tip-25),(192-half,cy+22),(154,cy-4),(117,cy+19),
                   (190,cy+35),(265,cy+17),(229,cy-3),(192+half,cy+17)],fill=dark)
        for side in (-1,1):
            for k in range(24):
                dx=side*rng.randint(5,half)
                y=cy+rng.randint(-22,24)
                if not 2<=192+dx<SIZE-2:continue
                d.line((192+dx,y,192+dx+side*rng.randint(7,20),y+rng.randint(0,9)),
                       fill=mid,width=rng.randint(2,5))
                if k%3==0:
                    d.line((192+dx,y-3,192+dx+side*13,y-8),fill=sun,width=2)
    if season=='winter':
        # Snow rests on upper edges but lower needle silhouette stays evergreen.
        for k in range(75):
            x=rng.randint(67,319);y=rng.randint(40,268)
            if im.getpixel((x,y))[3]<80:continue
            d.line((x,y,x+rng.randint(5,14),y+1),fill=(226,235,239,rng.randint(190,250)),width=rng.randint(2,4))
    return im

def shadow(species):
    im=Image.new('RGBA',(SIZE,SIZE));d=ImageDraw.Draw(im)
    # A separate contact/overhead ground shadow independent of crown alpha fades.
    rx,ry=(133,62) if species=='oak' else (104,69)
    for k in range(10,0,-1):
        expand=k*7
        alpha=round((1-k/11)*36)
        oval(d,192,284,rx+expand,ry+expand*.6,(12,24,17,alpha))
    oval(d,192,286,rx,ry,(14,27,21,80))
    oval(d,194,317,22,12,(10,23,17,100))
    return im.filter(ImageFilter.GaussianBlur(2.0))

def build(output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    records={}
    for species in ('oak','pine'):
        for channel,image in (('trunk',trunk(species)),('shadow',shadow(species))):
            name=f'{species}_{channel}.png';image.save(output/name,optimize=True)
            records[f'{species}:{channel}']={'file':name,'sha256':sha256((output/name).read_bytes()).hexdigest(),
                                            'size':[SIZE,SIZE],'channel':channel,'anchor':[192,369] if channel=='trunk' else [192,286]}
        for season in ('spring','summer','autumn','winter'):
            image=crown_oak(season) if species=='oak' else crown_pine(season)
            name=f'{species}_crown_{season}.png';image.save(output/name,optimize=True)
            records[f'{species}:crown:{season}']={
                'file':name,'sha256':sha256((output/name).read_bytes()).hexdigest(),
                'size':[SIZE,SIZE],'channel':'crown','season':season,'anchor':[192,369],
            }
    payload={
        'version':SCHEMA_VERSION,'description':'Layered anchored oak/pine RGBA source art; separate trunk/crown/shadow, visual only',
        'source':'tools/build_worldspace_tree_art.py',
        'license':'WORLDSEED original code-generated artwork',
        'dimensions':[SIZE,SIZE], 'premultiplied_alpha':False,
        'anchor_policy':'bottom-center tree foot; all channels align to same source trunk world cell',
        'footprint_policy':'all collision and harvesting remain on authoritative source cell, not sprite bounds',
        'fow_policy':'clip all sprite pixels to current visibility before drawing',
        'entries':records,
    }
    (output/'manifest.json').write_text(json.dumps(payload,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    packed=BytesIO()
    with ZipFile(packed,'w',compression=ZIP_DEFLATED,compresslevel=9) as archive:
        for png in sorted(output.glob('*.png')):
            info=ZipInfo(png.name,(2020,1,1,0,0,0))
            info.compress_type=ZIP_DEFLATED
            archive.writestr(info,png.read_bytes(),compress_type=ZIP_DEFLATED,compresslevel=9)
    encoded=b85encode(packed.getvalue()).decode('ascii')
    (output/'tree_layers.b85').write_text('\n'.join(encoded[i:i+120]
                                       for i in range(0,len(encoded),120))+'\n',encoding='ascii')
    return payload

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=Path('worldseed/assets/sprites/worldspace/trees'))
    args=parser.parse_args(argv)
    data=build(args.output_dir)
    print(f"Generated {len(data['entries'])} layered tree sprites at {args.output_dir}")

if __name__=='__main__': main()
