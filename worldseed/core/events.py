from dataclasses import dataclass
from worldseed.core.coords import WorldPos


@dataclass(frozen=True, slots=True)
class GameEvent:
    turn: int
    message: str


@dataclass(frozen=True, slots=True)
class MovedEvent:
    entity_id: int
    old: WorldPos
    new: WorldPos


@dataclass(frozen=True, slots=True)
class GatheredEvent:
    entity_id: int
    position: WorldPos
    item_id: str
    amount: int
