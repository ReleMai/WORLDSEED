"""Event-owned GPU navigation; simulation commands never run from observation."""
from __future__ import annotations

from worldseed.entities.components import Inventory, Vitals
from worldseed.presentation.gl_gameplay_ui import MenuRow, OverlayModel
from worldseed.ui.gpu_gameplay_actions import action_rows, dispatch_action
from worldseed.ui.gpu_gameplay_input import GpuGameplayInput
from worldseed.ui.navigation import (
    ACTION_ROOT, ACTION_INTERACT, WORLD_CONSOLE_ROOT, CONSOLE_CHARACTER,
    CONSOLE_LOCAL, CONSOLE_SYSTEM,
)
from worldseed.ui.router import classify_key
from worldseed.ui.session import NavigationStack, RouteState


CONTROLS = (
    'WASD / arrows: move in the world. Shift: sprint.',
    'Enter: Action Hub. Tab: World Console. Esc: pause / back.',
    'Left click: select a currently visible cell. Right click: open Actions.',
    'Choose Harvest or Step in Actions to issue an existing game command.',
    'Mouse wheel: zoom in the world; page records while a panel is open.',
    'Arrow keys: select a menu row. Enter or click: choose. Esc: back one level.',
    'P: pick up. Period: wait 10 minutes. F12: screenshot.',
    'This candidate uses a temporary world. Quitting discards the session.',
)


def _menu(rows, allowed):
    return tuple(MenuRow(key, label) for key, label in rows if key in allowed)


class GpuGameplaySession:
    """One UI stack over the existing input/clock owner; no extra event pump."""

    def __init__(self, sim, registry, *, now=None, input_controller=None):
        self.sim, self.registry = sim, registry
        self.input = input_controller or GpuGameplayInput(sim, now=now)
        self.nav = None
        self.window_focused = True
        self.selected_cell = None
        self.message = ''
        self.quit_requested = False
        self.page_size = 8
        self._message_log = None

    @property
    def modal(self):
        return self.nav is not None

    def open(self, route_id, *, now=None):
        title = {'actions':'Actions', 'console':'World Console', 'pause':'Paused'}[route_id]
        self.input.set_focus(False, now=now)
        self.nav = NavigationStack(RouteState(route_id, title))

    def dismiss(self, *, now=None):
        self.nav = None
        self.input.set_focus(self.window_focused, now=now)

    def set_focus(self, focused, *, now=None):
        self.window_focused = bool(focused)
        self.input.set_focus(self.window_focused and not self.modal, now=now)

    def select_cell(self, cell, snapshot):
        if self.modal or cell not in snapshot.current_cells:
            return False
        self.selected_cell = cell
        return True

    def release(self, key):
        self.input.release(key)

    def update(self, now, *, sprint=False):
        return self.input.update(now, sprint=sprint) if not self.modal else False

    def _action_rows(self, snapshot):
        return action_rows(snapshot, self.registry, self.selected_cell)

    def rows(self, snapshot):
        if not self.nav:
            return ()
        route = self.nav.current.route_id
        if route == 'actions':
            return _menu(ACTION_ROOT, {'interact', 'wait'})
        if route == 'interact':
            rows = _menu(ACTION_INTERACT, {'g', 'p', 'l'})
            if any(row.kind == 'move' for row in self._action_rows(snapshot)):
                rows += (MenuRow('step', 'Step to selected cell'),)
            return rows
        if route in ('harvest', 'pickup', 'step'):
            kind = {'harvest':'gather', 'pickup':'pickup', 'step':'move'}[route]
            return tuple(MenuRow(row.uid, row.label) for row in self._action_rows(snapshot)
                         if row.kind == kind)
        if route == 'console':
            return _menu(WORLD_CONSOLE_ROOT, {'character', 'local', 'system'})
        if route == 'character':
            return _menu(CONSOLE_CHARACTER, {'character_sheet', 'health', 'inventory'})
        if route == 'local':
            return _menu(CONSOLE_LOCAL, {'inspect'})
        if route == 'system':
            return _menu(CONSOLE_SYSTEM, {'help'})
        if route == 'pause':
            return (MenuRow('resume', 'Resume'), MenuRow('help', 'Controls'),
                    MenuRow('quit', 'Quit temporary session'))
        if route == 'inventory':
            inventory = self.sim.entities.get(self.sim.player_id, Inventory)
            items = [(iid,count) for iid,count in sorted(inventory.items.items()) if count > 0]
            page = min(self.nav.current.payload.get('page', 0), max(0,(len(items)-1)//20))
            start = page*20
            rows = tuple(MenuRow('item:'+iid,
                f'{self.registry.items[iid].name if iid in self.registry.items else iid}  × {count}')
                for iid, count in items[start:start+20])
            if start:
                rows += (MenuRow('previous-page', 'Previous inventory page'),)
            if start+20 < len(items):
                rows += (MenuRow('next-page', 'Next inventory page'),)
            return rows
        return ()

    def details(self, snapshot):
        if not self.nav:
            return ()
        route = self.nav.current.route_id
        if route == 'help':
            return CONTROLS
        if route in ('health', 'character_sheet'):
            vitals = self.sim.entities.get(self.sim.player_id, Vitals)
            return (f'Health {vitals.hp}/{vitals.max_hp}; stamina {vitals.stamina}',
                    f'Hunger {vitals.hunger}; thirst {vitals.thirst}',
                    f'Blood {vitals.blood}; pain {vitals.pain}; temperature {vitals.body_temp}')
        if route == 'inspect':
            cell = self.selected_cell or snapshot.viewer.cell
            terrain = dict(snapshot.terrain).get(cell)
            if cell not in snapshot.current_cells or terrain is None:
                return ('No currently visible prepared cell selected.',)
            feature = dict(snapshot.resources).get(cell)
            definition = self.registry.terrains.get(terrain)
            rows = [f'Cell {cell}: {definition.name if definition else terrain}']
            if feature is not None:
                resource = self.registry.resources.get(feature.feature_id)
                rows.append(f'{resource.name if resource else feature.feature_id}: {feature.stage}')
            rows.extend((f'Game minute {snapshot.minute}; {snapshot.season}',
                         'Weather: '+str(dict(snapshot.weather).get('kind', 'sheltered'))))
            return tuple(rows)
        if route == 'item':
            iid = self.nav.current.payload['item']
            item = self.registry.items.get(iid)
            return (item.name if item else iid,
                    str(getattr(item, 'description', '') or 'Carried in your inventory.'))
        if route in ('harvest', 'pickup', 'step') and not self.rows(snapshot):
            return ('No currently visible target is within reach.',)
        if route == 'inventory' and not self.rows(snapshot):
            return ('Your inventory is empty.',)
        return ()

    def _push(self, route_id, title, **payload):
        self.nav.push(RouteState(route_id, title, payload=payload))

    def activate(self, key, snapshot, *, now=None):
        if not self.window_focused or not self.nav or key not in {row.key for row in self.rows(snapshot)}:
            return False
        route = self.nav.current.route_id
        if route == 'pause' and key in ('resume', 'quit'):
            self.quit_requested = key == 'quit'
            self.dismiss(now=now)
        elif route == 'actions' and key == 'wait':
            row = next((row for row in action_rows(snapshot, self.registry) if row.kind == 'wait'), None)
            if row is not None:
                self._dispatch(row, snapshot, now=now)
        elif route in ('harvest', 'pickup', 'step'):
            row = next((row for row in self._action_rows(snapshot) if row.uid == key), None)
            if row is not None:
                self._dispatch(row, snapshot, now=now)
        elif route == 'inventory':
            if key in ('previous-page', 'next-page'):
                current = self.nav.current
                current.payload['page'] = max(0,current.payload.get('page',0)
                                             + (1 if key == 'next-page' else -1))
                current.selected = current.scroll = 0
            else:
                self._push('item', 'Item', item=key.removeprefix('item:'))
        else:
            mapped = {'g':('harvest','Harvest'), 'p':('pickup','Pick up'),
                      'l':('inspect','Look'), 'step':('step','Step')}
            child, title = mapped.get(key, (key, next(row.label for row in self.rows(snapshot)
                                                    if row.key == key)))
            self._push(child, title)
        return True

    def _dispatch(self, row, snapshot, *, now=None):
        result = dispatch_action(self.sim, row, snapshot)
        self.message = result.message
        self._message_log = self.sim.log[-1] if self.sim.log else None
        if result.dispatched:
            self.dismiss(now=now)

    def press(self, key, snapshot, *, repeat=False, now=None):
        intent = classify_key(key)
        if not self.window_focused or repeat:
            return intent.kind
        if not self.nav:
            if intent.kind in ('actions', 'console', 'pause'):
                self.open({'actions':'actions','console':'console','pause':'pause'}[intent.kind], now=now)
            elif intent.kind == 'gather':
                self.open('actions', now=now)
                self._push('interact', 'Interact')
                self._push('harvest', 'Harvest')
            elif intent.kind == 'direct_menu' and intent.value in ('i', 'f', '?'):
                self.open('console', now=now)
                if intent.value == '?':
                    self._push('system', 'System')
                    self._push('help', 'Controls')
                else:
                    self._push('character', 'Character')
                    self._push('inventory' if intent.value == 'i' else 'health',
                               'Inventory' if intent.value == 'i' else 'Health')
            else:
                return self.input.press(key, repeat=repeat, now=now)
            return intent.kind
        if intent.kind == 'pause':
            if not self.nav.back():
                self.dismiss(now=now)
            return 'back'
        if snapshot is None:
            return 'ui'  # wait for the first authorized frame before choosing
        rows = self.rows(snapshot)
        route = self.nav.current
        if key in ('UP', 'DOWN', 'PAGEUP', 'PAGEDOWN'):
            step = (-1 if key in ('UP','PAGEUP') else 1)
            if key in ('PAGEUP','PAGEDOWN'):
                step *= self.page_size
            if rows:
                route.selected = max(0, min(len(rows)-1, route.selected+step))
            else:
                route.scroll = max(0, route.scroll+step)
        elif intent.kind == 'actions' and rows:
            route.selected = min(route.selected, len(rows)-1)
            self.activate(rows[route.selected].key, snapshot, now=now)
        # W/A/S/D are never menu selection keys.
        return 'ui'

    def observe(self, snapshot):
        """Only player-owned fields and already-admitted snapshot values."""
        if self.selected_cell not in snapshot.current_cells:
            self.selected_cell = None
        vitals = self.sim.entities.get(self.sim.player_id, Vitals)
        pos = self.sim.player_pos
        target = f'Selected {self.selected_cell}' if self.selected_cell else 'Select a visible cell'
        hud = (f'HP {vitals.hp}/{vitals.max_hp}   Stamina {vitals.stamina}   '
               f'Hunger {vitals.hunger}   Thirst {vitals.thirst}',
               f'Minute {snapshot.minute}   {snapshot.season}   Position {pos.x}, {pos.y}, {pos.z}')
        latest = self.sim.log[-1] if self.sim.log else None
        if latest is not self._message_log:
            self.message = ''
        message = self.message or (latest.message if latest is not None else '')
        rows = self.rows(snapshot)
        details = self.details(snapshot)
        if self.nav:
            route = self.nav.current
            route.selected = min(route.selected, max(0, len(rows)-1))
            if rows:
                route.scroll = max(0, min(route.scroll, route.selected))
                if route.selected >= route.scroll+self.page_size:
                    route.scroll = route.selected-self.page_size+1
            return OverlayModel(hud=hud, message=message, target=target,
                panel_title=route.title, rows=rows, selected=route.selected,
                scroll=route.scroll, details=details, breadcrumb=self.nav.breadcrumbs(),
                detail_scroll=route.scroll if not rows else 0)
        return OverlayModel(hud=hud, message=message, target=target)

    def close(self):
        self.input.close()
