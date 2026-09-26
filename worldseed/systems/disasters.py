from __future__ import annotations
from worldseed.core.rng import hash_u64
from worldseed.systems.state import LivingWorldState
from worldseed.systems.history import HistorySystem


class DisasterSystem:
    def __init__(self,state:LivingWorldState,seed:bytes,history:HistorySystem):
        self.state=state;self.seed=seed;self.history=history
        self.route_planner=None;self.region_planner=None

    def attach_transport(self,route_planner,region_planner=None)->None:
        self.route_planner=route_planner
        self.region_planner=region_planner

    def monthly_update(self,minute:int)->None:
        month=minute//(30*1440)
        for town in self.state.settlements.values():
            roll=hash_u64(self.seed,'disaster',town.uid,month)%1000
            if roll<10 and town.stocks.get('core:iron_ore',0)>0:
                lost=max(1,town.stocks.get('core:iron_ore',0)//2)
                town.stocks['core:iron_ore']-=lost
                town.stocks['core:coal']=max(0,town.stocks.get('core:coal',0)-lost//2)
                self.history.record(
                    'mine_collapse',
                    f'A mine collapse near {town.name} destroyed {lost} units of ore supply.',
                    minute,town.region_x,town.region_y,[town.uid],salience=55,
                )
            elif roll<18:
                lost=max(1,town.stocks.get('core:wheat',0)//3)
                town.stocks['core:wheat']=max(0,town.stocks.get('core:wheat',0)-lost)
                town.food_stress=min(100,town.food_stress+15)
                self.history.record(
                    'drought',f'Drought reduced stores around {town.name}.',
                    minute,town.region_x,town.region_y,[town.uid],salience=50,
                )
            elif roll<30 and self.route_planner is not None and self.region_planner is not None:
                # Floods require physical water/flood opportunity. The disaster
                # roll decides timing; geography decides whether the event can
                # exist and which route/crossing is actually affected.
                plan=self.region_planner.plan(town.region_x,town.region_y,persist=True)
                water_strength=max((int(w.river_class) for w in plan.waters if w.water_kind!='ocean'),default=0)
                exposure=max(int(getattr(plan,'crossing_value',0)),water_strength*16)
                if exposure<28:
                    continue
                event_roll=int(hash_u64(self.seed,'regional-flood',town.uid,month)%100)
                if event_roll>=min(90,20+exposure):
                    continue
                severity=min(100,22+exposure//2+water_strength*7)
                affected=self.route_planner.apply_region_hazard(
                    (town.region_x,town.region_y),'flood',severity,minute
                )
                if not affected:
                    continue
                field_loss=min(town.stocks.get('core:wheat',0),max(1,severity//8))
                town.stocks['core:wheat']=max(0,town.stocks.get('core:wheat',0)-field_loss)
                town.food_stress=min(100,town.food_stress+max(2,severity//12))
                self.history.record(
                    'flood',
                    f'Flooding around {town.name} damaged fields, roads, and river crossings.',
                    minute,town.region_x,town.region_y,[town.uid,*affected],salience=62,
                )
