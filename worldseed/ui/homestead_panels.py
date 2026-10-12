"""WORLDSEED homestead floating gameplay overlays.

Pure presentation helpers: never consume inventory, generate terrain, or alter
homestead state. Click targets are consumed by the app's command dispatcher.
"""
from __future__ import annotations

def _label(term, value, pos, *, color=None, large=False, centered=False, width=None):
    font=term.font if large else term.small_font
    color=color or term._theme['text']
    value=str(value)
    if width is not None:value=term._fit_ui_text(value,font,max(12,int(width)))
    surf=font.render(value,True,color)
    rect=surf.get_rect(center=pos) if centered else surf.get_rect(topleft=pos)
    term.screen.blit(surf,rect)
    return rect


def _button(term, rect, label, token, *, prominent=False, enabled=True):
    pg=term.pg
    rect=pg.Rect(rect)
    hover=rect.collidepoint(term._last_mouse) and enabled
    fill=(76,72,51) if prominent else (43,49,47)
    if hover:fill=(92,85,56) if prominent else (54,62,57)
    if not enabled:fill=(30,34,34)
    pg.draw.rect(term.screen,fill,rect,border_radius=5)
    pg.draw.rect(term.screen,term._theme['accent'] if prominent and enabled else term._theme['edge'],rect,2 if prominent and enabled else 1,border_radius=5)
    _label(term,label,rect.center,centered=True,color=term._theme['text'] if enabled else term._theme['muted'],width=rect.width-12)
    if enabled:term._ui_target(rect,token)


def render_cabin_style(pg,style,size=(420,252)):
    """Generate an individual illustrated catalog image from stable style data.

    The returned sprite is a UI concept preview. Footprints, entrances, and
    material costs continue to come exclusively from the simulation catalog.
    """
    w,h=size
    surf=pg.Surface(size,pg.SRCALPHA)
    idx=int(style['id'].rsplit('_',1)[-1])
    roof_type=style.get('roof_detail','simple')
    trim=style.get('trim','plank')
    accent=style.get('accent','straight')
    door=style.get('door_position','center')
    colors=[
        ((128,93,61),(91,75,48)),((108,82,58),(70,86,56)),
        ((144,94,64),(110,74,52)),((139,111,72),(125,119,69)),
        ((112,95,82),(75,71,76)),((121,98,65),(63,91,63)),
        ((92,83,78),(84,74,75)),((142,103,64),(81,76,61)),
        ((139,93,61),(100,70,53)),((127,92,60),(85,67,50))]
    logs,roof=colors[(idx-1)%len(colors)]
    pg.draw.rect(surf,(28,37,34,255),(0,0,w,h))
    # Dim scenic gradient and a simple ground contour make the artwork legible.
    for i in range(0,h,4):
        t=i/max(1,h)
        c=(int(29+12*t),int(42+16*t),int(44+7*t))
        pg.draw.rect(surf,c,(0,i,w,4))
    pg.draw.ellipse(surf,(27,37,31),(20,183,w-40,62))
    pg.draw.ellipse(surf,(54,67,48),(56,197,w-112,31))
    # Foundation platform, heavier for Highland / Riverbank.
    foundation=(100,98,91) if trim=='stone' else (90,73,52)
    base=pg.Rect(77,182,268,20)
    if accent=='raised_sill':
        pg.draw.rect(surf,(71,57,39),(95,184,10,38))
        pg.draw.rect(surf,(71,57,39),(324,184,10,38))
        base=base.move(0,-11)
    pg.draw.rect(surf,foundation,base,border_radius=3)
    pg.draw.line(surf,(35,29,25),base.bottomleft,base.bottomright,3)
    # Layered timber front with a right-facing side to add depth.
    front=pg.Rect(110,97,200,91)
    pg.draw.polygon(surf,(65,50,36),[(310,99),(348,85),(348,176),(310,188)])
    pg.draw.rect(surf,logs,front)
    for row in range(0,8):
        y=front.y+row*12
        pg.draw.line(surf,(61,45,31),(front.x,y),(front.right,y),3)
        pg.draw.line(surf,(184,137,84),(front.x+3,y+3),(front.right-4,y+3),2)
        if row%2==0:
            pg.draw.circle(surf,(52,43,31),(front.x+6,y+6),3)
            pg.draw.circle(surf,(52,43,31),(front.right-7,y+6),3)
    pg.draw.line(surf,(195,154,97),front.topleft,front.bottomleft,5)
    pg.draw.line(surf,(65,50,34),front.topright,front.bottomright,4)
    # Gabled/thatch roof shape. Silhouette changes for named variant profiles.
    peak=34 if roof_type in ('steep','front_gable') else 53
    eave=78 if roof_type=='overhang' else 90
    left=92 if roof_type in ('overhang','porch') else 103
    right=327 if roof_type in ('overhang','porch') else 317
    if roof_type=='side_gable':
        roofpts=[(left,57),(300,57),(355,94),(right,108),(left-7,108)]
        ridge=((left+12,61),(296,61))
    else:
        roofpts=[(left,eave),(202,peak),(right,eave),(right+13,100),(202,peak+15),(left-13,100)]
        ridge=((202,peak+5),(202,peak+15))
    pg.draw.polygon(surf,roof,roofpts)
    pg.draw.lines(surf,(38,31,26),True,roofpts,5)
    pg.draw.line(surf,(199,162,107),ridge[0],ridge[1],3)
    # Visible thatch shingles; avoid noisy fine-detail textures.
    for row in range(3):
        ry=66+row*11
        if roof_type=='side_gable':ry=70+row*10
        pg.draw.line(surf,(188,154,103),(132,ry),(286,ry),2)
    if roof_type=='patched':
        pg.draw.polygon(surf,(126,115,97),[(243,65),(277,74),(266,85),(233,78)])
        pg.draw.line(surf,(52,43,39),(232,79),(267,86),2)
    if roof_type=='moss' or accent=='ivy':
        for i in range(7):
            x=118+((i*43)%185)
            y=75+(i%3)*5
            pg.draw.ellipse(surf,(63,105,67),(x,y,24,12))
            pg.draw.circle(surf,(103,142,81),(x+8,y+2),4)
    if roof_type=='dormer':
        pg.draw.polygon(surf,(92,72,55),[(175,64),(204,43),(232,64),(227,79),(179,79)])
        pg.draw.rect(surf,(187,153,97),(193,63,18,15))
    if roof_type=='chimney':
        pg.draw.rect(surf,(100,75,61),(274,31,31,43))
        pg.draw.rect(surf,(147,106,83),(272,27,35,7))
        pg.draw.ellipse(surf,(157,158,145,110),(279,14,18,12))
    if roof_type=='porch':
        pg.draw.polygon(surf,(101,78,49),[(87,113),(310,113),(339,135),(97,135)])
        for px in (99,332):
            pg.draw.line(surf,(164,128,80),(px,128),(px,192),6)
    if accent in ('braces','carved') or trim=='crossbeam':
        for x in (118,292):
            pg.draw.line(surf,(198,152,94),(x,107),(x+23,133),4)
            pg.draw.line(surf,(198,152,94),(x+23,107),(x,133),4)
    # Door position is the authoritative style field used by construction.
    doorx={'left':133,'center':199,'right':266}[door]
    if accent=='raised_sill':door_y=132
    else:door_y=124
    dr=pg.Rect(doorx-17,door_y,34,64)
    pg.draw.rect(surf,(50,37,31),dr)
    pg.draw.rect(surf,(127,91,58),dr.inflate(-5,-5))
    pg.draw.line(surf,(58,44,31),(doorx,dr.y+5),(doorx,dr.bottom-4),3)
    pg.draw.circle(surf,(217,174,103),(dr.right-8,dr.centery+8),3)
    # Single glazed window and wooden shutters, away from the door.
    winx=260 if door!='right' else 143
    wr=pg.Rect(winx-14,132,28,27)
    pg.draw.rect(surf,(51,42,33),wr.inflate(6,6))
    pg.draw.rect(surf,(123,174,164),wr)
    pg.draw.line(surf,(58,53,43),(wr.centerx,wr.top),(wr.centerx,wr.bottom),3)
    pg.draw.line(surf,(58,53,43),(wr.x,wr.centery),(wr.right,wr.centery),3)
    if accent=='shutters':
        pg.draw.rect(surf,(176,125,75),(wr.x-11,wr.y,8,wr.height))
        pg.draw.rect(surf,(176,125,75),(wr.right+3,wr.y,8,wr.height))
    if accent=='weathered':
        for px,py in ((135,123),(176,165),(285,155)):
            pg.draw.line(surf,(67,55,50),(px,py),(px+12,py+3),2)
    if roof_type=='porch' or accent=='hearth':
        pg.draw.ellipse(surf,(136,117,91),(doorx-24,198,48,10))
    # Lighting rim / grass weeds
    for i in range(12):
        gx=58+(i*37)%313;gy=212+(i*11)%23
        pg.draw.line(surf,(78,106,61),(gx,gy),(gx-2,gy-5),2)
    return surf


def present_style_selector(term, style, index, count):
    pg=term.pg;screen=term.screen
    x,y,w,h,cx,cy,cw=term._floating_feature_shell(
        'homestead_styles','BUILD','LOG CABIN','Select an exterior design before positioning its blueprint.')
    panel=pg.Rect(cx,cy,cw,max(90,y+h-143-cy))
    pg.draw.rect(screen,(24,32,31),panel,border_radius=6)
    pg.draw.rect(screen,term._theme['edge'],panel,1,border_radius=6)
    inset=max(38,min(62,cw//8))
    artrect=pg.Rect(panel.left+inset,panel.y+10,panel.w-inset*2,panel.h-20)
    artwork=None
    # Match the top-down south-facing art used by the placed-world renderer.
    from worldseed.ui.homestead_art import cabin_asset_path,topdown_cabin_asset_path
    resolved=topdown_cabin_asset_path(style['id'],0) or cabin_asset_path(style['id'])
    if resolved is not None:
        artwork=term._load_sprite(resolved,max(40,artrect.w),max(40,artrect.h),smooth=True)
    if artwork is None:
        key=('log-cabin-preview-v2',style['id'])
        artwork=term._sprite_cache.get(key)
        if artwork is None:
            artwork=render_cabin_style(pg,style)
            term._sprite_cache[key]=artwork
        ratio=min(artrect.w/max(1,artwork.get_width()),artrect.h/max(1,artwork.get_height()))
        artwork=pg.transform.smoothscale(artwork,(max(1,int(artwork.get_width()*ratio)),max(1,int(artwork.get_height()*ratio))))
    screen.blit(artwork,artwork.get_rect(center=artrect.center))
    pg.draw.rect(screen,(143,119,77),artrect,1,border_radius=3)
    size=44
    _button(term,(panel.x+8,panel.centery-size//2,size,size),'‹','UI_ACTION:cabin_prev')
    _button(term,(panel.right-size-8,panel.centery-size//2,size,size),'›','UI_ACTION:cabin_next')
    tag=style['name'].split(' — ')[-1]
    title_y=panel.bottom+11
    _label(term,tag,(x+w//2,title_y+7),large=True,centered=True,width=cw-10)
    countline=f'{index+1:02d} / {count:02d}  ·  {style.get("roof_detail","Thatch").replace("_"," ").title()} roof  ·  {style.get("door_position","Center").title()} door'
    _label(term,countline,(x+w//2,title_y+30),centered=True,color=term._theme['muted'],width=cw-10)
    base_y=y+h-84
    _button(term,(cx,base_y,154,33),'Other structures','UI_ACTION:cabin_other')
    _button(term,(cx+cw-187,base_y,187,33),'Place blueprint  →','UI_ACTION:cabin_place',prominent=True)
    term._draw_floating_footer(x,y,w,h,'← / → browse styles  ·  Enter selects  ·  Drag title  ·  Esc closes')
    pg.display.flip();term.clock.tick(120)


def present_blueprint_depot(term,data):
    pg=term.pg;screen=term.screen;site=data['site']
    x,y,w,h,cx,cy,cw=term._floating_feature_shell(
        'homestead_depot','CONSTRUCTION','LOG CABIN BLUEPRINT',
        f"{data['style_name']}  ·  {data['stage_name']}")
    total=sum(n for _,_,have,n,carry in data['materials'])
    stocked=sum(have for _,_,have,n,carry in data['materials'])
    # Do not claim construction progress from deposited stock alone.
    box=pg.Rect(cx,cy,cw,51)
    pg.draw.rect(screen,(35,43,40),box,border_radius=6)
    pg.draw.rect(screen,term._theme['edge'],box,1,border_radius=6)
    _label(term,f'PROJECT STAGE {site["stage"]} / 4',(box.x+12,box.y+8),color=term._theme['accent'])
    _label(term,f'DEPOSITED {stocked} / {total}',(box.right-12,box.y+9),width=box.w//2,
           color=term._theme['text'])
    gauge=pg.Rect(box.x+12,box.bottom-15,box.w-24,7)
    pg.draw.rect(screen,(69,72,69),gauge,border_radius=3)
    fill=pg.Rect(gauge.x,gauge.y,int(gauge.w*stocked/max(1,total)),gauge.h)
    if fill.w:pg.draw.rect(screen,(153,141,92),fill,border_radius=3)
    row_top=box.bottom+10
    # A two-column material ledger keeps icon, stock and deposit actions
    # readable even in the minimum supported 800x520 game window.
    gap=8
    card_w=(cw-gap)//2
    rh=max(49,min(64,(y+h-119-row_top-12)//3))
    for index,(iid,label,have,need,carried) in enumerate(data['materials']):
        col=index%2;row=index//2
        r=pg.Rect(cx+col*(card_w+gap),row_top+row*(rh+6),card_w,rh)
        pg.draw.rect(screen,(32,39,39),r,border_radius=5)
        pg.draw.rect(screen,(71,81,76),r,1,border_radius=5)
        icon_size=max(31,min(42,rh-8))
        icon=pg.Rect(r.x+6,r.centery-icon_size//2,icon_size,icon_size)
        pg.draw.rect(screen,(48,56,52),icon,border_radius=4)
        term._draw_item_icon(iid,icon,scale=.90)
        # Actual inventory icons are preferred over bespoke faux material art.
        label_x=icon.right+9
        buttons_w=92
        label_width=max(60,r.right-label_x-buttons_w-11)
        _label(term,label,(label_x,r.y+6),width=label_width)
        line_text=f'{have}/{need} supplied  ·  {carried} carried'
        _label(term,line_text,(label_x,r.bottom-20),color=term._theme['muted'],
               width=max(70,r.right-label_x-9))
        if site['stage']<4 and have<need:
            right=r.right-6
            _button(term,(right-55,r.y+5,55,25),'ALL',
                    'UI_ACTION:depot_item_all:'+iid,enabled=carried>0)
            _button(term,(right-92,r.y+5,33,25),'+1',
                    'UI_ACTION:depot_item_one:'+iid,enabled=carried>0)
        else:
            _label(term,'✓' if have>=need else '–',(r.right-19,r.y+9),
                   color=term._theme['accent'] if have>=need else term._theme['muted'])
    controls_top=min(y+h-143,row_top+3*(rh+6)+4)
    info=str(data.get('notice','')).strip()
    if info:
        _label(term,info,(cx,controls_top),color=term._theme['accent'],width=cw)
    else:
        _label(term,str(data.get('thatch_hint','')),(cx,controls_top),
               color=term._theme['muted'],width=cw)
    by=y+h-91
    if data.get('confirm_cancel'):
        _label(term,'Return all deposited materials and remove the blueprint?',(cx,by-22),
               color=term._theme['danger'],width=cw)
        _button(term,(cx,by,126,33),'Keep site','UI_ACTION:depot_cancel_back')
        _button(term,(cx+136,by,190,33),'Confirm removal','UI_ACTION:depot_cancel_confirm',prominent=True)
    elif site['stage']<4:
        _button(term,(cx,by,144,33),'Deposit carried','UI_ACTION:depot_all',prominent=True)
        _button(term,(cx+153,by,170,33),'Build next stage','UI_ACTION:depot_build')
        _button(term,(cx+cw-126,by,126,33),'Remove site','UI_ACTION:depot_cancel')
    else:
        _label(term,'Cabin construction complete.',(cx,by+8),color=term._theme['accent'])
    term._draw_floating_footer(x,y,w,h,'Click materials to deposit  ·  Drag title  ·  Resize corner  ·  Esc closes')
    pg.display.flip();term.clock.tick(120)
