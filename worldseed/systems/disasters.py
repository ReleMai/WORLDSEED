from __future__ import annotations
from worldseed.core.rng import hash_u64
from worldseed.systems.state import LivingWorldState
from worldseed.systems.history import HistorySystem

class DisasterSystem:
    def __init__(self,state:LivingWorldState,seed:bytes,history:HistorySystem):self.state=state;self.seed=seed;self.history=history
    def monthly_update(self,minute:int)->None:
        month=minute//(30*1440)
        for town in self.state.settlements.values():
            roll=hash_u64(self.seed,'disaster',town.uid,month)%1000
            if roll<10 and town.stocks.get('core:iron_ore',0)>0:
                lost=max(1,town.stocks.get('core:iron_ore',0)//2);town.stocks['core:iron_ore']-=lost;town.stocks['core:coal']=max(0,town.stocks.get('core:coal',0)-lost//2)
                self.history.record('mine_collapse',f'A mine collapse near {town.name} destroyed {lost} units of ore supply.',minute,town.region_x,town.region_y,[town.uid],salience=55)
            elif roll<18:
                lost=max(1,town.stocks.get('core:wheat',0)//3);town.stocks['core:wheat']=max(0,town.stocks.get('core:wheat',0)-lost);town.food_stress=min(100,town.food_stress+15)
                self.history.record('drought',f'Drought reduced stores around {town.name}.',minute,town.region_x,town.region_y,[town.uid],salience=50)
