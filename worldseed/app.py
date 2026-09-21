from __future__ import annotations
from dataclasses import asdict, dataclass
from pathlib import Path
import secrets,sys,time
from worldseed.config import AUTOSAVE_TURNS,DATA_DIR,DEFAULT_SAVE_DIR,ENGINE_VERSION,RESOURCEGEN_VERSION,INITIAL_PREGEN_CHUNK_RADIUS,LOAD_WARM_CHUNK_RADIUS,CHUNK_SIZE
from worldseed.content.registry import ContentRegistry
from worldseed.content.mods import ModManager, ModError
from worldseed.core.coords import WorldPos, split_world
from worldseed.entities.components import Inventory,PlayerControlled,Position,Renderable,Vitals
from worldseed.entities.store import EntityStore
from worldseed.persistence.database import WorldDatabase
from worldseed.sim.commands import *
from worldseed.sim.engine import Simulation
from worldseed.systems.state import LivingWorldState, pos_key
from worldseed.systems.resources import ResourceSystem
from worldseed.ui.renderer import Renderer
from worldseed.ui.screens import *
from worldseed.ui.terminal import Terminal


def _present_game_frame(term, ctx, renderer, message: str = '', cursor=None) -> None:
    presenter = getattr(term, 'present_game', None)
    if callable(presenter):
        presenter(ctx.registry, ctx.world, ctx.entities, ctx.sim, ctx.player_id, message, cursor)
    else:
        w, h = term.size()
        term.present(renderer.render(ctx.world, ctx.entities, ctx.sim, ctx.player_id, w, h, message, cursor=cursor))

from worldseed.ui.widgets import select_menu, view_text
from worldseed.ui.pointer import WindowCloseRequested
from worldseed.ui.session import NavigationStack, RouteState
from worldseed.ui.layout import screen_width
from worldseed.ui.startup import StartSelection, main_menu
from worldseed.ui.navigation import *
from worldseed.ui.router import DIRECTIONS as DIRECTION_KEYS, DIRECT_MENUS as MENU_KEYS, classify_key
from worldseed.world.generator import WorldGenerator
from worldseed.world.hydrology import HydrologyGenerator
from worldseed.world.world import World
PLAYER_ID=1
UI_BACK='__UI_BACK__'
@dataclass(slots=True)
class GameContext:
    db:WorldDatabase;registry:ContentRegistry;world:World;entities:EntityStore;sim:Simulation;player_id:int

def _safe(name:str)->str:return ''.join(ch if ch.isalnum() or ch in '-_' else '_' for ch in name.strip()) or 'world'

def _new_world_prompt(term:Terminal):
    from worldseed.ui.startup import new_game_wizard
    return new_game_wizard(term)

def _choose_world(term:Terminal):
    return main_menu(term)

def _find_spawn(world:World,origin:str='wanderer',resources:ResourceSystem|None=None)->WorldPos:
    """Find a connected, zero-supply-capable start without exhaustive scanning.

    Generator v4 uses broad climate/elevation fields, so the origin may sit in a
    large ocean. We first sample terrain directly (which does not materialize
    chunks), then perform expensive resource/connectivity checks for only the
    nearest promising land regions.
    """
    from collections import deque

    preferred={'core:grass','core:forest','core:sand','core:scrub','core:tundra','core:berry_thicket'}

    def terrain_id(x:int,y:int)->str:
        return world.generator.terrain_at(WorldPos(x,y,0))

    def terrain_passable(x:int,y:int)->bool:
        tid=terrain_id(x,y)
        td=world.registry.terrains.get(tid)
        return bool(td and td.passable)

    def tree_climate_possible(x:int,y:int,tid:str|None=None)->bool:
        tid=tid or terrain_id(x,y);fields=world.generator.sample_fields(WorldPos(x,y,0))
        for rd in world.registry.resources.values():
            if 'tree' not in rd.tags or (rd.terrains and tid not in rd.terrains):continue
            if rd.min_temp<=fields.temperature<=rd.max_temp and rd.min_moisture<=fields.moisture<=rd.max_moisture:return True
        return False

    def open_cell(q:WorldPos)->bool:
        return world.is_passable(q) and (resources is None or not resources.blocks_movement(q))

    # Sparse direct-generator sampling. 24-cell spacing means every point in the
    # search square is within roughly 12 cells of a sampled center, while avoiding
    # the catastrophic sparse chunk materialization RC9 incurred.
    coarse=[]
    step=24;limit=576
    for y in range(-limit,limit+1,step):
        for x in range(-limit,limit+1,step):
            tid=terrain_id(x,y)
            if tid in preferred:
                # Empty-hands progression needs eventual timber. Strongly favor
                # climate/terrain combinations that can naturally support trees.
                tree_penalty=0 if tree_climate_possible(x,y,tid) else 240
                biome_bonus=0 if tid in {'core:grass','core:forest'} else 8
                coarse.append((max(abs(x),abs(y))+biome_bonus+tree_penalty,abs(x)+abs(y),x,y))
    if not coarse:return WorldPos(0,0,0)

    offsets=sorted(((abs(dx)+abs(dy),dx,dy) for dy in range(-12,13) for dx in range(-12,13)))

    def refine(cx:int,cy:int)->WorldPos|None:
        fallback=None
        for _,dx,dy in offsets:
            x,y=cx+dx,cy+dy;tid=terrain_id(x,y)
            if tid not in preferred or not terrain_passable(x,y):continue
            open_terrain=sum(terrain_passable(x+ox,y+oy) for ox,oy in ((1,0),(-1,0),(0,1),(0,-1)))
            if open_terrain<3:continue
            p=WorldPos(x,y,0)
            if resources is not None and resources.blocks_movement(p):continue
            if fallback is None:fallback=p
            if tree_climate_possible(x,y,tid):return p
        return fallback

    def opportunity_audit(p:WorldPos):
        primitive=set();edible=False;tree=False;water=False
        if resources is None:return primitive,False,True,True
        for y in range(p.y-14,p.y+15):
            for x in range(p.x-14,p.x+15):
                q=WorldPos(x,y,0)
                if 'water' in world.tile_at(q).terrain.tags:water=True
                fv=resources.feature_at(q)
                if not fv or fv.stage!='mature':continue
                rd=resources.registry.resources.get(fv.feature_id)
                if not rd:continue
                ys=set(rd.yields)
                if not rd.required_tool_tag:
                    if 'core:stone' in ys:primitive.add('stone')
                    if 'core:stout_branch' in ys:primitive.add('branch')
                    if 'core:brush' in ys:primitive.add('fiber')
                    if any(resources.registry.items.get(i) and resources.registry.items[i].nutrition>0 for i in ys):edible=True
                if 'tree' in rd.tags:tree=True
        if not tree:
            # Timber can be somewhat farther away because the player reaches it
            # only after crafting the first chopping tool.
            for y in range(p.y-28,p.y+29,2):
                for x in range(p.x-28,p.x+29,2):
                    fv=resources.feature_at(WorldPos(x,y,0))
                    if not fv or fv.stage!='mature':continue
                    rd=resources.registry.resources.get(fv.feature_id)
                    if rd and 'tree' in rd.tags:tree=True;break
                if tree:break
        return primitive,edible,tree,water

    def reachable(p:WorldPos,radius:int=14)->int:
        if not open_cell(p):return 0
        seen={(p.x,p.y)};q=deque([p])
        while q:
            cur=q.popleft()
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                nx,ny=cur.x+dx,cur.y+dy
                if (nx,ny) in seen or max(abs(nx-p.x),abs(ny-p.y))>radius:continue
                np=WorldPos(nx,ny,0)
                if not open_cell(np):continue
                seen.add((nx,ny));q.append(np)
        return len(seen)

    fallback=None;best=None;best_score=-10**9;viable=0
    # Nearest 56 land samples are ample even for broad climate regions and keep
    # world creation bounded. Most worlds resolve in the first few candidates.
    for _,__,cx,cy in sorted(coarse)[:160]:
        p=refine(cx,cy)
        if p is None:continue
        if fallback is None:fallback=p
        primitive,edible,tree,water=opportunity_audit(p)
        if not {'stone','branch','fiber'}.issubset(primitive) or not tree:continue
        reach=reachable(p,14)
        if reach<450:continue
        tid=world.tile_at(p).terrain_id
        score=reach + (90 if tid in {'core:grass','core:forest'} else 0) + (45 if water else 0) + (30 if edible else 0) - (abs(p.x)+abs(p.y))//8
        if score>best_score:best_score=score;best=p
        viable+=1
        if viable>=5:return best
    return best or fallback or WorldPos(0,0,0)

def _pregen_bounds(center:WorldPos,radius_chunks:int)->tuple[int,int,int,int]:
    key,_,_=split_world(center);r=max(0,int(radius_chunks))
    x0=(key.x-r)*CHUNK_SIZE;y0=(key.y-r)*CHUNK_SIZE
    x1=(key.x+r+1)*CHUNK_SIZE-1;y1=(key.y+r+1)*CHUNK_SIZE-1
    return x0,y0,x1,y1

def _relocate_spawn_after_hydrology(world:World,pos:WorldPos,resources:ResourceSystem)->WorldPos:
    """Keep a new character off a newly projected deep river/lake cell.

    The original site selection intentionally runs against the cheap base climate
    field before hydrology planning. Once the prepared physical geography exists,
    this bounded deterministic repair chooses the nearest dry/passable cell.
    """
    def good(q:WorldPos)->bool:
        tid=world.generator.terrain_at(q);td=world.registry.terrains.get(tid)
        return bool(td and td.passable and 'water' not in td.tags and not resources.blocks_movement(q))
    if good(pos):return pos
    candidates=[]
    for radius in range(1,33):
        for dy in range(-radius,radius+1):
            for dx in range(-radius,radius+1):
                if max(abs(dx),abs(dy))!=radius:continue
                q=WorldPos(pos.x+dx,pos.y+dy,pos.z)
                if good(q):candidates.append((abs(dx)+abs(dy),dy,dx,q))
        if candidates:return min(candidates,key=lambda row:(row[0],row[1],row[2]))[-1]
    return pos

def _load_context(sel,progress=None,prepare_world:bool=True)->GameContext:
    def emit(phase:str,value:float,detail:str='')->None:
        if progress:progress(phase,max(0.0,min(1.0,float(value))),detail)
    emit('Reading world definition',0.01,'Loading content and generation rules')
    if isinstance(sel,StartSelection):
        path,is_new,name,seed_hex,player_name,origin,build=sel.path,sel.is_new,sel.world_name,sel.seed_hex,sel.player_name,sel.origin,sel.build
    else:
        path,is_new,name,seed_hex=sel;player_name=None;origin=None;build=None
    mod_manager=ModManager(Path.cwd()/"mods")
    try:
        mod_order=mod_manager.resolve()
    except ModError as exc:
        raise RuntimeError(f"Mod configuration error: {exc}") from exc
    reg=ContentRegistry.load(DATA_DIR,[m.path/"data" for m in mod_order if (m.path/"data").exists()])
    emit('Opening seeded world',0.03,'Creating save database' if is_new else 'Opening persistent world')
    if is_new:db=WorldDatabase.create(path,name,seed_hex)
    else:db=WorldDatabase.open(path);seed_hex=str(db.get_meta('world_seed'))
    seed=bytes.fromhex(seed_hex)
    try:gen_version=int(db.get_meta('worldgen_version'))
    except KeyError:gen_version=2
    world=World(WorldGenerator(seed,reg,version=gen_version),reg,db,auto_hydrology=False)
    hydrology=HydrologyGenerator(world.generator,db) if gen_version>=5 else None
    # Resource generation is versioned separately from terrain. RC10 intentionally
    # migrates pre-versioned RC9 saves to the safer v3 placement model while
    # keeping their terrain/worldgen version pinned, so coastlines and biomes do
    # not move underneath an existing character.
    try:resource_version=int(db.get_meta('resourcegen_version'))
    except KeyError:
        resource_version=RESOURCEGEN_VERSION
        db.set_meta('resourcegen_version',resource_version);db.connection.commit()
    world.resourcegen_version=resource_version
    entities=EntityStore();player=entities.spawn(preferred_id=PLAYER_ID)
    pp=db.load_component(player,'Position');ip=db.load_component(player,'Inventory');vp=db.load_component(player,'Vitals')
    state=LivingWorldState.from_dict(db.load_sim_state())
    if is_new:
        state.player_name=(player_name or 'Wanderer').strip() or 'Wanderer';state.player_origin='custom';state.player_sex=(getattr(sel,'player_sex','male') or 'male').lower();state.player_sprite_index=int(getattr(sel,'player_sprite_index',0) or 0)
        state.player_crafting_discovery_enabled=True
        if build:
            state.player_attributes={str(k):int(v) for k,v in build.get('attributes',{}).items()}
            state.player_skills={str(k):int(v) for k,v in build.get('skills',{}).items()}
            state.player_talents=sorted({str(x) for x in build.get('talents',[])})
        intellect=state.player_attributes.get('intellect',5);scholar=state.player_skills.get('scholarship',0)
        state.player_literacy=max(20,min(100,28+intellect*6+scholar*3+(10 if 'quick_study' in state.player_talents else 0)))
    spawn_resources=ResourceSystem(state,reg,seed,world)
    if pp is None:
        emit('Selecting viable starting region',0.06,'Scanning deterministic climate, terrain and primitive resources')
        pos=_find_spawn(world,state.player_origin,spawn_resources)
    else:
        pos=WorldPos(int(pp['x']),int(pp['y']),int(pp.get('z',0)))

    if is_new and prepare_world:
        radius=int(INITIAL_PREGEN_CHUNK_RADIUS)
        if hydrology is not None:
            bounds=_pregen_bounds(pos,radius)
            def hydro_progress(i,total,detail):emit('Resolving watersheds',0.08+0.14*(i/max(1,total)),detail)
            hydrology.prepare_world_bounds(*bounds,persist=True,progress=hydro_progress)
            world.generator.attach_hydrology(hydrology)
            pos=_relocate_spawn_after_hydrology(world,pos,spawn_resources)
        def terrain_progress(i,total,detail):emit('Carving rivers / shaping terrain',0.22+0.33*(i/max(1,total)),f'{detail}  •  {i}/{total} chunks')
        world_stats=world.pre_generate(pos,radius,terrain_progress,persist=True)
        def resource_progress(i,total,detail):emit('Placing natural resources',0.55+0.35*(i/max(1,total)),f'{detail}  •  {i}/{total} chunks')
        resource_stats=spawn_resources.pre_generate(pos,radius,resource_progress,persist=True)
        db.set_meta('pregen_complete',True);db.set_meta('pregen_radius_chunks',radius)
        db.set_meta('pregen_center',[pos.x//32,pos.y//32]);db.set_meta('pregen_surface_chunks',world_stats['total'])
        db.set_meta('pregen_resource_chunks',resource_stats['total']);db.connection.commit()
    elif not is_new and prepare_world:
        warm=int(LOAD_WARM_CHUNK_RADIUS)
        if hydrology is not None:
            bounds=_pregen_bounds(pos,warm)
            def hydro_warm(i,total,detail):emit('Loading watershed plan',0.08+0.16*(i/max(1,total)),detail)
            hydrology.prepare_world_bounds(*bounds,persist=True,progress=hydro_warm)
            world.generator.attach_hydrology(hydrology)
        def warm_terrain(i,total,detail):emit('Warming nearby terrain',0.24+0.28*(i/max(1,total)),f'{detail}  •  {i}/{total}')
        world.warm_region(pos,warm,warm_terrain)
        def warm_resources(i,total,detail):emit('Warming nearby resources',0.52+0.30*(i/max(1,total)),f'{detail}  •  {i}/{total}')
        spawn_resources.pre_generate(pos,warm,warm_resources,persist=True)
    elif hydrology is not None:
        # Tool/test contexts that skip preparation still get a deterministic
        # geography provider, but normal gameplay prepares caches before entry.
        world.generator.attach_hydrology(hydrology)
    # RC5 introduced blocking natural-resource features.  An older save may
    # have been standing on a coordinate that now deterministically contains
    # a mature tree/boulder.  Preserve the character's valid saved position by
    # treating that one feature as already cleared instead of trapping them.
    if not is_new and spawn_resources.blocks_movement(pos):
        state.resource_depletion[pos_key(pos.x,pos.y,pos.z)]=state.clock_minute
    # RC7 rule: a new character begins with nothing. No class kit, money,
    # food, tools, medical supplies, or container is granted. The opening
    # survival loop must be bootstrapped entirely from the world.
    if ip is None:inv=Inventory({})
    else:inv=Inventory({str(k):int(v) for k,v in ip.get('items',{}).items()})
    if vp is None:
        endurance=state.player_attributes.get('endurance',5);bonus=10 if 'hardy' in state.player_talents else 0
        max_hp=80+endurance*4+bonus;vit=Vitals(hp=max_hp,max_hp=max_hp)
    else:vit=Vitals(**{k:int(v) for k,v in vp.items() if k in Vitals.__dataclass_fields__})
    entities.add(player,Position(pos));entities.add(player,inv);entities.add(player,vit);entities.add(player,PlayerControlled());entities.add(player,Renderable('@',state.player_name))
    emit('Starting living-world simulation',0.92,'Realizing nearby ecology, settlements and history')
    sim=Simulation(world,entities,reg,int(db.get_meta('turn')),state,seed,resources_system=spawn_resources);sim._discover(pos)
    sim.loaded_mods=[f"{m.id}@{m.version}" for m in mod_order]
    sim.mod_hash=mod_manager.content_hash(mod_order) if mod_order else 'none'
    if is_new:sim._message(f'{state.player_name} enters the world.')
    else:
        mins=sim.lod.offline_minutes(time.time())
        if mins:
            summary=sim.advance_offline(mins,sim.state.offline_policy)
            days=max(1,summary.get('days',0));sim._message(f"Time passed while you were away: {days} day{'s' if days!=1 else ''}.")
        else:sim._message('You return to the same persistent world.')
    emit('World ready',1.0,f'Spawn {pos.x}, {pos.y}  •  prepared exploration area loaded')
    sim.state.last_offline_wall_time=time.time();return GameContext(db,reg,world,entities,sim,player)
def _save(ctx:GameContext)->None:
    p=ctx.entities.get(ctx.player_id,Position).value;inv=ctx.entities.get(ctx.player_id,Inventory);v=ctx.entities.get(ctx.player_id,Vitals);ctx.sim.state.last_offline_wall_time=time.time()
    if ctx.db.path.exists() and ctx.db.path.stat().st_size>0:
        ctx.db.backup(3)
    ctx.db.set_meta('last_saved_at',time.time());ctx.db.set_meta('player_name',ctx.sim.state.player_name);ctx.db.set_meta('player_origin',ctx.sim.state.player_origin);ctx.db.set_meta('player_sex',ctx.sim.state.player_sex);ctx.db.set_meta('player_sprite_index',int(ctx.sim.state.player_sprite_index))
    ctx.db.save_state(turn=ctx.sim.turn,tile_deltas=ctx.world.drain_dirty_tiles(),player_id=ctx.player_id,position=p,inventory=inv.items,vitals=asdict(v),sim_state=ctx.sim.state.to_dict())

def _select(terminal:Terminal,title:str,rows:list[tuple[str,str]],allow_escape=True,**kwargs)->str|None:
    return select_menu(terminal,title,rows,allow_escape=allow_escape,**kwargs)

def _view_text(term:Terminal,text:str,**kwargs)->None:
    view_text(term,text,**kwargs)

def _direction(term:Terminal)->tuple[int,int]|None:
    k=select_menu(term,'DIRECTION',[('UP','North'),('RIGHT','East'),('DOWN','South'),('LEFT','West')],subtitle='Choose an adjacent tile.')
    return DIRECTION_KEYS.get(k)
def _gather_action(ctx:GameContext,term:Terminal)->str:
    """Harvest targeting uses the map itself, never a second list menu."""
    sim=ctx.sim;p=sim.player_pos
    offsets=[(0,0),(0,-1),(0,1),(-1,0),(1,0)]
    candidates=[(dx,dy) for dx,dy in offsets if sim.resources.is_harvestable(p.moved(dx,dy))]
    if not candidates:return 'Nothing harvestable is within reach.'
    if len(candidates)==1:
        dx,dy=candidates[0];sim.execute(GatherCommand(ctx.player_id,dx,dy));return sim.log[-1].message if sim.log else ''
    renderer=Renderer(ctx.registry);cursor=p
    while True:
        target_desc=sim.resources.description(cursor) if sim.resources.is_harvestable(cursor) else 'Nothing harvestable'
        msg=f'HARVEST — {target_desc}. Click a nearby tile and Confirm; Esc cancels.'
        _present_game_frame(term,ctx,renderer,msg,cursor);k=term.read_key()
        if k.startswith('UI_WORLD:'):
            _,x,y=k.split(':');nxt=WorldPos(int(x),int(y),p.z)
            if abs(nxt.x-p.x)+abs(nxt.y-p.y)<=1:cursor=nxt
            continue
        if k in ('ESC','q','Q'):return UI_BACK
        if k in ('\r','\n'):
            rdx,rdy=cursor.x-p.x,cursor.y-p.y
            if abs(rdx)+abs(rdy)<=1 and sim.resources.is_harvestable(cursor):
                sim.execute(GatherCommand(ctx.player_id,rdx,rdy));return sim.log[-1].message if sim.log else ''
            continue
        direction=DIRECTION_KEYS.get(k.lower() if len(k)==1 else k)
        if direction:
            nxt=cursor.moved(*direction);rdx,rdy=nxt.x-p.x,nxt.y-p.y
            if abs(rdx)+abs(rdy)<=1:cursor=nxt

def _talk_action(ctx:GameContext,term:Terminal)->str:
    sim=ctx.sim;p=sim.player_pos
    nearby=[]
    for n in sim.state.npcs.values():
        dist=abs(n.x-p.x)+abs(n.y-p.y)
        if n.alive and n.z==p.z and dist<=1:
            label=n.name if n.uid in sim.known_npc_ids() else 'Stranger'
            nearby.append((n.uid,n.x-p.x,n.y-p.y,f'{label} — {n.occupation if n.uid in sim.known_npc_ids() else "unknown occupation"}'))
    if not nearby:return 'Nobody is close enough to talk to.'
    if len(nearby)==1:
        _,dx,dy,_=nearby[0]
    else:
        uid=_select(term,'TALK TO',[(uid,label) for uid,_,_,label in nearby])
        if not uid:return UI_BACK
        _,dx,dy,_=next(row for row in nearby if row[0]==uid)
    sim.execute(TalkCommand(ctx.player_id,dx,dy));return sim.log[-1].message if sim.log else ''

def _near_market(sim:Simulation):
    p=sim.player_pos;c=[s for s in sim.state.settlements.values() if abs(s.x-p.x)+abs(s.y-p.y)<=10 and s.uid in sim.known_settlement_ids()];return min(c,key=lambda s:abs(s.x-p.x)+abs(s.y-p.y),default=None)

def _look_mode(ctx:GameContext,term:Terminal)->None:
    sim=ctx.sim;renderer=Renderer(ctx.registry);cursor=sim.player_pos
    while True:
        known=sim.is_discovered(cursor)
        if known:
            tile=sim.world.tile_at(cursor);msg=f'LOOK {cursor.x},{cursor.y},z{cursor.z}: {tile.terrain.name}. Enter=details, ESC=exit.'
        else:msg=f'LOOK {cursor.x},{cursor.y},z{cursor.z}: unexplored. Enter=details, ESC=exit.'
        _present_game_frame(term,ctx,renderer,msg,cursor);k=term.read_key()
        if k.startswith('UI_WORLD:'):
            _,x,y=k.split(':');nxt=WorldPos(int(x),int(y),sim.player_pos.z)
            if max(abs(nxt.x-sim.player_pos.x),abs(nxt.y-sim.player_pos.y))<=35:cursor=nxt
            continue
        if k in ('ESC','q','Q'):return
        if k in ('\r','\n'):
            if known:_view_text(term,look_screen(sim,screen_width(term.size()[0],118),cursor))
            continue
        direction=DIRECTION_KEYS.get(k.lower() if len(k)==1 else k)
        if direction:
            nxt=cursor.moved(*direction)
            # Looking is local and cannot force realization of arbitrary distant space.
            if max(abs(nxt.x-sim.player_pos.x),abs(nxt.y-sim.player_pos.y))<=35:cursor=nxt

def _nearby_water(sim:Simulation)->bool:
    p=sim.player_pos
    for dx,dy in ((0,0),(1,0),(-1,0),(0,1),(0,-1)):
        q=p.moved(dx,dy);tile=sim.world.tile_at(q);fluid=sim.environment.fluid_at(q)
        if 'water' in tile.terrain.tags or (fluid and fluid.fluid=='water' and fluid.amount>10):return True
    return False

def _process_carcass_menu(ctx:GameContext,term:Terminal)->str:
    sim=ctx.sim;reg=ctx.registry;rows=[]
    for c in sim.processing.nearby_carcasses(sim.player_pos,1):
        sp=reg.species.get(c.species_id);state=[]
        if c.skinned:state.append('skinned')
        if c.butchered:state.append('butchered')
        if c.deboned:state.append('deboned')
        rows.append((c.uid,f'{sp.name if sp else c.species_id} — quality {c.quality}%'+(f' — {", ".join(state)}' if state else '')))
    uid=_select(term,'CARCASSES WITHIN REACH',rows)
    if not uid:return UI_BACK
    c=sim.state.carcasses[uid];sp=reg.species.get(c.species_id);actions=[]
    if not c.skinned:actions.append(('skin','Skin — remove hide before butchering for the best hide'))
    if not c.butchered:actions.append(('butcher','Butcher — separate meat, organs and fat'))
    if c.butchered and not c.deboned:actions.append(('debone','Debone — recover bones and sinew; finishes carcass'))
    act=_select(term,(sp.name if sp else 'CARCASS').upper(),actions)
    if not act:return UI_BACK
    sim.execute(ProcessCarcassCommand(ctx.player_id,uid,act));return sim.log[-1].message if sim.log else ''

def _preservation_menu(ctx:GameContext,term:Terminal)->str:
    sim=ctx.sim;inv=ctx.entities.get(ctx.player_id,Inventory);reg=ctx.registry
    specs=[
        ('dry_meat','Dry game meat','Drying Rack','2 raw game meat → 2 dried meat (~12h)'),
        ('dry_small_game','Dry small game','Drying Rack','2 small-game meat → 1 dried meat (~10h)'),
        ('dry_hide','Dry scraped hide','Drying Rack','1 scraped hide → 1 rawhide (~12h)'),
        ('tan_hide','Bark-tan scraped hide','Tanning Frame','1 scraped hide + 2 bark → 1 leather (~24h)'),
    ]
    rows=[]
    for pid,name,station,desc in specs:
        rows.append((pid,f'{name} | {station} | {desc}'))
    pick=_select(term,'PRESERVE / PROCESS OVER TIME',rows)
    if not pick:return UI_BACK
    sim.execute(StartProcessingCommand(ctx.player_id,pick));return sim.log[-1].message if sim.log else ''

def _cooking_menu(ctx:GameContext,term:Terminal)->str:
    sim=ctx.sim;reg=ctx.registry;inv=ctx.entities.get(ctx.player_id,Inventory);stations=sim.building.nearby_station_ids(sim.player_pos);water=_nearby_water(sim) or inv.count('core:clean_water')>0
    methods=[]
    for m in reg.cooking_methods.values():
        station=reg.structures[m.station].name if m.station in reg.structures else m.station
        ready=m.station in stations and (not m.cookware or inv.count(m.cookware)>0) and (not m.requires_water or water)
        note=[]
        if m.station not in stations:note.append(station)
        if m.cookware and inv.count(m.cookware)<=0:note.append(reg.items[m.cookware].name)
        if m.requires_water and not water:note.append('water')
        methods.append((m.id,f'[{'READY' if ready else 'NEEDS'}] {m.name} — {m.min_ingredients}-{m.max_ingredients} ingredients — {m.minutes}m'+(f' — needs {", ".join(note)}' if note else '')))
    mid=_select(term,'COOKING METHOD',methods)
    if not mid:return UI_BACK
    method=reg.cooking_methods[mid];selected=[]
    while True:
        preview=sim.food.preview(mid,selected) if selected else {'satiety':0,'hydration':0,'calories':0,'protein':0,'carbs':0,'fat':0,'fiber':0,'groups':{}}
        header=f'{len(selected)}/{method.max_ingredients} ingredients | satiety {preview["satiety"]} | kcal {preview["calories"]} | P {preview["protein"]} C {preview["carbs"]} F {preview["fat"]}'
        rows=[]
        if len(selected)>=method.min_ingredients:rows.append(('__cook__',f'COOK NOW — {sim.food.meal_name(mid,selected)}'))
        counts={}
        for iid in selected:counts[iid]=counts.get(iid,0)+1
        for iid,n in sorted(inv.items.items()):
            item=reg.items.get(iid)
            if not item or n-counts.get(iid,0)<=0 or not set(item.tags).intersection(method.allowed_tags):continue
            rows.append((iid,f'Add {item.name} — have {n-counts.get(iid,0)} | kcal {item.calories} | {"/".join(item.food_groups) or "ingredient"}'))
        if selected:rows.append(('__remove__','Remove last ingredient'))
        pick=_select(term,'COOK — '+header,rows)
        if not pick:return UI_BACK
        if pick=='__remove__':selected.pop();continue
        if pick=='__cook__':
            sim.execute(CookMealCommand(ctx.player_id,mid,tuple(selected)));return sim.log[-1].message if sim.log else ''
        selected.append(pick)
        if len(selected)>=method.max_ingredients:
            ok,why=sim.food.can_cook(mid,selected,inv,stations,water)
            if ok:
                sim.execute(CookMealCommand(ctx.player_id,mid,tuple(selected)));return sim.log[-1].message if sim.log else ''

def _rest_menu(ctx:GameContext,term:Terminal)->str:
    comfort,s,sd=ctx.sim.building.best_rest_structure(ctx.sim.player_pos)
    where=sd.name if sd else 'the ground'
    rows=[('60',f'Rest 1 hour — {where}'),('240',f'Rest 4 hours — {where}'),('480',f'Sleep 8 hours — {where}')]
    pick=_select(term,'REST / SLEEP',rows)
    if not pick:return UI_BACK
    ctx.sim.execute(RestCommand(ctx.player_id,int(pick)));return ctx.sim.log[-1].message if ctx.sim.log else ''

def _hunt_action(ctx:GameContext,term:Terminal)->str:
    sim=ctx.sim;reg=ctx.registry;inv=ctx.entities.get(ctx.player_id,Inventory);weapons=[reg.items[i] for i,n in inv.items.items() if n>0 and i in reg.items and reg.items[i].range>1 and reg.items[i].weapon_damage>0]
    if not weapons:return 'You have no ranged weapon.'
    max_range=max(w.range for w in weapons);p=sim.player_pos;renderer=Renderer(reg);cursor=p
    while True:
        c=next((c for c in sim.state.creatures.values() if c.hp>0 and (c.x,c.y,c.z)==(cursor.x,cursor.y,cursor.z)),None)
        desc=(reg.species[c.species_id].name if c else 'No animal')
        _present_game_frame(term,ctx,renderer,f'AIM: {desc} | range {abs(cursor.x-p.x)+abs(cursor.y-p.y)}/{max_range} | Enter fire | Esc cancel',cursor)
        k=term.read_key();low=k.lower() if len(k)==1 else k
        if k.startswith('UI_WORLD:'):
            _,x,y=k.split(':');n=WorldPos(int(x),int(y),p.z)
            if abs(n.x-p.x)+abs(n.y-p.y)<=max_range:cursor=n
            continue
        if low in ('ESC','q'):return UI_BACK
        if low in DIRECTION_KEYS:
            dx,dy=DIRECTION_KEYS[low];n=cursor.moved(dx,dy)
            if abs(n.x-p.x)+abs(n.y-p.y)<=max_range:cursor=n
            continue
        if low in ('ENTER',' ','\r','\n'):
            if not c:continue
            sim.execute(RangedAttackCommand(ctx.player_id,c.uid));return sim.log[-1].message if sim.log else ''

def _action_palette(ctx:GameContext,term:Terminal)->str:
    """Primary gameplay action hub with retained navigation state.

    ESC from a feature returns to its action category, then to the action root,
    then to gameplay.  Successful world-changing actions close the palette.
    """
    nav=NavigationStack(RouteState('actions','Actions'))
    submenus={
        'interact':ACTION_INTERACT,'survival':ACTION_SURVIVAL,'work':ACTION_WORK,
        'combat':ACTION_COMBAT,'world':ACTION_WORLD,
    }
    while True:
        route=nav.current
        if route.route_id=='actions':
            choice=_stack_menu(term,nav,ACTION_ROOT,subtitle='Esc returns to gameplay.')
            if choice is None:return ''
            if choice=='__BACK__':continue
            if choice=='wait':
                ctx.sim.execute(WaitCommand(ctx.player_id,10));return ctx.sim.log[-1].message if ctx.sim.log else ''
            nav.push(RouteState(f'action-group:{choice}',choice.title(),payload={'group':choice}))
            continue
        if route.route_id.startswith('action-group:'):
            group=route.payload['group'];action=_stack_menu(term,nav,submenus[group])
            if action is None:return ''
            if action=='__BACK__':continue
            if action=='l':_look_mode(ctx,term);continue
            if action=='farm':
                result=_farm_menu(ctx,term)
                if result==UI_BACK:continue
                return ctx.sim.log[-1].message if ctx.sim.log else ''
            if action=='down':ctx.sim.execute(VerticalMoveCommand(ctx.player_id,-1));return ctx.sim.log[-1].message if ctx.sim.log else ''
            if action=='up':ctx.sim.execute(VerticalMoveCommand(ctx.player_id,1));return ctx.sim.log[-1].message if ctx.sim.log else ''
            if action=='g':
                result=_gather_action(ctx,term);
                if result==UI_BACK:continue
                return result
            if action=='shaft':
                ctx.sim.execute(ExcavateShaftCommand(ctx.player_id));return ctx.sim.log[-1].message if ctx.sim.log else ''
            if action=='drink':ctx.sim.execute(DrinkCommand(ctx.player_id));return ctx.sim.log[-1].message if ctx.sim.log else ''
            if action=='rest':
                result=_rest_menu(ctx,term);
                if result==UI_BACK:continue
                return result
            if action=='cook':
                result=_cooking_menu(ctx,term);
                if result==UI_BACK:continue
                return result
            if action=='process':
                result=_process_carcass_menu(ctx,term);
                if result==UI_BACK:continue
                return result
            if action=='preserve':
                result=_preservation_menu(ctx,term);
                if result==UI_BACK:continue
                return result
            if action=='hunt':
                result=_hunt_action(ctx,term);
                if result==UI_BACK:continue
                return result
            if action=='talk':
                result=_talk_action(ctx,term)
                if result==UI_BACK:continue
                return result
            if action=='p':ctx.sim.execute(PickupCommand(ctx.player_id));return ctx.sim.log[-1].message if ctx.sim.log else ''
            result=_handle_menu(ctx,term,action)
            if result==UI_BACK:
                continue
            return result
        if not nav.back():return ''

def _farm_menu(ctx:GameContext,term:Terminal)->str:
    sim=ctx.sim
    while True:
        action=_select(term,'FARMING',[
            ('till','Till current tile — requires a digging/tilling tool'),('plant','Plant crop / review crop requirements'),('harvest','Harvest current crop'),
            ('water','Irrigate current crop — requires nearby water'),('fertilize','Apply bone meal'),
        ])
        if not action:return UI_BACK
        if action=='till':sim.till();sim.execute(WaitCommand(ctx.player_id,10))
        elif action=='plant':
            cid=_select(term,'PLANT',[(c.id,f'{c.name} — seeds {ctx.entities.get(ctx.player_id,Inventory).count(c.seed_item)} | {c.growth_hours//24}d | N/P/K {c.nitrogen}/{c.phosphorus}/{c.potassium} | seasons {"/".join(c.seasons)}') for c in ctx.registry.crops.values()])
            if cid:sim.execute(PlantCommand(ctx.player_id,cid))
        elif action=='harvest':sim.execute(HarvestCommand(ctx.player_id))
        elif action=='water':sim.irrigate();sim.execute(WaitCommand(ctx.player_id,10))
        elif action=='fertilize':sim.execute(FertilizeCommand(ctx.player_id))
        return ctx.sim.log[-1].message if ctx.sim.log else ''

def _stack_menu(term: Terminal, nav: NavigationStack, rows, *, subtitle: str = '', presentation: str = '', presentation_data: dict | None = None) -> str | None:
    """Render the current route as a retained menu.

    ESC pops exactly one route. At the navigation root it returns None so the
    owning feature can dismiss back to gameplay.
    """
    current = nav.current
    parent = ' > '.join(r.title for r in nav._stack[:-1]) if nav.depth > 1 else ''
    choice = select_menu(term, current.title, rows, subtitle=subtitle,
                         breadcrumb=parent, state=current, presentation=presentation,
                         presentation_data=presentation_data)
    if choice is None:
        if nav.back():
            return '__BACK__'
        return None
    return choice


def _stack_view(term: Terminal, nav: NavigationStack, text: str, *, presentation: str = '', presentation_data: dict | None = None) -> None:
    """Show a detail route and always restore its exact parent on ESC/Enter."""
    current = nav.current
    parent = ' > '.join(r.title for r in nav._stack[:-1]) if nav.depth > 1 else ''
    view_text(term, text, title=current.title, breadcrumb=parent, state=current, presentation=presentation, presentation_data=presentation_data)
    nav.pop()


def _settlement_rows(sim: Simulation) -> list[tuple[str, str]]:
    p = sim.player_pos
    return [(town.uid, f'{town.name} | pop {town.population} | stress {town.food_stress} | r({town.region_x},{town.region_y})')
            for town in sorted(sim.known_settlements(), key=lambda s:(abs(s.x-p.x)+abs(s.y-p.y),s.name))]

def _known_history(sim: Simulation):
    known=sim.known_event_ids()
    return [e for e in sim.state.history if e.uid in known]

def _known_artifacts(sim: Simulation):
    owners={'player'}|sim.known_npc_ids()|sim.known_settlement_ids()
    return [a for a in sim.state.artifacts.values() if a.owner in owners or any(str(row.get('owner','')) in owners for row in a.provenance)]

def _known_books(sim: Simulation):
    owners={'player'}|sim.known_npc_ids()|sim.known_settlement_ids()
    # Libraries are knowledge locations inside already discovered settlements.
    library_ids={lib.uid for lib in sim.state.libraries.values() if lib.settlement_id in sim.known_settlement_ids()}
    return [b for b in sim.state.books.values() if b.owner in owners or b.owner in library_ids]

def _known_graves(sim: Simulation):
    discovered=set(sim.state.discovered_tiles);known_people=sim.known_npc_ids()
    return [g for g in sim.state.graves.values() if g.person_uid in known_people or pos_key(g.x,g.y,g.z) in discovered]

def _known_outbreaks(sim: Simulation):
    known=sim.known_settlement_ids();return [(oid,d) for oid,d in sim.state.diseases.items() if d.settlement_id in known]

def _ledger_rows(sim: Simulation, category: str) -> list[tuple[str, str]]:
    if category == 'people':
        rows=[]
        for n in sorted(sim.known_npcs(),key=lambda n:(not n.alive,n.name,n.uid)):
            town=sim.state.settlements.get(n.settlement_id);town_name=town.name if town and town.uid in sim.known_settlement_ids() else 'unknown settlement'
            rows.append((n.uid,f'{n.name} | age {n.age} | {n.occupation} | {"alive" if n.alive else "dead"} | {town_name}'))
        return rows
    if category == 'factions':
        return [(f.uid,f'{f.name} | power {f.power} | treasury {f.treasury}c | wars {sum(x in sim.known_faction_ids() for x in f.at_war)}') for f in sorted(sim.known_factions(),key=lambda f:f.name)]
    if category == 'routes':
        known=sim.known_settlement_ids();rows=[]
        for r in sorted((x for x in sim.state.trade_routes.values() if x.origin in known and x.destination in known),key=lambda r:(r.danger,-r.traffic,r.uid)):
            a=sim.state.settlements.get(r.origin);b=sim.state.settlements.get(r.destination)
            rows.append((r.uid,f'{a.name if a else "?"} -> {b.name if b else "?"} | danger {r.danger} | traffic {r.traffic}'))
        return rows
    if category == 'artifacts':
        return [(a.uid,f'{a.name} | q{a.quality} cond {a.condition}% | owner {a.owner if a.owner=="player" else "known owner"}') for a in sorted(_known_artifacts(sim),key=lambda a:(a.name,a.uid))]
    if category == 'books':
        return [(b.uid,f'{b.title} | {b.author} | {b.knowledge} | known copy') for b in sorted(_known_books(sim),key=lambda b:(b.title,b.uid))]
    if category == 'sites':
        known=sim.known_site_ids();return [(d.uid,f'{d.name} | chunk {d.chunk_x},{d.chunk_y},z{d.z} | {"CLEARED" if d.cleared else "active"}') for d in sorted((x for x in sim.state.dungeon_sites.values() if x.uid in known),key=lambda d:(d.z,d.name))]
    if category == 'events':
        return [(e.uid,f'Y{e.minute//(1440*120)+1} [{e.event_type}] s{e.salience} {e.summary}') for e in sorted(_known_history(sim),key=lambda e:(e.minute,e.uid),reverse=True)]
    if category == 'graves':
        return [(g.uid,f'{g.grave_type}: {g.person_name} | ({g.x},{g.y},z{g.z})') for g in sorted(_known_graves(sim),key=lambda g:(g.person_name,g.uid))]
    if category == 'outbreaks':
        rows=[]
        for oid,d in sorted(_known_outbreaks(sim),key=lambda kv:(-kv[1].infected,kv[0])):
            town=sim.state.settlements.get(d.settlement_id);ddef=sim.registry.diseases.get(d.disease_id)
            rows.append((oid,f'{ddef.name if ddef else d.name or d.disease_id} | {town.name if town else "known settlement"} | active {d.infected} | deaths {d.deaths} | {d.policy}'))
        return rows
    return []

def _ledger_counts(sim: Simulation) -> dict[str,int]:
    return {
        'people':len(sim.known_npc_ids()), 'factions':len(sim.known_faction_ids()),
        'routes':len(_ledger_rows(sim,'routes')), 'artifacts':len(_known_artifacts(sim)),
        'books':len(_known_books(sim)), 'sites':len(sim.known_site_ids()),
        'events':len(_known_history(sim)), 'graves':len(_known_graves(sim)),
        'outbreaks':len(_known_outbreaks(sim)),
    }

def _ledger_detail(sim: Simulation, category: str, uid: str, width: int) -> str:
    funcs = {
        'people': npc_detail_screen, 'factions': faction_detail_screen,
        'routes': route_detail_screen, 'artifacts': artifact_detail_screen,
        'books': book_detail_screen, 'sites': dungeon_detail_screen,
        'events': event_detail_screen, 'graves': grave_detail_screen,
        'outbreaks': disease_detail_screen,
    }
    return funcs[category](sim, uid, width)


def _world_ledger(ctx: GameContext, term: Terminal, nav: NavigationStack | None = None) -> None:
    """Stack-driven ledger. ESC from a detail returns to its list; another ESC
    returns to the ledger categories; another returns to the caller/gameplay.
    """
    sim = ctx.sim
    own_stack = nav is None
    if nav is None:
        nav = NavigationStack(RouteState('ledger', 'World Ledger'))
    elif nav.current.route_id != 'ledger':
        nav.push(RouteState('ledger', 'World Ledger'))
    counts=_ledger_counts(sim)
    categories = [
        ('people',f'Discovered people ({counts["people"]}) — identity, family, relationships, memories'),
        ('factions',f'Known factions ({counts["factions"]}) — rulers, wars, claims, relations'),
        ('routes',f'Known trade routes ({counts["routes"]}) — waypoints, danger, cargo economics'),
        ('artifacts',f'Known artifacts ({counts["artifacts"]}) — components, condition, provenance'),
        ('books',f'Known books ({counts["books"]}) — authors, facts, language, ownership'),
        ('sites',f'Discovered historical sites ({counts["sites"]}) — locks, occupants, timeline'),
        ('events',f'Known historical events ({counts["events"]}) — subjects, causes, salience'),
        ('graves',f'Discovered graves / tombs ({counts["graves"]}) — linked historical people'),
        ('outbreaks',f'Known outbreaks ({counts["outbreaks"]}) — pathogens, cases, policies'),
    ]
    while True:
        route = nav.current
        if route.route_id == 'ledger':
            choice = _stack_menu(term, nav, categories)
            if choice is None:
                return
            if choice == '__BACK__':
                if not own_stack and nav.current.route_id != 'ledger':
                    return
                continue
            nav.push(RouteState(f'ledger-list:{choice}', choice.replace('_',' ').title(), payload={'category':choice}))
            continue
        if route.route_id.startswith('ledger-list:'):
            category = route.payload['category']
            choice = _stack_menu(term, nav, _ledger_rows(sim, category))
            if choice is None:
                return
            if choice == '__BACK__':
                continue
            nav.push(RouteState(f'ledger-detail:{category}:{choice}', 'Record Detail', payload={'category':category,'uid':choice}))
            _stack_view(term, nav, _ledger_detail(sim, category, choice, screen_width(term.size()[0],118)))
            continue
        # Defensive recovery: a foreign route should not trap the user.
        if not nav.back():
            return


def _console_view_text(ctx: GameContext, route_id: str, width: int) -> str:
    sim=ctx.sim; reg=ctx.registry
    inv=ctx.entities.get(ctx.player_id,Inventory)
    if route_id=='alerts': return alerts_screen(sim,width)
    if route_id=='character_sheet': return equipment_screen(sim,reg,inv,width)
    if route_id=='health': return health_screen(sim,width)
    if route_id=='inventory': return inventory_screen(reg,inv,width,sim)
    if route_id=='inspect': return look_screen(sim,width)
    if route_id=='room': return box('ROOM ANALYSIS',[f'{k}: {v}' for k,v in sim.building.room_at(sim.player_pos).items()],width)
    if route_id=='journal': return journal_screen(sim,width)
    if route_id=='region': return world_screen(sim,width)
    if route_id=='ecology': return ecology_screen(sim,width)
    if route_id=='economy': return economy_screen(sim,width)
    if route_id=='people': return society_screen(sim,width)
    if route_id=='factions': return faction_screen(sim,width)
    if route_id=='knowledge': return knowledge_screen(sim,width)
    if route_id=='magic': return magic_screen(sim,width)
    if route_id=='history': return history_screen(sim,width)
    if route_id=='simulation': return simulation_screen(sim,width)
    if route_id=='help': return help_screen(width)
    raise KeyError(route_id)


def _world_console(ctx: GameContext, term: Terminal) -> None:
    """Retained hierarchical World Console.

    This replaces nested blocking menu calls with an explicit screen stack.
    ESC always pops one route and restores the exact parent selection/scroll.
    """
    sim=ctx.sim
    nav=NavigationStack(RouteState('console','World Console'))
    groups={
        'character':CONSOLE_CHARACTER,'local':CONSOLE_LOCAL,'world':CONSOLE_WORLD,
        'society':CONSOLE_SOCIETY,'knowledge':CONSOLE_KNOWLEDGE,
        'records':CONSOLE_RECORDS,'system':CONSOLE_SYSTEM,
    }
    direct_views={'alerts','journal','character_sheet','health','inventory','inspect','room','region','ecology','economy','people','factions','knowledge','magic','history','simulation','help'}
    while True:
        route=nav.current
        if route.route_id=='console':
            choice=_stack_menu(term,nav,WORLD_CONSOLE_ROOT,
                               subtitle='Esc returns to the game. Enter opens one category.')
            if choice is None:return
            if choice=='__BACK__':continue
            if choice=='alerts':
                nav.push(RouteState('alerts','Alerts'))
                _stack_view(term,nav,_console_view_text(ctx,'alerts',screen_width(term.size()[0],118)))
                continue
            nav.push(RouteState(f'group:{choice}',choice.title(),payload={'group':choice}))
            continue
        if route.route_id.startswith('group:'):
            group=route.payload['group'];choice=_stack_menu(term,nav,groups.get(group,[]))
            if choice is None:return
            if choice=='__BACK__':continue
            if choice in direct_views:
                nav.push(RouteState(choice,choice.replace('_',' ').title()))
                _stack_view(term,nav,_console_view_text(ctx,choice,screen_width(term.size()[0],118)))
            elif choice=='look':
                _look_mode(ctx,term)
            elif choice=='settlements':
                nav.push(RouteState('settlements','Settlements'))
            elif choice=='ledger':
                _world_ledger(ctx,term,nav)
            elif choice=='settings':
                nav.push(RouteState('settings','Settings'))
            continue
        if route.route_id=='settlements':
            uid=_stack_menu(term,nav,_settlement_rows(sim))
            if uid is None:return
            if uid=='__BACK__':continue
            nav.push(RouteState(f'settlement:{uid}','Settlement Detail',payload={'uid':uid}))
            _stack_view(term,nav,settlement_detail_screen(sim,uid,screen_width(term.size()[0],118)))
            continue
        if route.route_id=='settings':
            rows=[
                ('color',f'ANSI color: {"ON" if sim.state.ui_color else "OFF"}'),
                ('unicode',f'Unicode glyphs: {"ON" if sim.state.ui_unicode else "OFF"}'),
                ('offline',f'Offline progression: {sim.state.offline_policy.upper()} (OFF / SAFE / FULL)'),
                ('density',f'UI density: {sim.state.ui_density.upper()}'),
                ('backup','Create manual rotating save backup now'),
                ('mods',f'Loaded data mods: {len(getattr(sim,"loaded_mods",[]))}'),
            ]
            choice=_stack_menu(term,nav,rows)
            if choice is None:return
            if choice=='__BACK__':continue
            if choice=='color':sim.state.ui_color=not sim.state.ui_color
            elif choice=='unicode':sim.state.ui_unicode=not sim.state.ui_unicode
            elif choice=='offline':
                order=['off','safe','full'];idx=order.index(sim.state.offline_policy) if sim.state.offline_policy in order else 0;sim.state.offline_policy=order[(idx+1)%len(order)]
            elif choice=='density':sim.state.ui_density='compact' if sim.state.ui_density=='dense' else 'dense'
            elif choice=='backup':
                target=ctx.db.backup(3);nav.push(RouteState('settings-backup','Backup Created'));_stack_view(term,nav,box('BACKUP CREATED',[str(target)],screen_width(term.size()[0],110)))
            elif choice=='mods':
                rows2=getattr(sim,'loaded_mods',[]) or ['No external data mods are active.'];nav.push(RouteState('settings-mods','Data Mods'));_stack_view(term,nav,box('DATA MODS',rows2+[f'hash={getattr(sim,"mod_hash","none")}'],screen_width(term.size()[0],110)))
            continue
        # ledger routes are handled inside _world_ledger and should be gone on return.
        if route.route_id.startswith('ledger'):
            _world_ledger(ctx,term,nav);continue
        if not nav.back():return


def _settings(ctx:GameContext,term:Terminal)->None:
    """Direct settings shortcut uses the same stack behavior as World Console."""
    sim=ctx.sim;nav=NavigationStack(RouteState('settings','Settings'))
    while True:
        rows=[
            ('color',f'ANSI color: {"ON" if sim.state.ui_color else "OFF"}'),
            ('unicode',f'Unicode glyphs: {"ON" if sim.state.ui_unicode else "OFF"}'),
            ('offline',f'Offline progression: {sim.state.offline_policy.upper()} (OFF / SAFE / FULL)'),
            ('density',f'UI density: {sim.state.ui_density.upper()}'),
            ('backup','Create manual rotating save backup now'),
            ('mods',f'Loaded data mods: {len(getattr(sim,"loaded_mods",[]))}'),
        ]
        choice=_stack_menu(term,nav,rows)
        if choice is None:return
        if choice=='__BACK__':continue
        if choice=='color':sim.state.ui_color=not sim.state.ui_color
        elif choice=='unicode':sim.state.ui_unicode=not sim.state.ui_unicode
        elif choice=='offline':
            order=['off','safe','full'];idx=order.index(sim.state.offline_policy) if sim.state.offline_policy in order else 0;sim.state.offline_policy=order[(idx+1)%len(order)]
        elif choice=='density':sim.state.ui_density='compact' if sim.state.ui_density=='dense' else 'dense'
        elif choice=='backup':
            target=ctx.db.backup(3);nav.push(RouteState('backup','Backup Created'));_stack_view(term,nav,box('BACKUP CREATED',[str(target)],screen_width(term.size()[0],110)))
        elif choice=='mods':
            rows2=getattr(sim,'loaded_mods',[]) or ['No external data mods are active.'];nav.push(RouteState('mods','Data Mods'));_stack_view(term,nav,box('DATA MODS',rows2+[f'hash={getattr(sim,"mod_hash","none")}'],screen_width(term.size()[0],110)))

def _storage_menu(ctx:GameContext,term:Terminal)->str:
    sim=ctx.sim;reg=ctx.registry;pid=ctx.player_id;inv=ctx.entities.get(pid,Inventory)
    c=sim.building.nearby_container(sim.player_pos)
    if not c:
        _view_text(term,box('STORAGE',['No accessible container is adjacent to you.'],screen_width(term.size()[0],88)));return UI_BACK
    nav=NavigationStack(RouteState('storage','Nearby Storage'))
    while True:
        route=nav.current
        if route.route_id=='storage':
            mass,volume=sim.building.container_load(c)
            choice=_stack_menu(term,nav,[
                ('store',f'Store item — {mass/1000:.1f}/{c.capacity_mass_g/1000:.1f} kg'),
                ('take',f'Take item — {volume/1000:.1f}/{c.capacity_volume_ml/1000:.1f} L'),
                ('inspect',f'Inspect contents — {sum(c.items.values())} items'),
            ])
            if choice is None:return UI_BACK
            if choice=='__BACK__':continue
            if choice=='inspect':
                rows=[f'{reg.items[iid].name if iid in reg.items else iid} x{n}' for iid,n in sorted(c.items.items()) if n>0]
                nav.push(RouteState('storage-inspect','Container Contents'))
                _stack_view(term,nav,box('CONTAINER CONTENTS',rows or ['Empty.'],screen_width(term.size()[0],96)))
                continue
            nav.push(RouteState(f'storage-{choice}',choice.title(),payload={'mode':choice}))
            continue
        if route.route_id in ('storage-store','storage-take'):
            mode=route.payload['mode']
            source=inv.items if mode=='store' else c.items
            title='STORE WHICH ITEM?' if mode=='store' else 'TAKE WHICH ITEM?'
            rows=[(iid,f'{reg.items[iid].name} x{n}') for iid,n in sorted(source.items()) if n>0 and iid in reg.items]
            iid=_stack_menu(term,nav,rows,subtitle='Esc returns to the storage menu.')
            if iid is None:return UI_BACK
            if iid=='__BACK__':continue
            sim.execute(StoreCommand(pid,iid,1) if mode=='store' else TakeFromContainerCommand(pid,iid,1))
            return sim.log[-1].message if sim.log else ''
        if not nav.back():return UI_BACK


def _inventory_ui_data(reg:ContentRegistry,inv:Inventory,sim:Simulation)->dict:
    total_mass=sum(reg.items[iid].mass_g*n for iid,n in inv.items.items() if iid in reg.items and n>0)
    total_volume=sum(reg.items[iid].volume_ml*n for iid,n in inv.items.items() if iid in reg.items and n>0)
    categories={}
    items={}
    for iid,n in inv.items.items():
        item=reg.items.get(iid)
        if not item or n<=0:continue
        cat=item.category or 'misc';categories[cat]=categories.get(cat,0)+n
        items[iid]={
            'name':item.name,'count':n,'category':cat,
            'mass_kg':item.mass_g*n/1000.0,'unit_mass_kg':item.mass_g/1000.0,
            'volume_l':item.volume_ml*n/1000.0,'description':item.description or item.flavor or '',
            'equip_slot':item.equip_slot or '', 'nutrition':item.nutrition,
            'tags':list(item.tags),'roles':list(item.utility_roles),
        }
    equipped={slot:iid for slot,iid in sim.state.player_equipment.items() if iid in reg.items}
    return {
        'total_mass_kg':total_mass/1000.0,'total_volume_l':total_volume/1000.0,
        'stack_count':len(items),'item_count':sum(v['count'] for v in items.values()),
        'categories':categories,'items':items,'equipped':equipped,
        'near_storage':bool(sim.building.nearby_container(sim.player_pos)),
        'player_sex':getattr(sim.state,'player_sex','male'),
        'player_sprite_index':int(getattr(sim.state,'player_sprite_index',0)),
        'player_name':sim.state.player_name,
    }


def _recipe_ui_data(reg:ContentRegistry,sim:Simulation,inv:Inventory,recipes)->dict:
    stations=sim.building.nearby_station_ids(sim.player_pos)
    rows={}
    for r in recipes:
        missing=sim.crafting.missing_requirements(r.id,inv,stations)
        outputs=[{'id':iid,'name':reg.items[iid].name if iid in reg.items else iid,'qty':n} for iid,n in r.outputs.items()]
        inputs=[{'id':iid,'name':reg.items[iid].name if iid in reg.items else iid,'need':n,'have':inv.count(iid)} for iid,n in r.inputs.items()]
        rows[r.id]={
            'name':r.name,'category':r.category or 'general','description':r.description or '',
            'minutes':r.minutes,'difficulty':r.difficulty,'skill':r.skill,
            'station':reg.structures[r.station].name if r.station and r.station in reg.structures else '',
            'ready':not missing,'missing':list(missing),'outputs':outputs,'inputs':inputs,
        }
    return {'recipes':rows}


def _design_ui_data(reg:ContentRegistry,inv:Inventory,designs)->dict:
    rows={}
    for d in designs:
        slots=[]
        for slot,options in d.components.items():
            choices=[]
            for iid,meta in options.items():
                choices.append({'id':iid,'name':reg.items[iid].name if iid in reg.items else iid,'qty':int(meta['qty']),'have':inv.count(iid),'material':reg.materials[meta['material']].name if meta['material'] in reg.materials else meta['material']})
            slots.append({'name':slot,'choices':choices})
        rows[d.id]={'name':d.name,'output_id':d.output_item,'output_name':reg.items[d.output_item].name if d.output_item in reg.items else d.output_item,'minutes':d.minutes,'slots':slots,'primary':d.primary_component}
    return {'designs':rows}


def _crafting_home_ui_data(reg:ContentRegistry,sim:Simulation,inv:Inventory,known,ideas)->dict:
    total=max(1,len(reg.recipes));known_n=len(known);items_n=len(set(sim.state.player_discovered_items))
    return {
        'known_recipes':known_n,'total_recipes':len(reg.recipes),'progress':known_n/total,
        'ready_experiments':len(ideas),'known_materials':items_n,
        'experiments_run':int(sim.state.player_crafting_experiments),
        'crafting_skill':sim.player_skill('crafting'),
        'knowledge_count':len(sim.state.player_knowledge),
    }


def _crafting_material_ui_data(reg:ContentRegistry,sim:Simulation)->dict:
    items={}
    for iid in sorted(set(sim.state.player_discovered_items)):
        item=reg.items.get(iid)
        if not item:continue
        items[iid]={'name':item.name,'category':item.category or 'misc','material':reg.materials[item.material].name if item.material and item.material in reg.materials else '', 'description':item.description or item.flavor or ''}
    return {'items':items,'count':len(items)}


def _crafting_tree_ui_data(reg:ContentRegistry,sim:Simulation,inv:Inventory)->dict:
    nodes=[]
    for rid,status,parents in sim.crafting.discovery_tree_rows(inv):
        r=reg.recipes[rid]
        nodes.append({
            'id':rid,'name':r.name,'category':r.category or 'general','status':status,
            'parents':[x for x in parents.split(', ') if x],
            'outputs':[iid for iid in r.outputs if iid in reg.items],
            'minutes':r.minutes,
        })
    return {'nodes':nodes,'known':sum(1 for n in nodes if n['status']=='known'),'total':len(nodes)}


def _inventory_menu(ctx:GameContext,term:Terminal)->str:
    sim=ctx.sim;reg=ctx.registry;pid=ctx.player_id
    nav=NavigationStack(RouteState('inventory','INVENTORY // PACK'))
    while True:
        inv=ctx.entities.get(pid,Inventory);route=nav.current;width=screen_width(term.size()[0],108)
        if route.route_id=='inventory':
            inv_ui=_inventory_ui_data(reg,inv,sim)
            choice=_stack_menu(term,nav,[
                ('overview',f'Pack overview — {sum(inv.items.values())} total stacked items'),
                ('browse','Browse / inspect carried items'),
                ('storage','Nearby container storage'),
                ('equipment','Equipment, anatomy & wounds'),
                ('read','Read a carried book'),
            ],subtitle='Esc returns to gameplay.',presentation='inventory_home',presentation_data=inv_ui)
            if choice is None:return UI_BACK
            if choice=='__BACK__':continue
            if choice=='overview':
                nav.push(RouteState('inventory-overview','INVENTORY // PACK OVERVIEW'));_stack_view(term,nav,inventory_screen(reg,inv,width,sim));continue
            if choice=='browse':nav.push(RouteState('inventory-browse','INVENTORY // CARRIED ITEMS'));continue
            if choice=='storage':
                result=_storage_menu(ctx,term)
                if result!=UI_BACK:return result
                continue
            if choice=='equipment':
                result=_handle_menu(ctx,term,'f')
                if result!=UI_BACK:return result
                continue
            if choice=='read':sim.execute(ReadBookCommand(pid));return sim.log[-1].message if sim.log else ''
        elif route.route_id=='inventory-browse':
            rows=[(iid,f'{reg.items[iid].name} x{n} | {reg.items[iid].mass_g*n/1000:.1f} kg') for iid,n in sorted(inv.items.items(),key=lambda kv:(reg.items[kv[0]].name if kv[0] in reg.items else kv[0])) if n>0 and iid in reg.items]
            iid=_stack_menu(term,nav,rows,presentation='inventory_items',presentation_data=_inventory_ui_data(reg,inv,sim))
            if iid is None:return UI_BACK
            if iid=='__BACK__':continue
            nav.push(RouteState(f'inventory-item:{iid}',reg.items[iid].name,payload={'iid':iid}));continue
        elif route.route_id.startswith('inventory-item:'):
            iid=route.payload['iid'];item=reg.items.get(iid)
            if item is None or inv.count(iid)<=0:
                nav.back();continue
            actions=[('inspect','Inspect details'),('drop','Drop one')]
            if item.nutrition>0:actions.append(('eat',f'Eat — nutrition {item.nutrition}'))
            if item.equip_slot:actions.append(('equip',f'Equip — {item.equip_slot}'))
            if sim.building.nearby_container(sim.player_pos):actions.append(('store','Store one in nearby container'))
            act=_stack_menu(term,nav,actions,subtitle=f'{item.name} x{inv.count(iid)}',presentation='inventory_item_actions',presentation_data={'item_id':iid,**_inventory_ui_data(reg,inv,sim)})
            if act is None:return UI_BACK
            if act=='__BACK__':continue
            if act=='inspect':
                nav.push(RouteState(f'inventory-detail:{iid}','INVENTORY // ITEM DETAIL',payload={'iid':iid}));_stack_view(term,nav,item_detail_screen(reg,sim,inv,iid,width),presentation='inventory_item_detail',presentation_data={'item_id':iid,**_inventory_ui_data(reg,inv,sim)});continue
            if act=='drop':sim.execute(DropCommand(pid,iid,1))
            elif act=='eat':sim.execute(EatCommand(pid,iid))
            elif act=='equip':sim.execute(EquipCommand(pid,iid))
            elif act=='store':sim.execute(StoreCommand(pid,iid,1))
            return sim.log[-1].message if sim.log else ''
        if not nav.back():return UI_BACK

def _crafting_menu(ctx:GameContext,term:Terminal)->str:
    """Discovery-first crafting browser.

    The terminal backend keeps full keyboard parity while the pygame backend
    renders these top-level routes as graphical tabs/cards. All discovery
    mutation is performed by simulation commands; opening this UI is read-only.
    """
    sim=ctx.sim;reg=ctx.registry;pid=ctx.player_id;inv=ctx.entities.get(pid,Inventory)
    while True:
        known=sorted(sim.crafting.discovered_recipes(inv),key=lambda r:(r.category or 'general',r.name))
        ideas=sim.crafting.researchable_recipes(inv)
        discovered_items=set(sim.state.player_discovered_items)
        rows=[
            ('recipes',f'Discovered Recipes — {len(known)} known'),
            ('ideas',f'Experiment — {len(ideas)} material combinations ready to test'),
            ('materials',f'Materials — {len(discovered_items)} item types examined'),
            ('tree','Tech Tree — trace discovered recipes and future branches'),
        ]
        if reg.designs:rows.append(('design','Component Designs — choose materials part by part'))
        pick=_select(term,'CRAFTING MODE // WORKBENCH',rows,presentation='crafting_home',presentation_data=_crafting_home_ui_data(reg,sim,inv,known,ideas))
        if not pick:return UI_BACK

        if pick=='materials':
            by_cat={}
            for iid in sorted(discovered_items,key=lambda x:(reg.items[x].category if x in reg.items else '',reg.items[x].name if x in reg.items else x)):
                item=reg.items.get(iid)
                if not item:continue
                by_cat.setdefault(item.category or 'misc',[]).append(item)
            body=['New material types reveal simple techniques immediately; multi-material techniques become experiments.','']
            if not by_cat:body.append('You have not examined any craft materials yet. Gather or pick up something useful.')
            for cat,items in sorted(by_cat.items()):
                body.append(cat.replace('_',' ').upper())
                body.extend('  '+it.name for it in items[:24])
                body.append('')
            _view_text(term,box('CRAFTING // MATERIAL DISCOVERIES',body,screen_width(term.size()[0],104)),presentation='crafting_materials',presentation_data=_crafting_material_ui_data(reg,sim))
            continue

        if pick=='tree':
            body=['Legend: [KNOWN] usable now  [TEST] can be learned through trial and error  [LOCKED] needs new material knowledge','']
            for rid,status,parents in sim.crafting.discovery_tree_rows(inv):
                r=reg.recipes[rid]
                if status=='known': label=f'[KNOWN] {r.name}'
                elif status=='experiment': label=f'[TEST]  {r.name}'
                elif status=='knowledge': label=f'[LOCKED] {r.category.replace("_"," ").title()} technique — outside knowledge required'
                else: label=f'[LOCKED] {r.category.replace("_"," ").title()} technique — discover more materials'
                if parents and status in {'known','experiment'}:
                    parent_names=[reg.recipes[x].name for x in parents.split(', ') if x in reg.recipes]
                    if parent_names:label+='  ← '+', '.join(parent_names)
                body.append(label)
            _view_text(term,box('CRAFTING // DISCOVERY TECH TREE',body,screen_width(term.size()[0],112)),presentation='crafting_tree',presentation_data=_crafting_tree_ui_data(reg,sim,inv))
            continue

        if pick=='ideas':
            if not ideas:
                _view_text(term,box('CRAFTING // EXPERIMENT',['No unresolved material combinations are ready.','Find new material types or craft simple components to reveal new branches.'],screen_width(term.size()[0],96)))
                continue
            rid=_select(term,'CRAFTING // EXPERIMENT',[(r.id,f'{r.name} — test {", ".join(reg.items[i].name for i in sorted(sim.crafting.discovery_requirements(r)) if i in reg.items)}') for r in ideas],presentation='crafting_experiments',presentation_data={**_recipe_ui_data(reg,sim,inv,ideas),'clues':{r.id:[i for i in sorted(sim.crafting.discovery_requirements(r)) if i in reg.items] for r in ideas}})
            if not rid:continue
            r=reg.recipes[rid]
            req=sim.crafting.discovery_requirements(r)
            body=[r.name,'',r.description or 'A possible technique suggested by materials you have handled.','',
                  'KNOWN MATERIAL CLUES']+[f'  {reg.items[i].name}' for i in sorted(req) if i in reg.items]
            body+=['',f'Experiment time: {max(10,15+r.difficulty*5)} minutes','No output is created until the recipe itself is learned and crafted.']
            action=_select(term,'CRAFTING // TRIAL & ERROR',[('experiment','Experiment and record the technique'),('back','Not now')],presentation='crafting_experiment_detail',presentation_data={'recipe_id':rid,**_recipe_ui_data(reg,sim,inv,[r]),'clues':{rid:[i for i in sorted(req) if i in reg.items]}})
            if action=='experiment':
                sim.execute(ExperimentRecipeCommand(pid,rid));return sim.log[-1].message if sim.log else ''
            continue

        if pick=='design':
            design_list=list(reg.designs.values())
            did=_select(term,'CRAFTING // COMPONENT DESIGN',[(d.id,f'{d.name} → {reg.items[d.output_item].name} | {d.minutes}m') for d in design_list],presentation='crafting_designs',presentation_data=_design_ui_data(reg,inv,design_list))
            if not did:continue
            d=reg.designs[did];choices={};slots=list(d.components.items());idx=0
            while 0<=idx<len(slots):
                slot,options=slots[idx];choice=_select(term,f'CRAFTING // {d.name.upper()} — {slot.upper()}',[(iid,f'{reg.items[iid].name} — have {inv.count(iid)}, need {meta["qty"]} | {reg.materials[meta["material"]].name}') for iid,meta in options.items()],presentation='crafting_component_choices',presentation_data={'design_id':did,'slot':slot,**_design_ui_data(reg,inv,[d])})
                if not choice:
                    if idx==0:break
                    idx-=1;choices.pop(slots[idx][0],None);continue
                choices[slot]=choice;idx+=1
            if choices and idx==len(slots):sim.execute(ComponentCraftCommand(pid,did,choices));return sim.log[-1].message if sim.log else ''
            continue

        # Discovered-recipe tab.
        if not known:
            _view_text(term,box('CRAFTING // DISCOVERED RECIPES',['No recipes discovered yet.','Handle basic materials such as branches, stone, brush, bone, clay, or ore to start uncovering techniques.'],screen_width(term.size()[0],96)))
            continue
        categories=sorted(set(r.category or 'general' for r in known))
        category=_select(term,'CRAFTING // RECIPES',[(c,f'{c.replace("_"," ").title()} — {sum(1 for r in known if (r.category or "general")==c)} discovered') for c in categories],presentation='crafting_categories',presentation_data={'counts':{c:sum(1 for r in known if (r.category or 'general')==c) for c in categories},'known':len(known)})
        if not category:continue
        recipes=[r for r in known if (r.category or 'general')==category]
        stations=sim.building.nearby_station_ids(sim.player_pos);recipe_rows=[]
        for r in recipes:
            missing=sim.crafting.missing_requirements(r.id,inv,stations);ready=not missing
            result=', '.join(f'{reg.items[i].name} x{n}' for i,n in r.outputs.items() if i in reg.items)
            recipe_rows.append((r.id,f'[{"READY" if ready else "NEEDS"}] {r.name} → {result} | {r.minutes}m'+(f' | {missing[0]}' if missing else '')))
        rid=_select(term,f'CRAFTING // {category.replace("_"," ").upper()}',recipe_rows,presentation='crafting_recipes',presentation_data=_recipe_ui_data(reg,sim,inv,recipes))
        if not rid:continue
        r=reg.recipes[rid];missing=sim.crafting.missing_requirements(r.id,inv,stations)
        body=[r.name,'',r.description or 'A practical process.', '', 'OUTPUT']+[f'  {reg.items[i].name} x{n}' for i,n in r.outputs.items() if i in reg.items]
        body+=['','MATERIALS']+[f'  {reg.items[i].name if i in reg.items else i}: {inv.count(i)}/{n}' for i,n in r.inputs.items()]
        if r.tool_qualities:body+=['','TOOLS']+[f'  {q.replace("_"," ").title()} quality {need}+' for q,need in r.tool_qualities.items()]
        if r.station:body+=['',f'Station: {reg.structures[r.station].name}']
        body+=[f'Skill: {r.skill.replace("_"," ").title()} (difficulty {r.difficulty})',f'Base time: {r.minutes} minutes']
        outs=[reg.items[i] for i in r.outputs if i in reg.items]
        roles=sorted({role for it in outs for role in it.utility_roles})
        if roles:body+=['','ENABLES','  '+', '.join(x.replace('_',' ') for x in roles)]
        if missing:body+=['','NOT READY']+[f'  {x}' for x in missing]
        action=_select(term,f'CRAFTING // {r.name.upper()}',[('craft','Craft now')] if not missing else [('view','Close detail')],presentation='crafting_recipe_detail',presentation_data={'recipe_id':rid,**_recipe_ui_data(reg,sim,inv,[r])})
        if action=='craft':sim.execute(CraftCommand(pid,rid));return sim.log[-1].message if sim.log else ''

def _structure_group(st)->str:
    tags=set(st.tags);uses=set(st.uses)
    if {'bed','furniture','container'} & tags or {'sleep','storage','rest'} & uses:return 'camp & furniture'
    if 'station' in tags:return 'workstations'
    if {'wall','door','roof','support'} & tags:return 'building & structure'
    if 'bridge' in tags:return 'travel & access'
    return 'other'

def _building_menu(ctx:GameContext,term:Terminal)->str:
    sim=ctx.sim;reg=ctx.registry;pid=ctx.player_id;inv=ctx.entities.get(pid,Inventory)
    while True:
        groups=sorted(set(_structure_group(st) for st in reg.structures.values()))
        group=_select(term,'CONSTRUCTION',[(g,f'{g.title()} — {sum(1 for st in reg.structures.values() if _structure_group(st)==g)} plans') for g in groups])
        if not group:return UI_BACK
        rows=[]
        structs=sorted((st for st in reg.structures.values() if _structure_group(st)==group),key=lambda s:s.name)
        for st in structs:
            missing=[f'{reg.items[i].name if i in reg.items else i} {inv.count(i)}/{n}' for i,n in st.cost.items() if inv.count(i)<n]
            uses=', '.join(x.replace('_',' ') for x in st.uses[:3]) or 'structure'
            rows.append((st.id,f'[{"READY" if not missing else "NEEDS"}] {st.name} — {uses}'+(f' | {missing[0]}' if missing else '')))
        sid=_select(term,group.upper(),rows)
        if not sid:continue
        st=reg.structures[sid];body=[st.name,'',st.description or 'A constructed piece.','','USES','  '+(', '.join(x.replace('_',' ') for x in st.uses) or 'physical construction')]
        if st.comfort:body.append(f'Comfort: {st.comfort}')
        if st.work_bonus:body.append(f'Work bonus: {st.work_bonus}')
        if st.warmth:body.append(f'Warmth: {st.warmth}')
        if st.shelter:body.append(f'Shelter: {st.shelter}')
        body+=['','MATERIALS']+[f'  {reg.items[i].name if i in reg.items else i}: {inv.count(i)}/{n}' for i,n in st.cost.items()]
        _view_text(term,box(st.name.upper(),body,screen_width(term.size()[0],94),'Esc back'))
        d=_direction(term)
        if not d:continue
        sim.execute(BuildCommand(pid,sid,*d));return sim.log[-1].message if sim.log else ''

def _handle_menu(ctx:GameContext,term:Terminal,key:str)->str:
    sim=ctx.sim;reg=ctx.registry;pid=ctx.player_id;lower=key.lower() if len(key)==1 else key
    if lower=='drink':sim.execute(DrinkCommand(pid));return sim.log[-1].message if sim.log else ''
    if lower=='rest':return _rest_menu(ctx,term)
    if lower=='cook':return _cooking_menu(ctx,term)
    if lower=='process':return _process_carcass_menu(ctx,term)
    if lower=='preserve':return _preservation_menu(ctx,term)
    if lower=='hunt':return _hunt_action(ctx,term)
    if lower=='i':
        result=_inventory_menu(ctx,term);return UI_BACK if result==UI_BACK else (sim.log[-1].message if sim.log else result)
    if lower=='?':_view_text(term,help_screen(screen_width(term.size()[0],100)));return ''
    if lower=='l':_look_mode(ctx,term);return ''
    if lower=='m':
        presenter=getattr(term,'present_region_map',None)
        if callable(presenter):
            from worldseed.ui.atlas_map import begin_atlas, atlas_input
            begin_atlas(term,sim)
            presenter(sim)
            while True:
                mk=term.read_key();ml=mk.lower() if len(mk)==1 else mk
                if mk=='ESC' or ml in ('m','q','\r','\n'):break
                if atlas_input(term,sim,mk):presenter(sim)
            return ''
        _view_text(term,world_screen(sim,screen_width(term.size()[0],106)));return ''
    if lower=='h':_view_text(term,history_screen(sim,screen_width(term.size()[0],110)));return ''
    if lower=='v':_view_text(term,faction_screen(sim,screen_width(term.size()[0],110)));return ''
    if lower=='r':room=sim.building.room_at(sim.player_pos);_view_text(term,box('ROOM ANALYSIS',[f'{k}: {v}' for k,v in room.items()],screen_width(term.size()[0],96)));return ''
    if lower=='c':return _crafting_menu(ctx,term)
    if lower=='b':return _building_menu(ctx,term)
    if lower=='u':
        d=_direction(term)
        if not d:return UI_BACK
        sim.execute(DismantleCommand(pid,*d));return sim.log[-1].message if sim.log else ''
    if lower=='f':
        while True:
            mode=_select(term,'EQUIPMENT / HEALTH ACTION',[
                ('overview','Review equipment, anatomy & wounds'),('equip','Equip armor/clothing'),
                ('unequip','Unequip slot'),('treat','Treat a wound'),('medicine','Take medicine for symptomatic infection')])
            if not mode:return UI_BACK
            if mode=='overview':
                _view_text(term,equipment_screen(sim,reg,ctx.entities.get(pid,Inventory),screen_width(term.size()[0],100)));continue
            if mode=='equip':
                inv=ctx.entities.get(pid,Inventory);rows=[(iid,f'{reg.items[iid].name} -> {reg.items[iid].equip_slot} | armor {reg.items[iid].armor}') for iid,n in inv.items.items() if n>0 and iid in reg.items and reg.items[iid].equip_slot]
                iid=_select(term,'EQUIP',rows)
                if not iid:continue
                sim.execute(EquipCommand(pid,iid));return sim.log[-1].message if sim.log else ''
            if mode=='unequip':
                rows=[(slot,f'{slot}: {reg.items[iid].name}') for slot,iid in sorted(sim.state.player_equipment.items()) if iid in reg.items]
                slot=_select(term,'UNEQUIP',rows)
                if not slot:continue
                sim.execute(UnequipCommand(pid,slot));return sim.log[-1].message if sim.log else ''
            if mode=='treat':
                wounds=[(str(i),f'{w.get("part","?").replace("_"," ")} {w.get("tissue","?")} sev {w.get("severity",0)} bleed {w.get("bleeding",0)}' + (' fracture' if w.get('fracture') else '')) for i,w in enumerate(sim.state.player_wounds) if int(w.get('severity',0))>0 or int(w.get('bleeding',0))>0 or w.get('fracture')]
                wi=_select(term,'SELECT WOUND',wounds)
                if wi is None:continue
                inv=ctx.entities.get(pid,Inventory);treatments=[(iid,f'{reg.items[iid].name} x{n}') for iid,n in inv.items.items() if n>0 and iid in ('core:bandage','core:splint')]
                iid=_select(term,'SELECT TREATMENT',treatments)
                if not iid:continue
                sim.execute(TreatWoundCommand(pid,int(wi),iid));return sim.log[-1].message if sim.log else ''
            if mode=='medicine':
                sim.execute(TreatDiseaseCommand(pid));return sim.log[-1].message if sim.log else ''
    if lower=='e':
        inv=ctx.entities.get(pid,Inventory);rows=[]
        for uid,meal in sim.state.prepared_meals.items():
            if meal.owner=='player' and meal.portions>0:rows.append(('meal:'+uid,f'{meal.name} — {meal.portions} portion(s) | {meal.calories} kcal | P{meal.protein} C{meal.carbs} F{meal.fat}'))
        for iid,n in inv.items.items():
            if iid in reg.items and reg.items[iid].nutrition>0:
                it=reg.items[iid];rows.append(('item:'+iid,f'{it.name} x{n} | satiety {it.nutrition} | {it.calories} kcal | {"/".join(it.food_groups) or "food"}'))
        pick=_select(term,'EAT',rows)
        if not pick:return UI_BACK
        if pick.startswith('meal:'):sim.execute(EatMealCommand(pid,pick[5:]))
        else:sim.execute(EatCommand(pid,pick[5:]))
        return sim.log[-1].message if sim.log else ''
    if lower=='x':
        d=_direction(term)
        if not d:return UI_BACK
        sim.execute(AttackCommand(pid,*d));return sim.log[-1].message if sim.log else ''
    if lower=='k':
        while True:
            mode=_select(term,'ARCANE ACTION',[
                ('overview','Review magical laws, rituals & contamination'),('cast','Cast discovered law'),
                ('experiment','Experiment with source + form'),('ritual','Perform known ritual')])
            if not mode:return UI_BACK
            if mode=='overview':_view_text(term,magic_screen(sim,screen_width(term.size()[0],110)));continue
            if mode=='cast':
                laws=[(x.uid,f'{x.source}+{x.form} cost {x.stamina_cost}; {x.time_constraint}/{x.terrain_constraint or "any"}') for x in sim.state.magic_laws.values() if f'knowledge:{x.uid}' in sim.state.player_knowledge]
                uid=_select(term,'CAST DISCOVERED LAW',laws)
                if not uid:continue
                sim.execute(CastMagicCommand(pid,uid));return sim.log[-1].message if sim.log else ''
            if mode=='experiment':
                source=_select(term,'EXPERIMENT: SOURCE',[(x,x.title()) for x in ('ember','tide','stone','gale','bloom','shade','star','blood')])
                if not source:continue
                form=_select(term,'EXPERIMENT: FORM',[(x,x.title()) for x in ('project','bind','mend','reveal','ward','shape')])
                if not form:continue
                sim.execute(ExperimentMagicCommand(pid,source,form));return sim.log[-1].message if sim.log else ''
            if mode=='ritual':
                rows=[(r.uid,f'{r.name}: {r.effect}; {r.duration_minutes}m; participants {r.min_participants}') for r in sim.state.rituals.values()]
                rid=_select(term,'RITUAL',rows)
                if not rid:continue
                sim.execute(RitualCommand(pid,rid));return sim.log[-1].message if sim.log else ''
    if lower=='z':
        sim.execute(ReadBookCommand(pid));return sim.log[-1].message if sim.log else ''
    if lower=='o':
        town=_near_market(sim)
        if not town:_view_text(term,box('MARKET',['No discovered settlement market is within 10 tiles. Open TAB > World > Settlements to browse known towns.'],screen_width(term.size()[0],92)));return UI_BACK
        while True:
            mode=_select(term,f'{town.name} MARKET',[('buy','Buy'),('sell','Sell')])
            if not mode:return UI_BACK
            if mode=='buy':rows=[(iid,f'{reg.items[iid].name}: stock {n}, buy {sim.player_trade_price(town.uid,iid,True)}c') for iid,n in town.stocks.items() if n>0 and iid in reg.items]
            else:
                inv=ctx.entities.get(pid,Inventory);rows=[(iid,f'{reg.items[iid].name}: x{n}, sell {sim.player_trade_price(town.uid,iid,False)}c') for iid,n in inv.items.items() if n>0 and iid!='core:copper_coin' and iid in reg.items]
            iid=_select(term,mode.upper(),rows)
            if not iid:continue
            inv=ctx.entities.get(pid,Inventory);price=sim.economy.trade_price(town.uid,iid,mode=='buy')
            maximum=min(town.stocks.get(iid,0),inv.count('core:copper_coin')//max(1,price)) if mode=='buy' else inv.count(iid)
            quantities=[q for q in (1,5,10) if q<=maximum]
            if maximum>0 and maximum not in quantities:quantities.append(maximum)
            qkey=_select(term,'QUANTITY',[(str(q),f'{q} unit(s) — {q*price}c') for q in quantities]) if quantities else None
            if not qkey:continue
            amount=int(qkey);sim.execute(BuyCommand(pid,town.uid,iid,amount) if mode=='buy' else SellCommand(pid,town.uid,iid,amount));return sim.log[-1].message if sim.log else ''
    return ''

def _map_key(key:str,pid:int):
    k=key.lower() if len(key)==1 else key
    if k in DIRECTION_KEYS:return MoveCommand(pid,*DIRECTION_KEYS[k])
    if k=='g':return GatherCommand(pid)
    if k=='.':return WaitCommand(pid,10)
    if k=='>':return VerticalMoveCommand(pid,-1)
    if k=='<':return VerticalMoveCommand(pid,1)
    if k=='p':return PickupCommand(pid)
    if k=='n':return None
    if k=='j':return HarvestCommand(pid)
    return None

def _pause_menu(ctx:GameContext,term:Terminal)->str:
    while True:
        choice=_select(term,'PAUSED',[('resume','Resume game'),('save','Save game'),('console','Open World Console'),('menu','Save & return to main menu'),('quit','Save & quit WORLDSEED')],allow_escape=True)
        if not choice:return 'resume'
        if choice=='resume':return 'resume'
        if choice=='save':_save(ctx);return 'saved'
        if choice=='console':_world_console(ctx,term);continue
        if choice=='menu':_save(ctx);return 'menu'
        if choice=='quit':_save(ctx);return 'quit'

def run_game(ctx:GameContext,term:Terminal)->str:
    renderer=Renderer(ctx.registry);last='';autosave=ctx.sim.turn
    while True:
        _present_game_frame(term,ctx,renderer,last);last=''
        key=term.read_key();intent=classify_key(key)
        if intent.kind=='quit':
            _save(ctx);return 'quit'
        if intent.kind=='pause':
            choice=_pause_menu(ctx,term)
            if choice=='quit':return 'quit'
            if choice=='menu':return 'menu'
            if choice=='saved':last='Game saved.'
            continue
        if intent.kind=='actions':last=_action_palette(ctx,term);continue
        if intent.kind=='console':_world_console(ctx,term);continue
        if intent.kind=='settings':_settings(ctx,term);continue
        if intent.kind=='direct_menu':
            result=_handle_menu(ctx,term,str(intent.value));last='' if result==UI_BACK else result;continue
        if intent.kind=='move':ctx.sim.execute(MoveCommand(ctx.player_id,*intent.value))
        elif intent.kind=='gather':
            result=_gather_action(ctx,term);last='' if result==UI_BACK else result;continue
        elif intent.kind=='pickup':ctx.sim.execute(PickupCommand(ctx.player_id))
        elif intent.kind=='wait':ctx.sim.execute(WaitCommand(ctx.player_id,int(intent.value)))
        elif intent.kind=='vertical':ctx.sim.execute(VerticalMoveCommand(ctx.player_id,int(intent.value)))
        elif intent.kind=='farm':
            if intent.value=='till':ctx.sim.till();ctx.sim.execute(WaitCommand(ctx.player_id,10))
            elif intent.value=='plant':
                cid=_select(term,'PLANT',[(c.id,f'{c.name} — seeds {ctx.entities.get(ctx.player_id,Inventory).count(c.seed_item)} | {c.growth_hours//24}d | N/P/K {c.nitrogen}/{c.phosphorus}/{c.potassium} | seasons {"/".join(c.seasons)}') for c in ctx.registry.crops.values()])
                if cid:ctx.sim.execute(PlantCommand(ctx.player_id,cid))
                else:continue
            elif intent.value=='harvest':ctx.sim.execute(HarvestCommand(ctx.player_id))
            else:
                mode=_select(term,'CROP CARE',[('water','Irrigate crop'),('fertilize','Apply bone meal')])
                if mode=='water':ctx.sim.irrigate();ctx.sim.execute(WaitCommand(ctx.player_id,10))
                elif mode=='fertilize':ctx.sim.execute(FertilizeCommand(ctx.player_id))
                else:continue
        else:
            continue
        last=ctx.sim.log[-1].message if ctx.sim.log else ''
        if ctx.sim.turn-autosave>=AUTOSAVE_TURNS:
            _save(ctx);autosave=ctx.sim.turn;last='Autosaved.'
def _make_display_backend():
    force_terminal='--terminal' in sys.argv
    force_window='--window' in sys.argv
    if not force_terminal:
        try:
            from worldseed.ui.pygame_terminal import PygameTerminal
            if PygameTerminal.available():
                return PygameTerminal()
            if force_window:
                raise RuntimeError('pygame-ce is required for --window. Install with: pip install pygame-ce')
        except Exception:
            if force_window:
                raise
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise RuntimeError('No graphical backend available and no interactive terminal was detected. Install pygame-ce or run from a terminal.')
    return Terminal()

def main()->int:
    try:
        term=_make_display_backend()
    except Exception as exc:
        print(f'WORLDSEED display error: {exc}');return 2
    term.enter()
    try:
        while True:
            sel=_choose_world(term)
            if sel is None:return 0
            last_loading_bucket=[-1]
            def loading_progress(phase,value,detail=''):
                bucket=int(float(value)*100)
                if bucket==last_loading_bucket[0] and bucket not in (0,100):return
                last_loading_bucket[0]=bucket
                presenter=getattr(term,'present_loading',None)
                if callable(presenter):presenter(phase,value,detail)
                else:
                    width=34;filled=max(0,min(width,int(width*float(value))))
                    bar='['+'#'*filled+'-'*(width-filled)+']'
                    term.present(f'WORLDSEED // WORLD GENERATION\n\n{phase}\n{detail}\n\n{bar} {int(float(value)*100)}%')
            loading_progress('Loading WORLDSEED',0.0,'Preparing deterministic seed data')
            try:ctx=_load_context(sel,loading_progress)
            except Exception as exc:
                _view_text(term,box('LOAD FAILED',[str(exc)],min(90,term.size()[0]-2)));continue
            # Loading can take long enough for key-repeat events from the startup
            # wizard to remain queued. Discard only pending gameplay key presses
            # at the transition so a stale Esc cannot immediately open PAUSED.
            discard=getattr(term,'discard_pending_input',None)
            if callable(discard):discard()
            try:
                outcome=run_game(ctx,term)
            except WindowCloseRequested:
                _save(ctx);return 0
            finally:
                ctx.db.close()
            if outcome=='quit':return 0
            # 'menu' simply loops back into the retained terminal main menu.
    except WindowCloseRequested:
        return 0
    finally:
        term.restore()
