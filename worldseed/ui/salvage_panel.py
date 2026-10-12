"""One retained salvage surface: carried finds, components and active disassembly.

This module owns presentation/navigation only. Every material transfer and every
minigame step still goes through the existing simulation commands.
"""
from __future__ import annotations

from copy import deepcopy

from worldseed.entities.components import Inventory
from worldseed.sim.commands import (SalvageActionCommand, StartSalvageCommand,
    StartSalvageGameCommand, QuickSalvageCommand, SalvagePerkCommand,
    ResetSalvagePerksCommand, ResearchSalvageDossierCommand)
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
            'perk_view': sim.salvaging.perk_view(),
            'dossiers': {sid: len(rows) for sid, rows in sim.state.player_salvage_dossiers.items()},
            'nearby_stations': sorted(getattr(sim, '_player_station_ids', lambda: set())()),
            'active_session': session, 'result': deepcopy(result or {}),
            'skill_level': level, 'skill_xp': int(getattr(sim.state, 'player_salvaging_xp', 0)),
            'skill_threshold': sim.salvaging.skill_threshold(level),
            'output_names': {iid: ctx.registry.items[iid].name for iid in (result or {}).get('outputs', {}) if iid in ctx.registry.items}}


def run_salvage_panel(ctx, term):
    """Select, begin, play and repeat without separate preview/result menus."""
    from worldseed.app import UI_BACK, _live_panel_world_move, _stack_menu

    nav = NavigationStack(RouteState('salvaging-panel', 'SALVAGING', payload={'query': ''}))
    status = ''
    perks_open = False
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
        data['perks_open'] = perks_open
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
        if choice == 'UI_ACTION:salvage:perks':
            perks_open = not perks_open
            continue
        if choice.startswith('UI_ACTION:salvage:perk:'):
            perk_id = choice.rsplit(':', 1)[-1]
            ctx.sim.execute(SalvagePerkCommand(ctx.player_id, perk_id))
            status = ctx.sim.log[-1].message if ctx.sim.log else ''
            continue
        if choice == 'UI_ACTION:salvage:reset':
            ctx.sim.execute(ResetSalvagePerksCommand(ctx.player_id))
            status = ctx.sim.log[-1].message if ctx.sim.log else ''
            continue
        if choice.startswith('UI_ACTION:salvage:research:'):
            station = choice.split(':', 3)[-1]
            ctx.sim.execute(ResearchSalvageDossierCommand(ctx.player_id, station))
            status = ctx.sim.log[-1].message if ctx.sim.log else ''
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
        if choice == 'UI_ACTION:salvage:batch':
            count = min(inv.count(selected_item), 6 if 'wreckbreaker' in ctx.sim.state.player_salvage_perks else 4)
            ctx.sim.execute(QuickSalvageCommand(ctx.player_id,selected_item,count))
            status = ctx.sim.log[-1].message if ctx.sim.log else ''
            result = deepcopy(ctx.sim.state.player_salvage_log[-1]) if ctx.sim.state.player_salvage_log else {}
            continue
        if choice == 'UI_ACTION:salvage:quick':
            ok,reason=ctx.sim.salvaging.can_start(selected_item,inv)
            if not ok:status=reason;continue
            ctx.sim.execute(QuickSalvageCommand(ctx.player_id,selected_item))
            status=ctx.sim.log[-1].message if ctx.sim.log else ''
            result=ctx.sim.state.player_salvage_log[-1] if ctx.sim.state.player_salvage_log else {}
            continue
        if choice == 'UI_ACTION:salvage:begin':
            ok, reason = ctx.sim.salvaging.can_start(selected_item, inv)
            if not ok:
                status = reason
                continue
            ctx.sim.execute(StartSalvageGameCommand(ctx.player_id, selected_item))
            if ctx.sim.salvaging.session_view():
                result = {}
            status = ctx.sim.log[-1].message if ctx.sim.log else ''
            continue
        if choice.startswith('UI_ACTION:salvage:act:'):
            action = choice.split('UI_ACTION:salvage:act:', 1)[1]
            session = ctx.sim.salvaging.session_view()
            actions={row['id'] for row in session['choices']} if session else set()
            if session and session.get('version') == 2:
                actions.update('select:'+str(n['id']) for n in session.get('nodes',()))
                actions.update(('survey','stabilize','undo'))
                if session.get('can_prioritize'):
                    actions.update('prioritize:'+iid for iid in session.get('possible_outputs',()))
            if session and session['phase']=='disassembly':actions.update(('tune_left','tune_right'))
            if not session or action not in actions:
                continue
            ctx.sim.execute(SalvageActionCommand(ctx.player_id, action))
            status = ctx.sim.log[-1].message if ctx.sim.log else ''
            if not ctx.sim.salvaging.session_view() and ctx.sim.state.player_salvage_log:
                result = deepcopy(ctx.sim.state.player_salvage_log[-1])


class SalvagePanelMixin:
    """Item grid plus an independently scrollable material preview and game."""

    def _salvage_browser_geometry(self, *, active=False, tabletop=False):
        state = self._floating_panel_state('salvaging')
        x, y, w, h = (state[key] for key in ('x', 'y', 'w', 'h'))
        body = self.pg.Rect(x + 16, y + 122, w - 32, max(1, h - 170))
        grid_w = max(1, int(body.width * (.36 if tabletop else .48)))
        grid = self.pg.Rect(body.x, body.y, grid_w, body.height)
        right = self.pg.Rect(grid.right + 12, body.y, body.width - grid_w - 12, body.height)
        columns = max(1, (grid.width - 40) // 112)
        capacity = columns * max(1, (grid.height - 54) // 124)
        game_h = right.height if tabletop else min(270, max(250, right.height - 160)) if active else 160
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
        x, y, w, h, cx, cy, cw = self._floating_feature_shell('salvaging', 'SALVAGING', 'Recovery workshop', show_heading=False)
        self._panel_reset_input_regions()
        self._button((cx, cy, 120, 30), '‹ WORKBENCH', 'UI_ACTION:tab:recipes')
        self._button((cx + 126, cy, 120, 30),
                     'BACK TO WORK' if data.get('perks_open') else 'SKILL PERKS', 'UI_ACTION:salvage:perks')
        self._button((cx + cw - 104, cy, 104, 30), 'SEARCH', 'UI_ACTION:search')
        if data.get('perks_open'):
            self._draw_salvage_perk_tree(pg.Rect(x + 16, y + 122, w - 32, max(1,h - 170)), data)
            self._draw_floating_footer(x,y,w,h,subtitle or 'Spend earned skill points · Unlock paths in tier order')
            pg.display.flip()
            self.clock.tick(120)
            return
        label = f"Salvaging Lv {data.get('skill_level', 0)} · XP {data.get('skill_xp', 0)}/{data.get('skill_threshold', 24)}"
        if data.get('query'):
            label += ' · Search: ' + data['query']
        self._panel_text(label, (cx, y + 91, cw, 22), color=th['accent'], max_lines=1)
        tabletop = data.get('active_session',{}).get('version') == 2 if data.get('active_session') else False
        geo = self._salvage_browser_geometry(active=bool(data.get('active_session')), tabletop=tabletop)
        grid, detail, game = geo['grid'], geo['detail'], geo['game']
        for rect in ((grid, game) if tabletop else (grid, detail, game)):
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
        if not tabletop:
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
                half=(game.width-30)//2
                self._button((button.x,button.y,half,button.height),'CAREFUL [B]','UI_ACTION:salvage:begin')
                self._button((button.x+half+6,button.y,half,button.height),'QUICK · LESS XP','UI_ACTION:salvage:quick')
                perks = data.get('perk_view', {})
                paths = perks.get('paths', [])
                owns_batch = any(node.get('owned') for path in paths for node in path.get('perks', ()) if node.get('id')=='sweep_job')
                if owns_batch and preview.get('count',0) >= 2:
                    self._button((game.x + 12, game.y + 79, game.width - 24, 30),
                                 'BATCH QUICK · SAME ITEM', 'UI_ACTION:salvage:batch')
            else:
                self._panel_text(preview.get('reason') or 'No carried salvageable item selected.', button.inflate(-8, -2), color=th['muted'], max_lines=2)
        self._draw_floating_footer(x, y, w, h, subtitle or 'Click selects · B begins · 1–3 choose · WASD moves · Esc keeps work')
        self._draw_crafting_tab_tooltip()
        pg.display.flip()
        self.clock.tick(120)

    def _draw_salvage_perk_tree(self, rect, data):
        pg, th = self.pg, self._theme
        self._panel_surface(rect)
        perks = data.get('perk_view', {})
        points = perks.get('points', 0)
        self._panel_text(f"SALVAGING MASTERY  ·  Level {perks.get('level',0)}/10  ·  {points} unspent point(s)",
                         (rect.x + 10, rect.y + 8, rect.width - 165, 26), color=th['accent'])
        self._button((rect.right - 152, rect.y + 6, 142, 29),
                     f"RESPEC ×{perks.get('respecs',0)}", 'UI_ACTION:salvage:reset')
        gap = 9
        col_w = max(1, (rect.width - 28 - gap * 2) // 3)
        hovered_description = ''
        for col, path in enumerate(perks.get('paths', ())):
            px = rect.x + 10 + col*(col_w + gap)
            panel = pg.Rect(px, rect.y + 46, col_w, max(1, rect.height - 58))
            pg.draw.rect(self.screen, th['panel2'], panel, border_radius=5)
            pg.draw.rect(self.screen, th['edge'], panel, 1, border_radius=5)
            self._panel_text(path['label'].upper(), (px+8, panel.y+6, col_w-16, 23), color=th['accent'])
            node_h = min(53, max(34, (panel.height - 40)//5))
            for index, node in enumerate(path['perks']):
                top = panel.y + 32 + index*node_h
                cell = pg.Rect(px+7, top, col_w-14, max(24,node_h-4))
                color = th['good'] if node['owned'] else th['accent'] if node['available'] else th['muted']
                pg.draw.rect(self.screen, (34,50,41) if node['owned'] else (51,49,35) if node['available'] else th['panel'], cell, border_radius=4)
                pg.draw.rect(self.screen, color if node['owned'] else th['edge'], cell, 1, border_radius=4)
                self._panel_text(('✓ ' if node['owned'] else '+ ' if node['available'] else '· ') + node['name'],
                                 (cell.x+7,cell.y+4,cell.width-14,19), color=color, max_lines=1)
                if cell.height > 38:
                    self._panel_text(f"Tier {node['tier']}  ·  Level {node['level']}",
                                     (cell.x+7,cell.y+22,cell.width-14,16), color=th['muted'], max_lines=1)
                if cell.collidepoint(self._last_mouse):
                    hovered_description = node['description']
                if node['available']:
                    self._ui_target(cell,'UI_ACTION:salvage:perk:'+node['id'])
        if hovered_description:
            self._panel_text(hovered_description, (rect.x+10,rect.bottom-65,rect.width-20,31),
                             color=th['muted'],max_lines=2)
        finished = [sid for sid, count in data.get('dossiers', {}).items()
                    if count >= 3 and sid in data.get('nearby_stations', ())]
        if finished:
            self._button((rect.x+10, rect.bottom-36, min(280,rect.width-20), 28),
                         'RESEARCH COMPLETED DOSSIER', 'UI_ACTION:salvage:research:'+finished[0])

    def _draw_salvage_tabletop(self, rect, session):
        """Separate material-specific puzzle boards; all hit regions are commands."""
        pg, th = self.pg, self._theme
        x, y, w, h = rect.x, rect.y, rect.width, rect.height
        game = session['game']
        self._panel_text(session.get('game_title','SALVAGE PUZZLE'),
                         (x+12,y+8,w-24,24),color=th['accent'],max_lines=1)
        done, total = session['step'], session['stage_count']
        progress = pg.Rect(x+12,y+35,w-24,7)
        pg.draw.rect(self.screen, th['edge'], progress, border_radius=3)
        if done:
            pg.draw.rect(self.screen, th['good'], (progress.x,progress.y,max(1,progress.width*done//total),7),border_radius=3)
        self._panel_text(f"Quality {session.get('score',0)} / 100  ·  Strain {session.get('stress',0)}  ·  {done}/{total} parts",
                         (x+12,y+46,w-24,20),color=th['muted'],max_lines=1)
        self._panel_text(session.get('cue',''),(x+12,y+68,w-24,36),color=th['text'],max_lines=2)
        if session.get('phase') == 'inspection':
            self._panel_text(session.get('game_description',''),(x+15,y+121,w-30,max(42,h-205)),
                             color=th['muted'],max_lines=4)
            self._button((x+15,rect.bottom-49,w-30,35),'EXAMINE AND START','UI_ACTION:salvage:act:inspect')
            return
        nodes = session.get('nodes',())
        ncols = 2 if w < 600 else 3
        gap = 7
        node_w = max(64,(w - 26-(ncols-1)*gap)//ncols)
        node_h = 40 if h < 385 else 47
        node_y = y+111
        for index,node in enumerate(nodes):
            px=x+12+(index%ncols)*(node_w+gap)
            py=node_y+(index//ncols)*(node_h+gap)
            cell=pg.Rect(px,py,node_w,node_h)
            selected=node['selected'];blocked=node['locked'];complete=node['done']
            border=th['accent'] if selected else th['good'] if complete else th['edge']
            bg=(54,48,35) if selected else (31,52,42) if complete else (39,45,46) if not blocked else th['panel']
            pg.draw.rect(self.screen,bg,cell,border_radius=4)
            pg.draw.rect(self.screen,border,cell,2 if selected else 1,border_radius=4)
            # A distinctive material glyph anchors each tabletop's graphic grammar.
            mark=pg.Rect(cell.x+6,cell.y+8,20,20)
            if game=='fracture':
                pg.draw.polygon(self.screen,th['accent'] if node['valuable'] else th['muted'],
                                [(mark.centerx,mark.y),(mark.right,mark.centery),(mark.centerx+2,mark.bottom),(mark.x,mark.centery)])
                pg.draw.line(self.screen,th['panel'],mark.midtop,mark.center,2)
            elif game=='recovery':
                pg.draw.rect(self.screen,th['accent'],mark,1)
                for delta in (4,9,14):
                    pg.draw.line(self.screen,th['muted'],(mark.x+delta,mark.y+3),(mark.x+delta,mark.bottom-3),1)
            else:
                pg.draw.circle(self.screen,th['muted'],mark.center,9,2)
                pg.draw.line(self.screen,th['accent'],(mark.x+6,mark.y+6),(mark.right-6,mark.bottom-6),2)
            label=('✓ ' if complete else '○ ' if blocked else '')+node['label']
            self._panel_text(label,(cell.x+30,cell.y+4,cell.width-35,node_h-7),color=th['muted'] if blocked else th['text'],max_lines=2)
            self._ui_target(cell,'UI_ACTION:salvage:act:select:'+str(node['id']))
        rows=(len(nodes)+ncols-1)//ncols
        action_y=node_y+rows*(node_h+gap)+5
        actions=list(session.get('choices',()))
        if session.get('can_survey'):
            actions.append({'id':'survey','label':'Inspect seam'})
        if session.get('can_stabilize'):
            actions.append({'id':'stabilize','label':'Stabilize'})
        if session.get('can_undo'):
            actions.append({'id':'undo','label':'Correct mistake'})
        if session.get('can_prioritize') and session.get('possible_outputs'):
            priority = session.get('priority','')
            choices=list(session['possible_outputs'])
            candidate=choices[(choices.index(priority)+1)%len(choices)] if priority in choices else choices[0]
            actions.append({'id':'prioritize:'+candidate,'label':'Favor '+candidate.split(':')[-1].replace('_',' ')})
        room=max(28,rect.bottom-action_y-12)
        columns=2
        button_h=max(23,min(31,(room-8)//max(1,(len(actions)+1)//2)-3))
        for index,action in enumerate(actions):
            bw=max(55,(w-31)//2)
            bx=x+12+(index%2)*(bw+7)
            by=action_y+(index//2)*(button_h+4)
            if by+button_h>rect.bottom-6:break
            self._button((bx,by,bw,button_h),action['label'],
                         'UI_ACTION:salvage:act:'+action['id'])

    def _draw_salvage_game(self, rect, session):
        if session.get('version') == 2:
            self._draw_salvage_tabletop(rect,session)
            return
        th, pg = self._theme, self.pg
        phase = session.get('phase')
        stage = 'INSPECTION' if phase == 'inspection' else f"STAGE {int(session.get('step', 0)) + 1}/{session.get('stage_count', 3)}"
        self._panel_text(stage + f" · Care {session.get('score', 0)}/{session.get('max_score', 6)}",
                         (rect.x + 12, rect.y + 10, rect.width - 24, 22), color=th['accent'], max_lines=1)
        self._panel_text(session.get('name', ''), (rect.x + 12, rect.y + 32, rect.width - 24, 20), max_lines=1)
        choices = session.get('choices', ())
        button_h, gap = (31, 4)
        actions_top = rect.bottom - 10 - len(choices) * (button_h + gap)
        self._panel_text(session.get('cue') or session.get('prompt', ''),
                         (rect.x + 12, rect.y + 52, rect.width - 24, 36), color=th['muted'],max_lines=2)
        if phase!='inspection':
            target=int(session.get('target',0));dial=int(session.get('dial',0))
            meter_y=rect.y+90;meter_w=max(80,rect.width-155)
            for position in range(5):
                slot=pg.Rect(rect.x+15+position*(meter_w//5),meter_y,max(10,meter_w//5-4),22)
                fg=th['good'] if position==target and position==dial else th['accent'] if position==target else (77,90,85) if position==dial else th['panel2']
                pg.draw.rect(self.screen,fg,slot,border_radius=3)
            self._button((rect.right-110,meter_y,43,25),'◀','UI_ACTION:salvage:act:tune_left')
            self._button((rect.right-62,meter_y,43,25),'▶','UI_ACTION:salvage:act:tune_right')
            self._panel_text(f"Align dark marker with gold target · Precision {session.get('precision',0)}/3",
                             (rect.x+12,meter_y+23,rect.width-24,17),color=th['muted'],max_lines=1)
        for index, choice in enumerate(choices):
            button = pg.Rect(rect.x + 12, actions_top + index * (button_h + gap), rect.width - 24, button_h)
            self._button(button, f"[{index + 1}] " + choice.get('label', ''), 'UI_ACTION:salvage:act:' + choice['id'])

