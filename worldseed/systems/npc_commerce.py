"""Named workers trade carried goods at the existing settlement market."""
from __future__ import annotations

from collections import Counter

from worldseed.core.coords import WorldPos
from worldseed.systems.household_economy import FOODS


class NPCCommerceSystem:
    def __init__(self, state, registry, economy, goods, physicalization, storage_access):
        self.state = state
        self.registry = registry
        self.economy = economy
        self.goods = goods
        self.physicalization = physicalization
        self.storage_access = storage_access

    def market_position(self, town):
        skeleton_lookup = getattr(self.physicalization, 'skeleton_for', None)
        skeleton = skeleton_lookup(town.uid) if skeleton_lookup else None
        frontage = getattr(self.physicalization, 'frontage_for', None)
        if skeleton is not None and frontage:
            for structure in sorted(getattr(skeleton, 'structures', ()), key=lambda s: s.uid):
                if structure.function == 'market' and not structure.destroyed:
                    target = frontage(structure.uid)
                    if target is not None:
                        return target
        lookup = getattr(self.physicalization, 'destination_for_function', None)
        return (lookup(town.uid, ('market',)) if lookup else None) or WorldPos(town.x, town.y, 0)

    def _market_tasks(self, town, action, items):
        pos = self.market_position(town)
        return [dict(kind='move', x=pos.x, y=pos.y, z=pos.z, physical_path=True,
                     commerce_task=True),
                dict(kind='perform', action=action, items=dict(items), commerce_task=True)]

    def plan_inputs(self, npc, town, inputs, minute):
        """Plan owned-storage withdrawals and a paid purchase, without moving goods."""
        needed = {iid: max(0, qty-int(npc.inventory.get(iid, 0))) for iid, qty in inputs.items()}
        tasks = []
        for container in self.storage_access.own_storages(npc, town):
            take = {iid: min(qty, max(0, int(container.items.get(iid, 0))))
                    for iid, qty in needed.items() if qty > 0}
            take = {iid: qty for iid, qty in take.items() if qty > 0}
            if not take:
                continue
            steps = self.storage_access.transfer_tasks(npc, container, 'profession_withdraw', take)
            if not steps:
                continue
            tasks.extend(steps)
            for iid, qty in take.items():
                needed[iid] -= qty
        purchase = {iid: qty for iid, qty in needed.items() if qty > 0}
        if any(town.stocks.get(iid, 0) < qty for iid, qty in purchase.items()):
            return None
        cost = sum(self.economy.trade_price(town.uid, iid, True)*qty for iid, qty in purchase.items())
        if cost > npc.wealth:
            return None
        if purchase:
            tasks.extend(self._market_tasks(town, 'commerce_buy', purchase))
        return tasks

    def _reserve(self, npc, item_id):
        # Preserve household food/fuel, replanting seed and one process batch.
        reserve = 2 if item_id in FOODS or item_id == 'core:wood' else 0
        if any(c.seed_item == item_id for c in self.registry.crops.values()):
            reserve = max(reserve, 4)
        proc = self.registry.settlement_processes.get(npc.assigned_process_id)
        return max(reserve, int(proc.inputs.get(item_id, 0)) if proc else 0)

    def plan_surplus(self, npc, town, item_ids, minute, container=None):
        containers = [container] if container else self.storage_access.own_storages(npc, town)
        for source in containers:
            if source is None:
                continue
            items = {}
            budget = max(0, int(town.wealth))
            for iid in sorted(set(item_ids)):
                price = self.economy.trade_price(town.uid, iid, False)
                qty = min(max(0, int(source.items.get(iid, 0))-self._reserve(npc, iid)),
                          self.goods.carry_fit(npc, iid), budget//price)
                if qty:
                    items[iid] = qty
                    budget -= qty*price
            if not items:
                continue
            steps = self.storage_access.transfer_tasks(npc, source, 'commerce_pickup', items,
                                                        commerce_task=True)
            if not steps:
                continue
            steps += self._market_tasks(town, 'commerce_sell', items)
            # Unsold cargo returns to its real source; a cash shortage never deletes it.
            steps += self.storage_access.transfer_tasks(npc, source, 'commerce_return', items,
                                                        commerce_task=True)
            return steps
        return []

    def after_deposit(self, npc, town, container, item_ids, minute):
        if not any(t.get('commerce_task') for t in npc.tasks):
            npc.tasks.extend(self.plan_surplus(npc, town, item_ids, minute, container))

    def execute(self, npc, town, task, minute):
        if task.get('completed'):
            return False
        action = task.get('action')
        items = {str(i): max(0, int(q)) for i, q in task.get('items', {}).items()}
        if action in {'commerce_pickup', 'commerce_return'}:
            container = next((c for c in self.storage_access.own_storages(npc, town)
                              if c.uid == task.get('container_uid')), None)
            if container is None or not self.storage_access.in_reach(npc, container):
                return False
            if action == 'commerce_pickup':
                items = {iid: min(qty, max(0, container.items.get(iid, 0)-self._reserve(npc, iid)))
                         for iid, qty in items.items()}
                self.goods.withdraw(npc, container, minute, items=items, source_kind='market_surplus')
            else:
                self.goods.deposit(npc, container, minute, items=items, source_kind='unsold_cargo')
            task['completed'] = True
            return True
        pos = self.market_position(town)
        if npc.uid in self.state.interior_actors or npc.z != pos.z or abs(npc.x-pos.x)+abs(npc.y-pos.y) > 1:
            return False
        if action == 'commerce_buy':
            cost = sum(self.economy.trade_price(town.uid, iid, True)*qty for iid, qty in items.items())
            mass, volume = self.goods.inventory_load(npc)
            cap_mass, cap_volume = self.goods.carry_capacity(npc)
            for iid, qty in items.items():
                item = self.registry.items.get(iid)
                if item is None:
                    return False
                mass += item.mass_g*qty; volume += item.volume_ml*qty
            if (cost > npc.wealth or mass > cap_mass or volume > cap_volume
                    or any(town.stocks.get(iid, 0) < qty for iid, qty in items.items())):
                # The market can change during the walk. Abandon the dependent
                # work plan, retaining already collected inputs for replanning.
                npc.tasks.clear()
                npc.routine_phase = 'waiting_for_supplies'
                return False
            for iid, qty in items.items():
                town.stocks[iid] -= qty
                npc.inventory[iid] = npc.inventory.get(iid, 0)+qty
            npc.wealth -= cost; town.wealth += cost
            self.economy.record_transaction(town.uid, 'npc_input_purchase', npc.uid, town.uid,
                                            copper_value=cost, minute=minute, requested=items)
        elif action == 'commerce_sell':
            equipped = Counter(getattr(npc, 'equipment', {}).values())
            sold = {}; revenue = 0
            for iid, wanted in sorted(items.items()):
                price = self.economy.trade_price(town.uid, iid, False)
                qty = min(wanted, max(0, npc.inventory.get(iid, 0)-equipped[iid]),
                          max(0, town.wealth-revenue)//price)
                if not qty:
                    continue
                npc.inventory[iid] -= qty
                if not npc.inventory[iid]:
                    npc.inventory.pop(iid)
                town.stocks[iid] = town.stocks.get(iid, 0)+qty
                sold[iid] = qty; revenue += qty*price
            npc.wealth += revenue; town.wealth -= revenue
            if sold:
                self.economy.record_transaction(town.uid, 'npc_output_sale', npc.uid, town.uid,
                                                copper_value=revenue, minute=minute, offered=sold)
        else:
            return False
        task['completed'] = True
        return True
