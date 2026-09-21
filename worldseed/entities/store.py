from __future__ import annotations

from collections import defaultdict
from typing import Iterator, TypeVar

T = TypeVar("T")


class EntityStore:
    def __init__(self) -> None:
        self.alive: set[int] = set()
        self._components: dict[type, dict[int, object]] = defaultdict(dict)
        self._next_id = 1

    def spawn(self, preferred_id: int | None = None) -> int:
        if preferred_id is not None:
            entity_id = preferred_id
            if entity_id in self.alive:
                raise ValueError(f"Entity already exists: {entity_id}")
            self._next_id = max(self._next_id, entity_id + 1)
        else:
            entity_id = self._next_id
            self._next_id += 1
        self.alive.add(entity_id)
        return entity_id

    def despawn(self, entity_id: int) -> None:
        self.alive.discard(entity_id)
        for table in self._components.values():
            table.pop(entity_id, None)

    def add(self, entity_id: int, component: object) -> None:
        if entity_id not in self.alive:
            raise KeyError(f"Unknown entity {entity_id}")
        self._components[type(component)][entity_id] = component

    def get(self, entity_id: int, typ: type[T]) -> T:
        return self._components[typ][entity_id]  # type: ignore[return-value]

    def try_get(self, entity_id: int, typ: type[T]) -> T | None:
        return self._components.get(typ, {}).get(entity_id)  # type: ignore[return-value]

    def query(self, *types: type) -> Iterator[int]:
        if not types:
            yield from sorted(self.alive)
            return
        sets = [set(self._components.get(t, {})) for t in types]
        for entity_id in sorted(set.intersection(*sets) if sets else set()):
            if entity_id in self.alive:
                yield entity_id
