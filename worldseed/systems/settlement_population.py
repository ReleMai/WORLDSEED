"""Bind active settlement representatives to persistent physical plans.

The simulation ledger owns people and occupations. The settlement plan owns
physical homes, rooms, parcels and workplaces. This module only binds those
existing authorities together; it does not create a second population or a
second economy.
"""
from __future__ import annotations

from dataclasses import dataclass

from worldseed.core.coords import WorldPos
from worldseed.core.rng import hash_u64
from worldseed.systems.state import CreatureState
from worldseed.systems.npc_equipment import NPCEquipmentSystem


@dataclass(frozen=True, slots=True)
class SettlementBindingStats:
    settlement_id: str
    npcs: int = 0
    homes_bound: int = 0
    workplaces_bound: int = 0
    repositioned: int = 0
    homeless: int = 0


class SettlementPopulationBinder:
    """Deterministically bind realized NPC representatives to plan IDs."""

    WORK_FUNCTIONS = {
        "farmer": ("barn", "mill", "farm_field"),
        "herder": ("animal_pen", "barn"),
        "miner": ("mine_site", "smithy"),
        "smith": ("smithy",),
        "lumberjack": ("logging_camp", "workshop"),
        "carpenter": ("workshop",),
        "cook": ("inn", "residence", "bakery"),
        "miller": ("mill",),
        "baker": ("bakery",),
        "butcher": ("butcher",),
        "fisher": ("fishery",),
        "weaver": ("weavery",),
        "tanner": ("tannery",),
        "brewer": ("brewery",),
        "potter": ("pottery",),
        "mason": ("mason_yard",),
        "merchant": ("market",),
        "hunter": (),
        "healer": ("clinic",),
        "guard": ("watchhouse",),
        "scholar": ("archive", "school"),
        "priest": ("shrine",),
    }

    def __init__(self, state, registry, seed: bytes, physicalization):
        self.state = state
        self.registry = registry
        self.seed = seed or b""
        self.physicalization = physicalization
        self.equipment = NPCEquipmentSystem(state, registry)

    @staticmethod
    def _rooms_for(skeleton, structure_id: str):
        return sorted(
            (room for room in skeleton.rooms if room.structure_plan_id == structure_id),
            key=lambda room: (room.kind, room.uid),
        )

    @staticmethod
    def _parcel_for_structure(skeleton, structure_id: str):
        return next(
            (parcel for parcel in skeleton.parcels if structure_id in parcel.structure_ids),
            None,
        )

    def _home_room(self, skeleton, structure):
        rooms = self._rooms_for(skeleton, structure.uid)
        if not rooms:
            return None
        return next((room for room in rooms if room.kind == "bedroom"), rooms[0])

    def _work_room(self, skeleton, structure):
        rooms = self._rooms_for(skeleton, structure.uid)
        if not rooms:
            return None
        preferred = {
            "smithy": ("smithy", "workshop", "storage"),
            "workshop": ("workshop", "storage"),
            "mill": ("workshop", "storage"),
            "fishery": ("workshop", "storage"),
            "barn": ("storage", "workshop"),
            "bakery": ("workshop", "storage", "room"),
            "butcher": ("workshop", "storage", "room"),
            "weavery": ("workshop", "storage", "room"),
            "tannery": ("workshop", "storage", "room"),
            "pottery": ("workshop", "storage", "room"),
            "brewery": ("workshop", "storage", "room"),
            "mason_yard": ("workshop", "storage", "room"),
            "market": ("shop", "room"),
            "clinic": ("clinic", "storage", "room"),
            "watchhouse": ("watch", "room"),
            "shrine": ("sanctuary", "room"),
            "archive": ("study", "storage", "room"),
            "school": ("study", "room"),
        }.get(structure.function, ("workshop", "storage", "room"))
        for kind in preferred:
            found = next((room for room in rooms if room.kind == kind), None)
            if found is not None:
                return found
        return rooms[0]

    def _bed_fixture(self, skeleton, room) -> str:
        if room is None:
            return ""
        placements = {piece.uid: piece for piece in skeleton.pieces}
        for fixture_id in sorted(room.fixture_ids):
            placement = placements.get(fixture_id)
            if placement is None:
                continue
            definition = self.registry.settlement_pieces.get(placement.piece_id)
            if definition is not None and "bed" in definition.tags:
                return placement.uid
        return ""

    def _ranked(self, npc_uid: str, candidates, domain: str):
        return sorted(
            candidates,
            key=lambda row: (
                -int(hash_u64(self.seed, domain, npc_uid, row.uid)),
                row.uid,
            ),
        )

    def _structure_has_role(self,skeleton,structure_uid:str,occupation:str)->bool:
        for piece in skeleton.pieces:
            if piece.structure_plan_id!=str(structure_uid):
                continue
            definition=self.registry.settlement_pieces.get(piece.piece_id)
            if definition is not None and str(definition.workplace_role)==str(occupation):
                return True
        return False

    def _spawn_in_room(self, npc_uid: str, room, occupied: set[tuple[int, int]]) -> tuple[int, int] | None:
        if room is None:
            return None
        frontage_lookup=getattr(self.physicalization,"frontage_for",None)
        frontage=frontage_lookup(room.structure_plan_id) if callable(frontage_lookup) else None
        if frontage is not None:
            # A household's room/bed IDs still bind its residents, but their
            # exterior bodies must wait outside the solid portal footprint.
            options=[frontage]+[frontage.moved(dx,dy) for dx,dy in ((-1,0),(1,0),(0,-1),(0,1))]
            candidates=[(int((p.x,p.y) in occupied),abs(p.x-frontage.x)+abs(p.y-frontage.y),p.y,p.x)
                        for p in options if self.physicalization.passable(p,True)]
            if candidates:
                _,_,y,x=min(candidates)
                return x,y
        candidates = []
        for x, y in room.cells:
            pos = WorldPos(int(x), int(y), 0)
            if not self.physicalization.passable(pos, True):
                continue
            collision = 1 if (int(x), int(y)) in occupied else 0
            score = int(hash_u64(self.seed, "npc-home-cell", npc_uid, int(x), int(y)))
            candidates.append((collision, -score, int(y), int(x)))
        if not candidates:
            return None
        _, _, y, x = min(candidates)
        return x, y

    def _common_spawn(self, skeleton, npc_uid: str, occupied: set[tuple[int, int]]) -> tuple[int, int]:
        candidates = []
        for x, y in skeleton.plan.common_cells:
            pos = WorldPos(int(x), int(y), 0)
            if not self.physicalization.passable(pos, True):
                continue
            collision = 1 if (int(x), int(y)) in occupied else 0
            score = int(hash_u64(self.seed, "npc-common-cell", npc_uid, int(x), int(y)))
            candidates.append((collision, -score, int(y), int(x)))
        if candidates:
            _, _, y, x = min(candidates)
            return x, y
        return int(skeleton.plan.anchor_x), int(skeleton.plan.anchor_y)

    def bind_settlement(self, settlement, *, reposition_unbound: bool = True) -> SettlementBindingStats:
        skeleton = self.physicalization.skeleton_for(settlement.uid)
        if skeleton is None:
            return SettlementBindingStats(str(settlement.uid))

        representatives = sorted(
            (
                npc for npc in self.state.npcs.values()
                if npc.alive and npc.settlement_id == settlement.uid
            ),
            key=lambda npc: npc.uid,
        )
        homes = sorted(
            (
                structure for structure in skeleton.structures
                if not structure.destroyed and structure.function in {"residence", "inn", "barracks", "outskirt_camp"}
            ),
            key=lambda structure: structure.uid,
        )
        structures = {structure.uid: structure for structure in skeleton.structures}
        valid_homes = {structure.uid for structure in homes}

        # Preserve already-valid bindings from saves and reserve those homes.
        home_load = {uid: 0 for uid in valid_homes}
        for npc in representatives:
            if npc.home_id in home_load:
                home_load[npc.home_id] += 1

        occupied = {
            (int(npc.x), int(npc.y))
            for npc in representatives
            if npc.home_id in valid_homes
        }
        homes_bound = workplaces_bound = repositioned = homeless = 0

        for npc in representatives:
            had_valid_home = npc.home_id in valid_homes
            home = structures.get(npc.home_id) if had_valid_home else None
            if home is None and homes:
                preferred = (
                    [row for row in homes if row.function == "barracks"] if npc.occupation == "guard"
                    else [row for row in homes if row.function == "residence"]
                )
                ranked = self._ranked(npc.uid, preferred or homes, "npc-home-structure")
                # Prefer an unused physical home. If every home is occupied,
                # share the least-loaded one rather than inventing a fake ID.
                unused = [row for row in ranked if home_load.get(row.uid, 0) == 0]
                if unused:
                    home = unused[0]
                else:
                    home = min(
                        ranked,
                        key=lambda row: (
                            home_load.get(row.uid, 0),
                            -int(hash_u64(self.seed, "npc-home-share", npc.uid, row.uid)),
                            row.uid,
                        ),
                    )
                npc.home_id = home.uid
                home_load[home.uid] = home_load.get(home.uid, 0) + 1

            if home is not None:
                homes_bound += 1
                home_room = self._home_room(skeleton, home)
                npc.home_room_id = home_room.uid if home_room is not None else ""
                npc.bed_fixture_id = self._bed_fixture(skeleton, home_room)
                # A physical property claim uses the same stable structure ID
                # as the settlement plan. Parcel membership remains discoverable
                # from the skeleton and is not a second ownership identifier.
                # Inns, barracks and camps are shared lodging, not private
                # property silently granted to their occupants.
                if home.function == "residence":
                    npc.property_id = home.uid
                    settlement.property_owners.setdefault(home.uid, npc.uid)
                else:
                    npc.property_id = ""
                if reposition_unbound and not had_valid_home and npc.uid not in getattr(self.state,"interior_actors",{}):
                    target = self._spawn_in_room(npc.uid, home_room, occupied)
                    if target is None and home.entrance is not None:
                        entrance=WorldPos(int(home.entrance[0]),int(home.entrance[1]),0)
                        if self.physicalization.passable(entrance,True):
                            target = (entrance.x,entrance.y)
                    if target is None:
                        target = self._common_spawn(skeleton, npc.uid, occupied)
                    npc.x, npc.y, npc.z = target[0], target[1], 0
                    npc.tasks = []
                    occupied.add(target)
                    repositioned += 1
                elif reposition_unbound and npc.uid not in getattr(self.state,"interior_actors",{}):
                    # Legacy exterior anchors in a now-solid shell are moved
                    # only during activation, never by render or inspection.
                    current=WorldPos(int(npc.x),int(npc.y),int(npc.z))
                    shell_blocks=getattr(self.physicalization,"shell_blocks",None)
                    rescue=getattr(self.physicalization,"displace_shell_position",None)
                    if callable(shell_blocks) and shell_blocks(current) and callable(rescue):
                        target=rescue(current,lambda p:self.physicalization.passable(p,True) and (p.x,p.y) not in occupied,max_radius=12)
                        if target is not None:
                            occupied.discard((npc.x,npc.y))
                            npc.x,npc.y,npc.z=target.x,target.y,target.z
                            npc.tasks=[]
                            occupied.add((npc.x,npc.y))
                            repositioned+=1
            else:
                npc.home_id = ""
                npc.home_room_id = ""
                npc.bed_fixture_id = ""
                npc.property_id = ""
                homeless += 1
                if reposition_unbound and npc.uid not in getattr(self.state,"interior_actors",{}):
                    target = self._common_spawn(skeleton, npc.uid, occupied)
                    npc.x, npc.y, npc.z = target[0], target[1], 0
                    npc.tasks = []
                    occupied.add(target)
                    repositioned += 1

            preferences = self.WORK_FUNCTIONS.get(npc.occupation, ())
            workplace_candidates = [
                structure for structure in skeleton.structures
                if not structure.destroyed and structure.function in preferences
            ]
            if npc.occupation == "farmer" and any(row.function == "barn" for row in workplace_candidates):
                # Fields have no room-backed stores. Bind employment to the real
                # farm barn; the profession still works the plan's crop parcels.
                workplace_candidates = [row for row in workplace_candidates if row.function == "barn"]
            if npc.workplace_id not in {row.uid for row in workplace_candidates}:
                npc.workplace_id = ""
                npc.work_room_id = ""
            if not npc.workplace_id and workplace_candidates:
                # Preference order is semantic: exact physical extraction sites
                # precede legacy fallback workshops. Hashing breaks ties only
                # between equivalent structures.
                ranked=sorted(
                    workplace_candidates,
                    key=lambda row:(
                        preferences.index(row.function),
                        -int(hash_u64(self.seed,"npc-workplace-structure",npc.uid,row.uid)),
                        row.uid,
                    ),
                )
                role_ready=[row for row in ranked if self._structure_has_role(skeleton,row.uid,npc.occupation)]
                workplace=(role_ready or ranked)[0]
                npc.workplace_id = workplace.uid
            workplace = structures.get(npc.workplace_id)
            if workplace is not None and workplace.function in preferences:
                work_room = self._work_room(skeleton, workplace)
                npc.work_room_id = work_room.uid if work_room is not None else ""
                workplaces_bound += 1
            elif not preferences:
                npc.workplace_id = ""
                npc.work_room_id = ""

        self.equipment.provision_settlement(settlement, representatives)
        return SettlementBindingStats(
            str(settlement.uid),
            npcs=len(representatives),
            homes_bound=homes_bound,
            workplaces_bound=workplaces_bound,
            repositioned=repositioned,
            homeless=homeless,
        )

    def reconcile_active(self, settlements) -> None:
        """Derive compatibility summaries from authoritative physical plans."""
        active=set(self.physicalization.active_settlement_ids)
        for settlement in settlements:
            if settlement.uid not in active:continue
            skeleton=self.physicalization.skeleton_for(settlement.uid)
            if skeleton is None:continue
            settlement.housing_capacity=int(skeleton.plan.housing_capacity)
            settlement.homeless=max(0,int(settlement.population)-settlement.housing_capacity)
            settlement.resource_specializations=list(skeleton.plan.resource_specializations[:2])
            settlement.crop_ids=list(skeleton.plan.crop_ids)
            settlement.livestock_species_ids=list(skeleton.plan.livestock_species_ids[:2])
            summary={}
            for structure in skeleton.structures:
                if structure.destroyed:continue
                key=str(structure.function or structure.building_type or "building")
                summary[key]=summary.get(key,0)+1
            farms=sum(1 for parcel in skeleton.parcels if parcel.kind=="farm")
            if farms:summary["farm"]=farms
            settlement.buildings=summary
            self._sync_livestock(settlement,skeleton)

    def _sync_livestock(self, settlement, skeleton) -> None:
        """Represent plan-owned pens with ordinary authoritative creatures."""
        pens=[p for p in skeleton.parcels if p.purpose=="animal_pen" and p.livestock_species_ids]
        for pen in pens:
            blocked={(piece.x,piece.y) for piece in skeleton.pieces if piece.structure_plan_id in set(pen.structure_ids) and piece.role not in {"pen_gate"}}
            cells=[p for p in sorted(pen.cells,key=lambda q:(q[1],q[0])) if p not in blocked]
            if not cells:continue
            for species_index,species_id in enumerate(pen.livestock_species_ids[:2]):
                spec=self.registry.species.get(species_id)
                if spec is None:continue
                for ordinal in range(2):
                    uid=f"livestock:{settlement.uid}:{pen.uid}:{species_id}:{ordinal}"
                    if uid in self.state.creatures:continue
                    pick=int(hash_u64(self.seed,"settlement-livestock",uid)%len(cells))
                    x,y=cells[pick]
                    self.state.creatures[uid]=CreatureState(
                        uid,species_id,x,y,0,spec.max_hp,behavior="calm",stamina=spec.stamina,
                        domestic=True,settlement_id=settlement.uid,pen_id=pen.uid,
                    )

    def bind_active(self, settlements) -> tuple[SettlementBindingStats, ...]:
        active = set(self.physicalization.active_settlement_ids)
        rows = []
        for settlement in sorted(settlements, key=lambda row: row.uid):
            if settlement.uid in active:
                rows.append(self.bind_settlement(settlement))
        return tuple(rows)
