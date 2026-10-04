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
    waypoints: list[list[int]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> InteriorActor:
        return cls(**value)
