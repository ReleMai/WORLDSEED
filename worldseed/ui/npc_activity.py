"""Observational labels for the task an actor is executing right now."""
from __future__ import annotations

from worldseed.systems.npc_schedule import schedule_at, schedule_rows


def schedule_label(npc, seed: bytes, minute: int) -> str:
    """Read the current personal block without updating the actor's routine."""
    block = schedule_at(npc, seed, minute)
    start = f'{block.start_minute // 60:02d}:{block.start_minute % 60:02d}'
    end = f'{block.end_minute // 60:02d}:{block.end_minute % 60:02d}'
    return f'{start}–{end} | {block.label}'


def timeline_rows(npc, seed: bytes) -> list[tuple[str, str]]:
    """Expose the same deterministic daily timeline consumed by simulation."""
    return schedule_rows(npc, seed)


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
