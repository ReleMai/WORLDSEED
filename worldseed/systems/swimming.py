"""Bounded player swimming rules; terrain and bridges remain world authorities."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class WaterExposure:
    mode: str = 'dry'
    depth: str = ''
    salinity: str = ''

def exposure(sim, pos):
    structure=sim.building.structure_at(pos)
    if structure:
        definition=sim.registry.structures[structure.structure_id]
        if definition.passable and 'bridge' in definition.tags:return WaterExposure()
    terrain=sim.world.tile_at(pos).terrain
    tags=set(terrain.tags)
    fluid=sim.environment.fluid_at(pos)
    if fluid and fluid.fluid=='water' and fluid.amount>=120:
        return WaterExposure('swimming' if fluid.amount>=220 else 'wading','floodwater','fresh')
    if 'water' not in tags:return WaterExposure()
    salt='salt' if 'saltwater' in tags else 'brackish' if 'brackish' in tags else 'fresh' if 'water_source' in tags else 'unknown'
    return WaterExposure('wading' if 'shallow' in tags else 'swimming',
                         'shallows' if 'shallow' in tags else 'swimming depth',salt)

def stroke_cost(sim, pos, dx, dy):
    skill=max(0,min(10,sim.player_skill('swimming')))
    endurance=max(1,min(20,sim.player_attribute('endurance')))
    from worldseed.entities.components import Inventory
    inv=sim.entities.get(sim.player_id,Inventory)
    mass=sum(sim.registry.items[i].mass_g*n for i,n in inv.items.items() if i in sim.registry.items)
    cost=10 + min(12,mass//5000) - skill//2 - endurance//3
    current=sim.world.current_at(pos,prepared_only=True)
    if current and current.flowing:
        alignment=dx*current.dx+dy*current.dy
        cost+=current.speed//22 if alignment<0 else -(current.speed//40) if alignment>0 else current.speed//45
    if 'rapids' in sim.world.tile_at(pos).terrain.tags:cost+=4
    return max(3,cost)

def practice(sim):
    level=sim.player_skill('swimming')
    if level>=10:return
    sim.state.player_swimming_xp+=1
    threshold=20+level*10
    if sim.state.player_swimming_xp>=threshold:
        sim.state.player_swimming_xp-=threshold
        sim.state.player_skills['swimming']=level+1
        sim._message(f'Swimming improves to {level+1}. Your strokes become more efficient.')
