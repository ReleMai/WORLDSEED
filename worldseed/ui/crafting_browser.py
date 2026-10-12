"""Read-only crafting browser presentation, shared by the pygame workbench tabs."""
from __future__ import annotations


class CraftingBrowserMixin:
    """A bounded recipe list and independently scrollable recipe inspection pane."""

    _CRAFT_ROW_HEIGHT = 70
    _CRAFT_ROW_PITCH = 76

    def _crafting_browser_geometry(self):
        pg = self.pg
        state = self._floating_panel_state('crafting')
        x, y, w, h = (state[key] for key in ('x', 'y', 'w', 'h'))
        # Always reserve the category pager/status band. Paging capacity must
        # not change when switching to a category with fewer than seven tabs.
        body = pg.Rect(x + 16, y + 158, w - 32, max(1, h - 200))
        gap = 12
        detail_w = min(390, max(284, int(body.width * .43)))
        listing = pg.Rect(body.x, body.y, max(1, body.width - detail_w - gap), body.height)
        detail = pg.Rect(listing.right + gap, body.y, detail_w, body.height)
        capacity = max(1, (listing.height - 52) // self._CRAFT_ROW_PITCH)
        return {'body': body, 'list': listing, 'detail': detail, 'capacity': capacity}

    def _crafting_tabs(self, x, y, w, active):
        """Keep the shared 30px tab strip, reserving a separate search slot."""
        pg = self.pg
        self._crafting_tab_tooltip = None
        tabs = (('Recipes', 'recipes'), ('Workshops', 'workshops'),
                ('Discovery', 'discovery'),
                ('Salvaging', 'salvaging'))
        gap = 4
        available = max(5, w - 112)
        width = max(1, (available - gap * 3) // 4)
        for index, (label, token) in enumerate(tabs):
            rect = pg.Rect(x + index * (width + gap), y, width, 30)
            chosen = token == active
            hovered = rect.collidepoint(self._last_mouse)
            pg.draw.rect(self.screen, (40, 46, 44) if chosen else self._theme['panel2'], rect, border_radius=4)
            pg.draw.line(self.screen, self._theme['edge_hi'] if hovered else self._theme['edge'],
                         (rect.x, rect.bottom - 1), (rect.right - 1, rect.bottom - 1))
            if chosen:
                pg.draw.line(self.screen, self._theme['accent'],
                             (rect.x + 8, rect.bottom - 2), (rect.right - 8, rect.bottom - 2), 3)
            text = self.small_font.render(self._fit_ui_text(label, self.small_font, width - 10),
                                          True, self._theme['accent'] if chosen else self._theme['text'])
            self.screen.blit(text, text.get_rect(center=(rect.centerx, rect.centery - 1)))
            self._ui_target(rect, f'UI_ACTION:tab:{token}')
            if hovered:
                tooltip = 'Experiment Grid' if token == 'discovery' else label
                self._crafting_tab_tooltip = (tooltip, pg.Rect(rect.x, rect.bottom + 5,
                                                              self.small_font.size(tooltip)[0] + 20, 25))

    def _draw_crafting_tab_tooltip(self):
        pending = getattr(self, '_crafting_tab_tooltip', None)
        if not pending:
            return
        label, tip = pending
        tip = tip.clamp(self.screen.get_rect())
        self.pg.draw.rect(self.screen, (12, 16, 17), tip, border_radius=4)
        self.pg.draw.rect(self.screen, self._theme['edge_hi'], tip, 1, border_radius=4)
        text = self.small_font.render(label, True, self._theme['text'])
        self.screen.blit(text, text.get_rect(center=tip.center))

    def _crafting_categories(self, x, y, width, data):
        pg = self.pg
        categories = list(data.get('categories') or [])
        active = str(data.get('category', ''))
        fresh = set(data.get('new_categories') or [])
        pages = max(1, (len(categories) + 5) // 6)
        page = max(0, min(int(data.get('category_page', 0)), pages - 1))
        visible = categories[page * 6:(page + 1) * 6]
        gap = 5
        # Keep slots stable on the final page; fewer categories must not turn
        # into enormous buttons or move the recipe area.
        slot_w = max(1, (width - gap * 5) // 6)
        for index, category in enumerate(visible):
            rect = pg.Rect(x + index * (slot_w + gap), y, slot_w, 30)
            chosen = category == active
            hover = rect.collidepoint(self._last_mouse)
            color = self._theme['accent'] if chosen else self._theme['edge_hi'] if hover else self._theme['edge']
            pg.draw.rect(self.screen, (43, 46, 39) if chosen else self._theme['panel2'], rect, border_radius=4)
            pg.draw.rect(self.screen, color, rect, 1, border_radius=4)
            label = category.replace('_', ' ').title()
            fg = self._theme['accent'] if chosen else self._theme['text']
            if category in fresh:
                pg.draw.circle(self.screen, self._theme['good'], (rect.right - 6, rect.y + 6), 2)
            rendered = self.small_font.render(self._fit_ui_text(label, self.small_font, rect.width - 14), True, fg)
            self.screen.blit(rendered, rendered.get_rect(center=rect.center))
            self._ui_target(rect, f'UI_ACTION:category:{category}')
            if hover and self.small_font.size(label)[0] > rect.width - 14:
                self._crafting_tab_tooltip = (label, pg.Rect(rect.x, rect.bottom + 5,
                                                            self.small_font.size(label)[0] + 20, 25))
        band_y = y + 35
        if pages > 1:
            self._button((x + width - 125, band_y, 28, 24), '‹', 'UI_ACTION:category_page:prev')
            self._button((x + width - 28, band_y, 28, 24), '›', 'UI_ACTION:category_page:next')
            self._panel_text(f'{page + 1} / {pages}', pg.Rect(x + width - 92, band_y + 4, 60, 20),
                             color=self._theme['muted'], max_lines=1)
        status = str(data.get('query') or '')
        status = 'Search: ' + status if status else active.replace('_', ' ').title() + ' recipes'
        self._panel_text(status, pg.Rect(x, band_y + 3, width - (140 if pages > 1 else 0), 22),
                         color=self._theme['muted'], max_lines=1)

    def _crafting_detail_lines(self, recipe):
        """Show the authoritative physical allocation and material-result quality."""
        th = self._theme
        lines = [('text', str(recipe.get('name', 'Recipe')), th['accent']),
                 ('text', f"{recipe.get('minutes', 0)} min  ·  {str(recipe.get('skill', 'crafting')).replace('_', ' ').title()}  ·  Difficulty {recipe.get('difficulty', 0)}", th['muted'])]
        if recipe.get('station'):
            lines.append(('text', 'Station: ' + str(recipe['station']), th['muted']))
        quality = recipe.get('material_quality')
        if recipe.get('material_quality_enabled') and quality is not None:
            source = str(recipe.get('material_source') or 'Selected materials')
            lines.append(('text', f'Input quality: {quality}/100 · {source}', th['accent']))
        lines.append(('text', 'PRODUCES', th['muted']))
        for output in recipe.get('outputs') or []:
            label = f"{output.get('name', output.get('id', ''))} ×{output.get('qty', 1)}"
            if output.get('quality') is not None:
                label += f" · Quality {output['quality']}/100"
            lines.append(('item', str(output.get('id', '')), label, th['good']))
            if output.get('material_name'):
                lines.append(('text', 'Material: ' + str(output['material_name']), th['muted']))
            lines.extend(('text', str(benefit), th['good']) for benefit in output.get('benefits') or [])
        lines.append(('text', 'REQUIRES', th['muted']))
        for ingredient in recipe.get('inputs') or []:
            enough = ingredient.get('have', 0) >= ingredient.get('need', 0)
            units = ' ' + str(ingredient['unit_label']) if ingredient.get('unit_label') else ''
            suffix = ' · retained' if ingredient.get('retained') else ''
            lines.append(('item', str(ingredient.get('id', '')),
                          f"{ingredient.get('name', ingredient.get('id', ''))}  {ingredient.get('have', 0)}/{ingredient.get('need', 0)}{units}{suffix}",
                          th['text'] if enough else th['danger']))
            if ingredient.get('tag'):
                labels=[]
                for option in ingredient.get('options') or []:
                    label=str(option.get('name',''))
                    if option.get('quality') is not None:
                        label += f" · base q{option['quality']}"
                    if option.get('source'):
                        label += ' · ' + str(option['source']).replace('_',' ').title()
                    if option.get('units'):
                        label += f" · {option['units']} units each"
                    labels.append(label)
                if labels:
                    lines.append(('text', 'Accepts: ' + '; '.join(labels), th['muted']))
        if not recipe.get('inputs'):
            lines.append(('text', 'No carried materials required.', th['text']))
        consumed=recipe.get('consumed_items') or []
        if consumed:
            lines.append(('text', 'WILL CONSUME · PHYSICAL ITEMS', th['accent']))
            for item in consumed:
                label=f"{item['name']} ×{item['qty']}"
                if item.get('quality') is not None:label+=f" · q{item['quality']}"
                if item.get('source'):label+=' · '+str(item['source']).replace('_',' ').title()
                lines.append(('item', str(item['id']), label, th['text']))
        elif recipe.get('consumed') is None and recipe.get('material_quality_enabled'):
            lines.append(('text', 'Add the required materials to preview the result.', th['muted']))
        if recipe.get('missing'):
            lines.append(('text', 'STILL NEEDED', th['muted']))
            lines.extend(('text', str(value), th['danger']) for value in recipe['missing'])
        if recipe.get('description'):
            lines.append(('text', 'ABOUT THIS RECIPE', th['muted']))
            lines.append(('text', str(recipe['description']), th['text']))
        return lines

    def _crafting_preference_control(self, recipe, detail):
        """Pin material selection above the existing action, outside text scrolling."""
        if not recipe.get('material_preference_enabled'):
            return 0
        labels={'auto':'Auto','refined':'Refined first','recovered':'Recovered first'}
        label=labels.get(recipe.get('material_preference','auto'),'Auto')
        self._button((detail.x+12,detail.bottom-77,detail.width-24,27),
                     'Materials: '+label+' · Change','UI_ACTION:material_preference')
        return 34

    def _present_crafting_unified(self, title, rows, selected, *, subtitle='', breadcrumb='',
                                  footer='', page_start=0, total=None, data=None):
        data = data or {}
        pg, screen, th = self.pg, self.screen, self._theme
        recipes = data.get('recipes') or {}
        x, y, w, h, cx, cy, cw = self._floating_feature_shell(
            'crafting', 'WORKBENCH', 'Crafting', show_heading=False)
        self._panel_reset_input_regions()
        self._button((x + w - 128, y + 7, 78, 27), 'PACK', 'UI_ACTION:open_inventory')
        self._crafting_tabs(cx, cy, cw, 'recipes')
        self._button((cx + cw - 104, cy, 104, 30), 'SEARCH', 'UI_ACTION:search')
        self._crafting_categories(cx, y + 92, cw, data)
        geometry = self._crafting_browser_geometry()
        listing, detail = geometry['list'], geometry['detail']
        self._panel_surface(listing)
        self._panel_surface(detail)
        count = len(rows) if total is None else total
        self._panel_text(f'RECIPES  ·  {count}', pg.Rect(listing.x + 12, listing.y + 10, listing.width - 24, 22),
                         color=th['muted'], max_lines=1)
        selected_key = data.get('selected_key')
        if selected_key is None and 0 <= selected < len(rows):
            selected_key = getattr(rows[selected], 'key', '')
        for index, row in enumerate(rows[:geometry['capacity']]):
            key = getattr(row, 'key', '')
            recipe = recipes.get(key, {})
            rect = pg.Rect(listing.x + 10, listing.y + 34 + index * self._CRAFT_ROW_PITCH,
                           listing.width - 42, self._CRAFT_ROW_HEIGHT)
            chosen = key == selected_key
            hovered = rect.collidepoint(self._last_mouse)
            pg.draw.rect(screen, (43, 49, 46) if chosen else (34, 41, 40) if hovered else th['panel2'], rect, border_radius=5)
            pg.draw.rect(screen, th['accent'] if chosen else th['edge_hi'] if hovered else th['edge'],
                         rect, 2 if chosen else 1, border_radius=5)
            if chosen:
                pg.draw.rect(screen, th['accent'], (rect.x + 1, rect.y + 8, 3, rect.height - 16), border_radius=1)
            outputs = recipe.get('outputs') or []
            icon = pg.Rect(rect.x + 9, rect.y + 8, 50, 50)
            pg.draw.rect(screen, (20, 27, 27), icon, border_radius=4)
            if outputs:
                self._panel_item_icon(str(outputs[0].get('id', '')), icon.inflate(-6, -6))
            name = str(recipe.get('name') or getattr(row, 'label', key))
            self._panel_text(name, pg.Rect(rect.x + 68, rect.y + 7, rect.width - 78, 36),
                             color=th['text'], max_lines=2)
            ready = bool(recipe.get('ready'))
            badge = 'READY' if ready else 'NEEDS MATERIALS' if recipe else 'NO RECIPES'
            badge_color = th['good'] if ready else th['danger'] if recipe else th['muted']
            self._panel_text(badge, pg.Rect(rect.x + 68, rect.bottom - 22, rect.width - 78, 18),
                             color=badge_color, max_lines=1)
            if recipe.get('new'):
                pg.draw.circle(screen, th['good'], (rect.x + 55, rect.y + 10), 3)
            self._ui_target(rect, f'UI_SELECT:{index}')
        self._panel_scrollbar(pg.Rect(listing.right - 24, listing.y + 34, 18, max(1, listing.height - 62)),
                              page_start, geometry['capacity'], count)
        range_label = f'{page_start + 1}–{min(count, page_start + len(rows))} of {count}' if count else 'No recipes'
        self._panel_text(range_label + '  ·  Wheel / PgUp / PgDn',
                         pg.Rect(listing.x + 12, listing.bottom - 25, listing.width - 24, 20),
                         color=th['muted'], max_lines=1)
        self._panel_text('RECIPE DETAILS', pg.Rect(detail.x + 12, detail.y + 10, detail.width - 24, 22),
                         color=th['muted'], max_lines=1)
        recipe = recipes.get(selected_key, {})
        preference_height = self._crafting_preference_control(recipe, detail) if recipe else 0
        content = pg.Rect(detail.x + 12, detail.y + 35, detail.width - 24, max(1, detail.height - 92 - preference_height))
        if recipe:
            self._panel_detail('crafting:' + str(selected_key), content, self._crafting_detail_lines(recipe))
            button = pg.Rect(detail.x + 12, detail.bottom - 43, detail.width - 24, 31)
            if recipe.get('ready'):
                self._button(button, 'CRAFT RECIPE', 'UI_ACTION:craft')
            else:
                pg.draw.rect(screen, (28, 34, 34), button, border_radius=4)
                self._panel_text('Missing requirements', button.inflate(-16, -8), color=th['muted'], max_lines=1)
        else:
            self._panel_text('Select a known recipe to inspect its materials, outputs and workshop requirements.',
                             content, color=th['muted'])
        self._draw_floating_footer(x, y, w, h, subtitle or 'Select a recipe · Scroll details · Drag title · Resize corner · Esc closes')
        self._draw_crafting_tab_tooltip()
        pg.display.flip()
        self.clock.tick(120)
