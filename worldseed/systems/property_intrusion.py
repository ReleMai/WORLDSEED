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
from worldseed.systems.state import CasingIntelState, ContainerState, pos_key


_STORAGE_FUNCTIONS = {
    "residence": ("Household Chest", "core:wood_chest", ("core:wheat","core:turnip","core:dried_meat","core:clean_water","core:soap"), 3),
    "smithy": ("Smithy Stores", "core:wood_storage_box", ("core:iron_bloom","core:stone","core:wood"), 3),
    "workshop": ("Workshop Stores", "core:wood_storage_box", ("core:wood","core:leather","core:stone"), 3),
    "mill": ("Mill Stores", "core:wood_storage_box", ("core:wheat","core:wood"), 3),
    "fishery": ("Fishery Stores", "core:wood_storage_box", ("core:dried_meat","core:clean_water","core:wood"), 3),
    "barn": ("Barn Stores", "core:storage_basket", ("core:wheat","core:turnip","core:wood"), 4),
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

    def __init__(self, state, registry, seed: bytes, physicalization, civics):
        self.state=state
        self.registry=registry
        self.seed=seed
        self.physicalization=physicalization
        self.civics=civics

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
            if entrance is not None and (x,y)==(int(entrance[0]),int(entrance[1])):
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
                if entrance is not None and (x,y)==(int(entrance[0]),int(entrance[1])):
                    continue
                p=WorldPos(x,y,0)
                if self.physicalization.passable(p,True):
                    distance=0 if entrance is None else abs(x-int(entrance[0]))+abs(y-int(entrance[1]))
                    candidates.append((-distance,y,x))
        if not candidates:
            return None
        _,y,x=min(candidates)
        return WorldPos(x,y,0),room.uid

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
                access="private",lock_level=0,seeded_from_settlement=True,
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


class CasingSystem:
    """Accumulate property intel only from the player's physical survey."""

    CARDINALS=((1,0),(-1,0),(0,1),(0,-1))

    def __init__(self,state,physicalization,civics,property_storage):
        self.state=state
        self.physicalization=physicalization
        self.civics=civics
        self.property_storage=property_storage

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

    def start(self, property_id: str, player_pos: WorldPos, minute: int, stealth) -> tuple[bool,str]:
        structure=self._structure(property_id)
        if structure is None:
            return False,"That property is not physically present."
        if self._distance_to_structure(player_pos,structure)>2:
            return False,"Move next to the property before casing it."
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
        perimeter=self._perimeter(structure)
        surveyed=set(intel.surveyed_cells)
        if (player_pos.x,player_pos.y) in perimeter:
            token=f"{player_pos.x},{player_pos.y}"
            if token not in surveyed:
                surveyed.add(token);changed=True
                intel.surveyed_cells=sorted(surveyed)[-96:]

        if structure.entrance is not None:
            entrance=WorldPos(int(structure.entrance[0]),int(structure.entrance[1]),0)
            if not intel.entrance_known and self._visible_nearby(player_pos,entrance,stealth,2):
                intel.entrance_known=True;changed=True
                messages.append("You identify the property's main entrance.")

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
        perimeter=self._perimeter(structure)
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
            "occupant_count":len(intel.occupant_uids),
            "owner_known":bool(intel.owner_known),
            "attention":self.attention_label(max(intel.suspicion,self.victim_suspicion(intel.owner_uid))),
            "suspicion":max(intel.suspicion,self.victim_suspicion(intel.owner_uid)),
            "alarm_level":int(intel.alarm_level),
            "sessions":int(intel.sessions),
        }
