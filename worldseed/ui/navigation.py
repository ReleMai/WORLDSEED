from __future__ import annotations

# Navigation definitions live outside app.py so adding a simulation system does
# not require editing input-loop control flow and visual layout in the same place.

WORLD_CONSOLE_ROOT = [
    ('alerts', '[!] Alerts & current problems'),
    ('character', '[@] Character & survival'),
    ('local', '[.] Local world & construction'),
    ('world', '[W] Map, places & wildlife'),
    ('society', '[$] Society, economy & politics'),
    ('knowledge', '[*] Knowledge, religion & magic'),
    ('records', '[#] Records, chronicle & world ledger'),
    ('system', '[~] Options & help'),
]

CONSOLE_CHARACTER = [
    ('character_sheet', 'Body, equipment & wounds'),
    ('health', 'Health, disease & immunity'),
    ('inventory', 'Inventory & physical items'),
]

CONSOLE_LOCAL = [
    ('inspect', 'Current tile / room / environment'),
    ('look', 'Interactive look cursor'),
    ('room', 'Room / shelter analysis'),
]

CONSOLE_WORLD = [
    ('journal', 'Journal'),
    ('region', 'Map & known places'),
    ('settlements', 'Settlement browser'),
    ('ecology', 'Wildlife'),
]

CONSOLE_SOCIETY = [
    ('economy', 'Economy, labor & trade'),
    ('people', 'People, families & institutions'),
    ('factions', 'Factions, culture & politics'),
]

CONSOLE_KNOWLEDGE = [
    ('knowledge', 'Knowledge, books & languages'),
    ('magic', 'Magic, rituals & contamination'),
]

CONSOLE_RECORDS = [
    ('history', 'World chronicle & legends'),
    ('ledger', 'World ledger / individual records'),
]

CONSOLE_SYSTEM = [
    ('settings', 'Game & interface options'),
    ('help', 'Controls'),
]

ACTION_ROOT = [
    ('interact', '[E] Interact with this location'),
    ('survival', '[+] Survival & body'),
    ('work', '[#] Craft, build & farm'),
    ('combat', '[X] Combat'),
    ('world', '[W] Travel, trade & knowledge'),
    ('wait', '[.] Wait 10 minutes'),
]

ACTION_INTERACT = [
    ('g', 'Harvest / mine here or an adjacent resource'),
    ('talk', 'Talk to someone nearby'),
    ('p', 'Pick up items'),
    ('l', 'Look / examine'),
    ('i', 'Inventory / nearby storage'),
]

ACTION_SURVIVAL = [
    ('e', 'Eat / prepared meals'),
    ('drink', 'Drink water'),
    ('rest', 'Rest / sleep'),
    ('f', 'Equipment, wounds & treatment'),
]

ACTION_WORK = [
    ('c', 'Craft / component design'),
    ('cook', 'Cook a meal'),
    ('process', 'Process a carcass'),
    ('preserve', 'Dry, tan & preserve'),
    ('b', 'Build'),
    ('u', 'Dismantle / unbuild'),
    ('shaft', 'Excavate vertical shaft (pick + 2 wood)'),
    ('farm', 'Farming & crop care'),
]

ACTION_COMBAT = [
    ('x', 'Attack adjacent target'),
    ('hunt', 'Aim a ranged weapon'),
]

ACTION_WORLD = [
    ('o', 'Trade at nearby market'),
    ('z', 'Read a carried book'),
    ('k', 'Magic / ritual'),
    ('down', 'Descend'),
    ('up', 'Ascend'),
]
