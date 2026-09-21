from __future__ import annotations
from worldseed.content.registry import ContentRegistry, SpeciesDef
from worldseed.core.rng import PCG32, derive_seed

PREFIX=["Ash","Gloom","Thorn","Frost","Mire","Stone","Dusk","Ember","Hollow","Pale","Iron","Moss","Night","Red","Glass"]
SUFFIX=["stalker","maw","crawler","grazer","hulk","lurker","runner","shell","fang","back","horn","wretch","drake","walker"]
COVER=["scaled","furred","plated","leathery","spined","downy"]

def install_procedural_species(registry:ContentRegistry,seed:bytes,count:int=8)->list[str]:
    created=[]
    niches=[("herbivore",("grass","forest"),0), ("herbivore",("tundra",),5), ("omnivore",("scrub","grass"),20), ("carnivore",("forest","grass"),65), ("carnivore",("underground",),72), ("omnivore",("underground",),45)]
    for i in range(count):
        rng=PCG32(derive_seed(seed,"generated-species",i));diet,habitats,base_agg=niches[i%len(niches)]
        name=f"{rng.choice(PREFIX)}{rng.choice(SUFFIX)}";sid=f"world:{name.lower()}:{i}"
        mass=4+rng.randbelow(190);hp=max(8,int(mass**0.65)*2+rng.randbelow(15));damage=max(1,int(mass**0.45)+rng.randbelow(5));aggression=max(0,min(100,base_agg+rng.randbelow(25)-10))
        reproduction=6+rng.randbelow(35);mortality=6+rng.randbelow(20);capacity=max(8,26000//max(20,mass))
        # viability: large carnivores get smaller capacities/reproduction to avoid impossible predator worlds
        if diet=="carnivore":capacity=max(5,capacity//3);reproduction=min(reproduction,18)
        body_plan=rng.choice([{"torso":55,"head":15,"limbs":30},{"core":65,"head":10,"limbs":25},{"thorax":50,"abdomen":25,"limbs":25}])
        covering=rng.choice(COVER);display=name[0].upper()+name[1:]
        attack_name=rng.choice(["raking bite","lunging strike","horn thrust","clawing rush","body slam","defensive kick"])
        dtype="bite" if diet=="carnivore" else rng.choice(["blunt","pierce","bite"])
        attack=({"name":attack_name,"damage":damage,"type":dtype,"bleeding":2 if dtype in ("bite","pierce") else 0,"fracture":10 if dtype=="blunt" and mass>70 else 0},)
        carcass={"core:raw_game_meat":max(1,mass//12),"core:fresh_hide":1 if mass>=3 else 0,"core:bone":max(1,mass//25),"core:animal_fat":max(0,mass//30),"core:offal":max(1,mass//35),"core:sinew":1 if mass>=8 else 0}
        desc=f"A {covering} {diet} adapted to {', '.join(habitats).replace('underground','deep caves')}."
        flavor=f"Its silhouette is unfamiliar; only time and observation will make its habits predictable."
        temp_lo=7000 if 'tundra' in habitats else 12000;temp_hi=48000 if 'tundra' in habitats else 60000
        moist_lo=18000 if 'scrub' in habitats else 0;moist_hi=65535
        sp=SpeciesDef(sid,display,rng.choice(["m","M","q","Q","s"]),diet,mass,hp,damage,aggression,1+rng.randbelow(3),reproduction,mortality,capacity,tuple(habitats),{},body_plan,desc,flavor,temp_lo,temp_hi,moist_lo,moist_hi,1,max(1,1+rng.randbelow(4)),attack,carcass)
        # validator constraints
        if sp.carrying_capacity<=0 or sp.max_hp<=0 or sp.reproduction>50:continue
        registry.species[sid]=sp;created.append(sid)
    return created
