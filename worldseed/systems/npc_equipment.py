"""Bounded personal equipment backed by the existing carried-goods authority."""
from __future__ import annotations

from collections import Counter

from worldseed.systems.physical_goods import SettlementPhysicalGoodsSystem


EQUIPMENT_SLOTS = frozenset({"hand", "head", "body", "hands", "legs", "offhand"})

# Modest existing tools; missing local supply is a shortage, never free gear.
JOB_TOOLS = {
    "miner": ("core:iron_pick", "core:stone_pick"),
    "lumberjack": ("core:stone_axe",),
    "farmer": ("core:crude_hoe", "core:digging_stick"),
    "smith": ("core:stone_hammer",),
    "carpenter": ("core:stone_axe", "core:stone_hammer"),
    "mason": ("core:stone_hammer",),
    "potter": ("core:digging_stick",),
    "cook": ("core:stone_knife", "core:crude_knife"),
    "butcher": ("core:stone_knife", "core:crude_knife"),
    "tanner": ("core:stone_knife", "core:stone_flake"),
    "weaver": ("core:bone_needle", "core:bone_awl"),
    "hunter": ("core:fishing_spear", "core:stone_knife"),
    "fisher": ("core:fishing_spear", "core:reed_rod"),
    "guard": ("core:iron_sword", "core:stone_axe"),
}


def starting_equipment_stock(npcs, registry) -> dict[str, int]:
    """Initial town capital only, before any named-worker issuance.

    This is called only while creating a settlement, never while loading or
    activating existing saved people. No RNG stream or geography changes.
    """
    stock: Counter[str] = Counter()
    for npc in npcs:
        if npc.age < 16:
            continue
        stock.update(("core:leather_vest", "core:leather_leggings"))
        tools = JOB_TOOLS.get(npc.occupation, ())
        if tools:
            stock[tools[0]] += 1
        if npc.occupation == "guard":
            stock["core:leather_hood"] += 1
            stock["core:wood_round_shield"] += 1
    return {iid: qty for iid, qty in sorted(stock.items()) if iid in registry.items}


class NPCEquipmentSystem:
    """Issue existing supply once and keep gear as inventory references.

    An unsuccessful attempt leaves no marker, allowing future supply to serve
    a worker. The equipment map and cumulative issuance audit are bounded per
    named NPC; there is no second wallet, roster or private stock ledger.
    """

    def __init__(self, state, registry):
        self.state = state
        self.registry = registry
        self.goods = SettlementPhysicalGoodsSystem(state, registry)

    def _valid(self, slot: str, item_id: str) -> bool:
        item = self.registry.items.get(item_id)
        if item is None or slot not in EQUIPMENT_SLOTS:
            return False
        if slot == "hand":
            return bool({"tool", "weapon"}.intersection(item.tags))
        return item.equip_slot == slot

    def reconcile(self, npc) -> None:
        used: Counter[str] = Counter()
        kept = {}
        for slot, iid in sorted(npc.equipment.items()):
            if self._valid(slot, iid) and int(npc.inventory.get(iid, 0)) > used[iid]:
                kept[slot] = iid
                used[iid] += 1
        npc.equipment = kept

    def _containers(self, npc, town):
        # Personal property and assigned employer stores only. Shared municipal
        # storage is available through town stock, not by raiding another home.
        return sorted(
            (c for c in self.state.containers.values()
             if c.settlement_id == town.uid and c.kind == "property"
             and ((c.property_id == npc.home_id and c.owner == npc.uid)
                  or (npc.workplace_id and c.property_id == npc.workplace_id))),
            key=lambda c: (c.property_id != npc.workplace_id, c.uid),
        )

    def provision(self, npc, town, minute: int, containers=()) -> int:
        self.reconcile(npc)
        if not npc.alive or npc.age < 16:
            return 0
        desired = {"body": ("core:leather_vest",), "legs": ("core:leather_leggings",)}
        if npc.occupation in JOB_TOOLS:
            desired["hand"] = JOB_TOOLS[npc.occupation]
        if npc.occupation == "guard":
            desired["head"] = ("core:leather_hood",)
            desired["offhand"] = ("core:wood_round_shield", "core:wicker_shield")
        equipped = 0
        for slot, candidates in desired.items():
            if slot in npc.equipment:
                continue
            reserved = Counter(npc.equipment.values())
            carried = next((iid for iid in candidates
                            if self._valid(slot, iid)
                            and int(npc.inventory.get(iid, 0)) > reserved[iid]), None)
            if carried is None:
                for iid in candidates:
                    if not self._valid(slot, iid):
                        continue
                    source = next((c for c in containers if int(c.items.get(iid, 0)) > 0), None)
                    moved = self.goods.issue_equipment(npc, town, iid, minute, container=source)
                    if moved:
                        carried = iid
                        break
            if carried is not None:
                npc.equipment[slot] = carried
                equipped += 1
        return equipped

    def provision_settlement(self, town, representatives=None) -> int:
        representatives = (n for n in self.state.npcs.values() if n.settlement_id == town.uid) if representatives is None else representatives
        equipped = 0
        for npc in sorted(representatives, key=lambda n: n.uid):
            equipped += self.provision(npc, town, self.state.clock_minute, self._containers(npc, town))
        return equipped
