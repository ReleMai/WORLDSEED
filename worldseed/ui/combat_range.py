from __future__ import annotations

from math import hypot

from worldseed.core.coords import WorldPos
from worldseed.entities.components import Vitals
from worldseed.systems.state import pos_key


def difficulty_label(chance: int) -> str:
    chance=max(0,min(100,int(chance)))
    if chance>=80:return "easy"
    if chance>=65:return "favorable"
    if chance>=50:return "fair"
    if chance>=35:return "hard"
    return "very hard"


def _direction(origin: WorldPos, cursor: WorldPos) -> tuple[float,float]:
    dx=cursor.x-origin.x;dy=cursor.y-origin.y
    length=hypot(dx,dy)
    if length<=0.001:return (1.0,0.0)
    return (dx/length,dy/length)


def _inside_directional_sector(dx:int,dy:int,fx:float,fy:float) -> bool:
    # Broad hunting cone: the cursor rotates the sector while the weapon range
    # remains the hard physical boundary. The widening edge remains readable on
    # a square tile grid without pretending every cell is equally easy.
    dot=dx*fx+dy*fy
    if dot<=0:return False
    lateral=abs(dx*fy-dy*fx)
    return lateral<=0.75+dot*0.58


def ranged_overlay(sim, weapon, cursor:WorldPos, zone:str="center") -> dict:
    origin=sim.player_pos
    fx,fy=_direction(origin,cursor)
    perception=sim.player_attribute("perception")
    hunting=sim.player_skill("hunting")
    vitals=sim.entities.get(sim.player_id,Vitals)
    cells=[]
    creatures={(c.x,c.y,c.z):c for c in sim.state.creatures.values() if c.hp>0 and c.z==origin.z}
    for dy in range(-weapon.range,weapon.range+1):
        for dx in range(-weapon.range,weapon.range+1):
            distance=abs(dx)+abs(dy)
            if distance<1 or distance>weapon.range or not _inside_directional_sector(dx,dy,fx,fy):continue
            pos=origin.moved(dx,dy)
            if pos_key(pos.x,pos.y,pos.z) not in sim.discovered_tiles_set:continue
            target=creatures.get((pos.x,pos.y,pos.z))
            behavior=target.behavior if target else "calm"
            aim_quality=sim.state.player_aim_quality if target and sim.state.player_aim_target==target.uid and sim.state.player_aim_zone==zone else 0
            blocked=not sim._visible_from(origin,pos)
            chance=0 if blocked else sim.combat.ranged_hit_chance(
                weapon,distance,perception,hunting,zone,aim_quality,vitals.stamina,behavior
            )
            cells.append({
                "x":pos.x,"y":pos.y,"z":pos.z,"chance":chance,
                "difficulty":"blocked" if blocked else difficulty_label(chance),
                "blocked":blocked,
            })
    selected=next((c for c in cells if (c["x"],c["y"],c["z"])==(cursor.x,cursor.y,cursor.z)),None)
    return {
        "mode":"ranged","weapon_id":weapon.id,"weapon_name":weapon.name,
        "origin":(origin.x,origin.y,origin.z),"cursor":(cursor.x,cursor.y,cursor.z),
        "max_range":weapon.range,"zone":zone,"cells":cells,
        "cursor_difficulty":selected["difficulty"] if selected else "outside sector",
    }


def melee_overlay(sim, weapon, cursor:WorldPos) -> dict:
    origin=sim.player_pos
    reach=max(1,weapon.reach if weapon else 1)
    agility=sim.player_attribute("agility")
    melee=sim.player_skill("melee")
    vitals=sim.entities.get(sim.player_id,Vitals)
    cells=[]
    creatures={(c.x,c.y,c.z):c for c in sim.state.creatures.values() if c.hp>0 and c.z==origin.z}
    for dy in range(-reach,reach+1):
        for dx in range(-reach,reach+1):
            distance=abs(dx)+abs(dy)
            if distance<1 or distance>reach:continue
            pos=origin.moved(dx,dy)
            if pos_key(pos.x,pos.y,pos.z) not in sim.discovered_tiles_set:continue
            target=creatures.get((pos.x,pos.y,pos.z))
            behavior=target.behavior if target else "calm"
            blocked=distance>1 and not sim._visible_from(origin,pos)
            chance=0 if blocked else sim.combat.melee_hit_chance(weapon,distance,agility,melee,vitals.stamina,behavior)
            cells.append({
                "x":pos.x,"y":pos.y,"z":pos.z,"chance":chance,
                "difficulty":"blocked" if blocked else difficulty_label(chance),"blocked":blocked,
            })
    selected=next((c for c in cells if (c["x"],c["y"],c["z"])==(cursor.x,cursor.y,cursor.z)),None)
    return {
        "mode":"melee","weapon_id":weapon.id if weapon else "unarmed",
        "weapon_name":weapon.name if weapon else "Unarmed",
        "origin":(origin.x,origin.y,origin.z),"cursor":(cursor.x,cursor.y,cursor.z),
        "max_range":reach,"cells":cells,
        "cursor_difficulty":selected["difficulty"] if selected else "out of reach",
    }
