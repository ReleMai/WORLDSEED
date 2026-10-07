"""Observational labels for the task an actor is executing right now."""
from __future__ import annotations


def activity_label(npc) -> str:
    task = npc.tasks[0] if npc.tasks else {}
    kind = str(task.get('kind', ''))
    if kind == 'move':
        if task.get('commerce_task'):
            return 'Hauling goods — market trade'
        if task.get('storage_task'):
            return 'Hauling goods — home or work storage'
        return 'Walking — ' + str(npc.goal or 'daily routine').replace('_', ' ')
    action = str(task.get('action', ''))
    labels = {'commerce_buy': 'Buying work supplies', 'commerce_pickup': 'Collecting surplus',
              'commerce_sell': 'Selling goods', 'commerce_return': 'Storing unsold goods',
              'profession_deposit': 'Storing produced goods', 'mining_deposit': 'Storing mined materials'}
    if action in labels:
        return labels[action]
    if action:
        return action.replace('_', ' ').capitalize()
    if kind == 'activity':
        return 'Working — ' + str(npc.occupation).replace('_', ' ')
    return str(npc.routine_phase or npc.goal or 'idle').replace('_', ' ').capitalize()


def possessions_rows(npc, registry) -> list[tuple[str, str]]:
    """Equipment references carried items; it is never extra inventory."""
    rows = [('Carried cash', f'{int(npc.wealth)}c')]
    equipment = getattr(npc, 'equipment', {})
    for slot, item_id in sorted(equipment.items()):
        item = registry.items.get(item_id)
        if item is not None and npc.inventory.get(item_id, 0) > 0:
            rows.append((slot.replace('_', ' ').title(), item.name))
    for item_id, quantity in sorted(npc.inventory.items()):
        if int(quantity) <= 0:
            continue
        item = registry.items.get(item_id)
        rows.append((item.name if item else 'Unidentified item', str(int(quantity))))
    if not npc.inventory:
        rows.append(('Pack', 'Empty'))
    return rows
