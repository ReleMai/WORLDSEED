from __future__ import annotations
from dataclasses import dataclass, field
import heapq

@dataclass(order=True, slots=True)
class ScheduledEvent:
    due_minute: int
    sequence: int
    kind: str = field(compare=False)
    payload: dict = field(default_factory=dict, compare=False)

class Scheduler:
    def __init__(self) -> None:
        self._heap: list[ScheduledEvent] = []
        self._sequence = 0

    def schedule(self, due_minute: int, kind: str, payload: dict | None = None) -> None:
        self._sequence += 1
        heapq.heappush(self._heap, ScheduledEvent(int(due_minute), self._sequence, kind, payload or {}))

    def pop_due(self, minute: int) -> list[ScheduledEvent]:
        out = []
        while self._heap and self._heap[0].due_minute <= minute:
            out.append(heapq.heappop(self._heap))
        return out

    def to_json(self) -> list[dict]:
        return [{"due":e.due_minute,"seq":e.sequence,"kind":e.kind,"payload":e.payload} for e in sorted(self._heap)]

    @classmethod
    def from_json(cls, rows: list[dict]) -> "Scheduler":
        s = cls()
        for r in rows:
            ev = ScheduledEvent(int(r["due"]), int(r.get("seq", 0)), str(r["kind"]), dict(r.get("payload", {})))
            heapq.heappush(s._heap, ev); s._sequence = max(s._sequence, ev.sequence)
        return s
