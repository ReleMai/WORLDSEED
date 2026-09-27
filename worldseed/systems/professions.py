from __future__ import annotations

from collections import defaultdict

from worldseed.core.coords import WorldPos
from worldseed.core.rng import hash_u64
from worldseed.systems.activities import ActivityAffordance
from worldseed.systems.state import CropPlot, SoilState, pos_key


class SettlementProfessionSystem:
    """Phase-4 exact profession loops beyond mining.

    This system intentionally covers the professions the user identified as the
    next focus: lumberjack, farmer, blacksmith/smith, carpenter, and cook. Named
    workers use real resources/fields/stations, carried inventory and physical
    storage. Their represented aggregate labor slot is removed by
    EconomySystem, so exact work replaces rather than duplicates ledger output.
    """

    PROCESS_IDS = {
        "lumberjack": {"core:logging"},
        "farmer": {"core:field_wheat", "core:field_turnip"},
        "smith": {"core:iron_smelt"},
        "carpenter": {"core:woodcraft"},
        "cook": {"core:hearth_roast"},
        "miller": {"core:grain_milling"},
        "baker": {"core:bread_baking"},
        "butcher": {"core:butcher_portions"},
        "fisher": {"core:fish_smoking"},
        "weaver": {"core:cloth_weaving"},
        "tanner": {"core:leather_tanning"},
        "healer": {"core:town_tonic", "core:town_soap"},
        "brewer": {"core:small_ale_brewing"},
        "potter": {"core:pottery_work"},
        "mason": {"core:masonry_work"},
    }
    SKILLS = {
        "lumberjack": ("woodcutting", "forestry", "hauling"),
        "farmer": ("farming", "soilcraft", "hauling"),
        "smith": ("smithing", "metallurgy", "hauling"),
        "carpenter": ("carpentry", "joinery", "hauling"),
        "cook": ("cooking", "hearthcraft", "hauling"),
        "miller": ("milling", "graincraft", "hauling"),
        "baker": ("baking", "cooking", "hauling"),
        "butcher": ("butchery", "hunting", "hauling"),
        "fisher": ("fishcraft", "preservation", "hauling"),
        "weaver": ("weaving", "textiles", "hauling"),
        "tanner": ("tanning", "leatherwork", "hauling"),
        "healer": ("medicine", "herbalism", "hauling"),
        "brewer": ("brewing", "fermentation", "hauling"),
        "potter": ("pottery", "kilncraft", "hauling"),
        "mason": ("masonry", "stonecutting", "hauling"),
    }
    OUTPUT_TAGS = {
        "lumberjack": {"core:wood", "core:bark", "core:stout_branch"},
        "farmer": {"core:wheat", "core:turnip"},
        "smith": {"core:iron_bloom"},
        "carpenter": {"core:wooden_bowl"},
        "cook": {"core:cooked_meat"},
        "miller": {"core:flour"},
        "baker": {"core:bread"},
        "butcher": {"core:meat", "core:animal_fat"},
        "fisher": {"core:smoked_fish"},
        "weaver": {"core:woven_cloth"},
        "tanner": {"core:leather"},
        "healer": {"core:herbal_tonic", "core:soap"},
        "brewer": {"core:small_ale"},
        "potter": {"core:clay_pot"},
        "mason": {"core:dressed_stone"},
    }
    WORKSHOP_TAGS = {
        "carpenter": ("carpentry", "workshop"),
        "cook": ("cooking", "hearth", "kitchen", "oven"),
        "miller": ("milling",),
        "baker": ("oven", "kitchen"),
        "butcher": ("butchery",),
        "fisher": ("smoking", "fish"),
        "weaver": ("loom", "textile"),
        "tanner": ("tanning",),
        "healer": ("healing",),
        "brewer": ("brewing",),
        "potter": ("pottery",),
        "mason": ("masonry", "quarry"),
    }
    WORKSHOP_DURATION = {
        "carpenter": 35, "cook": 25, "miller": 30, "baker": 45,
        "butcher": 30, "fisher": 50, "weaver": 55, "tanner": 70,
        "healer": 35, "brewer": 65, "potter": 50, "mason": 45,
    }

    def __init__(self, state, registry, seed: bytes, world, physicalization, activities, goods, resources):
        self.state=state
        self.registry=registry
        self.seed=seed or b""
        self.world=world
        self.physicalization=physicalization
        self.activities=activities
        self.goods=goods
        self.resources=resources

    # ---------- shared profession identity / progression ----------

    def ensure_profile(self, npc) -> None:
        names=self.SKILLS.get(str(npc.occupation))
        if not names:return
        age_bonus=max(0,min(3,(int(npc.age)-18)//12))
        for index,name in enumerate(names):
            base=1+age_bonus+(1 if index==0 else 0)+int(hash_u64(self.seed,"profession-skill",npc.uid,name)%3)
            npc.skills.setdefault(name,min(10,max(1,base)))
            npc.skill_xp.setdefault(name,0)

    def _gain_xp(self,npc,skill:str,amount:int)->None:
        self.ensure_profile(npc)
        level=max(0,int(npc.skills.get(skill,0)))
        xp=max(0,int(npc.skill_xp.get(skill,0)))+max(0,int(amount))
        while level<10 and xp>=70+level*28:
            xp-=70+level*28
            level+=1
        npc.skills[skill]=level
        npc.skill_xp[skill]=xp

    def has_active_work(self,npc)->bool:
        return any(bool(task.get("profession_task")) for task in npc.tasks)

    @staticmethod
    def is_physical_task(task:dict)->bool:
        return bool(task.get("profession_task"))

    def _process_for(self,npc,minute:int):
        if npc.work_assignment_day!=int(minute)//1440:
            return None
        process_id=str(npc.assigned_process_id or "")
        if process_id not in self.PROCESS_IDS.get(str(npc.occupation),set()):
            return None
        proc=self.registry.settlement_processes.get(process_id)
        return proc if proc is not None and proc.occupation==npc.occupation else None

    def supports_physical_work(self,npc,town)->bool:
        occ=str(npc.occupation)
        if occ not in self.PROCESS_IDS or self.physicalization is None:
            return False
        skeleton=self.physicalization.skeleton_for(town.uid)
        if skeleton is None or not npc.workplace_id:
            return False
        if occ=="farmer":
            return any(parcel.kind=="farm" for parcel in skeleton.parcels)
        if occ=="lumberjack":
            return self.resources is not None
        return bool(self.activities.work_affordances(npc,town))

    def abstract_worker_claim(self,town,proc,day:int,available_workers:int)->int:
        if proc.id not in self.PROCESS_IDS.get(str(proc.occupation),set()) or available_workers<=0:
            return 0
        reservation=self.state.labor_reservations.get(f"labor:{town.uid}:{proc.id}")
        if reservation is None or not reservation.active or reservation.assigned_day!=int(day):
            return 0
        exact=0
        for uid in sorted(reservation.representative_uids):
            npc=self.state.npcs.get(uid)
            if npc is None or not npc.alive or npc.occupation!=proc.occupation:
                continue
            if self.supports_physical_work(npc,town):
                exact+=1
        return min(max(0,int(available_workers)),exact*max(1,int(proc.workers)))

    # ---------- storage / cargo authority ----------

    def _containers(self,town_uid:str):
        return sorted(
            (c for c in self.state.containers.values() if c.settlement_id==str(town_uid)),
            key=lambda c:c.uid,
        )

    def _work_storage(self,npc,town):
        rows=[
            c for c in self._containers(town.uid)
            if c.property_id==str(npc.workplace_id)
        ]
        if rows:return rows[0]
        # A valid exact profession must have a physical destination. Do not
        # invent a detached hidden store when property storage has not materialized.
        return None

    def _use_position(self,container)->WorldPos:
        rows=[]
        for dx,dy in ((0,-1),(-1,0),(1,0),(0,1)):
            pos=WorldPos(int(container.x)+dx,int(container.y)+dy,int(container.z))
            if not self.world.is_passable(pos):continue
            if self.physicalization is not None and not self.physicalization.passable(pos,True):continue
            rows.append((pos.y,pos.x,pos))
        return min(rows,key=lambda r:r[:2])[2] if rows else WorldPos(int(container.x),int(container.y),int(container.z))

    def _move(self,pos:WorldPos,**meta)->dict:
        return {
            "kind":"move","x":int(pos.x),"y":int(pos.y),"z":int(pos.z),
            "exact":True,"physical_path":True,"profession_task":True,**meta,
        }

    def _ensure_input_sources(self,npc,town,storage,inputs:dict[str,int],minute:int):
        # Carried inputs count first.
        needed={iid:max(0,int(qty)-int(npc.inventory.get(iid,0))) for iid,qty in inputs.items()}
        needed={iid:qty for iid,qty in needed.items() if qty>0}
        if not needed:return []

        containers=self._containers(town.uid)
        allocations=defaultdict(dict)
        for iid in sorted(needed):
            remaining=needed[iid]
            ranked=sorted(
                containers,
                key=lambda c:(
                    0 if c.uid==storage.uid else 1,
                    0 if c.kind=="workplace" else 1,
                    abs(int(npc.x)-int(c.x))+abs(int(npc.y)-int(c.y)),
                    c.uid,
                ),
            )
            for container in ranked:
                have=max(0,int(container.items.get(iid,0)))
                take=min(remaining,have)
                if take>0:
                    allocations[container.uid][iid]=allocations[container.uid].get(iid,0)+take
                    remaining-=take
                if remaining<=0:break
            if remaining>0:
                # Only now cross from aggregate stock into the exact workplace.
                self.goods.stage_from_settlement(
                    town,storage,minute,items={iid:remaining},
                    source_kind="profession_input_materialization",
                    source_uid=str(npc.assigned_process_id),
                    metadata={"profession":npc.occupation},
                )
                have=max(0,int(storage.items.get(iid,0))-int(allocations[storage.uid].get(iid,0)))
                take=min(remaining,have)
                if take>0:
                    allocations[storage.uid][iid]=allocations[storage.uid].get(iid,0)+take
                    remaining-=take
            if remaining>0:return None

        by_uid={c.uid:c for c in containers}
        if storage.uid not in by_uid:by_uid[storage.uid]=storage
        return [(by_uid[uid],items) for uid,items in sorted(allocations.items()) if items]

    def _withdraw_tasks(self,npc,town,storage,inputs,minute,process_id):
        sources=self._ensure_input_sources(npc,town,storage,inputs,minute)
        if sources is None:return None
        tasks=[]
        for container,items in sources:
            tasks.append(self._move(self._use_position(container),process_id=process_id))
            tasks.append({
                "kind":"perform","action":"profession_withdraw","profession_task":True,
                "container_uid":container.uid,"items":dict(items),"process_id":process_id,
            })
        return tasks

    def withdraw(self,npc,town,task:dict,minute:int)->bool:
        container=next((c for c in self.state.containers.values() if c.uid==task.get("container_uid")),None)
        if container is None:return False
        if max(abs(int(npc.x)-int(container.x)),abs(int(npc.y)-int(container.y)),abs(int(npc.z)-int(container.z)))>1:
            return False
        row=self.goods.withdraw(
            npc,container,minute,items=dict(task.get("items") or {}),
            source_kind="profession_input",source_uid=str(task.get("process_id","")),
            metadata={"profession":npc.occupation},
        )
        return row is not None or all(
            int(npc.inventory.get(iid,0))>=int(qty)
            for iid,qty in (task.get("items") or {}).items()
        )

    def deposit(self,npc,town,task:dict,minute:int)->bool:
        container=next((c for c in self.state.containers.values() if c.uid==task.get("container_uid")),None)
        if container is None:return False
        if max(abs(int(npc.x)-int(container.x)),abs(int(npc.y)-int(container.y)),abs(int(npc.z)-int(container.z)))>1:
            return False
        requested={
            iid:int(npc.inventory.get(iid,0))
            for iid in task.get("items",[])
            if int(npc.inventory.get(iid,0))>0
        }
        if not requested:return True
        row=self.goods.deposit(
            npc,container,minute,items=requested,
            source_kind="profession_output",source_uid=str(task.get("process_id","")),
            metadata={"profession":npc.occupation},
        )
        return row is not None

    # ---------- physical workshop professions ----------

    def _choose_station(self,npc,town,minute:int,tags:tuple[str,...],exclude:set[str]|None=None):
        exclude=exclude or set()
        rows=[
            a for a in self.activities.work_affordances(npc,town)
            if a.target_uid not in exclude and (not tags or set(tags)&set(a.tags))
        ]
        rows.sort(key=lambda a:(
            abs(int(npc.x)-a.use_x)+abs(int(npc.y)-a.use_y),
            -a.work_bonus,a.target_uid,
        ))
        for affordance in rows:
            if not self.activities._occupied(affordance,minute,npc.uid):
                return affordance
        return None

    def _workshop_plan(self,npc,town,minute:int,proc):
        storage=self._work_storage(npc,town)
        if storage is None:return []
        withdraw=self._withdraw_tasks(npc,town,storage,proc.inputs,minute,proc.id)
        if withdraw is None:return []

        if npc.occupation=="smith":
            first=self._choose_station(npc,town,minute,("forge",))
            if first is None:return []
            heat=self.activities.reserve(npc,first,minute,duration_minutes=25,lease_minutes=300,phase="heat")
            if heat is None:return []
            tasks=withdraw+self.activities._tasks_for(heat,"smith_heat")
            second=self._choose_station(npc,town,minute,("anvil",),{first.target_uid})
            if second is not None:
                shape=self.activities.reserve(npc,second,minute,duration_minutes=20,lease_minutes=300,phase="shape")
                if shape is not None:
                    tasks+=self.activities._tasks_for(shape,"smith_shape")
            final_reservation=next(
                (t.get("reservation_uid") for t in reversed(tasks) if t.get("kind")=="activity"),""
            )
        else:
            tags=self.WORKSHOP_TAGS.get(str(npc.occupation),("workshop",))
            station=self._choose_station(npc,town,minute,tags)
            if station is None:return []
            skill_name=self.SKILLS.get(str(npc.occupation),("crafting",))[0]
            skill=int(npc.skills.get(skill_name,1))
            base=max(15,int(self.WORKSHOP_DURATION.get(str(npc.occupation),35)))
            duration=max(10,base-skill*2)
            row=self.activities.reserve(npc,station,minute,duration_minutes=duration,lease_minutes=max(240,duration+120),phase="produce")
            if row is None:return []
            tasks=withdraw+self.activities._tasks_for(row,f"{npc.occupation}_work")
            final_reservation=row.uid

        # The last activity completion creates the process output in carried cargo.
        for task in reversed(tasks):
            if task.get("kind")=="activity" and task.get("reservation_uid")==final_reservation:
                task["on_complete"]="profession_process"
                task["profession_task"]=True
                task["process_id"]=proc.id
                task["inputs"]=dict(proc.inputs)
                task["outputs"]=dict(proc.outputs)
                break
        for task in tasks:
            task["profession_task"]=True
            if task.get("kind")=="move":task["physical_path"]=True;task["exact"]=True
        tasks.append(self._move(self._use_position(storage),process_id=proc.id))
        tasks.append({
            "kind":"perform","action":"profession_deposit","profession_task":True,
            "container_uid":storage.uid,"items":list(proc.outputs),"process_id":proc.id,
        })
        return tasks

    def complete_process(self,npc,town,task:dict,minute:int)->bool:
        inputs={str(i):int(q) for i,q in (task.get("inputs") or {}).items()}
        if any(int(npc.inventory.get(iid,0))<qty for iid,qty in inputs.items()):
            return False
        for iid,qty in inputs.items():
            left=int(npc.inventory.get(iid,0))-qty
            if left>0:npc.inventory[iid]=left
            else:npc.inventory.pop(iid,None)
        outputs={str(i):int(q) for i,q in (task.get("outputs") or {}).items()}
        for iid,qty in outputs.items():
            made=self.goods.add_to_actor(npc,iid,qty)
            if made<qty:
                # Exact output may not disappear because a worker's hands are full.
                # Return uncarried overflow to the workplace container.
                storage=self._work_storage(npc,town)
                if storage is not None:
                    storage.items[iid]=storage.items.get(iid,0)+(qty-made)
        skills=self.SKILLS.get(str(npc.occupation),("crafting",))
        primary=skills[0] if skills else "crafting"
        self._gain_xp(npc,primary,18)
        if len(skills)>1:self._gain_xp(npc,skills[1],8)
        if len(skills)>2:self._gain_xp(npc,skills[2],4)
        return True

    # ---------- lumberjack ----------

    def _tree_use_position(self,pos:WorldPos):
        rows=[]
        for dx,dy in ((0,-1),(-1,0),(1,0),(0,1)):
            p=WorldPos(pos.x+dx,pos.y+dy,0)
            if self.world.is_passable(p) and self.physicalization.passable(p,True):
                rows.append((p.y,p.x,p))
        return min(rows,key=lambda r:r[:2])[2] if rows else None

    def _tree_target(self,npc,town,minute:int):
        self.ensure_profile(npc)
        forestry=max(1,int(npc.skills.get("forestry",1)))
        radius=min(60,24+forestry*4)
        origin=self.physicalization.destination_for(npc.workplace_id,npc.work_room_id) or WorldPos(int(town.x),int(town.y),0)
        candidates=[]
        for dist in range(2,radius+1):
            # Manhattan rings stop as soon as a useful local stand is found.
            ring=[]
            for dx in range(-dist,dist+1):
                dy=dist-abs(dx);ring.append((dx,dy))
                if dy:ring.append((dx,-dy))
            for dx,dy in sorted(set(ring),key=lambda p:(p[1],p[0])):
                pos=WorldPos(origin.x+dx,origin.y+dy,0)
                fv=self.resources.feature_at(pos,minute)
                if fv is None or fv.stage!="mature":continue
                definition=self.registry.resources.get(fv.feature_id)
                if definition is None or "tree" not in set(definition.tags):continue
                use=self._tree_use_position(pos)
                if use is None:continue
                value=sum(
                    max(1,int(getattr(self.registry.items.get(iid),"base_value",0) or 1))*int(lo+hi)
                    for iid,(lo,hi) in definition.yields.items()
                )
                candidates.append((-value,dist,pos.y,pos.x,pos,use,definition))
                if len(candidates)>=12:break
            if len(candidates)>=12 or (candidates and dist>=10):break
        return min(candidates,key=lambda r:r[:4]) if candidates else None

    def _logging_plan(self,npc,town,minute:int,proc):
        storage=self._work_storage(npc,town)
        if storage is None:return []
        cargo={iid for iid in self.OUTPUT_TAGS["lumberjack"] if int(npc.inventory.get(iid,0))>0}
        if cargo:
            return [
                self._move(self._use_position(storage),process_id=proc.id),
                {"kind":"perform","action":"profession_deposit","profession_task":True,
                 "container_uid":storage.uid,"items":sorted(cargo),"process_id":proc.id},
            ]
        target=self._tree_target(npc,town,minute)
        if target is None:return []
        _,distance,_,_,pos,use,definition=target
        skill=max(1,int(npc.skills.get("woodcutting",1)))
        affordance=ActivityAffordance(
            uid=f"affordance:tree:{pos.x}:{pos.y}:0",
            activity="woodcutting",settlement_id=town.uid,
            target_uid=f"natural-resource:{pos.x}:{pos.y}:0:{definition.id}",
            target_kind="natural_resource",workplace_role="lumberjack",
            x=pos.x,y=pos.y,z=0,use_x=use.x,use_y=use.y,use_z=0,
            work_bonus=skill,tags=("tree","woodcutting"),
        )
        duration=max(8,int(definition.minutes)*max(45,100-skill*6)//100)
        reservation=self.activities.reserve(
            npc,affordance,minute,duration_minutes=duration,
            lease_minutes=max(180,distance*8+duration+60),phase="fell",
        )
        if reservation is None:return []
        tasks=self.activities._tasks_for(reservation,"fell_tree",on_complete="profession_resource")
        for t in tasks:
            t["profession_task"]=True;t["process_id"]=proc.id
            t["resource_pos"]=[pos.x,pos.y,0];t["resource_id"]=definition.id
            if t.get("kind")=="move":t["exact"]=True;t["physical_path"]=True
        tasks += [
            self._move(self._use_position(storage),process_id=proc.id),
            {"kind":"perform","action":"profession_deposit","profession_task":True,
             "container_uid":storage.uid,"items":sorted(definition.yields),"process_id":proc.id},
        ]
        return tasks

    def complete_resource(self,npc,town,task:dict,minute:int)->bool:
        raw=task.get("resource_pos") or []
        if len(raw)!=3:return False
        pos=WorldPos(int(raw[0]),int(raw[1]),int(raw[2]))
        fv=self.resources.feature_at(pos,minute)
        if fv is None or fv.stage!="mature" or fv.feature_id!=task.get("resource_id"):
            return False
        definition=self.registry.resources.get(fv.feature_id)
        if definition is None:return False
        made=0
        skill=max(1,int(npc.skills.get("woodcutting",1)))
        for iid,(lo,hi) in sorted(definition.yields.items()):
            span=max(1,int(hi)-int(lo)+1)
            qty=int(lo)+int(hash_u64(self.seed,"npc-resource-yield",npc.uid,pos.x,pos.y,minute,iid)%span)
            qty+=skill//5
            made+=self.goods.add_to_actor(npc,iid,qty)
        if made<=0:return False
        self.state.resource_depletion[pos_key(pos.x,pos.y,pos.z)]=int(minute)
        self.resources.revision+=1
        self._gain_xp(npc,"woodcutting",14)
        self._gain_xp(npc,"forestry",6)
        return True

    # ---------- farmer ----------

    def _field_cells(self,town):
        skeleton=self.physicalization.skeleton_for(town.uid)
        if skeleton is None:return []
        cells=[]
        for parcel in sorted((p for p in skeleton.parcels if p.kind=="farm"),key=lambda p:p.uid):
            cells.extend((int(x),int(y)) for x,y in parcel.cells)
        return sorted(set(cells),key=lambda p:(p[1],p[0]))

    @staticmethod
    def _crop_for_process(proc_id:str):
        return {"core:field_wheat":"core:wheat","core:field_turnip":"core:turnip"}.get(str(proc_id))

    def _farm_affordance(self,npc,town,pos:WorldPos,action:str,minute:int,duration:int):
        affordance=ActivityAffordance(
            uid=f"affordance:field:{pos.x}:{pos.y}:{action}",
            activity=f"farm_{action}",settlement_id=town.uid,
            target_uid=f"field:{pos.x}:{pos.y}:0",target_kind="field",
            workplace_role="farmer",x=pos.x,y=pos.y,z=0,
            use_x=pos.x,use_y=pos.y,use_z=0,
            work_bonus=int(npc.skills.get("farming",1)),tags=("field",action),
        )
        return self.activities.reserve(npc,affordance,minute,duration_minutes=duration,lease_minutes=180,phase=action)

    def _farmer_plan(self,npc,town,minute:int,proc):
        crop_id=self._crop_for_process(proc.id)
        crop_def=self.registry.crops.get(crop_id) if crop_id else None
        storage=self._work_storage(npc,town)
        if crop_def is None or storage is None:return []
        field=self._field_cells(town)
        if not field:return []

        carried={crop_def.harvest_item} if int(npc.inventory.get(crop_def.harvest_item,0))>0 else set()
        if carried:
            return [
                self._move(self._use_position(storage),process_id=proc.id),
                {"kind":"perform","action":"profession_deposit","profession_task":True,
                 "container_uid":storage.uid,"items":sorted(carried),"process_id":proc.id},
            ]

        mature=[];growing=[];empty=[]
        for x,y in field:
            key=pos_key(x,y,0);plot=self.state.crops.get(key)
            if plot is None:empty.append((x,y));continue
            if plot.crop_id!=crop_id:continue
            (mature if plot.mature else growing).append((x,y,plot))
        if mature:
            x,y,plot=min(mature,key=lambda r:(abs(npc.x-r[0])+abs(npc.y-r[1]),r[1],r[0]))
            row=self._farm_affordance(npc,town,WorldPos(x,y,0),"harvest",minute,max(8,18-int(npc.skills.get("farming",1))))
            if row is None:return []
            tasks=self.activities._tasks_for(row,"farm_harvest",on_complete="profession_farm")
            for t in tasks:
                t["profession_task"]=True;t["process_id"]=proc.id;t["farm_action"]="harvest";t["crop_id"]=crop_id
                if t.get("kind")=="move":t["exact"]=True;t["physical_path"]=True
            tasks += [
                self._move(self._use_position(storage),process_id=proc.id),
                {"kind":"perform","action":"profession_deposit","profession_task":True,
                 "container_uid":storage.uid,"items":[crop_def.harvest_item],"process_id":proc.id},
            ]
            return tasks

        if growing:
            x,y,plot=min(growing,key=lambda r:(int(r[2].moisture),int(r[2].health),r[1],r[0]))
            row=self._farm_affordance(npc,town,WorldPos(x,y,0),"tend",minute,10)
            if row is None:return []
            tasks=self.activities._tasks_for(row,"farm_tend",on_complete="profession_farm")
            for t in tasks:
                t["profession_task"]=True;t["process_id"]=proc.id;t["farm_action"]="tend";t["crop_id"]=crop_id
                if t.get("kind")=="move":t["exact"]=True;t["physical_path"]=True
            return tasks

        if not empty:return []
        # Planting requires one real seed carried from storage/aggregate stock.
        withdraw=self._withdraw_tasks(npc,town,storage,{crop_def.seed_item:1},minute,proc.id)
        if withdraw is None:return []
        x,y=min(empty,key=lambda p:(abs(npc.x-p[0])+abs(npc.y-p[1]),p[1],p[0]))
        row=self._farm_affordance(npc,town,WorldPos(x,y,0),"plant",minute,12)
        if row is None:return []
        tasks=withdraw+self.activities._tasks_for(row,"farm_plant",on_complete="profession_farm")
        for t in tasks:
            t["profession_task"]=True;t["process_id"]=proc.id;t["farm_action"]="plant";t["crop_id"]=crop_id;t["seed_item"]=crop_def.seed_item
            if t.get("kind")=="move":t["exact"]=True;t["physical_path"]=True
        return tasks

    def complete_farm(self,npc,town,task:dict,minute:int)->bool:
        reservation=self.state.activity_reservations.get(str(task.get("reservation_uid","")))
        if reservation is None:return False
        pos=WorldPos(int(reservation.use_x),int(reservation.use_y),0)
        key=pos_key(pos.x,pos.y,0);action=str(task.get("farm_action",""));crop_id=str(task.get("crop_id",""))
        crop_def=self.registry.crops.get(crop_id)
        if crop_def is None:return False
        if action=="plant":
            seed=str(task.get("seed_item") or crop_def.seed_item)
            if int(npc.inventory.get(seed,0))<=0 or key in self.state.crops:return False
            left=int(npc.inventory.get(seed,0))-1
            if left:npc.inventory[seed]=left
            else:npc.inventory.pop(seed,None)
            self.state.soils.setdefault(key,SoilState(pos.x,pos.y,0))
            self.state.crops[key]=CropPlot(crop_id,pos.x,pos.y,0,int(minute))
            self._gain_xp(npc,"farming",8);self._gain_xp(npc,"soilcraft",4)
            return True
        plot=self.state.crops.get(key)
        if plot is None or plot.crop_id!=crop_id:return False
        if action=="tend":
            plot.moisture=min(100,int(plot.moisture)+18)
            plot.health=min(100,int(plot.health)+4)
            self._gain_xp(npc,"farming",3);self._gain_xp(npc,"soilcraft",3)
            return True
        if action=="harvest" and plot.mature:
            span=max(1,int(crop_def.yield_max)-int(crop_def.yield_min)+1)
            qty=int(crop_def.yield_min)+int(hash_u64(self.seed,"npc-crop-yield",npc.uid,pos.x,pos.y,minute)%span)
            qty=max(1,qty*max(35,int(plot.health))//100)
            qty+=int(npc.skills.get("farming",1))//4
            made=self.goods.add_to_actor(npc,crop_def.harvest_item,qty)
            if made<=0:return False
            self.state.crops.pop(key,None)
            soil=self.state.soils.setdefault(key,SoilState(pos.x,pos.y,0))
            soil.last_crop_id=crop_id
            self._gain_xp(npc,"farming",14);self._gain_xp(npc,"soilcraft",5)
            return True
        return False

    # ---------- public planning / activity completion ----------

    def plan_work(self,npc,town,minute:int)->list[dict]:
        if not self.supports_physical_work(npc,town):return []
        self.ensure_profile(npc)
        proc=self._process_for(npc,minute)
        if proc is None:return []
        if npc.occupation=="lumberjack":return self._logging_plan(npc,town,minute,proc)
        if npc.occupation=="farmer":return self._farmer_plan(npc,town,minute,proc)
        return self._workshop_plan(npc,town,minute,proc)

    def complete_activity(self,npc,town,task:dict,minute:int)->bool:
        marker=str(task.get("on_complete",""))
        if marker=="profession_process":return self.complete_process(npc,town,task,minute)
        if marker=="profession_resource":return self.complete_resource(npc,town,task,minute)
        if marker=="profession_farm":return self.complete_farm(npc,town,task,minute)
        return False
