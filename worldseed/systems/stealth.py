"""Read-only stealth perception over the same physical world used by gameplay.

Stealth is not a second visibility model. Observer cones use terrain, natural
features, player construction, and generated settlement walls/doors through the
same obstruction rules used by the simulation. The system exposes bounded
snapshots for UI and crime checks; it never mutates NPC positions or settlement
plans while rendering.
"""
from __future__ import annotations

from dataclasses import dataclass

from worldseed.core.coords import WorldPos
from worldseed.core.rng import hash_u64


@dataclass(frozen=True, slots=True)
class StealthObserverView:
    uid: str
    x: int
    y: int
    z: int
    facing_dx: int
    facing_dy: int
    vision_range: int
    sees_player: bool


class StealthSystem:
    MAX_OBSERVERS = 20
    MAX_RANGE = 12

    def __init__(self, state, seed: bytes, world, resources, building, physicalization, environment):
        self.state = state
        self.seed = seed
        self.world = world
        self.resources = resources
        self.building = building
        self.physicalization = physicalization
        self.environment = environment

    @staticmethod
    def _sign(value: int) -> int:
        return 0 if value == 0 else (1 if value > 0 else -1)

    def visible_from(
        self,
        origin: WorldPos,
        target: WorldPos,
        opaque_cache: dict[tuple[int, int, int], bool] | None = None,
    ) -> bool:
        if origin.z != target.z:
            return False
        x0, y0 = origin.x, origin.y
        x1, y1 = target.x, target.y
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        line: list[WorldPos] = []
        while True:
            line.append(WorldPos(x0, y0, origin.z))
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy
        for cell in line[1:-1]:
            key = (cell.x, cell.y, cell.z)
            blocked = None if opaque_cache is None else opaque_cache.get(key)
            if blocked is None:
                tile = self.world.tile_at(cell)
                door_lookup=getattr(self.physicalization,"door_at",None)
                physical_door=door_lookup(cell) if callable(door_lookup) else None
                door_state=(
                    self.state.door_security.get(physical_door.structure_piece_uid)
                    if physical_door is not None and getattr(physical_door,"structure_piece_uid","")
                    else None
                )
                blocked = bool(
                    tile.terrain.blocks_sight
                    or (
                        self.resources.blocks_sight(cell)
                        and not self.physicalization.clears_natural_feature(cell)
                    )
                    or self.building.blocks_sight(cell)
                    or bool(door_state and door_state.locked and not door_state.forced)
                )
                if opaque_cache is not None:
                    opaque_cache[key] = blocked
            if blocked:
                return False
        return True

    def _fallback_facing(self, npc) -> tuple[int, int]:
        directions = ((0, -1), (1, 0), (0, 1), (-1, 0))
        return directions[hash_u64(self.seed, "stealth-facing", npc.uid) % len(directions)]

    def facing(self, npc) -> tuple[int, int]:
        dx = self._sign(int(getattr(npc, "facing_dx", 0)))
        dy = self._sign(int(getattr(npc, "facing_dy", 0)))
        if dx == 0 and dy == 0:
            return self._fallback_facing(npc)
        return dx, dy

    def observer_range(self, npc, minute: int) -> int:
        base = {
            "guard": 10,
            "hunter": 9,
            "merchant": 8,
            "healer": 7,
            "priest": 7,
        }.get(str(npc.occupation), 7)
        if str(getattr(npc, "goal", "")) == "guard":
            base += 1
        casing_id=str(getattr(self.state,"player_casing_property_id","") or "")
        intel=getattr(self.state,"casing_intel",{}).get(casing_id) if casing_id else None
        if intel is not None and int(getattr(intel,"alarm_level",0))>0:
            if npc.uid==getattr(intel,"owner_uid","") or npc.uid in getattr(intel,"occupant_uids",()) or npc.occupation=="guard":
                base += min(3,int(getattr(intel,"alarm_level",0)))
        if npc.z != 0:
            return max(3, min(self.MAX_RANGE, base - 2))
        try:
            weather, lighting = self.environment.visual_conditions(int(minute), WorldPos(npc.x, npc.y, npc.z))
            visibility = max(3, min(8, int(weather.get("visibility", 8))))
            base = max(3, base * visibility // 8)
            ambient = int(getattr(lighting, "ambient_light", 65535))
            if ambient < 11000:
                base = max(3, base * 48 // 100)
            elif ambient < 22000:
                base = max(3, base * 62 // 100)
            elif ambient < 36000:
                base = max(3, base * 78 // 100)
            if int(weather.get("fog", 0)) >= 55:
                base -= 1
        except Exception:
            pass
        return max(3, min(self.MAX_RANGE, base))

    def _inside_cone(self, npc, target: WorldPos, vision_range: int) -> bool:
        dx = int(target.x) - int(npc.x)
        dy = int(target.y) - int(npc.y)
        if target.z != npc.z:
            return False
        if dx == 0 and dy == 0:
            return True
        dist2 = dx * dx + dy * dy
        if dist2 > vision_range * vision_range:
            return False
        if abs(dx) + abs(dy) <= 1:
            return True
        fx, fy = self.facing(npc)
        dot = dx * fx + dy * fy
        if dot <= 0:
            return False
        # Roughly a 90-degree field of view (45 degrees either side). Diagonal
        # facing works without floating point by comparing cross and dot terms.
        cross = abs(dx * fy - dy * fx)
        return cross <= dot

    def can_see(self, npc, target: WorldPos, minute: int) -> bool:
        radius = self.observer_range(npc, minute)
        if not self._inside_cone(npc, target, radius):
            return False
        return self.visible_from(WorldPos(npc.x, npc.y, npc.z), target)

    def movement_noise(self, base_noise: int) -> int:
        """Reduce player movement noise while sneaking without making it silent."""
        skill = max(0, int(self.state.player_skills.get("stealth", 0)))
        agility = max(1, int(self.state.player_attributes.get("agility", 5)))
        reduction = min(72, skill * 6 + max(0, agility - 5) * 4)
        return max(1, int(base_noise) * (100 - reduction) // 100)

    def _nearby_observers(self, player_pos: WorldPos, minute: int):
        rows = []
        for npc in self.state.npcs.values():
            if not npc.alive or npc.z != player_pos.z:
                continue
            radius = self.observer_range(npc, minute)
            distance = abs(int(npc.x) - player_pos.x) + abs(int(npc.y) - player_pos.y)
            if distance > radius * 2:
                continue
            rows.append((distance, npc.uid, npc, radius))
        rows.sort(key=lambda row: (row[0], row[1]))
        return rows[: self.MAX_OBSERVERS]

    def snapshot(self, player_pos: WorldPos, minute: int, active: bool = True) -> dict:
        if not active:
            return {
                "active": False,
                "cells": (),
                "observers": (),
                "seen_by": (),
                "structure_id": "",
                "room_id": "",
            }
        cell_watchers: dict[tuple[int, int, int], set[str]] = {}
        observer_views: list[StealthObserverView] = []
        opaque_cache: dict[tuple[int, int, int], bool] = {}
        for _, _, npc, radius in self._nearby_observers(player_pos, minute):
            origin = WorldPos(int(npc.x), int(npc.y), int(npc.z))
            sees_player = False
            for y in range(origin.y - radius, origin.y + radius + 1):
                for x in range(origin.x - radius, origin.x + radius + 1):
                    target = WorldPos(x, y, origin.z)
                    if not self._inside_cone(npc, target, radius):
                        continue
                    if not self.visible_from(origin, target, opaque_cache):
                        continue
                    cell_watchers.setdefault((x, y, origin.z), set()).add(npc.uid)
                    if target == player_pos:
                        sees_player = True
            fx, fy = self.facing(npc)
            observer_views.append(
                StealthObserverView(
                    npc.uid, origin.x, origin.y, origin.z, fx, fy, radius, sees_player
                )
            )
        observers_by_uid = {row.uid: row for row in observer_views}
        cells = tuple(
            {
                "x": x,
                "y": y,
                "z": z,
                "observer_uids": tuple(sorted(uids)),
                "alert": any(observers_by_uid[uid].sees_player for uid in uids),
            }
            for (x, y, z), uids in sorted(cell_watchers.items(), key=lambda row: (row[0][2], row[0][1], row[0][0]))
        )
        seen_by = tuple(sorted(row.uid for row in observer_views if row.sees_player))
        physical = self.physicalization.cell_at(player_pos)
        return {
            "active": True,
            "cells": cells,
            "observers": tuple(
                {
                    "uid": row.uid,
                    "x": row.x,
                    "y": row.y,
                    "z": row.z,
                    "facing_dx": row.facing_dx,
                    "facing_dy": row.facing_dy,
                    "range": row.vision_range,
                    "sees_player": row.sees_player,
                }
                for row in observer_views
            ),
            "seen_by": seen_by,
            "structure_id": physical.structure_id if physical is not None else "",
            "room_id": physical.room_id if physical is not None else "",
        }

    def witnesses(self, player_pos: WorldPos, minute: int, settlement_id: str = "") -> tuple[str, ...]:
        snap = self.snapshot(player_pos, minute, active=True)
        if not settlement_id:
            return tuple(snap["seen_by"])
        return tuple(
            uid
            for uid in snap["seen_by"]
            if uid in self.state.npcs and self.state.npcs[uid].settlement_id == settlement_id
        )
