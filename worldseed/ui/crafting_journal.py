"""Read-only projection of learned recipes and recent experiment chronology."""
from __future__ import annotations


def crafting_journal_data(registry, state):
    known = set(state.player_discovered_recipes) if state.player_crafting_discovery_enabled else set(registry.recipes)
    recent = list(reversed(getattr(state, 'player_crafting_log', ())[-80:]))
    entries = []
    seen = set()

    def append(recipe_id, record=None):
        if recipe_id in seen or recipe_id not in known or recipe_id not in registry.recipes:
            return
        seen.add(recipe_id)
        recipe = registry.recipes[recipe_id]
        entries.append({'id': recipe_id, 'name': recipe.name,
                        'minute': record.get('minute') if record else None,
                        'ingredients': list(record.get('ingredients', ())) if record else [],
                        'outputs': [{'id': iid, 'name': registry.items[iid].name, 'qty': qty}
                                    for iid, qty in recipe.outputs.items() if iid in registry.items]})

    for record in recent:
        append(record.get('recipe_id'), record)
    latest = dict(entries[0]) if entries else None
    # Older saves retain their complete known catalogue even without chronology.
    for recipe_id in sorted(known, key=lambda rid: (registry.recipes[rid].name, rid) if rid in registry.recipes else ('', rid)):
        append(recipe_id)
    return {'learned_history': entries, 'learned_count': len(entries), 'latest_result': latest}
