"""Shared, observational item-browser drawing and inventory layout."""
from __future__ import annotations

from worldseed.content.item_catalog import ITEM_TYPE_LABELS


class ItemPanelMixin:
    def _panel_surface(self, rect):
        self.pg.draw.rect(self.screen, (23, 29, 31), rect, border_radius=7)
        self.pg.draw.rect(self.screen, self._theme['edge'], rect, 1, border_radius=7)

    def _panel_text(self, text, rect, font=None, color=None, max_lines=None):
        rect=self.pg.Rect(rect);font=font or self.small_font
        lines=self._wrap_pixel_text(str(text),font,max(1,rect.w))
        limit=max(0,rect.h//font.get_linesize())
        if max_lines is not None:limit=min(limit,max_lines)
        shown=lines[:limit]
        if shown and len(lines)>limit:
            shown[-1]=self._fit_ui_text(shown[-1]+'…',font,rect.w)
        old=self.screen.get_clip();self.screen.set_clip(rect.clip(old))
        for index,line in enumerate(shown):
            self.screen.blit(font.render(line,True,color or self._theme['text']),(rect.x,rect.y+index*font.get_linesize()))
        self.screen.set_clip(old)
        return len(shown)*font.get_linesize()

    def _panel_item_icon(self, iid, rect):
        """Normalize transparent export margins without stretching item art."""
        rect=self.pg.Rect(rect)
        path=self._visuals.resolve(self._visuals.ref('items',iid))
        cache=getattr(self,'_panel_icon_cache',None)
        if cache is None:cache=self._panel_icon_cache={}
        key=(str(path),rect.w,rect.h)
        if key not in cache:
            if len(cache)>=192:cache.pop(next(iter(cache)))
            try:
                source=self.pg.image.load(str(path)).convert_alpha()
                bounds=source.get_bounding_rect(min_alpha=8)
                if bounds.w and bounds.h:
                    source=source.subsurface(bounds)
                    ratio=min(max(1,rect.w-8)/source.get_width(),max(1,rect.h-8)/source.get_height())
                    cache[key]=self.pg.transform.smoothscale(source,(max(1,round(source.get_width()*ratio)),max(1,round(source.get_height()*ratio))))
                else:cache[key]=None
            except (OSError,self.pg.error,TypeError):cache[key]=None
        sprite=cache[key]
        if sprite is not None:self.screen.blit(sprite,sprite.get_rect(center=rect.center))
        else:self._panel_text('?',rect,color=self._theme['muted'])

    def _panel_scrollbar(self, rect, start, capacity, total):
        pg=self.pg;rect=pg.Rect(rect);maximum=max(0,total-capacity)
        if not maximum:return
        self._button((rect.x,rect.y,rect.w,20),'↑','UI_SCROLL:'+str(max(0,start-capacity)))
        self._button((rect.x,rect.bottom-20,rect.w,20),'↓','UI_SCROLL:'+str(min(maximum,start+capacity)))
        track=pg.Rect(rect.x,rect.y+24,rect.w,max(1,rect.h-48))
        pg.draw.rect(self.screen,(13,19,21),track,border_radius=5)
        thumb_h=min(track.h,max(24,round(track.h*capacity/max(1,total))))
        top=track.y+round((track.h-thumb_h)*min(maximum,start)/maximum)
        pg.draw.rect(self.screen,self._theme['accent'],(track.x+3,top,max(2,track.w-6),thumb_h),border_radius=4)
        self._panel_scroll_track=(track,maximum,thumb_h)
        self._ui_target(track,'UI_SCROLL_TRACK')

    def _panel_detail(self, key, rect, lines):
        """Scroll all detail content above pinned action controls, with clipping."""
        pg=self.pg;rect=pg.Rect(rect);states=getattr(self,'_panel_detail_states',None)
        if states is None:states=self._panel_detail_states={}
        if key not in states:
            if len(states)>=32:states.pop(next(iter(states)))
            states[key]=0
        flow=[];content_w=max(1,rect.w-19)
        for entry in lines:
            kind=entry[0]
            if kind=='item':
                _,iid,text,color=entry
                wrapped=self._wrap_pixel_text(str(text),self.small_font,max(1,content_w-46))
                flow.append((kind,iid,wrapped,color,max(42,len(wrapped)*18)+6))
            else:
                _,text,color=entry
                for line in self._wrap_pixel_text(str(text),self.small_font,content_w):
                    flow.append(('text','',[line],color,20))
        height=sum(row[4] for row in flow);maximum=max(0,height-rect.h)
        offset=min(maximum,states[key]);states[key]=offset
        self._panel_detail_view=(key,rect,maximum)
        yy=rect.y-offset;old=self.screen.get_clip();self.screen.set_clip(rect.clip(old))
        for kind,iid,wrapped,color,rh in flow:
            if yy+rh>rect.y and yy<rect.bottom:
                xx=rect.x
                if kind=='item':self._panel_item_icon(iid,pg.Rect(xx,yy,40,40));xx+=46
                for i,line in enumerate(wrapped):self.screen.blit(self.small_font.render(line,True,color),(xx,yy+i*18))
            yy+=rh
        self.screen.set_clip(old)
        self._panel_detail_track=None
        if maximum:
            track=pg.Rect(rect.right-10,rect.y,8,rect.h);thumb_h=min(track.h,max(18,round(track.h*rect.h/max(1,height))))
            top=track.y+round((track.h-thumb_h)*offset/maximum)
            pg.draw.rect(self.screen,self._theme['edge'],track,border_radius=4)
            pg.draw.rect(self.screen,self._theme['accent'],(track.x,top,track.w,thumb_h),border_radius=4)
            self._panel_detail_track=(track,key,maximum,thumb_h)
            self._ui_target(track,'UI_DETAIL_TRACK')

    def _panel_scroll_pointer(self, token):
        detail=token=='UI_DETAIL_TRACK'
        state=getattr(self,'_panel_detail_track' if detail else '_panel_scroll_track',None)
        if not state:return 'UI_REDRAW'
        if detail:track,key,maximum,thumb_h=state
        else:track,maximum,thumb_h=state
        ratio=(self._last_mouse[1]-track.y-thumb_h/2)/max(1,track.h-thumb_h)
        offset=max(0,min(maximum,round(ratio*maximum)))
        if detail:
            self._panel_detail_states[key]=offset
            return 'UI_REDRAW'
        return 'UI_SCROLL:'+str(offset)

    def _panel_reset_input_regions(self):
        self._panel_scroll_track=None;self._panel_detail_track=None;self._panel_detail_view=None
        self._inventory_desc_rect=None;self._inventory_desc_track=None

    def _inventory_browser_geometry(self):
        pg=self.pg;p=self._floating_panel_state('inventory_unified');x,y,w,h=(p[k] for k in ('x','y','w','h'))
        cw=w-32;dw=max(238,min(302,round(cw*.34)))
        body=pg.Rect(x+16,y+140,cw,h-188)
        grid=pg.Rect(body.x,body.y,body.w-dw-12,body.h)
        detail=pg.Rect(grid.right+12,body.y,dw,body.h)
        columns=max(1,(grid.w-42)//114)
        capacity=columns*max(1,(grid.h-54)//124)
        return {'body':body,'grid':grid,'detail':detail,'columns':columns,'capacity':capacity}

    def menu_grid_columns(self, presentation):
        if presentation=='discovery_pot':return self._discovery_browser_geometry()['columns']
        if presentation=='salvaging_unified':return self._salvage_browser_geometry()['columns']
        return self._inventory_browser_geometry()['columns'] if presentation=='inventory_unified' else 1

    def _present_inventory_unified(self,title,rows,selected,*,subtitle='',breadcrumb='',footer='',page_start=0,total=None,data=None):
        data=data or {};pg=self.pg;screen=self.screen;th=self._theme;items=data.get('items',{})
        x,y,w,h,cx,cy,cw=self._floating_feature_shell('inventory_unified','PACK','Inventory',show_heading=False)
        self._panel_reset_input_regions()
        self._button((x+w-138,y+7,88,27),'CRAFTING','UI_ACTION:open_crafting')
        summary=f"{data.get('stack_count',len(items))} stacks  ·  {data.get('item_count',0)} items"
        self._panel_text(summary,(cx,cy,cw-256,28),font=self.font)
        self._panel_text(f"{data.get('total_mass_kg',0):.1f} kg   /   {data.get('total_volume_l',0):.1f} L",(cx+cw-250,cy,250,28),color=th['accent'])
        filters=['all']+list(data.get('filter_categories') or []);per=6;page=min(max(0,int(data.get('filter_page',0))),(len(filters)-1)//per)
        visible=filters[page*per:(page+1)*per];paged=len(filters)>per
        width=(cw-(78 if paged else 0)-5*(len(visible)-1))//max(1,len(visible))
        for i,cat in enumerate(visible):
            r=pg.Rect(cx+i*(width+5),y+90,width,29);active=cat==data.get('active_filter','all')
            label='All items' if cat=='all' else ITEM_TYPE_LABELS.get(cat,cat.replace('_',' ').title())
            pg.draw.rect(screen,(53,48,34) if active else th['panel2'],r,border_radius=5)
            if active:pg.draw.line(screen,th['accent'],(r.x+8,r.bottom-1),(r.right-8,r.bottom-1),2)
            text=self.small_font.render(self._fit_ui_text(label,self.small_font,r.w-12),True,th['text'] if active else th['muted']);screen.blit(text,text.get_rect(center=r.center))
            self._ui_target(r,'UI_ACTION:filter:'+cat)
        if paged:
            self._button((cx+cw-72,y+90,32,29),'‹','UI_ACTION:filter_page:prev');self._button((cx+cw-34,y+90,32,29),'›','UI_ACTION:filter_page:next')
        self._panel_text(subtitle or 'Click to select  ·  Right-click for actions',(cx,y+122,cw,16),color=th['muted'])
        geo=self._inventory_browser_geometry();grid=geo['grid'];detail=geo['detail'];columns=geo['columns']
        self._panel_surface(grid);self._panel_surface(detail)
        self._panel_text('BACKPACK',(grid.x+12,grid.y+10,grid.w-24,22),color=th['accent'])
        total=len(rows) if total is None else total
        counter=f'{page_start+1}–{page_start+len(rows)} / {total}' if rows else '0 items'
        self._panel_text(counter,(grid.x+12,grid.bottom-23,grid.w-42,20),color=th['muted'])
        card_w=(grid.w-42-8*(columns-1))//columns
        hover=None
        for i,row in enumerate(rows):
            r=pg.Rect(grid.x+10+(i%columns)*(card_w+8),grid.y+36+(i//columns)*124,card_w,116)
            if r.bottom>grid.bottom-26:break
            iid=getattr(row,'key','');m=items.get(iid,{});active=i==selected;over=r.collidepoint(self._last_mouse)
            pg.draw.rect(screen,(48,48,36) if active else (34,43,44) if over else (27,35,37),r,border_radius=6)
            pg.draw.rect(screen,th['accent'] if active else th['edge_hi'] if over else (48,60,62),r,2 if active else 1,border_radius=6)
            icon=pg.Rect(r.centerx-29,r.y+5,58,58)
            if iid!='__empty__':self._panel_item_icon(iid,icon)
            name=str(m.get('name',getattr(row,'label',iid)))
            self._panel_text(name,(r.x+8,r.y+66,r.w-16,36),max_lines=2)
            if iid!='__empty__':
                qty=self.small_font.render('×'+str(m.get('count',0)),True,th['accent']);badge=pg.Rect(r.right-qty.get_width()-12,r.y+5,qty.get_width()+8,19)
                pg.draw.rect(screen,(14,20,22),badge,border_radius=4);screen.blit(qty,(badge.x+4,badge.y+1))
            self._ui_target(r,f'UI_SELECT:{i}')
            if over:hover=(name,r)
        self._panel_scrollbar((grid.right-24,grid.y+35,18,max(50,grid.h-62)),page_start,geo['capacity'],total)
        iid=data.get('selected_key') or data.get('selected_item_id')
        if not iid and rows and 0<=selected<len(rows):iid=getattr(rows[selected],'key','')
        m=items.get(iid,{})
        if m:
            self._panel_text('SELECTED ITEM',(detail.x+12,detail.y+10,detail.w-24,20),color=th['accent'])
            action_top=detail.bottom-146
            lines=[('item',iid,m.get('name',iid),th['text']),('text',f"{m.get('count',0)} carried  ·  {str(m.get('category','misc')).replace('_',' ').title()}",th['accent']),('text',f"{m.get('unit_mass_kg',0):.2f} kg each   ·   {m.get('unit_volume_l',0):.2f} L each",th['muted']),('text',m.get('description',''),th['text'])]
            lines.extend(('text',str(v),th['muted']) for v in m.get('detail_lines',[]) if v)
            if m.get('tags'):lines.append(('text','Crafting tags: '+', '.join(str(tag).replace('_',' ') for tag in m['tags']),th['accent']))
            self._panel_detail('inventory:'+iid,pg.Rect(detail.x+12,detail.y+34,detail.w-24,max(18,action_top-detail.y-42)),lines)
            shown_amount=data.get('action_amount',1) if iid==data.get('selected_item_id',iid) else 1
            amount=max(1,min(int(shown_amount),max(1,int(m.get('count',1)))))
            self._panel_text(f'Quantity  {amount} / {m.get("count",0)}',(detail.x+12,action_top,detail.w-24,20))
            bw=(detail.w-39)//4
            for i,(label,token) in enumerate((('−','qty_down'),('+','qty_up'),('Half','split'),('All','qty_all'))):
                self._button((detail.x+12+i*(bw+5),action_top+24,bw,27),label,'UI_ACTION:'+token)
            aw=(detail.w-29)//2
            def action(rect,label,token,enabled):
                if enabled:self._button(rect,label,token)
                else:self._panel_text(label,pg.Rect(rect).inflate(-8,-8),color=th['muted'],max_lines=1)
            action((detail.x+12,action_top+60,aw,30),str(m.get('use_label','Use'))+' [U]','UI_ACTION:use',m.get('can_use',False))
            action((detail.x+17+aw,action_top+60,aw,30),'Drop [X]','UI_ACTION:drop',True)
            action((detail.x+12,action_top+97,detail.w-24,30),'Store [E]' if data.get('near_storage') else 'No storage nearby','UI_ACTION:store',bool(data.get('near_storage')))
        else:self._panel_text('Select an item to see its details.',detail.inflate(-24,-36),color=th['muted'])
        self._draw_floating_footer(x,y,w,h)
        if hover and self._ui_context is None:
            name,anchor=hover;tip_w=min(330,max(120,self.small_font.size(name)[0]+20));tip_h=22+18*len(self._wrap_pixel_text(name,self.small_font,tip_w-16))
            tip=pg.Rect(min(anchor.x,screen.get_width()-tip_w-8),min(anchor.bottom+6,screen.get_height()-tip_h-8),tip_w,tip_h)
            pg.draw.rect(screen,(12,16,17),tip,border_radius=5);pg.draw.rect(screen,th['edge_hi'],tip,1,border_radius=5)
            self._panel_text(name,tip.inflate(-16,-12))
        self._draw_item_context_popup(rows,data,selected)
        pg.display.flip();self.clock.tick(120)
