from __future__ import annotations
from worldseed.core.coords import WorldPos
from worldseed.core.rng import hash_u64
from worldseed.systems.state import LivingWorldState, NPCState
from worldseed.systems.history import HistorySystem
from worldseed.systems.pathfinding import local_path

class NPCSystem:
    def __init__(self,state:LivingWorldState,seed:bytes,history:HistorySystem,world=None,building=None,lod=None):
        self.state=state;self.seed=seed;self.history=history;self.world=world;self.building=building;self.lod=lod
        self.settlement_physicalization=None;self.settlement_population=None;self.economy=None;self.property_security=None;self.households=None;self.workplace_logistics=None;self.route_planner=None

    def attach_settlement_population(self,physicalization,population_binder)->None:
        self.settlement_physicalization=physicalization
        self.settlement_population=population_binder
    def attach_economy(self,economy)->None:self.economy=economy
    def attach_property_security(self,security)->None:self.property_security=security
    def attach_households(self,households)->None:self.households=households
    def attach_workplace_logistics(self,system)->None:self.workplace_logistics=system
    def attach_route_planner(self,system)->None:self.route_planner=system
    @staticmethod
    def _face_step(npc:NPCState,old_x:int,old_y:int)->None:
        dx=int(npc.x)-int(old_x);dy=int(npc.y)-int(old_y)
        npc.facing_dx=0 if dx==0 else (1 if dx>0 else -1)
        npc.facing_dy=0 if dy==0 else (1 if dy>0 else -1)

    def hourly_update(self,minute:int,player_pos:WorldPos)->None:
        for npc in self.state.npcs.values():
            if not npc.alive:continue
            if self.lod is not None:
                tier=self.lod.npc_tier(player_pos,npc)
                if not self.lod.should_update(tier,minute,"ai"):continue
            elif abs(npc.x-player_pos.x)+abs(npc.y-player_pos.y)>1200:continue
            town=self.state.settlements.get(npc.settlement_id)
            if not town:continue
            npc.hunger=min(100,npc.hunger+3);npc.thirst=min(100,npc.thirst+5);npc.rest=min(100,npc.rest+2)
            defaults={"social":20,"safety":15,"health":0,"faith":10,"learning":10,"purpose":20}
            for key,value in defaults.items():npc.needs.setdefault(key,value)
            npc.needs["social"]=min(100,npc.needs["social"]+2)
            npc.needs["health"]=min(100,max(npc.needs["health"],100-npc.hp)+(8 if npc.infections else 0))
            if npc.occupation=="priest":npc.needs["faith"]=min(100,npc.needs["faith"]+3)
            if npc.occupation=="scholar" or "curious" in npc.traits:npc.needs["learning"]=min(100,npc.needs["learning"]+2)
            if town.food_stress>55:npc.needs["safety"]=min(100,npc.needs["safety"]+2)
            if not npc.home_id:self._assign_property(npc,town)
            if not npc.tasks:self._choose_goal_and_plan(npc,town,minute)
            self._execute_task(npc,town,minute,player_pos)
    def _binding_destination(self,structure_id:str,room_id:str,town)->WorldPos:
        if self.settlement_physicalization is not None and structure_id:
            target=self.settlement_physicalization.destination_for(structure_id,room_id)
            if target is not None:return target
        return WorldPos(int(town.x),int(town.y),0)

    def _service_destination(self,town,functions)->WorldPos:
        if self.settlement_physicalization is not None:
            target=self.settlement_physicalization.destination_for_function(town.uid,functions)
            if target is not None:return target
        return WorldPos(int(town.x),int(town.y),0)

    def _routine_bias(self,npc:NPCState,minute:int)->dict[str,int]:
        """Soft daily rhythm. Urgent needs still override these preferences."""
        hour=(int(minute)%1440)//60
        out={"eat":0,"rest":0,"work":0,"socialize":0,"guard":0,"worship":0,"learn":0}
        if npc.age<16:
            if 8<=hour<15:out["learn"]+=55
            if 16<=hour<20:out["socialize"]+=45
            if hour>=21 or hour<7:out["rest"]+=100
            return out
        if npc.occupation=="guard":
            shift=int(hash_u64(self.seed,"guard-shift",npc.uid)%3)
            start=(0,8,16)[shift]
            active=((hour-start)%24)<8
            if active:out["guard"]+=90
            else:out["rest"]+=35
        else:
            start,end={
                "farmer":(6,15),"herder":(6,15),"merchant":(8,18),
                "healer":(7,18),"scholar":(9,17),"priest":(7,15),
                "miner":(7,16),"hunter":(6,14),
            }.get(npc.occupation,(8,17))
            if start<=hour<end:out["work"]+=55
        if hour in (7,12,18):out["eat"]+=55
        if 18<=hour<21:
            out["socialize"]+=45
            if npc.occupation=="priest" or npc.needs.get("faith",0)>45:out["worship"]+=35
        if npc.occupation=="scholar" and 17<=hour<20:out["learn"]+=35
        if hour>=22 or hour<6:out["rest"]+=105
        return out

    def _choose_goal_and_plan(self,npc:NPCState,town,minute:int)->None:
        war=bool(self.state.factions.get(npc.faction_id).at_war) if npc.faction_id in self.state.factions else False
        needs=npc.needs
        routine=self._routine_bias(npc,minute)
        scores={
            "eat":npc.hunger*3+routine["eat"],
            "drink":npc.thirst*4,
            "rest":npc.rest*2+routine["rest"]+(80 if npc.rest>=80 else 0),
            "work":((65+(25 if "ambitious" in npc.traits else 0)-npc.hunger)+routine["work"]) if npc.workplace_id else 10,
            "socialize":needs.get("social",0)*2+(15 if "kind" in npc.traits else 0)+routine["socialize"],
            "guard":((50 if npc.occupation=="guard" else 0)+(35 if war else 0)+routine["guard"]),
            "heal":max((100-npc.hp)*4,needs.get("health",0)*3),
            "worship":(needs.get("faith",0)*2+routine["worship"]) if npc.occupation=="priest" or needs.get("faith",0)>55 else 0,
            "learn":(needs.get("learning",0)*2+routine["learn"]) if npc.occupation=="scholar" or "curious" in npc.traits or npc.age<16 else 0,
        }
        if npc.hunger>=80:scores["eat"]+=90
        if npc.thirst>=75:scores["drink"]+=100
        if npc.hunger>=85 and npc.wealth<=1 and ("greedy" in npc.traits or town.food_stress>=70):
            scores["steal"]=npc.hunger*3+25
        best=max(scores,key=scores.get);best_score=scores[best]
        if npc.goal_score*110//100>=best_score and npc.goal in scores:best=npc.goal;best_score=npc.goal_score
        npc.goal=best;npc.goal_score=best_score
        center=WorldPos(int(town.x),int(town.y),0)
        if best=="work":
            target=self._binding_destination(npc.workplace_id,npc.work_room_id,town)
            npc.tasks=[{"kind":"move","x":target.x,"y":target.y},{"kind":"perform","action":"work"}]
        elif best=="rest":
            target=self._binding_destination(npc.home_id,npc.home_room_id,town)
            npc.tasks=[{"kind":"move","x":target.x,"y":target.y},{"kind":"perform","action":"rest"}]
        elif best=="eat":
            target=self._service_destination(town,("market",))
            npc.tasks=[{"kind":"move","x":target.x,"y":target.y},{"kind":"perform","action":"eat"}]
        elif best=="drink":
            npc.tasks=[{"kind":"move","x":center.x,"y":center.y},{"kind":"perform","action":"drink"}]
        elif best=="guard":
            target=None
            if self.route_planner is not None and getattr(town,"frontier_status","core") in {"frontier","contested"}:
                target=self.route_planner.patrol_destination_for_settlement(town.uid)
            if target is None:target=self._service_destination(town,("watchhouse",))
            npc.tasks=[{"kind":"move","x":target.x,"y":target.y},{"kind":"perform","action":"guard"}]
        elif best=="heal":
            target=self._service_destination(town,("clinic",))
            npc.tasks=[{"kind":"move","x":target.x,"y":target.y},{"kind":"perform","action":"heal"}]
        elif best=="worship":
            target=self._service_destination(town,("shrine",))
            npc.tasks=[{"kind":"move","x":target.x,"y":target.y},{"kind":"perform","action":"worship"}]
        elif best=="learn":
            target=self._service_destination(town,("archive","school"))
            npc.tasks=[{"kind":"move","x":target.x,"y":target.y},{"kind":"perform","action":"learn"}]
        elif best=="steal":
            target=self._service_destination(town,("market",))
            npc.tasks=[{"kind":"move","x":target.x,"y":target.y},{"kind":"perform","action":"steal"}]
        elif best=="socialize":
            peers=[p for p in self.state.npcs.values() if p.alive and p.settlement_id==npc.settlement_id and p.uid!=npc.uid]
            kin=set(npc.parents)|set(npc.children)|set(npc.kinship)
            if npc.spouse_uid:kin.add(npc.spouse_uid)
            peers.sort(key=lambda p:(0 if p.uid in kin else 1,-npc.relationships.get(p.uid,{}).get("affection",0),p.uid))
            if peers:
                close=[p for p in peers if p.uid in kin]
                pool=close or peers[:max(1,min(4,len(peers)))]
                other=pool[hash_u64(self.seed,"social-target",npc.uid,minute//60)%len(pool)]
                if other.uid in kin:
                    target=self._binding_destination(npc.home_id,npc.home_room_id,town)
                else:
                    target=self._service_destination(town,("market","shrine"))
                npc.tasks=[{"kind":"move","x":target.x,"y":target.y},{"kind":"social","target":other.uid}]
            else:
                target=self._service_destination(town,("market","shrine"))
                npc.tasks=[{"kind":"move","x":target.x,"y":target.y},{"kind":"perform","action":"socialize"}]
    def _execute_task(self,npc:NPCState,town,minute:int,player_pos:WorldPos)->None:
        if not npc.tasks:return
        task=npc.tasks[0]
        if task['kind']=='move':
            goal=WorldPos(int(task['x']),int(task['y']),npc.z);start=WorldPos(npc.x,npc.y,npc.z)
            if abs(npc.x-goal.x)+abs(npc.y-goal.y)<=1:npc.tasks.pop(0);return
            if self.world and abs(npc.x-player_pos.x)<80 and abs(npc.y-player_pos.y)<60:
                def passable(p):
                    world_pass=self.world.is_passable(p)
                    if not world_pass and self.settlement_physicalization is not None:
                        crossing=self.settlement_physicalization.crossing_at(p)
                        world_pass=bool(crossing and str(crossing.kind) in {"bridge","ford"} and not bool(crossing.blocked))
                    if not world_pass:return False
                    if self.building and not self.building.passable(p,world_pass):return False
                    if self.property_security and self.property_security.blocks_actor(p,npc.uid,minute):return False
                    return True
                path=local_path(start,goal,passable,800)
                if len(path)>1:
                    old_x,old_y=npc.x,npc.y
                    step=path[min(3,len(path)-1)];npc.x,npc.y=step.x,step.y
                    self._face_step(npc,old_x,old_y)
                    if step==goal:npc.tasks.pop(0)
                # Exact nearby actors may wait/replan when a locked door or
                # other physical obstacle blocks the route. Never fall through
                # to coarse straight-line movement and ghost through it.
                return
            # aggregate/remote travel is straight-line at coarse fidelity
            old_x,old_y=npc.x,npc.y
            npc.x += 0 if npc.x==goal.x else (1 if goal.x>npc.x else -1);npc.y += 0 if npc.y==goal.y else (1 if goal.y>npc.y else -1)
            self._face_step(npc,old_x,old_y)
        elif task['kind']=='perform':
            action=task['action'];npc.tasks.pop(0)
            if action=='eat':
                food=next((iid for iid in ('core:wheat','core:turnip','core:meat') if town.stocks.get(iid,0)>0),None)
                if food:
                    town.stocks[food]-=1;npc.hunger=max(0,npc.hunger-45)
                    if self.economy is not None and npc.wealth>0:
                        price=min(npc.wealth,self.economy.trade_price(town.uid,food,buy=True))
                        npc.wealth-=price;town.wealth+=price
                        self.economy.record_transaction(
                            town.uid,"npc_purchase",npc.uid,town.uid,
                            copper_value=price,minute=minute,requested={food:1},
                        )
            elif action=='drink':npc.thirst=max(0,npc.thirst-55)
            elif action=='rest':npc.rest=max(0,npc.rest-55)
            elif action=='work':self._work(npc,town,minute);npc.needs['purpose']=max(0,npc.needs.get('purpose',0)-20)
            elif action=='guard':npc.rest=min(100,npc.rest+5);npc.needs['safety']=max(0,npc.needs.get('safety',0)-20)
            elif action=='heal':
                medicine=next((iid for iid in ('core:herbal_tonic','core:medicinal_herb') if town.stocks.get(iid,0)>0),None)
                if medicine:town.stocks[medicine]-=1;npc.hp=min(100,npc.hp+25)
                npc.needs['health']=max(0,100-npc.hp)
            elif action=='worship':npc.needs['faith']=max(0,npc.needs.get('faith',0)-45)
            elif action=='learn':npc.needs['learning']=max(0,npc.needs.get('learning',0)-40);npc.literacy=min(100,npc.literacy+1)
            elif action=='steal' and self.economy is not None:self.economy.npc_steal_food(npc,town,minute)
            elif action=='household_pickup' and self.households is not None:self.households.pickup_delivery(task.get('delivery_uid',''),npc.uid,minute)
            elif action=='household_dropoff' and self.households is not None:self.households.dropoff_delivery(task.get('delivery_uid',''),npc.uid,minute)
            elif action=='workplace_pickup' and self.workplace_logistics is not None:self.workplace_logistics.pickup_shipment(task.get('shipment_uid',''),npc.uid,minute)
            elif action=='workplace_dropoff' and self.workplace_logistics is not None:self.workplace_logistics.dropoff_shipment(task.get('shipment_uid',''),npc.uid,minute)
            elif action=='socialize':npc.needs['social']=max(0,npc.needs.get('social',0)-35)
        elif task['kind']=='social':
            npc.tasks.pop(0);other=self.state.npcs.get(task['target'])
            if other:self._socialize(npc,other,minute)
    def _assign_property(self,npc:NPCState,town)->None:
        # Exact IDs are assigned only when the authoritative physical plan is
        # active. Distant Tier-C NPCs remain aggregate instead of receiving
        # fabricated house/workplace identifiers.
        if self.settlement_population is not None:
            self.settlement_population.bind_settlement(town)
    def _work(self,npc:NPCState,town,minute:int=0)->None:
        # Production belongs to the aggregate labor reservation. The named NPC
        # is its physical representative and must not mint a second output.
        if self.economy is not None:
            self.economy.representative_work(npc,town,minute)
    def _socialize(self,npc:NPCState,other:NPCState,minute:int)->None:
        rel=npc.relationships.setdefault(other.uid,{"affection":0,"trust":0,"fear":0,"respect":0,"obligation":0,"familiarity":0});rel['familiarity']=min(100,rel['familiarity']+2);rel['trust']=min(100,rel['trust']+1);rel['affection']=min(100,rel['affection']+1)
        npc.needs["social"]=max(0,npc.needs.get("social",0)-35)
        npc.memories.append({"minute":minute,"type":"social","subject":other.uid,"salience":5,"valence":5});npc.memories=npc.memories[-40:]
