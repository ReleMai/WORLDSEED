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
        "farmer": ("mill", "barn"),
        "herder": ("barn",),
        "miner": ("smithy",),
        "smith": ("smithy",),
        "carpenter": ("workshop",),
        "merchant": ("workshop", "mill"),
        "hunter": (),
        "healer": (),
        "guard": (),
        "scholar": (),
        "priest": (),
    }

    def __init__(self, state, registry, seed: bytes, physicalization):
        self.state = state
        self.registry = registry
        self.seed = seed or b""
        self.physicalization = physicalization

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

    def _spawn_in_room(self, npc_uid: str, room, occupied: set[tuple[int, int]]) -> tuple[int, int] | None:
        if room is None:
            return None
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
                if not structure.destroyed and structure.function == "residence"
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
                ranked = self._ranked(npc.uid, homes, "npc-home-structure")
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
                parcel = self._parcel_for_structure(skeleton, home.uid)
                npc.property_id = parcel.uid if parcel is not None else ""
                settlement.property_owners.setdefault(home.uid, npc.uid)
                if reposition_unbound and not had_valid_home:
                    target = self._spawn_in_room(npc.uid, home_room, occupied)
                    if target is None and home.entrance is not None:
                        target = (int(home.entrance[0]), int(home.entrance[1]))
                    if target is None:
                        target = self._common_spawn(skeleton, npc.uid, occupied)
                    npc.x, npc.y, npc.z = target[0], target[1], 0
                    npc.tasks = []
                    occupied.add(target)
                    repositioned += 1
            else:
                npc.home_id = ""
                npc.home_room_id = ""
                npc.bed_fixture_id = ""
                npc.property_id = ""
                homeless += 1
                if reposition_unbound:
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
            if npc.workplace_id not in {row.uid for row in workplace_candidates}:
                npc.workplace_id = ""
                npc.work_room_id = ""
            if not npc.workplace_id and workplace_candidates:
                workplace = self._ranked(
                    npc.uid, workplace_candidates, "npc-workplace-structure"
                )[0]
                npc.workplace_id = workplace.uid
            workplace = structures.get(npc.workplace_id)
            if workplace is not None and workplace.function in preferences:
                work_room = self._work_room(skeleton, workplace)
                npc.work_room_id = work_room.uid if work_room is not None else ""
                workplaces_bound += 1
            elif not preferences:
                npc.workplace_id = ""
                npc.work_room_id = ""

        return SettlementBindingStats(
            str(settlement.uid),
            npcs=len(representatives),
            homes_bound=homes_bound,
            workplaces_bound=workplaces_bound,
            repositioned=repositioned,
            homeless=homeless,
        )

    def bind_active(self, settlements) -> tuple[SettlementBindingStats, ...]:
        active = set(self.physicalization.active_settlement_ids)
        rows = []
        for settlement in sorted(settlements, key=lambda row: row.uid):
            if settlement.uid in active:
                rows.append(self.bind_settlement(settlement))
        return tuple(rows)
