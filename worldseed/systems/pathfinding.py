from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import heapq
from typing import Callable

from worldseed.core.coords import WorldPos
from worldseed.core.rng import hash_u64


def local_path(start: WorldPos, goal: WorldPos, is_passable, max_nodes: int = 1200) -> list[WorldPos]:
    if start.z != goal.z:
        return []
    if start == goal:
        return [start]
    q = deque([start])
    came = {start: None}
    nodes = 0
    while q and nodes < max_nodes:
        cur = q.popleft()
        nodes += 1
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = cur.moved(dx, dy)
            if nxt in came:
                continue
            if abs(nxt.x - start.x) + abs(nxt.y - start.y) > 40:
                continue
            if not is_passable(nxt):
                continue
            came[nxt] = cur
            if nxt == goal:
                path = [nxt]
                p = cur
                while p is not None:
                    path.append(p)
                    p = came[p]
                return list(reversed(path))
            q.append(nxt)
    return []


@dataclass(frozen=True, slots=True)
class RegionalRoute:
    regions: tuple[tuple[int, int], ...]
    distance: int
    danger: int
    travel_minutes: int


class HierarchicalPathfinder:
    """Coarse-to-fine path planner for long travel.

    Local actor movement remains tile based.  Long journeys are planned through
    512x512 macro-regions and can then be refined into chunk/local paths only
    when a traveler becomes relevant to the player.  This avoids pathfinding
    across hundreds of thousands of tiles for caravans and refugees.
    """

    REGION_SIZE = 512

    def __init__(self, state, seed: bytes):
        self.state = state
        self.seed = seed

    def _region_hazard(self, rx: int, ry: int) -> int:
        danger = int(hash_u64(self.seed, "route-hazard", rx, ry) % 18)
        for town in self.state.settlements.values():
            if (town.region_x, town.region_y) != (rx, ry):
                continue
            danger += town.food_stress // 8
            faction = self.state.factions.get(town.faction_id)
            if faction and faction.at_war:
                danger += 18
        return min(90, danger)

    def regional_path(self, start: tuple[int, int], goal: tuple[int, int], max_nodes: int = 4096) -> RegionalRoute:
        if start == goal:
            return RegionalRoute((start,), 0, self._region_hazard(*start), 360)
        open_heap: list[tuple[int, int, tuple[int, int]]] = []
        g = {start: 0}
        came: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
        serial = 0

        def h(node: tuple[int, int]) -> int:
            return abs(node[0] - goal[0]) + abs(node[1] - goal[1])

        heapq.heappush(open_heap, (h(start), serial, start))
        nodes = 0
        while open_heap and nodes < max_nodes:
            _, _, cur = heapq.heappop(open_heap)
            nodes += 1
            if cur == goal:
                break
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nxt = (cur[0] + dx, cur[1] + dy)
                step = 10 + self._region_hazard(*nxt)
                ng = g[cur] + step
                if ng >= g.get(nxt, 1 << 60):
                    continue
                g[nxt] = ng
                came[nxt] = cur
                serial += 1
                heapq.heappush(open_heap, (ng + h(nxt) * 10, serial, nxt))

        if goal not in came:
            # Deterministic Manhattan fallback so simulation never deadlocks.
            path = [start]
            x, y = start
            while x != goal[0]:
                x += 1 if goal[0] > x else -1
                path.append((x, y))
            while y != goal[1]:
                y += 1 if goal[1] > y else -1
                path.append((x, y))
        else:
            path = []
            cur = goal
            while cur is not None:
                path.append(cur)
                cur = came[cur]
            path.reverse()

        hazards = [self._region_hazard(*r) for r in path]
        danger = min(95, sum(hazards) // max(1, len(hazards)))
        distance = max(0, len(path) - 1)
        # 12 hours per macro-region, plus risk/terrain delay.
        travel = max(360, distance * 720 + danger * 6)
        return RegionalRoute(tuple(path), distance, danger, travel)

    def between_settlements(self, origin_id: str, destination_id: str) -> RegionalRoute | None:
        a = self.state.settlements.get(origin_id)
        b = self.state.settlements.get(destination_id)
        if not a or not b:
            return None
        return self.regional_path((a.region_x, a.region_y), (b.region_x, b.region_y))


    def chunk_corridor(self, start_world: tuple[int, int], goal_world: tuple[int, int]) -> list[tuple[int, int]]:
        """Return a deterministic coarse chunk corridor between two world points.

        Macro-regions choose the strategic route; this chunk corridor supplies
        the middle layer used by caravans/armies before any local tile path is
        realized.  Bresenham-style stepping keeps memory proportional to trip
        length rather than map area.
        """
        x0,y0=start_world[0]//32,start_world[1]//32
        x1,y1=goal_world[0]//32,goal_world[1]//32
        dx=abs(x1-x0);dy=-abs(y1-y0);sx=1 if x0<x1 else -1;sy=1 if y0<y1 else -1;err=dx+dy
        out=[]
        while True:
            out.append((x0,y0))
            if (x0,y0)==(x1,y1):break
            e2=2*err
            if e2>=dy:err+=dy;x0+=sx
            if e2<=dx:err+=dx;y0+=sy
        return out

    def full_route_between_settlements(self, origin_id: str, destination_id: str) -> dict | None:
        a=self.state.settlements.get(origin_id);b=self.state.settlements.get(destination_id)
        if not a or not b:return None
        regional=self.regional_path((a.region_x,a.region_y),(b.region_x,b.region_y))
        chunks=self.chunk_corridor((a.x,a.y),(b.x,b.y))
        return {"regional":regional,"chunks":chunks,"origin_world":(a.x,a.y),"destination_world":(b.x,b.y)}

    def settlement_graph_path(self, origin_id: str, destination_id: str) -> list[str]:
        """Dijkstra through established trade routes when possible."""
        if origin_id == destination_id:
            return [origin_id]
        edges: dict[str, list[tuple[str, int]]] = {}
        for route in self.state.trade_routes.values():
            cost = max(1, route.distance * 10 + route.danger)
            edges.setdefault(route.origin, []).append((route.destination, cost))
        heap = [(0, origin_id)]
        dist = {origin_id: 0}
        prev: dict[str, str] = {}
        while heap:
            cost, node = heapq.heappop(heap)
            if node == destination_id:
                break
            if cost != dist.get(node):
                continue
            for nxt, step in edges.get(node, []):
                nc = cost + step
                if nc < dist.get(nxt, 1 << 60):
                    dist[nxt] = nc
                    prev[nxt] = node
                    heapq.heappush(heap, (nc, nxt))
        if destination_id not in dist:
            return []
        out = [destination_id]
        while out[-1] != origin_id:
            out.append(prev[out[-1]])
        out.reverse()
        return out
