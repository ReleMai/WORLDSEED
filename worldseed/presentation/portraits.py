"""Deterministic layered NPC face composites, owned entirely by presentation.

Each portrait version identifies a face by the world seed, NPC UID and sex.
Occupation, relationship, discovery and renderer call order do not participate.
Age only adds presentation changes to the same facial identity. The NPC's
saved version pin selects the frozen catalog; descriptors are recomputed without
world queries, mutable RNG streams or external art dependencies.
"""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, fields
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any

from worldseed.core.rng import hash_u64

PORTRAIT_VERSION = 2
MAX_PORTRAIT_SIZE = 520
PORTRAIT_NAMESPACE = "presentation:npc-portrait:v2"
_BASE_PARTS = ("head", "jaw", "ears", "nose", "eyes", "brows", "mouth", "hair", "facial_hair", "neck", "bust")
_BASE_PALETTES = ("skin", "hair", "eye", "cloth")
_PARTS = (*_BASE_PARTS, "tattoo", "markings", "accessory", "shading", "cloth_detail")
_PALETTES = (*_BASE_PALETTES, "ink", "metal")
_STYLES_V1 = {
    "hair": {"crop", "swept", "parted", "curls", "waves", "long", "braid", "tied", "bun", "shag", "coils", "bald", "receding", "undercut"},
    "facial_hair": {"none", "stubble", "moustache", "goatee", "short_beard", "full_beard", "forked_beard", "sideburns"},
    "bust": {"tunic", "mantle", "collar", "shawl", "layered"},
}
_STYLES = {key: set(styles) for key, styles in _STYLES_V1.items()}
_STYLES["hair"].update({"bob", "pixie", "mohawk", "dreadlocks", "cornrows", "double_braid", "afro", "topknot", "side_braid", "wavy_bob", "high_ponytail", "fringe", "spiked", "ringlets", "half_up", "buzz"})
_STYLES["bust"].update({"hood", "cape", "waistcoat", "high_collar", "wrap", "lace_front", "furs"})
_STYLES["facial_hair"].update({"chinstrap", "handlebar", "van_dyke", "braided_beard"})
_STYLES.update({
    "eyes": {"almond", "round", "narrow", "deep_set", "wide", "hooded", "upturned", "downturned", "monolid", "heavy_lid", "sleepy", "sharp"},
    "tattoo": {"none", "cheek_runes", "temple_spiral", "brow_dots", "chin_lines", "neck_bands", "eye_arc", "cheek_stars", "face_lattice"},
    "markings": {"none", "freckles", "dense_freckles", "mole", "scar_cheek", "scar_brow", "scar_nose", "dimples", "birthmark", "vitiligo", "beauty_marks"},
    "accessory": {"none", "ear_stud", "ear_hoop", "double_hoops", "nose_stud", "septum", "neck_beads", "pendant", "ear_cuff", "hair_pin", "round_glasses", "square_glasses"},
    "shading": {"soft", "warm", "cool", "dramatic", "sculpted", "weathered"},
    "cloth_detail": {"plain", "stripes", "checks", "embroidery", "diamond_trim", "buttons", "lacing", "patches", "brocade"},
})
_GEOMETRY = {
    "head": {"width": (8, 18), "height": (12, 22), "temple": (-2, 2), "cheek": (-2, 2)},
    "jaw": {"width": (-4, 4), "chin": (-2, 3)},
    "ears": {"width": (1, 4), "height": (4, 9), "lift": (-2, 2)},
    "nose": {"width": (1, 4), "length": (3, 9), "bridge": (-1, 1), "tip": (-1, 1)},
    "eyes": {"width": (3, 6), "slant": (-1, 1), "lid": (0, 2)},
    "brows": {"width": (3, 6), "thick": (1, 2), "arch": (-2, 2)},
    "mouth": {"width": (4, 9), "fullness": (0, 2), "curve": (-1, 1)},
    "hair": {}, "facial_hair": {},
    "neck": {"width": (3, 8)}, "bust": {"width": (20, 29)},
    "tattoo": {}, "markings": {}, "accessory": {}, "shading": {"contrast": (0, 30)}, "cloth_detail": {},
}


def validate_portrait_catalog(data: Any) -> None:
    """Reject malformed part catalogs before a face can reach the renderer."""
    if not isinstance(data, dict) or type(data.get("version")) is not int or data.get("version") not in (1, 2):
        raise ValueError("Unsupported portrait feature catalog version")
    version = data["version"]
    styles = _STYLES_V1 if version == 1 else _STYLES
    for section, required in (("parts", _BASE_PARTS if version == 1 else _PARTS), ("palettes", _BASE_PALETTES if version == 1 else _PALETTES)):
        groups = data.get(section)
        if not isinstance(groups, dict) or set(groups) != set(required):
            raise ValueError(f"Portrait {section} must define {', '.join(required)}")
        for group, entries in groups.items():
            if not isinstance(entries, dict) or not entries:
                raise ValueError(f"Empty portrait pool: {group}")
            totals = dict.fromkeys(("male", "female", "unknown"), 0)
            for key, definition in entries.items():
                if not isinstance(key, str) or not re.fullmatch(r"[a-z][a-z0-9_]*:[a-z][a-z0-9_]*", key):
                    raise ValueError(f"Portrait IDs must be namespaced: {key}")
                if not isinstance(definition, dict):
                    raise ValueError(f"Invalid portrait definition: {key}")
                weights = definition.get("weights")
                if not isinstance(weights, dict) or set(weights) != set(totals):
                    raise ValueError(f"Missing portrait sex weights: {key}")
                for sex, weight in weights.items():
                    if type(weight) is not int or not 0 <= weight <= 100:
                        raise ValueError(f"Invalid portrait weight: {key}/{sex}")
                    totals[sex] += weight
                if section == "palettes":
                    colors = definition.get("colors")
                    minimum = 4 if group == "skin" else 2 if group == "eye" else 3
                    if not isinstance(colors, list) or len(colors) != minimum:
                        raise ValueError(f"Invalid portrait palette length: {key}")
                    for color in colors:
                        if not isinstance(color, list) or len(color) != 3 or any(type(c) is not int or not 0 <= c <= 255 for c in color):
                            raise ValueError(f"Invalid portrait RGB color: {key}")
                else:
                    expected = {"weights", *_GEOMETRY[group]}
                    if group in styles:
                        expected.add("style")
                    if set(definition) != expected:
                        raise ValueError(f"Missing or unsupported portrait parameters: {key}")
                    for parameter, value in definition.items():
                        if parameter == "weights":
                            continue
                        if parameter == "style":
                            if not isinstance(value, str) or value not in styles.get(group, set()):
                                raise ValueError(f"Unsupported portrait style: {key}")
                        elif type(value) is not int or not _GEOMETRY[group][parameter][0] <= value <= _GEOMETRY[group][parameter][1]:
                            raise ValueError(f"Invalid portrait shape parameter: {key}/{parameter}")
            if any(total <= 0 for total in totals.values()):
                raise ValueError(f"Portrait pool has no selectable parts: {group}")


@lru_cache(maxsize=2)
def _catalog(version: int = PORTRAIT_VERSION) -> dict:
    if type(version) is not int or version not in (1, 2):
        raise ValueError("Unsupported portrait catalog version")
    path = Path(__file__).resolve().parents[1] / "data" / ("portrait_features_v1.json" if version == 1 else "portrait_features.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_portrait_catalog(data)
    if data["version"] != version:
        raise ValueError("Portrait catalog does not match requested version")
    return data


def portrait_catalog(version: int = PORTRAIT_VERSION) -> dict:
    """Return a detached catalog for inspection and authoring tools."""
    return deepcopy(_catalog(version))


@dataclass(frozen=True, slots=True)
class PortraitSpec:
    version: int
    identity: str
    sex: str
    age_stage: str
    head: str
    jaw: str
    ears: str
    nose: str
    eyes: str
    brows: str
    mouth: str
    hair: str
    facial_hair: str
    neck: str
    bust: str
    skin_palette: str
    hair_palette: str
    eye_palette: str
    cloth_palette: str
    eye_spacing: int
    eye_height: int
    asymmetry: int
    complexion: int
    detail: int
    tattoo: str = "core:none"
    markings: str = "core:none"
    accessory: str = "core:none"
    shading: str = "core:soft"
    cloth_detail: str = "core:plain"
    ink_palette: str = ""
    metal_palette: str = ""

    @property
    def facial_identity(self) -> tuple:
        """Stable composite identity; age effects never replace facial parts."""
        legacy_extras = {"tattoo", "markings", "accessory", "shading", "cloth_detail", "ink_palette", "metal_palette"} if self.version == 1 else set()
        return tuple(getattr(self, field.name) for field in fields(self) if field.name != "age_stage" and field.name not in legacy_extras)


def portrait_spec(seed: bytes, npc_uid: str, sex: str, age: int = 30, *, version: int = PORTRAIT_VERSION) -> PortraitSpec:
    """Describe a face without loading pygame, touching state, or rolling RNG."""
    if not isinstance(seed, bytes):
        raise TypeError("Portrait seed must be bytes")
    if not isinstance(npc_uid, str) or not npc_uid:
        raise ValueError("Portrait requires a permanent nonempty NPC UID")
    if type(version) is not int or version not in (1, 2):
        raise ValueError("Unsupported portrait identity version")
    sex = str(sex).strip().lower()
    sex = sex if sex in ("male", "female") else "unknown"
    age = max(0, int(age))
    namespace = f"presentation:npc-portrait:v{version}"
    identity = f"{hash_u64(seed, namespace + ':identity', npc_uid, sex):016x}"
    catalog = _catalog(version)

    def pick(section: str, group: str) -> str:
        entries = catalog[section][group]
        total = sum(value["weights"][sex] for value in entries.values())
        token = hash_u64(seed, namespace + ':' + section + ':' + group, npc_uid, sex) % total
        for name, value in sorted(entries.items()):
            token -= value["weights"][sex]
            if token < 0:
                return name
        raise AssertionError("Validated portrait pool had no selection")

    chosen = {part: pick("parts", part) for part in (_BASE_PARTS if version == 1 else _PARTS)}
    chosen.update({part + "_palette": pick("palettes", part) for part in (_BASE_PALETTES if version == 1 else _PALETTES)})
    # Each subtle proportion/detail uses its own domain. A new optional part
    # cannot shift unrelated choices or consume the simulation's RNG stream.
    for key, bound, offset in (("eye_spacing", 3, -1), ("eye_height", 3, -1), ("asymmetry", 3, -1), ("complexion", 4, 0), ("detail", 6, 0)):
        chosen[key] = int(hash_u64(seed, namespace + ':' + key, npc_uid, sex) % bound) + offset
    return PortraitSpec(version, identity, sex, "youth" if age < 18 else "elder" if age >= 55 else "adult", **chosen)


def _mix(a, b, fraction):
    return tuple(round(x + (y - x) * fraction) for x, y in zip(a, b))


def _draw_portrait_v1(spec: PortraitSpec):
    """Build reusable silhouette, face, hair and clothing masks at 64px."""
    import pygame as pg

    if spec.version != 1:
        raise ValueError("Unsupported portrait renderer version")
    c = _catalog(1)
    p = {part: c["parts"][part][getattr(spec, part)] for part in _BASE_PARTS}
    skin = tuple(tuple(v) for v in c["palettes"]["skin"][spec.skin_palette]["colors"])
    hair = tuple(tuple(v) for v in c["palettes"]["hair"][spec.hair_palette]["colors"])
    eye = tuple(tuple(v) for v in c["palettes"]["eye"][spec.eye_palette]["colors"])
    cloth = tuple(tuple(v) for v in c["palettes"]["cloth"][spec.cloth_palette]["colors"])
    if spec.age_stage == "elder":
        hair = tuple(_mix(color, target, .72) for color, target in zip(hair, ((222, 222, 208), (158, 162, 157), (91, 97, 97))))
    outline = _mix(skin[3], (23, 27, 34), .5)
    surface = pg.Surface((64, 64), pg.SRCALPHA)
    d = pg.draw
    x = 32
    hw = p["head"]["width"] - (1 if spec.age_stage == "youth" else 0)
    hh = p["head"]["height"]
    top, chin = 29 - hh, 29 + hh + p["jaw"]["chin"]
    left, right = x - hw, x + hw
    jaw = max(6, hw - 4 + p["jaw"]["width"])
    cheek = p["head"]["cheek"]
    style = p["hair"]["style"]

    # Hair behind the head provides a real modular silhouette, including
    # shoulder-length cuts, tied hair, braids and buns.
    if style in ("long", "waves", "braid", "shag", "tied"):
        end = 54 if style in ("long", "waves", "braid") else 47
        back = [(left-2,top+5),(left-4,23),(left-4,end-4),(left-1,end),(left+3,end-2),(x,end-5),(right-2,end),(right+4,end-1),(right+3,25),(right+2,top+4),(x,top-3)]
        d.polygon(surface, hair[2], back)
        d.polygon(surface, hair[1], [(left-1,top+5),(left-2,end-5),(left+2,end-2),(left+4,22),(x,top)])
        d.lines(surface,hair[0],False,[(left+1,19),(left,34),(left+1,end-7)],1)
        if style == "waves":
            for yy in range(21, end-4, 8):
                d.lines(surface,hair[0],False,[(right+1,yy),(right-1,yy+3),(right+1,yy+6)],1)
        if style == "braid":
            for yy in range(29,59,5):
                d.polygon(surface,hair[2],[(right,yy),(right+5,yy+2),(right+3,yy+6),(right-1,yy+3)])
                d.line(surface,hair[0],(right,yy+1),(right+3,yy+3))
            d.rect(surface,cloth[0],(right,57,4,2))
        if style == "tied":
            d.ellipse(surface,hair[2],(right-1,16,10,27))
            d.lines(surface,hair[0],False,[(right+3,19),(right+5,29),(right+3,39)],1)
    if style == "bun":
        d.ellipse(surface,hair[2],(x+1,top-7,15,13))
        d.ellipse(surface,hair[1],(x+2,top-6,11,9))
        d.arc(surface,hair[0],(x+4,top-5,7,6),.7,3.4,1)

    # Shoulders, garments and neck are independent composite parts. Clothing
    # is stable cosmetic identity and never claims an unseen occupation.
    shoulders = p["bust"]["width"] - (2 if spec.age_stage == "youth" else 0)
    garment = [(x-shoulders,64),(x-shoulders+2,56),(x-14,50),(x-8,48),(x+8,48),(x+15,51),(x+shoulders-2,57),(x+shoulders,64)]
    d.polygon(surface,outline,garment)
    inner = [(px,py+1 if py<60 else py) for px,py in garment]
    d.polygon(surface,cloth[1],inner)
    d.polygon(surface,cloth[0],[(x-shoulders+4,57),(x-12,52),(x-5,52),(x-7,64),(x-shoulders+1,64)])
    d.polygon(surface,cloth[2],[(x+9,51),(x+shoulders-3,57),(x+shoulders,64),(x+4,64)])
    neck = p["neck"]["width"] - (1 if spec.age_stage == "youth" else 0)
    d.polygon(surface,outline,[(x-neck,chin-5),(x+neck,chin-5),(x+neck+1,51),(x+4,57),(x-4,57),(x-neck-1,51)])
    d.polygon(surface,skin[1],[(x-neck+1,chin-5),(x+neck-1,chin-5),(x+neck,51),(x+3,55),(x-3,55),(x-neck,51)])
    d.polygon(surface,skin[2],[(x+1,chin-4),(x+neck-1,chin-4),(x+neck,51),(x+3,55),(x,53)])
    d.line(surface,skin[0],(x-neck+2,47),(x-neck+2,50))
    garment_style = p["bust"]["style"]
    if garment_style in ("collar", "layered"):
        d.polygon(surface,cloth[2],[(x-10,48),(x-3,55),(x,59),(x-8,56),(x-13,52)])
        d.polygon(surface,cloth[0],[(x+10,48),(x+4,55),(x,59),(x+10,55),(x+13,52)])
        d.lines(surface,cloth[0],False,[(x-11,49),(x-6,55),(x-2,57)],1)
    elif garment_style in ("mantle", "shawl"):
        d.polygon(surface,cloth[2],[(x-14,49),(x-7,51),(x+10,59),(x+4,64),(x-7,57),(x-19,57)])
        d.lines(surface,cloth[0],False,[(x-15,51),(x-8,53),(x+9,60)],1)
        d.circle(surface,(185,160,99),(x+9,58),2)
        d.rect(surface,(226,204,139),(x+8,57,1,1))
    else:
        d.lines(surface,cloth[2],False,[(x-8,50),(x-4,56),(x,58),(x+5,56),(x+8,50)],2)
        d.lines(surface,cloth[0],False,[(x-7,51),(x-3,56),(x,57)],1)
    if garment_style == "layered":
        d.line(surface,cloth[0],(x,59),(x,64),1)
        d.rect(surface,(194,170,108),(x-1,60,2,2))
    for sx in (-1,1):
        d.line(surface,cloth[2],(x+sx*(shoulders-7),59),(x+sx*(shoulders-5),63),1)

    # Ears are separate parts, with inner cartilage and a lit outer rim.
    ear = p["ears"]
    for side in (-1,1):
        ex, ey = x + side*hw, 26-ear["lift"]
        ew, eh = ear["width"], ear["height"]
        if spec.ears.endswith("pointed"):
            pts=[(ex-side,ey-2),(ex+side*(ew+2),ey-3),(ex+side*ew,ey+eh-2),(ex,ey+eh)]
            d.polygon(surface,outline,pts)
            d.polygon(surface,skin[1],[(ex,ey-1),(ex+side*(ew+1),ey-2),(ex+side*(ew-1),ey+eh-2),(ex,ey+eh-1)])
        else:
            rect=(ex-ew if side<0 else ex-1,ey,ew+2,eh)
            d.ellipse(surface,outline,rect)
            d.ellipse(surface,skin[1],(rect[0]+1,ey+1,ew,eh-2))
        d.line(surface,skin[2],(ex+side,ey+2),(ex+side,ey+eh-3),1)
        if side<0:d.rect(surface,skin[0],(ex-1,ey+1,1,2))

    temple=p["head"]["temple"]
    face_shape=[(x-5,top),(x+5,top),(right-2+temple,top+4),(right,21),(right,29),(right-1+cheek,34),(x+jaw,chin-5),(x+4,chin-1),(x,chin),(x-4,chin-1),(x-jaw,chin-5),(left+1-cheek,34),(left,29),(left,21),(left+2-temple,top+4)]
    mask=pg.Surface((64,64),pg.SRCALPHA)
    d.polygon(mask,(255,255,255,255),face_shape)
    face=pg.Surface((64,64),pg.SRCALPHA)
    face.fill(skin[1])
    # Plane shading: forehead, temples, cheekbones and jaw retain varied
    # silhouettes; masking avoids coloring hair, ears or transparent corners.
    d.polygon(face,skin[2],[(x+4,top),(right+2,top),(right+3,chin),(x+3,chin),(x+6,38),(x+8,31),(x+7,23)])
    d.polygon(face,skin[0],[(left+3,top+5),(x-2,top+2),(x+1,21),(x-4,24),(left+3,25)])
    d.polygon(face,skin[0],[(left+3,30),(x-6,29),(x-4,34),(x-7,37),(left+4,35)])
    d.polygon(face,skin[2],[(left,33),(left+5,36),(x-6,40),(x-5,chin),(left-2,chin)])
    d.polygon(face,_mix(skin[1],skin[0],.35),[(x-3,36),(x+4,36),(x+5,42),(x,chin-2),(x-5,42)])
    d.polygon(face,skin[3],[(right-1,26),(right+1,24),(right+2,chin),(x+6,chin),(right-2,35)])
    face.blit(mask,(0,0),special_flags=pg.BLEND_RGBA_MULT)
    surface.blit(face,(0,0))
    d.lines(surface,outline,False,face_shape[3:13],1)

    # Eyes comprise sockets, whites, colored iris/pupil, upper lid and catch
    # light; geometry and spacing vary independently of head/jaw shape.
    eyes=p["eyes"]
    ey=26+spec.eye_height
    spacing=7+spec.eye_spacing
    white=_mix(skin[0],(242,235,212),.72)
    for side in (-1,1):
        cx=x+side*spacing
        width=eyes["width"]
        y=ey+(spec.asymmetry if side>0 else 0)
        lx=cx-width//2
        d.line(surface,skin[2],(lx-1,y-2),(lx+width,y-2),1)
        d.polygon(surface,white,[(lx,y),(lx+1,y-1),(lx+width-2,y-1+eyes["slant"]),(lx+width,y),(lx+width-1,y+1),(lx+1,y+1)])
        d.rect(surface,eye[0],(cx,y-1,2,3))
        d.rect(surface,eye[1],(cx+1,y,1,2))
        d.rect(surface,outline,(cx+1,y,1,1))
        d.rect(surface,white,(cx,y-1,1,1))
        d.lines(surface,outline,False,[(lx,y),(lx+1,y-1),(lx+width-2,y-1+eyes["slant"]),(lx+width,y)],1)
        d.line(surface,skin[2],(lx+1,y+2),(lx+width-1,y+2),1)
        if eyes["lid"]==2:d.line(surface,skin[3],(lx+1,y-1),(lx+width-1,y-1),1)
        brow=p["brows"]
        by=y-4
        bw=brow["width"]
        bx=cx-bw//2
        bcolor=_mix(hair[1],skin[3],.25)
        d.lines(surface,bcolor,False,[(bx,by),(cx,by-brow["arch"]),(bx+bw,by+side//2)],brow["thick"])
        if spec.brows.endswith("broken"):d.rect(surface,skin[1],(bx+2,by-1,1,3))

    # Independent nose bridge, tip, nostrils and philtrum.
    nose=p["nose"]
    ny=ey+1
    bottom=ny+nose["length"]
    nw=nose["width"]
    bridge=nose["bridge"]
    d.polygon(surface,skin[2],[(x+1,ny),(x+2+bridge,ny+3),(x+nw,bottom),(x+1,bottom+1),(x,bottom-1)])
    d.line(surface,skin[0],(x-1,ny),(x-1+bridge,bottom-2),1)
    d.line(surface,skin[0],(x-1,bottom-1),(x+1,bottom-1),1)
    d.line(surface,skin[3],(x-nw,bottom),(x-1,bottom+1),1)
    d.rect(surface,skin[3],(x+nw-1,bottom,1,1))
    if nose["tip"]>0:d.rect(surface,skin[0],(x-1,bottom-1,3,1))
    d.line(surface,skin[2],(x,bottom+2),(x,bottom+3),1)
    mouth=p["mouth"]
    my=max(39,bottom+4)
    my=min(my,chin-4)
    mw=mouth["width"]
    lip=_mix(skin[2],(135,69,71),.32)
    d.line(surface,lip,(x-mw//2,my),(x-1,my-mouth["curve"]),1)
    d.line(surface,lip,(x,my-mouth["curve"]),(x+mw//2,my),1)
    d.line(surface,skin[3],(x-mw//2+1,my+1),(x+mw//2-1,my+1),1)
    if mouth["fullness"]:
        d.line(surface,_mix(lip,skin[0],.3),(x-mw//2+1,my+2),(x+mw//2-1,my+2),1)
        if mouth["fullness"]==2:d.line(surface,lip,(x-2,my-1),(x+2,my-1),1)
    d.line(surface,skin[0],(x-3,my+3),(x+2,my+3),1)

    # Stable cosmetic detail: freckles, a small mole, a healed scar or a
    # clear complexion. These expose no private biography or game stats.
    if spec.complexion==1:
        for side in (-1,1):
            for dx,dy in ((0,0),(2,1),(-2,1),(1,2)):
                d.rect(surface,skin[2],(x+side*8+dx,31+dy,1,1))
    elif spec.complexion==2:
        d.rect(surface,skin[3],(x-9,35,1,1))
    if spec.detail==2:
        d.line(surface,skin[2],(right-6,21),(right-4,27),1)
        d.line(surface,skin[0],(right-7,21),(right-5,27),1)
    if spec.age_stage=="elder":
        for side in (-1,1):
            ex=x+side*spacing
            d.line(surface,skin[2],(ex+side*3,ey+2),(ex+side*5,ey+3),1)
            d.line(surface,skin[2],(x+side*4,36),(x+side*6,my+1),1)
        d.line(surface,skin[2],(x-6,19),(x+4,19),1)
        d.line(surface,skin[0],(x-4,18),(x+3,18),1)
        d.line(surface,skin[2],(x-3,chin-2),(x+3,chin-2),1)

    # Facial hair is a reusable mask layer, never an entire precolored sprite.
    beard=p["facial_hair"]["style"] if spec.age_stage!="youth" else "none"
    if beard in ("full_beard","forked_beard","short_beard"):
        length=5 if beard=="short_beard" else 11 if beard=="forked_beard" else 8
        end=chin+length-4
        beard_pts=[(left+2,33),(left+5,39),(x-6,my+3),(x,my+4),(x+6,my+3),(right-3,35),(right-3,42),(x+7,end-1),(x+2,end),(x,end-2 if beard=="forked_beard" else end),(x-3,end),(x-8,end-2),(left+3,42)]
        d.polygon(surface,hair[2],beard_pts)
        d.lines(surface,hair[1],False,[(left+4,35),(left+6,42),(x-5,end-3),(x-2,end-1)],2)
        for bx in range(x-5,x+6,3):d.line(surface,hair[1],(bx,my+5),(bx+1,end-2),1)
        d.lines(surface,hair[0],False,[(left+5,38),(left+7,44),(x-4,end-3)],1)
    elif beard=="goatee":
        d.polygon(surface,hair[2],[(x-4,my+4),(x+4,my+4),(x+3,chin+2),(x,chin+5),(x-3,chin+2)])
        d.line(surface,hair[0],(x-2,my+5),(x-1,chin+2),1)
    elif beard=="stubble":
        for yy in range(my+3,chin-1,2):
            for xx in range(x-jaw+3,x+jaw-2,3):
                if (xx+yy)%3:d.rect(surface,_mix(hair[1],skin[1],.35),(xx,yy,1,1))
        for side in (-1,1):d.line(surface,_mix(hair[1],skin[1],.45),(x+side*(hw-3),33),(x+side*(hw-4),38),1)
    if beard in ("moustache","goatee","full_beard","forked_beard","short_beard"):
        d.lines(surface,hair[2],False,[(x-6,my),(x-3,my-1),(x-1,my),(x+1,my),(x+3,my-1),(x+6,my)],2)
        d.line(surface,hair[0],(x-5,my-1),(x-2,my-1),1)
    if beard=="sideburns":
        for side in (-1,1):d.line(surface,hair[1],(x+side*(hw-2),28),(x+side*(hw-3),36),3)

    # Front hair is the final separate mask. Front/back silhouette families
    # combine with all face parts, and strand shading follows each hairstyle.
    if style not in ("bald","receding"):
        cap=[(left-2,23),(left-3,top+5),(left+1,top),(x-5,top-3),(x+5,top-3),(right,top+1),(right+3,top+7),(right+2,24),(right-1,20),(right-3,top+7),(x+4,top+5),(x-4,top+5),(left+3,top+9),(left+2,24)]
        d.polygon(surface,hair[2],cap)
        d.polygon(surface,hair[1],[(left-1,top+5),(left+3,top+1),(x-4,top-1),(x+4,top),(x+4,top+4),(left+4,top+7),(left+1,19)])
        if style in ("swept","waves","long"):
            d.polygon(surface,hair[1],[(left+1,top+5),(x-1,top+1),(right-2,top+3),(x+3,top+10),(left+3,24),(left+1,21)])
            for offset in (0,3,6):d.lines(surface,hair[0],False,[(x+3+offset,top+2),(x-3+offset,top+6),(left+4+offset//2,top+10)],1)
        elif style in ("parted","tied","bun","braid"):
            d.line(surface,hair[2],(x,top),(x-1,top+6),1)
            for side in (-1,1):
                d.lines(surface,hair[0],False,[(x+side*2,top+1),(x+side*7,top+3),(x+side*(hw-2),top+7)],1)
                d.line(surface,hair[1],(x+side*(hw-1),20),(x+side*(hw-1),26),2)
        elif style in ("curls","coils"):
            radius=3 if style=="curls" else 2
            for xx,yy in ((left+2,top+5),(left+6,top+1),(x,top-1),(x+5,top),(right-3,top+3),(right,top+7),(left,top+10)):
                d.circle(surface,hair[2],(xx,yy),radius+1)
                d.circle(surface,hair[1],(xx-1,yy-1),radius)
                d.line(surface,hair[0],(xx-1,yy-2),(xx+1,yy-2),1)
            if style=="coils":
                for xx in range(left+3,right-2,4):d.rect(surface,hair[0],(xx,top+5+(xx%3),1,2))
        elif style=="shag":
            d.polygon(surface,hair[1],[(left,top+5),(right,top+4),(right-2,24),(right-5,19),(x+3,23),(x+1,18),(x-4,22),(x-6,18),(left+2,25)])
            for xx in range(left+3,right-2,4):d.line(surface,hair[0],(xx,top+3),(xx-2,top+8),1)
        elif style=="undercut":
            d.polygon(surface,skin[2],[(left,20),(left+2,17),(left+3,26),(left+1,28)])
            d.polygon(surface,hair[1],[(left+2,top+2),(x+7,top-3),(right+1,top+2),(x+5,top+8),(left+4,top+10)])
            d.lines(surface,hair[0],False,[(right-3,top+1),(x+2,top+3),(left+5,top+7)],2)
        else:
            for xx in range(left+2,right-1,4):d.line(surface,hair[0],(xx,top+3),(xx+1,top+5),1)
            d.lines(surface,hair[1],False,[(left+1,18),(left+2,21),(left+2,25)],2)
    elif style=="receding":
        for side in (-1,1):
            d.polygon(surface,hair[2],[(x+side*8,top+1),(x+side*(hw+1),top+6),(x+side*(hw+1),27),(x+side*(hw-2),24),(x+side*(hw-3),top+5)])
            d.line(surface,hair[0],(x+side*(hw-1),top+7),(x+side*(hw-1),23),1)
    else:
        d.line(surface,skin[0],(x-5,top+2),(x+3,top+2),1)
    if spec.age_stage=="elder" and style!="bald":
        d.line(surface,hair[0],(left+1,22),(left+2,26),1)
    return surface


def _hair_back_v2(pg, surface, style, hair, cloth, g):
    """Distinct back silhouettes: cropped, bobbed, tied, braided and coiled."""
    d=pg.draw
    x,left,right,top=g['x'],g['left'],g['right'],g['top']
    longcuts={'long','waves','braid','shag','tied','half_up','dreadlocks','ringlets','side_braid','double_braid'}
    if style in longcuts:
        end=47 if style in ('shag','tied') else 54
        d.polygon(surface,hair[2],[(left-2,top+5),(left-4,23),(left-4,end-4),(left-1,end),(left+3,end-2),(x,end-5),(right-2,end),(right+4,end-1),(right+3,25),(right+2,top+4),(x,top-3)])
        d.polygon(surface,hair[1],[(left-1,top+5),(left-2,end-5),(left+2,end-2),(left+4,22),(x,top)])
        d.lines(surface,hair[0],False,[(left+1,19),(left,34),(left+1,end-7)],1)
        if style=='waves':
            for yy in range(21,end-4,8):d.lines(surface,hair[0],False,[(right+1,yy),(right-1,yy+3),(right+1,yy+6)],1)
        if style in ('braid','double_braid','side_braid'):
            sides=(-1,1) if style=='double_braid' else (-1,) if style=='side_braid' else (1,)
            for side in sides:
                bx=left-1 if side<0 else right
                for yy in range(29,59,5):
                    d.polygon(surface,hair[2],[(bx,yy),(bx+side*5,yy+2),(bx+side*3,yy+6),(bx-side,yy+3)])
                    d.line(surface,hair[0],(bx,yy+1),(bx+side*3,yy+3))
                    d.line(surface,hair[1],(bx+side*3,yy+4),(bx,yy+5))
                d.rect(surface,cloth[0],(min(bx,bx+side*3),57,4,2))
        if style=='dreadlocks':
            for side in (-1,1):
                for i in range(3):
                    bx=x+side*(g['hw']-1+i*2)
                    end=48+(i%2)*7
                    d.lines(surface,hair[2],False,[(bx,16),(bx-side,30),(bx+side,end)],3)
                    d.lines(surface,hair[0],False,[(bx-side,22),(bx-side,33),(bx,end-3)],1)
                    d.line(surface,cloth[1],(bx-1,end-6),(bx+1,end-6))
        if style=='ringlets':
            for side in (-1,1):
                for yy in range(24,51,6):
                    bx=x+side*(g['hw']+1)+(yy//6%2)
                    d.circle(surface,hair[2],(bx,yy),4)
                    d.circle(surface,hair[1],(bx-1,yy-1),3)
                    d.arc(surface,hair[0],(bx-2,yy-2,4,4),.3,4.4,1)
        if style=='tied':
            d.ellipse(surface,hair[2],(right-1,16,10,27))
            d.lines(surface,hair[0],False,[(right+3,19),(right+5,29),(right+3,39)],1)
    if style in ('bob','wavy_bob'):
        edge=41 if style=='bob' else 44
        d.polygon(surface,hair[2],[(left-4,top+7),(left-4,edge),(left+3,edge-1),(left+4,24),(right-4,24),(right-3,edge),(right+5,edge-2),(right+4,top+7),(x,top-2)])
        for side in (-1,1):
            bx=x+side*(g['hw']+1)
            if style=='bob':
                d.line(surface,hair[1],(bx,20),(bx,edge-2),2)
                d.line(surface,hair[0],(bx-side,23),(bx-side,edge-5),1)
            else:
                for yy in range(21,edge-3,6):
                    d.lines(surface,hair[1],False,[(bx,yy),(bx+side*2,yy+2),(bx,yy+5)],2)
                    d.rect(surface,hair[0],(bx-side,yy,1,2))
    if style in ('bun','topknot','half_up'):
        bx=x+7 if style=='bun' else x+2
        by=top-3 if style=='half_up' else top-6
        d.ellipse(surface,hair[2],(bx-6,by-2,14,12))
        d.ellipse(surface,hair[1],(bx-5,by-1,11,9))
        d.arc(surface,hair[0],(bx-3,by,7,6),.7,3.4,1)
        if style=='topknot':d.line(surface,cloth[0],(bx-4,by+8),(bx+5,by+8),2)
    if style=='high_ponytail':
        d.polygon(surface,hair[2],[(x+7,top-4),(right+7,top),(right+10,18),(right+8,36),(right+3,46),(right+2,34),(right+5,22),(right+3,9)])
        d.lines(surface,hair[0],False,[(x+10,top-2),(right+6,14),(right+7,28),(right+4,40)],2)
        d.line(surface,cloth[0],(x+8,top-1),(x+12,top+1),2)
    if style=='afro':
        for bx,by,radius in ((left-1,21,8),(left+2,top+3,8),(x-7,top-2,8),(x+1,top-4,8),(x+10,top,9),(right+3,top+8,8),(right+4,24,7)):
            d.circle(surface,hair[2],(bx,by),radius)
            d.circle(surface,hair[1],(bx-1,by-2),radius-2)
            d.arc(surface,hair[0],(bx-4,by-5,7,7),.5,3.0,1)


def _hair_front_v2(pg, surface, style, hair, skin, g):
    """Thirty materially different cuts share three independently chosen dyes."""
    d=pg.draw
    x,left,right,top,hw=g['x'],g['left'],g['right'],g['top'],g['hw']
    if style=='bald':
        d.line(surface,skin[0],(x-5,top+2),(x+3,top+2),1)
        return
    if style=='receding':
        for side in (-1,1):
            d.polygon(surface,hair[2],[(x+side*8,top+1),(x+side*(hw+1),top+6),(x+side*(hw+1),27),(x+side*(hw-2),24),(x+side*(hw-3),top+5)])
            d.line(surface,hair[0],(x+side*(hw-1),top+7),(x+side*(hw-1),23),1)
        return
    if style=='mohawk':
        d.polygon(surface,hair[2],[(x-4,22),(x-5,top+2),(x-3,top-7),(x+1,top-9),(x+4,top-5),(x+5,top+4),(x+3,22)])
        d.polygon(surface,hair[1],[(x-3,top+3),(x-2,top-5),(x,top-7),(x+2,top-3),(x+2,top+8),(x,20)])
        d.line(surface,hair[0],(x-1,top-5),(x,top+4),2)
        for side in (-1,1):d.line(surface,skin[2],(x+side*(hw-2),17),(x+side*(hw-2),23),1)
        return
    if style=='buzz':
        d.polygon(surface,_mix(hair[1],skin[1],.22),[(left,20),(left+1,top+4),(x-5,top),(x+5,top),(right-1,top+4),(right,20),(right-3,17),(x+4,top+4),(x-4,top+4),(left+3,17)])
        for yy in range(top+3,18,3):
            for xx in range(left+3,right-2,3):
                if (xx+yy)%4:d.rect(surface,hair[2],(xx,yy,1,1))
        return
    cap=[(left-2,23),(left-3,top+5),(left+1,top),(x-5,top-3),(x+5,top-3),(right,top+1),(right+3,top+7),(right+2,24),(right-1,20),(right-3,top+7),(x+4,top+5),(x-4,top+5),(left+3,top+9),(left+2,24)]
    d.polygon(surface,hair[2],cap)
    d.polygon(surface,hair[1],[(left-1,top+5),(left+3,top+1),(x-4,top-1),(x+4,top),(x+4,top+4),(left+4,top+7),(left+1,19)])
    if style in ('swept','waves','long','half_up','side_braid'):
        d.polygon(surface,hair[1],[(left+1,top+5),(x-1,top+1),(right-2,top+3),(x+3,top+10),(left+3,24),(left+1,21)])
        for offset in (0,3,6):d.lines(surface,hair[0],False,[(x+3+offset,top+2),(x-3+offset,top+6),(left+4+offset//2,top+10)],1)
        if style=='half_up':d.line(surface,cloth_color(hair),(x-3,top+3),(x+5,top+3),1)
        if style=='side_braid':d.line(surface,hair[0],(x+5,top+5),(right-1,19),2)
    elif style in ('parted','tied','bun','braid','double_braid','topknot','high_ponytail'):
        d.line(surface,hair[2],(x,top),(x-1,top+6),1)
        for side in (-1,1):
            d.lines(surface,hair[0],False,[(x+side*2,top+1),(x+side*7,top+3),(x+side*(hw-2),top+7)],1)
            d.line(surface,hair[1],(x+side*(hw-1),20),(x+side*(hw-1),26),2)
        if style=='high_ponytail':d.lines(surface,hair[0],False,[(left+1,top+7),(x,top),(x+10,top-1)],1)
        if style=='double_braid':d.line(surface,hair[0],(x-2,top+6),(left+4,21),1)
        if style=='topknot':d.line(surface,hair[2],(x-4,top+2),(x+4,top+2),2)
    elif style in ('curls','coils','afro','ringlets'):
        radius=3 if style in ('curls','ringlets') else 2
        for xx,yy in ((left+2,top+5),(left+6,top+1),(x,top-1),(x+5,top),(right-3,top+3),(right,top+7),(left,top+10)):
            d.circle(surface,hair[2],(xx,yy),radius+1)
            d.circle(surface,hair[1],(xx-1,yy-1),radius)
            d.arc(surface,hair[0],(xx-2,yy-2,4,4),.3,3.8,1)
        if style in ('coils','afro'):
            for xx in range(left+3,right-2,4):d.rect(surface,hair[0],(xx,top+5+(xx%3),1,2))
        if style=='ringlets':
            for xx in (x-5,x+2):
                d.lines(surface,hair[2],False,[(xx,top+5),(xx+2,17),(xx,20),(xx-1,18)],2)
    elif style=='shag':
        d.polygon(surface,hair[1],[(left,top+5),(right,top+4),(right-2,24),(right-5,19),(x+3,23),(x+1,18),(x-4,22),(x-6,18),(left+2,25)])
        for xx in range(left+3,right-2,4):d.line(surface,hair[0],(xx,top+3),(xx-2,top+8),1)
    elif style=='undercut':
        d.polygon(surface,skin[2],[(left,20),(left+2,17),(left+3,26),(left+1,28)])
        d.polygon(surface,hair[1],[(left+2,top+2),(x+7,top-3),(right+1,top+2),(x+5,top+8),(left+4,top+10)])
        d.lines(surface,hair[0],False,[(right-3,top+1),(x+2,top+3),(left+5,top+7)],2)
    elif style in ('bob','wavy_bob','fringe'):
        line=21 if style=='fringe' else 20
        d.polygon(surface,hair[1],[(left,top+5),(right,top+5),(right-1,line),(x+5,line-1),(x+4,line),(x-5,line),(left+1,line-1)])
        for xx in range(left+3,right-2,4):d.lines(surface,hair[0],False,[(xx,top+4),(xx-1,line-3)],1)
        d.line(surface,hair[2],(left+1,line),(right-1,line),1)
        if style=='wavy_bob':d.lines(surface,hair[0],False,[(x-4,top+6),(x-5,17),(x-2,19),(x+2,17)],1)
        if style=='fringe':d.line(surface,hair[2],(x+5,line-4),(x+4,line),2)
    elif style=='pixie':
        d.polygon(surface,hair[1],[(left-1,top+5),(x-7,top-2),(x+6,top),(right+2,top+6),(right-3,21),(x+3,top+8),(x-4,top+5),(left+2,21)])
        d.lines(surface,hair[0],False,[(left+3,top+4),(x-3,top+1),(x+3,top+4),(right-3,19)],1)
        d.line(surface,hair[2],(x-3,top+5),(left+4,top+10),2)
    elif style=='cornrows':
        d.polygon(surface,_mix(skin[2],hair[1],.25),[(left,20),(left+1,top+4),(x-5,top),(x+5,top),(right,top+5),(right,23),(right-3,20),(left+3,20)])
        for offset in (-8,-4,0,4,8):
            bx=x+offset
            d.lines(surface,hair[2],False,[(bx,top+1+abs(offset)//4),(bx-1,top+8),(bx,20)],2)
            d.line(surface,hair[0],(bx,top+3+abs(offset)//4),(bx,17),1)
            for yy in range(top+5,20,4):d.rect(surface,hair[1],(bx-1,yy,2,1))
    elif style=='dreadlocks':
        for bx in range(left+2,right+1,4):
            end=20+(bx//4)%3
            d.lines(surface,hair[2],False,[(bx,top),(bx-1,top+7),(bx,end)],3)
            d.line(surface,hair[0],(bx-1,top+3),(bx-1,end-3),1)
    elif style=='spiked':
        spikes=[]
        for xx in range(left, right+1,5):spikes.extend([(xx,top+4),(xx+2,max(0,top-5-(xx%3)))])
        spikes.extend([(right+2,20),(right-2,top+8),(left+1,top+8),(left-1,21)])
        d.polygon(surface,hair[2],spikes)
        for xx in range(left+2,right,5):d.lines(surface,hair[0],False,[(xx,max(0,top-3-(xx%3))),(xx-1,top+5)],1)
    else:  # cropped cap
        for xx in range(left+2,right-1,4):d.line(surface,hair[0],(xx,top+3),(xx+1,top+5),1)
        d.lines(surface,hair[1],False,[(left+1,18),(left+2,21),(left+2,25)],2)


def cloth_color(hair):
    return _mix(hair[0],(198,168,112),.35)


def _garment_v2(pg,surface,style,cloth,skin,g):
    """Cosmetic textile silhouettes; these never create equipment or armor."""
    d=pg.draw
    x,neck,shoulders=g['x'],g['neck'],g['shoulders']
    if style=='high_collar':
        d.polygon(surface,cloth[2],[(x-neck-3,44),(x-neck-2,52),(x-2,57),(x+2,57),(x+neck+3,51),(x+neck+3,44),(x+neck,46),(x+neck,51),(x+2,54),(x-2,54),(x-neck,50),(x-neck,46)])
        d.line(surface,cloth[0],(x-neck-3,44),(x-neck-1,51),1)
        d.line(surface,cloth[0],(x+neck+3,45),(x+neck+2,52),1)
    elif style=='waistcoat':
        d.polygon(surface,cloth[0],[(x-13,49),(x-6,54),(x,60),(x+6,54),(x+13,49),(x+11,64),(x-11,64)])
        d.polygon(surface,cloth[2],[(x-12,51),(x-6,55),(x-1,61),(x-1,64),(x-11,64)])
        d.polygon(surface,cloth[2],[(x+12,51),(x+6,55),(x+1,61),(x+1,64),(x+11,64)])
        d.lines(surface,cloth[0],False,[(x-11,51),(x-5,56),(x-1,60)],1)
    elif style=='cape':
        d.polygon(surface,cloth[2],[(x-shoulders+1,59),(x-14,49),(x-8,49),(x-4,55),(x-12,59),(x-19,64),(x-shoulders,64)])
        d.polygon(surface,cloth[0],[(x+shoulders-1,59),(x+14,49),(x+8,49),(x+4,55),(x+12,59),(x+19,64),(x+shoulders,64)])
        d.line(surface,cloth[0],(x-10,53),(x+9,53),1)
        d.rect(surface,cloth[2],(x-1,52,3,3))
    elif style=='wrap':
        d.polygon(surface,cloth[0],[(x-15,49),(x-8,51),(x+14,63),(x+10,64),(x-18,55)])
        d.polygon(surface,cloth[2],[(x+13,49),(x+7,51),(x-13,63),(x-8,64),(x+18,54)])
        d.lines(surface,cloth[1],False,[(x-13,52),(x-6,55),(x+10,64)],1)
    elif style=='lace_front':
        d.polygon(surface,cloth[2],[(x-8,51),(x-3,56),(x-2,64),(x+2,64),(x+3,56),(x+8,51),(x+5,64),(x-5,64)])
        for yy in range(56,64,3):
            d.line(surface,cloth[0],(x-2,yy),(x+2,yy+2),1)
            d.line(surface,cloth[0],(x+2,yy),(x-2,yy+2),1)
    elif style=='furs':
        light=_mix(cloth[0],(204,187,149),.5)
        for side in (-1,1):
            for i in range(5):
                bx=x+side*(7+i*3)
                by=50+i
                d.polygon(surface,cloth[2],[(bx-side*2,by),(bx+side*3,by+1),(bx+side*2,by+6),(bx,by+4),(bx-side*2,by+7)])
                d.line(surface,light,(bx,by+1),(bx-side,by+4),2)
    elif style=='shawl':
        d.polygon(surface,cloth[0],[(x-17,50),(x-8,52),(x+12,61),(x+7,64),(x-18,55)])
        for bx in range(x-17,x-7,3):d.line(surface,cloth[2],(bx,55),(bx-1,59),1)
    elif style=='hood':
        d.polygon(surface,cloth[2],[(x-16,49),(x-9,49),(x-3,56),(x-11,59),(x-21,55)])
        d.polygon(surface,cloth[0],[(x+16,49),(x+9,49),(x+3,56),(x+11,59),(x+21,55)])
        d.line(surface,cloth[0],(x-13,52),(x-8,56),1)
    elif style=='mantle':
        d.rect(surface,cloth[0],(x-shoulders+5,58,2,6))
    elif style=='collar':
        d.line(surface,cloth[0],(x+3,59),(x+3,64),1)


def _eyes_v2(pg,surface,spec,p,skin,hair,eye,g):
    """Colored irises inside twelve distinct eyelid/socket geometries."""
    d=pg.draw
    x,ey,spacing=g['x'],g['ey'],g['spacing']
    shape=p['eyes']['style']
    white=_mix(skin[0],(242,235,212),.72)
    outline=_mix(skin[3],(23,27,34),.5)
    for side in (-1,1):
        cx=x+side*spacing
        width=p['eyes']['width']
        y=ey+(spec.asymmetry if side>0 else 0)
        lx=cx-width//2
        rx=lx+width
        upper=-2 if shape in ('round','wide') else -1
        lower=2 if shape in ('round','wide') else 1
        outer_y=-1 if shape in ('upturned','sharp','almond') else 1 if shape in ('downturned','sleepy') else 0
        outer_y=max(-2,min(2,outer_y+p['eyes']['slant']))
        inner_y=0
        yleft=outer_y if side<0 else inner_y
        yright=outer_y if side>0 else inner_y
        if shape in ('deep_set','heavy_lid'):
            d.polygon(surface,skin[2],[(lx-1,y-3),(rx+1,y-3),(rx+1,y+3),(lx-1,y+3)])
            d.line(surface,skin[3],(lx,y-2),(rx,y-2),1)
        else:
            d.line(surface,skin[2],(lx-1,y-2),(rx,y-2),1)
        if shape in ('narrow','monolid'):
            upper=0 if shape=='narrow' else -1
            lower=1
        if shape in ('hooded','heavy_lid','sleepy'):
            upper=0
        polygon=[(lx,y+yleft),(lx+1,y+upper),(rx-1,y+upper),(rx,y+yright),(rx-1,y+lower),(lx+1,y+lower)]
        d.polygon(surface,white,polygon)
        iris_y=y-1 if upper<0 else y
        iris_h=3 if upper<0 else 2
        d.rect(surface,eye[0],(cx,iris_y,2,iris_h))
        d.rect(surface,eye[1],(cx+1,y,1,max(1,lower)))
        d.rect(surface,outline,(cx+1,y,1,1))
        d.rect(surface,white,(cx,iris_y,1,1))
        d.lines(surface,outline,False,polygon[:4],1)
        d.line(surface,skin[2],(lx+1,y+lower+1),(rx-1,y+lower+1),1)
        if p['eyes']['lid']:
            d.line(surface,skin[2] if p['eyes']['lid']==1 else skin[3],(lx+1,y-3),(rx-1,y-3),1)
        if shape=='hooded':d.line(surface,skin[3],(lx+1,y-2),(rx-1,y-2),1)
        elif shape=='monolid':d.line(surface,skin[2],(lx,y-1),(rx,y-1),1)
        elif shape=='heavy_lid':d.line(surface,skin[3],(lx+1,y-1),(rx-1,y-1),2)
        elif shape=='sharp':d.line(surface,outline,(lx if side<0 else rx,y-1),(lx-1 if side<0 else rx+1,y-2),1)
        brow=p['brows']
        by=y-4-(1 if shape in ('round','wide') else 0)
        bw=brow['width']
        bx=cx-bw//2
        bcolor=_mix(hair[1],skin[3],.25)
        d.lines(surface,bcolor,False,[(bx,by),(cx,by-brow['arch']),(bx+bw,by+side//2)],brow['thick'])
        if spec.brows.endswith('broken'):d.rect(surface,skin[1],(bx+2,by-1,1,3))


def _draw_portrait_v2(spec: PortraitSpec):
    """Build reusable silhouette, face, hair and clothing masks at 64px."""
    import pygame as pg

    if spec.version != 2:
        raise ValueError("Unsupported portrait renderer version")
    c = _catalog(2)
    p = {part: c["parts"][part][getattr(spec, part)] for part in _PARTS}
    skin = tuple(tuple(v) for v in c["palettes"]["skin"][spec.skin_palette]["colors"])
    hair = tuple(tuple(v) for v in c["palettes"]["hair"][spec.hair_palette]["colors"])
    eye = tuple(tuple(v) for v in c["palettes"]["eye"][spec.eye_palette]["colors"])
    cloth = tuple(tuple(v) for v in c["palettes"]["cloth"][spec.cloth_palette]["colors"])
    if spec.age_stage == "elder":
        hair = tuple(_mix(color, target, .72) for color, target in zip(hair, ((222, 222, 208), (158, 162, 157), (91, 97, 97))))
    outline = _mix(skin[3], (23, 27, 34), .5)
    surface = pg.Surface((64, 64), pg.SRCALPHA)
    from worldseed.presentation.portrait_layers import (skin_overlays, accessory_overlay, cloth_overlay, shade_planes)
    palettes = dict(skin=skin, hair=hair, eye=eye, cloth=cloth,
                    ink=tuple(tuple(v) for v in c["palettes"]["ink"][spec.ink_palette]["colors"]),
                    metal=tuple(tuple(v) for v in c["palettes"]["metal"][spec.metal_palette]["colors"]))
    d = pg.draw
    x = 32
    hw = p["head"]["width"] - (1 if spec.age_stage == "youth" else 0)
    hh = p["head"]["height"]
    top, chin = 29 - hh, 29 + hh + p["jaw"]["chin"]
    left, right = x - hw, x + hw
    jaw = max(6, hw - 4 + p["jaw"]["width"])
    cheek = p["head"]["cheek"]
    style = p["hair"]["style"]

    geometry = dict(x=x,hw=hw,hh=hh,top=top,chin=chin,left=left,right=right,jaw=jaw,
                    ey=26+spec.eye_height,spacing=7+spec.eye_spacing,neck=p["neck"]["width"],
                    shoulders=p["bust"]["width"],my=39)
    _hair_back_v2(pg,surface,style,hair,cloth,geometry)
    if p["bust"]["style"] == "hood":
        d.polygon(surface,cloth[2],[(left-6,51),(left-6,18),(left-2,top-4),(x,top-6),(right+3,top-3),(right+6,19),(right+7,53),(right,55),(right+2,21),(right-1,top+3),(left+2,top+3),(left-2,21),(left,53)])
        d.lines(surface,cloth[0],False,[(left-5,47),(left-4,19),(left-1,top-2),(x-2,top-4)],1)

    # Shoulders, garments and neck are independent composite parts. Clothing
    # is stable cosmetic identity and never claims an unseen occupation.
    shoulders = p["bust"]["width"] - (2 if spec.age_stage == "youth" else 0)
    garment = [(x-shoulders,64),(x-shoulders+2,56),(x-14,50),(x-8,48),(x+8,48),(x+15,51),(x+shoulders-2,57),(x+shoulders,64)]
    d.polygon(surface,outline,garment)
    inner = [(px,py+1 if py<60 else py) for px,py in garment]
    d.polygon(surface,cloth[1],inner)
    d.polygon(surface,cloth[0],[(x-shoulders+4,57),(x-12,52),(x-5,52),(x-7,64),(x-shoulders+1,64)])
    d.polygon(surface,cloth[2],[(x+9,51),(x+shoulders-3,57),(x+shoulders,64),(x+4,64)])
    cloth_mask=pg.Surface((64,64),pg.SRCALPHA)
    d.polygon(cloth_mask,(255,255,255,255),garment)
    neck = p["neck"]["width"] - (1 if spec.age_stage == "youth" else 0)
    d.polygon(surface,outline,[(x-neck,chin-5),(x+neck,chin-5),(x+neck+1,51),(x+4,57),(x-4,57),(x-neck-1,51)])
    d.polygon(surface,skin[1],[(x-neck+1,chin-5),(x+neck-1,chin-5),(x+neck,51),(x+3,55),(x-3,55),(x-neck,51)])
    d.polygon(surface,skin[2],[(x+1,chin-4),(x+neck-1,chin-4),(x+neck,51),(x+3,55),(x,53)])
    d.line(surface,skin[0],(x-neck+2,47),(x-neck+2,50))
    garment_style = p["bust"]["style"]
    if garment_style in ("collar", "layered"):
        d.polygon(surface,cloth[2],[(x-10,48),(x-3,55),(x,59),(x-8,56),(x-13,52)])
        d.polygon(surface,cloth[0],[(x+10,48),(x+4,55),(x,59),(x+10,55),(x+13,52)])
        d.lines(surface,cloth[0],False,[(x-11,49),(x-6,55),(x-2,57)],1)
    elif garment_style in ("mantle", "shawl"):
        d.polygon(surface,cloth[2],[(x-14,49),(x-7,51),(x+10,59),(x+4,64),(x-7,57),(x-19,57)])
        d.lines(surface,cloth[0],False,[(x-15,51),(x-8,53),(x+9,60)],1)
        d.circle(surface,(185,160,99),(x+9,58),2)
        d.rect(surface,(226,204,139),(x+8,57,1,1))
    else:
        d.lines(surface,cloth[2],False,[(x-8,50),(x-4,56),(x,58),(x+5,56),(x+8,50)],2)
        d.lines(surface,cloth[0],False,[(x-7,51),(x-3,56),(x,57)],1)
    if garment_style == "layered":
        d.line(surface,cloth[0],(x,59),(x,64),1)
        d.rect(surface,(194,170,108),(x-1,60,2,2))
    for sx in (-1,1):
        d.line(surface,cloth[2],(x+sx*(shoulders-7),59),(x+sx*(shoulders-5),63),1)

    neck_mask=pg.Surface((64,64),pg.SRCALPHA)
    d.polygon(neck_mask,(255,255,255,255),[(x-neck+1,chin-5),(x+neck-1,chin-5),(x+neck,51),(x+3,55),(x-3,55),(x-neck,51)])
    cloth_mask.blit(neck_mask,(0,0),special_flags=pg.BLEND_RGBA_SUB)
    geometry.update(neck=neck,shoulders=shoulders)
    _garment_v2(pg,surface,p["bust"]["style"],cloth,skin,geometry)
    # Raised collars/wraps occlude parts of the anatomical neck. Retain only
    # exposed skin for ink; move covered neck pixels into the textile mask.
    anatomical_neck=neck_mask.copy()
    neck_mask.fill((0,0,0,0))
    for py in range(max(0,chin-5),57):
        for px in range(x-neck-1,x+neck+2):
            if anatomical_neck.get_at((px,py)).a and tuple(surface.get_at((px,py))[:3]) in skin:
                neck_mask.set_at((px,py),(255,255,255,255))
    covered_neck=anatomical_neck.copy()
    covered_neck.blit(neck_mask,(0,0),special_flags=pg.BLEND_RGBA_SUB)
    cloth_mask.blit(covered_neck,(0,0))
    cloth_overlay(pg,surface,cloth_mask,spec=spec,parts=p,palettes=palettes,geometry=geometry)

    # Ears are separate parts, with inner cartilage and a lit outer rim.
    ear = p["ears"]
    for side in (-1,1):
        ex, ey = x + side*hw, 26-ear["lift"]
        ew, eh = ear["width"], ear["height"]
        if spec.ears.endswith("pointed"):
            pts=[(ex-side,ey-2),(ex+side*(ew+2),ey-3),(ex+side*ew,ey+eh-2),(ex,ey+eh)]
            d.polygon(surface,outline,pts)
            d.polygon(surface,skin[1],[(ex,ey-1),(ex+side*(ew+1),ey-2),(ex+side*(ew-1),ey+eh-2),(ex,ey+eh-1)])
        else:
            rect=(ex-ew if side<0 else ex-1,ey,ew+2,eh)
            d.ellipse(surface,outline,rect)
            d.ellipse(surface,skin[1],(rect[0]+1,ey+1,ew,eh-2))
        d.line(surface,skin[2],(ex+side,ey+2),(ex+side,ey+eh-3),1)
        if side<0:d.rect(surface,skin[0],(ex-1,ey+1,1,2))

    temple=p["head"]["temple"]
    face_shape=[(x-5,top),(x+5,top),(right-2+temple,top+4),(right,21),(right,29),(right-1+cheek,34),(x+jaw,chin-5),(x+4,chin-1),(x,chin),(x-4,chin-1),(x-jaw,chin-5),(left+1-cheek,34),(left,29),(left,21),(left+2-temple,top+4)]
    mask=pg.Surface((64,64),pg.SRCALPHA)
    d.polygon(mask,(255,255,255,255),face_shape)
    neck_mask.blit(mask,(0,0),special_flags=pg.BLEND_RGBA_SUB)
    face=pg.Surface((64,64),pg.SRCALPHA)
    shade_planes(pg,face,spec=spec,part=p["shading"],skin=skin,geometry=geometry)
    face.blit(mask,(0,0),special_flags=pg.BLEND_RGBA_MULT)
    surface.blit(face,(0,0))
    d.lines(surface,outline,False,face_shape[3:13],1)
    # Rasterized chin outlines can extend a pixel past the filled face mask.
    # Such edge pixels are contour, not exposed neck suitable for tattoo ink.
    for py in range(max(0,chin-5),57):
        for px in range(x-neck-1,x+neck+2):
            if neck_mask.get_at((px,py)).a and tuple(surface.get_at((px,py))[:3]) not in skin:
                neck_mask.set_at((px,py),(0,0,0,0))

    ey=26+spec.eye_height
    spacing=7+spec.eye_spacing
    _eyes_v2(pg,surface,spec,p,skin,hair,eye,geometry)

    # Independent nose bridge, tip, nostrils and philtrum.
    nose=p["nose"]
    ny=ey+1
    bottom=ny+nose["length"]
    nw=nose["width"]
    bridge=nose["bridge"]
    d.polygon(surface,skin[2],[(x+1,ny),(x+2+bridge,ny+3),(x+nw,bottom),(x+1,bottom+1),(x,bottom-1)])
    d.line(surface,skin[0],(x-1,ny),(x-1+bridge,bottom-2),1)
    d.line(surface,skin[0],(x-1,bottom-1),(x+1,bottom-1),1)
    d.line(surface,skin[3],(x-nw,bottom),(x-1,bottom+1),1)
    d.rect(surface,skin[3],(x+nw-1,bottom,1,1))
    if nose["tip"]>0:d.rect(surface,skin[0],(x-1,bottom-1,3,1))
    d.line(surface,skin[2],(x,bottom+2),(x,bottom+3),1)
    mouth=p["mouth"]
    my=max(39,bottom+4)
    my=min(my,chin-4)
    mw=mouth["width"]
    lip=_mix(skin[2],(135,69,71),.32)
    mouth_left=x-mw//2
    mouth_right=mouth_left+mw
    d.line(surface,lip,(mouth_left,my),(x-1,my-mouth["curve"]),1)
    d.line(surface,lip,(x,my-mouth["curve"]),(mouth_right,my),1)
    d.line(surface,skin[3],(mouth_left+1,my+1),(mouth_right-1,my+1),1)
    if mouth["fullness"]:
        d.line(surface,_mix(lip,skin[0],.3),(mouth_left+1,my+2),(mouth_right-1,my+2),1)
        if mouth["fullness"]==2:d.line(surface,lip,(x-2,my-1),(x+2,my-1),1)
    d.line(surface,skin[0],(x-3,my+3),(x+2,my+3),1)

    if spec.age_stage=="elder":
        for side in (-1,1):
            ex=x+side*spacing
            d.line(surface,skin[2],(ex+side*3,ey+2),(ex+side*5,ey+3),1)
            d.line(surface,skin[2],(x+side*4,36),(x+side*6,my+1),1)
        d.line(surface,skin[2],(x-6,19),(x+4,19),1)
        d.line(surface,skin[0],(x-4,18),(x+3,18),1)
        d.line(surface,skin[2],(x-3,chin-2),(x+3,chin-2),1)

    geometry.update(ey=ey,spacing=spacing,my=my,nose_bottom=bottom)
    skin_mask=mask.copy()
    skin_mask.blit(neck_mask,(0,0))
    skin_overlays(pg,surface,skin_mask,face_mask=mask,neck_mask=neck_mask,
                  spec=spec,parts=p,palettes=palettes,geometry=geometry)

    # Facial hair is a reusable mask layer, never an entire precolored sprite.
    beard=p["facial_hair"]["style"] if spec.age_stage!="youth" else "none"
    if beard in ("full_beard","forked_beard","short_beard","braided_beard"):
        length=5 if beard=="short_beard" else 11 if beard=="forked_beard" else 8
        end=chin+length-4
        beard_pts=[(left+2,33),(left+5,39),(x-6,my+3),(x,my+4),(x+6,my+3),(right-3,35),(right-3,42),(x+7,end-1),(x+2,end),(x,end-2 if beard=="forked_beard" else end),(x-3,end),(x-8,end-2),(left+3,42)]
        d.polygon(surface,hair[2],beard_pts)
        d.lines(surface,hair[1],False,[(left+4,35),(left+6,42),(x-5,end-3),(x-2,end-1)],2)
        for bx in range(x-5,x+6,3):d.line(surface,hair[1],(bx,my+5),(bx+1,end-2),1)
        d.lines(surface,hair[0],False,[(left+5,38),(left+7,44),(x-4,end-3)],1)
    elif beard=="goatee":
        d.polygon(surface,hair[2],[(x-4,my+4),(x+4,my+4),(x+3,chin+2),(x,chin+5),(x-3,chin+2)])
        d.line(surface,hair[0],(x-2,my+5),(x-1,chin+2),1)
    elif beard=="van_dyke":
        d.polygon(surface,hair[2],[(x-3,my+5),(x+3,my+5),(x+2,chin+2),(x,chin+6),(x-2,chin+2)])
        d.line(surface,hair[0],(x-1,my+6),(x,chin+2),1)
        d.lines(surface,hair[1],False,[(x-8,my-1),(x-4,my-2),(x-1,my)],1)
        d.lines(surface,hair[1],False,[(x+1,my),(x+4,my-2),(x+8,my-1)],1)
    elif beard=="stubble":
        for yy in range(my+3,chin-1,2):
            for xx in range(x-jaw+3,x+jaw-2,3):
                if (xx+yy)%3:d.rect(surface,_mix(hair[1],skin[1],.35),(xx,yy,1,1))
        for side in (-1,1):d.line(surface,_mix(hair[1],skin[1],.45),(x+side*(hw-3),33),(x+side*(hw-4),38),1)
    if beard in ("moustache","goatee","van_dyke","handlebar","full_beard","forked_beard","short_beard","braided_beard"):
        d.lines(surface,hair[2],False,[(x-6,my),(x-3,my-1),(x-1,my),(x+1,my),(x+3,my-1),(x+6,my)],2)
        d.line(surface,hair[0],(x-5,my-1),(x-2,my-1),1)
    if beard=="sideburns":
        for side in (-1,1):d.line(surface,hair[1],(x+side*(hw-2),28),(x+side*(hw-3),36),3)

    if beard == "chinstrap":
        d.lines(surface,hair[2],False,[(left+3,33),(left+4,40),(x-4,chin-1),(x,chin),(x+4,chin-1),(right-4,40),(right-3,33)],2)
        d.line(surface,hair[0],(x-3,chin-1),(x+2,chin-1),1)
    elif beard == "handlebar":
        for side in (-1,1):
            d.lines(surface,hair[2],False,[(x+side*5,my),(x+side*8,my+1),(x+side*9,my-1),(x+side*8,my-2)],2)
    elif beard == "braided_beard":
        for yy in range(chin-2,57,4):
            d.polygon(surface,hair[2],[(x-3,yy),(x+3,yy),(x+2,yy+4),(x-2,yy+4)])
            d.line(surface,hair[0],(x-2,yy),(x+1,yy+2),1)
        d.rect(surface,palettes["metal"][1],(x-2,56,4,2))
    _hair_front_v2(pg,surface,style,hair,skin,geometry)
    accessory_overlay(pg,surface,spec=spec,parts=p,palettes=palettes,geometry=geometry)
    return surface


def _draw_portrait(spec: PortraitSpec):
    if spec.version == 1:
        return _draw_portrait_v1(spec)
    if spec.version == 2:
        return _draw_portrait_v2(spec)
    raise ValueError("Unsupported portrait renderer version")


def render_portrait(spec: PortraitSpec, size: int = 128):
    """Render a transparent pixel-art bust; callers can cache the surface."""
    import pygame as pg
    if type(size) is not int or not 16 <= size <= MAX_PORTRAIT_SIZE:
        raise ValueError("Portrait size must be an integer between 16 and 512")
    base = _draw_portrait(spec)
    return base if size == 64 else pg.transform.scale(base, (size, size))


class PortraitComposer:
    """Bounded LRU of complete portraits: repeated frames do no mask work."""
    def __init__(self, max_entries: int = 96, max_bytes: int = 16 * 1024 * 1024):
        if type(max_entries) is not int or not 1 <= max_entries <= 512:
            raise ValueError("Portrait cache capacity must be between 1 and 512")
        if type(max_bytes) is not int or not 1024 <= max_bytes <= 64 * 1024 * 1024:
            raise ValueError("Portrait cache byte limit must be between 1KiB and 64MiB")
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self._cache_bytes = 0
        self._surfaces: OrderedDict[tuple[PortraitSpec, int], Any] = OrderedDict()
        self.render_count = 0

    @property
    def cache_size(self) -> int:
        return len(self._surfaces)

    @property
    def cache_bytes(self) -> int:
        return self._cache_bytes

    def render(self, spec: PortraitSpec, size: int = 128):
        if type(size) is not int or not 16 <= size <= MAX_PORTRAIT_SIZE:
            raise ValueError("Portrait size must be an integer between 16 and 512")
        key = (spec, size)
        if key in self._surfaces:
            self._surfaces.move_to_end(key)
            return self._surfaces[key]
        surface = render_portrait(spec, size)
        self.render_count += 1
        image_bytes = surface.get_pitch() * surface.get_height()
        if image_bytes > self.max_bytes:
            return surface
        while self._surfaces and (len(self._surfaces) >= self.max_entries or self._cache_bytes + image_bytes > self.max_bytes):
            _, previous = self._surfaces.popitem(last=False)
            self._cache_bytes -= previous.get_pitch() * previous.get_height()
        self._surfaces[key] = surface
        self._cache_bytes += image_bytes
        return surface

    def clear(self) -> None:
        self._surfaces.clear()
        self._cache_bytes = 0
