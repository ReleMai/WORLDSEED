"""One retained salvage surface: carried finds, components and active disassembly.

This module owns presentation/navigation only. Every material transfer and every
minigame step still goes through the existing simulation commands.
"""
from __future__ import annotations

from copy import deepcopy

from worldseed.entities.components import Inventory
from worldseed.sim.commands import SalvageActionCommand, StartSalvageCommand
from worldseed.ui.session import NavigationStack, RouteState
from worldseed.ui.widgets import prompt_text


def salvage_panel_data(ctx, inv, *, query='', result=None):
    """Build a read model from carried sources and the authoritative project."""
    from worldseed.app import _salvage_preview_ui_data

    sim = ctx.sim
    session = sim.salvaging.session_view()
    available = sim.salvaging.available_items(inv)
    items = {row['item_id']: dict(row) for row in available
             if not query or query.casefold() in row['name'].casefold()}
    # The reserved source remains visible even when beginning consumed its last
    # carried copy. Opening/closing this panel cannot reserve another copy.
    if session and session['item_id'] not in items:
        iid = session['item_id']
        items[iid] = {'item_id': iid, 'name': session['name'], 'count': inv.count(iid),
                      'can_start': False, 'reason': 'Current project; finish its disassembly below.'}
    previews = {iid: _salvage_preview_ui_data(ctx.registry, sim, inv, iid) for iid in items}
    level = sim.player_skill('salvaging')
    return {'items': items, 'previews': previews, 'query': query,
            'active_session': session, 'result': deepcopy(result or {}),
            'skill_level': level, 'skill_xp': int(getattr(sim.state, 'player_salvaging_xp', 0)),
            'skill_threshold': sim.salvaging.skill_threshold(level),
            'output_names': {iid: ctx.registry.items[iid].name for iid in (result or {}).get('outputs', {}) if iid in ctx.registry.items}}


def run_salvage_panel(ctx, term):
    """Select, begin, play and repeat without separate preview/result menus."""
    from worldseed.app import UI_BACK, _live_panel_world_move, _stack_menu

    nav = NavigationStack(RouteState('salvaging-panel', 'SALVAGING', payload={'query': ''}))
    status = ''
    result = {}
    session = ctx.sim.salvaging.session_view()
    selected_item = session['item_id'] if session else None
    while True:
        route = nav.current
        inv = ctx.entities.get(ctx.player_id, Inventory)
        data = salvage_panel_data(ctx, inv, query=route.payload['query'], result=result)
        rows = [(iid, row['name']) for iid, row in data['items'].items()]
        if not rows:
            rows = [('__empty__', 'No salvageable items in your pack')]
        ids = [key for key, _ in rows]
        if selected_item in ids:
            route.selected = ids.index(selected_item)
        route.selected = max(0, min(route.selected, len(rows) - 1))
        choice = _stack_menu(term, nav, rows, subtitle=status,
                             presentation='salvaging_unified', presentation_data=data)
        selected_item = rows[route.selected][0]
        status = ''
        if choice is None:
            return UI_BACK
        if choice == '__BACK__':
            continue
        if choice.startswith('UI_ACTION:tab:'):
            if choice != 'UI_ACTION:tab:salvaging':
                return choice
            continue
        moved = _live_panel_world_move(ctx, term, choice)
        if moved is not None:
            status = moved
            continue
        if choice == 'UI_ACTION:search':
            nav.push(RouteState('salvaging-search', 'SALVAGING // SEARCH'))
            value = prompt_text(term, nav.current.title, 'Item name (blank shows all):',
                                default=route.payload['query'], max_len=48)
            nav.pop()
            if value is not None:
                route.payload['query'] = value
                route.selected = 0
                route.scroll = 0
                selected_item = None
            continue
        if choice in data['items']:
            # Explicit selection previews the item, without opening another
            # screen or consuming it. Begin remains a labelled player action.
            selected_item = choice
            continue
        if choice == 'UI_ACTION:salvage:begin':
            ok, reason = ctx.sim.salvaging.can_start(selected_item, inv)
            if not ok:
                status = reason
                continue
            ctx.sim.execute(StartSalvageCommand(ctx.player_id, selected_item))
            if ctx.sim.salvaging.session_view():
                result = {}
            status = ctx.sim.log[-1].message if ctx.sim.log else ''
            continue
        if choice.startswith('UI_ACTION:salvage:act:'):
            action = choice.rsplit(':', 1)[-1]
            session = ctx.sim.salvaging.session_view()
            if not session or action not in {row['id'] for row in session['choices']}:
                continue
            ctx.sim.execute(SalvageActionCommand(ctx.player_id, action))
            status = ctx.sim.log[-1].message if ctx.sim.log else ''
            if not ctx.sim.salvaging.session_view() and ctx.sim.state.player_salvage_log:
                result = deepcopy(ctx.sim.state.player_salvage_log[-1])


class SalvagePanelMixin:
    """Item grid plus an independently scrollable material preview and game."""

    def _salvage_browser_geometry(self, *, active=False):
        state = self._floating_panel_state('crafting')
        x, y, w, h = (state[key] for key in ('x', 'y', 'w', 'h'))
        body = self.pg.Rect(x + 16, y + 122, w - 32, max(1, h - 170))
        grid_w = max(1, int(body.width * .48))
        grid = self.pg.Rect(body.x, body.y, grid_w, body.height)
        right = self.pg.Rect(grid.right + 12, body.y, body.width - grid_w - 12, body.height)
        columns = max(1, (grid.width - 40) // 112)
        capacity = columns * max(1, (grid.height - 54) // 124)
        game_h = min(270, max(250, right.height - 160)) if active else 160
        game = self.pg.Rect(right.x, right.bottom - game_h, right.width, game_h)
        detail = self.pg.Rect(right.x, right.y, right.width, max(1, right.height - game_h - 8))
        return {'grid': grid, 'right': right, 'detail': detail, 'game': game,
                'columns': columns, 'capacity': capacity}

    def _salvage_material_lines(self, preview, result, *, active=False):
        th = self._theme
        lines = []
        if preview:
            if not active:
                lines.extend([('item', preview['item_id'], preview.get('name', ''), th['text']),
                              ('text', f"{preview.get('count', 0)} carried · {preview.get('minutes', 0)} min · Difficulty {preview.get('difficulty', 0)}", th['muted']),
                              ('text', 'RECOVERABLE COMPONENTS', th['accent'])])
            for group in ('guaranteed', 'rare'):
                for part in preview.get(group, ()):
                    low, high = part.get('min', 1), part.get('max', 1)
                    count = str(low) if low == high else f'{low}–{high}'
                    chance = f" · Rare base {part.get('chance_percent', 0)}%" if group == 'rare' else ' · Guaranteed'
                    lines.append(('item', part['item_id'], f"{part['name']} ×{count}{chance}", th['good'] if group == 'guaranteed' else th['accent']))
                    if part.get('description'):
                        lines.append(('text', part['description'], th['muted']))
                    uses = part.get('uses', ())
                    lines.append(('text', 'Learned uses: ' + (', '.join(uses) if uses else 'Experiment with recovered parts to learn techniques.'), th['muted']))
            if preview.get('description'):
                lines.extend([('text', 'ABOUT THE SOURCE', th['accent']),
                              ('text', preview['description'], th['text'])])
            for quality, need in preview.get('tools', {}).items():
                lines.append(('text', f"Tool: {quality.replace('_', ' ').title()} {need}+", th['muted']))
        else:
            lines.append(('text', 'Carry a salvageable find to preview its reusable components here.', th['muted']))
        if result:
            recovered = [('text', 'LAST RECOVERY · ' + result.get('name', ''), th['accent'])]
            for iid, count in result.get('outputs', {}).items():
                name = getattr(self, '_salvage_output_names', {}).get(iid, iid)
                suffix = ' · Rare' if iid in result.get('rare_outputs', {}) else ''
                recovered.append(('item', iid, f'{name} ×{count}{suffix}', th['good']))
            return recovered + [('text', 'NEXT SOURCE', th['accent'])] + lines
        return lines

    def _present_salvaging_unified(self, title, rows, selected, *, subtitle='', breadcrumb='',
                                   footer='', page_start=0, total=None, data=None):
        data = data or {}
        pg, screen, th = self.pg, self.screen, self._theme
        x, y, w, h, cx, cy, cw = self._floating_feature_shell('crafting', 'WORKBENCH', 'Salvaging', show_heading=False)
        self._panel_reset_input_regions()
        self._crafting_tabs(cx, cy, cw, 'salvaging')
        self._button((cx + cw - 104, cy, 104, 30), 'SEARCH', 'UI_ACTION:search')
        label = f"Salvaging Lv {data.get('skill_level', 0)} · XP {data.get('skill_xp', 0)}/{data.get('skill_threshold', 24)}"
        if data.get('query'):
            label += ' · Search: ' + data['query']
        self._panel_text(label, (cx, y + 91, cw, 22), color=th['accent'], max_lines=1)
        geo = self._salvage_browser_geometry(active=bool(data.get('active_session')))
        grid, detail, game = geo['grid'], geo['detail'], geo['game']
        for rect in (grid, detail, game):
            self._panel_surface(rect)
        self._panel_text('CARRIED FINDS', (grid.x + 12, grid.y + 10, grid.width - 24, 22), color=th['muted'])
        items = data.get('items', {})
        chosen = data.get('selected_key')
        if chosen is None and 0 <= selected < len(rows):
            chosen = getattr(rows[selected], 'key', '')
        columns = geo['columns']
        card_w = (grid.width - 40 - 8 * (columns - 1)) // columns
        for index, row in enumerate(rows[:geo['capacity']]):
            iid = getattr(row, 'key', '')
            item = items.get(iid, {})
            rect = pg.Rect(grid.x + 10 + (index % columns) * (card_w + 8),
                           grid.y + 36 + (index // columns) * 124, card_w, 116)
            active, hovered = iid == chosen, rect.collidepoint(self._last_mouse)
            pg.draw.rect(screen, (48, 48, 36) if active else (34, 43, 44) if hovered else th['panel2'], rect, border_radius=6)
            pg.draw.rect(screen, th['accent'] if active else th['edge_hi'] if hovered else th['edge'], rect, 2 if active else 1, border_radius=6)
            if iid != '__empty__':
                self._panel_item_icon(iid, pg.Rect(rect.centerx - 29, rect.y + 5, 58, 58))
                self._panel_text('×' + str(item.get('count', 0)), (rect.right - 39, rect.y + 6, 34, 18), color=th['accent'], max_lines=1)
            self._panel_text(item.get('name', getattr(row, 'label', iid)), (rect.x + 7, rect.y + 66, rect.width - 14, 36), max_lines=2)
            self._ui_target(rect, f'UI_SELECT:{index}')
        count = len(rows) if total is None else total
        self._panel_scrollbar((grid.right - 24, grid.y + 35, 18, max(50, grid.height - 62)), page_start, geo['capacity'], count)
        self._panel_text(f'{page_start + 1}–{page_start + len(rows)} / {count}' if items else '0 carried finds',
                         (grid.x + 12, grid.bottom - 23, grid.width - 42, 20), color=th['muted'])
        preview = data.get('previews', {}).get(chosen, {})
        result = data.get('result', {})
        self._salvage_output_names = data.get('output_names', {})
        # The attached game already names the reserved object. Start its
        # smaller preview with components instead of repeating the header.
        lines = self._salvage_material_lines(preview, result, active=bool(data.get('active_session')))
        self._panel_detail('salvage:' + str(chosen), detail.inflate(-24, -20), lines)
        session = data.get('active_session')
        if session:
            self._draw_salvage_game(game, session)
        else:
            complete = bool(result)
            self._panel_text('RECOVERY COMPLETE' if complete else 'READY TO DISASSEMBLE' if preview else 'NO SALVAGEABLE FINDS',
                             (game.x + 12, game.y + 12, game.width - 24, 22), color=th['good'] if complete else th['accent'])
            summary = (f"Care {result.get('score', 0)}/{result.get('max_score', 6)} · Practice +{result.get('xp_gained', 0)}. Recovered parts are in your pack."
                       if complete else 'Select a find to preview materials. Begin dismantles one carried item; progress is kept when you close this panel.')
            self._panel_text(summary, (game.x + 12, game.y + 43, game.width - 24, max(40, game.height - 104)), color=th['muted'])
            button = pg.Rect(game.x + 12, game.bottom - 45, game.width - 24, 32)
            if preview.get('can_start'):
                self._button(button, 'SALVAGE NEXT ITEM [B]' if complete else 'BEGIN SALVAGE [B]', 'UI_ACTION:salvage:begin')
            else:
                self._panel_text(preview.get('reason') or 'No carried salvageable item selected.', button.inflate(-8, -2), color=th['muted'], max_lines=2)
        self._draw_floating_footer(x, y, w, h, subtitle or 'Click selects · B begins · 1–3 choose · WASD moves · Esc keeps work')
        self._draw_crafting_tab_tooltip()
        pg.display.flip()
        self.clock.tick(120)

    def _draw_salvage_game(self, rect, session):
        th, pg = self._theme, self.pg
        phase = session.get('phase')
        stage = 'INSPECTION' if phase == 'inspection' else f"STAGE {int(session.get('step', 0)) + 1}/{session.get('stage_count', 3)}"
        self._panel_text(stage + f" · Care {session.get('score', 0)}/{session.get('max_score', 6)}",
                         (rect.x + 12, rect.y + 10, rect.width - 24, 22), color=th['accent'], max_lines=1)
        self._panel_text(session.get('name', ''), (rect.x + 12, rect.y + 32, rect.width - 24, 20), max_lines=1)
        choices = session.get('choices', ())
        button_h, gap = (35, 5)
        actions_top = rect.bottom - 10 - len(choices) * (button_h + gap)
        self._panel_text(session.get('cue') or session.get('prompt', ''),
                         (rect.x + 12, rect.y + 55, rect.width - 24, max(20, actions_top - rect.y - 61)), color=th['muted'])
        for index, choice in enumerate(choices):
            button = pg.Rect(rect.x + 12, actions_top + index * (button_h + gap), rect.width - 24, button_h)
            self._button(button, f"[{index + 1}] " + choice.get('label', ''), 'UI_ACTION:salvage:act:' + choice['id'])

