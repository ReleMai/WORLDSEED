"""Exact settlement-plan atlas.

Derived only from stable RC14 physical-plan objects. It never realizes NPCs,
generates terrain, or becomes a second settlement authority.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Iterable

from worldseed.core.canonical import canonical_hash
from worldseed.world.regional_plan import (
    BuildingPiecePlan,
    LandUseParcel,
    RoadSegmentPlan,
    RoomPlanState,
    SettlementPlanState,
    StructurePlanState,
)


@dataclass(frozen=True, slots=True)
class SettlementAtlasCell:
    x: int
    y: int
    road_ids: tuple[str, ...] = ()
    parcel_id: str = ""
    land_use: str = ""
    structure_id: str = ""
    building_type: str = ""
    room_id: str = ""
    room_kind: str = ""
    piece_ids: tuple[str, ...] = ()
    piece_content_ids: tuple[str, ...] = ()


@dataclass(slots=True)
class SettlementAtlasSnapshot:
    settlement_plan_id: str
    version: int
    left: int
    top: int
    right: int
    bottom: int
    cells: dict[tuple[int, int], SettlementAtlasCell] = field(default_factory=dict)
    labels: tuple[tuple[str, str, int, int], ...] = ()
    fingerprint: str = ""

    @property
    def width(self) -> int:
        return self.right - self.left + 1

    @property
    def height(self) -> int:
        return self.bottom - self.top + 1

    def contains(self, x: int, y: int) -> bool:
        return self.left <= x <= self.right and self.top <= y <= self.bottom

    def cell_at(self, x: int, y: int) -> SettlementAtlasCell | None:
        return self.cells.get((int(x), int(y)))

    def to_dict(self) -> dict:
        rows = [asdict(self.cells[key]) for key in sorted(self.cells, key=lambda p: (p[1], p[0]))]
        return {
            "settlement_plan_id": self.settlement_plan_id,
            "version": self.version,
            "left": self.left,
            "top": self.top,
            "right": self.right,
            "bottom": self.bottom,
            "cells": rows,
            "labels": [list(row) for row in self.labels],
            "fingerprint": self.fingerprint,
        }


def _bounds_from_points(points: set[tuple[int, int]], anchor: tuple[int, int], margin: int) -> tuple[int, int, int, int]:
    points = set(points)
    points.add((int(anchor[0]), int(anchor[1])))
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin


def build_settlement_atlas(
    plan: SettlementPlanState,
    *,
    roads: Iterable[RoadSegmentPlan] = (),
    parcels: Iterable[LandUseParcel] = (),
    structures: Iterable[StructurePlanState] = (),
    rooms: Iterable[RoomPlanState] = (),
    pieces: Iterable[BuildingPiecePlan] = (),
    margin: int = 3,
) -> SettlementAtlasSnapshot:
    """Build a deterministic sparse atlas from one settlement physical plan."""
    roads = tuple(sorted(roads, key=lambda row: row.uid))
    parcels = tuple(sorted(parcels, key=lambda row: row.uid))
    structures = tuple(sorted(structures, key=lambda row: row.uid))
    rooms = tuple(sorted(rooms, key=lambda row: row.uid))
    pieces = tuple(sorted(pieces, key=lambda row: row.uid))

    points: set[tuple[int, int]] = set()
    road_map: dict[tuple[int, int], set[str]] = {}
    parcel_map: dict[tuple[int, int], LandUseParcel] = {}
    structure_map: dict[tuple[int, int], StructurePlanState] = {}
    room_map: dict[tuple[int, int], RoomPlanState] = {}
    piece_map: dict[tuple[int, int], list[BuildingPiecePlan]] = {}

    for road in roads:
        for point in road.polyline:
            p = (int(point[0]), int(point[1]))
            points.add(p)
            road_map.setdefault(p, set()).add(road.uid)

    for parcel in parcels:
        for point in parcel.cells:
            p = (int(point[0]), int(point[1]))
            points.add(p)
            parcel_map.setdefault(p, parcel)

    for structure in structures:
        for point in structure.footprint:
            p = (int(point[0]), int(point[1]))
            points.add(p)
            structure_map.setdefault(p, structure)

    for room in rooms:
        for point in room.cells:
            p = (int(point[0]), int(point[1]))
            points.add(p)
            room_map.setdefault(p, room)
    for piece in pieces:
        p=(int(piece.x),int(piece.y));points.add(p);piece_map.setdefault(p,[]).append(piece)

    left, top, right, bottom = _bounds_from_points(
        points, (plan.anchor_x, plan.anchor_y), max(0, int(margin))
    )
    atlas = SettlementAtlasSnapshot(
        settlement_plan_id=plan.uid,
        version=max(1, int(plan.atlas_version)),
        left=left,
        top=top,
        right=right,
        bottom=bottom,
    )

    all_cells = set(road_map) | set(parcel_map) | set(structure_map) | set(room_map) | set(piece_map)
    for x, y in sorted(all_cells, key=lambda p: (p[1], p[0])):
        parcel = parcel_map.get((x, y))
        structure = structure_map.get((x, y))
        room = room_map.get((x, y))
        cell_pieces=sorted(piece_map.get((x,y),()),key=lambda p:(p.layer,p.piece_id,p.uid))
        atlas.cells[(x, y)] = SettlementAtlasCell(
            x=x,
            y=y,
            road_ids=tuple(sorted(road_map.get((x, y), ()))),
            parcel_id=parcel.uid if parcel else "",
            land_use=parcel.kind if parcel else "",
            structure_id=structure.uid if structure else "",
            building_type=(structure.building_type or structure.function) if structure else "",
            room_id=room.uid if room else "",
            room_kind=room.kind if room else "",
            piece_ids=tuple(p.uid for p in cell_pieces),
            piece_content_ids=tuple(p.piece_id for p in cell_pieces),
        )

    labels = [("settlement", plan.archetype, int(plan.anchor_x), int(plan.anchor_y))]
    for structure in structures:
        if not structure.footprint:
            continue
        xs = [p[0] for p in structure.footprint]
        ys = [p[1] for p in structure.footprint]
        labels.append((
            "building",
            structure.building_type or structure.function,
            sum(xs) // len(xs),
            sum(ys) // len(ys),
        ))
    atlas.labels = tuple(sorted(labels, key=lambda row: (row[0], row[1], row[3], row[2])))

    payload = atlas.to_dict()
    payload["fingerprint"] = ""
    atlas.fingerprint = canonical_hash(payload)
    return atlas
