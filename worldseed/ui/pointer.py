"""Presentation-only pointer targets. Tokens are interpreted by existing widgets.
No simulation state is stored here, and hit regions are rebuilt every frame.
"""
from worldseed.ui.presentation_style import draw_button_background


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

    def _button(self, rect, label, token, *, enabled=True, prominent=False, destructive=False):
        pg=self.pg;rect=pg.Rect(rect)
        hover=bool(enabled) and rect.collidepoint(self._last_mouse)
        text_color=draw_button_background(pg,self.screen,rect,self._theme,
                                          hovered=hover,enabled=enabled,
                                          prominent=prominent,destructive=destructive)
        text=self.small_font.render(self._fit_ui_text(label,self.small_font,rect.width-12),True,text_color)
        self.screen.blit(text,text.get_rect(center=rect.center))
        if enabled:self._ui_target(rect,token)

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
        if presentation=='npc_dialogue':
            panel=self._floating_panel_state('npc_dialogue')
            # Match the 52px shell, 64px portrait strip, 36px path, 46px
            # footer, 40px reply heading, and 44px paging reserve. The last
            # 34px row uses no trailing gap, so add four before division.
            return max(1,(panel['h']-278)//38)
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

    def present_creation_overview(self,kind,data):
        """Graphical review screens for character and world creation."""
        pg=self.pg;screen=self.screen
        label='CHARACTER OVERVIEW' if kind=='character' else 'WORLD OVERVIEW'
        x,y,w,h=self._draw_chrome(f'WORLDSEED // {label}')
        self._paint_menu_veil((x,y,w,h));self._set_input_mode('ui')
        panel_w=max(860,min(1180,w-70));panel_h=max(540,min(720,h-80))
        panel=pg.Rect(x+(w-panel_w)//2,y+(h-panel_h)//2,panel_w,panel_h)
        pg.draw.rect(screen,(17,22,23),panel,border_radius=10)
        pg.draw.rect(screen,self._theme['accent'],panel,2,border_radius=10)
        heading=self.title_font.render(label,True,self._theme['accent']);screen.blit(heading,(panel.x+24,panel.y+20))
        pg.draw.line(screen,self._theme['edge'],(panel.x+20,panel.y+60),(panel.right-20,panel.y+60),1)
        body=pg.Rect(panel.x+20,panel.y+76,panel.width-40,panel.height-150)

        if kind=='character':
            left=pg.Rect(body.x,body.y,240,body.height)
            right=pg.Rect(left.right+16,body.y,body.right-left.right-16,body.height)
            for rr in (left,right):
                pg.draw.rect(screen,self._theme['panel'],rr,border_radius=7);pg.draw.rect(screen,self._theme['edge'],rr,1,border_radius=7)
            name=str(data.get('name','Wanderer'));sex=str(data.get('sex','male'));index=int(data.get('sprite_index',0))
            ns=self.title_font.render(self._fit_ui_text(name,self.title_font,left.width-28),True,self._theme['text']);screen.blit(ns,(left.x+14,left.y+14))
            meta=self.small_font.render(f"{sex.title()} · {data.get('sprite_label','Appearance')}",True,self._theme['muted']);screen.blit(meta,(left.x+14,left.y+45))
            paths=getattr(self,'_visuals',None)
            sprite_paths=paths.player_paths(sex) if paths is not None else ()
            if sprite_paths:
                frame=pg.Rect(left.x+24,left.y+82,left.width-48,260)
                pg.draw.rect(screen,(12,17,18),frame,border_radius=6);pg.draw.rect(screen,self._theme['edge_hi'],frame,1,border_radius=6)
                sprite=self._load_sprite(sprite_paths[max(0,min(index,len(sprite_paths)-1))],frame.width-18,frame.height-18)
                if sprite is not None:screen.blit(sprite,(frame.centerx-sprite.get_width()//2,frame.bottom-sprite.get_height()-8))
            note=self.small_font.render('This is the build that will enter the world.',True,self._theme['muted']);screen.blit(note,(left.x+14,left.bottom-30))

            cols=3;gap=10;col_w=(right.width-gap*2-24)//3
            sections=[
                ('ATTRIBUTES',data.get('attributes',[])),
                ('TRAINED SKILLS',data.get('skills',[])),
                ('TALENTS',data.get('talents',[])),
            ]
            for ci,(section,rows) in enumerate(sections):
                rr=pg.Rect(right.x+8+ci*(col_w+gap),right.y+8,col_w,right.height-16)
                pg.draw.rect(screen,(24,29,30),rr,border_radius=6);pg.draw.rect(screen,self._theme['edge'],rr,1,border_radius=6)
                hs=self.small_font.render(section,True,self._theme['accent']);screen.blit(hs,(rr.x+10,rr.y+10));yy=rr.y+38
                for row in list(rows)[:12]:
                    if yy+42>rr.bottom-8:break
                    if isinstance(row,dict):
                        nm=str(row.get('name',''));val=row.get('value',None);desc=str(row.get('description',''))
                    else:nm=str(row);val=None;desc=''
                    label=nm+(f'  {val}' if val is not None else '')
                    ls=self.small_font.render(self._fit_ui_text(label,self.small_font,rr.width-20),True,self._theme['text']);screen.blit(ls,(rr.x+10,yy));yy+=18
                    if desc:
                        ds=self.small_font.render(self._fit_ui_text(desc,self.small_font,rr.width-20),True,self._theme['muted']);screen.blit(ds,(rr.x+10,yy));yy+=20
                    else:yy+=8
        else:
            left=pg.Rect(body.x,body.y,int(body.width*.55),body.height)
            right=pg.Rect(left.right+16,body.y,body.right-left.right-16,body.height)
            for rr in (left,right):
                pg.draw.rect(screen,self._theme['panel'],rr,border_radius=7);pg.draw.rect(screen,self._theme['edge'],rr,1,border_radius=7)
            world=str(data.get('world_name','New World'));seed=str(data.get('seed',''));start=str(data.get('start_mode','wilderness')).replace('_',' ').title()
            ws=self.title_font.render(self._fit_ui_text(world,self.title_font,left.width-30),True,self._theme['text']);screen.blit(ws,(left.x+15,left.y+16))
            cards=[('WORLD SEED',seed),('START',start),('SURVIVOR',str(data.get('character_name','Wanderer'))),('APPEARANCE',f"{str(data.get('sex','male')).title()} · {data.get('sprite_label','')}")]
            yy=left.y+62
            for lab,val in cards:
                rr=pg.Rect(left.x+14,yy,left.width-28,62)
                pg.draw.rect(screen,(24,29,30),rr,border_radius=5);pg.draw.rect(screen,self._theme['edge'],rr,1,border_radius=5)
                screen.blit(self.small_font.render(lab,True,self._theme['muted']),(rr.x+10,rr.y+8))
                vv=self.font.render(self._fit_ui_text(str(val),self.font,rr.width-20),True,self._theme['text']);screen.blit(vv,(rr.x+10,rr.y+30));yy+=72
            screen.blit(self.small_font.render('BEGINNING PROFILE',True,self._theme['accent']),(right.x+12,right.y+12))
            yy=right.y+42
            for row in data.get('attributes',[]):
                nm=str(row.get('name',''));val=int(row.get('value',0))
                screen.blit(self.small_font.render(nm,True,self._theme['text']),(right.x+12,yy))
                bar=pg.Rect(right.x+112,yy+4,right.width-136,8);pg.draw.rect(screen,(45,50,49),bar,border_radius=3)
                fill=pg.Rect(bar.x,bar.y,round(bar.width*max(0,min(10,val))/10),bar.height)
                if fill.width:pg.draw.rect(screen,self._theme['accent'],fill,border_radius=3)
                yy+=28
            yy+=10;screen.blit(self.small_font.render('TALENTS',True,self._theme['accent']),(right.x+12,yy));yy+=25
            for talent in data.get('talents',[])[:8]:
                screen.blit(self.small_font.render('• '+str(talent),True,self._theme['text']),(right.x+15,yy));yy+=22

        footer=self.small_font.render('Review the choices above. Continue confirms this stage; Back returns to edit.',True,self._theme['muted'])
        # Keep explanatory copy in its own row.  Navigation occupies the final
        # 43 pixels of the panel, so sharing that baseline caused the copy to
        # paint directly across Back/Continue on both overview screens.
        footer_rect=footer.get_rect(centerx=panel.centerx,y=panel.bottom-72)
        self._creation_overview_footer_rect=footer_rect
        screen.blit(footer,footer_rect)
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
