from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from worldseed.core.canonical import canonical_hash


def stable_plan_uid(kind: str, parent_uid: str, slot: str | int, geometry: Iterable[tuple[int, int]] | None = None) -> str:
    """Return a stable plan identity independent of iteration/process ordering.

    RC14 plan identity is derived only from stable parent identity, a deterministic
    slot/key, and (where appropriate) canonical geometry.  It must never depend
    on dict insertion order, Python's process hash, or transient realization IDs.
    """
    geom = None if geometry is None else [[int(x), int(y)] for x, y in geometry]
    digest = canonical_hash({"kind": str(kind), "parent": str(parent_uid), "slot": str(slot), "geometry": geom})[:24]
    return f"{kind}:{digest}"


@dataclass(slots=True)
class RegionalPlanState:
    uid: str
    region_x: int
    region_y: int
    version: int
    settlement_ids: list[str] = field(default_factory=list)
    route_ids: list[str] = field(default_factory=list)
    land_use_ids: list[str] = field(default_factory=list)
    revision: int = 0


@dataclass(slots=True)
class SettlementPlanState:
    uid: str
    settlement_id: str
    version: int
    anchor_x: int
    anchor_y: int
    archetype: str
    orientation: int = 0
    road_segment_ids: list[str] = field(default_factory=list)
    parcel_ids: list[str] = field(default_factory=list)
    structure_site_ids: list[str] = field(default_factory=list)
    crossing_ids: list[str] = field(default_factory=list)
    land_use_summary: dict[str, int] = field(default_factory=dict)
    housing_capacity: int = 0
    workplace_capacity: dict[str, int] = field(default_factory=dict)
    plan_revision: int = 0
    history_projection_revision: int = 0
    atlas_version: int = 1
    atlas_bounds: tuple[int, int, int, int] | None = None
    rank: str = "village"
    common_cells: list[tuple[int, int]] = field(default_factory=list)
    gateway_cells: list[tuple[int, int]] = field(default_factory=list)
    culture_style: str = ""


@dataclass(slots=True)
class RoomPlanState:
    """Stable interior room inside a larger planned structure."""
    uid: str
    structure_plan_id: str
    kind: str = "room"
    cells: list[tuple[int, int]] = field(default_factory=list)
    doorway_cells: list[tuple[int, int]] = field(default_factory=list)
    fixture_ids: list[str] = field(default_factory=list)
    area: int = 0
    enclosed: bool = True
    sheltered: bool = False
    roof_percent: int = 0


@dataclass(slots=True)
class StructurePiecePlan:
    """One concrete construction/furnishing piece inside a planned building."""
    uid: str
    structure_plan_id: str
    piece_id: str
    x: int
    y: int
    layer: str = "structure"
    role: str = ""


@dataclass(slots=True)
class StructurePlanState:
    uid: str
    settlement_plan_id: str
    content_id: str
    function: str
    footprint: list[tuple[int, int]] = field(default_factory=list)
    entrance: tuple[int, int] | None = None
    orientation: int = 0
    owner_uid: str = ""
    household_id: str = ""
    workplace_role: str = ""
    construction_stage: str = "planned"
    condition: int = 100
    destroyed: bool = False
    local_materialized_id: str = ""
    building_type: str = ""
    enclosed: bool = False
    interior_area: int = 0
    room_ids: list[str] = field(default_factory=list)
    piece_ids: list[str] = field(default_factory=list)
    roof_percent: int = 0


@dataclass(slots=True)
class RoadSegmentPlan:
    uid: str
    route_id: str = ""
    settlement_plan_id: str = ""
    road_class: str = "path"
    polyline: list[tuple[int, int]] = field(default_factory=list)
    chunk_corridor: list[tuple[int, int]] = field(default_factory=list)
    width: int = 1
    surface: str = "earth"
    condition: int = 100
    traffic: int = 0
    crossing_ids: list[str] = field(default_factory=list)
    blocked: bool = False
    last_maintenance_minute: int = 0


@dataclass(slots=True)
class LandUseParcel:
    uid: str
    settlement_plan_id: str
    cells: list[tuple[int, int]] = field(default_factory=list)
    kind: str = "reserve"
    owner_uid: str = ""
    fertility: int = 0
    wetness: int = 0
    current_use_state: str = "available"
    structure_ids: list[str] = field(default_factory=list)
    purpose: str = ""
    access_road_id: str = ""
    terrain_score: int = 0


@dataclass(slots=True)
class CrossingPlan:
    uid: str
    route_id: str
    x: int
    y: int
    kind: str = "ford"
    river_class: int = 0
    condition: int = 100
    blocked: bool = False


def plan_to_dict(value: Any) -> dict[str, Any]:
    return asdict(value)
