"""Physical property storage, casing knowledge, and non-criminal suspicion.

Generated settlement structures remain the property authority. This module adds
sparse local storage containers backed by those structures and a player-knowledge
layer that is learned by physically moving around a target while casing it.

Casing is suspicious, not itself a crime: observed repetition raises attention
around the same owner/property, but it never creates a theft record or bounty.
"""
from __future__ import annotations

from dataclasses import dataclass

from worldseed.core.coords import WorldPos
from worldseed.core.rng import hash_u64
from worldseed.systems.state import (
    CasingIntelState, ContainerState, DoorSecurityState, PhysicalKeyState, SecurityIncidentState,
    TrespassState, pos_key,
)


_STORAGE_FUNCTIONS = {
    "residence": ("Household Chest", "core:wood_chest", ("core:wheat","core:turnip","core:meat","core:dried_meat","core:clean_water","core:soap"), 4),
    "smithy": ("Smithy Stores", "core:wood_storage_box", ("core:iron_ore","core:coal","core:iron_bloom","core:wood","core:stone"), 5),
    "workshop": ("Workshop Stores", "core:wood_storage_box", ("core:wood","core:plant_cordage","core:leather","core:stone"), 4),
    "mill": ("Mill Stores", "core:wood_storage_box", ("core:wheat","core:wheat_seed","core:turnip_seed","core:wood"), 4),
    "fishery": ("Fishery Stores", "core:wood_storage_box", ("core:dried_meat","core:clean_water","core:wood"), 3),
    "barn": ("Barn Stores", "core:storage_basket", ("core:wheat_seed","core:turnip_seed","core:wheat","core:turnip","core:wood"), 5),
    "clinic": ("Clinic Cabinet", "core:wood_storage_box", ("core:herbal_tonic","core:soap","core:clean_water"), 3),
    "watchhouse": ("Watchhouse Locker", "core:wood_chest", ("core:dried_meat","core:clean_water","core:wood"), 2),
    "archive": ("Archive Cabinet", "core:wood_chest", ("core:book","core:soap"), 2),
    "school": ("School Cabinet", "core:wood_chest", ("core:book","core:soap"), 2),
}


@dataclass(frozen=True, slots=True)
class PropertyStorageSync:
    settlement_id: str
    structures: int = 0
    created: int = 0
    reserved_items: int = 0


class PropertyStorageSystem:
    """Materialize one stable, owned storage point for eligible structures.

    Initial contents are transferred out of the settlement stock ledger. No
    goods are invented; once a container exists it is never reseeded.
    """

    def __init__(self, state, registry, seed: bytes, physicalization, civics, keys=None):
        self.state=state
        self.registry=registry
        self.seed=seed
        self.physicalization=physicalization
        self.civics=civics
        self.keys=keys or PhysicalKeySystem(state,seed)

    def _room_for(self, skeleton, structure):
        rooms=sorted(
            (r for r in skeleton.rooms if r.structure_plan_id==structure.uid),
            key=lambda r:(
                0 if r.kind in {"storage","bedroom","workshop","clinic","study","watch"} else 1,
                r.kind,r.uid,
            ),
        )
        return rooms[0] if rooms else None

    def _position(self, skeleton, structure):
        room=self._room_for(skeleton,structure)
        if room is None or not room.cells:
            return None
        fixture_cells={
            (int(p.x),int(p.y))
            for p in skeleton.pieces
            if p.structure_plan_id==structure.uid and p.role=="fixture"
        }
        occupied_npcs={
            (int(n.x),int(n.y))
            for n in self.state.npcs.values()
            if n.alive and int(n.z)==0
        }
        entrance=structure.entrance
        candidates=[]
        for x,y in room.cells:
            x=int(x);y=int(y)
            if (x,y) in fixture_cells or (x,y) in occupied_npcs:
                continue
            if entrance is not None and abs(x-int(entrance[0]))+abs(y-int(entrance[1]))<=1:
                continue
            p=WorldPos(x,y,0)
            if not self.physicalization.passable(p,True):
                continue
            distance=0 if entrance is None else abs(x-int(entrance[0]))+abs(y-int(entrance[1]))
            candidates.append((-distance,y,x))
        if not candidates:
            for x,y in room.cells:
                x=int(x);y=int(y)
                if (x,y) in fixture_cells or (x,y) in occupied_npcs:
                    continue
                if entrance is not None and abs(x-int(entrance[0]))+abs(y-int(entrance[1]))<=1:
                    continue
                p=WorldPos(x,y,0)
                if self.physicalization.passable(p,True):
                    distance=0 if entrance is None else abs(x-int(entrance[0]))+abs(y-int(entrance[1]))
                    candidates.append((-distance,y,x))
        if not candidates:
            return None
        _,y,x=min(candidates)
        return WorldPos(x,y,0),room.uid

    @staticmethod
    def _lock_level(function: str) -> int:
        return {"residence":18,"smithy":24,"workshop":20,"mill":18,"fishery":14,"barn":14,"clinic":24,"watchhouse":36,"archive":34,"school":18}.get(str(function),12)

    def _existing(self, uid: str):
        return next((c for c in self.state.containers.values() if c.uid==uid),None)

    def _reserve_contents(self, town, structure_uid: str, preferred, stack_cap: int):
        items={}
        for iid in preferred:
            if iid not in self.registry.items:
                continue
            available=max(0,int(town.stocks.get(iid,0)))
            if available<=0:
                continue
            desired=1+int(hash_u64(self.seed,"property-storage-stock",structure_uid,iid)%max(1,min(3,available)))
            qty=min(available,desired)
            if qty<=0:
                continue
            town.stocks[iid]=available-qty
            items[iid]=qty
            if len(items)>=stack_cap:
                break
        return items

    def sync_settlement(self, settlement_id: str) -> PropertyStorageSync:
        town=self.state.settlements.get(str(settlement_id))
        skeleton=self.physicalization.skeleton_for(str(settlement_id))
        if town is None or skeleton is None:
            return PropertyStorageSync(str(settlement_id))
        self.civics.ensure_settlement(town.uid)
        created=reserved=eligible=0
        for structure in sorted(skeleton.structures,key=lambda s:s.uid):
            profile=_STORAGE_FUNCTIONS.get(str(structure.function))
            if structure.destroyed or profile is None:
                continue
            eligible+=1
            name,source_id,preferred,stack_cap=profile
            uid=f"property-storage:{structure.uid}"
            owner=self.civics.owner_for_structure(town.uid,structure.uid) or town.uid
            existing=self._existing(uid)
            if existing is not None:
                existing.owner=owner
                existing.settlement_id=town.uid
                existing.property_id=structure.uid
                existing.access="private"
                self.keys.ensure_lock(existing)
                if existing.lock_level<=0:existing.lock_level=self._lock_level(structure.function)
                if existing.last_tampered_minute<0 and not existing.picked:existing.locked=existing.lock_level>0
                continue
            placed=self._position(skeleton,structure)
            if placed is None:
                continue
            position,room_id=placed
            key=pos_key(position.x,position.y,position.z)
            occupied=self.state.containers.get(key)
            if occupied is not None:
                continue
            items=self._reserve_contents(town,structure.uid,preferred,stack_cap)
            reserved+=sum(items.values())
            self.state.containers[key]=ContainerState(
                uid=uid,x=position.x,y=position.y,z=position.z,owner=owner,
                capacity_mass_g=160000 if structure.function in {"barn","smithy","workshop","mill"} else 90000,
                capacity_volume_ml=260000 if structure.function in {"barn","smithy","workshop","mill"} else 140000,
                items=items,name=name,kind="property",movable=False,source_id=source_id,
                settlement_id=town.uid,property_id=structure.uid,room_id=room_id,
                access="private",lock_level=self._lock_level(structure.function),
                locked=self._lock_level(structure.function)>0,lock_uid=f"lock:{uid}",seeded_from_settlement=True,
            )
            created+=1
        return PropertyStorageSync(town.uid,eligible,created,reserved)

    def sync_active(self) -> tuple[PropertyStorageSync,...]:
        return tuple(
            self.sync_settlement(uid)
            for uid in sorted(self.physicalization.active_settlement_ids)
        )

    def for_property(self, property_id: str) -> tuple[ContainerState,...]:
        return tuple(sorted(
            (
                c for c in self.state.containers.values()
                if c.kind=="property" and c.property_id==str(property_id)
            ),
            key=lambda c:c.uid,
        ))


    def by_id(self, container_uid: str):
        return next((c for c in self.state.containers.values() if c.uid==str(container_uid)),None)

    @staticmethod
    def authorized_actor(container:ContainerState,actor_uid:str)->bool:
        actor_uid=str(actor_uid or "")
        return container.access=="public" or actor_uid==container.owner or actor_uid in container.keyholder_uids or (actor_uid=="player" and container.owner=="player")

    def blocks_actor(self,container:ContainerState,actor_uid:str)->bool:
        self.keys.ensure_lock(container)
        return bool(container.locked and not self.authorized_actor(container,actor_uid) and not self.keys.actor_has_key(actor_uid,container.lock_uid))

    def set_locked_with_key(self,container_uid:str,actor_uid:str,locked:bool):
        container=self.by_id(container_uid)
        if container is None:return False,"That storage is no longer present."
        self.keys.ensure_lock(container)
        if not (self.authorized_actor(container,actor_uid) or self.keys.actor_has_key(actor_uid,container.lock_uid)):return False,"You do not have a key for that storage."
        if container.picked and locked:return False,"The picked lock must be repaired before it can be locked again."
        container.locked=bool(locked)
        return True,f"You {'lock' if locked else 'unlock'} {container.name or 'the storage'}."

    def grant_keyholder(self,container_uid:str,actor_uid:str)->bool:
        container=self.by_id(container_uid);actor_uid=str(actor_uid or "")
        if container is None or not actor_uid:return False
        if actor_uid not in container.keyholder_uids:container.keyholder_uids=sorted(set(container.keyholder_uids+[actor_uid]))
        return True

    def attempt_lockpick(self,container_uid:str,inventory,minute:int,skill:int,agility:int):
        container=self.by_id(container_uid)
        if container is None:return False,"That storage is no longer present.",0
        if not container.locked:return True,f"{container.name or 'The storage'} is already unlocked.",0
        if self.authorized_actor(container,"player"):return False,"You already have access to this storage.",0
        if inventory.count("core:lockpick")<=0:return False,"You need a lockpick.",0
        container.pick_attempts+=1;container.last_tampered_minute=int(minute)
        chance=max(5,min(92,32+int(skill)*7+int(agility)*2-container.lock_level))
        roll=int(hash_u64(self.seed,"container-lockpick",container.uid,container.pick_attempts,minute)%100)
        if roll<chance:
            container.locked=False;container.picked=True
            return True,"You pick the storage lock.",5
        return False,"The storage lock holds.",5


class PhysicalKeySystem:
    def __init__(self,state,seed:bytes):self.state=state;self.seed=seed
    @staticmethod
    def lock_uid(target_uid:str)->str:return f"lock:{target_uid}"
    def ensure_lock(self,target)->str:
        if not target.lock_uid:target.lock_uid=self.lock_uid(target.uid)
        return target.lock_uid
    def ensure_key(self,target,owner_uid:str,label:str="",minute:int=0)->PhysicalKeyState:
        lock_uid=self.ensure_lock(target);owner_uid=str(owner_uid);uid=f"key:{target.uid}:{owner_uid}"
        key=self.state.physical_keys.get(uid)
        if key is None:key=PhysicalKeyState(uid,lock_uid,owner_uid,label or "Property key",created_minute=int(minute));self.state.physical_keys[uid]=key
        return key
    def actor_has_key(self,actor_uid:str,lock_uid:str)->bool:return bool(lock_uid) and any(k.owner_uid==str(actor_uid) and k.lock_uid==lock_uid for k in self.state.physical_keys.values())
    def keys_for_actor(self,actor_uid:str):return tuple(sorted((k for k in self.state.physical_keys.values() if k.owner_uid==str(actor_uid)),key=lambda k:k.uid))
    def transfer(self,key_uid:str,from_uid:str,to_uid:str)->bool:
        key=self.state.physical_keys.get(str(key_uid));to_uid=str(to_uid)
        if key is None or key.owner_uid!=str(from_uid) or not to_uid:return False
        key.owner_uid=to_uid;return True
    def duplicate(self,key_uid:str,owner_uid:str,minute:int=0):
        source=self.state.physical_keys.get(str(key_uid))
        if source is None:return None
        serial=1
        while f"{source.uid}:copy:{serial}" in self.state.physical_keys:serial+=1
        uid=f"{source.uid}:copy:{serial}";key=PhysicalKeyState(uid,source.lock_uid,str(owner_uid),f"{source.label} copy",source.uid,int(minute));self.state.physical_keys[uid]=key;return key


class PropertySecuritySystem:
    """Physical access control for generated settlement properties.

    Door state is keyed by the stable StructurePiecePlan uid. Generated plans
    remain the geometry authority; this layer owns only dynamic lock/condition,
    trespass and security-response state.
    """

    PUBLIC_ENTRANCES={"market","clinic","shrine","school"}
    WORK_ENTRANCES={"smithy","workshop","mill","fishery","barn"}
    SECURE_FUNCTIONS={"residence","watchhouse","archive"}
    # Exact local opening hours only exist for active physical workplaces.
    # Distant Tier-C labor remains aggregate and never requires door updates.
    WORK_OPEN_HOURS={
        "barn":(5,20),"fishery":(5,17),"mill":(5,19),
        "smithy":(7,18),"workshop":(7,18),
    }
    PUBLIC_OPEN_HOURS={
        "market":(7,20),"clinic":(7,20),"shrine":(6,22),"school":(8,16),
    }

    def __init__(self,state,registry,seed:bytes,physicalization,civics,keys=None):
        self.state=state
        self.registry=registry
        self.seed=seed
        self.physicalization=physicalization
        self.civics=civics
        self.keys=keys or PhysicalKeySystem(state,seed)

    def _function(self, property_id: str) -> str:
        structure=self.physicalization.structure_by_id(str(property_id))
        return str(structure.function) if structure is not None else ""

    def _profile(self, function: str, role: str) -> tuple[str,bool,int]:
        function=str(function);role=str(role)
        if role=="entrance" and function in self.PUBLIC_ENTRANCES:
            # Public while open does not mean lockless. Keep a real physical
            # lock so closing hours can secure the same stable door.
            return "public",False,18
        if function in self.WORK_ENTRANCES and role=="entrance":
            return "work",False,22
        if function in self.SECURE_FUNCTIONS:
            base={"residence":24,"archive":42,"watchhouse":52}.get(function,30)
            if role=="interior_door":base+=6
            return ("restricted" if function in {"archive","watchhouse"} else "private"),True,base
        if role=="interior_door":
            return "restricted",bool(hash_u64(self.seed,"interior-lock",function)%100<35),28
        return "private",False,16

    def sync_settlement(self, settlement_id: str) -> int:
        settlement_id=str(settlement_id)
        skeleton=self.physicalization.skeleton_for(settlement_id)
        town=self.state.settlements.get(settlement_id)
        if skeleton is None or town is None:return 0
        self.civics.ensure_settlement(settlement_id)
        made=0
        structures={s.uid:s for s in skeleton.structures if not s.destroyed}
        for piece in sorted(skeleton.pieces,key=lambda p:p.uid):
            if piece.role not in {"entrance","interior_door"}:
                continue
            structure=structures.get(piece.structure_plan_id)
            if structure is None:continue
            owner=self.civics.owner_for_structure(settlement_id,structure.uid) or town.uid
            access,initial_locked,base=self._profile(structure.function,piece.role)
            level=0 if base<=0 else min(90,base+int(hash_u64(self.seed,"door-lock-level",piece.uid)%16))
            door=self.state.door_security.get(piece.uid)
            if door is None:
                door=DoorSecurityState(
                    uid=piece.uid,settlement_id=settlement_id,property_id=structure.uid,
                    x=int(piece.x),y=int(piece.y),z=0,role=str(piece.role),owner_uid=owner,
                    access=access,locked=bool(initial_locked),lock_level=level,
                )
                door.lock_uid=self.keys.ensure_lock(door)
                self.state.door_security[piece.uid]=door;made+=1
            else:
                door.settlement_id=settlement_id;door.property_id=structure.uid
                door.x=int(piece.x);door.y=int(piece.y);door.z=0;door.role=str(piece.role)
                door.owner_uid=owner;door.access=access
                self.keys.ensure_lock(door)
                if door.lock_level<=0 and level>0 and not door.forced:
                    door.lock_level=level
        return made

    def sync_active(self) -> int:
        return sum(self.sync_settlement(uid) for uid in sorted(self.physicalization.active_settlement_ids))

    def door_at(self,pos:WorldPos):
        cell=self.physicalization.door_at(pos)
        if cell is None or not cell.structure_piece_uid:return None
        return self.state.door_security.get(cell.structure_piece_uid)

    def door_by_id(self,door_uid:str):
        return self.state.door_security.get(str(door_uid))

    def doors_for_property(self,property_id:str):
        return tuple(sorted(
            (d for d in self.state.door_security.values() if d.property_id==str(property_id)),
            key=lambda d:(d.role,d.y,d.x,d.uid),
        ))

    @staticmethod
    def lock_band(level:int)->str:
        level=max(0,int(level))
        if level>=60:return "heavy"
        if level>=40:return "sturdy"
        if level>=20:return "simple"
        return "none"

    def authorized_actor(self,door:DoorSecurityState,actor_uid:str)->bool:
        """Return whether an actor may pass a locked physical property door.

        Home/work/property links remain the authority for resident and employee
        access. ``keyholder_uids`` is only an explicit sparse exception for
        guests/future physical keys; it does not duplicate household or labor
        membership.
        """
        actor_uid=str(actor_uid or "")
        if not actor_uid:return False
        if actor_uid==door.owner_uid or actor_uid in door.keyholder_uids:return True
        if int(door.guest_access_until.get(actor_uid,-1))>=int(self.state.clock_minute):return True
        npc=self.state.npcs.get(actor_uid)
        if npc is None:return False
        if npc.home_id==door.property_id or npc.property_id==door.property_id:return True
        if npc.workplace_id==door.property_id:return True
        prop=self.state.properties.get(door.property_id)
        return bool(prop and actor_uid in prop.occupants)

    def authorized_player(self,door:DoorSecurityState)->bool:
        return self.authorized_actor(door,"player")

    def blocks_actor(self,pos:WorldPos,actor_uid:str,minute:int|None=None)->bool:
        door=self.door_at(pos)
        return bool(door and door.locked and not door.forced and not self.authorized_actor(door,actor_uid) and not self.keys.actor_has_key(actor_uid,self.keys.ensure_lock(door)))

    def blocks_player(self,pos:WorldPos)->bool:
        return self.blocks_actor(pos,"player")

    def set_locked_with_key(self,door_uid:str,actor_uid:str,locked:bool):
        door=self.door_by_id(door_uid)
        if door is None:return False,"That door is no longer present."
        self.keys.ensure_lock(door)
        if door.forced:return False,"The broken door cannot be locked until it is repaired."
        if door.picked and locked:return False,"The picked lock must be repaired before it can be locked again."
        if not (self.authorized_actor(door,actor_uid) or self.keys.actor_has_key(actor_uid,door.lock_uid)):return False,"You do not have a key for that door."
        door.locked=bool(locked);door.schedule_locked=False;door.last_schedule_minute=-1
        return True,f"You {'lock' if locked else 'unlock'} the door."

    def grant_keyholder(self,property_id:str,actor_uid:str)->int:
        """Grant explicit guest/key access without changing property ownership."""
        actor_uid=str(actor_uid or "")
        if not actor_uid:return 0
        changed=0
        for door in self.doors_for_property(property_id):
            if actor_uid not in door.keyholder_uids:
                door.keyholder_uids=sorted(set(door.keyholder_uids+[actor_uid]));changed+=1
        return changed

    def revoke_keyholder(self,property_id:str,actor_uid:str)->int:
        actor_uid=str(actor_uid or "")
        changed=0
        for door in self.doors_for_property(property_id):
            if actor_uid in door.keyholder_uids:
                door.keyholder_uids=[uid for uid in door.keyholder_uids if uid!=actor_uid];changed+=1
        return changed

    def grant_guest_access(self,property_id:str,actor_uid:str,until_minute:int)->int:
        actor_uid=str(actor_uid or "")
        if not actor_uid:return 0
        changed=0
        for door in self.doors_for_property(property_id):
            before=int(door.guest_access_until.get(actor_uid,-1))
            door.guest_access_until[actor_uid]=max(before,int(until_minute))
            if int(door.guest_access_until[actor_uid])!=before:changed+=1
        return changed

    def knock_on_door(self,door_uid:str,player_pos:WorldPos,minute:int,persuasion:int=0)->dict:
        """Request a resident response without teleporting them or opening UI."""
        door=self.door_by_id(door_uid)
        if door is None:return {"outcome":"missing","message":"That door is no longer present.","npc_uid":""}
        if door.role!="entrance" or self._function(door.property_id) not in {"residence","inn","barracks","outskirt_camp"}:
            return {"outcome":"not_home","message":"This is not a private home entrance.","npc_uid":""}
        if door.z!=player_pos.z or abs(door.x-player_pos.x)+abs(door.y-player_pos.y)>1:
            return {"outcome":"far","message":"Move next to the door before knocking.","npc_uid":""}
        residents=[]
        for npc in self.state.npcs.values():
            if not npc.alive or npc.z!=door.z:continue
            if npc.home_id!=door.property_id and npc.property_id!=door.property_id:continue
            cell=self.physicalization.cell_at(WorldPos(npc.x,npc.y,npc.z))
            if cell is not None and cell.structure_id==door.property_id:
                residents.append(npc)
        if not residents:
            return {"outcome":"unanswered","message":"You knock, but no one inside answers.","npc_uid":""}
        residents.sort(key=lambda npc:(abs(npc.x-door.x)+abs(npc.y-door.y),npc.uid))
        npc=residents[0]
        if door.answering_npc_uid:
            answering=self.state.npcs.get(door.answering_npc_uid)
            if answering is not None and door.answered_minute>=door.answer_requested_minute and (answering.x,answering.y,answering.z)==(door.x,door.y,door.z):
                return {"outcome":"answered","message":f"{answering.name} is waiting at the open door. Speak to them when you are ready.","npc_uid":answering.uid}
            if answering is not None and door.answered_minute<door.answer_requested_minute:
                return {"outcome":"approaching","message":"You knock again. Someone inside is already coming to the door.","npc_uid":door.answering_npc_uid}
            door.answering_npc_uid="";door.answer_requested_minute=-1;door.answered_minute=-1;door.answer_outcome=""
        rel=npc.relationships.setdefault("player",{"affection":0,"trust":0,"fear":0,"respect":0,"familiarity":0})
        trust=int(rel.get("trust",0));affection=int(rel.get("affection",0));familiarity=int(rel.get("familiarity",0))
        heat=int(self.state.player_crime_heat.get(door.settlement_id,0))
        hour=(int(minute)%1440)//60
        threshold=12+(14 if hour>=22 or hour<6 else 0)+(12 if "suspicious" in npc.traits else 0)
        willingness=trust+affection//2+familiarity//3+max(0,int(persuasion))*3-heat
        outcome="invited" if willingness>=threshold else "door_talk"
        door.answering_npc_uid=npc.uid;door.answer_requested_minute=int(minute)
        door.answered_minute=-1;door.answer_outcome=outcome
        npc.tasks=[
            {"kind":"move","x":door.x,"y":door.y,"z":door.z,"exact":True,"physical_path":True,"door_answer_uid":door.uid},
            {"kind":"perform","action":"answer_door","door_uid":door.uid},
        ]
        return {"outcome":"approaching","message":f"You knock. Footsteps move through the house as {npc.name} decides whether to answer.","npc_uid":npc.uid}

    def complete_door_answer(self,door_uid:str,npc_uid:str,minute:int)->bool:
        door=self.door_by_id(door_uid);npc=self.state.npcs.get(str(npc_uid))
        if door is None or npc is None or door.answering_npc_uid!=npc.uid:return False
        if (npc.x,npc.y,npc.z)!=(door.x,door.y,door.z):return False
        door.locked=False;door.schedule_locked=False;door.answered_minute=int(minute)
        if door.answer_outcome=="invited":
            self.grant_guest_access(door.property_id,"player",int(minute)+120)
        return True

    def update_scheduled_locks(self,minute:int)->int:
        """Apply active-workplace opening hours to stable entrance locks.

        Work and public-service entrances follow bounded local opening hours;
        private/restricted doors retain their stronger security profile. A
        picked or forced door is never relocked here; that
        requires a future owner repair/security action.
        """
        hour=(int(minute)%1440)//60;changed=0
        for door in sorted(self.state.door_security.values(),key=lambda d:d.uid):
            expired=[uid for uid,until in door.guest_access_until.items() if int(until)<int(minute)]
            for uid in expired:door.guest_access_until.pop(uid,None)
            if expired and self._function(door.property_id)=="residence" and door.role=="entrance" and not door.forced and not door.picked:
                if not door.locked:door.locked=True;changed+=1
            if door.role!="entrance" or door.access not in {"work","public"}:continue
            function=self._function(door.property_id)
            hours=(self.WORK_OPEN_HOURS if door.access=="work" else self.PUBLIC_OPEN_HOURS).get(function)
            if hours is None:continue
            door.last_schedule_minute=int(minute)
            if door.forced or door.picked:
                door.schedule_locked=False
                continue
            start,end=hours
            should_lock=not (start<=hour<end)
            if should_lock:
                if not door.locked:
                    door.locked=True;door.schedule_locked=True;changed+=1
            elif door.schedule_locked:
                door.locked=False;door.schedule_locked=False;changed+=1
        return changed

    def _witnesses(self,door:DoorSecurityState,pos:WorldPos,minute:int,stealth,noise_radius:int=0):
        seen=set(stealth.witnesses(pos,minute,door.settlement_id))
        if noise_radius>0:
            prop=self.state.properties.get(door.property_id)
            interested={door.owner_uid}
            if prop:interested.update(prop.occupants)
            for npc in self.state.npcs.values():
                if not npc.alive or npc.z!=pos.z or npc.settlement_id!=door.settlement_id:continue
                distance=abs(npc.x-pos.x)+abs(npc.y-pos.y)
                if distance<=noise_radius and (npc.occupation=="guard" or npc.uid in interested):
                    seen.add(npc.uid)
        return tuple(sorted(uid for uid in seen if uid in self.state.npcs))

    def _alert_guards(self,door:DoorSecurityState,witnesses,level:int)->None:
        structure=self.physicalization.structure_by_id(door.property_id)
        target=(door.x,door.y)
        if structure is not None and structure.entrance is not None:
            target=(int(structure.entrance[0]),int(structure.entrance[1]))
        witness_set=set(witnesses)
        for npc in self.state.npcs.values():
            if not npc.alive or npc.settlement_id!=door.settlement_id or npc.occupation!="guard":
                continue
            distance=abs(npc.x-door.x)+abs(npc.y-door.y)
            if npc.uid not in witness_set and distance>10+level*3:continue
            npc.goal="guard";npc.goal_score=max(int(npc.goal_score),80+level*5)
            npc.tasks=[
                {"kind":"move","x":target[0],"y":target[1]},
                {"kind":"perform","action":"guard"},
            ]

    def _incident(self,door:DoorSecurityState,kind:str,minute:int,witnesses,severity:int):
        witnesses=tuple(sorted(set(witnesses)))
        row=SecurityIncidentState(
            uid=self.state.uid("security"),settlement_id=door.settlement_id,
            property_id=door.property_id,actor_uid="player",kind=str(kind),
            minute=int(minute),severity=max(1,int(severity)),witnessed=bool(witnesses),
            witness_uids=list(witnesses),door_uid=door.uid,
        )
        self.state.security_incidents[row.uid]=row
        if witnesses:
            guards=sum(1 for uid in witnesses if self.state.npcs.get(uid) and self.state.npcs[uid].occupation=="guard")
            self.state.player_crime_heat[door.settlement_id]=min(
                100,self.state.player_crime_heat.get(door.settlement_id,0)+severity+guards*5
            )
            self._alert_guards(door,witnesses,min(3,max(1,severity//6)))
        return row

    def attempt_lockpick(self,door_uid:str,inventory,player_pos:WorldPos,minute:int,stealth,skill:int,agility:int):
        door=self.door_by_id(door_uid)
        if door is None:return False,"That door is not physically present.",0
        if abs(door.x-player_pos.x)+abs(door.y-player_pos.y)>1 or door.z!=player_pos.z:
            return False,"Move next to the door before working the lock.",0
        if self.authorized_player(door):
            door.locked=False
            return True,"You have legitimate access to this door.",0
        if door.forced or not door.locked:return True,"The door is already unsecured.",0
        if inventory.count("core:lockpick")<=0:return False,"You need a lockpick.",0
        door.pick_attempts+=1;door.last_tampered_minute=int(minute)
        chance=max(5,min(92,34+int(skill)*7+max(0,int(agility)-5)*5-door.lock_level))
        roll=int(hash_u64(self.seed,"property-lockpick",door.uid,door.pick_attempts,int(minute)//5)%100)
        witnesses=self._witnesses(door,player_pos,minute,stealth,noise_radius=1)
        self._incident(door,"lock_tampering",minute,witnesses,6)
        if roll<chance:
            door.locked=False;door.picked=True;door.schedule_locked=False
            return True,f"You pick the {self.lock_band(door.lock_level)} lock.",5
        broke=(hash_u64(self.seed,"lockpick-break",door.uid,door.pick_attempts,int(minute))%100)<18
        if broke:
            inventory.remove("core:lockpick",1)
            return False,"The lock resists you and the pick snaps.",5
        return False,"The lock resists the attempt.",5

    def force_entry(self,door_uid:str,inventory,player_pos:WorldPos,minute:int,stealth,strength:int):
        door=self.door_by_id(door_uid)
        if door is None:return False,"That door is not physically present.",0,0
        if abs(door.x-player_pos.x)+abs(door.y-player_pos.y)>1 or door.z!=player_pos.z:
            return False,"Move next to the door before forcing it.",0,0
        if self.authorized_player(door):
            door.locked=False
            return True,"You have legitimate access to this door.",0,0
        if door.forced:return True,"The doorway has already been forced open.",0,0
        best_power=0;best_name="your weight"
        for iid,count in inventory.items.items():
            if count<=0:continue
            item=self.registry.items.get(iid)
            if item is None:continue
            tags=set(item.tags)
            if not tags.intersection({"axe","hammer","pick"}):continue
            power=max(int(item.tool_power),max((int(v) for v in item.tool_qualities.values()),default=0))
            if power>best_power:
                best_power=power;best_name=item.name.lower()
        damage=max(6,8+int(strength)*2+best_power*8)
        door.condition=max(0,door.condition-damage);door.last_tampered_minute=int(minute)
        witnesses=self._witnesses(door,player_pos,minute,stealth,noise_radius=9)
        self._incident(door,"forced_entry",minute,witnesses,14)
        if door.condition<=0:
            door.locked=False;door.forced=True;door.schedule_locked=False
            return True,f"You break the door open with {best_name}.",2,85
        return False,f"You batter the door with {best_name}; it holds at {door.condition}% condition.",2,80

    def _property_restricted(self,property_id:str)->bool:
        doors=self.doors_for_property(property_id)
        return any(d.access!="public" for d in doors)

    def _door_for_property(self,property_id:str):
        rows=self.doors_for_property(property_id)
        return next((d for d in rows if d.role=="entrance"),rows[0] if rows else None)

    def note_player_step(self,old:WorldPos,new:WorldPos,minute:int,stealth)->list[str]:
        messages=[]
        old_cell=self.physicalization.cell_at(old)
        cell=self.physicalization.cell_at(new)
        old_property=old_cell.structure_id if old_cell is not None else ""
        new_property=cell.structure_id if cell is not None else ""
        current=str(self.state.player_trespass_property_id or "")
        if current and new_property!=current:
            row=self.state.trespass_states.get(current)
            if row:row.active=False
            self.state.player_trespass_property_id=""
            messages.append("You leave the restricted property.")
            current=""
        if not new_property:
            return messages
        if new_property==old_property:
            crossed=self.door_at(new)
            if crossed is None or crossed.access=="public" or self.authorized_player(crossed):
                return messages
            door=crossed
        else:
            if not self._property_restricted(new_property):
                return messages
            door=self.door_at(new) or self._door_for_property(new_property)
            if door is None or self.authorized_player(door):
                return messages
        entry_method="forced" if door.forced else "picked" if door.picked else "unsecured"
        row=self.state.trespass_states.get(new_property)
        if row is None:
            row=TrespassState(new_property,door.settlement_id)
            self.state.trespass_states[new_property]=row
        row.active=True;row.entered_minute=int(minute);row.entry_method=entry_method
        self.state.player_trespass_property_id=new_property
        witnesses=self._witnesses(door,new,minute,stealth,noise_radius=0)
        if witnesses:
            row.witness_uids=sorted(set(row.witness_uids).union(witnesses))
            row.last_seen_minute=int(minute);row.search_level=max(row.search_level,1)
            self._incident(door,"trespass",minute,witnesses,5)
            messages.append("Your unauthorized entry is noticed.")
        else:
            messages.append("You enter the property without permission.")
        return messages

    def update_response(self,player_pos:WorldPos,minute:int,stealth)->list[str]:
        property_id=str(self.state.player_trespass_property_id or "")
        if not property_id:return []
        cell=self.physicalization.cell_at(player_pos)
        if cell is None or cell.structure_id!=property_id:
            row=self.state.trespass_states.get(property_id)
            if row:row.active=False
            self.state.player_trespass_property_id=""
            return ["You are no longer trespassing."]
        row=self.state.trespass_states.get(property_id)
        door=self._door_for_property(property_id)
        if row is None or door is None:return []
        seen=tuple(sorted(set(stealth.witnesses(player_pos,minute,row.settlement_id))))
        guards=[self.state.npcs[uid] for uid in seen if uid in self.state.npcs and self.state.npcs[uid].occupation=="guard"]
        prop=self.state.properties.get(property_id)
        interested=set(prop.occupants if prop else ())
        if prop:interested.add(prop.owner_uid)
        occupants=[self.state.npcs[uid] for uid in seen if uid in self.state.npcs and uid in interested]
        witnesses=guards or occupants
        if not witnesses:return []
        row.witness_uids=sorted(set(row.witness_uids).union(n.uid for n in witnesses))
        row.last_seen_minute=int(minute)
        for npc in guards:
            npc.goal="guard";npc.goal_score=max(int(npc.goal_score),100)
            npc.tasks=[{"kind":"move","x":player_pos.x,"y":player_pos.y},{"kind":"perform","action":"guard"}]
        if not row.warned:
            row.warned=True;row.warning_count+=1;row.search_level=max(row.search_level,1)
            return ["A guard or occupant challenges you and orders you out of the property."]
        # A second observed step after the initial warning is an escalation.
        if row.search_level<2:
            row.search_level=2;row.warning_count+=1
            self._incident(door,"defied_trespass_warning",minute,[n.uid for n in witnesses],10)
            return ["You ignore the warning. Guards begin an active search and removal response."]
        return []

    def summary(self,property_id:str)->dict:
        doors=self.doors_for_property(property_id)
        trespass=self.state.trespass_states.get(str(property_id))
        return {
            "doors":len(doors),
            "locked":sum(1 for d in doors if d.locked and not d.forced),
            "forced":sum(1 for d in doors if d.forced),
            "trespassing":bool(trespass and trespass.active),
            "search_level":int(trespass.search_level if trespass else 0),
        }


class CasingSystem:
    """Accumulate property intel only from the player's physical survey."""

    CARDINALS=((1,0),(-1,0),(0,1),(0,-1))

    def __init__(self,state,physicalization,civics,property_storage,security=None):
        self.state=state
        self.physicalization=physicalization
        self.civics=civics
        self.property_storage=property_storage
        self.security=security

    def _structure(self, property_id: str):
        return self.physicalization.structure_by_id(str(property_id))

    def _settlement_id(self, property_id: str) -> str:
        structure=self._structure(property_id)
        if structure is None:
            return ""
        for uid in self.physicalization.active_settlement_ids:
            skeleton=self.physicalization.skeleton_for(uid)
            if skeleton and any(s.uid==structure.uid for s in skeleton.structures):
                return uid
        return ""

    @staticmethod
    def _distance_to_structure(pos: WorldPos, structure) -> int:
        if structure is None or not structure.footprint:
            return 9999
        return min(abs(pos.x-int(x))+abs(pos.y-int(y)) for x,y in structure.footprint)

    def victim_suspicion(self, owner_uid: str) -> int:
        if not owner_uid:
            return 0
        return min(100,sum(
            int(row.suspicion) for row in self.state.casing_intel.values()
            if row.owner_uid==owner_uid
        ))

    @staticmethod
    def attention_label(value: int) -> str:
        value=max(0,int(value))
        if value>=70:return "alarmed"
        if value>=45:return "watchful"
        if value>=20:return "noticed"
        return "low"

    @staticmethod
    def _alarm_level(value: int) -> int:
        return 3 if value>=70 else 2 if value>=45 else 1 if value>=20 else 0

    def intel_for(self, property_id: str):
        return self.state.casing_intel.get(str(property_id))

    @staticmethod
    def can_case(structure) -> bool:
        """Survey secure property; open agricultural land is ordinary inspection."""
        return bool(structure and getattr(structure,"enclosed",False)
                    and not getattr(structure,"destroyed",False)
                    and getattr(structure,"function","") not in {
                        "farm_field","animal_pen","logging_camp","mine_site","monument"
                    })

    def start(self, property_id: str, player_pos: WorldPos, minute: int, stealth) -> tuple[bool,str]:
        structure=self._structure(property_id)
        if structure is None:
            return False,"That property is not physically present."
        if not self.can_case(structure):
            return False,"This is open land or an outdoor worksite. Inspect it directly; it does not need casing."
        if self._distance_to_structure(player_pos,structure)>5:
            return False,"Move within sight of the property before casing it."
        settlement_id=self._settlement_id(property_id)
        if not settlement_id:
            return False,"That property is outside the active settlement."
        owner=self.civics.owner_for_structure(settlement_id,structure.uid)
        intel=self.state.casing_intel.get(structure.uid)
        if intel is None:
            intel=CasingIntelState(structure.uid,settlement_id,owner_uid=owner)
            self.state.casing_intel[structure.uid]=intel
        else:
            intel.owner_uid=owner or intel.owner_uid
            intel.settlement_id=settlement_id
        intel.sessions+=1
        intel.last_started_minute=int(minute)
        self.state.player_casing_property_id=structure.uid
        self.state.player_stealth_mode=True
        witnesses=stealth.witnesses(player_pos,minute,settlement_id)
        if witnesses and intel.sessions>1:
            self._add_suspicion(intel,witnesses,2+min(6,intel.sessions-1),minute)
        return True,"Casing started. Move around the property to learn entrances, rooms, occupants, and storage."

    def stop(self) -> str:
        if not self.state.player_casing_property_id:
            return "You are not casing a property."
        self.state.player_casing_property_id=""
        return "You stop casing the property."

    def _add_suspicion(self, intel: CasingIntelState, witnesses, amount: int, minute: int) -> tuple[int,int]:
        old=intel.alarm_level
        witness_set=set(intel.witness_uids)
        witness_set.update(str(uid) for uid in witnesses if uid)
        intel.witness_uids=sorted(witness_set)[-24:]
        intel.suspicion=min(100,intel.suspicion+max(0,int(amount)))
        intel.last_observed_minute=int(minute)
        aggregate=self.victim_suspicion(intel.owner_uid)
        intel.alarm_level=self._alarm_level(max(intel.suspicion,aggregate))
        for uid in witnesses:
            npc=self.state.npcs.get(uid)
            if npc is None:
                continue
            npc.memories.append({
                "minute":int(minute),"type":"suspicious_casing",
                "subject":"player","property_id":intel.property_id,
                "salience":10+intel.alarm_level*8,"valence":-4-intel.alarm_level*2,
            })
            npc.memories=npc.memories[-40:]
            if intel.alarm_level>=2:
                rel=npc.relationships.setdefault(
                    "player",
                    {"affection":0,"trust":0,"fear":0,"respect":0,"obligation":0,"familiarity":0},
                )
                rel["trust"]=max(-100,int(rel.get("trust",0))-2)
                rel["familiarity"]=min(100,int(rel.get("familiarity",0))+2)
            if intel.alarm_level>=3 and npc.occupation=="guard":
                npc.goal="guard"
                npc.goal_score=max(int(getattr(npc,"goal_score",0)),85)
        return old,intel.alarm_level

    def _visible_nearby(self, player_pos: WorldPos, target: WorldPos, stealth, radius: int = 2) -> bool:
        if abs(player_pos.x-target.x)+abs(player_pos.y-target.y)>radius:
            return False
        return stealth.visible_from(player_pos,target)

    def _perimeter(self, structure) -> set[tuple[int,int]]:
        footprint={(int(x),int(y)) for x,y in structure.footprint}
        ring=set()
        for x,y in footprint:
            for dx,dy in self.CARDINALS:
                q=(x+dx,y+dy)
                if q not in footprint:
                    ring.add(q)
        return ring

    def _survey_targets(self, structure) -> set[tuple[int,int]]:
        """Exterior cells that can meaningfully be surveyed.

        Dense villages can place another home's wall immediately beside a
        property. Those occupied cells are not required for a complete casing
        survey because no person could physically stand there. Remaining
        exterior cells can be learned by sightline from nearby streets/yards.
        """
        out=set()
        for x,y in self._perimeter(structure):
            p=WorldPos(int(x),int(y),0)
            cell=self.physicalization.cell_at(p)
            if cell is not None and cell.structure_id and cell.structure_id!=structure.uid:
                continue
            if self.physicalization.passable(p,True):
                out.add((int(x),int(y)))
        return out or self._perimeter(structure)

    def observe_step(self, player_pos: WorldPos, minute: int, stealth) -> list[str]:
        property_id=str(self.state.player_casing_property_id or "")
        if not property_id:
            return []
        structure=self._structure(property_id)
        intel=self.state.casing_intel.get(property_id)
        if structure is None or intel is None:
            self.state.player_casing_property_id=""
            return ["The property is no longer available to case."]
        if self._distance_to_structure(player_pos,structure)>6:
            self.state.player_casing_property_id=""
            return ["You move away and stop casing the property."]

        messages=[]
        changed=False
        perimeter=self._survey_targets(structure)
        surveyed=set(intel.surveyed_cells)
        # Casing is an observation activity, not a requirement to squeeze the
        # avatar into every alley around a building. Every exposed exterior cell
        # within a short sightline can be surveyed from the current vantage.
        for x,y in sorted(perimeter):
            if abs(player_pos.x-x)+abs(player_pos.y-y)>6:
                continue
            target=WorldPos(x,y,player_pos.z)
            if not stealth.visible_from(player_pos,target):
                continue
            token=f"{x},{y}"
            if token not in surveyed:
                surveyed.add(token);changed=True
        if changed:
            intel.surveyed_cells=sorted(surveyed)[-160:]

        if structure.entrance is not None:
            entrance=WorldPos(int(structure.entrance[0]),int(structure.entrance[1]),0)
            if not intel.entrance_known and self._visible_nearby(player_pos,entrance,stealth,2):
                intel.entrance_known=True;changed=True
                messages.append("You identify the property's main entrance.")

        if self.security is not None:
            known_doors=set(intel.door_uids);known_locks=set(intel.lock_uids)
            for door in self.security.doors_for_property(property_id):
                dpos=WorldPos(door.x,door.y,door.z)
                if door.uid not in known_doors and self._visible_nearby(player_pos,dpos,stealth,2):
                    known_doors.add(door.uid);changed=True
                    messages.append("You identify a doorway in the property's access pattern.")
                if door.lock_level>0 and door.uid not in known_locks and self._visible_nearby(player_pos,dpos,stealth,1):
                    known_locks.add(door.uid);changed=True
                    messages.append(f"You inspect a {self.security.lock_band(door.lock_level)} lock.")
            intel.door_uids=sorted(known_doors);intel.lock_uids=sorted(known_locks)

        cell=self.physicalization.cell_at(player_pos)
        if cell is not None and cell.structure_id==property_id and cell.room_id:
            rooms=set(intel.room_ids)
            if cell.room_id not in rooms:
                rooms.add(cell.room_id);intel.room_ids=sorted(rooms);changed=True
                room=self.physicalization.room_by_id(cell.room_id)
                if room is not None:
                    messages.append(f"You learn the layout of a {str(room.kind).replace('_',' ')}.")

        known_storage=set(intel.storage_uids)
        for container in self.property_storage.for_property(property_id):
            cpos=WorldPos(container.x,container.y,container.z)
            if container.uid not in known_storage and self._visible_nearby(player_pos,cpos,stealth,2):
                known_storage.add(container.uid);changed=True
                messages.append(f"You locate {container.name.lower()}.")
        if known_storage!=set(intel.storage_uids):
            intel.storage_uids=sorted(known_storage)

        occupants=set(intel.occupant_uids)
        prop=self.state.properties.get(property_id)
        if prop:
            for uid in prop.occupants:
                npc=self.state.npcs.get(uid)
                if npc is None or not npc.alive or npc.z!=player_pos.z:
                    continue
                if abs(npc.x-player_pos.x)+abs(npc.y-player_pos.y)<=5 and stealth.visible_from(player_pos,WorldPos(npc.x,npc.y,npc.z)):
                    if uid not in occupants:
                        occupants.add(uid);changed=True
            intel.occupant_uids=sorted(occupants)
            if intel.entrance_known and not intel.owner_known and prop.owner_uid:
                owner=self.state.npcs.get(prop.owner_uid)
                if owner is not None and owner.uid in occupants:
                    intel.owner_known=True;changed=True

        witnesses=stealth.witnesses(player_pos,minute,intel.settlement_id)
        relevant=[]
        for uid in witnesses:
            npc=self.state.npcs.get(uid)
            if npc is None:
                continue
            if uid==intel.owner_uid or uid in intel.occupant_uids or npc.occupation=="guard":
                relevant.append(uid)
        if changed and witnesses:
            # Ordinary passersby notice repeated loitering slowly; owners,
            # occupants and guards react faster.
            amount=1+len(relevant)*2+(1 if intel.sessions>1 else 0)
            old,new=self._add_suspicion(intel,witnesses,amount,minute)
            if new>old:
                if new==1:messages.append("Your repeated attention to the property has been noticed.")
                elif new==2:messages.append("The household is watching your behavior closely.")
                else:messages.append("The property is alarmed; guards and occupants are alert to your presence.")
        return messages

    def summary(self, property_id: str | None = None) -> dict:
        property_id=str(property_id or self.state.player_casing_property_id or "")
        intel=self.state.casing_intel.get(property_id)
        structure=self._structure(property_id) if property_id else None
        if intel is None or structure is None:
            return {"active":False}
        perimeter=self._survey_targets(structure)
        surveyed={
            tuple(int(v) for v in token.split(",",1))
            for token in intel.surveyed_cells if "," in token
        }
        progress=0 if not perimeter else min(100,len(surveyed & perimeter)*100//len(perimeter))
        storage_cells=[]
        for container in self.property_storage.for_property(property_id):
            if container.uid in intel.storage_uids:
                storage_cells.append((container.x,container.y,container.z))
        return {
            "active":self.state.player_casing_property_id==property_id,
            "property_id":property_id,
            "function":str(structure.function),
            "survey_progress":progress,
            "entrance_known":bool(intel.entrance_known),
            "room_count":len(intel.room_ids),
            "storage_count":len(intel.storage_uids),
            "storage_cells":tuple(storage_cells),
            "door_count":len(intel.door_uids),
            "lock_count":len(intel.lock_uids),
            "occupant_count":len(intel.occupant_uids),
            "owner_known":bool(intel.owner_known),
            "attention":self.attention_label(max(intel.suspicion,self.victim_suspicion(intel.owner_uid))),
            "suspicion":max(intel.suspicion,self.victim_suspicion(intel.owner_uid)),
            "alarm_level":int(intel.alarm_level),
            "sessions":int(intel.sessions),
        }
