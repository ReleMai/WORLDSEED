"""Persistent indoor spaces, expressed in fixed-point metres, not world cells.

One outdoor tile corresponds to 1000 units for visual scale only. No indoor
position is rounded to a cell. Stable fixture IDs reference existing plan
pieces; indoor layouts never manufacture inventories or economic capacity.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

UNIT = 1000
ACTOR_RADIUS = 180


@dataclass(slots=True)
class InteriorRect:
    x: int
    y: int
    w: int
    h: int

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x < self.x + self.w and self.y <= y < self.y + self.h

    def overlaps(self, other: InteriorRect) -> bool:
        return (self.x < other.x + other.w and self.x + self.w > other.x
                and self.y < other.y + other.h and self.y + self.h > other.y)


@dataclass(slots=True)
class InteriorRoom:
    uid: str
    name: str
    rect: InteriorRect


@dataclass(slots=True)
class InteriorFurniture:
    uid: str
    piece_id: str
    x: int
    y: int
    w: int
    h: int
    owner_uid: str = ""
    source_uid: str = ""
    solid: bool = True

    @property
    def rect(self) -> InteriorRect:
        return InteriorRect(self.x, self.y, self.w, self.h)


@dataclass(slots=True)
class InteriorPile:
    uid: str
    x: int
    y: int
    items: dict[str, int] = field(default_factory=dict)


@dataclass(slots=True)
class InteriorStair:
    """A persistent, non-solid passage between floors of one building."""
    uid: str
    x: int
    y: int
    w: int
    h: int
    target_space_id: str
    target_x: int
    target_y: int
    direction: str = "up"

    @property
    def rect(self) -> InteriorRect:
        return InteriorRect(self.x, self.y, self.w, self.h)


@dataclass(slots=True)
class InteriorObservation:
    """Last-seen static geometry, never a live inventory or actor reference."""
    uid: str
    kind: str
    content_id: str
    x: int
    y: int
    w: int
    h: int
    height_ratio: float = 1.
    flat: bool = False
    solid: bool = False


@dataclass(slots=True)
class InteriorPlan:
    uid: str
    building_id: str
    door_uid: str
    exterior_x: int
    exterior_y: int
    exterior_z: int
    width: int
    height: int
    name: str = "Building"
    function: str = "residence"
    owner_uid: str = ""
    rooms: list[InteriorRoom] = field(default_factory=list)
    walls: list[InteriorRect] = field(default_factory=list)
    furniture: list[InteriorFurniture] = field(default_factory=list)
    entry_x: int = 0
    entry_y: int = 0
    version: int = 1
    piles: list[InteriorPile] = field(default_factory=list)
    layout_id: str = ""
    floor_index: int = 0
    floor_count: int = 1
    stairs: list[InteriorStair] = field(default_factory=list)
    furnishing_version: int = 0
    variant_id: str = ""
    floor_material: str = ""
    wall_material: str = ""
    # Fixed 500-unit cells observed by the player. Indexed only within this
    # plan/floor: entering a different building can never disclose its rooms.
    explored_cells: list[int] = field(default_factory=list)
    # Boundary cells use sixteen 125-unit subcells. Keys retain the original
    # 500-unit cell identity, so old discoveries need no reinterpretation.
    explored_detail: dict[str, int] = field(default_factory=dict)
    observed_objects: list[InteriorObservation] = field(default_factory=list)
    # None identifies a legacy plan whose existing floor memory predates wall
    # snapshots. The first gameplay observation adopts explicit wall memory.
    observed_walls: list[InteriorRect] | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> InteriorPlan:
        data = dict(value)
        data["rooms"] = [InteriorRoom(r["uid"], r["name"], InteriorRect(**r["rect"])) for r in data.get("rooms", [])]
        data["walls"] = [InteriorRect(**r) for r in data.get("walls", [])]
        data["furniture"] = [InteriorFurniture(**r) for r in data.get("furniture", [])]
        data["piles"] = [InteriorPile(**r) for r in data.get("piles", [])]
        data["stairs"] = [InteriorStair(**r) for r in data.get("stairs", [])]
        data["explored_cells"] = sorted({int(index) for index in data.get("explored_cells", [])
                                          if type(index) is int and 0 <= index < 4096})
        data["explored_detail"] = {str(index): mask for index, mask in
            data.get("explored_detail", {}).items()
            if str(index).isdigit() and 0 <= int(index) < 4096
            and type(mask) is int and 0 < mask <= 65535}
        data["observed_objects"] = [InteriorObservation(**row) for row in
            data.get("observed_objects", [])[:672]
            if row.get("kind") in ("furniture", "stairs", "exit")]
        if data.get('observed_walls') is not None:
            data['observed_walls']=[InteriorRect(**row) for row in data['observed_walls'][:256]]
        return cls(**data)


@dataclass(slots=True)
class InteriorActor:
    space_id: str
    x: int
    y: int
    target_x: int | None = None
    target_y: int | None = None
    action: str = "idle"
    last_tick: int = -1
    last_need_minute: int = -1
    # A meal is completed once per scheduled block after reaching furniture.
    # Persisted across save/load so reloading cannot award multiple meals.
    last_meal_minute: int = -1
    waypoints: list[list[int]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> InteriorActor:
        return cls(**value)
