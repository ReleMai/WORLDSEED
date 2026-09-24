"""Local projection of persistent settlement plans.

This is a bounded reconstruction layer. It never invents a second village,
mutates generated terrain, or copies planned walls into player-built structure
state. The authoritative SettlementSkeleton remains the source; this module
indexes only the currently relevant cells for simulation/render queries.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from worldseed.core.coords import WorldPos


@dataclass(frozen=True, slots=True)
class PhysicalizedSettlementCell:
    x: int
    y: int
    settlement_id: str
    parcel_id: str = ""
    road_ids: tuple[str, ...] = ()
    structure_id: str = ""
    room_id: str = ""
    ground_piece_id: str = ""
    structure_piece_id: str = ""
    fixture_piece_id: str = ""
    roof_piece_id: str = ""

    @property
    def occupied(self) -> bool:
        return bool(self.structure_piece_id or self.fixture_piece_id)


class SettlementPhysicalizationSystem:
    """Materialize nearby settlement plans into a cheap local cell index."""

    ROAD_PIECES = {
        "path": "core:footpath_piece",
        "trail": "core:footpath_piece",
        "road": "core:dirt_lane_piece",
        "maintained_road": "core:cobble_road_piece",
    }

    def __init__(self, world, registry, region_planner, skeleton_planner):
        self.world = world
        self.registry = registry
        self.region_planner = region_planner
        self.skeleton_planner = skeleton_planner
        self._cells: dict[tuple[int, int], PhysicalizedSettlementCell] = {}
        self._rooms: dict[str, object] = {}
        self._structures: dict[str, object] = {}
        self._active_settlement_ids: tuple[str, ...] = ()
        self.revision = 0

    @property
    def active_settlement_ids(self) -> tuple[str, ...]:
        return self._active_settlement_ids

    def clear(self) -> None:
        self._cells.clear()
        self._rooms.clear()
        self._structures.clear()
        self._active_settlement_ids = ()
        self.revision += 1

    def _road_piece(self, road_class: str) -> str:
        preferred = self.ROAD_PIECES.get(str(road_class), "core:dirt_lane_piece")
        if preferred in self.registry.settlement_pieces:
            return preferred
        rows = sorted(
            (p.id for p in self.registry.settlement_pieces.values() if p.category == "road")
        )
        return rows[0] if rows else ""

    @staticmethod
    def _merge_cell(existing: PhysicalizedSettlementCell | None, **changes) -> PhysicalizedSettlementCell:
        base = {
            "x": changes["x"], "y": changes["y"], "settlement_id": changes["settlement_id"],
            "parcel_id": "", "road_ids": (), "structure_id": "", "room_id": "",
            "ground_piece_id": "", "structure_piece_id": "", "fixture_piece_id": "", "roof_piece_id": "",
        }
        if existing is not None:
            base.update({
                "parcel_id": existing.parcel_id, "road_ids": existing.road_ids,
                "structure_id": existing.structure_id, "room_id": existing.room_id,
                "ground_piece_id": existing.ground_piece_id,
                "structure_piece_id": existing.structure_piece_id,
                "fixture_piece_id": existing.fixture_piece_id,
                "roof_piece_id": existing.roof_piece_id,
            })
        base.update({k: v for k, v in changes.items() if k not in ("x", "y", "settlement_id")})
        base["x"] = int(changes["x"]); base["y"] = int(changes["y"])
        base["settlement_id"] = str(changes["settlement_id"])
        return PhysicalizedSettlementCell(**base)

    def _index_skeleton(self, settlement_id: str, skeleton) -> None:
        for parcel in skeleton.parcels:
            for x, y in parcel.cells:
                key = (int(x), int(y)); old = self._cells.get(key)
                self._cells[key] = self._merge_cell(
                    old, x=x, y=y, settlement_id=settlement_id, parcel_id=parcel.uid
                )

        for road in skeleton.roads:
            piece_id = self._road_piece(road.road_class)
            for x, y in road.polyline:
                key = (int(x), int(y)); old = self._cells.get(key)
                roads = tuple(sorted(set((old.road_ids if old else ()) + (road.uid,))))
                self._cells[key] = self._merge_cell(
                    old, x=x, y=y, settlement_id=settlement_id,
                    road_ids=roads, ground_piece_id=piece_id,
                )

        for structure in skeleton.structures:
            self._structures[structure.uid] = structure
            for x, y in structure.footprint:
                key = (int(x), int(y)); old = self._cells.get(key)
                self._cells[key] = self._merge_cell(
                    old, x=x, y=y, settlement_id=settlement_id, structure_id=structure.uid
                )

        for room in skeleton.rooms:
            self._rooms[room.uid] = room
            for x, y in room.cells:
                key = (int(x), int(y)); old = self._cells.get(key)
                self._cells[key] = self._merge_cell(
                    old, x=x, y=y, settlement_id=settlement_id, room_id=room.uid
                )

        for placement in skeleton.pieces:
            key = (int(placement.x), int(placement.y)); old = self._cells.get(key)
            piece = self.registry.settlement_pieces.get(placement.piece_id)
            if piece is None:
                continue
            changes = {}
            if placement.role in {"wall", "partition", "entrance", "interior_door"}:
                changes["structure_piece_id"] = placement.piece_id
            elif placement.role == "fixture":
                changes["fixture_piece_id"] = placement.piece_id
            elif placement.role == "roof" or piece.category == "roof":
                changes["roof_piece_id"] = placement.piece_id
            elif placement.role == "floor" or piece.layer == "ground":
                changes["ground_piece_id"] = placement.piece_id
            self._cells[key] = self._merge_cell(
                old, x=placement.x, y=placement.y, settlement_id=settlement_id, **changes
            )

    def sync(self, settlements: Iterable, center_region: tuple[int, int], radius: int = 0) -> int:
        """Rebuild the local index from settlements near one active region.

        Missing environmental preparation is treated as not-yet-materializable,
        never as permission to invent a fallback layout.
        """
        rx, ry = int(center_region[0]), int(center_region[1])
        selected = sorted(
            (
                s for s in settlements
                if abs(int(s.region_x) - rx) <= radius and abs(int(s.region_y) - ry) <= radius
            ),
            key=lambda s: s.uid,
        )
        new_cells = {}
        new_rooms = {}
        new_structures = {}
        old_cells, old_rooms, old_structures = self._cells, self._rooms, self._structures
        self._cells, self._rooms, self._structures = new_cells, new_rooms, new_structures
        active = []
        try:
            for settlement in selected:
                region = self.region_planner.plan(settlement.region_x, settlement.region_y, persist=True)
                try:
                    skeleton = self.skeleton_planner.plan(
                        region, settlement.uid, settlement.population, persist=True
                    )
                except ValueError:
                    continue
                active.append(settlement.uid)
                self._index_skeleton(settlement.uid, skeleton)
        except Exception:
            self._cells, self._rooms, self._structures = old_cells, old_rooms, old_structures
            raise
        self._active_settlement_ids = tuple(active)
        self.revision += 1
        return len(active)

    def cell_at(self, pos: WorldPos) -> PhysicalizedSettlementCell | None:
        if pos.z != 0:
            return None
        return self._cells.get((int(pos.x), int(pos.y)))

    def piece_def_at(self, pos: WorldPos):
        cell = self.cell_at(pos)
        if cell is None:
            return None
        piece_id = cell.structure_piece_id or cell.fixture_piece_id
        return self.registry.settlement_pieces.get(piece_id) if piece_id else None

    def passable(self, pos: WorldPos, world_passable: bool = True) -> bool:
        piece = self.piece_def_at(pos)
        return bool(world_passable if piece is None else world_passable and piece.passable)

    def blocks_sight(self, pos: WorldPos) -> bool:
        piece = self.piece_def_at(pos)
        return bool(piece and piece.blocks_sight)

    def clears_natural_feature(self, pos: WorldPos) -> bool:
        cell = self.cell_at(pos)
        if cell is None:
            return False
        return bool(
            cell.road_ids or cell.ground_piece_id or cell.structure_id
            or cell.structure_piece_id or cell.fixture_piece_id
        )

    def glyph_at(self, pos: WorldPos) -> str | None:
        cell = self.cell_at(pos)
        if cell is None:
            return None
        for piece_id in (cell.structure_piece_id, cell.fixture_piece_id, cell.ground_piece_id):
            piece = self.registry.settlement_pieces.get(piece_id)
            if piece is not None:
                return piece.glyph
        return None

    def room_at(self, pos: WorldPos) -> dict | None:
        cell = self.cell_at(pos)
        if cell is None or not cell.room_id:
            return None
        room = self._rooms.get(cell.room_id)
        if room is None:
            return None
        fixture_names = []
        for fixture_uid in getattr(room, "fixture_ids", ()):
            for c in self._cells.values():
                if c.fixture_piece_id:
                    # Fixture IDs are placement IDs, while cells store piece IDs;
                    # names are optional presentation detail and not authority.
                    pass
        return {
            "enclosed": bool(room.enclosed),
            "sheltered": bool(room.sheltered),
            "roof_percent": int(room.roof_percent),
            "area": int(room.area),
            "doors": len(room.doorway_cells),
            "beds": 1 if room.kind == "bedroom" else 0,
            "stations": fixture_names,
            "classification": str(room.kind),
            "room_id": room.uid,
            "structure_id": room.structure_plan_id,
            "settlement_id": cell.settlement_id,
        }

    def structure_at(self, pos: WorldPos):
        cell = self.cell_at(pos)
        if cell is None or not cell.structure_id:
            return None
        return self._structures.get(cell.structure_id)
