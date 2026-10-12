"""Read-only discovery and physical-workshop surfaces for the crafting window."""
from __future__ import annotations


class WorkbenchPanelsMixin:
    def _discovery_browser_geometry(self):
        pg = self.pg
        state = self._floating_panel_state('crafting')
        x, y, w, h = (state[key] for key in ('x', 'y', 'w', 'h'))
        body = pg.Rect(x + 16, y + 92, w - 32, max(1, h - 134))
        grid = pg.Rect(body.x, body.y, int(body.width * .55), body.height)
        right = pg.Rect(grid.right + 12, body.y, body.width - grid.width - 12, body.height)
        experiment = pg.Rect(right.x, right.y, right.width, min(198, right.height))
        journal = pg.Rect(right.x, experiment.bottom + 12, right.width, max(1, right.bottom - experiment.bottom - 12))
        columns = max(1, (grid.width - 42) // 126)
        capacity = columns * max(1, (grid.height - 54) // 112)
        return {'body': body, 'grid': grid, 'experiment': experiment,
                'journal': journal, 'columns': columns, 'capacity': capacity}

    def _workshop_browser_geometry(self):
        pg = self.pg
        state = self._floating_panel_state('crafting')
        x, y, w, h = (state[key] for key in ('x', 'y', 'w', 'h'))
        body = pg.Rect(x + 16, y + 178, w - 32, max(1, h - 220))
        detail_width = min(390, max(284, int(body.width * .43)))
        listing = pg.Rect(body.x, body.y, max(1, body.width - detail_width - 12), body.height)
        detail = pg.Rect(listing.right + 12, body.y, detail_width, body.height)
        capacity = max(1, (listing.height - 52) // 76)
        return {'body': body, 'list': listing, 'detail': detail, 'capacity': capacity}

    def _workbench_shell(self, title, active):
        geometry = self._floating_feature_shell('crafting', 'WORKBENCH', title, show_heading=False)
        self._panel_reset_input_regions()
        x, y, w, h, cx, cy, cw = geometry
        self._button((x + w - 128, y + 7, 78, 27), 'PACK', 'UI_ACTION:open_inventory')
        self._crafting_tabs(cx, cy, cw, active)
        return geometry

    def _discovery_material_cards(self, rows, selected, data, geometry, page_start, total):
        pg, th = self.pg, self._theme
        grid = geometry['grid']
        entries = data.get('items') or {}
        placed = list(data.get('selected_items') or [])
        self._panel_surface(grid)
        self._panel_text('CARRIED MATERIALS', (grid.x + 12, grid.y + 10, grid.width - 24, 20), color=th['accent'])
        if not entries:
            self._panel_text('Gather materials to begin experimenting. Carried items with a discovery path appear here.',
                             (grid.x + 14, grid.y + 48, grid.width - 42, grid.height - 84), color=th['muted'])
        columns = geometry['columns']
        card_width = (grid.width - 42 - 8 * (columns - 1)) // columns
        for index, row in enumerate(rows[:geometry['capacity']]):
            iid = getattr(row, 'key', '')
            if iid not in entries:
                continue
            item = entries[iid]
            rect = pg.Rect(grid.x + 10 + (index % columns) * (card_width + 8),
                           grid.y + 34 + (index // columns) * 112, card_width, 106)
            over = rect.collidepoint(self._last_mouse)
            selected_key = data.get('selected_key')
            chosen = iid == selected_key if selected_key is not None else index == selected
            pg.draw.rect(self.screen, (43, 49, 44) if chosen else (34, 43, 43) if over else th['panel2'], rect, border_radius=5)
            pg.draw.rect(self.screen, th['accent'] if chosen else th['edge_hi'] if over else th['edge'], rect,
                         2 if chosen else 1, border_radius=5)
            self._panel_item_icon(iid, pg.Rect(rect.centerx - 23, rect.y + 4, 46, 46))
            count = max(0, int(item.get('count', 0)))
            badge = self.small_font.render('×' + str(count), True, th['accent'])
            badge_rect = pg.Rect(rect.right - badge.get_width() - 12, rect.y + 5, badge.get_width() + 8, 18)
            pg.draw.rect(self.screen, (16, 22, 23), badge_rect, border_radius=3)
            self.screen.blit(badge, (badge_rect.x + 4, badge_rect.y))
            self._panel_text(item.get('name', iid), (rect.x + 8, rect.y + 52, rect.width - 16, 35), max_lines=2)
            known = len(item.get('known_recipes') or [])
            progress = f"{known}/{item.get('pool_count', 0)} known"
            if iid in placed:
                progress += f' · {placed.count(iid)} placed'
            self._panel_text(progress, (rect.x + 8, rect.bottom - 19, rect.width - 16, 18),
                             color=th['muted'], max_lines=1)
            self._ui_target(rect, f'UI_SELECT:{index}')
        actual_total = max(0, total if entries and total is not None else len(entries))
        self._panel_scrollbar((grid.right - 24, grid.y + 34, 18, max(50, grid.height - 62)),
                              page_start, geometry['capacity'], actual_total)
        counter = f'{page_start + 1}–{min(actual_total, page_start + len(rows))} / {actual_total}' if actual_total else '0 materials'
        self._panel_text(counter + ' · Click adds one', (grid.x + 12, grid.bottom - 23, grid.width - 38, 20),
                         color=th['muted'], max_lines=1)

    def _discovery_experiment(self, rect, data):
        pg, th = self.pg, self._theme
        self._panel_surface(rect)
        state = str(data.get('mix_state', 'red'))
        color = {'red': th['danger'], 'yellow': th['accent'], 'green': th['good']}.get(state, th['muted'])
        placed = list(data.get('selected_items') or [])[:5]
        self._panel_text('EXPERIMENT · 1–5 MATERIALS', (rect.x + 12, rect.y + 11, rect.width - 24, 23), color=th['accent'])
        gap = 5
        slot_width = max(1, (rect.width - 24 - 4 * gap) // 5)
        for index in range(5):
            slot = pg.Rect(rect.x + 12 + index * (slot_width + gap), rect.y + 42, slot_width, 65)
            filled = index < len(placed)
            pg.draw.rect(self.screen, (28, 36, 37), slot, border_radius=5)
            pg.draw.rect(self.screen, color if filled else th['edge'], slot, 2 if filled else 1, border_radius=5)
            self._panel_text(str(index + 1), (slot.x + 5, slot.y + 3, slot.width - 10, 18), color=th['muted'], max_lines=1)
            if filled:
                self._panel_item_icon(placed[index], pg.Rect(slot.x + 5, slot.y + 20, slot.width - 10, 40))
                self._ui_target(slot, f'UI_ACTION:remove_slot:{index}')
            else:
                plus = self.font.render('+', True, th['edge_hi'])
                self.screen.blit(plus, plus.get_rect(center=(slot.centerx, slot.centery + 7)))
        self._discovery_pot_center = (rect.centerx, rect.y + 75)
        label = {'red': 'Add materials to find a recipe path.',
                 'yellow': 'A possible path. Add or adjust a material.',
                 'green': 'Ready to reveal a new technique.'}.get(state, '')
        if data.get('known_exact'):
            label = 'Already learned: ' + ', '.join(data['known_exact'])
        self._panel_text(label, (rect.x + 12, rect.y + 115, rect.width - 24, 36), color=color, max_lines=2)
        self._button((rect.x + 12, rect.y + 156, 78, 30), 'CLEAR', 'UI_ACTION:clear')
        action = pg.Rect(rect.x + 96, rect.y + 156, rect.width - 108, 30)
        if state == 'green' and placed:
            self._button(action, 'MIX MATERIALS', 'UI_ACTION:mix')
        else:
            pg.draw.rect(self.screen, (27, 33, 34), action, border_radius=4)
            self._panel_text('MIX MATERIALS', action.inflate(-10, -10), color=th['muted'], max_lines=1)

    def _discovery_journal(self, rect, data, selected_key=None):
        pg, th = self.pg, self._theme
        self._panel_surface(rect)
        latest = data.get('latest_result') or {}
        self._panel_text('LATEST DISCOVERY', (rect.x + 12, rect.y + 9, rect.width - 50, 20), color=th['accent'], max_lines=1)
        if latest:
            self._button((rect.right - 32, rect.y + 6, 22, 22), '×', 'UI_ACTION:dismiss_result')
            outputs = latest.get('outputs') or []
            text_x = rect.x + 12
            if outputs:
                self._panel_item_icon(str(outputs[0].get('id', '')), pg.Rect(rect.x + 10, rect.y + 32, 42, 42))
                text_x += 48
            self._panel_text(latest.get('name', 'New technique learned'),
                             (text_x, rect.y + 33, rect.right - text_x - 12, 40), color=th['good'], max_lines=2)
        else:
            self._panel_text('Your next discovery will remain here until dismissed.',
                             (rect.x + 12, rect.y + 33, rect.width - 24, 40), color=th['muted'], max_lines=2)
        history = list(data.get('learned_history') or [])
        learned_count = max(0, int(data.get('learned_count', len(history))))
        self._panel_text(f'NOTES · {learned_count} LEARNED',
                         (rect.x + 12, rect.y + 85, rect.width - 24, 20), color=th['muted'], max_lines=1)
        lines = []
        material = (data.get('items') or {}).get(selected_key, {})
        if material:
            lines.append(('text', 'SELECTED MATERIAL', th['accent']))
            lines.append(('text', str(material.get('name', selected_key)), th['text']))
            tags = [str(tag).replace('_', ' ').title() for tag in material.get('tags', [])]
            if tags:
                lines.append(('text', 'Tags: ' + ' · '.join(tags), th['muted']))
            uses = list(material.get('known_recipes') or [])
            lines.append(('text', 'LEARNED USES', th['muted']))
            lines.extend(('text', str(name), th['text']) for name in uses)
            if not uses:
                lines.append(('text', 'No learned techniques use this material yet.', th['muted']))
        lines.append(('text', 'LEARNED HISTORY', th['accent']))
        for recipe in history:
            lines.append(('text', str(recipe.get('name', 'Learned technique')), th['text']))
            for output in recipe.get('outputs') or []:
                lines.append(('item', str(output.get('id', '')),
                              f"{output.get('name', output.get('id', ''))} ×{output.get('qty', 1)}", th['muted']))
        if not history:
            lines.append(('text', 'Recipes you reveal will be recorded here.', th['muted']))
        self._panel_detail('discovery:learned-history', pg.Rect(rect.x + 12, rect.y + 111, rect.width - 24,
                                                              max(1, rect.height - 123)), lines)

    def _present_discovery_pot(self, title, rows, selected, *, subtitle='', breadcrumb='', footer='',
                               page_start=0, total=None, data=None):
        data = data or {}
        x, y, w, h, _, _, _ = self._workbench_shell('Discovery', 'discovery')
        geometry = self._discovery_browser_geometry()
        self._discovery_material_cards(rows, selected, data, geometry, page_start, total)
        self._discovery_experiment(geometry['experiment'], data)
        selected_key = data.get('selected_key')
        if selected_key is None and 0 <= selected < len(rows):
            selected_key = getattr(rows[selected], 'key', '')
        self._discovery_journal(geometry['journal'], data, selected_key)
        self._draw_floating_footer(x, y, w, h, subtitle or 'Click material to add · Click filled slot to remove · Scroll learned history · Esc closes')
        self._draw_crafting_tab_tooltip()
        self.pg.display.flip()
        self.clock.tick(120)

    def _workshop_station_tabs(self, x, y, width, data, accent):
        pg, th = self.pg, self._theme
        stations = list(data.get('stations') or [])
        active = str(data.get('station_id') or '')
        pages = max(1, (len(stations) + 3) // 4)
        page = max(0, min(int(data.get('station_page', 0)), pages - 1))
        available = width - (76 if pages > 1 else 0)
        tab_width = max(1, (available - 18) // 4)
        for index, station in enumerate(stations[page * 4:(page + 1) * 4]):
            sid = str(station.get('station_id', ''))
            label = str(station.get('short_title') or station.get('title') or sid)
            rect = pg.Rect(x + index * (tab_width + 6), y, tab_width, 30)
            chosen = active == sid
            pg.draw.rect(self.screen, (43, 46, 40) if chosen else th['panel2'], rect, border_radius=4)
            pg.draw.rect(self.screen, accent if chosen else th['edge'], rect, 1, border_radius=4)
            rendered = self.small_font.render(self._fit_ui_text(label, self.small_font, rect.width - 14), True,
                                              accent if chosen else th['text'])
            self.screen.blit(rendered, rendered.get_rect(center=rect.center))
            self._ui_target(rect, 'UI_ACTION:workshop:' + sid)
            if rect.collidepoint(self._last_mouse) and self.small_font.size(label)[0] > rect.width - 14:
                self._crafting_tab_tooltip = (label, pg.Rect(rect.x, rect.bottom + 5,
                                                            self.small_font.size(label)[0] + 20, 25))
        if pages > 1:
            self._button((x + width - 72, y, 32, 30), '‹', 'UI_ACTION:workshop_page:prev')
            self._button((x + width - 34, y, 32, 30), '›', 'UI_ACTION:workshop_page:next')
        if not stations:
            self._panel_text('No usable workshop within reach', (x, y + 5, width, 24), color=th['muted'], max_lines=1)

    def _present_workshop_station(self, title, rows, selected, *, subtitle='', breadcrumb='', footer='',
                                  page_start=0, total=None, data=None):
        data = data or {}
        pg, th = self.pg, self._theme
        recipes = data.get('recipes') or {}
        profile = data.get('profile') or {}
        accent = tuple(profile.get('accent') or th['accent'])
        x, y, w, h, cx, _, cw = self._workbench_shell(str(profile.get('title') or 'Workshops'), 'workshops')
        self._workshop_station_tabs(cx, y + 92, cw, data, accent)
        self._panel_text(str(profile.get('purpose') or 'Move beside a generated or built workshop fixture to use its processes.'),
                         (cx, y + 131, cw, 37), color=th['muted'], max_lines=2)
        geometry = self._workshop_browser_geometry()
        listing, detail = geometry['list'], geometry['detail']
        self._panel_surface(listing)
        self._panel_surface(detail)
        known = max(0, int(data.get('known_count', len(recipes))))
        locked = max(0, int(data.get('locked_count', 0)))
        self._panel_text(f'{known} KNOWN · {locked} UNDISCOVERED',
                         (listing.x + 12, listing.y + 10, listing.width - 24, 20), color=accent, max_lines=1)
        selected_key = data.get('selected_key')
        if selected_key is None and 0 <= selected < len(rows):
            selected_key = getattr(rows[selected], 'key', '')
        for index, row in enumerate(rows[:geometry['capacity']]):
            rid = getattr(row, 'key', '')
            recipe = recipes.get(rid)
            if not recipe:
                continue
            rect = pg.Rect(listing.x + 10, listing.y + 34 + index * 76, listing.width - 42, 70)
            chosen = rid == selected_key
            hover = rect.collidepoint(self._last_mouse)
            pg.draw.rect(self.screen, (43, 49, 44) if chosen else (34, 42, 42) if hover else th['panel2'], rect, border_radius=5)
            pg.draw.rect(self.screen, accent if chosen else th['edge_hi'] if hover else th['edge'], rect,
                         2 if chosen else 1, border_radius=5)
            outputs = recipe.get('outputs') or []
            if outputs:
                self._panel_item_icon(str(outputs[0].get('id', '')), pg.Rect(rect.x + 8, rect.y + 8, 50, 50))
            self._panel_text(recipe.get('name', rid), (rect.x + 68, rect.y + 7, rect.width - 78, 36), max_lines=2)
            ready = bool(recipe.get('ready'))
            self._panel_text('READY' if ready else 'NEEDS REQUIREMENTS',
                             (rect.x + 68, rect.bottom - 22, rect.width - 78, 18),
                             color=th['good'] if ready else th['danger'], max_lines=1)
            self._ui_target(rect, f'UI_SELECT:{index}')
        if not recipes:
            message = ('No learned processes at this station yet. Experiment with materials in Discovery to reveal techniques.'
                       if data.get('station_id') else 'No usable workshop nearby. Approach a physical station to see its processes.')
            self._panel_text(message, (listing.x + 14, listing.y + 46, listing.width - 42, listing.height - 84), color=th['muted'])
        self._panel_scrollbar((listing.right - 24, listing.y + 34, 18, max(50, listing.height - 62)),
                              page_start, geometry['capacity'], known)
        counter = f'{page_start + 1}–{min(known, page_start + len(rows))} / {known}' if known else '0 learned processes'
        self._panel_text(counter, (listing.x + 12, listing.bottom - 23, listing.width - 38, 20), color=th['muted'], max_lines=1)
        self._panel_text('PROCESS DETAILS', (detail.x + 12, detail.y + 10, detail.width - 24, 20), color=accent, max_lines=1)
        recipe = recipes.get(selected_key)
        if recipe:
            preference_height = self._crafting_preference_control(recipe, detail)
            self._panel_detail('workshop:' + str(selected_key),
                               pg.Rect(detail.x + 12, detail.y + 35, detail.width - 24, max(1, detail.height - 92 - preference_height)),
                               self._crafting_detail_lines(recipe))
            button = pg.Rect(detail.x + 12, detail.bottom - 43, detail.width - 24, 31)
            if recipe.get('ready'):
                self._button(button, str(profile.get('action_label') or 'WORK'), 'UI_ACTION:workshop_craft')
            else:
                self._panel_text('Missing requirements', button.inflate(-14, -8), color=th['muted'], max_lines=1)
        else:
            self._panel_text('Select a learned process to inspect its outputs and complete requirements.',
                             (detail.x + 14, detail.y + 46, detail.width - 28, detail.height - 70), color=th['muted'])
        self._draw_floating_footer(x, y, w, h, subtitle or 'Nearby physical stations · Scroll processes and details · Esc closes')
        self._draw_crafting_tab_tooltip()
        pg.display.flip()
        self.clock.tick(120)

