from __future__ import annotations
from dataclasses import dataclass

DIRECTIONS = {
    'w': (0,-1), 'UP': (0,-1),
    's': (0,1), 'DOWN': (0,1),
    'a': (-1,0), 'LEFT': (-1,0),
    'd': (1,0), 'RIGHT': (1,0),
}

# Advanced direct shortcuts. These are conveniences, not required knowledge.
DIRECT_MENUS = frozenset({'i','?','l','m','h','v','r','c','b','u','e','x','k','o','z','f'})
assert not ({'w','a','s','d'} & DIRECT_MENUS), 'Movement keys may not be shadowed by menus'


@dataclass(frozen=True, slots=True)
class Intent:
    kind: str
    value: object = None


def classify_key(key: str) -> Intent:
    """Translate raw terminal keys into stable semantic UI intents.

    Keeping this table outside the application loop prevents feature screens
    from accidentally stealing movement keys (the historical `D` bug).
    """
    k = key.lower() if len(key) == 1 else key
    if key == ' ': return Intent('time_pause')
    if key == 'ESC': return Intent('pause')
    if k in DIRECTIONS: return Intent('move', DIRECTIONS[k])
    if k in ('\r','\n'): return Intent('actions')
    if key == '\t': return Intent('console')
    if key == '~': return Intent('settings')
    if key == 'QUIT': return Intent('quit')
    if key.startswith('UI_STANCE:'):
        stance = key.partition(':')[2]
        return Intent('stance', stance) if stance in ('normal', 'stalk', 'crouch', 'aggressive') else Intent('none')
    if key.startswith('UI_MOVE:'):
        mode=key.partition(':')[2]
        return Intent('movement_mode',mode) if mode in ('walk','run','stealth') else Intent('none')
    if k in DIRECT_MENUS: return Intent('direct_menu', k)
    if k == 'g': return Intent('gather')
    if k == 'p': return Intent('pickup')
    if k == '.': return Intent('wait', 10)
    if k == '>': return Intent('vertical', -1)
    if k == '<': return Intent('vertical', 1)
    if k == 't': return Intent('farm', 'till')
    if k == 'n': return Intent('farm', 'plant')
    if k == 'j': return Intent('farm', 'harvest')
    if k == 'y': return Intent('farm', 'care')
    return Intent('none')

# HUD buttons reuse the sole global key table; no duplicate command dispatch.
HUD_BUTTONS = (
    ('Inventory','i'), ('Crafting','c'), ('Build','b'), ('Health','f'), ('Map','m'),
    ('Actions','\r'), ('World','\t'), ('Look','l'), ('Help','?'), ('Pause','ESC'),
)
