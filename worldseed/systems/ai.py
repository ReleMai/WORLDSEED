from __future__ import annotations
from worldseed.core.coords import WorldPos
from worldseed.core.rng import hash_u64
from worldseed.systems.state import LivingWorldState, NPCState
from worldseed.systems.history import HistorySystem
from worldseed.systems.pathfinding import local_path
from worldseed.systems.household_economy import FOODS

class NPCSystem:
    # Explicit local durations release completed routines on simulation ticks.
    # Actions touching goods, cash, learning or aggregate work retain an hour
    # per completion; faster ticking cannot multiply their old coarse output.
    ROUTINE_MINUTES = {
        "drink": 5, "rest": 30, "socialize": 15, "worship": 30,
        "work": 60, "eat": 60, "heal": 60, "learn": 60, "steal": 60,
        "guard": 60, "territory_guard": 60,
    }

    @classmethod
    def _timed_routine(cls, task: dict) -> bool:
        return (task.get("kind") in {"social", "wait"}
                or (task.get("kind") == "perform"
                    and task.get("action") in cls.ROUTINE_MINUTES))

    def __init__(self,state:LivingWorldState,seed:bytes,history:HistorySystem,world=None,building=None,lod=None):
        self.state=state;self.seed=seed;self.history=history;self.world=world;self.building=building;self.lod=lod
        self.settlement_physicalization=None;self.settlement_population=None;self.economy=None;self.property_security=None;self.households=None;self.workplace_logistics=None;self.route_planner=None;self.territory=None;self.activities=None;self.mining=None;self.professions=None;self.interiors=None
        self.storage_access=None;self.commerce=None
        self._npc_spatial_buckets={};self._npc_spatial_positions={}
        self.rebuild_spatial_index()

    def _index_npc(self,npc)->None:
        """Maintain a transient locator, never a second actor/state authority."""
        current=(int(npc.x)//16,int(npc.y)//16,int(npc.z)) if npc.alive else None
        previous=self._npc_spatial_positions.get(npc.uid)
        if previous!=current and previous is not None:
            bucket=self._npc_spatial_buckets.get(previous,{})
            bucket.pop(npc.uid,None)
            if not bucket:self._npc_spatial_buckets.pop(previous,None)
            self._npc_spatial_positions.pop(npc.uid,None)
        if current is not None:
            self._npc_spatial_buckets.setdefault(current,{})[npc.uid]=npc
            self._npc_spatial_positions[npc.uid]=current

    def rebuild_spatial_index(self)->None:
        """Explicit startup/activation preparation only, never a UI query."""
        self._npc_spatial_buckets.clear();self._npc_spatial_positions.clear()
        for npc in self.state.npcs.values():self._index_npc(npc)

    def _indexed_npcs(self):
        # Reuse the existing simulation enumeration. The post-yield update
        # captures movement/death even when the caller takes an early continue;
        # no extra population scan is added to ticks or hourly decisions.
        for npc in self.state.npcs.values():
            try:yield npc
            finally:self._index_npc(npc)

    def nearby_npcs(self,pos:WorldPos,radius:int=24)->tuple:
        """Read only buckets intersecting a bounded local query."""
        radius=max(0,min(256,int(radius)));rows=[]
        for by in range((pos.y-radius)//16,(pos.y+radius)//16+1):
            for bx in range((pos.x-radius)//16,(pos.x+radius)//16+1):
                for uid,npc in self._npc_spatial_buckets.get((bx,by,pos.z),{}).items():
                    if (self.state.npcs.get(uid) is npc and npc.alive and npc.z==pos.z
                            and max(abs(npc.x-pos.x),abs(npc.y-pos.y))<=radius):
                        rows.append(npc)
        return tuple(sorted(rows,key=lambda npc:npc.uid))

    def attach_settlement_population(self,physicalization,population_binder)->None:
        self.settlement_physicalization=physicalization
        self.settlement_population=population_binder
    def attach_economy(self,economy)->None:self.economy=economy
    def attach_property_security(self,security)->None:self.property_security=security
    def attach_households(self,households)->None:self.households=households
    def attach_workplace_logistics(self,system)->None:self.workplace_logistics=system
    def attach_route_planner(self,system)->None:self.route_planner=system
    def attach_territory(self,system)->None:self.territory=system
    def attach_activity_system(self,system)->None:self.activities=system
    def attach_mining_profession(self,system)->None:self.mining=system
    def attach_profession_system(self,system)->None:self.professions=system
    def attach_interior_system(self,system)->None:self.interiors=system

    def _inside(self,npc:NPCState)->bool:
        return npc.uid in getattr(self.state,"interior_actors",{})

    def _home_entry_task(self,npc:NPCState):
        if self.interiors is None or self.property_security is None or not npc.home_id:
            return None
        doors=(door for door in self.property_security.doors_for_property(npc.home_id) if door.role=="entrance")
        door=next(doors,None)
        if door is None:return None
        frontage_lookup=getattr(self.settlement_physicalization,"frontage_for",None)
        threshold=frontage_lookup(npc.home_id) if callable(frontage_lookup) else None
        target=threshold or WorldPos(door.x,door.y,door.z)
        # Residents approach the same physical door as the player before the
        # shared portal authority transfers them to a continuous local space.
        return {"kind":"move","x":target.x,"y":target.y,"z":target.z,
                "exact":True,"physical_path":True,"interior_home_door_uid":door.uid}
    @staticmethod
    def _face_step(npc:NPCState,old_x:int,old_y:int)->None:
        dx=int(npc.x)-int(old_x);dy=int(npc.y)-int(old_y)
        npc.facing_dx=0 if dx==0 else (1 if dx>0 else -1)
        npc.facing_dy=0 if dy==0 else (1 if dy>0 else -1)

    def _is_active_local(self,npc:NPCState,player_pos:WorldPos)->bool:
        if self.lod is not None:
            return self.lod.npc_tier(player_pos,npc)=="A"
        return npc.z==player_pos.z and max(abs(npc.x-player_pos.x),abs(npc.y-player_pos.y))<=64

    def _tick_managed(self,npc:NPCState,player_pos:WorldPos)->bool:
        if self._is_active_local(npc,player_pos):
            return True
        mining_active=self.mining is not None and self.mining.has_active_trip(npc)
        profession_active=(self.professions is not None and self.professions.has_active_work(npc)) or any(task.get('commerce_task') for task in npc.tasks)
        if not (mining_active or profession_active):
            return False
        # Explicit profession trips may cross the immediate viewport boundary.
        # Tier B keeps those bounded physical plans on the fixed tick.
        if self.lod is not None:
            return self.lod.npc_tier(player_pos,npc)=="B"
        return max(abs(npc.x-player_pos.x),abs(npc.y-player_pos.y))<=256

    def _advance_needs(self,npc:NPCState,town)->None:
        npc.hunger=min(100,npc.hunger+3);npc.thirst=min(100,npc.thirst+5);npc.rest=min(100,npc.rest+2)
        defaults={"social":20,"safety":15,"health":0,"faith":10,"learning":10,"purpose":20}
        for key,value in defaults.items():npc.needs.setdefault(key,value)
        npc.needs["social"]=min(100,npc.needs["social"]+2)
        npc.needs["health"]=min(100,max(npc.needs["health"],100-npc.hp)+(8 if npc.infections else 0))
        if npc.occupation=="priest":npc.needs["faith"]=min(100,npc.needs["faith"]+3)
        if npc.occupation=="scholar" or "curious" in npc.traits:npc.needs["learning"]=min(100,npc.needs["learning"]+2)
        if town.food_stress>55:npc.needs["safety"]=min(100,npc.needs["safety"]+2)

    def decision_update(self,minute:int,player_pos:WorldPos,execute_active:bool=False)->None:
        """Run coarse need/decision cadence without driving active locomotion.

        Tier-A execution belongs to tick_update during normal play. Long
        fast-forwards may request execute_active to retain bounded legacy
        coarse progress instead of replaying every exact local tick.
        """
        if self.activities is not None:self.activities.cleanup(minute)
        provisioned_towns=set()
        for npc in self._indexed_npcs():
            if not npc.alive or self._inside(npc):continue
            tier=None
            if self.lod is not None:
                tier=self.lod.npc_tier(player_pos,npc)
                if not self.lod.should_update(tier,minute,"ai"):continue
            elif abs(npc.x-player_pos.x)+abs(npc.y-player_pos.y)>1200:continue
            town=self.state.settlements.get(npc.settlement_id)
            if not town:continue
            self._advance_needs(npc,town)
            if not npc.home_id:self._assign_property(npc,town)
            if not npc.tasks:self._choose_goal_and_plan(npc,town,minute)
            active=self._tick_managed(npc,player_pos)
            if active and town.uid not in provisioned_towns:
                provisioned_towns.add(town.uid)
                equipment=getattr(self.settlement_population,"equipment",None)
                provision=getattr(equipment,"provision_settlement",None)
                if callable(provision):provision(town)
            # Local timed routines can complete at this boundary too. Exact
            # locomotion and reserved work still belong to the fixed tick.
            task=npc.tasks[0] if npc.tasks else {}
            task_kind=task.get("kind","")
            profession_task=self.professions is not None and self.professions.is_physical_task(task)
            physical_task=profession_task or task.get('commerce_task') or task.get('storage_task') or task_kind in {"move","activity","mining_transition"} or (task_kind=="perform" and task.get("action") in {"mining_deposit","answer_door"})
            if active and not execute_active and self._timed_routine(task):
                self.execute_tick(npc,town,minute,player_pos)
            elif execute_active or not active or not physical_task:
                self._execute_task(npc,town,minute,player_pos)

    def tick_update(self,minute:int,player_pos:WorldPos)->None:
        """Execute one deterministic action slice for physically active NPCs."""
        if self.activities is not None:self.activities.cleanup(minute)
        # This is the single interior routine clock. Rendering may interpolate
        # presentation but cannot execute domestic actions or move residents.
        if self.interiors is not None:self.interiors.tick_update(minute)
        for npc in self._indexed_npcs():
            if not npc.alive or self._inside(npc) or not self._tick_managed(npc,player_pos):continue
            town=self.state.settlements.get(npc.settlement_id)
            if not town:continue
            if not npc.home_id:self._assign_property(npc,town)
            if not npc.tasks:self._choose_goal_and_plan(npc,town,minute)
            # Timed domestic routines release their next walk on this tick;
            # productive work remains on its own duration/reservation authority.
            if npc.tasks:
                task=npc.tasks[0];kind=task.get("kind")
                profession_task=self.professions is not None and self.professions.is_physical_task(task)
                if self._timed_routine(task) or profession_task or task.get('commerce_task') or task.get('storage_task') or kind in {"move","activity","mining_transition"} or (kind=="perform" and task.get("action") in {"mining_deposit","answer_door"}):
                    self.execute_tick(npc,town,minute,player_pos)

    def hourly_update(self,minute:int,player_pos:WorldPos)->None:
        """Compatibility entry point for older callers/tests."""
        self.decision_update(minute,player_pos,execute_active=True)

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
                "miner":(7,16),"lumberjack":(6,15),"carpenter":(7,16),
                "smith":(7,16),"cook":(6,18),"hunter":(6,14),
            }.get(npc.occupation,(8,17))
            if start<=hour<end:out["work"]+=55
        if hour in (7,12,18):out["eat"]+=55
        if 18<=hour<21:
            out["socialize"]+=45
            if npc.occupation=="priest" or npc.needs.get("faith",0)>45:out["worship"]+=35
        if npc.occupation=="scholar" and 17<=hour<20:out["learn"]+=35
        if hour>=22 or hour<6:out["rest"]+=105
        return out

    def select_utility_goal(self,npc:NPCState,town,minute:int)->tuple[str,int]:
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
        # Hysteresis compares today's utility, never the historical peak. A
        # satisfied thirst/sleep goal must release the actor to their next need.
        current_score=scores.get(npc.goal,0)
        if npc.goal in scores and current_score*110//100>=best_score:
            best=npc.goal;best_score=current_score
        npc.goal=best;npc.goal_score=best_score
        return best,best_score

    def generate_plan(self,npc:NPCState,town,minute:int,goal:str|None=None)->None:
        if self._inside(npc):return
        goal=npc.goal if goal is None else goal
        center=WorldPos(int(town.x),int(town.y),0)
        if goal=="work":
            ensure_assignments=getattr(self.economy,"ensure_work_assignments",None)
            if npc.work_assignment_day!=int(minute)//1440 and callable(ensure_assignments):
                ensure_assignments(town,minute)
            if self.mining is not None and self.mining.supports_physical_work(npc,town):
                physical_tasks=self.mining.plan_work(npc,town,minute)
                if physical_tasks:
                    npc.tasks=physical_tasks
                    return
                # A realized miner with a real workplace/cave authority must
                # wait for a viable vein/reservation rather than mint abstract ore.
                self._wait_for_work(npc,town)
                return
            if self.professions is not None and self.professions.supports_physical_work(npc,town):
                physical_tasks=self.professions.plan_work(npc,town,minute)
                if physical_tasks:
                    npc.tasks=physical_tasks
                    return
                self._wait_for_work(npc,town)
                return
            if self.activities is not None:
                physical_required=self.activities.supports_physical_work(npc,town)
                physical_tasks=self.activities.plan_work(npc,town,minute)
                if physical_tasks:
                    npc.tasks=physical_tasks
                    return
                if physical_required:
                    # A real nearby workplace exists but every compatible slot
                    # is reserved. Wait and retry on a later tick; never ghost
                    # through the reservation with abstract representative work.
                    self._wait_for_work(npc,town)
                    return
            target=self._binding_destination(npc.workplace_id,npc.work_room_id,town)
            npc.tasks=[{"kind":"move","x":target.x,"y":target.y},{"kind":"perform","action":"work"}]
        elif goal=="rest":
            target=self._binding_destination(npc.home_id,npc.home_room_id,town)
            entry=self._home_entry_task(npc)
            npc.tasks=[entry or {"kind":"move","x":target.x,"y":target.y},{"kind":"perform","action":"rest"}]
        elif goal=="eat":
            target=self._service_destination(town,("market",))
            npc.tasks=[{"kind":"move","x":target.x,"y":target.y},{"kind":"perform","action":"eat"}]
        elif goal=="drink":
            npc.tasks=[{"kind":"move","x":center.x,"y":center.y},{"kind":"perform","action":"drink"}]
        elif goal=="guard":
            target=None
            monument=None
            if self.route_planner is not None:
                monument=self.route_planner.territory_target_for_settlement(town.uid)
                if monument is not None:target=WorldPos(int(monument.x),int(monument.y),0)
            if self.route_planner is not None and getattr(town,"frontier_status","core") in {"frontier","contested"}:
                target=target or self.route_planner.patrol_destination_for_settlement(town.uid)
            if target is None:target=self._service_destination(town,("watchhouse",))
            npc.tasks=[{"kind":"move","x":target.x,"y":target.y,"exact":bool(monument),"physical_path":bool(monument)},{"kind":"perform","action":"territory_guard" if monument else "guard","monument_uid":monument.uid if monument else ""}]
        elif goal=="heal":
            target=self._service_destination(town,("clinic",))
            npc.tasks=[{"kind":"move","x":target.x,"y":target.y},{"kind":"perform","action":"heal"}]
        elif goal=="worship":
            target=self._service_destination(town,("shrine",))
            npc.tasks=[{"kind":"move","x":target.x,"y":target.y},{"kind":"perform","action":"worship"}]
        elif goal=="learn":
            target=self._service_destination(town,("archive","school"))
            npc.tasks=[{"kind":"move","x":target.x,"y":target.y},{"kind":"perform","action":"learn"}]
        elif goal=="steal":
            target=self._service_destination(town,("market",))
            npc.tasks=[{"kind":"move","x":target.x,"y":target.y},{"kind":"perform","action":"steal"}]
        elif goal=="socialize":
            peers=[p for p in self.state.npcs.values() if p.alive and not self._inside(p) and p.settlement_id==npc.settlement_id and p.uid!=npc.uid]
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
    def _wait_for_work(self,npc:NPCState,town)->None:
        # No viable resource/station/input means wait at the real workplace;
        # never replace the missing exact work with invented production.
        target=self._binding_destination(npc.workplace_id,npc.work_room_id,town)
        npc.tasks=[{"kind":"move","x":target.x,"y":target.y},
                   {"kind":"wait","reason":"work","duration_minutes":15}]

    def _choose_goal_and_plan(self,npc:NPCState,town,minute:int)->None:
        goal,_score=self.select_utility_goal(npc,town,minute)
        self.generate_plan(npc,town,minute,goal)

    def execute_tick(self,npc:NPCState,town,minute:int,player_pos:WorldPos)->None:
        if not npc.tasks or self._inside(npc):return
        task=npc.tasks[0]
        if task.get("kind")=="move":
            npc.routine_phase="walking_to_"+str(npc.goal or "destination")
        elif self._timed_routine(task):
            action="socialize" if task.get("kind")=="social" else str(task.get("action",task.get("reason","wait")))
            npc.routine_phase="waiting_for_work" if task.get("kind")=="wait" else action
            duration=max(5,int(task.get("duration_minutes",self.ROUTINE_MINUTES.get(action,15))))
            if task.get("kind")=="perform" and action in {"work","eat","heal","learn","steal","guard","territory_guard"}:
                duration=max(60,duration)
            task.setdefault("started_minute",int(minute))
            task.setdefault("complete_minute",int(task["started_minute"])+duration)
            if int(minute)<int(task["complete_minute"]):return
        self._execute_task(npc,town,minute,player_pos)

    def execute_interior_activity(self,npc:NPCState,town,minute:int)->None:
        """Use the existing completion authority after continuous indoor arrival."""
        if npc.tasks and npc.tasks[0].get("kind")=="activity":
            self._execute_task(npc,town,minute,WorldPos(npc.x,npc.y,npc.z),allow_interior_activity=True)

    def execute_interior_storage(self,npc:NPCState,town,minute:int)->None:
        """Complete cargo transfers only after the interior mover reaches storage."""
        if npc.tasks and npc.tasks[0].get('kind')=='perform' and npc.tasks[0].get('storage_task'):
            self._execute_task(npc,town,minute,WorldPos(npc.x,npc.y,npc.z),allow_interior_activity=True)

    def _execute_task(self,npc:NPCState,town,minute:int,player_pos:WorldPos,*,allow_interior_activity:bool=False)->None:
        if not npc.tasks:return
        if self._inside(npc) and not (allow_interior_activity and (npc.tasks[0].get("kind")=="activity" or npc.tasks[0].get('storage_task'))):return
        task=npc.tasks[0]
        if task['kind']=='move':
            # Persisted rest walks may still aim at the former tiled bedroom or
            # at a door moved by a bounded legacy access repair. Rebind only
            # the approach to the same authoritative home/door, not the NPC's
            # position, cargo or the household roster.
            home_walk = bool(task.get("interior_home_door_uid")) or (
                len(npc.tasks) > 1 and npc.tasks[1].get("kind") == "perform"
                and npc.tasks[1].get("action") == "rest")
            if home_walk and self.interiors is not None and self.property_security is not None:
                current = self._home_entry_task(npc)
                if current is not None:
                    previous = task.get("x"), task.get("y"), task.get("z", npc.z)
                    task.update(current)
                    if previous != (task["x"], task["y"], task["z"]):
                        task.pop("_local_path", None)
                        task.pop("_local_path_goal", None)
            # Legacy saves may contain a pending station walk aimed inside the
            # old tiled shell. Rebind the original reservation, not its goods.
            row=getattr(self.state,"activity_reservations",{}).get(str(task.get("reservation_uid","")))
            if self.interiors is not None and self.activities is not None and row is not None and row.target_kind=="fixture":
                if not row.metadata.get("space_id") and self.activities._indoor_target(npc,row.target_uid):
                    self.activities.bind_interior(row,npc)
                if row.metadata.get("space_id"):
                    task.update(x=row.use_x,y=row.use_y,z=row.use_z,exact=True,physical_path=True,
                                interior_work_door_uid=row.metadata["door_uid"],space_id=row.metadata["space_id"])
            goal=WorldPos(int(task['x']),int(task['y']),int(task.get('z',npc.z)));start=WorldPos(npc.x,npc.y,npc.z)
            if goal.z!=npc.z:
                # Vertical movement must use an explicit connector activity.
                return
            exact=bool(task.get('exact',False))
            distance=abs(npc.x-goal.x)+abs(npc.y-goal.y)
            reached=(npc.x,npc.y)==(goal.x,goal.y) if exact else distance<=1
            if reached:
                if task.get('interior_storage_door_uid') and self.interiors is not None:
                    if self.interiors.enter_storage_npc(npc,task['interior_storage_door_uid']):npc.tasks.pop(0)
                    return
                if task.get("interior_work_door_uid") and self.interiors is not None:
                    reservation=self.state.activity_reservations.get(str(task.get("reservation_uid","")))
                    if reservation is None or reservation.status in {"completed","cancelled"}:
                        npc.tasks.pop(0);return
                    if self.interiors.enter_work_npc(npc,task["interior_work_door_uid"]):npc.tasks.pop(0)
                    return
                if task.get("interior_home_door_uid") and self.interiors is not None:
                    if self.interiors.enter_npc(npc,task["interior_home_door_uid"]):
                        if task.get('storage_task'):npc.tasks.pop(0)
                        else:npc.tasks.clear()
                    return
                npc.tasks.pop(0);return
            if self.world and (
                bool(task.get('physical_path',False))
                or (abs(npc.x-player_pos.x)<80 and abs(npc.y-player_pos.y)<60 and npc.z==player_pos.z)
            ):
                def passable(p):
                    world_pass=self.world.is_passable(p)
                    if not world_pass and self.settlement_physicalization is not None:
                        crossing=self.settlement_physicalization.crossing_at(p)
                        world_pass=bool(crossing and str(crossing.kind) in {"bridge","ford"} and not bool(crossing.blocked))
                    if not world_pass:return False
                    if self.building and not self.building.passable(p,world_pass):return False
                    if self.property_security and self.property_security.blocks_actor(p,npc.uid,minute):return False
                    return True
                # Long exact trips (notably settlement -> cave) are advanced
                # through a nearby physical waypoint so local A* stays bounded.
                path_goal=goal
                cheb=max(abs(goal.x-npc.x),abs(goal.y-npc.y))
                if cheb>28:
                    dx=goal.x-npc.x;dy=goal.y-npc.y
                    px=npc.x+(dx*24//cheb);py=npc.y+(dy*24//cheb)
                    proxy=[]
                    for radius in range(0,5):
                        for oy in range(-radius,radius+1):
                            for ox in range(-radius,radius+1):
                                if max(abs(ox),abs(oy))!=radius:continue
                                p=WorldPos(px+ox,py+oy,npc.z)
                                if passable(p):
                                    proxy.append((abs(p.x-goal.x)+abs(p.y-goal.y),abs(ox)+abs(oy),p.y,p.x,p))
                        if proxy:break
                    if proxy:path_goal=min(proxy,key=lambda row:row[:4])[4]
                cache_goal=[int(path_goal.x),int(path_goal.y),int(path_goal.z)]
                cached=list(task.get("_local_path",[])) if task.get("_local_path_goal")==cache_goal else []
                if not cached:
                    path=local_path(start,path_goal,passable,1000,
                                    goal_radius=1 if not exact and path_goal==goal and not passable(goal) else 0)
                    cached=[[int(step.x),int(step.y)] for step in path[1:]]
                    task["_local_path"]=cached
                    task["_local_path_goal"]=cache_goal
                if cached:
                    old_x,old_y=npc.x,npc.y
                    moved=0
                    while cached and moved<3:
                        nx,ny=int(cached[0][0]),int(cached[0][1])
                        step_pos=WorldPos(nx,ny,npc.z)
                        if not passable(step_pos):
                            task.pop("_local_path",None);task.pop("_local_path_goal",None)
                            break
                        npc.x,npc.y=nx,ny;cached.pop(0);moved+=1
                    task["_local_path"]=cached
                    self._face_step(npc,old_x,old_y)
                    if (npc.x,npc.y)==(goal.x,goal.y):
                        if not any(task.get(key) for key in ('interior_home_door_uid','interior_work_door_uid','interior_storage_door_uid')):npc.tasks.pop(0)
                    elif not cached:
                        task.pop("_local_path",None);task.pop("_local_path_goal",None)
                # Never fall through to coarse movement while physically local.
                return
            # aggregate/remote travel is straight-line at coarse fidelity
            old_x,old_y=npc.x,npc.y
            npc.x += 0 if npc.x==goal.x else (1 if goal.x>npc.x else -1);npc.y += 0 if npc.y==goal.y else (1 if goal.y>npc.y else -1)
            self._face_step(npc,old_x,old_y)
            if (npc.x,npc.y)==(goal.x,goal.y) and not any(task.get(key) for key in ('interior_home_door_uid','interior_work_door_uid','interior_storage_door_uid')):npc.tasks.pop(0)
        elif task['kind']=='wait':
            npc.tasks.pop(0)
            return
        elif task['kind']=='mining_transition':
            if self.mining is None:
                npc.tasks.pop(0);return
            status=self.mining.transition(npc,task,minute)
            if status in {'completed','failed'}:npc.tasks.pop(0)
            return
        elif task['kind']=='activity':
            if self.activities is None:
                npc.tasks.pop(0)
                return
            status=self.activities.progress(task.get('reservation_uid',''),npc.uid,minute)
            row=self.state.activity_reservations.get(str(task.get('reservation_uid','')))
            if status=='not_at_target' and row is not None and row.metadata.get('space_id') and not self._inside(npc):
                npc.tasks.insert(0,{"kind":"move","x":row.use_x,"y":row.use_y,"z":row.use_z,"exact":True,"physical_path":True,"reservation_uid":row.uid,"interior_work_door_uid":row.metadata['door_uid'],"space_id":row.metadata['space_id'],"profession_task":bool(task.get('profession_task'))})
                return
            if status=='completed':
                npc.tasks.pop(0)
                if task.get('on_complete')=='work':
                    self._work(npc,town,minute)
                    npc.needs['purpose']=max(0,npc.needs.get('purpose',0)-20)
                elif task.get('on_complete')=='mining_extract' and self.mining is not None:
                    self.mining.complete_extract(npc,task.get('trip_uid',''),minute)
                    npc.needs['purpose']=max(0,npc.needs.get('purpose',0)-12)
                elif str(task.get('on_complete','')).startswith('profession_') and self.professions is not None:
                    if self.professions.complete_activity(npc,town,task,minute):
                        npc.needs['purpose']=max(0,npc.needs.get('purpose',0)-14)
            elif status in {'failed','cancelled'}:
                npc.tasks.pop(0)
            return
        elif task['kind']=='perform':
            action=task['action'];npc.tasks.pop(0)
            if action=='eat':
                food=next((iid for iid in FOODS if town.stocks.get(iid,0)>0),None)
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
            elif action=='territory_guard' and self.territory is not None:
                strength=max(8,min(40,12+npc.hp//5+(8 if npc.occupation=='guard' else 0)))
                self.territory.record_presence(task.get('monument_uid',''),npc.faction_id,strength)
                npc.rest=min(100,npc.rest+4);npc.needs['safety']=max(0,npc.needs.get('safety',0)-18)
            elif action=='heal':
                medicine=next((iid for iid in ('core:herbal_tonic','core:medicinal_herb') if town.stocks.get(iid,0)>0),None)
                if medicine:town.stocks[medicine]-=1;npc.hp=min(100,npc.hp+25)
                npc.needs['health']=max(0,100-npc.hp)
            elif action=='worship':npc.needs['faith']=max(0,npc.needs.get('faith',0)-45)
            elif action=='learn':npc.needs['learning']=max(0,npc.needs.get('learning',0)-40);npc.literacy=min(100,npc.literacy+1)
            elif action=='steal' and self.economy is not None:self.economy.npc_steal_food(npc,town,minute)
            elif action in {'household_pickup','household_dropoff'} and self.households is not None:
                transfer=self.households.pickup_delivery if action=='household_pickup' else self.households.dropoff_delivery
                if not transfer(task.get('delivery_uid',''),npc.uid,minute) and task.get('commerce_task'):
                    npc.tasks.insert(0,task)
            elif action=='workplace_pickup' and self.workplace_logistics is not None:self.workplace_logistics.pickup_shipment(task.get('shipment_uid',''),npc.uid,minute)
            elif action=='workplace_dropoff' and self.workplace_logistics is not None:self.workplace_logistics.dropoff_shipment(task.get('shipment_uid',''),npc.uid,minute)
            elif action=='mining_deposit' and self.mining is not None:self.mining.deposit(npc,town,task.get('trip_uid',''),task.get('container_uid',''),minute)
            elif action=='answer_door' and self.property_security is not None:self.property_security.complete_door_answer(task.get('door_uid',''),npc.uid,minute)
            elif action=='profession_withdraw' and self.professions is not None:self.professions.withdraw(npc,town,task,minute)
            elif action=='profession_deposit' and self.professions is not None:self.professions.deposit(npc,town,task,minute)
            elif action.startswith('commerce_') and self.commerce is not None:self.commerce.execute(npc,town,task,minute)
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
        if self._inside(npc) or self._inside(other):return
        rel=npc.relationships.setdefault(other.uid,{"affection":0,"trust":0,"fear":0,"respect":0,"obligation":0,"familiarity":0});rel['familiarity']=min(100,rel['familiarity']+2);rel['trust']=min(100,rel['trust']+1);rel['affection']=min(100,rel['affection']+1)
        npc.needs["social"]=max(0,npc.needs.get("social",0)-35)
        npc.memories.append({"minute":minute,"type":"social","subject":other.uid,"salience":5,"valence":5});npc.memories=npc.memories[-40:]
