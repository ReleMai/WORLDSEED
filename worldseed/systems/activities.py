from __future__ import annotations

from dataclasses import dataclass

from worldseed.core.coords import WorldPos
from worldseed.systems.state import ActivityReservationState


@dataclass(frozen=True, slots=True)
class ActivityAffordance:
    """Transient physical opportunity derived from the authoritative local plan."""

    uid: str
    activity: str
    settlement_id: str
    target_uid: str
    target_kind: str
    workplace_role: str
    x: int
    y: int
    z: int
    use_x: int
    use_y: int
    use_z: int
    work_bonus: int = 0
    tags: tuple[str, ...] = ()


class ActivitySystem:
    """Physical affordance discovery plus persistent exclusive reservations.

    Affordances are read models rebuilt from the settlement plan. Reservations
    are authoritative simulation state so two named nearby actors cannot use the
    same station at the same time merely because their utility AI chose it.
    """

    def __init__(self, state, registry, physicalization=None, world=None):
        self.state = state
        self.registry = registry
        self.physicalization = physicalization
        self.world = world or getattr(physicalization, "world", None)

    def attach_physicalization(self, physicalization) -> None:
        self.physicalization = physicalization
        if self.world is None:
            self.world = getattr(physicalization, "world", None)

    def cleanup(self, minute: int) -> None:
        now = int(minute)
        for row in self.state.activity_reservations.values():
            if row.status in {"completed", "cancelled"}:
                continue
            if row.expires_minute >= 0 and now > row.expires_minute:
                row.status = "cancelled"
                row.completed_minute = now

    def _position_available(self, x: int, y: int, z: int) -> bool:
        pos = WorldPos(int(x), int(y), int(z))
        world_passable = True
        if self.world is not None:
            world_passable = bool(self.world.is_passable(pos))
        if self.physicalization is not None:
            return bool(self.physicalization.passable(pos, world_passable))
        return world_passable

    def _use_position(self, placement) -> tuple[int, int, int] | None:
        # Work fixtures are often themselves impassable. Reserve a cardinal
        # standing cell that still belongs to the same planned structure.
        candidates = []
        for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)):
            x, y = int(placement.x) + dx, int(placement.y) + dy
            if not self._position_available(x, y, 0):
                continue
            if self.physicalization is not None:
                cell = self.physicalization.cell_at(WorldPos(x, y, 0))
                if cell is not None and cell.structure_id and cell.structure_id != placement.structure_plan_id:
                    continue
            candidates.append((y, x))
        if candidates:
            y, x = min(candidates)
            return x, y, 0
        if self.physicalization is not None:
            fallback = self.physicalization.destination_for(placement.structure_plan_id)
            if fallback is not None:
                return int(fallback.x), int(fallback.y), int(fallback.z)
        return None

    def work_affordances(self, npc, town) -> list[ActivityAffordance]:
        if self.physicalization is None or not npc.workplace_id:
            return []
        skeleton = self.physicalization.skeleton_for(town.uid)
        if skeleton is None:
            return []
        out = []
        for placement in skeleton.pieces:
            if placement.structure_plan_id != npc.workplace_id:
                continue
            definition = self.registry.settlement_pieces.get(placement.piece_id)
            if definition is None or definition.workplace_role != npc.occupation:
                continue
            use = self._use_position(placement)
            if use is None:
                continue
            out.append(
                ActivityAffordance(
                    uid=f"affordance:work:{placement.uid}",
                    activity="work",
                    settlement_id=town.uid,
                    target_uid=placement.uid,
                    target_kind="fixture",
                    workplace_role=str(definition.workplace_role),
                    x=int(placement.x),
                    y=int(placement.y),
                    z=0,
                    use_x=use[0],
                    use_y=use[1],
                    use_z=use[2],
                    work_bonus=int(definition.work_bonus),
                    tags=tuple(sorted(set(definition.tags))),
                )
            )
        return sorted(out, key=lambda row: (-row.work_bonus, row.target_uid))

    def _occupied(self, affordance: ActivityAffordance, minute: int, actor_uid: str) -> bool:
        self.cleanup(minute)
        for row in self.state.activity_reservations.values():
            if row.status not in {"reserved", "active"} or row.actor_uid == actor_uid:
                continue
            if row.target_uid == affordance.target_uid:
                return True
            if (row.use_x, row.use_y, row.use_z) == (affordance.use_x, affordance.use_y, affordance.use_z):
                return True
        return False

    def reserve(
        self,
        npc,
        affordance: ActivityAffordance,
        minute: int,
        *,
        duration_minutes: int,
        lease_minutes: int = 240,
        phase: str = "work",
    ) -> ActivityReservationState | None:
        if self._occupied(affordance, minute, npc.uid):
            return None
        uid = self.state.uid("activity-reservation")
        row = ActivityReservationState(
            uid=uid,
            actor_uid=npc.uid,
            settlement_id=affordance.settlement_id,
            activity=affordance.activity,
            phase=str(phase),
            affordance_uid=affordance.uid,
            target_uid=affordance.target_uid,
            target_kind=affordance.target_kind,
            x=affordance.x,
            y=affordance.y,
            z=affordance.z,
            use_x=affordance.use_x,
            use_y=affordance.use_y,
            use_z=affordance.use_z,
            reserved_minute=int(minute),
            duration_minutes=max(5, int(duration_minutes)),
            expires_minute=int(minute) + max(int(duration_minutes) + 30, int(lease_minutes)),
            metadata={"work_bonus": int(affordance.work_bonus), "tags": list(affordance.tags)},
        )
        self.state.activity_reservations[uid] = row
        return row

    def _choose(
        self,
        npc,
        town,
        minute: int,
        *,
        preferred_tags: tuple[str, ...] = (),
        exclude_targets: set[str] | None = None,
    ) -> ActivityAffordance | None:
        exclude = exclude_targets or set()
        rows = [row for row in self.work_affordances(npc, town) if row.target_uid not in exclude]
        if preferred_tags:
            preferred = [row for row in rows if set(preferred_tags) & set(row.tags)]
            if preferred:
                rows = preferred
        rows.sort(
            key=lambda row: (
                abs(int(npc.x) - row.use_x) + abs(int(npc.y) - row.use_y),
                -row.work_bonus,
                row.target_uid,
            )
        )
        for row in rows:
            if not self._occupied(row, minute, npc.uid):
                return row
        return None

    @staticmethod
    def _tasks_for(row: ActivityReservationState, action: str, *, on_complete: str = "") -> list[dict]:
        return [
            {
                "kind": "move",
                "x": int(row.use_x),
                "y": int(row.use_y),
                "reservation_uid": row.uid,
                "activity_phase": row.phase,
            },
            {
                "kind": "activity",
                "action": str(action),
                "reservation_uid": row.uid,
                "on_complete": str(on_complete),
            },
        ]

    def supports_physical_work(self, npc, town) -> bool:
        """Whether this nearby job has a real activity authority to obey."""
        return npc.occupation == "smith" and bool(self.work_affordances(npc, town))

    def plan_work(self, npc, town, minute: int) -> list[dict]:
        """Return an exact work plan for occupations promoted to physical work.

        WU2 promotes smiths first: heat at a forge, then shape at an anvil.
        Other occupations keep the existing coarse representative-work path
        until their own physical activity chain is defined.
        """
        if npc.occupation != "smith":
            return []
        first = self._choose(npc, town, minute, preferred_tags=("forge",))
        if first is None:
            return []
        heat = self.reserve(npc, first, minute, duration_minutes=15, phase="heat")
        if heat is None:
            return []

        second = self._choose(
            npc,
            town,
            minute,
            preferred_tags=("anvil",),
            exclude_targets={first.target_uid},
        )
        if second is None:
            # A degraded smithy can still perform one bounded physical work
            # activity at the available station; no output is minted here.
            heat.phase = "work"
            heat.duration_minutes = 30
            heat.expires_minute = int(minute) + 240
            return self._tasks_for(heat, "smith_work", on_complete="work")

        shape = self.reserve(npc, second, minute, duration_minutes=20, phase="shape")
        if shape is None:
            heat.phase = "work"
            heat.duration_minutes = 30
            return self._tasks_for(heat, "smith_work", on_complete="work")

        return (
            self._tasks_for(heat, "smith_heat")
            + self._tasks_for(shape, "smith_shape", on_complete="work")
        )

    def progress(self, reservation_uid: str, actor_uid: str, minute: int) -> str:
        row = self.state.activity_reservations.get(str(reservation_uid))
        if row is None or row.actor_uid != str(actor_uid):
            return "failed"
        now = int(minute)
        if row.status in {"completed", "cancelled"}:
            return row.status
        if row.expires_minute >= 0 and now > row.expires_minute:
            row.status = "cancelled"
            row.completed_minute = now
            return "cancelled"

        actor = self.state.npcs.get(str(actor_uid))
        if actor is None or not actor.alive:
            row.status = "cancelled"
            row.completed_minute = now
            return "cancelled"
        if max(abs(int(actor.x) - row.use_x), abs(int(actor.y) - row.use_y), abs(int(actor.z) - row.use_z)) > 1:
            return "not_at_target"

        if row.started_minute < 0:
            row.started_minute = now
            row.status = "active"
            row.expires_minute = max(row.expires_minute, now + row.duration_minutes + 30)
            return "active"
        if now < row.started_minute + row.duration_minutes:
            return "active"

        row.status = "completed"
        row.completed_minute = now
        return "completed"

    def cancel_actor(self, actor_uid: str, minute: int) -> None:
        for row in self.state.activity_reservations.values():
            if row.actor_uid == str(actor_uid) and row.status in {"reserved", "active"}:
                row.status = "cancelled"
                row.completed_minute = int(minute)
