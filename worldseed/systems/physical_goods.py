from __future__ import annotations

from worldseed.systems.state import PhysicalGoodsTransferState


class SettlementPhysicalGoodsSystem:
    """Authoritative hand-off between named NPC cargo and physical settlement stores.

    The settlement stock ledger is deliberately not touched here. A property
    container is already outside aggregate stock authority; market/workplace
    logistics may later move these physically held goods back into the aggregate
    economy. This prevents a named NPC from duplicating the same ore in both
    their bag and the settlement ledger.
    """

    def __init__(self, state, registry):
        self.state = state
        self.registry = registry

    def _item(self, item_id: str):
        return self.registry.items.get(str(item_id))

    def inventory_load(self, actor) -> tuple[int, int]:
        mass = volume = 0
        for item_id, raw_qty in actor.inventory.items():
            qty = max(0, int(raw_qty))
            item = self._item(item_id)
            if item is None or qty <= 0:
                continue
            mass += max(0, int(item.mass_g)) * qty
            volume += max(0, int(item.volume_ml)) * qty
        return mass, volume

    @staticmethod
    def carry_capacity(actor) -> tuple[int, int]:
        hauling = max(0, int(actor.skills.get("hauling", 0)))
        # A named worker has a modest carried load, not a wagon-sized inventory.
        return 22000 + hauling * 3500, 36000 + hauling * 4500

    def carry_fit(self, actor, item_id: str) -> int:
        item = self._item(item_id)
        if item is None:
            return 0
        mass, volume = self.inventory_load(actor)
        cap_mass, cap_volume = self.carry_capacity(actor)
        mfit = 999999 if item.mass_g <= 0 else max(0, (cap_mass - mass) // int(item.mass_g))
        vfit = 999999 if item.volume_ml <= 0 else max(0, (cap_volume - volume) // int(item.volume_ml))
        return max(0, min(mfit, vfit))

    def add_to_actor(self, actor, item_id: str, quantity: int) -> int:
        qty = min(max(0, int(quantity)), self.carry_fit(actor, item_id))
        if qty <= 0:
            return 0
        actor.inventory[item_id] = actor.inventory.get(item_id, 0) + qty
        return qty

    def _container_load(self, container) -> tuple[int, int]:
        mass = volume = 0
        for item_id, raw_qty in container.items.items():
            qty = max(0, int(raw_qty))
            item = self._item(item_id)
            if item is None or qty <= 0:
                continue
            mass += max(0, int(item.mass_g)) * qty
            volume += max(0, int(item.volume_ml)) * qty
        return mass, volume

    def container_fit(self, container, item_id: str) -> int:
        item = self._item(item_id)
        if item is None:
            return 0
        mass, volume = self._container_load(container)
        mfit = 999999 if item.mass_g <= 0 else max(0, (int(container.capacity_mass_g) - mass) // int(item.mass_g))
        vfit = 999999 if item.volume_ml <= 0 else max(0, (int(container.capacity_volume_ml) - volume) // int(item.volume_ml))
        return max(0, min(mfit, vfit))

    def deposit(
        self,
        actor,
        container,
        minute: int,
        *,
        items: dict[str, int] | None = None,
        unit_values: dict[str, int] | None = None,
        source_kind: str = "",
        source_uid: str = "",
        metadata: dict | None = None,
    ) -> PhysicalGoodsTransferState | None:
        requested = dict(items or actor.inventory)
        moved: dict[str, int] = {}
        for item_id in sorted(requested):
            available = max(0, int(actor.inventory.get(item_id, 0)))
            wanted = min(available, max(0, int(requested[item_id])))
            qty = min(wanted, self.container_fit(container, item_id))
            if qty <= 0:
                continue
            left = available - qty
            if left:
                actor.inventory[item_id] = left
            else:
                actor.inventory.pop(item_id, None)
            container.items[item_id] = container.items.get(item_id, 0) + qty
            moved[item_id] = qty
        if not moved:
            return None

        values = {item_id: max(0, int((unit_values or {}).get(item_id, 0))) for item_id in moved}
        total_value = sum(moved[item_id] * values.get(item_id, 0) for item_id in moved)
        uid = self.state.uid("physical-goods")
        row = PhysicalGoodsTransferState(
            uid=uid,
            settlement_id=str(container.settlement_id),
            actor_uid=str(actor.uid),
            container_uid=str(container.uid),
            direction="deposit",
            minute=int(minute),
            items=moved,
            unit_values=values,
            total_value=total_value,
            source_kind=str(source_kind),
            source_uid=str(source_uid),
            metadata=dict(metadata or {}),
        )
        self.state.physical_goods_transfers[uid] = row
        return row

    def stage_from_settlement(
        self,
        town,
        container,
        minute: int,
        *,
        items: dict[str, int],
        source_kind: str = "settlement_stock",
        source_uid: str = "",
        metadata: dict | None = None,
    ) -> PhysicalGoodsTransferState | None:
        """Move aggregate settlement stock into one exact physical container.

        This is an authority transition, not a copy: quantities leave town.stocks
        as soon as they become locally materialized.
        """
        moved: dict[str, int] = {}
        for item_id in sorted(items):
            available=max(0,int(town.stocks.get(item_id,0)))
            wanted=min(available,max(0,int(items[item_id])))
            qty=min(wanted,self.container_fit(container,item_id))
            if qty<=0:continue
            town.stocks[item_id]=available-qty
            container.items[item_id]=container.items.get(item_id,0)+qty
            moved[item_id]=qty
        if not moved:return None
        uid=self.state.uid("physical-goods")
        row=PhysicalGoodsTransferState(
            uid=uid,settlement_id=str(town.uid),actor_uid="settlement",
            container_uid=str(container.uid),direction="materialize",minute=int(minute),
            items=moved,source_kind=str(source_kind),source_uid=str(source_uid),
            metadata=dict(metadata or {}),
        )
        self.state.physical_goods_transfers[uid]=row
        return row

    def return_to_settlement(
        self,
        town,
        container,
        minute: int,
        *,
        items: dict[str, int],
        source_kind: str = "market_delivery",
        source_uid: str = "",
        metadata: dict | None = None,
    ) -> PhysicalGoodsTransferState | None:
        """Aggregate exact stored goods back into settlement stock exactly once."""
        moved: dict[str,int]={}
        for item_id in sorted(items):
            available=max(0,int(container.items.get(item_id,0)))
            qty=min(available,max(0,int(items[item_id])))
            if qty<=0:continue
            left=available-qty
            if left:container.items[item_id]=left
            else:container.items.pop(item_id,None)
            town.stocks[item_id]=town.stocks.get(item_id,0)+qty
            moved[item_id]=qty
        if not moved:return None
        uid=self.state.uid("physical-goods")
        row=PhysicalGoodsTransferState(
            uid=uid,settlement_id=str(town.uid),actor_uid="settlement",
            container_uid=str(container.uid),direction="aggregate",minute=int(minute),
            items=moved,source_kind=str(source_kind),source_uid=str(source_uid),
            metadata=dict(metadata or {}),
        )
        self.state.physical_goods_transfers[uid]=row
        return row

    def withdraw(
        self,
        actor,
        container,
        minute: int,
        *,
        items: dict[str, int],
        source_kind: str = "",
        source_uid: str = "",
        metadata: dict | None = None,
    ) -> PhysicalGoodsTransferState | None:
        moved: dict[str, int] = {}
        for item_id in sorted(items):
            available = max(0, int(container.items.get(item_id, 0)))
            wanted = min(available, max(0, int(items[item_id])))
            qty = min(wanted, self.carry_fit(actor, item_id))
            if qty <= 0:
                continue
            left = available - qty
            if left:
                container.items[item_id] = left
            else:
                container.items.pop(item_id, None)
            actor.inventory[item_id] = actor.inventory.get(item_id, 0) + qty
            moved[item_id] = qty
        if not moved:
            return None
        uid = self.state.uid("physical-goods")
        row = PhysicalGoodsTransferState(
            uid=uid,
            settlement_id=str(container.settlement_id),
            actor_uid=str(actor.uid),
            container_uid=str(container.uid),
            direction="withdraw",
            minute=int(minute),
            items=moved,
            source_kind=str(source_kind),
            source_uid=str(source_uid),
            metadata=dict(metadata or {}),
        )
        self.state.physical_goods_transfers[uid] = row
        return row
