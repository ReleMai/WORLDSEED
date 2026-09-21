from __future__ import annotations
from dataclasses import dataclass, field
from worldseed.core.coords import WorldPos

@dataclass(slots=True)
class Position:
    value: WorldPos

@dataclass(slots=True)
class Inventory:
    items: dict[str, int] = field(default_factory=dict)

    def add(self, item_id: str, amount: int) -> None:
        if amount <= 0:
            return
        self.items[item_id] = self.items.get(item_id, 0) + amount

    def remove(self, item_id: str, amount: int) -> bool:
        if amount <= 0:
            return True
        have = self.items.get(item_id, 0)
        if have < amount:
            return False
        left = have - amount
        if left:
            self.items[item_id] = left
        else:
            self.items.pop(item_id, None)
        return True

    def has(self, costs: dict[str, int]) -> bool:
        return all(self.count(i) >= n for i, n in costs.items())

    def consume(self, costs: dict[str, int]) -> bool:
        if not self.has(costs):
            return False
        for item_id, amount in costs.items():
            self.remove(item_id, amount)
        return True

    def count(self, item_id: str) -> int:
        return self.items.get(item_id, 0)

@dataclass(slots=True)
class Renderable:
    glyph: str
    name: str

@dataclass(slots=True)
class PlayerControlled:
    enabled: bool = True

@dataclass(slots=True)
class Vitals:
    hp: int = 100
    max_hp: int = 100
    hunger: int = 0
    thirst: int = 0
    stamina: int = 100
    body_temp: int = 50
    pain: int = 0
    blood: int = 100

@dataclass(slots=True)
class Identity:
    name: str
    age: int = 18
    culture_id: str = ""
    occupation: str = "wanderer"
    traits: tuple[str, ...] = ()

@dataclass(slots=True)
class Skills:
    values: dict[str, int] = field(default_factory=dict)

@dataclass(slots=True)
class Knowledge:
    facts: set[str] = field(default_factory=set)

@dataclass(slots=True)
class AIState:
    current_goal: str = "idle"
    goal_score: int = 0
    duty: int = 50
    fear: int = 30
    curiosity: int = 40
    social_need: int = 20

@dataclass(slots=True)
class Needs:
    hunger: int = 0
    thirst: int = 0
    rest: int = 0
    social: int = 0
    safety: int = 100

@dataclass(slots=True)
class Health:
    hp: int
    max_hp: int
    wounds: list[dict] = field(default_factory=list)
    diseases: list[str] = field(default_factory=list)

@dataclass(slots=True)
class Species:
    species_id: str

@dataclass(slots=True)
class FactionMembership:
    faction_id: str
    rank: str = "member"

@dataclass(slots=True)
class Ownership:
    owner_id: int | None = None
    faction_id: str | None = None

@dataclass(slots=True)
class Memories:
    rows: list[dict] = field(default_factory=list)

@dataclass(slots=True)
class Relationships:
    values: dict[str, dict[str, int]] = field(default_factory=dict)
