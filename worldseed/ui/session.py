from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RouteState:
    """Retained UI state for one logical screen.

    A route is intentionally UI-only: no simulation objects are mutated here.
    Selection and scroll are retained so popping a child restores the exact
    parent state the player left.
    """

    route_id: str
    title: str
    selected: int = 0
    scroll: int = 0
    payload: dict[str, Any] = field(default_factory=dict)


class NavigationStack:
    """Small screen-stack controller inspired by mature TUI screen stacks.

    Invariants:
    - root is never popped by ``back``; at root, back requests UI dismissal.
    - pushing a route never destroys parent selection/scroll.
    - replacing a route is explicit and different from pushing.
    - the stack owns *navigation state only*, never authoritative game state.
    """

    def __init__(self, root: RouteState):
        self._stack: list[RouteState] = [root]

    @property
    def current(self) -> RouteState:
        return self._stack[-1]

    @property
    def depth(self) -> int:
        return len(self._stack)

    @property
    def can_go_back(self) -> bool:
        return len(self._stack) > 1

    def push(self, route: RouteState) -> RouteState:
        self._stack.append(route)
        return route

    def replace(self, route: RouteState) -> RouteState:
        self._stack[-1] = route
        return route

    def pop(self) -> RouteState | None:
        if len(self._stack) <= 1:
            return None
        return self._stack.pop()

    def back(self) -> bool:
        """Pop one child. Return False at root so caller can dismiss UI."""
        if len(self._stack) <= 1:
            return False
        self._stack.pop()
        return True

    def reset_to_root(self) -> None:
        del self._stack[1:]

    def breadcrumbs(self, *, max_items: int = 5) -> str:
        names = [r.title for r in self._stack]
        if len(names) > max_items:
            names = ['…'] + names[-(max_items - 1):]
        return ' > '.join(names)

    def snapshot(self) -> tuple[tuple[str, int, int], ...]:
        """Stable lightweight snapshot used by navigation tests."""
        return tuple((r.route_id, r.selected, r.scroll) for r in self._stack)
