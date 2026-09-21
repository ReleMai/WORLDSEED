from __future__ import annotations
from worldseed.core.rng import hash_u64
from worldseed.systems.state import LivingWorldState
from worldseed.systems.history import HistorySystem

class LawSystem:
    def __init__(self,state:LivingWorldState,seed:bytes,history:HistorySystem):self.state=state;self.seed=seed;self.history=history
    def daily_update(self,minute:int)->None:
        for town in self.state.settlements.values():
            guard_count=sum(1 for n in self.state.npcs.values() if n.alive and n.settlement_id==town.uid and n.occupation=='guard')
            crime_pressure=max(0,town.food_stress + max(0,25-guard_count*5) - town.law.get('theft',30)//4)
            if hash_u64(self.seed,'crime',town.uid,minute//1440)%100<min(65,crime_pressure):
                candidates=[g for g,n in town.stocks.items() if n>2 and g!='core:copper_coin']
                if candidates:
                    good=candidates[hash_u64(self.seed,'crime-good',town.uid,minute//1440)%len(candidates)];qty=min(town.stocks[good],1+crime_pressure//20);town.stocks[good]-=qty
                    self.history.record('crime',f'Theft in {town.name}: {qty} {good} disappeared amid rising hardship.',minute,town.region_x,town.region_y,[town.uid],salience=20+crime_pressure//2)
            # severe law + enough guards occasionally records arrest, damping stress
            if town.food_stress>30 and guard_count and hash_u64(self.seed,'arrest',town.uid,minute//1440)%100<15:
                town.food_stress=max(0,town.food_stress-2);self.history.record('law',f'{town.name} guards arrested a suspected thief.',minute,town.region_x,town.region_y,[town.uid],salience=12)
