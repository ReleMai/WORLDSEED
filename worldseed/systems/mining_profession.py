from __future__ import annotations

from worldseed.core.coords import WorldPos
from worldseed.core.rng import hash_u64
from worldseed.systems.activities import ActivityAffordance
from worldseed.systems.state import ContainerState, MiningTripState, pos_key


class MiningProfessionSystem:
    """Physical Phase-4 miner profession.

    Named miners prospect deterministic natural cave entrances, select a real
    underground material face, travel through the cave connector, extract the
    terrain material into their own carried inventory, return to a physical
    mining-house ore bin, and deposit through SettlementPhysicalGoodsSystem.
    """

    RARITY = {
        "core:cave_wall": 1,
        "core:coal_seam": 2,
        "core:copper_vein": 4,
        "core:iron_vein": 5,
    }
    ORE_ITEMS = {"core:stone", "core:coal", "core:copper_ore", "core:iron_ore"}

    def __init__(self, state, registry, seed: bytes, world, physicalization, activities, goods):
        self.state = state
        self.registry = registry
        self.seed = seed or b""
        self.world = world
        self.physicalization = physicalization
        self.activities = activities
        self.goods = goods

    def ensure_profile(self, npc) -> None:
        if npc.occupation != "miner":
            return
        # Stable individual aptitudes give miners distinct professional profiles
        # without changing when save/load order changes.
        age_bonus = max(0, min(3, (int(npc.age) - 18) // 10))
        trait_bonus = 1 if "patient" in npc.traits else 0
        defaults = {
            "mining": 2 + age_bonus + trait_bonus + int(hash_u64(self.seed, "miner-skill", npc.uid, "mining") % 3),
            "prospecting": 1 + age_bonus // 2 + int(hash_u64(self.seed, "miner-skill", npc.uid, "prospecting") % 4),
            "hauling": 1 + int(hash_u64(self.seed, "miner-skill", npc.uid, "hauling") % 4),
            "cavecraft": 1 + trait_bonus + int(hash_u64(self.seed, "miner-skill", npc.uid, "cavecraft") % 4),
        }
        for key, value in defaults.items():
            npc.skills.setdefault(key, min(10, max(1, int(value))))
            npc.skill_xp.setdefault(key, 0)

    def _gain_xp(self, npc, skill: str, amount: int) -> None:
        self.ensure_profile(npc)
        current = max(0, int(npc.skill_xp.get(skill, 0))) + max(0, int(amount))
        level = max(0, int(npc.skills.get(skill, 0)))
        # Each level takes a little more field experience than the last.
        while level < 10 and current >= 80 + level * 30:
            current -= 80 + level * 30
            level += 1
        npc.skills[skill] = level
        npc.skill_xp[skill] = current

    def _storage_position(self, npc) -> WorldPos | None:
        if self.physicalization is None or not npc.workplace_id:
            return None
        room = self.physicalization.room_by_id(npc.work_room_id) if npc.work_room_id else None
        candidates = []
        cells = list(getattr(room, "cells", ()) or ())
        if not cells:
            target = self.physicalization.destination_for(npc.workplace_id, npc.work_room_id)
            if target is not None:
                cells = [(target.x, target.y)]
        occupied = {(int(c.x), int(c.y), int(c.z)) for c in self.state.containers.values()}
        for x, y in cells:
            pos = WorldPos(int(x), int(y), 0)
            if (pos.x, pos.y, 0) in occupied:
                continue
            if not self.physicalization.passable(pos, self.world.is_passable(pos)):
                continue
            distance = abs(int(npc.x) - pos.x) + abs(int(npc.y) - pos.y)
            candidates.append((distance, pos.y, pos.x))
        if not candidates:
            return None
        _, y, x = min(candidates)
        return WorldPos(x, y, 0)

    def ensure_mining_house_storage(self, npc, town):
        """Return the shared physical ore bin for this miner's bound work property."""
        if not npc.workplace_id:
            return None
        uid = f"mining-house-storage:{npc.workplace_id}"
        existing = next((c for c in self.state.containers.values() if c.uid == uid), None)
        if existing is not None:
            if npc.uid not in existing.keyholder_uids:
                existing.keyholder_uids = sorted(set(existing.keyholder_uids + [npc.uid]))
            return existing
        position = self._storage_position(npc)
        if position is None:
            return None
        container = ContainerState(
            uid=uid,
            x=position.x,
            y=position.y,
            z=0,
            owner=str(town.uid),
            capacity_mass_g=320000,
            capacity_volume_ml=180000,
            items={},
            name="Mining House Ore Bin",
            kind="workplace",
            movable=False,
            source_id="core:ore_bin_piece",
            settlement_id=str(town.uid),
            property_id=str(npc.workplace_id),
            room_id=str(npc.work_room_id),
            access="private",
            lock_level=0,
            locked=False,
            keyholder_uids=[npc.uid],
            seeded_from_settlement=False,
        )
        self.state.containers[pos_key(position.x, position.y, position.z)] = container
        return container

    def _surface_distance(self, town, entrance) -> int:
        return abs(int(town.x) - int(entrance.x)) + abs(int(town.y) - int(entrance.y))

    def ore_unit_value(self, item_id: str, terrain_id: str, cave_distance: int, depth: int) -> int:
        item = self.registry.items.get(str(item_id))
        base = max(1, int(getattr(item, "base_value", 1) or 1))
        rarity = max(1, int(self.RARITY.get(str(terrain_id), 1)))
        # Distance raises delivered value because remote ore consumed more labor
        # to identify and haul; selection still penalizes travel separately.
        distance_premium = min(18, max(0, int(cave_distance)) // 24)
        depth_premium = min(8, max(0, int(depth)) // 2)
        return base + rarity * 2 + distance_premium + depth_premium

    def _standing_cell(self, target: WorldPos, cave_x: int, cave_y: int) -> WorldPos | None:
        rows = []
        for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)):
            pos = WorldPos(target.x + dx, target.y + dy, target.z)
            if not self.world.is_passable(pos):
                continue
            distance = abs(pos.x - cave_x) + abs(pos.y - cave_y)
            rows.append((distance, pos.y, pos.x, pos))
        return min(rows, key=lambda row: row[:3])[3] if rows else None

    def _material_candidates(self, npc, town):
        caves = getattr(self.world.generator, "caves", None)
        if caves is None:
            return []
        self.ensure_profile(npc)
        prospecting = max(1, int(npc.skills.get("prospecting", 1)))
        cavecraft = max(1, int(npc.skills.get("cavecraft", 1)))
        search_radius = min(240, 72 + prospecting * 24)
        entrances = caves.entrances_near(int(town.x), int(town.y), search_radius)[:8]
        ore_candidates = []
        rock_candidates = []

        def add_candidate(entrance, depth, pos, generated_terrain_id):
            # Consult the live world only after geology identifies a useful
            # face. Player/NPC excavation deltas therefore remain authoritative.
            terrain = self.world.tile_at(pos).terrain
            terrain_id = str(terrain.id)
            if terrain_id != str(generated_terrain_id) or not terrain.gather_item or not terrain.depleted_to:
                return
            tags = set(terrain.tags)
            if "ore" not in tags and "rock" not in tags:
                return
            stand = self._standing_cell(pos, int(entrance.x), int(entrance.y))
            if stand is None:
                return
            surface_distance = self._surface_distance(town, entrance)
            underground_distance = abs(stand.x - int(entrance.x)) + abs(stand.y - int(entrance.y))
            trip_distance = surface_distance + underground_distance + depth * 3
            value = self.ore_unit_value(terrain.gather_item, terrain_id, trip_distance, depth)
            rarity = int(self.RARITY.get(terrain_id, 1))
            score = value * 100 + rarity * prospecting * 20 - trip_distance * max(3, 11 - prospecting)
            tie = int(hash_u64(self.seed, "miner-target", npc.uid, pos.x, pos.y, pos.z) % 100)
            row = (
                -score, -rarity, trip_distance, -depth, tie,
                entrance, pos, stand, terrain_id, str(terrain.gather_item), value,
            )
            (ore_candidates if "ore" in tags else rock_candidates).append(row)

        for entrance in entrances:
            max_depth = min(int(entrance.depth), 2 + prospecting + cavecraft // 2)
            for depth in range(1, max_depth + 1):
                z = -depth
                scan_radius = min(18, 8 + prospecting * 2)
                for radius in range(2, scan_radius + 1):
                    ring = []
                    for dx in range(-radius, radius + 1):
                        dy = radius - abs(dx)
                        ring.append((dx, dy))
                        if dy:
                            ring.append((dx, -dy))
                    for dx, dy in sorted(set(ring), key=lambda p: (p[1], p[0])):
                        pos = WorldPos(int(entrance.x) + dx, int(entrance.y) + dy, z)
                        generated_id = str(caves.terrain_at(pos))
                        if generated_id in {"core:coal_seam","core:copper_vein","core:iron_vein"}:
                            add_candidate(entrance, depth, pos, generated_id)
                            if len(ore_candidates) >= 32:
                                break
                        elif generated_id == "core:cave_wall" and len(rock_candidates) < 12:
                            add_candidate(entrance, depth, pos, generated_id)
                    if len(ore_candidates) >= 32:
                        break
                if len(ore_candidates) >= 32:
                    break
            if len(ore_candidates) >= 32:
                break

        candidates = ore_candidates or rock_candidates
        candidates.sort(key=lambda row: row[:5])
        return candidates

    @staticmethod
    def _move_task(pos: WorldPos, **extra) -> dict:
        return {
            "kind": "move", "x": int(pos.x), "y": int(pos.y), "z": int(pos.z),
            "exact": True, "physical_path": True, **extra,
        }

    def _storage_use_position(self, storage) -> WorldPos:
        rows=[]
        room_id=str(getattr(storage,"room_id","") or "")
        for dx,dy in ((0,-1),(-1,0),(1,0),(0,1)):
            pos=WorldPos(int(storage.x)+dx,int(storage.y)+dy,int(storage.z))
            if not self.world.is_passable(pos):
                continue
            if self.physicalization is not None and not self.physicalization.passable(pos,True):
                continue
            if room_id:
                cell=self.physicalization.cell_at(pos) if self.physicalization is not None else None
                if cell is not None and str(getattr(cell,"room_id","") or "") not in {"",room_id}:
                    continue
            rows.append((pos.y,pos.x,pos))
        return min(rows,key=lambda row:row[:2])[2] if rows else WorldPos(int(storage.x),int(storage.y),int(storage.z))

    def _cargo_items(self, npc) -> dict[str, int]:
        return {
            item_id: int(qty)
            for item_id, qty in npc.inventory.items()
            if int(qty) > 0 and item_id in self.ORE_ITEMS
        }

    def _return_plan(self, npc, town, storage, *, trip_uid: str = "") -> list[dict]:
        target = self._storage_use_position(storage)
        return [
            self._move_task(target, mining_trip_uid=trip_uid),
            {"kind": "perform", "action": "mining_deposit", "trip_uid": str(trip_uid), "container_uid": storage.uid},
        ]

    def abstract_worker_claim(self, town, proc, day: int, available_workers: int) -> int:
        """Remove exact named miners from the matching anonymous production slot.

        A representative miner physically extracting ore replaces, rather than
        supplements, the aggregate batch represented by that labor reservation.
        """
        if str(getattr(proc,"occupation",""))!="miner" or available_workers<=0:
            return 0
        reservation=self.state.labor_reservations.get(f"labor:{town.uid}:{proc.id}")
        if reservation is None or not reservation.active or reservation.assigned_day!=int(day):
            return 0
        exact=0
        for uid in sorted(reservation.representative_uids):
            npc=self.state.npcs.get(uid)
            if npc is None or not npc.alive or npc.occupation!="miner":
                continue
            if self.supports_physical_work(npc,town):
                exact+=1
        # The legacy representative materialization maps one named worker to one
        # process batch; preserve that accounting boundary while moving its
        # output into the physical cave/inventory/storage loop.
        return min(max(0,int(available_workers)),exact*max(1,int(proc.workers)))

    def has_active_trip(self, npc) -> bool:
        return any(
            row.miner_uid==npc.uid and row.status in {"planned","mined","returning"}
            for row in self.state.mining_trips.values()
        )

    def supports_physical_work(self, npc, town) -> bool:
        caves = getattr(self.world.generator, "caves", None)
        skeleton = self.physicalization.skeleton_for(town.uid) if self.physicalization is not None else None
        return bool(
            npc.occupation == "miner"
            and caves is not None
            and skeleton is not None
            and npc.workplace_id
        )

    def plan_work(self, npc, town, minute: int) -> list[dict]:
        if npc.occupation != "miner":
            return []
        self.ensure_profile(npc)
        storage = self.ensure_mining_house_storage(npc, town)
        if storage is None:
            return []

        cargo = self._cargo_items(npc)
        if cargo:
            open_trip = next((
                row for row in self.state.mining_trips.values()
                if row.miner_uid == npc.uid and row.status in {"mined", "returning"}
            ), None)
            return self._return_plan(npc, town, storage, trip_uid=open_trip.uid if open_trip else "")

        candidates = self._material_candidates(npc, town)
        if not candidates:
            return []
        _, _, distance, neg_depth, _, entrance, target, stand, terrain_id, item_id, unit_value = candidates[0]
        depth = abs(int(target.z))
        mining_skill = max(1, int(npc.skills.get("mining", 1)))
        duration = max(10, 34 + depth * 2 - mining_skill * 2)
        affordance = ActivityAffordance(
            uid=f"affordance:mine:{target.x}:{target.y}:{target.z}",
            activity="mining",
            settlement_id=str(town.uid),
            target_uid=f"mineral-face:{target.x}:{target.y}:{target.z}",
            target_kind="terrain",
            workplace_role="miner",
            x=target.x, y=target.y, z=target.z,
            use_x=stand.x, use_y=stand.y, use_z=stand.z,
            work_bonus=mining_skill,
            tags=("mine", "ore" if "vein" in terrain_id or "seam" in terrain_id else "rock"),
        )
        reservation = self.activities.reserve(
            npc, affordance, minute, duration_minutes=duration,
            lease_minutes=max(360, distance * 6 + duration + 120), phase="extract",
        )
        if reservation is None:
            return []

        trip_uid = self.state.uid("mining-trip")
        trip = MiningTripState(
            uid=trip_uid,
            miner_uid=npc.uid,
            settlement_id=town.uid,
            cave_x=int(entrance.x),
            cave_y=int(entrance.y),
            depth=depth,
            target_x=target.x,
            target_y=target.y,
            target_z=target.z,
            stand_x=stand.x,
            stand_y=stand.y,
            ore_terrain_id=terrain_id,
            ore_item_id=item_id,
            cave_distance=int(distance),
            unit_value=int(unit_value),
            started_minute=int(minute),
            storage_uid=storage.uid,
            metadata={
                "rarity": int(self.RARITY.get(terrain_id, 1)),
                "prospecting_skill": int(npc.skills.get("prospecting", 1)),
                "mining_skill": mining_skill,
            },
        )
        self.state.mining_trips[trip_uid] = trip
        mouth = WorldPos(int(entrance.x), int(entrance.y), 0)
        shaft = WorldPos(int(entrance.x), int(entrance.y), target.z)
        storage_pos = self._storage_use_position(storage)
        return [
            self._move_task(mouth, mining_trip_uid=trip_uid),
            {"kind": "mining_transition", "x": mouth.x, "y": mouth.y, "target_z": target.z, "trip_uid": trip_uid},
            self._move_task(stand, mining_trip_uid=trip_uid),
            {
                "kind": "activity", "action": "mine_extract",
                "reservation_uid": reservation.uid, "trip_uid": trip_uid,
                "on_complete": "mining_extract",
            },
            self._move_task(shaft, mining_trip_uid=trip_uid),
            {"kind": "mining_transition", "x": mouth.x, "y": mouth.y, "target_z": 0, "trip_uid": trip_uid},
            self._move_task(storage_pos, mining_trip_uid=trip_uid),
            {"kind": "perform", "action": "mining_deposit", "trip_uid": trip_uid, "container_uid": storage.uid},
        ]

    def transition(self, npc, task: dict, minute: int) -> str:
        x = int(task.get("x", npc.x)); y = int(task.get("y", npc.y))
        target_z = int(task.get("target_z", npc.z))
        if (int(npc.x), int(npc.y)) != (x, y):
            return "not_at_target"
        caves = getattr(self.world.generator, "caves", None)
        if caves is None or not caves.has_connector(WorldPos(x, y, target_z)):
            return "failed"
        if "started_minute" not in task:
            task["started_minute"] = int(minute)
            vertical = abs(target_z - int(npc.z))
            task["duration_minutes"] = max(5, vertical * 5)
            return "active"
        if int(minute) < int(task["started_minute"]) + int(task.get("duration_minutes", 5)):
            return "active"
        npc.z = target_z
        return "completed"

    def complete_extract(self, npc, trip_uid: str, minute: int) -> bool:
        trip = self.state.mining_trips.get(str(trip_uid))
        if trip is None or trip.miner_uid != npc.uid:
            return False
        target = WorldPos(trip.target_x, trip.target_y, trip.target_z)
        if max(abs(int(npc.x)-trip.stand_x), abs(int(npc.y)-trip.stand_y), abs(int(npc.z)-trip.target_z)) > 1:
            return False
        terrain = self.world.tile_at(target).terrain
        if str(terrain.id) != trip.ore_terrain_id or not terrain.gather_item or not terrain.depleted_to:
            trip.status = "failed"
            trip.completed_minute = int(minute)
            return False

        self.ensure_profile(npc)
        mining_skill = max(1, int(npc.skills.get("mining", 1)))
        base = max(1, int(terrain.gather_amount))
        yield_qty = base + mining_skill // 4
        fit = self.goods.carry_fit(npc, str(terrain.gather_item))
        yield_qty = min(yield_qty, fit)
        if yield_qty <= 0:
            trip.status = "returning"
            return False

        moved = self.goods.add_to_actor(npc, str(terrain.gather_item), yield_qty)
        if moved <= 0:
            trip.status = "returning"
            return False
        self.world.set_terrain(target, str(terrain.depleted_to))
        trip.extracted_quantity += int(moved)
        trip.status = "returning"
        trip.metadata["extracted_minute"] = int(minute)
        self._gain_xp(npc, "mining", 12 + trip.depth * 2 + int(self.RARITY.get(trip.ore_terrain_id, 1)) * 3)
        self._gain_xp(npc, "prospecting", 4 + int(self.RARITY.get(trip.ore_terrain_id, 1)))
        self._gain_xp(npc, "cavecraft", 2 + trip.depth)
        return True

    def deposit(self, npc, town, trip_uid: str, container_uid: str, minute: int) -> bool:
        container = next((c for c in self.state.containers.values() if c.uid == str(container_uid)), None)
        if container is None:
            return False
        if max(abs(int(npc.x)-int(container.x)), abs(int(npc.y)-int(container.y)), abs(int(npc.z)-int(container.z))) > 1:
            return False
        trip = self.state.mining_trips.get(str(trip_uid)) if trip_uid else None
        cargo = self._cargo_items(npc)
        if not cargo:
            if trip is not None:
                trip.status = "completed"
                trip.completed_minute = int(minute)
            return True

        unit_values = {}
        for item_id in cargo:
            if trip is not None and item_id == trip.ore_item_id:
                unit_values[item_id] = int(trip.unit_value)
            else:
                item = self.registry.items.get(item_id)
                unit_values[item_id] = max(1, int(getattr(item, "base_value", 1) or 1))

        transfer = self.goods.deposit(
            npc, container, minute,
            items=cargo,
            unit_values=unit_values,
            source_kind="mining_trip",
            source_uid=trip.uid if trip is not None else "",
            metadata={
                "profession": "miner",
                "cave_distance": int(trip.cave_distance) if trip is not None else 0,
                "depth": int(trip.depth) if trip is not None else 0,
            },
        )
        if transfer is None:
            return False
        if trip is not None:
            delivered = int(transfer.items.get(trip.ore_item_id, 0))
            trip.delivered_quantity += delivered
            trip.delivered_value += delivered * int(trip.unit_value)
            trip.status = "completed"
            trip.completed_minute = int(minute)
        self._gain_xp(npc, "hauling", max(2, sum(transfer.items.values()) + (trip.cave_distance // 40 if trip else 0)))
        return True
