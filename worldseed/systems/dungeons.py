from __future__ import annotations

from worldseed.config import CHUNK_SIZE
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos, split_world
from worldseed.core.rng import PCG32, derive_seed, hash_u64
from worldseed.entities.components import Inventory, Vitals
from worldseed.systems.history import HistorySystem
from worldseed.systems.state import CreatureState, DungeonSiteState, GroundPile, LivingWorldState, pos_key


class DungeonSystem:
    """Persistent interactive layer over deterministic historical site geometry."""

    def __init__(self, state: LivingWorldState, registry: ContentRegistry, seed: bytes, world, history: HistorySystem) -> None:
        self.state = state
        self.registry = registry
        self.seed = seed
        self.world = world
        self.history = history

    def activate_at(self, pos: WorldPos, minute: int) -> DungeonSiteState | None:
        if pos.z >= 0:
            return None
        key, _, _ = split_world(pos)
        info = self.world.generator.sites.info(key)
        if not info:
            return None
        existing = self.state.dungeon_sites.get(info.uid)
        if existing:
            return existing
        features = self.world.generator.sites.runtime_features(key)
        ox, oy = key.x * CHUNK_SIZE, key.y * CHUNK_SIZE
        traps = {pos_key(ox+x, oy+y, key.z): True for x, y in features["traps"]}
        locks = {pos_key(ox+x, oy+y, key.z): True for x, y in features["locks"]}
        site = DungeonSiteState(info.uid, info.name, key.x, key.y, key.z, minute, traps, locks, [], False, False, info.builder, [{"minute": minute - info.age_years*365*1440, "controller": info.builder, "event": "foundation"}])
        self.state.dungeon_sites[info.uid] = site
        self._seed_loot(site, features["loot"], ox, oy, minute)
        self._spawn_occupants(site, info.danger, features["occupants"], ox, oy)
        self.history.record("site_discovered", f"{info.name}, a {info.site_type} of {info.builder}, was entered.", minute, key.x, key.y, [info.uid], salience=35)
        return site

    def site_for_pos(self, pos: WorldPos) -> DungeonSiteState | None:
        key, _, _ = split_world(pos)
        info = self.world.generator.sites.info(key)
        return None if not info else self.state.dungeon_sites.get(info.uid)

    def is_locked(self, pos: WorldPos) -> bool:
        pk = pos_key(pos.x, pos.y, pos.z)
        return any(site.locks.get(pk, False) for site in self.state.dungeon_sites.values())

    def try_unlock(self, pos: WorldPos, inv: Inventory, minute: int) -> tuple[bool, str]:
        pk = pos_key(pos.x, pos.y, pos.z)
        site = next((s for s in self.state.dungeon_sites.values() if s.locks.get(pk, False)), None)
        if not site:
            return True, ""
        if inv.count("core:ancient_key") > 0:
            site.locks[pk] = False
            return True, "The ancient key turns in the old mechanism; the lock opens."
        if inv.count("core:lockpick") <= 0:
            return False, "An ancient locked barrier blocks the way. You need a key or lockpick."
        inv.remove("core:lockpick", 1)
        chance = 62 + min(25, len([x for x in self.state.player_knowledge if "lock" in x or "craft" in x]) * 3)
        roll = hash_u64(self.seed, "dungeon-lock", site.uid, pk, minute) % 100
        if roll < chance:
            site.locks[pk] = False
            return True, "The lockpick bends, but the ancient lock clicks open."
        return False, "The lockpick snaps inside the ancient mechanism."

    def trigger_trap(self, pos: WorldPos, vitals: Vitals, turn: int) -> str | None:
        pk = pos_key(pos.x, pos.y, pos.z)
        site = next((s for s in self.state.dungeon_sites.values() if s.traps.get(pk, False)), None)
        if not site:
            return None
        site.traps[pk] = False
        rng = PCG32(derive_seed(self.seed, "dungeon-trap", site.uid, pk, turn))
        trap_type = rng.choice(["spike pit", "dart volley", "falling stone", "razor wire"])
        part = rng.choice(["left_leg", "right_leg", "torso", "left_arm", "right_arm"])
        raw = 5 + rng.randbelow(12)
        armor = self._armor_for(part)
        damage = max(1, raw - armor // 5)
        dtype = "pierce" if trap_type in ("spike pit", "dart volley") else "cut" if trap_type == "razor wire" else "blunt"
        bleed = max(0, damage // 2 + (2 if dtype in ("pierce", "cut") else 0))
        fracture = dtype == "blunt" and damage >= 9 or trap_type == "spike pit" and damage >= 11
        vitals.hp = max(0, vitals.hp - damage)
        vitals.pain = min(100, vitals.pain + damage * 2)
        vitals.blood = max(0, vitals.blood - bleed // 2)
        self.state.player_body_parts[part] = max(0, self.state.player_body_parts.get(part, 100) - damage * 3)
        self.state.player_wounds.append({"part":part,"tissue":"muscle" if damage>5 else "skin","type":dtype,"severity":min(100,damage*7),"bleeding":bleed,"fracture":fracture,"turn":turn,"source":trap_type})
        return f"A hidden {trap_type} triggers! Your {part.replace('_',' ')} takes {damage} damage."

    def glyph_at(self, pos: WorldPos) -> str | None:
        pk = pos_key(pos.x, pos.y, pos.z)
        for site in self.state.dungeon_sites.values():
            if site.locks.get(pk, False):
                return "+"
            if pk in site.traps and not site.traps[pk]:
                return "^"
        return None

    def update_cleared(self, minute: int) -> list[str]:
        cleared = []
        for site in self.state.dungeon_sites.values():
            if site.cleared or not site.occupant_uids:
                continue
            if all(uid not in self.state.creatures for uid in site.occupant_uids):
                site.cleared = True
                site.occupation_history.append({"minute":minute,"controller":"","event":"cleared"})
                site.current_controller = ""
                cleared.append(site.uid)
                self.history.record("site_cleared", f"The hostile occupants of {site.name} were defeated.", minute, site.chunk_x, site.chunk_y, [site.uid], salience=55)
        return cleared

    def inspect_at(self, pos: WorldPos) -> dict | None:
        site = self.site_for_pos(pos)
        if not site:
            return None
        pk = pos_key(pos.x, pos.y, pos.z)
        return {
            "site": site.name,
            "cleared": site.cleared,
            "armed_trap_here": site.traps.get(pk, False),
            "sprung_trap_here": pk in site.traps and not site.traps[pk],
            "locked_here": site.locks.get(pk, False),
            "hostiles_remaining": sum(uid in self.state.creatures for uid in site.occupant_uids),
        }

    def _seed_loot(self, site: DungeonSiteState, local_positions: list[tuple[int, int]], ox: int, oy: int, minute: int) -> None:
        if site.loot_seeded:
            return
        for i, (lx, ly) in enumerate(local_positions):
            x, y = ox + lx, oy + ly
            key = pos_key(x, y, site.z)
            pile = self.state.ground_piles.setdefault(key, GroundPile(x, y, site.z, {}))
            if i == 0:
                pile.items["core:ancient_key"] = pile.items.get("core:ancient_key", 0) + 1
                pile.items["core:copper_coin"] = pile.items.get("core:copper_coin", 0) + 5 + (hash_u64(self.seed, "site-coins", site.uid) % 25)
            else:
                pile.items["core:relic"] = pile.items.get("core:relic", 0) + 1
                if hash_u64(self.seed, "site-book", site.uid) % 3 == 0:
                    pile.items["core:book"] = pile.items.get("core:book", 0) + 1
        site.loot_seeded = True

    def _spawn_occupants(self, site: DungeonSiteState, danger: int, local_positions: list[tuple[int, int]], ox: int, oy: int) -> None:
        species = [s for s in self.registry.species.values() if "underground" in s.habitats]
        if not species:
            species = list(self.registry.species.values())
        rng = PCG32(derive_seed(self.seed, "site-occupants", site.uid))
        count = min(len(local_positions), max(1, min(6, 1 + danger // 22)))
        for i in range(count):
            lx, ly = local_positions[i % len(local_positions)]
            sp = rng.choice(species)
            uid = self.state.uid("dungeon-creature")
            boss = i == 0 and danger >= 72
            notable = True  # site occupants persist until defeated; later LOD can aggregate them by site
            name = f"{sp.name} Warden" if boss else ""
            hp = sp.max_hp + danger // 8
            self.state.creatures[uid] = CreatureState(uid, sp.id, ox + lx, oy + ly, site.z, hp, notable=notable, name=name)
            site.occupant_uids.append(uid)

    def _armor_for(self, part: str) -> int:
        group = "head" if part in ("head", "neck") else "arms" if "arm" in part else "legs" if "leg" in part else "torso"
        total = 0
        for iid in self.state.player_equipment.values():
            item = self.registry.items.get(iid)
            if item and group in item.coverage:
                total += item.armor
        return total
