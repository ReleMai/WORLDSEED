"""Presentation-only pointer targets. Tokens are interpreted by existing widgets.
No simulation state is stored here, and hit regions are rebuilt every frame.
"""
class WindowCloseRequested(Exception):
    """Unwind a modal UI to the application save/exit boundary."""


class PointerUI:
    mouse_ui = True

    def _set_input_mode(self, mode):
        if getattr(self, '_input_mode', None) != mode:
            self._held_movement.clear()
            self._active_movement_key = None
            self._movement_next_repeat_ms = 0
        self._input_mode = mode

    def _ui_target(self, rect, token):
        self._pointer_targets.append((self.pg.Rect(rect), token))

    def _hit_token(self, pos):
        return next((token for rect,token in reversed(self._pointer_targets) if rect.collidepoint(pos)), None)

    def _button(self, rect, label, token):
        pg=self.pg;rect=pg.Rect(rect)
        hover=rect.collidepoint(self._last_mouse)
        pg.draw.rect(self.screen, (43,48,48) if hover else self._theme['panel2'], rect, border_radius=5)
        pg.draw.rect(self.screen,self._theme['accent'] if hover else self._theme['edge_hi'],rect,1,border_radius=5)
        text=self.small_font.render(self._fit_ui_text(label,self.small_font,rect.width-12),True,self._theme['text'])
        self.screen.blit(text,text.get_rect(center=rect.center))
        self._ui_target(rect,token)

    def _ui_navigation(self, *, confirm=False, extra=None, back=True, paging=True):
        w,h=self.screen.get_size();y=h-52
        buttons=[('Back','ESC')] if back else []
        if confirm:buttons.append(('Continue','\r'))
        elif paging:buttons.extend([('Previous','PGUP'),('Next','PGDN')])
        if extra:buttons.append(extra)
        panel=getattr(self,'_menu_nav_rect',None)
        if panel is not None:
            y=panel.bottom-43
            first_x=panel.centerx-(len(buttons)*104+(len(buttons)-1)*8)//2
        else:first_x=36
        for i,(label,token) in enumerate(buttons):
            self._button((first_x+i*112,y,104,30),label,token)

    def menu_page_size(self, presentation=''):
        w,h=self.screen.get_size()
        if presentation in ('container_inventory','inventory_unified','crafting_unified','discovery_pot','crafting_index'):
            panel_id='crafting' if presentation in ('crafting_unified','discovery_pot','crafting_index') else presentation
            state=getattr(self,'_floating_panels',{}).get(panel_id)
            if state:
                w,h=state.get('w',w),state.get('h',h)
            elif hasattr(self,'_floating_panel_minimum'):
                # Pagination is computed before the first panel render. Mirror
                # the renderer's default floating-panel geometry so the caller
                # never hands the panel more rows than it can actually expose.
                sw,sh=w,h
                min_w,min_h=self._floating_panel_minimum(panel_id)
                target_w=1080 if panel_id in ('container_inventory','crafting') else 900
                target_h=680 if panel_id in ('container_inventory','crafting') else 620
                w=max(min_w,min(sw-16,min(sw-48,target_w)))
                h=max(min_h,min(sh-16,min(sh-48,target_h)))
        usable=max(80,h-245)
        if presentation=='container_inventory':
            return max(4,2*max(2,usable//105))
        if presentation=='inventory_unified':
            detail_w=max(292,min(378,max(1,w-32)//3))
            grid_w=max(180,w-32-detail_w-16)
            cols=4 if grid_w>=570 else (3 if grid_w>=390 else 2)
            return cols*max(1,usable//120)
        if presentation=='crafting_unified':return max(1,(h-236)//73)
        if presentation=='discovery_pot':return max(1,(h-250)//49)
        if presentation=='crafting_index':return max(1,(h-285)//40)
        if presentation=='inventory_items':
            grid_w=w-72-max(280,min(360,(w-72)//3))-16
            return (4 if grid_w>=560 else 3)*max(1,usable//127)
        if presentation=='crafting_categories':return 3*max(1,usable//108)
        if presentation=='crafting_designs':return 3
        if presentation in ('crafting_recipes','crafting_experiments'):return max(1,min(6,usable//98))
        if presentation=='crafting_component_choices':return max(1,min(5,usable//117))
        if presentation:return max(1,min(5,usable//78))
        return max(1,usable//34)

    def document_page_size(self):
        return max(3,(self.screen.get_height()-220)//self.char_h)

    def present_text_entry(self, text):
        self.present(text)
        self._set_input_mode('text')
        self._ui_navigation(confirm=True)
        self.pg.display.flip()

    def present_text_field(self,title,label,value,*,max_len=48,allow_blank=True):
        """Purpose-built new-game text field instead of a boxed console dump."""
        pg=self.pg;screen=self.screen
        x,y,w,h=self._draw_chrome(f'WORLDSEED // {title}')
        self._paint_menu_veil((x,y,w,h));self._set_input_mode('text')
        panel_w=max(520,min(820,w-120));panel_h=270
        panel=pg.Rect(x+(w-panel_w)//2,y+(h-panel_h)//2,panel_w,panel_h)
        pg.draw.rect(screen,(18,23,24),panel,border_radius=9)
        pg.draw.rect(screen,self._theme['accent'],panel,2,border_radius=9)
        pg.draw.line(screen,self._theme['edge'],(panel.x+18,panel.y+62),(panel.right-18,panel.y+62),1)
        heading=self.title_font.render(str(title),True,self._theme['accent'])
        screen.blit(heading,(panel.x+22,panel.y+20))
        prompt=self.font.render(str(label),True,self._theme['text'])
        screen.blit(prompt,(panel.x+28,panel.y+84))
        help_map={
            'Name this world:':'This name identifies the save and world history. It does not change the seed.',
            'World seed (blank = random):':'Seeds reproduce terrain, settlements and generated civilization. Leave blank for a random seed.',
            'Character name:':'Your survivor name is used in social records, journals and property ownership.',
        }
        hint=help_map.get(str(label),'Type a value, then continue.')
        hs=self.small_font.render(self._fit_ui_text(hint,self.small_font,panel.width-56),True,self._theme['muted'])
        screen.blit(hs,(panel.x+28,panel.y+112))
        field=pg.Rect(panel.x+28,panel.y+148,panel.width-56,48)
        pg.draw.rect(screen,(12,17,18),field,border_radius=6)
        pg.draw.rect(screen,self._theme['edge_hi'],field,1,border_radius=6)
        shown=str(value)
        cursor='|' if (pg.time.get_ticks()//450)%2==0 else ''
        txt=self.font.render(self._fit_ui_text(shown+cursor,self.font,field.width-24),True,self._theme['text'])
        screen.blit(txt,(field.x+12,field.centery-txt.get_height()//2))
        count=self.small_font.render(f'{len(shown)}/{max_len}',True,self._theme['muted'])
        screen.blit(count,(field.right-count.get_width(),field.bottom+7))
        self._menu_nav_rect=panel
        self._ui_navigation(confirm=True)
        pg.display.flip();self.clock.tick(120)

    def present_allocation(self,title,rows,selected,remaining):
        """Two-pane point allocation with controls separate from row hit targets."""
        pg=self.pg;screen=self.screen
        x,y,w,h=self._draw_chrome(f'WORLDSEED // {title}')
        self._paint_menu_veil((x,y,w,h));self._set_input_mode('ui')
        panel_w=max(760,min(1040,w-80));panel_h=max(480,min(660,h-90))
        panel=pg.Rect(x+(w-panel_w)//2,y+(h-panel_h)//2,panel_w,panel_h)
        pg.draw.rect(screen,(18,23,24),panel,border_radius=9);pg.draw.rect(screen,self._theme['accent'],panel,2,border_radius=9)
        heading=self.title_font.render(str(title),True,self._theme['text']);screen.blit(heading,(panel.x+22,panel.y+18))
        rem=self.font.render(f'Points remaining: {remaining}',True,self._theme['accent'] if remaining else self._theme['good'])
        screen.blit(rem,(panel.right-rem.get_width()-22,panel.y+20))
        body_y=panel.y+62;footer_h=58;gap=14
        left=pg.Rect(panel.x+18,body_y,int((panel.width-36-gap)*.58),panel.height-80-footer_h)
        right=pg.Rect(left.right+gap,body_y,panel.right-left.right-gap-18,left.height)
        for rr in (left,right):
            pg.draw.rect(screen,self._theme['panel'],rr,border_radius=7);pg.draw.rect(screen,self._theme['edge'],rr,1,border_radius=7)
        capacity=max(5,(left.height-20)//48);start=(selected//capacity)*capacity
        page=rows[start:start+capacity]
        for local,row in enumerate(page):
            idx=start+local;rr=pg.Rect(left.x+10,left.y+10+local*48,left.width-20,40)
            active=idx==selected;hover=rr.collidepoint(self._last_mouse)
            pg.draw.rect(screen,(47,51,45) if active or hover else (26,31,32),rr,border_radius=5)
            pg.draw.rect(screen,self._theme['accent'] if active else self._theme['edge'],rr,2 if active else 1,border_radius=5)
            label=str(getattr(row,'label',row));name,value=(label.rsplit(': ',1)+[''])[:2] if ': ' in label else (label,'')
            ns=self.font.render(self._fit_ui_text(name,self.font,rr.width-96),True,self._theme['text']);screen.blit(ns,(rr.x+12,rr.centery-ns.get_height()//2))
            vs=self.font.render(value,True,self._theme['accent']);screen.blit(vs,(rr.right-vs.get_width()-12,rr.centery-vs.get_height()//2))
            self._ui_target(rr,f'UI_SELECT:{local}')
        active_row=rows[selected] if rows else None
        label=str(getattr(active_row,'label','')) if active_row else ''
        hint=str(getattr(active_row,'hint','')) if active_row else ''
        title_text=label.split(':',1)[0]
        ts=self.title_font.render(self._fit_ui_text(title_text,self.title_font,right.width-30),True,self._theme['accent']);screen.blit(ts,(right.x+15,right.y+18))
        yy=right.y+58
        for line in self._wrap_pixel_text(hint,self.font,right.width-30)[:6]:
            screen.blit(self.font.render(line,True,self._theme['text']),(right.x+15,yy));yy+=24
        note='Attributes define broad physical and mental capacity.' if str(title).upper()=='ATTRIBUTES' else 'Skills improve task effectiveness and unlock better results through practice.'
        yy=max(yy+16,right.y+180)
        for line in self._wrap_pixel_text(note,self.small_font,right.width-30)[:3]:
            screen.blit(self.small_font.render(line,True,self._theme['muted']),(right.x+15,yy));yy+=18
        control_y=right.bottom-58
        self._button((right.x+16,control_y,70,34),'−',f'UI_MINUS:{selected}')
        self._button((right.x+94,control_y,70,34),'+',f'UI_PLUS:{selected}')
        page_s=self.small_font.render(f'{selected+1}/{len(rows)}',True,self._theme['muted']);screen.blit(page_s,(right.right-page_s.get_width()-18,control_y+9))
        self._menu_nav_rect=panel
        self._ui_navigation(extra=('Continue','\r'))
        pg.display.flip();self.clock.tick(120)
        return start
