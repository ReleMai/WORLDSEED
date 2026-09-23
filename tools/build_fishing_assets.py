from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "worldseed" / "assets" / "sprites"
ITEMS = ASSETS / "items"
RES = ASSETS / "resources"
SPECIES = ASSETS / "species"
S = 64


def canvas():
    return Image.new("RGBA", (S, S), (0, 0, 0, 0))


def save(im, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, optimize=True)


def fish_icon(body, accent, stripe=False, flat=False, long=False):
    im=canvas();d=ImageDraw.Draw(im)
    if flat:
        d.ellipse((14,25,48,43),fill=body,outline=(34,38,37,255),width=2)
        d.polygon([(14,31),(5,22),(7,38)],fill=body)
        d.polygon([(31,25),(38,16),(40,27)],fill=accent)
    elif long:
        d.ellipse((12,23,52,41),fill=body,outline=(34,38,37,255),width=2)
        d.polygon([(13,29),(4,20),(6,42)],fill=body)
        d.polygon([(34,23),(42,15),(44,25)],fill=accent)
    else:
        d.ellipse((15,22,50,43),fill=body,outline=(34,38,37,255),width=2)
        d.polygon([(16,29),(5,20),(7,44)],fill=body)
        d.polygon([(31,22),(38,14),(42,24)],fill=accent)
        d.polygon([(31,43),(39,50),(42,41)],fill=accent)
    d.ellipse((43,27,47,31),fill=(235,235,214,255))
    d.ellipse((45,28,47,30),fill=(20,22,22,255))
    if stripe:
        for x in (24,31,38):
            d.line((x,24,x-2,41),fill=accent,width=2)
    d.line((48,34,55,34),fill=(30,34,34,255),width=1)
    return im


def plant_icon(kind):
    im=canvas();d=ImageDraw.Draw(im)
    if kind=="duckweed":
        for x,y in [(18,28),(27,22),(35,30),(43,24),(30,38),(20,40)]:
            d.ellipse((x-5,y-3,x+5,y+3),fill=(68,137,71,255),outline=(35,79,45,255))
    elif kind=="water_lily_root":
        d.polygon([(18,39),(26,28),(44,29),(50,37),(41,45),(26,46)],fill=(177,137,75,255),outline=(94,70,41,255))
        d.ellipse((17,15,45,35),fill=(68,137,71,255),outline=(35,79,45,255))
        d.polygon([(31,15),(31,26),(43,25)],fill=(0,0,0,0))
    elif kind=="pickerelweed":
        for x in (24,31,38):
            d.line((x,45,x,20),fill=(59,116,61,255),width=3)
            d.ellipse((x-7,25,x+2,34),fill=(71,143,75,255))
        for x,y in [(23,18),(29,15),(35,18),(39,14)]:
            d.ellipse((x-2,y-2,x+2,y+2),fill=(112,94,176,255))
    elif kind=="saltmarsh_grass":
        for x in range(17,48,4):
            d.line((32,49,x,18+(x%3)*4),fill=(119,145,70,255),width=2)
    elif kind=="eelgrass":
        for off in (-12,-6,0,6,12):
            d.arc((21+off//2,12,43+off//2,54),180,330,fill=(44,121,77,255),width=3)
    elif kind=="kelp":
        d.line((31,53,31,14),fill=(92,92,44,255),width=4)
        for y,side in [(20,-1),(27,1),(34,-1),(41,1)]:
            if side<0:d.ellipse((15,y-5,31,y+4),fill=(86,126,48,255))
            else:d.ellipse((31,y-5,49,y+4),fill=(86,126,48,255))
    elif kind=="beachgrass":
        for x in range(18,47,5):
            d.line((32,51,x,19+(x%4)*3),fill=(151,145,77,255),width=2)
    elif kind=="blue_mussels":
        for x,y in [(23,30),(34,24),(41,36),(28,41)]:
            d.ellipse((x-6,y-9,x+6,y+9),fill=(55,70,82,255),outline=(113,130,139,255),width=2)
    return im


def gear_icon(kind):
    im=canvas();d=ImageDraw.Draw(im)
    if kind in {"reed_rod","wood_rod"}:
        color=(133,101,52,255) if kind=="wood_rod" else (151,139,77,255)
        d.arc((8,7,57,61),200,320,fill=color,width=4)
        d.line((45,23,49,48),fill=(205,205,185,255),width=1)
        d.ellipse((46,47,51,52),outline=(180,151,78,255),width=1)
    elif "line" in kind:
        colors={"fiber_line":(185,162,102,255),"sinew_line":(160,126,95,255),"braided_line":(116,93,71,255)}
        d.ellipse((15,15,49,49),outline=colors[kind],width=4)
        d.ellipse((23,23,41,41),outline=colors[kind],width=3)
        if kind=="braided_line":d.arc((12,12,52,52),20,280,fill=(210,190,140,255),width=1)
    elif kind=="fishing_spear":
        d.line((10,51,49,12),fill=(130,90,48,255),width=4)
        d.polygon([(49,12),(56,7),(52,16)],fill=(175,180,174,255))
        d.polygon([(49,12),(57,13),(52,17)],fill=(175,180,174,255))
    elif kind=="fishing_net":
        d.ellipse((17,15,50,48),outline=(174,151,94,255),width=3)
        for x in range(22,48,7):d.line((x,18,x-5,45),fill=(144,126,84,255),width=1)
        for y in range(22,46,7):d.line((18,y,47,y-4),fill=(144,126,84,255),width=1)
        d.line((17,45,8,55),fill=(124,90,52,255),width=4)
    elif kind=="spoon_lure":
        d.ellipse((20,17,42,47),fill=(180,112,62,255),outline=(230,169,91,255),width=2)
        d.line((31,47,31,55),fill=(150,150,145,255),width=1)
        d.arc((28,51,36,59),0,270,fill=(190,190,185,255),width=2)
    elif kind=="earthworms":
        d.arc((10,17,52,48),15,175,fill=(151,86,75,255),width=5)
        d.arc((14,25,48,55),190,350,fill=(173,99,84,255),width=4)
    return im


def resource_sprite(kind):
    im=canvas();d=ImageDraw.Draw(im)
    if kind=="earthworm_patch":
        d.ellipse((8,31,56,57),fill=(99,73,49,150))
        d.arc((15,27,42,49),10,170,fill=(166,91,78,255),width=4)
        d.arc((28,33,55,53),170,340,fill=(145,78,70,255),width=4)
        return im
    if kind=="blue_mussel_bed":
        im.alpha_composite(plant_icon("blue_mussels"))
        return im
    icon_kind={
        "duckweed_mat":"duckweed","water_lily_patch":"water_lily_root",
        "pickerelweed_patch":"pickerelweed","saltmarsh_grass_patch":"saltmarsh_grass",
        "eelgrass_bed":"eelgrass","kelp_bed":"kelp","beachgrass_patch":"beachgrass"
    }[kind]
    base=plant_icon(icon_kind)
    im.alpha_composite(base)
    d=ImageDraw.Draw(im)
    if kind in {"duckweed_mat","eelgrass_bed","kelp_bed"}:
        d.line((5,54,59,54),fill=(68,129,142,130),width=2)
    return im


def animal_sprite(kind):
    im=canvas();d=ImageDraw.Draw(im)
    outline=(33,36,35,255)
    if kind=="muskrat":
        d.ellipse((15,28,47,47),fill=(93,72,55,255),outline=outline,width=2);d.ellipse((39,25,53,38),fill=(101,77,57,255),outline=outline)
        d.line((15,40,5,47),fill=(72,54,43,255),width=2);d.ellipse((47,29,50,32),fill=(15,15,15,255))
    elif kind=="beaver":
        d.ellipse((11,25,48,48),fill=(105,76,48,255),outline=outline,width=2);d.ellipse((39,23,54,37),fill=(116,83,52,255),outline=outline)
        d.ellipse((3,34,15,49),fill=(80,58,44,255),outline=outline);d.line((52,34,56,36),fill=(235,224,190,255),width=2)
    elif kind=="river_otter":
        d.ellipse((10,29,50,43),fill=(82,64,49,255),outline=outline,width=2);d.ellipse((43,24,56,36),fill=(91,70,52,255),outline=outline)
        d.line((12,36,3,42),fill=(72,55,43,255),width=4);d.ellipse((50,28,52,30),fill=(20,20,20,255))
    elif kind=="great_blue_heron":
        d.ellipse((25,32,43,48),fill=(99,112,119,255),outline=outline);d.line((34,33,39,13),fill=(112,121,126,255),width=4)
        d.ellipse((35,9,44,17),fill=(119,129,134,255),outline=outline);d.line((43,12,57,14),fill=(185,148,71,255),width=2)
        d.line((31,47,28,59),fill=(162,135,70,255),width=2);d.line((38,47,40,59),fill=(162,135,70,255),width=2)
    elif kind=="herring_gull":
        d.ellipse((19,28,45,43),fill=(211,211,199,255),outline=outline);d.polygon([(28,30),(10,20),(22,35)],fill=(169,174,176,255))
        d.ellipse((40,24,50,34),fill=(225,225,215,255),outline=outline);d.polygon([(49,28),(58,31),(49,33)],fill=(193,153,56,255))
    elif kind=="harbor_seal":
        d.ellipse((9,27,50,46),fill=(102,107,105,255),outline=outline,width=2);d.ellipse((42,24,56,37),fill=(112,116,113,255),outline=outline)
        d.polygon([(15,41),(4,49),(18,47)],fill=(91,96,94,255));d.ellipse((50,28,52,30),fill=(18,18,18,255))
    return im


def build():
    fish_specs={
        "brook_trout":((112,139,94,255),(220,113,62,255),True,False,False),
        "bluegill":((83,132,142,255),(218,172,69,255),True,False,False),
        "largemouth_bass":((86,117,70,255),(190,185,96,255),True,False,False),
        "channel_catfish":((105,111,104,255),(151,150,126,255),False,False,True),
        "common_carp":((153,119,68,255),(207,157,70,255),True,False,False),
        "northern_pike":((80,111,69,255),(184,199,133,255),True,False,True),
        "striped_bass":((121,137,142,255),(48,61,65,255),True,False,False),
        "summer_flounder":((142,116,76,255),(88,70,48,255),True,True,False),
        "striped_mullet":((149,157,148,255),(79,95,91,255),True,False,False),
        "atlantic_mackerel":((78,126,147,255),(40,73,88,255),True,False,False),
        "atlantic_cod":((129,115,90,255),(84,74,58,255),True,False,False),
        "red_drum":((164,104,70,255),(212,141,77,255),False,False,False),
    }
    for slug,(body,accent,stripe,flat,long) in fish_specs.items():
        save(fish_icon(body,accent,stripe,flat,long),ITEMS/f"{slug}.png")
    for slug in ("duckweed","water_lily_root","pickerelweed","saltmarsh_grass","eelgrass","kelp","beachgrass","blue_mussels"):
        save(plant_icon(slug),ITEMS/f"{slug}.png")
    for slug in ("earthworms","spoon_lure","reed_rod","wood_rod","fiber_line","sinew_line","braided_line","fishing_spear","fishing_net"):
        save(gear_icon(slug),ITEMS/f"{slug}.png")
    for slug in ("duckweed_mat","water_lily_patch","pickerelweed_patch","saltmarsh_grass_patch","eelgrass_bed","kelp_bed","earthworm_patch","beachgrass_patch","blue_mussel_bed"):
        save(resource_sprite(slug),RES/f"{slug}.png")
    for slug in ("muskrat","beaver","river_otter","great_blue_heron","herring_gull","harbor_seal"):
        save(animal_sprite(slug),SPECIES/slug/"variant_0.png")
    print("built fishing/ecology assets")


if __name__=="__main__":
    build()
