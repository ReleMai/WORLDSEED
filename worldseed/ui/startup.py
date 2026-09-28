from __future__ import annotations
from dataclasses import dataclass
import random
from pathlib import Path
import json, sqlite3, time, secrets
from worldseed.config import DEFAULT_SAVE_DIR, ENGINE_VERSION
from worldseed.ui.widgets import MenuRow, select_menu, prompt_text, panel, view_text

@dataclass(frozen=True, slots=True)
class StartSelection:
    path: Path
    is_new: bool
    world_name: str | None = None
    seed_hex: str | None = None
    player_name: str | None = None
    origin: str | None = None
    build: dict | None = None
    player_sex: str = "male"
    player_sprite_index: int = 0

@dataclass(frozen=True, slots=True)
class SaveSummary:
    path: Path
    world_name: str
    player_name: str
    origin: str
    clock_minute: int
    turn: int
    last_saved: float
    engine_version: str
    valid: bool = True
    error: str = ""

    @property
    def day(self)->int:return max(1,self.clock_minute//1440+1)
    @property
    def saved_label(self)->str:
        if not self.last_saved:return "unknown"
        return time.strftime('%Y-%m-%d %H:%M',time.localtime(self.last_saved))


def safe_name(name:str)->str:
    return ''.join(ch if ch.isalnum() or ch in '-_' else '_' for ch in name.strip()) or 'world'


def _meta(conn,key,default=None):
    row=conn.execute('SELECT value_json FROM world_meta WHERE key=?',(key,)).fetchone()
    if not row:return default
    try:return json.loads(row[0])
    except Exception:return default


def inspect_save(path:Path)->SaveSummary:
    try:
        conn=sqlite3.connect(f'file:{path.as_posix()}?mode=ro',uri=True)
        try:
            world=str(_meta(conn,'world_name',path.stem));turn=int(_meta(conn,'turn',0) or 0)
            engine=str(_meta(conn,'engine_version','unknown'));last=float(_meta(conn,'last_saved_at',0) or 0)
            player=str(_meta(conn,'player_name','Wanderer'));origin=str(_meta(conn,'player_origin','wanderer'))
            row=conn.execute('SELECT payload_json FROM sim_state WHERE slot=1').fetchone()
            clock=480
            if row:
                try:
                    raw=json.loads(row[0]);clock=int(raw.get('clock_minute',480));player=str(raw.get('player_name',player));origin=str(raw.get('player_origin',origin))
                except Exception:pass
            if not last:
                try:last=path.stat().st_mtime
                except OSError:last=0
            return SaveSummary(path,world,player,origin,clock,turn,last,engine)
        finally:conn.close()
    except Exception as exc:
        return SaveSummary(path,path.stem,'?','?',0,0,0,'?',False,str(exc))


def scan_saves()->list[SaveSummary]:
    DEFAULT_SAVE_DIR.mkdir(parents=True,exist_ok=True)
    rows=[inspect_save(p) for p in DEFAULT_SAVE_DIR.glob('*.db')]
    return sorted(rows,key=lambda s:(s.valid,s.last_saved),reverse=True)


def _load_menu(term,saves:list[SaveSummary])->StartSelection|None:
    if not saves:
        view_text(term,panel('LOAD GAME',['No saved worlds exist yet.'],min(70,term.size()[0]-2)))
        return None
    labels=[]
    for s in saves:
        if not s.valid:labels.append((str(s.path),f'[DAMAGED] {s.path.stem} — {s.error[:40]}'))
        else:labels.append((str(s.path),f'{s.world_name} | {s.player_name} | Day {s.day} | {s.saved_label}'))
    key=select_menu(term,'LOAD GAME',labels,subtitle='Choose a persistent world. Back returns to the main menu.')
    if not key:return None
    chosen=next(s for s in saves if str(s.path)==key)
    if not chosen.valid:
        view_text(term,panel('SAVE ERROR',[chosen.error],min(84,term.size()[0]-2)))
        return None
    return StartSelection(chosen.path,False)


ATTRIBUTE_DEFS = [
    ('strength','Strength','Raises melee force, carrying/physical-work performance, and tasks that depend on raw power.'),
    ('agility','Agility','Improves movement control, reactions, dodging and precise weapon handling.'),
    ('endurance','Endurance','Supports health, stamina, swimming/travel efficiency and resistance to exposure or exhaustion.'),
    ('intellect','Intellect','Improves learning, research, crafting judgment and technical or scholarly work.'),
    ('perception','Perception','Improves sight radius, tracking, observation, ranged awareness and noticing environmental details.'),
    ('will','Will','Improves pain/fear resistance, concentration under pressure and demanding magical actions.'),
]
SKILL_DEFS = [
    ('athletics','Athletics','Travel and physical endurance.'),
    ('swimming','Swimming','Efficient swimming; Endurance reduces stamina costs.'),
    ('survival','Survival','Living off the land and reading danger.'),
    ('foraging','Foraging','Plants, berries and useful wild materials.'),
    ('woodcutting','Woodcutting','Felling and processing trees.'),
    ('mining','Mining','Rock, ore and underground excavation.'),
    ('hunting','Hunting','Tracking and harvesting animals.'),
    ('fishing','Fishing','Reading water, presenting bait, and landing fish with hand, spear, rod, or net.'),
    ('melee','Melee','Close combat with weapons or fists.'),
    ('shield','Shield','Active blocking, coverage control and stamina-efficient guarding.'),
    ('crafting','Crafting','General fabrication and material work.'),
    ('medicine','Medicine','Treating wounds and illness.'),
    ('scholarship','Scholarship','Reading, research and historical study.'),
    ('persuasion','Persuasion','Conversation, trust and gathering information.'),
    ('trading','Trading','Valuation, bargaining and market awareness.'),
    ('stealth','Stealth','Quiet movement, concealment and theft under observation.'),
    ('naturalism','Naturalism','Ecology, species signs and population estimates.'),
    ('arcana','Arcana','Recognizing and manipulating magical laws.'),
]
TALENT_DEFS = [
    ('hardy','Hardy',2,'More health and better resistance to exposure.'),
    ('keen_senses','Keen Senses',1,'Slightly wider sight and better field observation.'),
    ('quick_study','Quick Study',1,'Improved literacy and learning.'),
    ('woodsman','Woodsman',1,'Better timber recovery from felled trees.'),
    ('stonewise','Stonewise',1,'Better recovery from mined rock and ore.'),
    ('field_medic','Field Medic',1,'More effective basic treatment.'),
    ('haggler','Haggler',1,'Small advantage when buying and selling.'),
    ('arcane_attuned','Arcane Attuned',2,'Greater sensitivity to magical phenomena.'),
]
ATTRIBUTE_POINTS=12
SKILL_POINTS=24
TALENT_POINTS=5
ATTRIBUTE_BASE=5
ATTRIBUTE_MAX=10
SKILL_MAX=10


def _random_build()->dict:
    rng=random.SystemRandom()
    attrs={k:ATTRIBUTE_BASE for k,_,_ in ATTRIBUTE_DEFS};remaining=ATTRIBUTE_POINTS
    while remaining:
        choices=[k for k in attrs if attrs[k]<ATTRIBUTE_MAX]
        k=rng.choice(choices);attrs[k]+=1;remaining-=1
    skills={k:0 for k,_,_ in SKILL_DEFS};remaining=SKILL_POINTS
    # Spend in small clusters so random people have strengths instead of 1 in everything.
    focus=rng.sample(list(skills),k=min(5,len(skills)))
    while remaining:
        weighted=focus*3+list(skills)
        k=rng.choice(weighted)
        if skills[k]>=SKILL_MAX:continue
        skills[k]+=1;remaining-=1
    talents=[];remaining=TALENT_POINTS
    choices=list(TALENT_DEFS);rng.shuffle(choices)
    for key,_,cost,_ in choices:
        if cost<=remaining and rng.randrange(100)<72:
            talents.append(key);remaining-=cost
        if remaining<=0:break
    while remaining:
        viable=[row for row in TALENT_DEFS if row[0] not in talents and row[2]<=remaining]
        if not viable:break
        row=rng.choice(viable);talents.append(row[0]);remaining-=row[2]
    return {'attributes':attrs,'skills':skills,'talents':sorted(talents)}


def _allocate_values(term,title,defs,values,pool,max_value,min_value=0)->dict|None:
    selected=0
    while True:
        spent=sum(max(0,int(values[k])-min_value) for k,_,_ in defs)
        remaining=pool-spent
        cols,_=term.size();width=max(58,min(96,cols-2));body=[f'Points remaining: {remaining}','']
        for i,(key,label,hint) in enumerate(defs):
            marker='>' if i==selected else ' '
            body.append(f'{marker} {label:<18} {values[key]:>2}/{max_value}')
            if i==selected:body.append(f'    {hint}')
        body+=['','↑/↓ select   → +1   ← -1   Enter continue when pool is spent   Esc back']
        allocator=getattr(term,'present_allocation',None)
        page_start=0
        if callable(allocator):
            from worldseed.ui.widgets import MenuRow
            rows=[MenuRow(key,f'{label}: {values[key]}/{max_value}',hint) for key,label,hint in defs]
            page_start=allocator(title,rows,selected,remaining)
        else:term.present(panel(title,body,width))
        k=term.read_key();kl=k.lower() if len(k)==1 else k
        if k.startswith(('UI_PLUS:','UI_MINUS:')):
            selected=int(k.split(':')[1]);kl='RIGHT' if k.startswith('UI_PLUS:') else 'LEFT'
        elif k.startswith(('UI_SELECT:','UI_HOVER:')):
            selected=page_start+int(k.split(':')[1]);continue
        elif k in ('PGUP','PGDN'):
            selected=max(0,min(len(defs)-1,selected+(-1 if k=='PGUP' else 1)*term.menu_page_size()));continue
        if k=='ESC':return None
        if kl in ('UP',):selected=(selected-1)%len(defs);continue
        if kl in ('DOWN',):selected=(selected+1)%len(defs);continue
        key=defs[selected][0]
        if kl in ('RIGHT',):
            if remaining>0 and values[key]<max_value:values[key]+=1
        elif kl in ('LEFT',):
            if values[key]>min_value:values[key]-=1
        elif k in ('\r','\n'):
            if remaining==0:return values


def _allocate_talents(term,selected_keys:list[str])->list[str]|None:
    idx=0;selected=set(selected_keys)
    while True:
        spent=sum(cost for key,_,cost,_ in TALENT_DEFS if key in selected);remaining=TALENT_POINTS-spent
        cols,_=term.size();width=max(64,min(100,cols-2));body=[f'Talent points remaining: {remaining}','']
        for i,(key,label,cost,hint) in enumerate(TALENT_DEFS):
            marker='>' if i==idx else ' ';flag='[X]' if key in selected else '[ ]'
            body.append(f'{marker} {flag} {label:<20} cost {cost}')
            if i==idx:body.append(f'    {hint}')
        body+=['','↑/↓ select   Enter buy   ← remove   Esc back', 'When all talent points are spent, Enter on an owned talent continues.']
        if getattr(term,'mouse_ui',False):
            rows=[
                MenuRow(
                    key,
                    f"{'Selected' if key in selected else 'Buy'} — {label} ({cost} points)",
                    hint,
                )
                for key,label,cost,hint in TALENT_DEFS
            ]
            if remaining==0:rows.append(MenuRow('__continue__','Continue','Finish character creation with the selected talents.'))
            choice=select_menu(term,'TALENTS',rows,subtitle=f'{remaining} points left. Select a talent to see exactly what it changes.')
            if choice is None:return None
            if choice=='__continue__':return sorted(selected)
            cost=next(c for key,_,c,_ in TALENT_DEFS if key==choice)
            if choice in selected:selected.remove(choice)
            elif cost<=remaining:selected.add(choice)
            continue
        term.present(panel('TALENTS',body,width))
        k=term.read_key();kl=k.lower() if len(k)==1 else k
        if k=='ESC':return None
        if kl in ('UP',):idx=(idx-1)%len(TALENT_DEFS);continue
        if kl in ('DOWN',):idx=(idx+1)%len(TALENT_DEFS);continue
        key,label,cost,_=TALENT_DEFS[idx]
        if kl in ('LEFT',):
            selected.discard(key);continue
        if kl in ('RIGHT','\r','\n'):
            if key not in selected and cost<=remaining:selected.add(key)
            elif key in selected and remaining==0 and k in ('\r','\n'):return sorted(selected)
        if remaining==0 and k in ('\r','\n'):return sorted(selected)


def _point_buy(term)->dict|None:
    attrs={k:ATTRIBUTE_BASE for k,_,_ in ATTRIBUTE_DEFS}
    skills={k:0 for k,_,_ in SKILL_DEFS}
    a=_allocate_values(term,'ATTRIBUTES',ATTRIBUTE_DEFS,attrs,ATTRIBUTE_POINTS,ATTRIBUTE_MAX,ATTRIBUTE_BASE)
    if a is None:return None
    sk=_allocate_values(term,'SKILLS',SKILL_DEFS,skills,SKILL_POINTS,SKILL_MAX,0)
    if sk is None:return None
    talents=_allocate_talents(term,[])
    if talents is None:return None
    return {'attributes':a,'skills':sk,'talents':talents}


def _build_summary(build:dict)->list[str]:
    attrs=build['attributes'];skills=build['skills'];talents=set(build['talents'])
    rows=['ATTRIBUTES', '  '+', '.join(f'{label} {attrs[key]}' for key,label,_ in ATTRIBUTE_DEFS), '', 'SKILLS']
    trained=[f'{label} {skills[key]}' for key,label,_ in SKILL_DEFS if skills[key]>0]
    rows += ['  '+', '.join(trained) if trained else '  None']
    rows += ['', 'TALENTS', '  '+(', '.join(label for key,label,_,_ in TALENT_DEFS if key in talents) or 'None')]
    return rows


PLAYER_SPRITE_LABELS = [
    'Look 01', 'Look 02', 'Look 03', 'Look 04', 'Look 05',
    'Look 06', 'Look 07', 'Look 08', 'Look 09', 'Look 10',
]


def _sex_menu(term)->str|None:
    return select_menu(term,'NEW CHARACTER',[('male','Male'),('female','Female')],subtitle='Choose the sex used for your survivor sprite set.')


def _sprite_menu(term, sex:str)->int|None:
    options=[(str(i),f'{PLAYER_SPRITE_LABELS[i]} — {sex.title()} sprite {i+1:02d}') for i in range(10)]
    choice=select_menu(term,'SURVIVOR APPEARANCE',options,subtitle='Choose one of the 10 available survivor looks for this character.')
    return None if choice is None else int(choice)


def _appearance_menu(term)->tuple[str,int]|None:
    presenter=getattr(term,'present_sprite_gallery',None)
    if not callable(presenter):
        sex=_sex_menu(term)
        if sex is None:return None
        sprite_index=_sprite_menu(term,sex)
        if sprite_index is None:return None
        return sex,sprite_index
    sex='male';selected=0
    while True:
        presenter(
            'SURVIVOR APPEARANCE',
            sex=sex,
            selected=selected,
            labels=PLAYER_SPRITE_LABELS,
            subtitle='Click Male or Female, choose a look, then Continue.',
            footer='Click a look • Click Continue • Back cancels',
        )
        k=term.read_key();kl=k.lower() if len(k)==1 else k
        if k.startswith('UI_APPEARANCE:'):
            selected=max(0,min(9,int(k.split(':')[1])));continue
        if k.startswith('UI_SEX:'):
            sex=k.split(':')[1];continue
        if k=='ESC':return None
        if kl in ('\r','\n',' '):return sex,selected
        if kl in ('\t','q','e'):
            sex='female' if sex=='male' else 'male'
            continue
        if kl in ('LEFT',):selected=max(0,selected-1);continue
        if kl in ('RIGHT',):selected=min(9,selected+1);continue
        if kl in ('UP',):selected=max(0,selected-5);continue
        if kl in ('DOWN',):selected=min(9,selected+5);continue


def _random_character_menu(term)->dict|None:
    build=_random_build()
    while True:
        term.present(panel('RANDOM CHARACTER',_build_summary(build),min(100,term.size()[0]-2),'Continue accepts • R rerolls • Back cancels'))
        if getattr(term,'mouse_ui',False):
            term._ui_navigation(confirm=True,extra=('Reroll','r'));term.pg.display.flip()
        k=term.read_key();kl=k.lower() if len(k)==1 else k
        if k=='ESC':return None
        if kl=='r':build=_random_build();continue
        if kl in ('RIGHT','\r','\n',' '):return build


def new_game_wizard(term)->StartSelection|None:
    world=prompt_text(term,'NEW WORLD','Name this world:',default='New World',max_len=40,allow_blank=False)
    if world is None:return None
    seed=prompt_text(term,'NEW WORLD','World seed (blank = random):',default='',max_len=64,allow_blank=True)
    if seed is None:return None
    if not seed:seed=secrets.token_hex(16)
    player=prompt_text(term,'NEW CHARACTER','Character name:',default='Wanderer',max_len=36,allow_blank=False)
    if player is None:return None
    appearance=_appearance_menu(term)
    if appearance is None:return None
    sex,sprite_index=appearance
    while True:
        mode=select_menu(term,'CHARACTER CREATION',[
            ('build','Build Character — spend attribute, skill and talent pools'),
            ('random','Random Character — roll a complete build using the same budgets'),
        ],subtitle='There are no classes. Your strengths come from the points you spend.')
        if not mode:return None
        build=_point_buy(term) if mode=='build' else _random_character_menu(term)
        if build is None:continue

        overview=getattr(term,'present_creation_overview',None)
        if callable(overview):
            attrs=[
                {'name':label,'value':build['attributes'][key],'description':hint}
                for key,label,hint in ATTRIBUTE_DEFS
            ]
            skills=[
                {'name':label,'value':build['skills'][key],'description':hint}
                for key,label,hint in SKILL_DEFS if build['skills'][key]>0
            ]
            talents=[
                {'name':label,'description':hint}
                for key,label,_,hint in TALENT_DEFS if key in set(build['talents'])
            ]
            overview('character',{
                'name':player,'sex':sex,'sprite_index':sprite_index,
                'sprite_label':PLAYER_SPRITE_LABELS[sprite_index],
                'attributes':attrs,'skills':skills,'talents':talents,
            })
            k=term.read_key()
            if k=='ESC':continue

        start_mode=select_menu(term,'STARTING LOCATION',[
            MenuRow('wilderness','Wilderness — standard survival start','Begin away from organized settlement life and establish yourself through exploration and survival.'),
            MenuRow('village','Village — settlement-focused start','Begin beside a generated settlement so homes, professions, trade and civilization are immediately accessible.'),
        ],subtitle='Starting location changes only where this survivor begins; the seeded world remains the same.')
        if not start_mode:continue

        summary=[f'World: {world}',f'Seed: {seed}',f'Character: {player}',f'Sex: {sex.title()}',f'Sprite: {PLAYER_SPRITE_LABELS[sprite_index]}','']+_build_summary(build)+['']
        while True:
            if callable(overview):
                overview('world',{
                    'world_name':world,'seed':seed,'start_mode':start_mode,
                    'character_name':player,'sex':sex,'sprite_label':PLAYER_SPRITE_LABELS[sprite_index],
                    'attributes':[
                        {'name':label,'value':build['attributes'][key]}
                        for key,label,_ in ATTRIBUTE_DEFS
                    ],
                    'talents':[
                        label for key,label,_,_ in TALENT_DEFS if key in set(build['talents'])
                    ],
                })
            else:
                term.present(panel('BEGIN WORLD',summary,min(96,term.size()[0]-2),'Continue begins • Back cancels'))
            k=term.read_key();kl=k.lower() if len(k)==1 else k
            if k=='ESC':break
            if kl in ('RIGHT','\r','\n',' '):
                path=DEFAULT_SAVE_DIR/f'{safe_name(world)}.db'
                if path.exists():path=DEFAULT_SAVE_DIR/f'{safe_name(world)}_{secrets.token_hex(2)}.db'
                return StartSelection(path,True,world,seed.encode().hex(),player,start_mode,build,sex,sprite_index)
        # back from world overview returns to build/random choice


def main_menu(term)->StartSelection|None:
    while True:
        saves=scan_saves();valid=[s for s in saves if s.valid]
        rows=[]
        if valid:
            c=valid[0];rows.append(('continue',f'Continue — {c.world_name} / {c.player_name} — Day {c.day}'))
        rows += [('new','New Game — create a world and character')]
        if saves:rows.append(('load',f'Load Game — {len(saves)} saved world(s)'))
        rows += [('help','Quick Start / controls'),('quit','Quit WORLDSEED')]
        choice=select_menu(term,f'WORLDSEED {ENGINE_VERSION}',rows,allow_escape=False,subtitle='A living-world sandbox. Click an option to begin.')
        if choice=='continue':return StartSelection(valid[0].path,False)
        if choice=='new':
            sel=new_game_wizard(term)
            if sel:return sel
        elif choice=='load':
            sel=_load_menu(term,saves)
            if sel:return sel
        elif choice=='help':
            view_text(term,panel('QUICK START',["WASD moves through the world.","Click Actions for nearby interactions.","Click World for journals, information and systems.","ESC opens pause at gameplay root and goes back inside menus.","Click Inventory, Crafting, Build, Health or Map in the HUD.","Names, places and records are learned through exploration rather than revealed globally."],min(90,term.size()[0]-2)))
        elif choice=='quit':return None
