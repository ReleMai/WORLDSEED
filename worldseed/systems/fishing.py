"""Skill-, habitat-, bait-, and gear-aware fishing simulation."""
from __future__ import annotations

from dataclasses import dataclass

from worldseed.core.coords import WorldPos
from worldseed.core.rng import PCG32, derive_seed

_METHOD_MINUTES = {"hand": 22, "spear": 16, "rod": 30, "net": 45}
_METHOD_RANGE = {"hand": 1, "spear": 1, "rod": 3, "net": 1}
_METHOD_BASE = {"hand": 18, "spear": 28, "rod": 34, "net": 42}
_LINE_LIMIT_G = {0: 900, 1: 1800, 2: 5000, 3: 12000, 4: 25000, 5: 45000}


@dataclass(frozen=True, slots=True)
class FishingGear:
    method: str
    rod_id: str = ""
    rod_quality: int = 0
    line_id: str = ""
    line_quality: int = 0
    implement_id: str = ""
    implement_quality: int = 0

    @property
    def label(self) -> str:
        if self.method == "hand":
            return "bare hands"
        if self.method == "rod":
            return f"rod q{self.rod_quality} / line q{self.line_quality}"
        return f"{self.method} q{self.implement_quality}"


class FishingSystem:
    def __init__(self, state, registry, seed: bytes, world) -> None:
        self.state = state
        self.registry = registry
        self.seed = bytes(seed)
        self.world = world

    def region_at(self, pos: WorldPos):
        return self.world.generator.fishing_region_at(pos)

    def is_fishable(self, pos: WorldPos) -> bool:
        if pos.z != 0:
            return False
        tile = self.world.tile_at(pos)
        return "water" in tile.terrain.tags and self.region_at(pos) is not None

    def _best_item(self, inv, tag: str, quality_key: str, default_quality: int = 0):
        best = ("", 0)
        for iid, count in inv.items.items():
            if count <= 0:
                continue
            item = self.registry.items.get(iid)
            if not item or tag not in item.tags:
                continue
            quality = int(item.tool_qualities.get(quality_key, default_quality))
            if quality > best[1] or (quality == best[1] and iid < best[0]):
                best = (iid, quality)
        return best

    def gear_for(self, inv, method: str) -> FishingGear | None:
        if method == "hand":
            return FishingGear(method)
        if method == "spear":
            iid, quality = self._best_item(inv, "fishing_spear", "fish_spear", 1)
            if not iid:
                iid, quality = self._best_item(inv, "spear", "fish_spear", 1)
            return FishingGear(method, implement_id=iid, implement_quality=quality) if iid else None
        if method == "rod":
            rod_id, rod_q = self._best_item(inv, "fishing_rod", "rod_quality", 0)
            line_id, line_q = self._best_item(inv, "fishing_line", "line_quality", 0)
            if not rod_id or not line_id:
                return None
            return FishingGear(method, rod_id=rod_id, rod_quality=rod_q, line_id=line_id, line_quality=line_q)
        if method == "net":
            iid, quality = self._best_item(inv, "fishing_net", "net_quality", 0)
            return FishingGear(method, implement_id=iid, implement_quality=quality) if iid else None
        return None

    def available_methods(self, inv, target: WorldPos, distance: int) -> list[tuple[str, str]]:
        region = self.region_at(target)
        if not region:
            return []
        out = []
        for method in ("hand", "spear", "rod", "net"):
            if distance > _METHOD_RANGE[method]:
                continue
            if method in {"hand", "spear", "net"} and region.depth != "shallow":
                continue
            gear = self.gear_for(inv, method)
            if gear is None:
                continue
            out.append((method, gear.label))
        return out

    def bait_options(self, inv) -> list[str]:
        defined = set()
        for fish in self.registry.fish.values():
            defined.update(fish.bait_affinity)
        defined.update(iid for iid,n in inv.items.items() if n>0 and iid in self.registry.items
                       and 'fishing_lure' in self.registry.items[iid].tags)
        return sorted(iid for iid in defined if inv.count(iid) > 0 and iid in self.registry.items)

    def _bait_bonus(self, fish, bait_id: str) -> int:
        if not bait_id:return 0
        item=self.registry.items.get(bait_id)
        affinity=int(fish.bait_affinity.get(bait_id,0))
        if item is not None and 'fishing_lure' in item.tags:
            return max(affinity,min(30,max(1,item.quality('lure_quality'))*5))
        return affinity

    def _stock_weight(self, fish, region) -> int:
        if region.habitat not in fish.habitats or not (fish.min_temp <= region.temperature <= fish.max_temp):
            return 0
        structure_bonus = 22 if region.structure in fish.structures else 0
        base = max(2, 112 - int(fish.rarity) + region.productivity // 2 + structure_bonus)
        pressure = int(self.state.fishing_pressure.get(f"{region.uid}:{fish.id}", 0))
        return max(1, base - pressure * 4)

    def _weighted_fish(self, candidates, region, bait_id: str, rng: PCG32):
        rows = []
        total = 0
        for fish in candidates:
            weight = self._stock_weight(fish, region)
            if weight <= 0:
                continue
            weight += max(0, self._bait_bonus(fish, bait_id)) * 2
            rows.append((fish, weight))
            total += weight
        if not rows:
            return None
        roll = rng.randbelow(total)
        for fish, weight in rows:
            if roll < weight:
                return fish
            roll -= weight
        return rows[-1][0]

    def _practice(self, success: bool, weight_g: int = 0) -> None:
        level = int(self.state.player_skills.get("fishing", 0))
        if level >= 10:
            return
        gain = 2 if success else 1
        if success and weight_g >= 4000:
            gain += 1
        self.state.player_fishing_xp = int(self.state.player_fishing_xp) + gain
        threshold = 24 + level * 14
        if self.state.player_fishing_xp >= threshold:
            self.state.player_fishing_xp -= threshold
            self.state.player_skills["fishing"] = level + 1

    def daily_update(self) -> None:
        recovered = {}
        for key, value in self.state.fishing_pressure.items():
            left = max(0, int(value) - 2)
            if left:
                recovered[key] = left
        self.state.fishing_pressure = recovered

    def attempt(self, target: WorldPos, inv, method: str, bait_id: str, minute: int, skill: int, perception: int, survival: int):
        region = self.region_at(target)
        if not region or not self.is_fishable(target):
            return False, "There is no fishable water there.", 10, {}
        method = str(method).lower()
        if method not in _METHOD_MINUTES:
            return False, "Unknown fishing method.", 10, {}
        origin_range = _METHOD_RANGE[method]
        gear = self.gear_for(inv, method)
        if gear is None:
            return False, f"You do not have the gear required for {method} fishing.", 10, {}
        if method in {"hand", "spear", "net"} and region.depth != "shallow":
            return False, f"{method.title()} fishing requires shallow water.", 10, {}

        lure = False
        if bait_id:
            bait = self.registry.items.get(bait_id)
            if not bait or inv.count(bait_id) <= 0:
                return False, "You do not have that bait.", 10, {}
            lure = "fishing_lure" in bait.tags
            if not lure:
                inv.remove(bait_id, 1)

        self.state.fishing_attempts = int(self.state.fishing_attempts) + 1
        rng = PCG32(derive_seed(
            self.seed, "fishing-attempt", region.uid, target.x, target.y,
            int(minute), self.state.fishing_attempts, method, bait_id
        ))

        candidates = [
            fish for fish in self.registry.fish.values()
            if method in fish.methods and self._stock_weight(fish, region) > 0
        ]
        fish = self._weighted_fish(candidates, region, bait_id, rng)
        if fish is None:
            self._practice(False)
            return False, f"The {region.structure.replace('_',' ')} shows no fish sign worth working.", _METHOD_MINUTES[method], {"region": region.uid}

        bait_bonus = self._bait_bonus(fish, bait_id)
        gear_bonus = gear.rod_quality * 5 + gear.line_quality * 2 + gear.implement_quality * 5
        pressure = int(self.state.fishing_pressure.get(f"{region.uid}:{fish.id}", 0))
        chance = (
            _METHOD_BASE[method] + min(40, max(0, skill) * 4)
            + min(16, max(0, perception) * 2)
            + min(10, max(0, survival))
            + region.productivity // 7 + bait_bonus // 2 + gear_bonus
            - int(fish.rarity) // 3 - pressure * 2
        )
        if method == "rod" and not bait_id:
            chance -= 12
        chance = max(6, min(92, chance))
        if rng.randbelow(100) >= chance:
            self._practice(False)
            hint = f" Bait affinity would add up to {max(fish.bait_affinity.values(), default=0)} points." if not bait_id else ""
            return False, f"No catch. You work the {region.structure.replace('_',' ')} with {gear.label}; the fish do not commit.{hint}", _METHOD_MINUTES[method], {"region": region.uid, "chance": chance}

        span = max(1, fish.max_weight_g - fish.min_weight_g)
        size_bonus = min(420, skill * 28 + gear.rod_quality * 55 + gear.line_quality * 28 + region.productivity * 2)
        size_roll = min(999, (rng.randbelow(1000) * 2 + size_bonus) // 2)
        weight_g = fish.min_weight_g + span * size_roll // 999

        if method == "hand":
            weight_g = min(weight_g, max(fish.min_weight_g, 1100 + skill * 80))
        elif method == "spear":
            weight_g = min(weight_g, max(fish.min_weight_g, 7000 + gear.implement_quality * 1200))
        elif method == "net":
            weight_g = min(weight_g, max(fish.min_weight_g, 3500 + gear.implement_quality * 900))

        if method == "rod":
            line_limit = _LINE_LIMIT_G.get(min(5, max(0, gear.line_quality)), _LINE_LIMIT_G[5])
            strain = fish.fight + weight_g // 220 - skill * 4 - gear.rod_quality * 8
            if weight_g > line_limit or strain > 100:
                break_risk = 72 if weight_g > line_limit else min(65, max(8, strain - 45))
                if rng.randbelow(100) < break_risk:
                    inv.remove(gear.line_id, 1)
                    self._practice(False)
                    return False, f"A {fish.name} overloads the tackle and breaks your {self.registry.items[gear.line_id].name.lower()}.", _METHOD_MINUTES[method], {"region": region.uid, "fish": fish.id, "escaped": True, "line_broke": True}
                self._practice(False)
                return False, f"You hook a heavy {fish.name}, but it throws the line before you can land it.", _METHOD_MINUTES[method], {"region": region.uid, "fish": fish.id, "escaped": True}

        count = 1
        if method == "net" and fish.schooling >= 4:
            count += 1 if rng.randbelow(100) < min(70, 20 + skill * 4 + gear.implement_quality * 8) else 0
            count += 1 if fish.schooling >= 8 and rng.randbelow(100) < min(45, 8 + skill * 3) else 0

        damage_penalty = {"hand": 2, "spear": 18, "rod": 0, "net": 8}[method]
        quality = (
            fish.quality_base + skill * 3 + perception + bait_bonus // 3
            + gear.rod_quality * 4 + gear.line_quality * 2 + gear.implement_quality * 2
            + region.productivity // 8 - damage_penalty - pressure
            + rng.randbelow(21) - 10
        )
        quality = max(10, min(100, quality))
        quality_label = "poor" if quality < 35 else "fair" if quality < 50 else "good" if quality < 70 else "prime" if quality < 85 else "exceptional"
        ratio = (weight_g - fish.min_weight_g) * 100 // max(1, span)
        size_label = "small" if ratio < 25 else "average" if ratio < 55 else "large" if ratio < 82 else "trophy-sized"

        inv.add(fish.item_id, count)
        pressure_key = f"{region.uid}:{fish.id}"
        self.state.fishing_pressure[pressure_key] = min(25, pressure + count * 2)
        record = {
            "minute": int(minute), "zone": region.uid, "habitat": region.habitat,
            "structure": region.structure, "species_id": fish.id, "item_id": fish.item_id,
            "method": method, "bait_id": bait_id, "weight_g": int(weight_g),
            "quality": int(quality), "count": int(count),
        }
        self.state.player_fishing_log.append(record)
        if len(self.state.player_fishing_log) > 240:
            del self.state.player_fishing_log[:-240]
        self._practice(True, weight_g)

        bait_name = self.registry.items[bait_id].name if bait_id in self.registry.items else "no bait"
        count_text = f" x{count}" if count > 1 else ""
        msg = (
            f"You land {size_label} {fish.name}{count_text} ({weight_g/1000:.2f} kg representative catch, "
            f"{quality_label} quality {quality}/100) from the {region.structure.replace('_',' ')} "
            f"using {gear.label} and {bait_name}."
        )
        return True, msg, _METHOD_MINUTES[method], {"region": region.uid, "fish": fish.id, "weight_g": weight_g, "quality": quality, "count": count}
