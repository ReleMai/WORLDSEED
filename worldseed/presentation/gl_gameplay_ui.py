"""Bounded GPU HUD and shared-menu projection for one caller-owned window.

Only caller-authorized immutable strings enter this module. It owns no events,
navigation, simulation, commands, world surfaces or gameplay state. Small font
surfaces become cached RGBA text textures; the world stays on the GPU.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from hashlib import blake2b
from math import isfinite

from worldseed.ui.layout import screen_width
from worldseed.ui.widgets import ANSI_RE, MenuRow, wrap_line
from .gl_worldspace import GLWorldspaceRenderer, SpriteCommand

MAX_UI_COMMANDS=64
MAX_UI_ROWS=2048
MAX_TEXT_CACHE=96
MAX_TEXT_CACHE_BYTES=4*1024*1024
UI_TEXTURE_BUDGET=8*1024*1024
LINE_PX=22
CHAR_PX=12
INK=(226,234,230)
MUTED=(166,188,181)
ACCENT=(237,201,126)
Rect=tuple[float,float,float,float]


@dataclass(frozen=True,slots=True)
class OverlayModel:
    """Authorized UI projection; row keys are opaque event-routing tokens."""
    hud:tuple[str,...]=()
    message:str=''
    target:str=''
    panel_title:str=''
    rows:tuple[MenuRow,...]=()
    selected:int=0
    scroll:int=0
    details:tuple[str,...]=()
    breadcrumb:str=''
    footer:str='WASD move | Enter actions | Tab world | Esc pause'
    detail_scroll:int=0

    def __post_init__(self):
        for name,limit in (('hud',4),('rows',MAX_UI_ROWS),('details',MAX_UI_ROWS)):
            rows=getattr(self,name)
            if not isinstance(rows,tuple) or len(rows)>limit:
                raise ValueError(f'bounded immutable {name} required')
        if any(not isinstance(row,MenuRow) for row in self.rows):
            raise ValueError('overlay rows must use shared MenuRow records')
        if len({row.key for row in self.rows})!=len(self.rows):
            raise ValueError('overlay row keys must be unique')
        strings=(*self.hud,*self.details,self.message,self.target,self.panel_title,
                 self.breadcrumb,self.footer,
                 *(text for row in self.rows for text in (row.key,row.label,row.hint)))
        if any(not isinstance(text,str) or len(text)>4096 for text in strings):
            raise ValueError('overlay strings exceed bounded record size')
        if any(type(value) is not int or value<0
               for value in (self.selected,self.scroll,self.detail_scroll)):
            raise ValueError('overlay selection and scroll must be nonnegative integers')


@dataclass(frozen=True,slots=True)
class HitRegion:
    uid:str
    bounds:Rect
    row_index:int=-1

    def contains(self,x,y):
        left,top,right,bottom=self.bounds
        return left<=x<right and top<=y<bottom


@dataclass(frozen=True,slots=True)
class TextRun:
    uid:str
    text:str
    bounds:Rect
    color:tuple[int,int,int]=INK


@dataclass(frozen=True,slots=True)
class Panel:
    uid:str
    bounds:Rect
    color:tuple[int,int,int,int]


@dataclass(frozen=True,slots=True)
class OverlayLayout:
    width:int
    height:int
    panels:tuple[Panel,...]
    texts:tuple[TextRun,...]
    hitregions:tuple[HitRegion,...]
    page_start:int=0
    page_size:int=0
    total_rows:int=0
    detail_start:int=0
    detail_page_size:int=0
    total_detail_lines:int=0

    def hit_test(self,x,y):
        if not all(type(value) in (int,float) and isfinite(value) for value in (x,y)):
            return None
        return next((region.uid for region in self.hitregions
                     if region.uid and region.contains(x,y)),None)

    def blocks_world(self,x,y):
        return any(region.contains(x,y) for region in self.hitregions)


def _flow(text,columns):
    clean=ANSI_RE.sub('',text).replace('\t',' ')
    return [line for paragraph in clean.splitlines() or ['']
            for line in wrap_line(paragraph,columns)]


def build_layout(width:int,height:int,model:OverlayModel)->OverlayLayout:
    """Pure, read-only geometry; no global minimum viewport or event routing."""
    if (type(width) is not int or type(height) is not int or
            not 1<=width<=3840 or not 1<=height<=2160 or not isinstance(model,OverlayModel)):
        raise ValueError('bounded viewport and immutable OverlayModel required')
    panels=[];texts=[];hits=[]
    margin=min(12,max(0,width//40))
    inner=max(1,width-2*margin)
    columns=max(8,min(inner//CHAR_PX,screen_width(max(1,inner//CHAR_PX))))
    def panel(uid,bounds,color=(12,24,23,238)):
        panels.append(Panel(uid,bounds,color));hits.append(HitRegion('',bounds))
    def text(uid,value,x,y,right,color=INK):
        if y>=height or right<=x:return
        # A heading/status is one line; full records use the paged details area.
        line=_flow(value,max(8,(right-x)//CHAR_PX))[0]
        texts.append(TextRun(uid,line,(float(x),float(max(0,y)),float(right),float(min(height,y+LINE_PX))),color))
    hud_lines=[line for value in model.hud for line in _flow(value,columns)]
    # HUD fields are deliberately short summaries; records belong in the paged
    # panel. Four source rows may wrap across two physical lines each.
    hud_lines=hud_lines[:8]
    hud_height=min(height,len(hud_lines)*LINE_PX+12) if hud_lines else 0
    if hud_lines:
        panel('hud',(0.,0.,float(width),float(hud_height)))
        for index,line in enumerate(hud_lines):text(f'hud:{index}',line,margin,6+index*LINE_PX,width-margin)
    footer_lines=[]
    if model.target:footer_lines.append(('target',model.target,ACCENT))
    if model.message:footer_lines.extend((f'message:{i}',line,INK)
        for i,line in enumerate(_flow(model.message,columns)[:2]))
    if model.footer:footer_lines.append(('controls',model.footer,MUTED))
    footer_height=min(height,len(footer_lines)*LINE_PX+12) if footer_lines else 0
    footer_top=max(hud_height,height-footer_height)
    if footer_lines and footer_top<height:
        panel('footer',(0.,float(footer_top),float(width),float(height)))
        for index,(uid,line,color) in enumerate(footer_lines):
            text(uid,line,margin,footer_top+6+index*LINE_PX,width-margin,color)
    page_start=page_size=detail_start=detail_size=detail_total=0
    if model.panel_title:
        panel_width=min(780,max(1,width-2*margin))
        left=(width-panel_width)//2;right=left+panel_width
        top=min(height,max(hud_height+10,margin))
        bottom=max(top,min(height-margin,footer_top-10))
        if bottom-top>=LINE_PX*4:
            panel('menu',(float(left),float(top),float(right),float(bottom)))
            # A modal captures its whole viewport, including transparent margins.
            hits.insert(0,HitRegion('',(0.,0.,float(width),float(height))))
            x=left+12;edge=right-12;y=top+8
            cols=max(8,(edge-x)//CHAR_PX)
            text('panel-title',model.panel_title,x,y,edge,ACCENT);y+=LINE_PX
            if model.breadcrumb:
                text('breadcrumb',model.breadcrumb,x,y,edge,MUTED);y+=LINE_PX
            detail_values=list(model.details)
            if model.rows:
                active=model.rows[min(model.selected,len(model.rows)-1)]
                # Long menu labels remain available in full through details
                # paging instead of creating an unselectable oversized row.
                if len(_flow(active.label,cols))>2:detail_values.insert(0,active.label)
                if active.hint and active.hint not in detail_values:detail_values.append(active.hint)
            flowed=[line for value in detail_values for line in _flow(value,cols)]
            detail_total=len(flowed)
            detail_capacity=min(4 if model.rows else 16,
                max(0,(bottom-y-LINE_PX*(3 if model.rows else 2))//LINE_PX))
            detail_start=min(model.detail_scroll,max(0,detail_total-detail_capacity))
            for index,line in enumerate(flowed[detail_start:detail_start+detail_capacity]):
                text(f'detail:{detail_start+index}',line,x,y,edge,MUTED);y+=LINE_PX
            detail_size=min(detail_capacity,max(0,detail_total-detail_start))
            if detail_total>detail_size:
                text('detail-page',f'Details {detail_start+1}-{detail_start+detail_size} / {detail_total}',
                     x,y,edge,MUTED);y+=LINE_PX
            capacity=min(16,max(0,(bottom-y-LINE_PX-8)//LINE_PX))
            page_start=min(model.scroll,max(0,len(model.rows)-1))
            for index,row in enumerate(model.rows[page_start:]):
                # Menu labels wrap; hints/details remain separate shared rows.
                lines=_flow(row.label,cols)[:2]
                if len(lines)>capacity-page_size:break
                row_index=page_start+index
                if row_index==model.selected:
                    panels.append(Panel('selected',(float(left+6),float(y),float(right-6),float(y+len(lines)*LINE_PX)),(47,69,59,255)))
                hits.append(HitRegion(row.key,(float(left+6),float(y),float(right-6),float(y+len(lines)*LINE_PX)),row_index))
                for part,line in enumerate(lines):
                    text(f'row:{row_index}:{part}',line,x,y,edge,ACCENT if row_index==model.selected else INK)
                    y+=LINE_PX
                page_size+=len(lines)
            shown=sum(region.row_index>=0 for region in hits)
            page_size=shown
            status=(f'{page_start+1}-{page_start+shown} / {len(model.rows)} | ' if model.rows else '')
            text('menu-controls',status+'Arrows select | Enter confirm | Esc back',x,bottom-LINE_PX-4,edge,MUTED)
    if len(panels)+len(texts)>MAX_UI_COMMANDS:
        raise ValueError('overlay exceeds bounded GPU command budget')
    return OverlayLayout(width,height,tuple(panels),tuple(texts),tuple(hits),page_start,
        page_size,len(model.rows),detail_start,detail_size,detail_total)


class _OverlayContext:
    """Reuse the sprite renderer while preserving the caller's completed scene.

    GLWorldspaceRenderer clears its target for world draws. Only this private
    proxy suppresses that operation; all GL objects/state remain caller-owned.
    """
    def __init__(self,context):object.__setattr__(self,'_context',context)
    def __getattr__(self,name):return getattr(self._context,name)
    def __setattr__(self,name,value):setattr(self._context,name,value)
    def clear(self,*args,**kwargs):pass


class GLGameplayUI:
    """Small text/panel sprite pass after atmosphere, without a window or pump."""
    def __init__(self,ctx,pg,width,height):
        self.pg=pg;self.width=width;self.height=height
        self.closed=False;self.cache_bytes=0;self._cache=OrderedDict()
        if not pg.font.get_init():pg.font.init()
        self.font=pg.font.SysFont('consolas,dejavusansmono,couriernew',18)
        self.renderer=GLWorldspaceRenderer(_OverlayContext(ctx),width,height,texture_budget=UI_TEXTURE_BUDGET)

    def _text_source(self,run):
        key=(run.text,run.color)
        old=self._cache.get(key)
        if old is not None:
            self._cache.move_to_end(key);return old
        surface=self.font.render(run.text or ' ',True,run.color)
        width,height=surface.get_size()
        rgba=self.pg.image.tobytes(surface,'RGBA')
        digest=blake2b(rgba,digest_size=16).hexdigest()
        value=(f'gpu-ui:text:{digest}',0,rgba,width,height)
        size=len(rgba)
        if size>MAX_TEXT_CACHE_BYTES:raise ValueError('single overlay text exceeds texture cache budget')
        while self._cache and (len(self._cache)>=MAX_TEXT_CACHE or self.cache_bytes+size>MAX_TEXT_CACHE_BYTES):
            _,removed=self._cache.popitem(last=False);self.cache_bytes-=len(removed[2])
        self._cache[key]=value;self.cache_bytes+=size
        return value

    def draw(self,model:OverlayModel)->OverlayLayout:
        if self.closed:raise RuntimeError('GPU overlay is closed')
        layout=build_layout(self.width,self.height,model)
        commands=[]
        for panel in layout.panels:
            tex=(f'gpu-ui:panel:{panel.color}',0,bytes(panel.color),1,1)
            commands.append(SpriteCommand(panel.uid,*tex,panel.bounds,(panel.bounds,)))
        for run in layout.texts:
            tex=self._text_source(run)
            x,y,right,bottom=run.bounds
            bounds=(x,y,x+tex[3],y+tex[4])
            commands.append(SpriteCommand(run.uid,*tex,bounds,((x,y,right,bottom),)))
        self.renderer.draw(commands,ambient=(1.,1.,1.))
        return layout

    def resize(self,width,height):
        build_layout(width,height,OverlayModel())
        self.renderer.resize(width,height);self.width=width;self.height=height

    def close(self):
        if self.closed:return
        self.closed=True
        self.renderer.close();self._cache.clear();self.cache_bytes=0
