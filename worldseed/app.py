from __future__ import annotations
from contextlib import nullcontext
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
import json,secrets,sys,time,traceback
from worldseed.debug import debug_log_path
from worldseed.config import AUTOSAVE_TURNS,DATA_DIR,DEFAULT_SAVE_DIR,ENGINE_VERSION,RESOURCEGEN_VERSION,INITIAL_PREGEN_CHUNK_RADIUS,LOAD_WARM_CHUNK_RADIUS,CHUNK_SIZE
from worldseed.content.registry import ContentRegistry
from worldseed.content.item_catalog import ITEM_TYPE_ORDER, item_sort_key, ordered_items
from worldseed.content.mods import ModManager, ModError
from worldseed.core.coords import WorldPos, split_world
from worldseed.core.rng import PCG32, derive_seed, hash_u64
from worldseed.entities.components import Inventory,PlayerControlled,Position,Renderable,Vitals
from worldseed.entities.store import EntityStore
from worldseed.persistence.database import WorldDatabase
from worldseed.profiling import measure_if_enabled
from worldseed.sim.commands import *
from worldseed.sim.engine import Simulation
from worldseed.sim.realtime import RealtimeSimulationDriver
from worldseed.systems.state import LivingWorldState, pos_key
from worldseed.systems.resources import ResourceSystem
from worldseed.systems.generation import ProceduralSocietyGenerator
from worldseed.systems.settlement_planner import SettlementSkeletonPlanner, settlement_rank_for_population
from worldseed.systems.dialogue import DialogueSystem
from worldseed.systems.dialogue_context import build_dialogue_facts
from worldseed.systems.workshops import WORKSHOP_PROFILES, STATION_PIECE_ALIASES, recipes_for_station, profile_dict
from worldseed.world.region_blocks import RegionBlockPlanner
from worldseed.ui.renderer import Renderer
from worldseed.ui.npc_activity import activity_label, possessions_rows, schedule_label, timeline_rows
from worldseed.ui.combat_range import ranged_overlay, melee_overlay
from worldseed.ui.screens import *
from worldseed.ui.terminal import Terminal


def _present_game_frame(term, ctx, renderer, message: str = '', cursor=None, combat_overlay=None) -> None:
    stealth_overlay=ctx.sim.stealth_snapshot() if ctx.sim.state.player_stealth_mode else None
    presenter = getattr(term, 'present_game', None)
    if callable(presenter):
        presenter(ctx.registry, ctx.world, ctx.entities, ctx.sim, ctx.player_id, message, cursor, combat_overlay, stealth_overlay)
    else:
        w, h = term.size()
        term.present(renderer.render(
            ctx.world, ctx.entities, ctx.sim, ctx.player_id, w, h, message,
            cursor=cursor, combat_overlay=combat_overlay, stealth_overlay=stealth_overlay,
        ))

from worldseed.ui.widgets import select_menu, view_text, prompt_text
from worldseed.ui.pointer import WindowCloseRequested
from worldseed.ui.session import NavigationStack, RouteState
from worldseed.ui.layout import screen_width
from worldseed.ui.trade_quotes import max_affordable_trade, trade_total
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

    coarse=[]
    if world.generator.version>=8:
        # v8 continents and structural basins operate on multi-thousand-cell
        # scales, so the old 576-cell terrain probe can legitimately sit inside
        # a large ocean. Search broad fields first without realizing chunks.
        def v8_coarse(limit:int,step:int):
            rows=[]
            for y in range(-limit,limit+1,step):
                for x in range(-limit,limit+1,step):
                    f=world.generator.sample_fields(WorldPos(x,y,0))
                    if not (26500<=f.elevation<=51500):
                        continue
                    climate_penalty=0
                    if f.moisture<22000:climate_penalty+=220
                    if not (17000<=f.temperature<=56500):climate_penalty+=220
                    relief_penalty=abs(f.elevation-35000)//180
                    rows.append((max(abs(x),abs(y))+climate_penalty+relief_penalty,abs(x)+abs(y),x,y))
            return rows
        coarse=v8_coarse(6144,192)
        if not coarse:
            coarse=v8_coarse(12288,384)
        # Refine only around promising broad-field samples. This avoids invoking
        # cave-site planning or chunk realization across the full search square.
        offsets=sorted(
            (abs(dx)+abs(dy),dx,dy)
            for dy in range(-96,97,8) for dx in range(-96,97,8)
        )
    else:
        # Frozen v4-v7 startup search.
        step=24;limit=576
        for y in range(-limit,limit+1,step):
            for x in range(-limit,limit+1,step):
                tid=terrain_id(x,y)
                if tid in preferred:
                    tree_penalty=0 if tree_climate_possible(x,y,tid) else 240
                    biome_bonus=0 if tid in {'core:grass','core:forest'} else 8
                    coarse.append((max(abs(x),abs(y))+biome_bonus+tree_penalty,abs(x)+abs(y),x,y))
        offsets=sorted(((abs(dx)+abs(dy),dx,dy) for dy in range(-12,13) for dx in range(-12,13)))
    if not coarse:return WorldPos(0,0,0)

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

@dataclass(frozen=True, slots=True)
class VillageTarget:
    region_x:int
    region_y:int
    population:int


def _village_targets(world:World,seed:bytes,reg:ContentRegistry,limit:int=12):
    """Return deterministic settlement candidates without creating regional plans.

    Population is derived from the same settlement RNG position used when a real
    regional planner supplies the anchor. Calling ProceduralSocietyGenerator
    without a planner would consume two RNG draws for its fallback x/y and would
    therefore choose a different population/rank than the eventual settlement.
    """
    from worldseed.world.regional_civilization import RegionalCivilizationPlanner
    civilization=RegionalCivilizationPlanner(world,getattr(world,"settlement_plan_version",1),seed=seed)
    villages=[];others=[]
    def region_has_base_land(rx:int,ry:int)->bool:
        x0,y0=rx*512,ry*512
        for gy in (1,2,3,4,5):
            for gx in (1,2,3,4,5):
                p=WorldPos(x0+gx*512//6,y0+gy*512//6,0)
                if int(world.generator.sample_fields(p).elevation)>=23800:return True
        return False
    for radius in range(0,9):
        for ry in range(-radius,radius+1):
            for rx in range(-radius,radius+1):
                if max(abs(rx),abs(ry))!=radius or not region_has_base_land(rx,ry):continue
                profile=civilization.profile(rx,ry)
                if not profile.settlement_present:continue
                rng=PCG32(derive_seed(seed,"settlement",rx,ry))
                pop=25+rng.randbelow(110)
                target=VillageTarget(rx,ry,pop)
                # Prefer physically strong sites before proximity. Hydrology can
                # later lower the score of a marginal dry-climate candidate;
                # high-quality candidates are substantially more stable after
                # the authoritative drainage pass.
                row=(-profile.score,-profile.route_value,abs(rx)+abs(ry),ry,rx,target)
                (villages if settlement_rank_for_population(pop)=='village' else others).append(row)
        if radius>=4 and len(villages)>=max(8,limit):break
    ordered=sorted(villages,key=lambda row:row[:-1])
    ordered+=sorted(others,key=lambda row:row[:-1])
    return tuple(row[-1] for row in ordered[:max(1,int(limit))])

def _find_village_target(world:World,seed:bytes,reg:ContentRegistry):
    rows=_village_targets(world,seed,reg,limit=1)
    return rows[0] if rows else None


def _village_gateway_spawn(world:World,seed:bytes,reg:ContentRegistry,target)->WorldPos:
    """Re-score the target region with prepared hydrology, then spawn at a gateway."""
    planner=RegionBlockPlanner(world)
    # A failed/older village-start attempt may already have persisted a plan
    # scored before hydrology existed. Refresh is intentional here: this is a
    # new-world startup path and the hydrology-aware plan is the first valid
    # physical authority for the settlement.
    region=planner.plan(target.region_x,target.region_y,persist=False,refresh=True)
    society=ProceduralSocietyGenerator(seed,reg,planner)
    generated=society.settlement_for_cell(target.region_x,target.region_y)
    if not generated:raise ValueError("Selected village region no longer contains a settlement")
    town=generated[0]
    skeletons=SettlementSkeletonPlanner(world)
    skeleton=skeletons.plan(region,town.uid,town.population,persist=False,refresh=True)
    commons=list(skeleton.plan.common_cells)
    if commons:
        cx=sum(x for x,_ in commons)//len(commons);cy=sum(y for _,y in commons)//len(commons)
    else:cx,cy=town.x,town.y
    gates=sorted(skeleton.plan.gateway_cells,key=lambda p:(abs(p[0]-cx)+abs(p[1]-cy),p[1],p[0]),reverse=True)

    def dry(q:WorldPos)->bool:
        td=world.registry.terrains.get(world.generator.terrain_at(q))
        env=world.environment_at(q)
        return bool(td and td.passable and 'water' not in td.tags and env is not None and not env.open_water)

    for gx,gy in gates:
        dx=0 if gx==cx else (1 if gx>cx else -1)
        dy=0 if gy==cy else (1 if gy>cy else -1)
        for step in range(2,7):
            q=WorldPos(gx+dx*step,gy+dy*step,0)
            if dry(q):return q
        for radius in range(1,5):
            ring=[]
            for oy in range(-radius,radius+1):
                for ox in range(-radius,radius+1):
                    if max(abs(ox),abs(oy))!=radius:continue
                    q=WorldPos(gx+ox,gy+oy,0)
                    if dry(q):ring.append((abs(ox)+abs(oy),oy,ox,q))
            if ring:return min(ring,key=lambda row:(row[0],row[1],row[2]))[-1]
    candidates=[]
    for radius in range(3,18):
        for oy in range(-radius,radius+1):
            for ox in range(-radius,radius+1):
                if max(abs(ox),abs(oy))!=radius:continue
                q=WorldPos(cx+ox,cy+oy,0)
                if dry(q):candidates.append((abs(ox)+abs(oy),oy,ox,q))
        if candidates:return min(candidates,key=lambda row:(row[0],row[1],row[2]))[-1]
    raise ValueError("Prepared village has no legal exterior spawn cell")


def _find_village_spawn(world:World,seed:bytes,reg:ContentRegistry)->WorldPos|None:
    """Compatibility helper for worlds whose hydrology is already prepared."""
    target=_find_village_target(world,seed,reg)
    return _village_gateway_spawn(world,seed,reg,target) if target is not None else None

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
    try:world.settlement_plan_version=int(db.get_meta('settlement_plan_version'))
    except KeyError:
        from worldseed.config import LEGACY_SETTLEMENT_PLAN_VERSION
        world.settlement_plan_version=LEGACY_SETTLEMENT_PLAN_VERSION
    try:world.routegen_version=int(db.get_meta('routegen_version'))
    except KeyError:world.routegen_version=1
    try:hydrology_version=int(db.get_meta('hydrology_version'))
    except KeyError:hydrology_version=1
    try:hydrology_morphology_version=int(db.get_meta('hydrology_morphology_version'))
    except KeyError:hydrology_morphology_version=1
    hydrology=HydrologyGenerator(
        world.generator,db,version=hydrology_version,
        morphology_version=hydrology_morphology_version,
    ) if gen_version>=5 else None
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
        state.player_name=(player_name or 'Wanderer').strip() or 'Wanderer'
        state.player_origin=str(origin or 'wilderness')
        state.player_sex=(getattr(sel,'player_sex','male') or 'male').lower();state.player_sprite_index=int(getattr(sel,'player_sprite_index',0) or 0)
        state.player_crafting_discovery_enabled=True
        if build:
            state.player_attributes={str(k):int(v) for k,v in build.get('attributes',{}).items()}
            state.player_skills={str(k):int(v) for k,v in build.get('skills',{}).items()}
            state.player_talents=sorted({str(x) for x in build.get('talents',[])})
        intellect=state.player_attributes.get('intellect',5);scholar=state.player_skills.get('scholarship',0)
        state.player_literacy=max(20,min(100,28+intellect*6+scholar*3+(10 if 'quick_study' in state.player_talents else 0)))
    spawn_resources=ResourceSystem(state,reg,seed,world)
    village_targets=()
    village_target=None
    if pp is None:
        emit('Selecting viable starting region',0.06,'Scanning deterministic climate, terrain and primitive resources')
        if state.player_origin=='village':
            village_targets=_village_targets(world,seed,reg)
            village_target=village_targets[0] if village_targets else None
            # Candidate discovery does not create/persist a regional anchor.
            # Prepare geography around the region center first.
            pos=(WorldPos(village_target.region_x*512+256,village_target.region_y*512+256,0)
                 if village_target is not None else None)
        else:pos=None
        if pos is None:pos=_find_spawn(world,state.player_origin,spawn_resources)
    else:
        pos=WorldPos(int(pp['x']),int(pp['y']),int(pp.get('z',0)))

    if is_new and prepare_world:
        radius=int(INITIAL_PREGEN_CHUNK_RADIUS)
        if hydrology is not None:
            def hydro_progress(i,total,detail):emit('Resolving watersheds',0.08+0.14*(i/max(1,total)),detail)
            if village_targets:
                chosen=None;last_error=None
                for candidate in village_targets:
                    center=WorldPos(candidate.region_x*512+256,candidate.region_y*512+256,0)
                    bounds=_pregen_bounds(center,radius)
                    hydrology.prepare_world_bounds(*bounds,persist=True,progress=hydro_progress)
                    world.generator.attach_hydrology(hydrology)
                    world.prepare_coastal_mouths(bounds)
                    try:
                        chosen=_village_gateway_spawn(world,seed,reg,candidate)
                        village_target=candidate
                        pos=chosen
                        break
                    except ValueError as exc:
                        last_error=exc
                        continue
                if chosen is None:
                    raise RuntimeError("No physically viable village start was found in the bounded candidate search.") from last_error
            else:
                bounds=_pregen_bounds(pos,radius)
                hydrology.prepare_world_bounds(*bounds,persist=True,progress=hydro_progress)
                world.generator.attach_hydrology(hydrology)
                world.prepare_coastal_mouths(bounds)
                pos=_relocate_spawn_after_hydrology(world,pos,spawn_resources)
        elif village_target is not None:
            pos=_village_gateway_spawn(world,seed,reg,village_target)
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
            world.prepare_coastal_mouths(bounds)
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
def _save(ctx:GameContext, *, backup:bool=True)->None:
    with measure_if_enabled(getattr(ctx.sim,'profiler',None),'save.total'):
        _save_checkpoint(ctx,backup=backup)

def _save_checkpoint(ctx:GameContext, *, backup:bool=True)->None:
    started=time.perf_counter()
    profiler=getattr(ctx.sim,'profiler',None)
    with measure_if_enabled(profiler,'save.capture'):
        p=ctx.entities.get(ctx.player_id,Position).value
        inventory=dict(ctx.entities.get(ctx.player_id,Inventory).items)
        vitals=asdict(ctx.entities.get(ctx.player_id,Vitals))
        tiles=ctx.world.snapshot_dirty_tiles()
        saved_at=time.time()
        # Capture state before touching the database. A failed snapshot must
        # leave the previous checkpoint metadata and live retry data intact.
        state=ctx.sim.state.checkpoint_snapshot()
        state['last_offline_wall_time']=saved_at
        metadata={
            'last_saved_at':saved_at,'player_name':ctx.sim.state.player_name,
            'player_origin':ctx.sim.state.player_origin,'player_sex':ctx.sim.state.player_sex,
            'player_sprite_index':int(ctx.sim.state.player_sprite_index),
        }
    # Rotating full-database backups are intentionally reserved for explicit
    # save/menu/quit checkpoints. Copying an ever-growing generated-world DB on
    # every routine autosave caused increasingly long apparent freezes during
    # exploration. Autosave still commits all authoritative state atomically.
    if backup and ctx.db.path.exists() and ctx.db.path.stat().st_size>0:
        with measure_if_enabled(profiler,'save.backup'):
            ctx.db.backup(3)
    with measure_if_enabled(profiler,'save.database'):
        ctx.db.save_state(turn=ctx.sim.turn,tile_deltas=tiles.tiles,player_id=ctx.player_id,
                          position=p,inventory=inventory,vitals=vitals,sim_state=state,
                          metadata=metadata,profiler=profiler)
    # save_state returns only after SQLite commits. A later edit, even one
    # restoring the same terrain value, has another revision and stays pending.
    ctx.world.acknowledge_dirty_tiles(tiles)
    ctx.sim.state.last_offline_wall_time=saved_at
    try:
        ctx.sim.debug.event("save",backup=bool(backup),elapsed_ms=round((time.perf_counter()-started)*1000,3),turn=int(ctx.sim.turn),world=str(ctx.db.path))
        ctx.sim.debug.flush()
    except Exception:pass

def _select(terminal:Terminal,title:str,rows:list[tuple[str,str]],allow_escape=True,**kwargs)->str|None:
    return select_menu(terminal,title,rows,allow_escape=allow_escape,**kwargs)

def _view_text(term:Terminal,text:str,**kwargs)->None:
    view_text(term,text,**kwargs)

def _direction(term:Terminal)->tuple[int,int]|None:
    k=select_menu(term,'DIRECTION',[('UP','North'),('RIGHT','East'),('DOWN','South'),('LEFT','West')],subtitle='Choose an adjacent tile.')
    return DIRECTION_KEYS.get(k)
def _harvestable_positions(sim:Simulation,origin:WorldPos|None=None)->list[WorldPos]:
    p=origin or sim.player_pos
    offsets=((0,0),(0,-1),(0,1),(-1,0),(1,0))
    return [p.moved(dx,dy) for dx,dy in offsets if sim.resources.is_harvestable(p.moved(dx,dy))]

def _gather_positions(ctx:GameContext,positions:list[WorldPos])->str:
    sim=ctx.sim;p=sim.player_pos;messages=[];seen=set()
    for target in positions:
        key=(target.x,target.y,target.z)
        if key in seen:continue
        seen.add(key)
        dx,dy=target.x-p.x,target.y-p.y
        if abs(dx)+abs(dy)>1:continue
        before=len(sim.log)
        sim.execute(GatherCommand(ctx.player_id,dx,dy))
        if len(sim.log)>before:messages.append(sim.log[-1].message)
    if not messages:return 'Nothing harvestable is within reach.'
    if len(messages)==1:return messages[0]
    return f'Gathered {len(messages)} nearby targets. ' + ' | '.join(messages)

def _gather_action(ctx:GameContext,term:Terminal)->str:
    """Gather the only nearby target immediately, or multi-select when several are in reach."""
    sim=ctx.sim;p=sim.player_pos
    candidates=_harvestable_positions(sim,p)
    if not candidates:return 'Nothing harvestable is within reach.'
    if len(candidates)==1:return _gather_positions(ctx,candidates)
    renderer=Renderer(ctx.registry);cursor=candidates[0];selected=set()
    while True:
        target_desc=sim.resources.description(cursor) if sim.resources.is_harvestable(cursor) else 'Nothing harvestable'
        picked=(cursor.x,cursor.y,cursor.z) in selected
        msg=(f'HARVEST — {target_desc} — {"SELECTED" if picked else "not selected"}. '
             f'Click or Space toggles; Enter gathers {len(selected)} selected; C clears; Esc cancels.')
        _present_game_frame(term,ctx,renderer,msg,cursor);k=term.read_key()
        if k.startswith('UI_WORLD:'):
            _,x,y=k.split(':');nxt=WorldPos(int(x),int(y),p.z)
            if abs(nxt.x-p.x)+abs(nxt.y-p.y)<=1:
                cursor=nxt
                if sim.resources.is_harvestable(cursor):
                    key=(cursor.x,cursor.y,cursor.z)
                    if key in selected:selected.remove(key)
                    else:selected.add(key)
            continue
        if k in ('ESC','q','Q'):return UI_BACK
        if k in ('c','C'):
            selected.clear();continue
        if k in (' ','SPACE','\t'):
            if sim.resources.is_harvestable(cursor):
                key=(cursor.x,cursor.y,cursor.z)
                if key in selected:selected.remove(key)
                else:selected.add(key)
            continue
        if k in ('\r','\n'):
            if not selected:return 'No harvest targets selected.'
            ordered=[WorldPos(x,y,z) for x,y,z in sorted(selected,key=lambda q:(abs(q[0]-p.x)+abs(q[1]-p.y),q[1],q[0]))]
            return _gather_positions(ctx,ordered)
        direction=DIRECTION_KEYS.get(k.lower() if len(k)==1 else k)
        if direction:
            nxt=cursor.moved(*direction);rdx,rdy=nxt.x-p.x,nxt.y-p.y
            if abs(rdx)+abs(rdy)<=1:cursor=nxt
def _fishing_action(ctx:GameContext,term:Terminal,target:WorldPos|None=None)->str:
    sim=ctx.sim;p=sim.player_pos;inv=ctx.entities.get(ctx.player_id,Inventory)
    if target is None:
        candidates=[]
        for dy in range(-3,4):
            for dx in range(-3,4):
                if abs(dx)+abs(dy)>3:continue
                q=p.moved(dx,dy)
                if sim.fishing.is_fishable(q):
                    region=sim.fishing.region_at(q)
                    candidates.append((abs(dx)+abs(dy),q,region))
        candidates.sort(key=lambda row:(row[0],row[1].y,row[1].x))
        if not candidates:return 'No fishable water is within casting range.'
        if len(candidates)==1:
            target=candidates[0][1]
        else:
            rows=[]
            for _,q,region in candidates:
                terrain=sim.world.tile_at(q).terrain.name
                rows.append((f'{q.x},{q.y}',f'{terrain} — {region.structure.replace("_"," ")} | {region.salinity} | productivity {region.productivity}'))
            choice=_select(term,'CHOOSE FISHING WATER',rows,subtitle='Rod range is up to 3 tiles; hand, spear, and net require adjacent shallow water.')
            if not choice:return UI_BACK
            x,y=(int(v) for v in choice.split(','))
            target=WorldPos(x,y,p.z)
    if target.z!=p.z or not sim.fishing.is_fishable(target):return 'That tile is not fishable water.'
    distance=abs(target.x-p.x)+abs(target.y-p.y)
    methods=sim.fishing.available_methods(inv,target,distance)
    if not methods:
        region=sim.fishing.region_at(target)
        return f'No usable fishing method for this {region.depth if region else "water"}. Craft a rod and line, fishing spear, or net, or move adjacent for hand fishing.'
    nested=bool(getattr(term,'mouse_ui',False) and target is not None)
    method=_select(term,'FISHING METHOD',[(m,f'{m.title()} — {label}') for m,label in methods],
                   subtitle='Choose how to fish this water.',presentation='world_context' if nested else '')
    if not method:return UI_BACK
    bait_id=''
    if method in ('rod','net'):
        bait_rows=[('__none__','No bait / bare presentation')]
        for iid in sim.fishing.bait_options(inv):
            item=ctx.registry.items[iid]
            lure='reusable lure' if 'fishing_lure' in item.tags else f'x{inv.count(iid)}'
            bait_rows.append((iid,f'{item.name} — {lure}'))
        bait_choice=_select(term,'BAIT / LURE',bait_rows,subtitle='Choose bait or fish without it.',presentation='world_context' if nested else '')
        if not bait_choice:return UI_BACK
        bait_id='' if bait_choice=='__none__' else bait_choice
    dx,dy=target.x-p.x,target.y-p.y
    sim.execute(FishingCommand(ctx.player_id,dx,dy,method,bait_id))
    return sim.log[-1].message if sim.log else ''

def _learn_area_from_npc(ctx:GameContext,npc)->str:
    sim=ctx.sim;town=sim.state.settlements.get(npc.settlement_id)
    if town is None:return f'{npc.name} does not know this country well enough to map it for you.'
    rel=npc.relationships.setdefault('player',{'affection':0,'trust':0,'fear':0,'respect':0,'familiarity':0})
    trust=int(rel.get('trust',0));familiarity=int(rel.get('familiarity',0))
    community=DialogueSystem.settlement_standing(sim.state,npc.settlement_id)
    persuasion=int(sim.state.player_skills.get('persuasion',0))
    guarded=8+int(hash_u64(sim.seed,'area-willingness',npc.uid)%25)
    if npc.occupation in {'guard','scholar','merchant'}:guarded=max(6,guarded-5)
    if any(str(t).lower() in {'suspicious','secretive','paranoid'} for t in npc.traits):guarded+=15
    willingness=trust+familiarity//2+community//4+persuasion*2
    if willingness<guarded:
        return f'{npc.name} is not ready to share local claims or resources with you. Personal trust, community standing, or persuasion may help.'
    token=f'{town.region_x},{town.region_y}'
    control=sim.state.territory_control.get(token)
    faction_id=(control.controller_faction_id if control else '') or town.faction_id
    resources=[]
    for iid,qty in sorted(town.stocks.items(),key=lambda row:(-int(row[1]),row[0])):
        if int(qty)<=0:continue
        item=ctx.registry.items.get(iid);resources.append(item.name if item else iid)
        if len(resources)>=6:break
    monuments=[m.uid for m in sim.state.claim_monuments.values() if (m.region_x,m.region_y)==(town.region_x,town.region_y)]
    sim.state.learned_regions[token]={
        'region_x':town.region_x,'region_y':town.region_y,'learned_minute':sim.clock.minute,
        'source_npc_uid':npc.uid,'faction_id':faction_id,'settlement_ids':[town.uid],
        'resources':resources,'monument_uids':sorted(monuments),
    }
    if faction_id:sim.state.discovered_factions=sorted(set(sim.state.discovered_factions+[faction_id]))
    return f'{npc.name} explains the local boundary, who holds it, and the main goods here: '+(', '.join(resources) if resources else 'no dependable surplus')+'.'

def _gift_npc(ctx:GameContext,term:Terminal,npc)->str:
    inv=ctx.entities.get(ctx.player_id,Inventory)
    rows=[]
    for iid,count in sorted(inv.items.items()):
        item=ctx.registry.items.get(iid)
        if count<=0 or item is None:continue
        if item.nutrition>0 or iid=='core:clean_water' or 'drink' in item.tags:
            rows.append((iid,f'{item.name} — have {count}'))
    if not rows:return 'You have no food or drink to offer.'
    iid=_select(term,'OFFER A GIFT',rows,subtitle='The item is transferred from your pack. Gifts matter more when they answer a real need.')
    if not iid:return 'You decide not to offer anything.'
    item=ctx.registry.items[iid]
    if not inv.remove(iid,1):return 'You no longer have that item.'
    npc.inventory[iid]=npc.inventory.get(iid,0)+1
    rel=npc.relationships.setdefault('player',{'affection':0,'trust':0,'fear':0,'respect':0,'familiarity':0})
    needed=(iid=='core:clean_water' and npc.thirst>=45) or (item.nutrition>0 and npc.hunger>=45)
    trust_gain=4 if needed else 2;affection_gain=5 if needed else 3
    rel['trust']=min(100,int(rel.get('trust',0))+trust_gain)
    rel['affection']=min(100,int(rel.get('affection',0))+affection_gain)
    rel['familiarity']=min(100,int(rel.get('familiarity',0))+3)
    npc.memories.append({'minute':ctx.sim.clock.minute,'type':'gift','subject':'player','item_id':iid,'salience':8,'valence':affection_gain})
    npc.memories=npc.memories[-40:]
    return f'{npc.name} accepts the {item.name.lower()}'+(' gratefully; it answers an immediate need.' if needed else ' with thanks.')

def _conversation_clock_hold(term):
    pause=getattr(term,'pause_realtime',None)
    return pause() if callable(pause) else nullcontext()


def _npc_portrait(sim,npc):
    from worldseed.presentation.portraits import portrait_spec
    return portrait_spec(getattr(sim,'seed',b''),npc.uid,getattr(npc,'sex',''),getattr(npc,'age',30),
                         version=getattr(npc,'portrait_version',1))


def _conversation_menu(ctx:GameContext,term:Terminal,target,response:str='')->str:
    with _conversation_clock_hold(term):
        return _conversation_thread(ctx,term,target,response)


def _conversation_thread(ctx:GameContext,term:Terminal,target,response:str='')->str:
    sim=ctx.sim;dialogue=DialogueSystem(sim.state,sim.seed)
    if target.uid not in sim.state.introduced_npcs:response=''
    nav=NavigationStack(RouteState('npc-dialogue','Stranger',payload={'topic':'root','response':response}))

    def open_topic(topic_id:str)->None:
        # Returning to an ancestor restores that exact route, including its
        # spoken answer, selection and text page. Cyclic links cannot grow an
        # unbounded session stack. This state is never written into a save.
        for index,route in enumerate(nav._stack):
            if route.payload.get('topic')==topic_id:
                while nav.depth>index+1:nav.back()
                return
        route=RouteState(f'npc-dialogue:{topic_id}',topic_id.replace('_',' ').upper(),payload={'topic':topic_id})
        if nav.depth>=24:nav.replace(route)
        else:nav.push(route)

    while True:
        route=nav.current;topic=str(route.payload.get('topic','root'))
        vitals=ctx.entities.get(ctx.player_id,Vitals)
        scene=dialogue.scene(target,sim.clock.minute,vitals,known=target.uid in sim.known_npc_ids(),topic=topic,
                             introduced=target.uid in sim.state.introduced_npcs,
                             facts=build_dialogue_facts(ctx,target))
        if nav.depth==1:nav.current.title=scene.speaker
        # Prose is a retained utterance. New branches sample current world
        # conditions, while returning to a parent preserves what was said.
        route.payload.setdefault('opening',scene.opening)
        route.payload.setdefault('spans',[{'text':span.text,'topic':span.topic} for span in scene.spans])
        route.payload.setdefault('label',scene.topic_label or scene.topic.replace('_',' ').title())
        response=str(route.payload.get('response',''))
        graphical=callable(getattr(term,'present_feature_menu',None))
        rows=[(option.key,option.label) for option in scene.options
              if not (graphical and option.action=='inspect')]
        data={'speaker':scene.speaker,'role':scene.role,'opening':route.payload['opening'],'response':response,
              'context':scene.context,'npc_uid':target.uid,'options':rows,'topic':scene.topic,
              'portrait':_npc_portrait(sim,target),'time_paused':True,
              'relationship':dict(scene.relationship),'transcript_page':route.scroll,
              'spans':route.payload['spans'],'topic_label':route.payload['label'],
              'path':[{'index':i,'label':r.payload.get('label',r.title),'topic':r.payload.get('topic','root')} for i,r in enumerate(nav._stack)],
              'thread':[{'topic':r.payload.get('topic','root'),'label':r.payload.get('label',r.title),
                         'text':r.payload.get('opening',''),'response':r.payload.get('response','')} for r in nav._stack[:-1]]}
        choice=_stack_menu(term,nav,rows,subtitle='Follow highlighted words to explore a topic. Esc returns to the previous thread.',presentation='npc_dialogue',presentation_data=data)
        route.scroll=max(0,int(data.get('transcript_page',route.scroll)))
        if choice in (None,'goodbye'):return response or scene.opening
        if choice=='__BACK__':continue
        if choice in ('UI_ACTION:transcript_previous','UI_ACTION:transcript_next'):
            maximum=max(0,int(data.get('transcript_pages',route.scroll+2))-1)
            route.scroll=max(0,min(maximum,route.scroll+(-1 if choice.endswith('previous') else 1)));continue
        if isinstance(choice,str) and choice.startswith('UI_ACTION:path:'):
            try:index=int(choice.rsplit(':',1)[1])
            except ValueError:continue
            if 0<=index<nav.depth-1:
                while nav.depth>index+1:nav.back()
            continue
        if isinstance(choice,str) and choice.startswith('UI_ACTION:topic:'):
            topic_id=choice[len('UI_ACTION:topic:'):]
            # Pointer tokens are untrusted UI input. Only links actually
            # offered in this utterance and the current scene may navigate.
            offered={span.topic for span in scene.spans if span.topic}
            spoken={span['topic'] for span in route.payload['spans'] if span.get('topic')}
            if topic_id in offered & spoken:open_topic(topic_id)
            continue
        if choice=='UI_ACTION:inspect':choice='inspect'
        if choice=='inspect' and not any(o.key=='inspect' for o in scene.options):
            push=getattr(term,'push_floating_panel',None);pop=getattr(term,'pop_floating_panel',None)
            if callable(push):push()
            try:_npc_profile_menu(ctx,term,target.uid)
            finally:
                if callable(pop):pop()
            continue
        option=next((row for row in scene.options if row.key==choice),None)
        if option is None:continue
        if option.next_topic:
            if option.key=='back':nav.back()
            else:open_topic(option.next_topic)
            continue
        if option.action=='introduce':
            sim.execute(IntroduceNPCCommand(ctx.player_id,target.uid))
            response=sim.log[-1].message if sim.log else ''
            nav.reset_to_root();nav.current.selected=0;nav.current.scroll=0
            # Invalidate the stranger transcript cache immediately. Otherwise
            # the new speaker name is known but the on-screen greeting still
            # contains the anonymous pre-introduction utterance until exit.
            nav.current.payload={'topic':'root','response':response}
            updater=getattr(term,'invalidate_dialogue_cache',None)
            if callable(updater):updater()
            continue
        dialogue.apply_option(target,option,sim.clock.minute)
        route.scroll=0
        if option.action=='inspect':
            push=getattr(term,'push_floating_panel',None);pop=getattr(term,'pop_floating_panel',None)
            if callable(push):push()
            try:_npc_profile_menu(ctx,term,target.uid)
            finally:
                if callable(pop):pop()
            continue
        if option.action=='area':route.payload['response']=_learn_area_from_npc(ctx,target);continue
        if option.action=='local_knowledge':
            from worldseed.systems.npc_knowledge import NPCKnowledgeSystem
            knowledge=NPCKnowledgeSystem(sim.state,sim.registry)
            response,facts=knowledge.answer(target,option.key)
            knowledge.disclose(facts)
            route.payload['response']=response
            continue
        if option.action=='knowledge':
            before=len(sim.log);sim.begin_conversation(target.uid)
            response=sim.log[-1].message if len(sim.log)>before else f'{target.name} has nothing new to add.'
            route.payload['response']=response
            continue
        if option.action=='gift':route.payload['response']=_gift_npc(ctx,term,target);continue
        if option.action=='trade':
            response=(f'{target.name} is willing to trade through the settlement market.' if target.occupation=='merchant' else f'{target.name} directs you to the local market; they are not a trader.')
            route.payload['response']=response
            continue
        if option.action=='attack':
            return 'You end the conversation aggressively. Direct NPC combat is not yet part of the combat authority.'
        route.payload['response']=option.response

def _talk_action(ctx:GameContext,term:Terminal,npc_uid:str='')->str:
    with _conversation_clock_hold(term):
        return _talk_action_paused(ctx,term,npc_uid)


def _talk_action_paused(ctx:GameContext,term:Terminal,npc_uid:str='')->str:
    sim=ctx.sim;p=sim.player_pos
    inside=sim.interiors.player_presence()
    if inside is not None:
        nearby=[n for uid,n in sim.state.npcs.items() if n.alive
                and (a:=sim.state.interior_actors.get(uid)) is not None
                and a.space_id==inside.space_id
                and (a.x-inside.x)**2+(a.y-inside.y)**2<=1800**2]
        if npc_uid:nearby=[n for n in nearby if n.uid==npc_uid]
        if not nearby:return 'Nobody is close enough to talk to.'
        uid=nearby[0].uid if len(nearby)==1 else _select(term,'TALK TO',[(n.uid,n.name if n.uid in sim.introduced_npc_ids() else 'Stranger') for n in nearby])
        if not uid:return UI_BACK
        target=sim.state.npcs[uid];sim.begin_conversation(uid)
        return _conversation_menu(ctx,term,target,sim.log[-1].message if sim.log else '')
    nearby=[]
    for n in sim.state.npcs.values():
        if n.uid in sim.state.interior_actors:continue
        dist=abs(n.x-p.x)+abs(n.y-p.y)
        if n.alive and n.z==p.z and dist<=1:
            label=n.name if n.uid in sim.introduced_npc_ids() else 'Stranger'
            nearby.append((n.uid,n.x-p.x,n.y-p.y,f'{label} — {n.occupation if n.uid in sim.introduced_npc_ids() else "unknown occupation"}'))
    if not nearby:return 'Nobody is close enough to talk to.'
    if npc_uid:
        picked=next((row for row in nearby if row[0]==npc_uid),None)
        if picked is None:return 'That person is no longer close enough to talk to.'
        _,dx,dy,_=picked
    elif len(nearby)==1:
        _,dx,dy,_=nearby[0]
    else:
        uid=_select(term,'TALK TO',[(uid,label) for uid,_,_,label in nearby])
        if not uid:return UI_BACK
        _,dx,dy,_=next(row for row in nearby if row[0]==uid)
    target=next((n for n in sim.state.npcs.values() if n.alive and (n.x,n.y,n.z)==(p.x+dx,p.y+dy,p.z)),None)
    if target is None:return 'Nobody is close enough to talk to.'
    sim.execute(TalkCommand(ctx.player_id,dx,dy))
    return _conversation_menu(ctx,term,target,sim.log[-1].message if sim.log else '')

def _near_market(sim:Simulation):
    p=sim.player_pos;candidates=[]
    for town in sim.state.settlements.values():
        if town.uid not in sim.known_settlement_ids():continue
        market=sim.settlement_physicalization.destination_for_function(town.uid,("market",))
        if market is not None:
            distance=abs(market.x-p.x)+abs(market.y-p.y)
            if market.z==p.z and distance<=4:candidates.append((distance,town))
            continue
        distance=abs(town.x-p.x)+abs(town.y-p.y)
        if distance<=10:candidates.append((distance,town))
    return min(candidates,key=lambda row:(row[0],row[1].uid),default=(0,None))[1]

def _casing_notes(ctx:GameContext,term:Terminal,property_id:str)->str:
    sim=ctx.sim;intel=sim.casing.intel_for(property_id);structure=sim.settlement_physicalization.structure_by_id(property_id)
    if intel is None or structure is None:
        return 'No casing notes have been gathered for this property.'
    summary=sim.casing.summary(property_id);known=sim.known_npc_ids()
    owner='Unknown'
    if intel.owner_known:
        if intel.owner_uid in sim.state.npcs:
            owner=sim.state.npcs[intel.owner_uid].name if intel.owner_uid in known else 'Unidentified private owner'
        elif intel.owner_uid in sim.state.settlements:
            town=sim.state.settlements[intel.owner_uid]
            owner=town.name if town.uid in sim.known_settlement_ids() else 'Settlement authority'
        elif intel.owner_uid:
            owner='Known institution'
    room_labels=[]
    for uid in intel.room_ids:
        room=sim.settlement_physicalization.room_by_id(uid)
        if room is not None:room_labels.append(str(room.kind).replace('_',' ').title())
    storage_rows=[]
    for container in sim.property_storage.for_property(property_id):
        if container.uid in intel.storage_uids:
            distance=abs(container.x-sim.player_pos.x)+abs(container.y-sim.player_pos.y)
            storage_rows.append(f'{container.name} — {"within reach" if distance<=1 else "located"}')
    known_occupants=[sim.state.npcs[uid].name for uid in intel.occupant_uids if uid in known and uid in sim.state.npcs]
    unidentified=max(0,len(intel.occupant_uids)-len(known_occupants))
    occupants=', '.join(known_occupants)
    if unidentified:occupants+=((', ' if occupants else '')+f'{unidentified} unidentified')
    lines=[
        f'Property: {str(structure.function).replace("_"," ").title()}',
        f'Exterior survey: {int(summary.get("survey_progress",0))}%',
        f'Main entrance: {"identified" if intel.entrance_known else "not identified"}',
        f'Owner: {owner}',
        f'Attention: {str(summary.get("attention","low")).title()}',
        f'Sessions: {int(summary.get("sessions",0))}',
        '',
        'Known rooms: '+(', '.join(sorted(set(room_labels))) if room_labels else 'none'),
        'Known occupants: '+(occupants or 'none'),
        'Known storage: '+(str(len(storage_rows)) if storage_rows else 'none'),
        'Known access points: '+str(len(intel.door_uids)),
        'Known locks: '+str(len(intel.lock_uids)),
    ]
    lines.extend(f'  {row}' for row in storage_rows[:6])
    lock_rows=[]
    for uid in intel.lock_uids:
        door=sim.property_security.door_by_id(uid)
        if door is None:continue
        state='forced open' if door.forced else 'unlocked' if not door.locked else 'locked'
        lock_rows.append(f'  {door.role.replace("_"," ").title()}: {sim.property_security.lock_band(door.lock_level)} lock — {state} — condition {door.condition}%')
    if lock_rows:lines+=['','Known security:']+lock_rows[:6]
    lines+=['','Observe exposed sides, doors and yards from nearby sightlines. You do not need to squeeze into every alley. Entering rooms still reveals only spaces and storage you physically reach.']
    _view_text(term,box('CASING NOTES',lines,screen_width(term.size()[0],96)))
    return UI_BACK


def _steal_property_storage_action(ctx:GameContext,term:Terminal,container)->str:
    sim=ctx.sim;reg=ctx.registry;pid=ctx.player_id
    if sim.state.player_hunting_stance!='stalk':
        return 'Select Stalk mode before attempting storage theft.'
    error=_container_reach_error(sim,container)
    if error:return error
    rows=[
        (iid,f'{reg.items[iid].name} — x{n} — value {sim.player_trade_price(container.settlement_id,iid,True)}c')
        for iid,n in sorted(container.items.items()) if n>0 and iid in reg.items
    ]
    if not rows:return f'{container.name} is empty.'
    iid=_select(term,'PROPERTY STORAGE',rows,subtitle=f'{container.name} • taking an item is theft.')
    if not iid:return UI_BACK
    maximum=min(10,int(container.items.get(iid,0)))
    quantities=[q for q in (1,2,5,10) if q<=maximum]
    qkey=_select(term,'STEAL · QUANTITY',[(str(q),f'{q} × {reg.items[iid].name}') for q in quantities]) if quantities else None
    if not qkey:return UI_BACK
    amount=int(qkey)
    snap=sim.stealth_snapshot();known=sim.known_npc_ids()
    watcher_names=[
        (sim.state.npcs[uid].name if uid in known and uid in sim.state.npcs else 'Stranger')
        for uid in snap.get('seen_by',())
        if uid in sim.state.npcs and sim.state.npcs[uid].settlement_id==container.settlement_id
    ]
    risk='No current observer has line of sight.' if not watcher_names else 'Seen by: '+', '.join(watcher_names[:4])
    confirm=_select(term,'STEAL · REVIEW',[('confirm','Take item'),('back','Cancel')],subtitle=f'{amount} × {reg.items[iid].name}. {risk}')
    if confirm!='confirm':return UI_BACK
    sim.execute(StealContainerCommand(pid,container.uid,iid,amount))
    return sim.log[-1].message if sim.log else ''


def _steal_market_action(ctx:GameContext,term:Terminal,town)->str:
    sim=ctx.sim;reg=ctx.registry;pid=ctx.player_id
    if not sim.state.player_stealth_mode:
        sim.execute(ToggleStealthCommand(pid,True))
        return sim.log[-1].message if sim.log else ''
    rows=[]
    for iid,n in sorted(town.stocks.items()):
        if n<=0 or iid not in reg.items:continue
        value=sim.player_trade_price(town.uid,iid,True)
        rows.append((iid,f'{reg.items[iid].name} — stock {n} — value {value}c'))
    iid=_select(
        term,'STEAL FROM MARKET',rows,
        subtitle='Sight cones use NPC facing plus real terrain, doors and generated building walls.',
    )
    if not iid:return UI_BACK
    maximum=min(10,town.stocks.get(iid,0))
    quantities=[q for q in (1,2,5,10) if q<=maximum]
    qkey=_select(
        term,'STEAL · QUANTITY',
        [(str(q),f'{q} × {reg.items[iid].name} — value {q*sim.player_trade_price(town.uid,iid,True)}c') for q in quantities],
    ) if quantities else None
    if not qkey:return UI_BACK
    amount=int(qkey)
    snap=sim.stealth_snapshot();seen=list(snap.get('seen_by',()))
    known=sim.known_npc_ids()
    watcher_names=[
        (sim.state.npcs[uid].name if uid in known and uid in sim.state.npcs else 'Stranger')
        for uid in seen if uid in sim.state.npcs and sim.state.npcs[uid].settlement_id==town.uid
    ]
    risk='No current observer has line of sight.' if not watcher_names else 'Seen by: '+', '.join(watcher_names[:4])
    confirm=_select(
        term,'STEAL · REVIEW',
        [('confirm','Take goods'),('back','Cancel')],
        subtitle=f'{amount} × {reg.items[iid].name}. {risk}',
    )
    if confirm!='confirm':return UI_BACK
    sim.execute(StealMarketCommand(pid,town.uid,iid,amount))
    return sim.log[-1].message if sim.log else ''

def _look_mode(ctx:GameContext,term:Terminal)->None:
    interiors=getattr(ctx.sim,'interiors',None)
    if interiors is not None and interiors.player_presence() is not None:
        from worldseed.ui.interior_inspection import interior_look_screen
        _view_text(term,interior_look_screen(ctx.sim,ctx.registry,screen_width(term.size()[0],88)))
        return
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
    interiors=getattr(sim,'interiors',None)
    if interiors is not None and interiors.player_presence() is not None:return False
    p=sim.player_pos
    for dx,dy in ((0,0),(1,0),(-1,0),(0,1),(0,-1)):
        q=p.moved(dx,dy);tile=sim.world.tile_at(q);fluid=sim.environment.fluid_at(q)
        if 'water' in tile.terrain.tags or (fluid and fluid.fluid=='water' and fluid.amount>10):return True
    return False

def _player_station_ids(sim:Simulation)->set[str]:
    # The same authoritative read is also usable by lightweight UI fixtures.
    return Simulation._player_station_ids(sim)

def _process_carcass_menu(ctx:GameContext,term:Terminal)->str:
    sim=ctx.sim;reg=ctx.registry;rows=[]
    for c in sim.processing.nearby_carcasses(sim.player_pos,1):
        sp=reg.species.get(c.species_id);state=[]
        if c.skinned:state.append('skinned')
        if c.butchered:state.append('butchered')
        if c.deboned:state.append('deboned')
        embedded=sum(c.embedded_items.values())
        rows.append((c.uid,f'{sp.name if sp else c.species_id} — quality {c.quality}%'+(f' — {", ".join(state)}' if state else '')+(f' — {embedded} embedded projectile(s)' if embedded else '')))
    uid=_select(term,'CARCASSES WITHIN REACH',rows)
    if not uid:return UI_BACK
    c=sim.state.carcasses[uid];sp=reg.species.get(c.species_id);actions=[]
    if c.embedded_items:actions.append(('recover','Recover embedded arrows / thrown weapons'))
    if any(str(p.get('name','')) not in c.harvested_parts for p in (sp.harvest_parts if sp else ())):
        actions.append(('anatomy','Harvest organs / anatomical parts — damage and animal size affect yield'))
    if not c.skinned:actions.append(('skin','Skin — remove hide before butchering for the best hide'))
    if not c.butchered:actions.append(('butcher','Butcher — separate bulk meat and fat'))
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
    sim=ctx.sim;reg=ctx.registry;inv=ctx.entities.get(ctx.player_id,Inventory);stations=_player_station_ids(sim);water=_nearby_water(sim) or inv.count('core:clean_water')>0
    methods=[]
    for m in reg.cooking_methods.values():
        station=reg.structures[m.station].name if m.station in reg.structures else m.station
        ready=m.station in stations and (not m.cookware or inv.count(m.cookware)>0) and (not m.requires_water or water)
        note=[]
        if m.station not in stations:note.append(station)
        if m.cookware and inv.count(m.cookware)<=0:note.append(reg.items[m.cookware].name)
        if m.requires_water and not water:note.append('water')
        status='READY' if ready else 'NEEDS'
        methods.append((m.id,f'[{status}] {m.name} — {m.min_ingredients}-{m.max_ingredients} ingredients — {m.minutes}m'+(f' — needs {", ".join(note)}' if note else '')))
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

def _hunt_action(ctx:GameContext,term:Terminal,initial:WorldPos|None=None)->str:
    sim=ctx.sim;reg=ctx.registry;inv=ctx.entities.get(ctx.player_id,Inventory);weapon=sim.combat.readied_weapon(inv)
    if not weapon or weapon.range<=1:return 'Ready a ranged or throwable weapon first.'
    p=sim.player_pos;renderer=Renderer(reg);zone='center'
    if initial is not None:
        cursor=initial
    else:
        candidates=[c for c in sim.state.creatures.values() if c.hp>0 and c.z==p.z and abs(c.x-p.x)+abs(c.y-p.y)<=weapon.range and sim._visible_from(p,WorldPos(c.x,c.y,c.z))]
        target=min(candidates,key=lambda c:abs(c.x-p.x)+abs(c.y-p.y),default=None)
        cursor=WorldPos(target.x,target.y,target.z) if target else p.moved(1,0)
    zones={'1':'center','2':'vitals','3':'head','4':'legs'}
    while True:
        c=next((c for c in sim.state.creatures.values() if c.hp>0 and (c.x,c.y,c.z)==(cursor.x,cursor.y,cursor.z)),None)
        desc=(reg.species[c.species_id].name if c else 'No animal');dist=abs(cursor.x-p.x)+abs(cursor.y-p.y)
        aim=sim.state.player_aim_quality if c and sim.state.player_aim_target==c.uid and sim.state.player_aim_zone==zone else 0
        overlay=ranged_overlay(sim,weapon,cursor,zone)
        difficulty=overlay.get('cursor_difficulty','outside sector')
        _present_game_frame(term,ctx,renderer,f'AIM: {desc} | {weapon.name} | range {dist}/{weapon.range} | {difficulty.upper()} | zone {zone} | aim {aim}/100 | A steady | Enter fire | 1 center 2 vitals 3 head 4 legs | Esc',cursor,overlay)
        k=term.read_key();low=k.lower() if len(k)==1 else k
        if k.startswith('UI_TARGET_HOVER:'):
            _,x,y=k.split(':');n=WorldPos(int(x),int(y),p.z)
            if 1<=abs(n.x-p.x)+abs(n.y-p.y)<=weapon.range:cursor=n
            continue
        if k.startswith('UI_WORLD:'):
            _,x,y=k.split(':');n=WorldPos(int(x),int(y),p.z)
            if 1<=abs(n.x-p.x)+abs(n.y-p.y)<=weapon.range:cursor=n
            continue
        if low in ('ESC','q'):return UI_BACK
        if low in zones:zone=zones[low];continue
        if low in DIRECTION_KEYS:
            dx,dy=DIRECTION_KEYS[low];n=cursor.moved(dx,dy)
            if abs(n.x-p.x)+abs(n.y-p.y)<=weapon.range:cursor=n
            continue
        if low=='a':
            if not c:continue
            uid=c.uid;sim.execute(AimCommand(ctx.player_id,uid,zone))
            moved=sim.state.creatures.get(uid)
            if moved:cursor=WorldPos(moved.x,moved.y,moved.z)
            continue
        if low in ('ENTER',' ','\r','\n'):
            if not c:continue
            sim.execute(RangedAttackCommand(ctx.player_id,c.uid));return sim.log[-1].message if sim.log else ''

def _melee_attack_action(ctx:GameContext,term:Terminal,initial:WorldPos|None=None)->str:
    sim=ctx.sim;reg=ctx.registry;inv=ctx.entities.get(ctx.player_id,Inventory);weapon=sim.combat.readied_weapon(inv)
    if weapon and 'ranged' in weapon.tags and not weapon.throwable:return f'The {weapon.name.lower()} is not suited to melee.'
    p=sim.player_pos;reach=max(1,weapon.reach if weapon else 1);renderer=Renderer(reg);mode='standard'
    mode_keys={'1':'standard','2':'quick','3':'power','4':'thrust'}
    if initial is not None:
        cursor=initial
    else:
        candidates=[c for c in sim.state.creatures.values() if c.hp>0 and c.z==p.z and 1<=abs(c.x-p.x)+abs(c.y-p.y)<=reach]
        target=min(candidates,key=lambda c:abs(c.x-p.x)+abs(c.y-p.y),default=None)
        cursor=WorldPos(target.x,target.y,target.z) if target else p.moved(1,0)
    while True:
        allowed=sim.combat.available_melee_modes(weapon)
        if mode not in allowed:mode='standard'
        profile=sim.combat.melee_mode_profile(weapon,mode)
        dist=abs(cursor.x-p.x)+abs(cursor.y-p.y)
        c=next((c for c in sim.state.creatures.values() if c.hp>0 and (c.x,c.y,c.z)==(cursor.x,cursor.y,cursor.z)),None)
        desc=reg.species[c.species_id].name if c else 'Empty tile'
        overlay=melee_overlay(sim,weapon,cursor,mode);difficulty=overlay.get('cursor_difficulty','out of reach')
        name=weapon.name if weapon else 'Unarmed'
        mode_help=' '.join(f'{i}:{m}' for i,m in mode_keys.items() if m in allowed)
        cost=sim.combat.melee_stamina_cost(weapon,mode)
        _present_game_frame(term,ctx,renderer,f'MELEE: {desc} | {name} | {mode.upper()} | reach {dist}/{reach} | {difficulty.upper()} | stamina {cost} | {mode_help} | Enter attack | Esc',cursor,overlay)
        k=term.read_key();low=k.lower() if len(k)==1 else k
        if k.startswith('UI_TARGET_HOVER:'):
            _,x,y=k.split(':');n=WorldPos(int(x),int(y),p.z)
            if 1<=abs(n.x-p.x)+abs(n.y-p.y)<=reach:cursor=n
            continue
        if k.startswith('UI_WORLD:'):
            _,x,y=k.split(':');n=WorldPos(int(x),int(y),p.z)
            if 1<=abs(n.x-p.x)+abs(n.y-p.y)<=reach:cursor=n
            continue
        if low in ('ESC','q'):return UI_BACK
        if low in mode_keys and mode_keys[low] in allowed:mode=mode_keys[low];continue
        if low in DIRECTION_KEYS:
            dx,dy=DIRECTION_KEYS[low];n=cursor.moved(dx,dy)
            if 1<=abs(n.x-p.x)+abs(n.y-p.y)<=reach:cursor=n
            continue
        if low in ('ENTER',' ','\r','\n'):
            if not c:continue
            sim.execute(AttackCommand(ctx.player_id,cursor.x-p.x,cursor.y-p.y,mode));return sim.log[-1].message if sim.log else ''

def _shield_bash_action(ctx:GameContext,term:Terminal)->str:
    sim=ctx.sim;reg=ctx.registry;shield=sim.combat.equipped_shield()
    if not shield:return 'Equip a shield before attempting a bash.'
    p=sim.player_pos;renderer=Renderer(reg)
    candidates=[c for c in sim.state.creatures.values() if c.hp>0 and c.z==p.z and abs(c.x-p.x)+abs(c.y-p.y)==1]
    target=min(candidates,key=lambda c:c.uid,default=None)
    cursor=WorldPos(target.x,target.y,target.z) if target else p.moved(1,0)
    while True:
        c=next((c for c in sim.state.creatures.values() if c.hp>0 and (c.x,c.y,c.z)==(cursor.x,cursor.y,cursor.z)),None)
        desc=reg.species[c.species_id].name if c else 'Empty tile'
        overlay=melee_overlay(sim,None,cursor,'standard')
        _present_game_frame(term,ctx,renderer,f'SHIELD BASH: {desc} | {shield.name} | adjacent | Enter bash | Esc',cursor,overlay)
        k=term.read_key();low=k.lower() if len(k)==1 else k
        if k.startswith('UI_TARGET_HOVER:') or k.startswith('UI_WORLD:'):
            _,x,y=k.split(':');n=WorldPos(int(x),int(y),p.z)
            if abs(n.x-p.x)+abs(n.y-p.y)==1:cursor=n
            continue
        if low in ('ESC','q'):return UI_BACK
        if low in DIRECTION_KEYS:
            dx,dy=DIRECTION_KEYS[low];cursor=p.moved(dx,dy);continue
        if low in ('ENTER',' ','\r','\n'):
            if not c:continue
            sim.execute(ShieldBashCommand(ctx.player_id,cursor.x-p.x,cursor.y-p.y));return sim.log[-1].message if sim.log else ''

def _disengage_action(ctx:GameContext,term:Terminal)->str:
    sim=ctx.sim;reg=ctx.registry;p=sim.player_pos;renderer=Renderer(reg);cursor=p.moved(1,0)
    while True:
        _present_game_frame(term,ctx,renderer,'DISENGAGE: choose an adjacent retreat tile that increases distance from every adjacent threat | Enter retreat | Esc',cursor)
        k=term.read_key();low=k.lower() if len(k)==1 else k
        if k.startswith('UI_TARGET_HOVER:') or k.startswith('UI_WORLD:'):
            _,x,y=k.split(':');n=WorldPos(int(x),int(y),p.z)
            if abs(n.x-p.x)+abs(n.y-p.y)==1:cursor=n
            continue
        if low in ('ESC','q'):return UI_BACK
        if low in DIRECTION_KEYS:
            dx,dy=DIRECTION_KEYS[low];cursor=p.moved(dx,dy);continue
        if low in ('ENTER',' ','\r','\n'):
            sim.execute(DisengageCommand(ctx.player_id,cursor.x-p.x,cursor.y-p.y))
            return sim.log[-1].message if sim.log else ''

def _combat_arena_menu(ctx:GameContext,term:Terminal)->str:
    """Developer combat laboratory that uses authoritative simulation commands."""
    sim=ctx.sim;reg=ctx.registry;pid=ctx.player_id
    nav=NavigationStack(RouteState('arena','COMBAT TEST ARENA'));status=''
    root=[
        ('presets','Load practice orientation'),
        ('items','Spawn weapons, shields & ammunition'),
        ('animals','Spawn an animal at a chosen bearing/range'),
        ('stats','Set combat skills / attributes'),
        ('injuries','Apply or heal injury states'),
        ('hits','Simulate incoming melee / ranged hits'),
        ('clear','Clear test animals and restore player'),
    ]
    while True:
        route=nav.current
        if route.route_id=='arena':
            choice=_stack_menu(term,nav,root,subtitle=status or 'Local test entities have no ecology cohort and do not affect wildlife populations.')
            status=''
            if choice is None:return UI_BACK
            if choice=='__BACK__':continue
            if choice=='clear':
                sim.execute(ArenaClearCommand(pid,True));status=sim.log[-1].message if sim.log else '';continue
            nav.push(RouteState('arena:'+choice,choice.replace('_',' ').title()))
            continue
        if route.route_id=='arena:presets':
            pick=_stack_menu(term,nav,[
                ('close','Close-combat ring — threats from four orientations'),
                ('ranged','Ranged lane — multiple ranges + flank threat'),
                ('injury','Injury lab — fracture, bleeding, treatment & shields'),
                ('shield','Shield gauntlet — all shield types + opposite threats'),
                ('tactics','Tactical AI field — charges, wolf flanks & herd panic'),
            ])
            if pick=='__BACK__':continue
            if pick is None:return UI_BACK
            sim.execute(ArenaPresetCommand(pid,pick));status=sim.log[-1].message if sim.log else '';nav.back();continue
        if route.route_id=='arena:items':
            rows=[]
            for item in ordered_items(reg.items.values()):
                if item.weapon_damage>0 or 'shield' in item.tags or 'ammo' in item.tags:
                    amount=20 if 'ammo' in item.tags else 1
                    role='shield' if 'shield' in item.tags else item.weapon_class or item.damage_type
                    rows.append((item.id,f'{item.name} — {role} — spawn x{amount}'))
            pick=_stack_menu(term,nav,rows)
            if pick=='__BACK__':continue
            if pick is None:return UI_BACK
            item=reg.items[pick];amount=20 if 'ammo' in item.tags else 1
            sim.execute(ArenaSpawnItemCommand(pid,pick,amount));status=sim.log[-1].message if sim.log else '';nav.back();continue
        if route.route_id=='arena:animals':
            rows=[(sp.id,f'{sp.name} — HP {sp.max_hp} | aggression {sp.aggression} | speed {sp.speed}') for sp in sorted(reg.species.values(),key=lambda q:q.name)]
            pick=_stack_menu(term,nav,rows)
            if pick=='__BACK__':continue
            if pick is None:return UI_BACK
            nav.push(RouteState('arena:animal_position','SPAWN ORIENTATION',payload={'species_id':pick}));continue
        if route.route_id=='arena:animal_position':
            orientations=[
                ('1,0','East adjacent'),('-1,0','West adjacent'),('0,-1','North adjacent'),('0,1','South adjacent'),
                ('2,0','East 2 — close reach drill'),('-2,0','West 2 — close reach drill'),
                ('4,0','East 4 — short ranged'),('0,-4','North 4 — short ranged'),
                ('7,0','East 7 — medium ranged'),('0,7','South 7 — medium ranged'),
                ('9,0','East 9 — long ranged'),('-6,-3','Northwest flank — 9 total range'),
            ]
            pick=_stack_menu(term,nav,orientations)
            if pick=='__BACK__':continue
            if pick is None:return UI_BACK
            dx,dy=(int(v) for v in pick.split(','))
            sim.execute(ArenaSpawnCreatureCommand(pid,route.payload['species_id'],dx,dy));status=sim.log[-1].message if sim.log else ''
            nav.back();nav.back();continue
        if route.route_id=='arena:stats':
            rows=[]
            for key,val in sorted(sim.state.player_attributes.items()):rows.append(('attribute|'+key,f'Attribute — {key.title()} = {val}'))
            for key,val in sorted(sim.state.player_skills.items()):rows.append(('skill|'+key,f'Skill — {key.replace("_"," ").title()} = {val}'))
            pick=_stack_menu(term,nav,rows)
            if pick=='__BACK__':continue
            if pick is None:return UI_BACK
            kind,key=pick.split('|',1);nav.push(RouteState('arena:stat_value','SET TEST VALUE',payload={'kind':kind,'key':key}));continue
        if route.route_id=='arena:stat_value':
            lo=1 if route.payload['kind']=='attribute' else 0
            values=sorted(set([lo,2,5,8,10,12,15,20]))
            pick=_stack_menu(term,nav,[(str(v),f'{route.payload["key"].replace("_"," ").title()} → {v}') for v in values if v>=lo])
            if pick=='__BACK__':continue
            if pick is None:return UI_BACK
            sim.execute(ArenaSetStatCommand(pid,route.payload['kind'],route.payload['key'],int(pick)));status=sim.log[-1].message if sim.log else ''
            nav.back();nav.back();continue
        if route.route_id=='arena:injuries':
            pick=_stack_menu(term,nav,[
                ('heal','Heal / reset all combat injuries'),('light_cut','Light torso cut'),
                ('bleeding_torso','Heavy bleeding torso wound'),('arm_fracture','Left-arm fracture'),
                ('leg_fracture','Left-leg fracture'),('exhausted','Severe stamina exhaustion'),
            ])
            if pick=='__BACK__':continue
            if pick is None:return UI_BACK
            sim.execute(ArenaInjuryCommand(pid,pick));status=sim.log[-1].message if sim.log else '';nav.back();continue
        if route.route_id=='arena:hits':
            tests=[
                ('melee|blunt|12|front|torso|','Front melee blunt — no active defense'),
                ('melee|blunt|12|front|torso|dodge','Front melee blunt — DODGE test'),
                ('melee|pierce|12|front|torso|parry','Front melee pierce — PARRY test'),
                ('melee|blunt|18|front|torso|guard','Front heavy impact — SHIELD GUARD test'),
                ('melee|blunt|18|front|torso|brace','Front heavy impact — SHIELD BRACE test'),
                ('melee|cut|10|side|left_arm|guard','Side melee cut — guard angle test'),
                ('melee|blunt|16|rear|head|guard','Rear heavy melee — guard failure-angle test'),
                ('ranged|pierce|12|front|torso|dodge','Front arrow — DODGE test'),
                ('ranged|pierce|12|front|torso|guard','Front arrow — SHIELD GUARD test'),
                ('ranged|pierce|12|side|torso|guard','Side arrow — shield angle test'),
                ('ranged|pierce|16|rear|torso|guard','Rear projectile — shield rear coverage test'),
            ]
            pick=_stack_menu(term,nav,tests,subtitle='Defense mode is injected only for this arena strike; front/side/rear follow current facing.')
            if pick=='__BACK__':continue
            if pick is None:return UI_BACK
            kind,dtype,damage,bearing,part,defense=pick.split('|')
            fx=int(sim.state.player_facing_dx);fy=int(sim.state.player_facing_dy)
            if fx==0 and fy==0:fx,fy=0,1
            if bearing=='front':dx,dy=fx,fy
            elif bearing=='rear':dx,dy=-fx,-fy
            else:dx,dy=-fy,fx
            sim.execute(ArenaIncomingHitCommand(pid,kind,dtype,int(damage),dx,dy,part,defense));status=sim.log[-1].message if sim.log else '';nav.back();continue


def _hunting_stance_menu(ctx:GameContext,term:Terminal)->str:
    sim=ctx.sim;current=str(getattr(sim.state,'player_hunting_stance','normal'))
    weather=sim.environment.weather.at(sim.clock.minute,sim.player_pos.x,sim.player_pos.y)
    wx=int(weather.get('wind_dx',0));wy=int(weather.get('wind_dy',0))
    wind='calm'
    if wx or wy:
        horiz='east' if wx>0 else 'west' if wx<0 else ''
        vert='south' if wy>0 else 'north' if wy<0 else ''
        wind='-'.join(x for x in (vert,horiz) if x)
    pick=_select(term,'STEALTH / STALKING',[
        ('normal',f'Normal{" [CURRENT]" if current=="normal" else ""} — fastest; no concealment stance'),
        ('stalk',f'Stalk{" [CURRENT]" if current=="stalk" else ""} — slower, quieter; observer cones enabled'),
        ('crouch',f'Crouch{" [CURRENT]" if current=="crouch" else ""} — slowest, strongest visual/noise concealment'),
        ('aggressive',f'Aggressive Stance{" [CURRENT]" if current=="aggressive" else ""} — lockpicking and door bashing'),
    ],subtitle=f'Wind: {wind}. Scent still carries downwind; stance cannot hide scent.')
    if not pick:return UI_BACK
    sim.execute(SetHuntingStanceCommand(ctx.player_id,pick))
    return sim.log[-1].message if sim.log else ''

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
            group=route.payload['group'];options=submenus[group]
            if group=='interact' and getattr(ctx.sim,'homestead',None) is not None:
                from worldseed.systems.homestead_blueprints import doorway,door_uid
                p=ctx.sim.player_pos
                cabin_entries=[('enter_cabin:'+site['uid'],'Enter your log cabin')
                               for site in ctx.sim.state.homesteads.values()
                               if int(site['stage'])==4 and (p.x,p.y,p.z)==doorway(site)[1]
                               and ctx.sim.property_security.door_by_id(door_uid(site)) is not None]
                options=cabin_entries+list(options)
            action=_stack_menu(term,nav,options)
            if action is None:return ''
            if action=='__BACK__':continue
            if action.startswith('enter_cabin:'):
                from worldseed.systems.homestead_blueprints import door_uid
                site=ctx.sim.homestead.completed(action.split(':',1)[1])
                if site is None:continue
                ctx.sim.execute(EnterInteriorCommand(ctx.player_id,door_uid(site)))
                return ctx.sim.log[-1].message if ctx.sim.log else ''
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
            if action=='collect_water':ctx.sim.execute(CollectWaterCommand(ctx.player_id));return ctx.sim.log[-1].message if ctx.sim.log else ''
            if action=='fish':
                result=_fishing_action(ctx,term)
                if result==UI_BACK:continue
                return result
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
            if action=='dodge':
                ctx.sim.execute(DodgeCommand(ctx.player_id));return ctx.sim.log[-1].message if ctx.sim.log else ''
            if action=='parry':
                ctx.sim.execute(ParryCommand(ctx.player_id));return ctx.sim.log[-1].message if ctx.sim.log else ''
            if action=='guard':
                ctx.sim.execute(GuardCommand(ctx.player_id));return ctx.sim.log[-1].message if ctx.sim.log else ''
            if action=='brace':
                ctx.sim.execute(BraceCommand(ctx.player_id));return ctx.sim.log[-1].message if ctx.sim.log else ''
            if action=='bash':
                result=_shield_bash_action(ctx,term)
                if result==UI_BACK:continue
                return result
            if action=='disengage':
                result=_disengage_action(ctx,term)
                if result==UI_BACK:continue
                return result
            if action=='arena':
                result=_combat_arena_menu(ctx,term)
                if result==UI_BACK:continue
                return result
            if action=='talk':
                result=_talk_action(ctx,term)
                if result==UI_BACK:continue
                return result
            if action=='stealth':
                result=_hunting_stance_menu(ctx,term)
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

def _container_reach_error(sim,container):
    if getattr(container,'interior_space_id',''):
        if not sim.interiors.container_in_reach(container.uid):
            return 'Move closer to this container; walls block interaction.'
    elif abs(container.x-sim.player_pos.x)+abs(container.y-sim.player_pos.y)>1 or container.z!=sim.player_pos.z:
        return 'Move next to the storage before opening it.'
    if sim.property_storage.blocks_actor(container,'player'):
        return 'This container is locked. Its contents are concealed.'
    return ''


def _storage_menu_terminal(ctx:GameContext,term:Terminal,container_uid:str|None=None)->str:
    sim=ctx.sim;reg=ctx.registry;pid=ctx.player_id;inv=ctx.entities.get(pid,Inventory)
    c=next((row for row in sim.state.containers.values() if row.uid==container_uid),None) if container_uid else sim.building.nearby_container(sim.player_pos)
    if not c and container_uid:
        _view_text(term,box('STORAGE',['That container is no longer available.'],screen_width(term.size()[0],88)));return UI_BACK
    if not c:
        _view_text(term,box('STORAGE',['No accessible container is adjacent to you.'],screen_width(term.size()[0],88)));return UI_BACK
    error=_container_reach_error(sim,c)
    if error:return error
    private=c.kind=='property' and c.owner!='player' and c.access!='public'
    nav=NavigationStack(RouteState('storage','Nearby Storage'))
    while True:
        route=nav.current
        if route.route_id=='storage':
            mass,volume=sim.building.container_load(c)
            choice=_stack_menu(term,nav,[
                ('store',f'Store item — {mass/1000:.1f}/{c.capacity_mass_g/1000:.1f} kg'),
                ('take',f'{"Steal" if private else "Take"} item — {volume/1000:.1f}/{c.capacity_volume_ml/1000:.1f} L'+(' — requires Stalk mode' if private and sim.state.player_hunting_stance!='stalk' else '')),
                ('inspect',f'Inspect contents — {sum(c.items.values())} items'),
            ])
            if choice is None:return UI_BACK
            if choice=='__BACK__':continue
            if choice=='inspect':
                rows=[f'{reg.items[iid].name if iid in reg.items else iid} x{n}' for iid,n in sorted(c.items.items()) if n>0]
                nav.push(RouteState('storage-inspect','Container Contents'))
                _stack_view(term,nav,box('CONTAINER CONTENTS',rows or ['Empty.'],screen_width(term.size()[0],96)))
                continue
            if choice=='take' and private and sim.state.player_hunting_stance!='stalk':
                return 'Select Stalk mode before stealing from private storage.'
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
            sim.execute(StoreCommand(pid,iid,1,c.uid) if mode=='store' else
                        (StealContainerCommand(pid,c.uid,iid,1) if private else TakeFromContainerCommand(pid,iid,1,c.uid)))
            return sim.log[-1].message if sim.log else ''
        if not nav.back():return UI_BACK


def _storage_menu(ctx:GameContext,term:Terminal,container_uid:str|None=None)->str:
    """One-screen graphical transfer view with terminal fallback."""
    if not (getattr(term,'mouse_ui',False) and callable(getattr(term,'present_feature_menu',None))):
        return _storage_menu_terminal(ctx,term,container_uid)
    sim=ctx.sim;reg=ctx.registry;pid=ctx.player_id;inv=ctx.entities.get(pid,Inventory)
    container=next((c for c in sim.state.containers.values() if c.uid==container_uid),None) if container_uid else sim.building.nearby_container(sim.player_pos)
    if not container and container_uid:
        _view_text(term,box('STORAGE',['That container is no longer available.'],screen_width(term.size()[0],88)));return UI_BACK
    if not container:
        _view_text(term,box('STORAGE',['No accessible container is adjacent to you.'],screen_width(term.size()[0],88)));return UI_BACK
    error=_container_reach_error(sim,container)
    if error:return error
    private=container.kind=='property' and container.owner!='player' and container.access!='public'
    uid=container.uid
    nav=NavigationStack(RouteState('container-inventory','CONTAINER STORAGE'))
    action_amount=1;last_selected=None;status='';container_query=''
    while True:
        container=next((row for row in sim.state.containers.values() if row.uid==uid),None)
        if not container:return status or UI_BACK
        error=_container_reach_error(sim,container)
        if error:return error
        inv=ctx.entities.get(pid,Inventory)
        pack_data=_inventory_ui_data(reg,inv,sim)
        container_data=_inventory_ui_data(reg,Inventory(dict(container.items)),sim,False)
        entries={};rows=[]
        pack_rows=[];container_rows=[]
        for iid,meta in pack_data['items'].items():
            if container_query and container_query.casefold() not in meta['name'].casefold():continue
            key=f'pack|{iid}';entries[key]={**meta,'side':'pack','iid':iid};pack_rows.append((key,f"{meta['name']} x{meta['count']}"))
        for iid,meta in container_data['items'].items():
            if container_query and container_query.casefold() not in meta['name'].casefold():continue
            key=f'container|{iid}';entries[key]={**meta,'side':'container','iid':iid};container_rows.append((key,f"{meta['name']} x{meta['count']}"))
        for i in range(max(len(pack_rows),len(container_rows))):
            if i<len(pack_rows):rows.append(pack_rows[i])
            if i<len(container_rows):rows.append(container_rows[i])
        if not rows:rows=[('__empty__','Both inventories are empty')]
        route=nav.current;route.selected=max(0,min(route.selected,len(rows)-1))
        selected_key=rows[route.selected][0]
        if selected_key!=last_selected:action_amount=1;last_selected=selected_key
        meta=entries.get(selected_key,{})
        count=int(meta.get('count',0));action_amount=max(1,min(action_amount,max(1,count)))
        mass,volume=sim.building.container_load(container)
        data={
            'entries':entries,'selected_key':selected_key,'action_amount':action_amount,
            'pack':pack_data,'container_items':container_data,
            'container':{
                'uid':container.uid,'name':container.name or 'Container','kind':container.kind,
                'condition':container.condition,'movable':container.movable,
                'mass_kg':mass/1000.0,'volume_l':volume/1000.0,
                'capacity_mass_kg':container.capacity_mass_g/1000.0,
                'capacity_volume_l':container.capacity_volume_ml/1000.0,
                'item_count':sum(container.items.values()),'stack_count':len(container.items),
            },
        }
        subtitle=status or ('Private storage: removing items is theft. Select Stalk mode; locks and witnesses still matter.' if private else 'Click either side • right-click for actions • Shift-click transfers the full stack. Natural containers can also be moved or broken apart.')
        status=''
        choice=_stack_menu(term,nav,rows,subtitle=subtitle,presentation='container_inventory',presentation_data=data)
        if choice is None:return UI_BACK
        if choice=='__BACK__':continue
        moved=_live_panel_world_move(ctx,term,choice)
        if moved is not None:
            if _container_reach_error(sim,container):
                return moved or 'You move away from the container.'
            status=moved;continue
        if not choice.startswith('UI_ACTION:'):
            last_selected=choice;action_amount=1;continue
        if choice=='UI_ACTION:container_search':
            value=prompt_text(term,'STORAGE // SEARCH','Filter both inventories (blank clears):',default=container_query,max_len=48)
            if value is not None:
                container_query=value;route.selected=0;route.scroll=0;last_selected=None
            continue
        if choice in ('UI_ACTION:store_many','UI_ACTION:take_many'):
            if choice.endswith('take_many') and private and sim.state.player_hunting_stance!='stalk':
                status='Select Stalk mode before stealing from private storage.'
                continue
            source=inv.items if choice=='UI_ACTION:store_many' else container.items
            transferred=0
            for iid,qty in sorted(source.items()):
                if transferred>=12:break
                if qty<=0 or iid not in reg.items:continue
                if container_query and container_query.casefold() not in reg.items[iid].name.casefold():continue
                before=inv.count(iid) if choice=='UI_ACTION:store_many' else container.items.get(iid,0)
                command=(StoreCommand(pid,iid,qty,uid) if choice=='UI_ACTION:store_many'
                         else StealContainerCommand(pid,uid,iid,qty) if private
                         else TakeFromContainerCommand(pid,iid,qty,uid))
                sim.execute(command)
                after=inv.count(iid) if choice=='UI_ACTION:store_many' else container.items.get(iid,0)
                if before>after:transferred+=1
            status=(f'Transferred {transferred} stacks.' if transferred
                    else 'Nothing transferable; check capacity, locks and access.')
            route.selected=0;route.scroll=0;last_selected=None
            continue
        if rows and 0<=route.selected<len(rows):
            selected_key=rows[route.selected][0];meta=entries.get(selected_key,{})
            count=int(meta.get('count',0))
            if selected_key!=last_selected:action_amount=1;last_selected=selected_key
        action=choice.split(':',1)[1]
        if action=='qty_down':action_amount=max(1,action_amount-1);continue
        if action=='qty_up':action_amount=min(max(1,count),action_amount+1);continue
        if action=='qty_all':action_amount=max(1,count);continue
        if action=='split':
            action_amount=max(1,(count+1)//2);status=f'Half-stack selected: {action_amount} of {count}.';continue
        if action in ('transfer','quick_transfer') and meta:
            iid=meta['iid'];amount=count if action=='quick_transfer' else min(action_amount,count)
            if meta['side']=='pack':sim.execute(StoreCommand(pid,iid,amount,uid))
            else:sim.execute(StealContainerCommand(pid,uid,iid,amount) if private else TakeFromContainerCommand(pid,iid,amount,uid))
            status=sim.log[-1].message if sim.log else '';last_selected=None;action_amount=1;continue
        if action.startswith('move:'):
            try:_,dx,dy=action.split(':');dx=int(dx);dy=int(dy)
            except Exception:continue
            sim.execute(MoveContainerCommand(pid,uid,dx,dy))
            status=sim.log[-1].message if sim.log else '';continue
        if action=='destroy':
            sim.execute(DestroyContainerCommand(pid,uid))
            return sim.log[-1].message if sim.log else ''
        continue



def _npc_need_status(value:int)->str:
    value=max(0,min(100,int(value)))
    if value>=80:return 'urgent'
    if value>=60:return 'high'
    if value>=30:return 'moderate'
    return 'low'


def _npc_profile_data(sim:Simulation,npc,active_tab:str)->dict:
    town=sim.state.settlements.get(npc.settlement_id)
    known=sim.known_npc_ids()
    rel_player=npc.relationships.get('player',{})
    familiarity=int(rel_player.get('familiarity',0))
    introduced=npc.uid in known and npc.uid in sim.state.introduced_npcs
    home=sim.settlement_physicalization.structure_by_id(npc.home_id) if introduced and npc.home_id else None
    work=sim.settlement_physicalization.structure_by_id(npc.workplace_id) if introduced and npc.workplace_id else None
    name=npc.name if npc.uid in known else 'Stranger'
    occupation=npc.occupation.replace('_',' ').title() if npc.uid in known else 'Unknown'
    summary={
        'name':name,'age':npc.age if npc.uid in known else None,'occupation':occupation,
        'settlement':town.name if town and town.uid in sim.known_settlement_ids() else 'Unknown',
        'activity':activity_label(npc),
        'home':home.function.replace('_',' ').title() if home else '',
        'workplace':work.function.replace('_',' ').title() if work else '',
        'traits':[str(v).title() for v in npc.traits] if familiarity>=16 else [],
        'familiarity':familiarity,
    }
    tabs={}
    worn=[]
    for slot,iid in sorted(getattr(npc,'equipment',{}).items()):
        if int(npc.inventory.get(iid,0))<=0:continue
        item=sim.registry.items.get(iid)
        if item is not None:
            worn.append(item.name)
    visible_injuries=[]
    if npc.hp<85:visible_injuries.append('Visible wounds or impaired movement')
    if npc.infections and npc.hp<70:visible_injuries.append('Visible signs of illness')
    tabs['appearance']=[('Wearing',', '.join(worn) if worn else 'No identifiable equipment'),
                        ('Visible injuries',', '.join(visible_injuries) if visible_injuries else 'None apparent')]
    if npc.uid not in known or npc.uid not in sim.state.introduced_npcs:
        summary={'name':'Stranger','age':None,'occupation':'Unknown','settlement':'Unknown',
                 'activity':'Unknown','home':'','workplace':'','traits':[],'familiarity':0}
        tabs['overview']=[('Identity','Not introduced'),('Information','Introduce yourself to learn about this person')]
        return {'summary':summary,'tabs':tabs,'active_tab':active_tab,'portrait':_npc_portrait(sim,npc)}
    overview=[
        ('Age',str(npc.age) if npc.uid in known else 'Unknown'),
        ('Occupation',occupation),
        ('Settlement',summary['settlement']),
        ('Current activity',summary['activity']),
        ('Position',f'{npc.x}, {npc.y}, z{npc.z}'),
    ]
    if summary['home']:overview.append(('Home',summary['home']))
    if summary['workplace']:overview.append(('Workplace',summary['workplace']))
    if familiarity>=16 and npc.traits:overview.append(('Traits',', '.join(x.title() for x in npc.traits)))
    if familiarity>=24 and npc.wants:overview.append(('Wants',', '.join(str(x) for x in npc.wants[:3])))
    if familiarity>=32 and npc.backstory:
        for key in ('birthplace','upbringing','formative_event','ambition'):
            if npc.backstory.get(key):
                overview.append((key.replace('_',' ').title(),str(npc.backstory[key]).capitalize()))
    summary['schedule']=schedule_label(npc,getattr(sim,'seed',b''),sim.state.clock_minute)
    overview.append(('Scheduled now',summary['schedule']))
    overview.append(('Personal timeline','Needs and urgent situations can interrupt these plans'))
    overview.extend(timeline_rows(npc,getattr(sim,'seed',b'')))
    tabs['overview']=overview
    registry=getattr(sim,'registry',None)
    if registry is not None:tabs['belongings']=possessions_rows(npc,registry)

    def relative_row(uid,role):
        if not uid:return None
        other=sim.state.npcs.get(uid)
        if other is None:return (role,'Unknown')
        if uid not in known:return (role,'Unknown relative')
        return (role,f'{other.name}, age {other.age}')

    family=[]
    row=relative_row(npc.spouse_uid,'Spouse')
    if row:family.append(row)
    for uid in npc.parents:
        row=relative_row(uid,'Parent')
        if row:family.append(row)
    for uid in npc.children:
        row=relative_row(uid,'Child')
        if row:family.append(row)
    if not family:
        family=[('Family','No known relatives')]
    tabs['family']=family

    relations=[]
    for uid,rel in npc.relationships.items():
        if uid!='player' and uid not in known:continue
        if uid=='player':
            label=sim.state.player_name or 'You'
        else:
            other=sim.state.npcs.get(uid);label=other.name if other else 'Unknown'
        affection=int(rel.get('affection',0));trust=int(rel.get('trust',0))
        score=(affection+trust)//2
        tone='close' if score>=55 else 'friendly' if score>=20 else 'neutral' if score>=-20 else 'strained' if score>=-55 else 'hostile'
        notes=[tone]
        if int(rel.get('respect',0))>=45:notes.append('respect')
        if int(rel.get('fear',0))>=45:notes.append('fear')
        role=npc.kinship.get(uid,'').replace('_',' ').title()
        relations.append((label,(', '.join(notes)+(f' · {role}' if role else '')).capitalize()))
    relations.sort(key=lambda row:row[0])
    trust=int(rel_player.get('trust',0));affection=int(rel_player.get('affection',0))
    respect=int(rel_player.get('respect',0));community=DialogueSystem.settlement_standing(sim.state,npc.settlement_id)
    player_skill=getattr(sim,'player_skill',None)
    persuasion=int(player_skill('persuasion')) if callable(player_skill) else 0
    readiness=max(0,min(100,trust+familiarity//2+community//4+persuasion*2))
    social_rows=[
        ('Trust',f'{trust:+d}',(trust+100)//2),
        ('Affection',f'{affection:+d}',(affection+100)//2),
        ('Respect',f'{respect:+d}',(respect+100)//2),
        ('Familiarity',f'{familiarity}/100',familiarity),
        ('Community standing',f'{community:+d}',(community+100)//2),
        ('Information readiness',f'{readiness}/100',readiness),
    ]
    tabs['relations']=social_rows+relations[:4]

    needs=[
        ('Hunger',npc.hunger),('Thirst',npc.thirst),('Fatigue',npc.rest),
        ('Health',npc.needs.get('health',max(0,100-npc.hp))),
        ('Social',npc.needs.get('social',0)),('Safety',npc.needs.get('safety',0)),
        ('Faith',npc.needs.get('faith',0)),('Learning',npc.needs.get('learning',0)),
        ('Purpose',npc.needs.get('purpose',0)),
    ]
    tabs['needs']=[(label,_npc_need_status(value),max(0,min(100,int(value)))) for label,value in needs]

    history=[]
    if familiarity>=24:
        for memory in sorted(npc.memories,key=lambda row:int(row.get('minute',0)),reverse=True)[:8]:
            kind=str(memory.get('type','event')).replace('_',' ').title()
            subject=str(memory.get('subject',''))
            subject_label=''
            if subject=='player':subject_label=sim.state.player_name or 'You'
            elif subject in known and subject in sim.state.npcs:subject_label=sim.state.npcs[subject].name
            elif subject in sim.known_settlement_ids() and subject in sim.state.settlements:subject_label=sim.state.settlements[subject].name
            history.append((kind,subject_label or 'Known event'))
    if not history:
        history=[('History','No personal history has been learned yet')]
    tabs['history']=history

    return {'summary':summary,'tabs':tabs,'active_tab':active_tab,'portrait':_npc_portrait(sim,npc)}


def _npc_profile_menu(ctx:GameContext,term:Terminal,npc_uid:str)->str:
    sim=ctx.sim;npc=sim.state.npcs.get(npc_uid)
    if npc is None or not npc.alive:return UI_BACK
    introduced=npc.uid in sim.known_npc_ids() and npc.uid in sim.state.introduced_npcs
    tabs=(('overview','Overview'),('appearance','Worn / Injuries'),('belongings','Cash / Gear / Pack'),('family','Family'),('relations','Relations'),('needs','Needs'),('history','Learned History')) if introduced else (('appearance','Worn / Injuries'),('overview','Unknown person'))
    active='overview' if introduced else 'appearance'
    nav=NavigationStack(RouteState('npc-profile',npc.name if introduced else 'Stranger'))
    while True:
        initial=next((i for i,row in enumerate(tabs) if row[0]==active),0)
        data=_npc_profile_data(sim,npc,active)
        summary=data['summary']
        subtitle=f"{summary['occupation']} · {summary['settlement']} · {summary['activity']}"
        nav.current.selected=initial
        choice=_stack_menu(
            term,nav,list(tabs),subtitle=subtitle,
            presentation='npc_profile',presentation_data=data,
        )
        if not choice:return UI_BACK
        active=choice
        if active=='belongings' or not getattr(term,'mouse_ui',False):
            page=_npc_profile_data(sim,npc,active)['tabs'].get(active,())
            lines=[]
            for row in page:
                if active=='needs':
                    lines.append(f'{row[0]}: {row[1]}')
                else:
                    lines.append(f'{row[0]}: {row[1]}')
            nav.push(RouteState('npc-profile-'+active,f'{summary["name"]} · {active.title()}'))
            _stack_view(term,nav,'\n'.join(lines) or 'No known information.')


def _building_context_menu(ctx:GameContext,term:Terminal,building_uid:str,part:str)->str:
    """A roof pixel identifies a static object, never its hidden ground cell."""
    sim=ctx.sim
    if sim.interiors.player_presence() is not None or sim.player_pos.z!=0:return UI_BACK
    planned=sim.settlement_physicalization.structure_by_id(building_uid)
    from worldseed.systems.building_shells import enclosed_shell
    if not enclosed_shell(planned) or part not in ('body','door'):return UI_BACK
    known=sim.discovered_tiles_set
    observed=[(x,y) for x,y in planned.footprint if pos_key(x,y,0) in known]
    if not observed:return UI_BACK
    if part=='door':
        target=planned.entrance
        if target is None or pos_key(*target,0) not in known:return UI_BACK
    else:
        p=sim.player_pos
        target=min(observed,key=lambda cell:(abs(cell[0]-p.x)+abs(cell[1]-p.y),cell))
    return _world_context_menu(ctx,term,WorldPos(*target,0),building_part=part)


def _world_context_menu(ctx:GameContext,term:Terminal,target:WorldPos,*,building_part:str='')->str:
    """Context actions for a right-clicked world tile; only mutations enforce reach."""
    sim=ctx.sim;p=sim.player_pos
    if sim.interiors.player_presence() is not None:return UI_BACK
    if target.z!=p.z:return UI_BACK
    distance=abs(target.x-p.x)+abs(target.y-p.y)
    rows=[]
    shell=sim.settlement_physicalization.shell_at(target)
    container=None if shell or building_part else sim.building.container_at(target)
    pile=None if building_part else sim.state.ground_piles.get(pos_key(target.x,target.y,target.z))
    creature=None if building_part else next((c for c in sim.state.creatures.values() if c.hp>0 and (c.x,c.y,c.z)==(target.x,target.y,target.z)),None)
    npc=None if building_part else next((n for n in sim.state.npcs.values() if n.alive and n.uid not in sim.state.interior_actors and (n.x,n.y,n.z)==(target.x,target.y,target.z)),None)
    physical=sim.settlement_physicalization.cell_at(target)
    planned=sim.settlement_physicalization.structure_by_id(physical.structure_id) if physical and physical.structure_id else None
    crossing=None if building_part else sim.settlement_physicalization.crossing_at(target)
    border_post=None if building_part else sim.settlement_physicalization.border_post_at(target)
    door=None if building_part=='body' else sim.property_security.door_at(target)
    homestead=sim.homestead.at(target)
    signs=[] if building_part else sim.hunting.signs_at(target)
    home=None if building_part else sim.hunting.home_at(target)
    monument=None if building_part else next((m for m in sim.state.claim_monuments.values() if (m.x,m.y,target.z)==(target.x,target.y,target.z)),None)
    if creature:
        sp=sim.registry.species.get(creature.species_id)
        label=sp.name if sp and creature.species_id in sim.known_species_ids() else 'animal'
        rows.append(('observe_animal',f'Observe {label} — {creature.behavior.replace("_"," ")}'))
        inv=ctx.entities.get(ctx.player_id,Inventory);weapon=sim.combat.readied_weapon(inv)
        reach=weapon.reach if weapon else 1
        if 1<=distance<=reach:rows.append(('attack_animal',f'Attack {label} — reach {distance}/{reach}'))
        if weapon and weapon.range>1 and distance<=weapon.range and sim._visible_from(p,target):
            rows.append(('aim_animal',f'Aim at {label} — {weapon.name}'))
            rows.append(('shoot_animal',f'Fire at {label} — range {distance}/{weapon.range}'))
    if npc:
        known=npc.uid in sim.introduced_npc_ids()
        label=npc.name if known else 'Stranger'
        if known:rows.append(('inspect_npc',f'Inspect {label} — {npc.occupation.replace("_"," ")}'))
        else:rows.append(('observe_npc','Observe person — identity unknown'))
        if distance<=1:rows.append(('talk_npc',f'Talk to {label}'))
    if monument:
        rows.append(('inspect_monument',f'Inspect {monument.monument_type.replace("_"," ").title()}'))
    private_storage=bool(container and container.kind=='property' and container.owner!='player' and container.access!='public')
    fixture_piece=sim.registry.settlement_pieces.get(physical.fixture_piece_id) if not building_part and physical and physical.fixture_piece_id else None
    fixture_station=STATION_PIECE_ALIASES.get(str(physical.fixture_piece_id)) if not building_part and physical and physical.fixture_piece_id else None
    if door is not None and distance<=1:
        if (shell is not None or homestead is not None and homestead['stage']==4) and door.role=='entrance':
            rows.append(('enter_interior','Enter building interior'))
        if planned is not None and planned.function=='residence' and door.role=='entrance':
            rows.append(('knock_property_door','Knock and wait for a resident'))
        if door.locked and not door.forced and not sim.property_security.authorized_player(door):
            lock_label=sim.property_security.lock_band(door.lock_level)
            rows.append(('inspect_property_door',f'Inspect locked door — lock {lock_label}'))
            inv=ctx.entities.get(ctx.player_id,Inventory)
            if sim.state.player_hunting_stance=='aggressive' and inv.count('core:lockpick')>0:
                rows.append(('lockpick_property_door',f'Pick lock — {lock_label}'))
            elif sim.state.player_hunting_stance=='aggressive':
                rows.append(('lockpick_property_door','Pick lock — requires Lockpick'))
            if sim.state.player_hunting_stance=='aggressive':
                rows.append(('force_property_door',f'Force entry — door condition {door.condition}%'))
        elif door.forced:
            rows.append(('inspect_property_door',f'Inspect forced doorway — condition {door.condition}%'))
        else:
            rows.append(('inspect_property_door',f'Inspect doorway — condition {door.condition}%'))
    if fixture_piece is not None and distance<=1:
        rows.append(('inspect_fixture',f'Inspect {fixture_piece.name}'))
        if fixture_station in WORKSHOP_PROFILES:
            rows.append(('use_fixture',f'Use {WORKSHOP_PROFILES[fixture_station].title.title()}'))
    if planned is not None:
        building_label=str(planned.function).replace('_',' ').title()
        if shell is not None and door is None:
            rows.append(('inspect_building_exterior',f'Inspect {building_label} exterior'))
        if planned.function=='market' and distance<=2:
            rows.append(('use_market_here','Trade at market stall'))
            if sim.state.player_hunting_stance=='stalk':
                rows.append(('steal_market_here','Steal from market stock'))
    if private_storage and distance<=1:
        owner=sim.state.npcs.get(container.owner)
        owner_label=owner.name if owner and owner.uid in sim.known_npc_ids() else 'private owner'
        lock_label=sim.property_security.lock_band(container.lock_level) if container.lock_level>0 else 'unlocked'
        rows.append(('inspect_property_storage',f'Inspect {container.name} — {owner_label} / {lock_label}'))
        if container.locked and sim.state.player_hunting_stance=='aggressive':
            inv=ctx.entities.get(ctx.player_id,Inventory)
            rows.append(('lockpick_property_storage',
                         f'Pick {container.name} lock'+('' if inv.count("core:lockpick")>0 else ' — requires Lockpick')))
        if not container.locked and sim.state.player_hunting_stance=='stalk':
            rows.append(('steal_property_storage',f'Steal from {container.name}'))
    if crossing is not None:
        condition=sim.route_planner.crossing_condition(crossing.route_id,crossing.uid)
        status='closed' if sim.route_planner.crossing_blocked(crossing.route_id,crossing.uid,sim.clock.minute) else 'open'
        rows.append(('inspect_crossing',f'Inspect {crossing.kind} — {condition}% / {status}'))
        if crossing.kind=='ferry' and distance<=3:
            toll=sim.route_planner.crossing_toll(crossing.route_id,crossing.x,crossing.y)
            rows.append(('use_crossing',f'Use ferry'+(f' — toll {toll}c' if toll else '')))
        if condition<100 and distance<=2:
            rows.append(('repair_crossing',f'Repair {crossing.kind} — condition {condition}%'))
    if border_post is not None:
        faction=sim.state.factions.get(border_post.controlling_faction_id)
        name=faction.name if faction else 'local authority'
        paid=int(sim.state.player_toll_passes.get(border_post.uid,0))>sim.clock.minute
        rows.append(('inspect_border_post',f'Border post — {name}'+(' / passage paid' if paid else f' / toll {border_post.toll_copper}c')))
        if distance<=1 and not paid:
            rows.append(('pay_road_toll',f'Pay road toll — {border_post.toll_copper}c'))
    if signs:
        rows.append(('inspect_sign',f'Inspect animal sign — {len(signs)} trace(s) on this tile'))
    if home and home.discovered:
        rows.append(('inspect_home',f'Inspect {home.kind} — animal shelter'))
        if distance<=1:rows.append(('search_home',f'Search {home.kind} — {sum(home.stored_items.values())} cached item(s)'))
    if not building_part and distance<=1 and sim.resources.is_harvestable(target):
        rows.append(('gather',f'Gather — {sim.resources.description(target)}'))
    if not building_part and distance<=3 and sim.fishing.is_fishable(target):
        region=sim.fishing.region_at(target)
        rows.append(('fish',f'Fish — {sim.world.tile_at(target).terrain.name} / {region.structure.replace("_"," ")}'))
    if distance<=1 and pile and pile.items:
        count=sum(max(0,int(n)) for n in pile.items.values())
        rows.append(('pickup',f'Pick up ground items — {count} item(s)'))
    if distance<=1 and container and not private_storage:
        rows.append(('open',f'Open {container.name or "container"}'))
    if homestead is not None and distance<=8:
        rows.append(('manage_blueprint','Inspect cabin & entrance' if homestead['stage']==4
                     else 'Open cabin blueprint & materials'))
    rows.append(('examine','Examine tile and contents'))
    subtitle='Right-click world actions.' + (' Move closer for pickup/gather/container actions.' if distance>1 else '')
    if building_part and shell is not None:
        subtitle='Exterior only; no hidden rooms or contents are revealed.'
        if building_part=='door' and shell.entrance is not None:
            subtitle=f'Entrance access: {shell.entrance[0]}, {shell.entrance[1]}. Approach the painted doorway to enter.'
    choice=_select(term,f'WORLD ACTIONS {target.x},{target.y}',rows,subtitle=subtitle,
                   presentation='world_context',presentation_data={'target':(target.x,target.y,target.z)})
    if not choice:return UI_BACK
    if choice=='manage_blueprint' and homestead is not None:
        return _homestead_blueprint_panel(ctx,term,homestead['uid'])
    if choice=='enter_interior':
        sim.execute(EnterInteriorCommand(ctx.player_id,door.uid))
        return sim.log[-1].message if sim.log else ''
    if choice=='inspect_building_exterior' and shell is not None:
        lines=[building_label, f'Exterior condition: {planned.condition}%',
               'The building exterior is solid. Use its separate entrance to go inside.']
        if shell.entrance:
            lines.append(f'Entrance: {shell.entrance[0]}, {shell.entrance[1]}')
        _view_text(term,box('BUILDING EXTERIOR',lines,screen_width(term.size()[0],92)))
        return UI_BACK
    if choice=='inspect_fixture' and fixture_piece is not None:
        lines=[
            fixture_piece.name,
            f'Type: {str(fixture_piece.category).replace("_"," ").title()}',
        ]
        if fixture_piece.workplace_role:
            lines.append(f'Profession: {str(fixture_piece.workplace_role).replace("_"," ").title()}')
        if fixture_piece.work_bonus:
            lines.append(f'Work bonus: +{fixture_piece.work_bonus}')
        if fixture_station in WORKSHOP_PROFILES:
            lines.append(WORKSHOP_PROFILES[fixture_station].purpose)
        _view_text(term,box('WORKSHOP OBJECT',lines,screen_width(term.size()[0],92)))
        return UI_BACK
    if choice=='use_fixture' and fixture_station in WORKSHOP_PROFILES:
        return _crafting_menu(ctx,term,'workshops',fixture_station)
    if choice=='inspect_property_storage' and container is not None:
        owner=sim.state.npcs.get(container.owner)
        owner_label=owner.name if owner and owner.uid in sim.known_npc_ids() else ('Player' if container.owner=='player' else 'Private owner')
        lock_state='locked' if container.locked else 'unlocked'
        _view_text(term,box('PROPERTY STORAGE',[
            container.name or 'Storage',
            f'Owner: {owner_label}',
            f'Access: {container.access.title()}',
            f'Lock: {lock_state} / {sim.property_security.lock_band(container.lock_level) if container.lock_level else "none"}',
            f'Contents: {sum(container.items.values())} item(s) in {len(container.items)} stack(s)',
            'Unauthorized removal is theft and requires Stalk mode. Locks and witnesses still matter.'
        ],screen_width(term.size()[0],96)))
        return UI_BACK
    if choice=='lockpick_property_storage' and container is not None:
        sim.execute(LockpickContainerCommand(ctx.player_id,container.uid))
        return sim.log[-1].message if sim.log else ''
    if choice=='inspect_property_door' and door is not None:
        lock_desc=sim.property_security.lock_band(door.lock_level)
        status='forced open' if door.forced else 'locked' if door.locked else 'unlocked'
        _view_text(term,box('PROPERTY DOOR',[
            f'Access: {door.access.title()}',
            f'Status: {status.title()}',
            f'Lock: {lock_desc}',
            f'Door condition: {door.condition}%',
        ],screen_width(term.size()[0],92)))
        return UI_BACK
    if choice=='knock_property_door' and door is not None:
        result=sim.property_security.knock_on_door(
            door.uid,sim.player_pos,sim.clock.minute,sim.player_skill('persuasion')
        )
        return str(result.get('message','No one answers.'))
    if choice=='lockpick_property_door' and door is not None:
        sim.execute(LockpickDoorCommand(ctx.player_id,door.uid))
        return sim.log[-1].message if sim.log else ''
    if choice=='force_property_door' and door is not None:
        sim.execute(ForceDoorCommand(ctx.player_id,door.uid))
        return sim.log[-1].message if sim.log else ''
    if choice=='steal_property_storage' and container:
        return _steal_property_storage_action(ctx,term,container)
    if choice=='use_market_here' and planned is not None and physical is not None:
        return _handle_menu(ctx,term,'o')
    if choice=='steal_market_here' and planned is not None and physical is not None:
        town=sim.state.settlements.get(physical.settlement_id)
        if town:return _steal_market_action(ctx,term,town)
        return UI_BACK
    if choice=='inspect_crossing' and crossing is not None:
        condition=sim.route_planner.crossing_condition(crossing.route_id,crossing.uid)
        blocked=sim.route_planner.crossing_blocked(crossing.route_id,crossing.uid,sim.clock.minute)
        infra=sim.state.route_infrastructure.get(crossing.route_id)
        _view_text(term,box('ROUTE CROSSING',[
            f'Type: {crossing.kind.title()}',
            f'Condition: {condition}%',
            f'Status: {"Closed" if blocked else "Open"}',
            f'River class: {crossing.river_class}',
            f'Route hazard: {getattr(infra,"hazard_reason","") or "none"}',
            f'Patrol strength: {crossing.patrol_strength}',
            f'Toll: {crossing.toll_copper}c',
        ],screen_width(term.size()[0],92)))
        return UI_BACK
    if choice=='use_crossing' and crossing is not None:
        sim.execute(UseCrossingCommand(ctx.player_id,crossing.uid))
        return sim.log[-1].message if sim.log else ''
    if choice=='repair_crossing' and crossing is not None:
        sim.execute(RepairCrossingCommand(ctx.player_id,crossing.uid))
        return sim.log[-1].message if sim.log else ''
    if choice=='inspect_border_post' and border_post is not None:
        faction=sim.state.factions.get(border_post.controlling_faction_id)
        rival=sim.state.factions.get(border_post.rival_faction_id)
        _view_text(term,box('BORDER POST',[
            f'Controller: {faction.name if faction else border_post.controlling_faction_id or "unclaimed"}',
            f'Rival: {rival.name if rival else border_post.rival_faction_id or "none"}',
            f'Toll: {border_post.toll_copper}c',
            f'Patrol: {border_post.patrol_strength}/100',
            f'Status: {"Contested" if border_post.contested else "Controlled"}',
            f'Collected: {border_post.treasury_collected}c',
        ],screen_width(term.size()[0],92)))
        return UI_BACK
    if choice=='inspect_monument' and monument is not None:
        token=f'{monument.region_x},{monument.region_y}';intel=sim.state.learned_regions.get(token)
        faction=sim.state.factions.get(monument.controller_faction_id) if intel else None
        resources=', '.join(str(v) for v in intel.get('resources',())[:6]) if intel else 'Unknown — ask an inhabitant about the area'
        owner=(faction.name if faction else ('Unclaimed' if intel else 'Unknown — ask an inhabitant'))
        capture=('Keep a stronger friendly presence here than the defender through daily control updates until capture reaches 100%.' if monument.integrity>0 else 'Repair the ruined monument before establishing control.')
        _view_text(term,box('CLAIM MONUMENT',[
            f'Tier: {monument.monument_type.replace("_"," ").title()}',f'Claim region: {token}',
            f'Owner: {owner}',f'Regional resources: {resources}',f'Integrity: {monument.integrity}%',
            f'Garrison: {monument.garrison_strength if intel else "Unknown"}',f'Capture progress: {monument.capture_progress if intel else "Unknown"}',
            f'How to capture: {capture}',
        ],screen_width(term.size()[0],96)))
        return UI_BACK
    if choice=='pay_road_toll' and border_post is not None:
        sim.execute(PayRoadTollCommand(ctx.player_id,border_post.uid))
        return sim.log[-1].message if sim.log else ''
    if choice=='inspect_npc' and npc:
        return _npc_profile_menu(ctx,term,npc.uid)
    if choice=='observe_npc' and npc:
        return 'Talk to this person to learn who they are.'
    if choice=='talk_npc' and npc:
        return _talk_action(ctx,term,npc.uid)
    if choice=='observe_animal':
        _view_text(term,look_screen(sim,screen_width(term.size()[0],118),target));return UI_BACK
    if choice=='attack_animal' and creature:
        return _melee_attack_action(ctx,term,target)
    if choice=='aim_animal' and creature:
        return _hunt_action(ctx,term,target)
    if choice=='shoot_animal' and creature:
        sim.execute(RangedAttackCommand(ctx.player_id,creature.uid))
        return sim.log[-1].message if sim.log else ''
    if choice=='inspect_sign':
        _view_text(term,look_screen(sim,screen_width(term.size()[0],118),target));return UI_BACK
    if choice=='inspect_home':
        _view_text(term,look_screen(sim,screen_width(term.size()[0],118),target));return UI_BACK
    if choice=='search_home' and home:
        sim.execute(SearchAnimalHomeCommand(ctx.player_id,home.uid))
        return sim.log[-1].message if sim.log else ''
    if choice=='gather':return _gather_positions(ctx,[target])
    if choice=='fish':return _fishing_action(ctx,term,target)
    if choice=='pickup':
        sim.execute(PickupCommand(ctx.player_id,target.x-p.x,target.y-p.y))
        return sim.log[-1].message if sim.log else ''
    if choice=='open' and container:return _storage_menu(ctx,term,container.uid)
    if choice=='examine':
        _view_text(term,look_screen(sim,screen_width(term.size()[0],118),target));return UI_BACK
    return UI_BACK


def _inventory_ui_data(reg:ContentRegistry,inv:Inventory,sim:Simulation,include_artifacts:bool=True)->dict:
    total_mass=sum(reg.items[iid].mass_g*n for iid,n in inv.items.items() if iid in reg.items and n>0)
    total_volume=sum(reg.items[iid].volume_ml*n for iid,n in inv.items.items() if iid in reg.items and n>0)
    categories={}
    items={}
    artifacts_by_item={}
    if include_artifacts:
        for artifact in sim.state.artifacts.values():
            if artifact.owner=='player':
                artifacts_by_item.setdefault(artifact.base_item,[]).append(artifact)
    for item in ordered_items(reg.items[iid] for iid,n in inv.items.items() if iid in reg.items and n>0):
        iid=item.id;n=inv.count(iid)
        cat=item.category or 'misc';categories[cat]=categories.get(cat,0)+n
        material=reg.materials.get(item.material) if item.material else None
        material_name=material.name if material else ''
        detail=[]
        if item.crafting_source:
            detail.append(f'Crafting material: {item.crafting_source.title()} | grade {item.crafting_quality}/100')
        if material:
            detail.append(f'Material: {material.name} | hardness {material.hardness} | toughness {material.toughness}')
        if item.nutrition>0 or item.calories or item.hydration:
            detail.append(f'Food: satiety {item.nutrition} | hydration {item.hydration} | {item.calories} kcal')
            if item.protein or item.carbs or item.fat or item.fiber:
                detail.append(f'Nutrition: protein {item.protein} | carbs {item.carbs} | fat {item.fat} | fiber {item.fiber}')
            if item.food_groups:detail.append('Diet: '+', '.join(x.title() for x in item.food_groups))
        if item.tool_qualities:
            detail.append('Tool: '+', '.join(f'{k.replace("_"," ")} {v}' for k,v in sorted(item.tool_qualities.items())))
        elif item.tool_power:
            detail.append(f'Tool effectiveness {item.tool_power}')
        if item.weapon_damage:
            weapon=f'Weapon: {item.weapon_class or item.damage_type} | {item.damage_type} {item.weapon_damage} | reach {item.reach}'
            if item.range>1:weapon+=f' | range {item.range}'
            weapon+=f' | accuracy {item.accuracy:+d} | stamina {item.stamina_cost}'
            if item.ammo_item:weapon+=f' | ammo {reg.items[item.ammo_item].name if item.ammo_item in reg.items else item.ammo_item}'
            if item.throwable:weapon+=' | throwable / recoverable'
            if item.two_handed:weapon+=' | two-handed'
            detail.append(weapon)
        if item.equip_slot:
            equip=f'Equipment: {item.equip_slot.replace("_"," ")}'
            if item.armor:equip+=f' | armor {item.armor}'
            if item.insulation:equip+=f' | warmth {item.insulation}'
            detail.append(equip)
            if item.coverage:detail.append('Covers: '+', '.join(x.replace('_',' ') for x in item.coverage))
        if item.spoilage_hours:detail.append(f'Keeps about {max(1,item.spoilage_hours//24)} day(s)')
        if item.utility_roles:detail.append('Roles: '+', '.join(x.replace('_',' ') for x in item.utility_roles))
        durable=sorted(artifacts_by_item.get(iid,()),key=lambda a:(a.condition,a.quality),reverse=True)
        if durable:
            detail.append(f'Individual durable items: {len(durable)}')
            artifact_system=getattr(sim,'artifacts',None)
            describe=getattr(artifact_system,'describe_effects',None)
            for artifact in durable:
                detail.append(f'{artifact.name or item.name}: condition {artifact.condition}% | quality {artifact.quality}/100')
                artifact_material=reg.materials.get(artifact.material)
                if artifact_material:detail.append('Made from: '+artifact_material.name)
                metadata=artifact.components.get('crafting',{})
                if not isinstance(metadata,dict):metadata={}
                if metadata.get('source'):
                    detail.append('Material source: '+str(metadata['source']).replace('_',' ').title())
                if callable(describe):
                    effects=describe(artifact)
                    benefits=[]
                    if item.weapon_damage:benefits.append(f"Damage ×{effects['damage_percent']/100:.2f}")
                    if item.armor:benefits.append(f"Armor ×{effects['armor_percent']/100:.2f}")
                    benefits.extend([f"Durability ×{effects['durability_percent']/100:.2f}",f"Trade value ×{effects['value_percent']/100:.2f}"])
                    detail.append(f"Effective quality {effects['quality']}/100 | "+' | '.join(benefits))
                for slot,component in artifact.components.items():
                    if not isinstance(component,dict) or 'material' not in component:continue
                    component_material=reg.materials.get(component['material'])
                    label=component_material.name if component_material else str(component['material']).replace('core:','').title()
                    detail.append(f"{slot.replace('_',' ').title()}: {label} | grade {component.get('quality',artifact.quality)}/100 | condition {component.get('condition',artifact.condition)}%")
                for ingredient in metadata.get('ingredients',()):
                    ingredient_item=reg.items.get(ingredient.get('id'))
                    name=ingredient_item.name if ingredient_item else str(ingredient.get('name','Material'))
                    source=str(ingredient.get('source','')).replace('_',' ').title()
                    detail.append(f"Input: {name} ×{ingredient.get('qty',1)} | grade {ingredient.get('quality',50)}/100"+(' | '+source if source else ''))
        if item.flavor and item.description:detail.append(item.flavor)
        use_kind=''
        use_label='Use'
        if item.nutrition>0:use_kind='eat';use_label='Use · Eat'
        elif item.weapon_damage>0:use_kind='ready';use_label='Use · Ready weapon'
        elif item.equip_slot:use_kind='equip';use_label='Use · Equip'
        elif iid=='core:book':use_kind='read';use_label='Use · Read'
        items[iid]={
            'name':item.name,'count':n,'category':cat,
            'mass_kg':item.mass_g*n/1000.0,'unit_mass_kg':item.mass_g/1000.0,
            'volume_l':item.volume_ml*n/1000.0,'unit_volume_l':item.volume_ml/1000.0,
            'description':item.description or item.flavor or '',
            'material':material_name,'equip_slot':item.equip_slot or '',
            'nutrition':item.nutrition,'hydration':item.hydration,'calories':item.calories,
            'armor':item.armor,'insulation':item.insulation,'weapon_damage':item.weapon_damage,
            'damage_type':item.damage_type,'tool_power':item.tool_power,
            'tags':list(item.tags),'roles':list(item.utility_roles),
            'detail_lines':detail,
            'can_use':bool(use_kind),'use_kind':use_kind,'use_label':use_label,
        }
    equipped={slot:iid for slot,iid in sim.state.player_equipment.items() if iid in reg.items}
    if sim.state.player_readied_weapon in reg.items:equipped['weapon']=sim.state.player_readied_weapon
    return {
        'total_mass_kg':total_mass/1000.0,'total_volume_l':total_volume/1000.0,
        'stack_count':len(items),'item_count':sum(v['count'] for v in items.values()),
        'categories':categories,'items':items,'equipped':equipped,
        'near_storage':bool(sim.building.nearby_container(sim.player_pos)),
        'player_sex':getattr(sim.state,'player_sex','male'),
        'player_sprite_index':int(getattr(sim.state,'player_sprite_index',0)),
        'player_name':sim.state.player_name,
    }

def _recipe_ui_data(reg:ContentRegistry,sim:Simulation,inv:Inventory,recipes,*,material_preference:str='auto')->dict:
    """Project the command's material allocation and quality without changing it."""
    stations=_player_station_ids(sim)
    rows={}
    skill_query=getattr(sim,'player_skill',None)
    interiors=getattr(sim,'interiors',None)
    presence=getattr(interiors,'player_presence',None)
    indoor=(presence() is not None) if callable(presence) else presence is not None
    bonus_query=getattr(sim.building,'environmental_bonuses',None)
    work_bonus=0 if indoor or not callable(bonus_query) else int(bonus_query(sim.player_pos).get('work_bonus',0))
    known_items=set(getattr(sim.state,'player_discovered_items',()))|{iid for iid,n in inv.items.items() if n>0}
    for r in recipes:
        skill_level=int(skill_query(r.skill)) if callable(skill_query) else 0
        preview=sim.crafting.preview(r,inv,preference=material_preference,skill_level=skill_level,work_bonus=work_bonus)
        missing=sim.crafting.missing_requirements(r.id,inv,stations,preference=material_preference)
        projected={output['id']:output for output in preview.get('outputs',())}
        outputs=[]
        for iid,n in r.outputs.items():
            item=reg.items.get(iid)
            output={'id':iid,'name':item.name if item else iid,'qty':n,
                    'description':item.description if item else '',
                    'roles':list(item.utility_roles) if item else [],
                    'unit_mass_kg':item.mass_g/1000 if item else 0}
            output.update(projected.get(iid,{}))
            material=reg.materials.get(output.get('material'))
            output['material_name']=material.name if material else ''
            outputs.append(output)
        inputs=sim.crafting.ingredient_rows(r,inv,preference=material_preference)
        if getattr(sim.state,'player_crafting_discovery_enabled',False):
            inputs=[dict(row,options=[dict(option) for option in row.get('options',()) if option['id'] in known_items])
                    if row.get('tag') else row for row in inputs]
        inputs.extend({'id':iid,'name':(reg.items[iid].name if iid in reg.items else iid)+' (catalyst)',
                       'need':n,'have':inv.count(iid),'retained':True} for iid,n in r.catalysts.items())
        consumed=preview.get('consumed')
        consumed_items=[dict(row) for row in preview.get('ingredients',())] or [
            {'id':iid,'name':reg.items[iid].name if iid in reg.items else iid,'qty':qty}
            for iid,qty in sorted((consumed or {}).items())]
        rows[r.id]={
            'name':r.name,'category':r.category or 'general','description':r.description or '',
            'minutes':r.minutes,'difficulty':r.difficulty,'skill':r.skill,
            'station':reg.structures[r.station].name if r.station and r.station in reg.structures else '',
            'ready':not missing,'missing':list(missing),'outputs':outputs,'inputs':inputs,
            'new':r.id in set(getattr(sim.state,'player_unseen_recipes',[])),
            'material_preference':preview.get('preference',material_preference),
            'material_preference_enabled':bool(r.input_tags or getattr(r,'input_units',{})),
            'material_quality_enabled':bool(preview.get('material_quality_enabled')),
            'material_quality':preview.get('material_quality'),'material_source':preview.get('source_label',''),
            'consumed':consumed,'consumed_items':consumed_items,
        }
    return {'recipes':rows,'material_preference':material_preference}


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
    for item in ordered_items(reg.items[iid] for iid in set(sim.state.player_discovered_items) if iid in reg.items):
        iid=item.id
        items[iid]={'name':item.name,'category':item.category or 'misc','material':reg.materials[item.material].name if item.material and item.material in reg.materials else '', 'description':item.description or item.flavor or ''}
    return {'items':items,'count':len(items)}


def _crafting_tree_ui_data(reg:ContentRegistry,sim:Simulation,inv:Inventory)->dict:
    nodes=[]
    for rid,status,parents in sim.crafting.discovery_tree_rows(inv):
        r=reg.recipes[rid]
        nodes.append({
            'id':rid,'name':r.name if status=='known' else 'Undiscovered technique','category':r.category or 'general','status':status,
            'parents':[x for x in parents.split(', ') if x],
            'outputs':[iid for iid in r.outputs if iid in reg.items],
            'minutes':r.minutes,
        })
    return {'nodes':nodes,'known':sum(1 for n in nodes if n['status']=='known'),'total':len(nodes)}


def _salvage_preview_ui_data(reg:ContentRegistry,sim:Simulation,inv:Inventory,item_id:str)->dict:
    """Enrich the salvage read model with only learned downstream techniques."""
    preview=sim.salvaging.preview(item_id,inv)
    if not preview:return {}
    data=dict(preview)
    known=sim.crafting.discovered_recipes(inv)
    for group in ('guaranteed','rare'):
        data[group]=[]
        for component in preview.get(group,()):
            row=dict(component);iid=row['item_id']
            uses=[r.name for r in known if sim.crafting.recipe_uses_item(r,iid) or iid in r.catalysts]
            row['uses']=uses
            from worldseed.systems.salvage_perks import has as has_salvage_perk
            if has_salvage_perk(sim.state, 'tell_tale_marks'):
                row['relevance'] = len(uses)
            item=reg.items.get(iid)
            row['description']=item.description if item else ''
            data[group].append(row)
    data['count']=inv.count(item_id)
    return data


def _salvage_preview_lines(data:dict)->list[str]:
    lines=[data.get('description',''),f"Method: {str(data.get('method','')).replace('_',' ')}",
           f"Time: {data.get('minutes',0)} minutes | Difficulty: {data.get('difficulty',0)}",
           f"Salvaging level {data.get('skill_level',0)} | XP {data.get('skill_xp',0)}/{data.get('skill_threshold',0)}",'',
           'Beginning dismantles ONE item. Escape preserves work so you can resume later.','',
           'RECOVERABLE COMPONENTS']
    for group in ('guaranteed','rare'):
        for row in data.get(group,()):
            low,high=row.get('min',1),row.get('max',1)
            quantity=str(low) if low==high else f'{low}–{high}'
            chance=f" | rare base {row.get('chance_percent',0)}%" if group=='rare' else ' | guaranteed'
            lines.append(f"{row['name']} x{quantity}{chance}")
            if row.get('description'):lines.append('  '+row['description'])
            uses=row.get('uses',())
            lines.append('  Learned uses: '+(', '.join(uses) if uses else 'Handle the component and experiment to learn techniques.'))
    if data.get('rare'):lines+=['','Careful recovery, tools and skill improve rare-component odds.']
    if data.get('tools'):
        lines+=['','TOOL QUALITIES']+[f'{str(key).replace("_"," ").title()} {value}+' for key,value in data['tools'].items()]
    if data.get('reason'):lines+=['',data['reason']]
    return lines


def _salvaging_menu(ctx:GameContext,term:Terminal)->str:
    """Retained catalogue, preview, resumable minigame and completion routes."""
    if getattr(term,'mouse_ui',False) and callable(getattr(term,'present_feature_menu',None)):
        from worldseed.ui.salvage_panel import run_salvage_panel
        return run_salvage_panel(ctx,term)
    sim=ctx.sim;reg=ctx.registry;pid=ctx.player_id
    nav=NavigationStack(RouteState('salvaging','SALVAGING // CARRIED ITEMS',payload={'query':''}))
    status=''
    while True:
        inv=ctx.entities.get(pid,Inventory);route=nav.current
        if route.route_id=='salvaging':
            query=route.payload.get('query','')
            available=sim.salvaging.available_items(inv)
            entries={row['item_id']:dict(row) for row in available if not query or query.casefold() in row['name'].casefold()}
            rows=[(iid,f"{row['name']} x{row['count']}") for iid,row in entries.items()]
            if sim.salvaging.session_view():rows.insert(0,('__resume__','Resume unfinished salvage'))
            if not rows:rows.append(('__none__','No salvageable items in your pack'))
            rows+=[('__search__',f'Search carried items'+(f' — {query}' if query else ''))]
            selected_item=route.payload.get('selected_item')
            if selected_item in {key for key,_ in rows}:
                route.selected=next(index for index,(key,_) in enumerate(rows) if key==selected_item)
            data={'mode':'catalogue','items':entries,'query':query,
                  'skill_level':sim.player_skill('salvaging'),'skill_xp':int(getattr(sim.state,'player_salvaging_xp',0)),
                  'skill_threshold':sim.salvaging.skill_threshold(sim.player_skill('salvaging')),
                  'active_session':sim.salvaging.session_view()}
            choice=_stack_menu(term,nav,rows,subtitle=status or 'Inspect an item to preview components and rare recovery odds.',
                               presentation='salvaging',presentation_data=data)
            if 0<=route.selected<len(rows):route.payload['selected_item']=rows[route.selected][0]
            status=''
            if choice is None:return UI_BACK
            if choice=='__BACK__':continue
            if choice.startswith('UI_ACTION:tab:'):
                if choice=='UI_ACTION:tab:salvaging':continue
                return choice
            moved=_live_panel_world_move(ctx,term,choice)
            if moved is not None:status=moved;continue
            if choice in {'__search__','UI_ACTION:search'}:
                nav.push(RouteState('salvaging-search','SALVAGING // SEARCH'))
                value=prompt_text(term,nav.current.title,'Item name (blank shows all):',default=query,max_len=48)
                nav.pop()
                if value is not None:
                    route.payload['query']=value;route.payload.pop('selected_item',None);route.selected=0
                continue
            if choice=='__resume__':
                route.payload['selected_item']=choice
                nav.push(RouteState('salvaging-session','SALVAGING // DISASSEMBLY'));continue
            if choice in entries:
                route.payload['selected_item']=choice
                nav.push(RouteState('salvaging-item',entries[choice]['name'],payload={'item_id':choice}));continue
            continue
        if route.route_id=='salvaging-item':
            data=_salvage_preview_ui_data(reg,sim,inv,route.payload['item_id'])
            if not data:nav.pop();continue
            rows=[('inspect','Inspect components & crafting uses')]
            if data.get('can_start'):rows.append(('begin','Begin salvage — dismantle one item'))
            if sim.salvaging.session_view():rows.append(('resume','Resume unfinished salvage'))
            choice=_stack_menu(term,nav,rows,subtitle=status or data.get('reason') or 'Preview is free. Begin dismantles one carried item.',
                               presentation='salvaging',presentation_data={'mode':'preview',**data})
            status=''
            if choice=='__BACK__':continue
            moved=_live_panel_world_move(ctx,term,choice)
            if moved is not None:status=moved;continue
            if choice=='inspect':
                nav.push(RouteState('salvaging-inspect','SALVAGING // COMPONENT PREVIEW'))
                _stack_view(term,nav,'\n'.join(_salvage_preview_lines(data)));continue
            if choice=='begin':
                sim.execute(StartSalvageCommand(pid,route.payload['item_id']))
                status=sim.log[-1].message if sim.log else ''
                if sim.salvaging.session_view():nav.push(RouteState('salvaging-session','SALVAGING // DISASSEMBLY'))
                continue
            if choice=='resume':nav.push(RouteState('salvaging-session','SALVAGING // DISASSEMBLY'))
            continue
        if route.route_id=='salvaging-session':
            session=sim.salvaging.session_view()
            if not session:
                result=dict(sim.state.player_salvage_log[-1]) if sim.state.player_salvage_log else {}
                nav.replace(RouteState('salvaging-result','SALVAGING // RECOVERED PARTS',payload={'result':result}));continue
            rows=[(row['id'],row['label']) for row in session['choices']]
            cue=' '.join(str(session.get(key,'')) for key in ('cue','prompt')).strip()
            choice=_stack_menu(term,nav,rows,subtitle=cue,presentation='salvaging',presentation_data={'mode':'session',**session})
            if choice=='__BACK__':continue
            moved=_live_panel_world_move(ctx,term,choice)
            if moved is not None:status=moved;continue
            if choice in {row['id'] for row in session['choices']}:
                sim.execute(SalvageActionCommand(pid,choice))
                status=sim.log[-1].message if sim.log else ''
                route.selected=0
            continue
        result=route.payload.get('result',{})
        outputs=[{'item_id':iid,'name':reg.items[iid].name if iid in reg.items else iid,'count':quantity,
                  'rare':iid in result.get('rare_outputs',{})} for iid,quantity in result.get('outputs',{}).items()]
        data={'mode':'result',**result,'recovered':outputs,
              'skill_threshold':sim.salvaging.skill_threshold(int(result.get('skill_level',0)))}
        choice=_stack_menu(term,nav,[('done','Return to previous screen'),('inspect','Inspect recovered components')],
                           subtitle=f"Recovered {len(outputs)} component kinds. Salvaging practice +{result.get('xp_gained',0)}.",
                           presentation='salvaging',presentation_data=data)
        if choice=='__BACK__':continue
        moved=_live_panel_world_move(ctx,term,choice)
        if moved is not None:status=moved;continue
        if choice=='done':nav.pop();continue
        if choice=='inspect':
            lines=[f"Recovery score: {result.get('score',0)}/{result.get('max_score',6)}",
                   f"Salvaging XP +{result.get('xp_gained',0)} | Level {result.get('skill_level',0)}",'']
            lines += [f"{row['name']} x{row['count']}"+(' (rare)' if row['rare'] else '') for row in outputs]
            nav.push(RouteState('salvaging-result-inspect','SALVAGING // RESULT DETAIL'))
            _stack_view(term,nav,'\n'.join(lines))


def _inventory_menu_terminal(ctx:GameContext,term:Terminal)->str:
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
            rows=[(iid,f"{meta['name']} x{meta['count']} | {meta['mass_kg']:.1f} kg")
                  for iid,meta in _inventory_ui_data(reg,inv,sim)['items'].items()]
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
            if item.weapon_damage>0:actions.append(('ready',f'Ready weapon — {item.weapon_class or item.damage_type}'))
            if item.equip_slot:actions.append(('equip',f'Equip — {item.equip_slot}'))
            if sim.building.nearby_container(sim.player_pos):actions.append(('store','Store one in nearby container'))
            act=_stack_menu(term,nav,actions,subtitle=f'{item.name} x{inv.count(iid)}',presentation='inventory_item_actions',presentation_data={'item_id':iid,**_inventory_ui_data(reg,inv,sim)})
            if act is None:return UI_BACK
            if act=='__BACK__':continue
            if act=='inspect':
                nav.push(RouteState(f'inventory-detail:{iid}','INVENTORY // ITEM DETAIL',payload={'iid':iid}));_stack_view(term,nav,item_detail_screen(reg,sim,inv,iid,width),presentation='inventory_item_detail',presentation_data={'item_id':iid,**_inventory_ui_data(reg,inv,sim)});continue
            if act=='drop':sim.execute(DropCommand(pid,iid,1))
            elif act=='eat':sim.execute(EatCommand(pid,iid))
            elif act=='ready':sim.execute(ReadyWeaponCommand(pid,iid))
            elif act=='equip':sim.execute(EquipCommand(pid,iid))
            elif act=='store':sim.execute(StoreCommand(pid,iid,1))
            return sim.log[-1].message if sim.log else ''
        if not nav.back():return UI_BACK


def _live_panel_world_move(ctx:GameContext,term:Terminal,choice:str)->str|None:
    """Apply WASD from a retained gameplay panel without closing it."""
    if not str(choice).startswith('UI_WORLD_MOVE:'):
        return None
    key=str(choice).rsplit(':',1)[1].lower()
    direction=DIRECTION_KEYS.get(key)
    if not direction:
        return ''
    before=len(ctx.sim.log)
    ctx.sim.execute(MoveCommand(ctx.player_id,*direction))
    message=ctx.sim.log[-1].message if len(ctx.sim.log)>before else ''
    # A focused companion panel is composited over a retained parent panel.
    # Repainting the world here would discard that stack.  The command still
    # executes immediately; the uncovered world refreshes when focus returns
    # to one panel or the panels close.  Single-panel movement remains live.
    if not getattr(term,'_floating_panel_stack',None):
        try:_present_game_frame(term,ctx,Renderer(ctx.registry),message)
        except Exception:pass
    return message

def _inventory_menu(ctx:GameContext,term:Terminal)->str:
    """Unified graphical inventory with terminal fallback.

    Pygame presents the carried-item grid, selected-item information and legal
    actions on one retained surface. The UI only selects intent; all mutations
    still travel through simulation commands. Text terminals retain the older
    hierarchical flow for complete keyboard/fallback compatibility.
    """
    if not (getattr(term,'mouse_ui',False) and callable(getattr(term,'present_feature_menu',None))):
        return _inventory_menu_terminal(ctx,term)
    sim=ctx.sim;reg=ctx.registry;pid=ctx.player_id
    parent_panel=getattr(term,'_floating_panel_id',None)
    nav=NavigationStack(RouteState('inventory','INVENTORY'))
    action_amount=1;last_selected=None;status='';active_filter='all';filter_page=0
    while True:
        inv=ctx.entities.get(pid,Inventory);route=nav.current
        data=_inventory_ui_data(reg,inv,sim)
        visible_items=[(iid,meta) for iid,meta in data['items'].items() if active_filter=='all' or meta.get('category')==active_filter]
        rows=[(iid,f"{meta['name']} x{meta['count']}") for iid,meta in visible_items]
        if rows:
            route.selected=max(0,min(route.selected,len(rows)-1))
            selected_iid=rows[route.selected][0]
        else:
            rows=[('__empty__','Your pack is empty')]
            route.selected=0;selected_iid='__empty__'
        if selected_iid!=last_selected:
            action_amount=1;last_selected=selected_iid
        count=inv.count(selected_iid) if selected_iid!='__empty__' else 0
        action_amount=max(1,min(action_amount,max(1,count)))
        filters=sorted(data.get('categories',{}),key=lambda cat:(ITEM_TYPE_ORDER.index(cat) if cat in ITEM_TYPE_ORDER else len(ITEM_TYPE_ORDER),cat))
        filter_page=min(filter_page,len(filters)//6)
        data.update({'selected_item_id':selected_iid,'action_amount':action_amount,'active_filter':active_filter,
                     'filter_categories':filters,'filter_page':filter_page})
        subtitle=status or 'Click to inspect • right-click for actions • Shift-click stores the full stack when a container is nearby.'
        status=''
        choice=_stack_menu(term,nav,rows,subtitle=subtitle,presentation='inventory_unified',presentation_data=data)
        if choice is None:return UI_BACK
        if choice=='__BACK__':continue
        moved=_live_panel_world_move(ctx,term,choice)
        if moved is not None:
            status=moved;continue
        if choice=='UI_ACTION:open_crafting':
            if parent_panel=='crafting':return UI_BACK
            push=getattr(term,'push_floating_panel',None);pop=getattr(term,'pop_floating_panel',None)
            if callable(push):push()
            try:_crafting_menu(ctx,term)
            finally:
                if callable(pop):pop()
            continue
        if not choice.startswith('UI_ACTION:'):
            if choice!='__empty__':
                action_amount=1;last_selected=choice
            continue
        action=choice.split(':',1)[1]
        if action.startswith('filter_page:'):
            filter_page=max(0,min(filter_page+(1 if action.endswith(':next') else -1),len(filters)//6));continue
        if action.startswith('filter:'):
            active_filter=action.split(':',1)[1] or 'all';route.selected=0;route.scroll=0;last_selected=None;action_amount=1;continue
        # Explicit keyboard/click navigation can change the retained row before
        # an inline action; hover and viewport scrolling preserve that target.
        if rows and 0<=route.selected<len(rows):
            selected_iid=rows[route.selected][0]
            count=inv.count(selected_iid) if selected_iid!='__empty__' else 0
            if selected_iid!=last_selected:
                action_amount=1;last_selected=selected_iid
        if selected_iid=='__empty__' or selected_iid not in reg.items or count<=0:
            continue
        if action=='qty_down':
            action_amount=max(1,action_amount-1);continue
        if action=='qty_up':
            action_amount=min(count,action_amount+1);continue
        if action=='qty_all':
            action_amount=count;continue
        if action=='split':
            action_amount=max(1,(count+1)//2)
            status=f'Quantity set to half: {action_amount} of {count}. Drop or store will use that amount.'
            continue
        if action=='drop':
            sim.execute(DropCommand(pid,selected_iid,min(action_amount,count)))
        elif action in ('store','quick_store'):
            amount=count if action=='quick_store' else min(action_amount,count)
            sim.execute(StoreCommand(pid,selected_iid,amount))
        elif action=='use':
            item=reg.items[selected_iid]
            if item.nutrition>0:sim.execute(EatCommand(pid,selected_iid))
            elif item.weapon_damage>0:sim.execute(ReadyWeaponCommand(pid,selected_iid))
            elif item.equip_slot:sim.execute(EquipCommand(pid,selected_iid))
            elif selected_iid=='core:book':sim.execute(ReadBookCommand(pid))
            else:
                status='That item has no direct inventory action yet.'
                continue
        else:
            continue
        status=sim.log[-1].message if sim.log else ''
        action_amount=1;last_selected=None

def _crafting_menu_graphical(ctx:GameContext,term:Terminal,initial_tab:str='recipes',initial_station:str='')->str:
    """One retained, movable crafting surface with recipe and discovery tabs."""
    sim=ctx.sim;reg=ctx.registry;pid=ctx.player_id
    parent_panel=getattr(term,'_floating_panel_id',None)
    def open_inventory_panel():
        if parent_panel=='inventory_unified':return False
        push=getattr(term,'push_floating_panel',None);pop=getattr(term,'pop_floating_panel',None)
        if callable(push):push()
        try:_inventory_menu(ctx,term)
        finally:
            if callable(pop):pop()
        return True
    tab=initial_tab if initial_tab in {'recipes','workshops','discovery','salvaging'} else 'recipes';categories=['all']+sorted({r.category or 'general' for r in reg.recipes.values()})
    initial=sim.crafting.discovered_recipes(ctx.entities.get(pid,Inventory))
    category='all'
    category_page=categories.index(category)//6 if category in categories else 0
    recipe_state=RouteState('crafting-recipes','CRAFTING')
    workshop_state=RouteState('crafting-workshop','WORKSHOP')
    pot_state=RouteState('crafting-pot','DISCOVERY')
    from worldseed.ui.crafting_journal import crafting_journal_data
    workshop_station=str(initial_station or '')
    station_page=0
    material_preference='auto'
    result_dismissed=False
    placed=[];status='';recipe_query='';salvage_return_tab='recipes';recipe_filter='all';discovery_station=''
    while True:
        inv=ctx.entities.get(pid,Inventory)
        if tab=='salvaging':
            result=_salvaging_menu(ctx,term)
            tab=result.split(':',2)[2] if result.startswith('UI_ACTION:tab:') else salvage_return_tab
            continue
        if tab=='workshops':
            nearby=sorted(
                sid for sid in _player_station_ids(sim)
                if sid in WORKSHOP_PROFILES
            )
            if workshop_station not in nearby:
                workshop_station=nearby[0] if nearby else ''
                workshop_state.selected=0
            station_rows=[]
            for sid in nearby:
                row=profile_dict(WORKSHOP_PROFILES[sid])
                row['short_title']=WORKSHOP_PROFILES[sid].title.replace("'S",'').replace(' WORKSHOP','').replace(' YARD','')
                station_rows.append(row)
            all_station_recipes=recipes_for_station(reg,workshop_station) if workshop_station else []
            known_ids={r.id for r in sim.crafting.discovered_recipes(inv)}
            station_recipes=[r for r in all_station_recipes if r.id in known_ids]
            station_recipes.sort(key=lambda r:r.name)
            rows=[(r.id,r.name) for r in station_recipes]
            if not rows:
                rows=[('__none__','No discovered process at this station' if workshop_station else 'No workshop station within reach')]
            workshop_state.selected=max(0,min(workshop_state.selected,len(rows)-1))
            data=_recipe_ui_data(reg,sim,inv,station_recipes,material_preference=material_preference)
            data.update({
                'profile':profile_dict(WORKSHOP_PROFILES[workshop_station]) if workshop_station else {},
                'stations':station_rows,'station_id':workshop_station,
                'locked_count':max(0,len(all_station_recipes)-len(station_recipes)),
                'station_page':station_page,
            })
            choice=_select(
                term,'WORKSHOP',rows,state=workshop_state,presentation='workshop_station',
                subtitle=status or (
                    WORKSHOP_PROFILES[workshop_station].purpose if workshop_station
                    else 'Stand beside a workshop fixture to use its dedicated processes.'
                ),presentation_data=data
            )
            status=''
            if choice is None:return UI_BACK
            moved=_live_panel_world_move(ctx,term,choice)
            if moved is not None:status=moved;continue
            if choice.startswith('UI_ACTION:tab:'):
                destination=choice.split(':',2)[2]
                if destination in {'recipes','workshops','discovery','salvaging'}:
                    if destination=='salvaging':salvage_return_tab=tab
                    tab=destination
                continue
            if choice=='UI_ACTION:material_preference':
                preferences=('auto','refined','recovered')
                material_preference=preferences[(preferences.index(material_preference)+1)%len(preferences)]
                continue
            if choice=='UI_ACTION:open_inventory':
                if not open_inventory_panel():return UI_BACK
                continue
            if choice=='UI_ACTION:tab:recipes':tab='recipes';continue
            if choice=='UI_ACTION:tab:workshops':tab='workshops';continue
            if choice=='UI_ACTION:tab:discovery':tab='discovery';continue
            if choice.startswith('UI_ACTION:workshop_page:'):
                delta=1 if choice.endswith(':next') else -1
                station_page=max(0,min(station_page+delta,max(0,(len(nearby)-1)//4)))
                continue
            if choice.startswith('UI_ACTION:workshop:'):
                sid=choice.split(':',2)[2]
                if sid in nearby:workshop_station=sid;workshop_state.selected=0
                continue
            if choice in reg.recipes:
                sim.state.player_unseen_recipes=[rid for rid in sim.state.player_unseen_recipes if rid!=choice]
                continue
            if choice=='UI_ACTION:workshop_craft' and station_recipes:
                rid=rows[workshop_state.selected][0]
                if rid in reg.recipes:
                    sim.execute(CraftCommand(pid,rid,material_preference))
                    status=sim.log[-1].message if sim.log else ''
                continue
            continue
        if tab=='recipes':
            all_known=sim.crafting.discovered_recipes(inv)
            stations=_player_station_ids(sim)
            missing_cache={r.id:sim.crafting.missing_requirements(r.id,inv,stations,preference=material_preference) for r in all_known}
            known=[r for r in all_known if
                   (category=='all' or (r.category or 'general')==category)
                   and (recipe_filter!='ready' or not missing_cache[r.id])
                   and (recipe_filter!='missing' or bool(missing_cache[r.id]))
                   and (not recipe_query or recipe_query.casefold() in ' '.join(
                       (r.name,r.category or '',*(reg.items[iid].name for iid in r.outputs if iid in reg.items))).casefold())]
            known.sort(key=lambda r:(bool(missing_cache[r.id]),r.name.casefold(),r.id))
            rows=[(r.id,r.name) for r in known] or [('__none__','No recipes in this category')]
            recipe_state.selected=max(0,min(recipe_state.selected,len(rows)-1))
            data=_recipe_ui_data(reg,sim,inv,known,material_preference=material_preference)
            unseen=set(getattr(sim.state,'player_unseen_recipes',[]));new_categories=sorted({reg.recipes[rid].category or 'general' for rid in unseen if rid in reg.recipes})
            data.update({'categories':categories,'category':category,'category_page':category_page,'new_categories':new_categories,'query':recipe_query,'recipe_filter':recipe_filter,'ready_total':sum(not x for x in missing_cache.values()),'known_total':len(all_known)})
            choice=_select(term,'CRAFTING',rows,state=recipe_state,presentation='crafting_unified',
                           subtitle=status or 'Browse techniques and inspect exactly what each recipe produces.',presentation_data=data)
            status=''
            if choice is None:return UI_BACK
            moved=_live_panel_world_move(ctx,term,choice)
            if moved is not None:status=moved;continue
            if choice.startswith('UI_ACTION:tab:'):
                destination=choice.split(':',2)[2]
                if destination in {'recipes','workshops','discovery','salvaging'}:
                    if destination=='salvaging':salvage_return_tab=tab
                    tab=destination
                continue
            if choice=='UI_ACTION:material_preference':
                preferences=('auto','refined','recovered')
                material_preference=preferences[(preferences.index(material_preference)+1)%len(preferences)]
                continue
            if choice=='UI_ACTION:open_inventory':
                if not open_inventory_panel():return UI_BACK
                continue
            if choice=='UI_ACTION:tab:discovery':tab='discovery';continue
            if choice=='UI_ACTION:search':
                value=prompt_text(term,'CRAFTING // SEARCH','Technique, profession or output (blank clears):',default=recipe_query,max_len=48)
                if value is not None:recipe_query=value;recipe_state.selected=0;recipe_state.scroll=0
                continue
            if choice.startswith('UI_ACTION:recipe_filter:'):
                recipe_filter=choice.rsplit(':',1)[-1];recipe_state.selected=0;recipe_state.scroll=0
                continue
            if choice.startswith('UI_ACTION:category_page:'):
                page_size=6
                delta=1 if choice.endswith(':next') else -1
                category_page=max(0,min(category_page+delta,max(0,(len(categories)-1)//page_size)))
                continue
            if choice.startswith('UI_ACTION:category:'):
                category=choice.split(':',2)[2];recipe_query='';recipe_state.selected=0;recipe_state.scroll=0;continue
            if choice in reg.recipes:
                sim.state.player_unseen_recipes=[rid for rid in sim.state.player_unseen_recipes if rid!=choice]
                continue
            if choice=='UI_ACTION:craft':
                rid=rows[recipe_state.selected][0]
                if rid in reg.recipes:
                    sim.execute(CraftCommand(pid,rid,material_preference))
                    status=sim.log[-1].message if sim.log else ''
                continue
            continue
        entries={}
        for item in ordered_items(reg.items[iid] for iid,n in inv.items.items() if iid in reg.items and n>0):
            iid=item.id;n=inv.count(iid)
            pool=sim.crafting.recipe_pool_for_item(iid)
            if not pool:continue
            entries[iid]={'name':reg.items[iid].name,'count':n,'pool_count':len(pool),
                          'known_recipes':[r.name for r in pool if sim.crafting.recipe_is_discovered(r.id)],
                          'tags':list(item.tags)}
        rows=[(iid,v['name']) for iid,v in entries.items()] or [('__none__','Gather materials to experiment')]
        pot_state.selected=max(0,min(pot_state.selected,len(rows)-1))
        from collections import Counter
        nearby_discovery=sorted(sid for sid in _player_station_ids(sim) if any(r.station==sid for r in reg.recipes.values()))
        if discovery_station not in nearby_discovery:discovery_station=''
        counts=Counter(placed);exact=sim.crafting.pot_candidates(tuple(placed),inv,station_id=discovery_station)
        known_exact=[r.name for r in reg.recipes.values()
                     if r.id in set(sim.state.player_discovered_recipes) and counts
                     and sim.crafting.discovery_matches(r,placed)]
        close=False
        if counts and not exact and not known_exact:
            for r in reg.recipes.values():
                if r.id in set(sim.state.player_discovered_recipes):continue
                if r.knowledge and r.knowledge not in sim.state.player_knowledge:continue
                if sim.crafting.discovery_matches(r,placed,partial=True):close=True;break
        mix_state='green' if exact else ('yellow' if close else 'red')
        station_tabs=[{'id':'','name':'Field'}]+[
            {'id':sid,'name':reg.structures[sid].name if sid in reg.structures else sid}
            for sid in nearby_discovery]
        data={'items':entries,'selected_items':tuple(placed),'candidates':len(exact),
              'known_exact':known_exact,'mix_state':mix_state,'discovery_station':discovery_station,
              'discovery_stations':station_tabs,
              'known_hints':[{'recipe_id':h['recipe_id'],'station_name':(
                  reg.structures[h['station_id']].name if h['station_id'] in reg.structures else h['station_id'])}
                  for h in sim.state.player_crafting_hints if h.get('recipe_id') not in sim.state.player_discovered_recipes]}
        data.update(crafting_journal_data(reg,sim.state))
        if result_dismissed:data['latest_result']=None
        choice=_select(term,'EXPERIMENT GRID',rows,state=pot_state,presentation='discovery_pot',
                       subtitle=status or 'Combine up to five carried materials. The grid color shows how close the mix is to a discoverable recipe.',presentation_data=data)
        status=''
        if choice is None:return UI_BACK
        moved=_live_panel_world_move(ctx,term,choice)
        if moved is not None:status=moved;continue
        if choice.startswith('UI_ACTION:tab:'):
            destination=choice.split(':',2)[2]
            if destination in {'recipes','workshops','discovery','salvaging'}:
                if destination=='salvaging':salvage_return_tab=tab
                tab=destination
            continue
        if choice=='UI_ACTION:open_inventory':
            if not open_inventory_panel():return UI_BACK
            continue
        if choice=='UI_ACTION:tab:recipes':tab='recipes';continue
        if choice=='UI_ACTION:tab:workshops':tab='workshops';continue
        if choice.startswith('UI_ACTION:remove_slot:'):
            try:idx=int(choice.rsplit(':',1)[1])
            except ValueError:continue
            if 0<=idx<len(placed):placed.pop(idx)
            continue
        if choice=='UI_ACTION:dismiss_result':result_dismissed=True;continue
        if choice=='UI_ACTION:clear':placed.clear();continue
        if choice.startswith('UI_ACTION:discovery_station:'):
            sid=choice.split(':',2)[2]
            if sid=='' or sid in nearby_discovery:
                discovery_station=sid;placed.clear();pot_state.selected=0
            continue
        if choice=='UI_ACTION:mix':
            # The command validates quantities and chooses the recipe. The UI
            # animates only after the simulation reports a successful result.
            before=set(sim.state.player_discovered_recipes)
            ingredients=tuple(placed)
            before_hints=len(sim.state.player_crafting_hints)
            sim.execute(DiscoveryPotCommand(pid,ingredients,discovery_station))
            status=sim.log[-1].message if sim.log else ''
            new=set(sim.state.player_discovered_recipes)-before
            if new:
                result_dismissed=False
                rid=sorted(new)[0];anim=getattr(term,'animate_discovery_pot',None)
                if callable(anim):anim(ingredients,reg.recipes[rid].name)
                placed.clear()
            elif len(sim.state.player_crafting_hints)>before_hints:
                placed.clear()
            continue
        if choice in entries:
            if len(placed)>=5:status='The experiment grid holds at most five items.'
            elif placed.count(choice)>=inv.count(choice):status='You do not carry another one of those.'
            else:placed.append(choice)


def _crafting_menu(ctx:GameContext,term:Terminal,initial_tab:str='recipes',initial_station:str='')->str:
    """Discovery-first crafting browser.

    The terminal backend keeps full keyboard parity while the pygame backend
    renders these top-level routes as graphical tabs/cards. All discovery
    mutation is performed by simulation commands; opening this UI is read-only.
    """
    if getattr(term,'mouse_ui',False) and callable(getattr(term,'present_feature_menu',None)):
        return _crafting_menu_graphical(ctx,term,initial_tab,initial_station)
    sim=ctx.sim;reg=ctx.registry;pid=ctx.player_id;inv=ctx.entities.get(pid,Inventory)
    home_state=RouteState('crafting-home','CRAFTING MODE // WORKBENCH')
    while True:
        inv=ctx.entities.get(pid,Inventory)
        known=sorted(sim.crafting.discovered_recipes(inv),key=lambda r:(r.category or 'general',r.name))
        ideas=sim.crafting.researchable_recipes(inv)
        discovered_items=set(sim.state.player_discovered_items)
        nearby_workshops=sorted(
            sid for sid in _player_station_ids(sim)
            if sid in WORKSHOP_PROFILES
        )
        rows=[
            ('recipes',f'Discovered Recipes — {len(known)} known'),
            ('workshops',f'Nearby Workshops — {len(nearby_workshops)} usable station(s)'),
            ('salvaging','Salvaging — recover components from carried finds'),
            ('ideas','Experiment Grid — combine 1–5 carried items'),
            ('materials',f'Materials — {len(discovered_items)} item types examined'),
            ('tree','Tech Tree — trace discovered recipes and future branches'),
        ]
        if reg.designs:rows.append(('design','Component Designs — choose materials part by part'))
        pick=_select(term,'CRAFTING MODE // WORKBENCH',rows,state=home_state,presentation='crafting_home',presentation_data=_crafting_home_ui_data(reg,sim,inv,known,ideas))
        if not pick:return UI_BACK

        if pick=='salvaging':
            _salvaging_menu(ctx,term)
            continue

        if pick=='workshops':
            if not nearby_workshops:
                _view_text(term,box('WORKSHOPS',['No usable workshop station is within reach.','Move beside a generated workshop fixture or a station you built.'],screen_width(term.size()[0],96)))
                continue
            sid=_select(term,'WORKSHOPS',[
                (station_id,f"{WORKSHOP_PROFILES[station_id].title} — {WORKSHOP_PROFILES[station_id].purpose}")
                for station_id in nearby_workshops
            ])
            if not sid:continue
            profile=WORKSHOP_PROFILES[sid]
            known_ids={r.id for r in sim.crafting.discovered_recipes(inv)}
            recipes=[r for r in recipes_for_station(reg,sid) if r.id in known_ids]
            if not recipes:
                _view_text(term,box(profile.title,[profile.purpose,'','You have not discovered a process for this station yet.'],screen_width(term.size()[0],96)))
                continue
            stations=_player_station_ids(sim)
            recipe_rows=[]
            for r in recipes:
                missing=sim.crafting.missing_requirements(r.id,inv,stations)
                result=', '.join(f'{reg.items[i].name} x{n}' for i,n in r.outputs.items() if i in reg.items)
                recipe_rows.append((r.id,f'[{"READY" if not missing else "NEEDS"}] {r.name} → {result}'+(f' | {missing[0]}' if missing else '')))
            rid=_select(term,profile.title,recipe_rows,subtitle=profile.purpose)
            if not rid:continue
            r=reg.recipes[rid];missing=sim.crafting.missing_requirements(rid,inv,stations)
            body=[profile.purpose,'',r.name,r.description or 'A workshop process.','','OUTPUT']
            body += [f'  {reg.items[i].name} x{n}' for i,n in r.outputs.items() if i in reg.items]
            body += ['','MATERIALS']+[f'  {reg.items[i].name if i in reg.items else i}: {inv.count(i)}/{n}' for i,n in r.inputs.items()]
            body += ['',f'Skill: {r.skill.replace("_"," ").title()} (difficulty {r.difficulty})',f'Time: {r.minutes} minutes']
            if missing:body += ['','NOT READY']+[f'  {x}' for x in missing]
            action=_select(term,profile.title,[(profile.action_label.lower(),profile.action_label)] if not missing else [('view','Close detail')],subtitle=' • '.join(body[:3]))
            if not missing and action==profile.action_label.lower():
                sim.execute(CraftCommand(pid,rid));return sim.log[-1].message if sim.log else ''
            continue

        if pick=='materials':
            by_cat={}
            for item in ordered_items(reg.items[iid] for iid in discovered_items if iid in reg.items):
                by_cat.setdefault(item.category or 'misc',[]).append(item)
            body=['Handled materials give clues. Combine carried materials in the experiment grid to uncover a matching recipe.','']
            if not by_cat:body.append('You have not examined any craft materials yet. Gather or pick up something useful.')
            for cat,items in by_cat.items():
                body.append(cat.replace('_',' ').upper())
                body.extend('  '+it.name for it in items)
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
            placed=[]
            while len(placed)<5:
                options=[(iid,f'{reg.items[iid].name} — held {inv.count(iid)}, placed {placed.count(iid)}; {len(sim.crafting.recipe_pool_for_item(iid))} possible recipes')
                         for iid in sorted(inv.items) if iid in reg.items and inv.count(iid)>placed.count(iid)]
                actions=[('__MIX__','Combine these items')] if len(placed)>=1 else []
                choice=_select(term,'CRAFTING // DISCOVERY POT',options+actions,subtitle=f'{len(placed)}/5 items placed. Pick another item or combine.') if options or actions else None
                if choice=='__MIX__':break
                if choice is None:placed=[];break
                placed.append(choice)
            if len(placed)>=1:
                sim.execute(DiscoveryPotCommand(pid,tuple(placed)))
                return sim.log[-1].message if sim.log else ''
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
            _view_text(term,box('CRAFTING // DISCOVERED RECIPES',['No recipes discovered yet.','Gather materials and combine them in the experiment grid to uncover techniques.'],screen_width(term.size()[0],96)))
            continue
        categories=sorted(set(r.category or 'general' for r in known))
        category=_select(term,'CRAFTING // RECIPES',[('__search__','Search learned techniques, professions or outputs')]+[(c,f'{c.replace("_"," ").title()} — {sum(1 for r in known if (r.category or "general")==c)} discovered') for c in categories],presentation='crafting_categories',presentation_data={'counts':{c:sum(1 for r in known if (r.category or 'general')==c) for c in categories},'known':len(known)})
        if not category:continue
        if category=='__search__':
            query=prompt_text(term,'CRAFTING // SEARCH','Technique, profession or output:',max_len=48)
            if query is None:continue
            recipes=[r for r in known if query.casefold() in ' '.join((r.name,r.category,*(reg.items[iid].name for iid in r.outputs if iid in reg.items))).casefold()]
            category='search results'
            if not recipes:
                _view_text(term,'No learned technique matches that search.');continue
        else:recipes=[r for r in known if (r.category or 'general')==category]
        stations=_player_station_ids(sim);recipe_rows=[]
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


def _homestead_blueprint_panel(ctx:GameContext,term:Terminal,uid:str)->str:
    """Clickable modal for player blueprint stock, stages, and cancellation."""
    from worldseed.systems.homestead_blueprints import (
        STAGES,progress,catalog,material_sources,carried_material)
    sim=ctx.sim
    inv=ctx.entities.get(ctx.player_id,Inventory)

    def completed_panel(site):
        from worldseed.systems.homestead_blueprints import doorway,door_uid
        outside=doorway(site)[1]
        choice=_select(term,'LOG CABIN • COMPLETE',[
            ('enter','Enter your log cabin'),('close','Return to the world')],
            subtitle=f'Approach the outside doorway at {outside[0]}, {outside[1]} to enter.')
        if choice=='enter':
            sim.execute(EnterInteriorCommand(ctx.player_id,door_uid(site)))
            return sim.log[-1].message if sim.log else ''
        return UI_BACK

    def deposit_requested(iid,amount):
        """Deposit accepted source items against one construction requirement."""
        remaining=max(0,int(amount));deposited=0
        for source in material_sources(iid):
            if not remaining:break
            qty=min(remaining,inv.count(source))
            if qty<=0:continue
            before=inv.count(source)
            sim.execute(DepositBlueprintCommand(ctx.player_id,uid,source,qty))
            accepted=before-inv.count(source)
            deposited+=accepted;remaining-=accepted
        return deposited

    show=getattr(term,'present_homestead_depot',None)
    if callable(show):
        notice='';confirm_cancel=False
        while uid in sim.state.homesteads:
            site=sim.state.homesteads[uid]
            if int(site['stage'])==4:return completed_panel(site)
            ledger=progress(site)
            style=catalog()[1].get(site['style_id'],{})
            materials=[(iid,'Roof thatch (mixed)' if iid=='core:reed_bundle'
                         else ctx.registry.items[iid].name if iid in ctx.registry.items else iid,
                         have,need,carried_material(inv,iid)) for iid,(have,need) in ledger.items()]
            show({'site':site,'style_name':style.get('name','Log cabin').split(' — ')[-1],
                  'stage_name':'Finished' if site['stage']>=4 else STAGES[site['stage']],
                  'materials':materials,'notice':notice,'confirm_cancel':confirm_cancel,
                  'thatch_hint':'Thatch: reeds, pine/juniper boughs, grasses, eelgrass, rushes or brush'})
            key=term.read_key()
            if key=='UI_REDRAW':continue
            if key in ('ESC','UI_ACTION:depot_close'):return UI_BACK
            if key=='UI_ACTION:depot_cancel':
                confirm_cancel=True;notice='';continue
            if key=='UI_ACTION:depot_cancel_back':
                confirm_cancel=False;continue
            if key=='UI_ACTION:depot_cancel_confirm' and confirm_cancel:
                sim.execute(CancelBlueprintCommand(ctx.player_id,uid))
                return sim.log[-1].message if sim.log else ''
            if confirm_cancel:continue
            if key=='UI_ACTION:depot_build':
                sim.execute(AdvanceBlueprintCommand(ctx.player_id,uid))
                notice=sim.log[-1].message if sim.log else ''
                continue
            if key=='UI_ACTION:depot_all':
                count=sum(deposit_requested(iid,need-have)
                          for iid,(have,need) in ledger.items())
                notice=f'Deposited {count} materials.' if count else 'No required materials can be deposited.'
                continue
            for prefix,one in (('UI_ACTION:depot_item_one:',True),
                               ('UI_ACTION:depot_item_all:',False)):
                if not key.startswith(prefix):continue
                iid=key[len(prefix):]
                if iid not in ledger:break
                have,need=ledger[iid]
                qty=min(1,max(0,need-have)) if one else max(0,need-have)
                taken=deposit_requested(iid,qty)
                notice=f'Deposited {taken} materials.' if taken else 'You do not carry more of this material.'
                break
        return UI_BACK
    while uid in sim.state.homesteads:
        site=sim.state.homesteads[uid]
        if int(site['stage'])==4:return completed_panel(site)
        rows=progress(site)
        stage=int(site['stage'])
        label='Complete' if stage>=4 else STAGES[stage]
        deposited=sum(h for h,n in rows.values())
        total=sum(n for h,n in rows.values())
        status=[f'{label} | Supplied: {deposited}/{total} items',
                f"Cabin: {catalog()[1][site['style_id']]['name']}",
                f"Location: {site['x']}, {site['y']} | Rotation: {site['orientation']*90} degrees",
                '']
        status += [f"{'Roof thatch' if iid=='core:reed_bundle' else ctx.registry.items[iid].name if iid in ctx.registry.items else iid}: {have}/{need} (carry {carried_material(inv,iid)})"
                   for iid,(have,need) in rows.items()]
        options=[('inspect','Material ledger and building details')]
        if stage<4:
            options += [('deposit_all','Deposit all carried materials needed'),
                        ('build','Build the next stage (from deposited materials)')]
            options += [(f'deposit:{iid}',f"Deposit {ctx.registry.items[iid].name if iid in ctx.registry.items else iid} — {have}/{need}")
                        for iid,(have,need) in rows.items() if need>have]
            options += [('cancel','Cancel blueprint and recover deposits')]
        choice=_select(term,f'LOG CABIN • {label.upper()}',options,subtitle=f'Site stock {deposited}/{total} | Materials remain deposited until you build.')
        if not choice:return UI_BACK
        if choice=='inspect':
            _view_text(term,box('LOG CABIN BLUEPRINT',status,screen_width(term.size()[0],94),'Esc back'))
            continue
        if choice=='deposit_all':
            for iid,(have,need) in rows.items():
                deposit_requested(iid,need-have)
            continue
        if choice.startswith('deposit:'):
            iid=choice.split(':',1)[1]
            have,need=rows[iid]
            qty=_select(term,'DEPOSIT MATERIAL',[
                ('1','Deposit 1'),('5','Deposit up to 5'),('all','Deposit everything needed that you carry')])
            if qty:
                amount=(need-have) if qty=='all' else int(qty)
                deposit_requested(iid,amount)
            continue
        if choice=='build':
            sim.execute(AdvanceBlueprintCommand(ctx.player_id,uid))
            continue
        if choice=='cancel':
            confirm=_select(term,'REMOVE BLUEPRINT',[('no','Keep blueprint'),('yes','Return deposits and remove unfinished site')])
            if confirm=='yes':
                sim.execute(CancelBlueprintCommand(ctx.player_id,uid))
                return sim.log[-1].message if sim.log else ''
    return UI_BACK

def _choose_log_cabin_style(ctx:GameContext,term:Terminal)->str:
    """Choose an authored cabin appearance, then preview it under the cursor."""
    from worldseed.systems.homestead_blueprints import catalog
    choices=sorted((style for style in catalog()[1].values()
                    if style['home_id']=='log_cabin'),key=lambda row:row['id'])
    panel=getattr(term,'present_homestead_styles',None)
    begin=getattr(term,'begin_homestead_placement',None)
    if callable(panel) and callable(begin):
        selection=0
        while True:
            panel(choices[selection],selection,len(choices))
            key=term.read_key()
            if key=='UI_REDRAW':continue
            if key in ('LEFT','UI_ACTION:cabin_prev'):
                selection=(selection-1)%len(choices);continue
            if key in ('RIGHT','UI_ACTION:cabin_next'):
                selection=(selection+1)%len(choices);continue
            if key=='UI_ACTION:cabin_other':return '__OTHER_STRUCTURES__'
            if key in ('\r','\n','UI_ACTION:cabin_place'):
                begin(choices[selection]['id'])
                return 'Move the cabin ghost with your mouse. R rotates; left-click places; right-click or Esc cancels.'
            if key=='ESC':return UI_BACK
    style=_select(term,'HOMESTEADS  /  LOG CABIN',
                  [(row['id'],row['name']) for row in choices],
                  subtitle='Choose a style, then position the cabin on the world map.')
    if not style:return UI_BACK
    # Terminal-only backend retains keyboard construction without GUI pointers.
    direction=_direction(term)
    if not direction:return UI_BACK
    target=ctx.sim.player_pos.moved(*direction)
    ctx.sim.execute(PlaceBlueprintCommand(ctx.player_id,style,target.x,target.y,0))
    return ctx.sim.log[-1].message if ctx.sim.log else ''


def _building_menu(ctx:GameContext,term:Terminal,*,legacy_only:bool=False)->str:
    interiors=getattr(ctx.sim,'interiors',None)
    if interiors is not None and interiors.player_presence() is not None:
        return 'Exterior construction requires stepping outside. Right-click indoor furniture to reposition furnishings you own.'
    sim=ctx.sim;reg=ctx.registry;pid=ctx.player_id;inv=ctx.entities.get(pid,Inventory)
    if not legacy_only and callable(getattr(term,'present_homestead_styles',None)):
        result=_choose_log_cabin_style(ctx,term)
        if result=='__OTHER_STRUCTURES__':return _building_menu(ctx,term,legacy_only=True)
        return result
    while True:
        buildable=[st for st in reg.structures.values() if 'natural_only' not in st.tags]
        groups=sorted(set(_structure_group(st) for st in buildable))
        if not legacy_only:groups=['homesteads']+groups
        group=_select(term,'CONSTRUCTION',[(g,'Homesteads — log cabins, 10 visual styles') if g=='homesteads' else (g,f'{g.title()} — {sum(1 for st in buildable if _structure_group(st)==g)} plans') for g in groups])
        if not group:return UI_BACK
        if group=='homesteads':
            return _choose_log_cabin_style(ctx,term)
        rows=[]
        structs=sorted((st for st in buildable if _structure_group(st)==group),key=lambda s:s.name)
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
    if lower=='collect_water':sim.execute(CollectWaterCommand(pid));return sim.log[-1].message if sim.log else ''
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
                if mk=='ESC':
                    controls=getattr(term,'_atlas_controls',None)
                    if controls is not None and getattr(controls,'detail',None) is not None:
                        atlas_input(term,sim,'ATLAS_DETAIL_BACK');presenter(sim);continue
                    break
                if ml in ('m','q','\r','\n'):break
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
                ('overview','Review equipment, anatomy & wounds'),('ready','Ready a carried weapon'),('lower','Lower readied weapon'),
                ('equip','Equip armor/clothing'),('unequip','Unequip slot'),('treat','Treat a wound'),('medicine','Take medicine for symptomatic infection')])
            if not mode:return UI_BACK
            if mode=='overview':
                _view_text(term,equipment_screen(sim,reg,ctx.entities.get(pid,Inventory),screen_width(term.size()[0],100)));continue
            if mode=='ready':
                inv=ctx.entities.get(pid,Inventory);rows=[(iid,f'{reg.items[iid].name} | {reg.items[iid].weapon_class or reg.items[iid].damage_type} | damage {reg.items[iid].weapon_damage} | reach {reg.items[iid].reach} | range {reg.items[iid].range}') for iid,n in inv.items.items() if n>0 and iid in reg.items and reg.items[iid].weapon_damage>0]
                iid=_select(term,'READY WEAPON',rows)
                if not iid:continue
                sim.execute(ReadyWeaponCommand(pid,iid));return sim.log[-1].message if sim.log else ''
            if mode=='lower':
                sim.execute(ClearReadyWeaponCommand(pid));return sim.log[-1].message if sim.log else ''
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
    if lower=='x':return _melee_attack_action(ctx,term)
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
        if not town:
            _view_text(term,box('MARKET',['No discovered market is within reach.'],screen_width(term.size()[0],92)))
            return UI_BACK
        sim.economy.ensure_currency(town)
        quote_name,quote_units=sim.economy.currency_quote(town.uid,10)
        bounty=int(sim.state.player_bounties.get(town.uid,0))
        heat=int(sim.state.player_crime_heat.get(town.uid,0))
        legal=f' Local bounty: {bounty}c.' if bounty else ''
        stealth_note=''
        if sim.state.player_stealth_mode:
            snap=sim.stealth_snapshot();seen=len(snap.get('seen_by',()))
            stealth_note=f' Stealth active: {seen} observer{"s" if seen!=1 else ""} can currently see you.'
        subtitle=f'{quote_name}: {quote_units} units ≈ 10 copper value. Prices reflect local supply. Barter uses the same valuation.{legal}{stealth_note}'
        while True:
            modes=[('buy','Buy'),('sell','Sell'),('barter','Barter')]
            if sim.state.player_stealth_mode:
                modes.extend([('steal','Steal'),('leave_stealth','Leave stealth mode')])
            else:
                modes.append(('stealth','Enter stealth mode'))
            mode=_select(term,f'{town.name} MARKET',modes,subtitle=subtitle)
            if not mode:return UI_BACK
            inv=ctx.entities.get(pid,Inventory)
            if mode=='stealth':
                sim.execute(ToggleStealthCommand(pid,True))
                return sim.log[-1].message if sim.log else ''
            if mode=='leave_stealth':
                sim.execute(ToggleStealthCommand(pid,False))
                return sim.log[-1].message if sim.log else ''
            if mode=='steal':
                result=_steal_market_action(ctx,term,town)
                if result==UI_BACK:continue
                return result
            if mode=='barter':
                offered_rows=[]
                for iid,n in sorted(inv.items.items()):
                    if n<=0 or iid=='core:copper_coin' or iid not in reg.items:continue
                    value=sim.player_barter_value(town.uid,{iid:1},True)
                    offered_rows.append((iid,f'{reg.items[iid].name} — x{n} — offer value {value}c'))
                offered_iid=_select(term,'BARTER · OFFER',offered_rows,subtitle='Choose one good from your pack.')
                if not offered_iid:continue
                offered_max=inv.count(offered_iid)
                offer_quantities=[q for q in (1,5,10) if q<=offered_max]
                if offered_max>0 and offered_max not in offer_quantities:offer_quantities.append(offered_max)
                oq=_select(
                    term,'BARTER · OFFER QUANTITY',
                    [(str(q),f'{q} × {reg.items[offered_iid].name} — {sim.player_barter_value(town.uid,{offered_iid:q},True)}c offer value') for q in offer_quantities],
                )
                if not oq:continue
                offered_amount=int(oq)
                request_rows=[]
                for iid,n in sorted(town.stocks.items()):
                    if n<=0 or iid==offered_iid or iid not in reg.items:continue
                    value=sim.player_barter_value(town.uid,{iid:1},False)
                    request_rows.append((iid,f'{reg.items[iid].name} — stock {n} — request value {value}c'))
                requested_iid=_select(term,'BARTER · REQUEST',request_rows,subtitle='Choose what you want from the market.')
                if not requested_iid:continue
                requested_max=town.stocks.get(requested_iid,0)
                request_quantities=[q for q in (1,5,10) if q<=requested_max]
                if requested_max>0 and requested_max not in request_quantities:request_quantities.append(requested_max)
                rq_rows=[]
                for q in request_quantities:
                    balance=sim.player_barter_balance(
                        town.uid,{offered_iid:offered_amount},{requested_iid:q}
                    )
                    state='acceptable' if balance>=0 else f'short {-balance}c'
                    rq_rows.append((str(q),f'{q} × {reg.items[requested_iid].name} — {state}'))
                rq=_select(term,'BARTER · REQUEST QUANTITY',rq_rows)
                if not rq:continue
                requested_amount=int(rq)
                balance=sim.player_barter_balance(
                    town.uid,{offered_iid:offered_amount},{requested_iid:requested_amount}
                )
                summary=(
                    f'{offered_amount} {reg.items[offered_iid].name} → '
                    f'{requested_amount} {reg.items[requested_iid].name} | '
                    +('offer accepted by value' if balance>=0 else f'offer short {-balance}c')
                )
                confirm=_select(term,'BARTER · REVIEW',[('confirm','Confirm trade'),('back','Change offer')],subtitle=summary)
                if confirm!='confirm':continue
                sim.execute(BarterCommand(pid,town.uid,offered_iid,offered_amount,requested_iid,requested_amount))
                return sim.log[-1].message if sim.log else ''
            if mode=='buy':
                rows=[]
                for iid,n in sorted(town.stocks.items()):
                    if n<=0 or iid not in reg.items:continue
                    price=sim.player_trade_price(town.uid,iid,True)
                    local_name,units=sim.economy.currency_quote(town.uid,price)
                    rows.append((iid,f'{reg.items[iid].name} — stock {n} — {price}c / {units} {local_name}'))
            else:
                rows=[]
                for iid,n in sorted(inv.items.items()):
                    if n<=0 or iid=='core:copper_coin' or iid not in reg.items:continue
                    price=sim.player_trade_price(town.uid,iid,False)
                    local_name,units=sim.economy.currency_quote(town.uid,price)
                    rows.append((iid,f'{reg.items[iid].name} — x{n} — {price}c / {units} {local_name}'))
            iid=_select(term,mode.upper(),rows,subtitle='Select a good. Local currency is shown as a value quote; copper remains the physical coin.')
            if not iid:continue
            maximum=max_affordable_trade(sim,town.uid,iid,town.stocks.get(iid,0),inv.count('core:copper_coin')) if mode=='buy' else inv.count(iid)
            quantities=[q for q in (1,5,10) if q<=maximum]
            if maximum>0 and maximum not in quantities:quantities.append(maximum)
            qrows=[]
            for q in quantities:
                total=trade_total(sim,town.uid,iid,mode=='buy',q);local_name,units=sim.economy.currency_quote(town.uid,total)
                qrows.append((str(q),f'{q} unit(s) — {total}c / {units} {local_name}'))
            qkey=_select(term,'QUANTITY',qrows) if qrows else None
            if not qkey:continue
            amount=int(qkey)
            sim.execute(BuyCommand(pid,town.uid,iid,amount) if mode=='buy' else SellCommand(pid,town.uid,iid,amount))
            return sim.log[-1].message if sim.log else ''

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

def _diagnostics_view(ctx:GameContext,term:Terminal)->str:
    """Show the exact playtest log users can hand back for diagnosis."""
    path=Path(debug_log_path(ctx.sim))
    try:ctx.sim.debug.flush()
    except Exception:pass
    slow=[]
    recent_errors=[]
    if path.exists():
        try:
            lines=path.read_text(encoding='utf-8',errors='replace').splitlines()[-600:]
            for raw in lines:
                try:row=json.loads(raw)
                except Exception:continue
                if not isinstance(row,dict):continue
                if row.get('kind')=='stage' and row.get('slow'):
                    slow.append(f"{row.get('name','stage')}: {row.get('elapsed_ms',0)} ms")
                elif row.get('kind')=='command_end' and row.get('slow'):
                    slow.append(f"{row.get('command','command')}: {row.get('elapsed_ms',0)} ms")
                elif row.get('kind')=='exception':
                    recent_errors.append(f"{row.get('where','runtime')}: {row.get('error','')}")
        except OSError:pass
    size=path.stat().st_size if path.exists() else 0
    lines=[
        'WORLDSEED writes one bounded JSONL diagnostics stream for this play session.',
        '',
        'DEBUG LOG',
        str(path),
        f'Size: {size/1024:.1f} KB',
        f'Turn: {ctx.sim.turn}  Minute: {ctx.sim.clock.minute}',
        f'Position: {ctx.sim.player_pos.x}, {ctx.sim.player_pos.y}, z{ctx.sim.player_pos.z}',
        '',
        'WHAT IT RECORDS',
        '• engine commands and elapsed time',
        '• region/village activation stages and slow-stage flags',
        '• UI actions and gameplay messages',
        '• saves and performance timing',
        '• crashes/exceptions with full Python traceback',
    ]
    if slow:lines+=['','RECENT SLOW OPERATIONS']+['• '+row for row in slow[-12:]]
    if recent_errors:lines+=['','RECENT ERRORS']+['• '+row for row in recent_errors[-6:]]
    profiler=getattr(ctx.sim,'profiler',None)
    if profiler is not None and profiler.enabled:
        report=profiler.snapshot()
        lines+=['','RUNTIME TIMINGS (milliseconds)',
                f"Percentiles cover up to {report['max_samples']} recent samples per stage; lifetime worst retains older stalls."]
        for name,row in sorted(report['stages'].items()):
            lines.append(f"{name}: p50 {row['p50_ms']:.2f}  p95 {row['p95_ms']:.2f}  p99 {row['p99_ms']:.2f}  worst {row['lifetime_worst_ms']:.2f}  n={row['window_count']}")
        if report['dropped_stages']:
            lines.append(f"Stage limit reached: {report['dropped_stages']} unretained samples.")
    else:
        lines+=['','Enable runtime timing with --profile-runtime or WORLDSEED_PROFILE=1.']
    lines+=['','If a freeze or crash occurs, send this JSONL file together with WORLDSEED_CRASH.log if one was created.']
    _view_text(term,box('SESSION DIAGNOSTICS',lines,screen_width(term.size()[0],112)))
    return UI_BACK

def _try_save(ctx:GameContext,term:Terminal|None=None,*,backup:bool=True)->bool:
    """Keep failed checkpoints recoverable without leaving the live world."""
    try:
        if backup:_save(ctx)
        else:_save(ctx,backup=False)
        return True
    except Exception as exc:
        message='Save failed. Current changes remain in memory.'
        path=str(ctx.db.path)
        try:ctx.sim.debug.exception('save',exc,world=path,backup=bool(backup))
        except Exception:pass
        try:ctx.sim._message(message)
        except Exception:pass
        if term is not None:
            pause=getattr(term,'pause_realtime',None)
            try:
                with pause() if callable(pause) else nullcontext():
                    _view_text(term,box('SAVE FAILED',[
                        message,
                        f'Save path: {path}',
                        f'Error: {exc}',
                        'After fixing disk space or access to this path, open Pause > Save game to retry.',
                        'Resume keeps the current session open.'
                    ],screen_width(term.size()[0],110)),title='SAVE FAILED')
            except Exception:
                # A second window-close request while reading the error cannot
                # discard the live world. Recovery still returns to the caller.
                pass
        return False


def _pause_menu(ctx:GameContext,term:Terminal)->str:
    while True:
        choice=_select(term,'PAUSED',[
            ('resume','Resume game'),('save','Save game'),
            ('diagnostics','Session diagnostics / debug log'),
            ('console','Open World Console'),('menu','Save & return to main menu'),
            ('quit','Save & quit WORLDSEED')
        ],allow_escape=True)
        if not choice:return 'resume'
        if choice=='resume':return 'resume'
        if choice=='save':
            if _try_save(ctx,term):return 'saved'
            continue
        if choice=='diagnostics':_diagnostics_view(ctx,term);continue
        if choice=='console':_world_console(ctx,term);continue
        if choice in {'menu','quit'}:
            if _try_save(ctx,term):return choice

def _interior_context_menu(ctx,term,x:int,y:int,object_kind:str='',object_uid:str='')->str:
    """Pointer coordinates and objects belong to the current interior, not a tile."""
    sim=ctx.sim;plan=sim.interiors.current_plan();actor=sim.interiors.player_presence()
    if plan is None or actor is None:return UI_BACK
    furniture=(next((f for f in plan.furniture if f.uid==object_uid),None)
               if object_kind=='furniture' else sim.interiors.hit_test(x,y))
    stair=next((s for s in getattr(plan,'stairs',()) if s.uid==object_uid),None) if object_kind=='stairs' else None
    container=sim.interiors.container_for_furniture(furniture.uid) if furniture is not None else None
    rows=[]
    if stair is not None:
        rows.append(('stairs',f'Go {stair.direction} stairs'))
    if furniture is not None:
        piece=sim.registry.settlement_pieces.get(furniture.piece_id)
        label=piece.name if piece else furniture.piece_id.split(':')[-1].replace('_',' ').title()
        if container is not None:
            label=container.name
            rows=[('inspect_storage',f'Inspect {label}')]
            if sim.interiors.container_in_reach(container.uid):
                blocked=sim.property_storage.blocks_actor(container,'player')
                if not blocked:rows.append(('open_storage',f'Open {label}'))
                elif sim.state.player_hunting_stance=='aggressive':
                    rows.append(('pick_storage',f'Pick {label} lock'))
            if furniture.piece_id in STATION_PIECE_ALIASES:
                rows.append(('use','Craft at '+label))
        else:
            rows=[('inspect',f'Inspect {label}'),('use',f'Use {label}')]
        if sim.interiors.can_rearrange(furniture):rows.append(('move',f'Reposition {label} freely'))
    for uid,presence in sim.interiors.actors_in_space(plan.uid):
        n=sim.state.npcs.get(uid)
        if n is not None and n.alive and (presence.x-x)**2+(presence.y-y)**2<=500**2:
            rows.append((f'talk:{uid}',f'Talk to {n.name if uid in sim.introduced_npc_ids() else "Stranger"}'))
    if getattr(plan,'floor_index',0)==0:
        rows.append(('exit','Leave through the entrance'))
    else:
        rows.append(('floor_info','Upstairs — use the stairs to reach the outside entrance'))
    if stair is None:
        for nearby in getattr(plan,'stairs',()):
            if (nearby.x+nearby.w//2-actor.x)**2+(nearby.y+nearby.h//2-actor.y)**2<=1800**2:
                rows.append(('stairs:'+nearby.uid,f'Go {nearby.direction} stairs'))
    if any((p.x-actor.x)**2+(p.y-actor.y)**2<=1400**2 for p in plan.piles):rows.append(('pickup','Collect nearby floor items'))
    choice=_select(term,'INTERIOR ACTIONS',rows,subtitle='Objects use their actual position and outline.',presentation='world_context')
    if choice=='stairs' and stair is not None:sim.execute(UseInteriorStairsCommand(ctx.player_id,stair.uid))
    elif choice and choice.startswith('stairs:'):sim.execute(UseInteriorStairsCommand(ctx.player_id,choice.split(':',1)[1]))
    elif choice=='floor_info':return 'Follow the stairs down to the ground-floor entrance.'
    elif choice=='exit':sim.execute(ExitInteriorCommand(ctx.player_id))
    elif choice=='pickup':sim.execute(PickupCommand(ctx.player_id))
    elif choice=='open_storage' and container is not None:
        sim.execute(UseInteriorFurnitureCommand(ctx.player_id,furniture.uid))
        return _storage_menu(ctx,term,container.uid)
    elif choice=='pick_storage' and container is not None:
        sim.execute(LockpickContainerCommand(ctx.player_id,container.uid))
    elif choice=='inspect_storage' and container is not None:
        reachable=sim.interiors.container_in_reach(container.uid)
        blocked=sim.property_storage.blocks_actor(container,'player')
        rows=[label,f'Lock: {"locked" if container.locked else "unlocked"}',
              'Private property: unauthorized removal is theft.' if container.owner!='player' and container.access!='public' else 'Accessible storage.',
              'Move closer; walls block interaction.' if not reachable else
              ('Contents concealed by the lock.' if blocked else 'Open to inspect the contents.')]
        from worldseed.systems.furniture_storage import storage_function
        function=storage_function(furniture.piece_id)
        if function:rows.append('Use: '+function['purpose'])
        rows.append(f'Capacity: {container.capacity_mass_g/1000:g} kg / {container.capacity_volume_ml/1000:g} L')
        _view_text(term,box('INDOOR STORAGE',rows,screen_width(term.size()[0],88)))
        return UI_BACK
    elif choice=='use' and furniture is not None:
        station=STATION_PIECE_ALIASES.get(furniture.piece_id)
        if station:
            status=sim.interiors.furniture_use_status(furniture.uid)
            if status=='busy':return 'This workstation is busy with a worker; wait until its reservation finishes.'
            if status!='available':return 'Move closer to this station; walls block interaction.'
            return _crafting_menu(ctx,term,'workshops',station)
        sim.execute(UseInteriorFurnitureCommand(ctx.player_id,furniture.uid))
    elif choice=='move' and furniture is not None:
        term._interior_placing=furniture.uid
        return 'Left-click a free position for the furniture; right-click cancels. Placement respects walls, objects and exits.'
    elif choice=='inspect' and furniture is not None:
        from worldseed.ui.interior_workstation import workstation_details
        detail=workstation_details(sim,furniture)
        geometry=f'{label}\nPosition {furniture.x/1000:.2f}, {furniture.y/1000:.2f}\nSize {furniture.w/1000:.2f} × {furniture.h/1000:.2f}\nFree placement; no outdoor tile snapping.'
        _view_text(term,detail or geometry,title='INTERIOR WORKSTATION' if detail else 'INTERIOR OBJECT')
        return UI_BACK
    elif choice and choice.startswith('talk:'):return _talk_action(ctx,term,choice.split(':',1)[1])
    else:return UI_BACK
    return sim.log[-1].message if sim.log else ''

def run_game(ctx:GameContext,term:Terminal)->str:
    # Track attempts, including failures, so a failed autosave cannot repeat on
    # every redraw. Pause > Save game remains available for an immediate retry.
    renderer=Renderer(ctx.registry);last='';autosave_attempt=ctx.sim.turn
    realtime=RealtimeSimulationDriver(ctx.sim);realtime.resume()
    action_presenter=getattr(term,'present_timed_action',None)
    if callable(action_presenter):
        def display_timed_action(command,minutes,advance):
            try:
                action_presenter(command,minutes,advance,
                                 lambda:_present_game_frame(term,ctx,renderer))
            finally:
                # Progress has already advanced the authoritative clock. The
                # normal realtime driver must not catch up wall seconds spent
                # animating the action and charge them a second time.
                if not realtime.paused:realtime.resume()
        ctx.sim._action_progress_callback=display_timed_action
    install=getattr(term,'set_realtime_callback',None)
    if callable(install):install(realtime.pump)
    install_free=getattr(term,'set_free_movement_callback',None)
    if callable(install_free):
        ctx.sim.set_free_movement_enabled(True)
        install_free(ctx.sim.update_free_movement)
    install_combat=getattr(term,'set_combat_callback',None)
    if callable(install_combat):install_combat(ctx.sim.combat_active)
    try:
      while True:
        _present_game_frame(term,ctx,renderer,last);last=''
        key=term.read_key()
        if key=='UI_REDRAW':
            if ctx.sim.turn-autosave_attempt>=AUTOSAVE_TURNS:
                saved=_try_save(ctx,term,backup=False);autosave_attempt=ctx.sim.turn
                last='Autosaved.' if saved else 'Autosave failed. Current changes remain in memory. Pause > Save game to retry.'
            continue
        try:
            ctx.sim.debug.event("ui_input",key=str(key),presentation=str(getattr(term,"_current_presentation","")))
        except Exception:
            pass
        if key=='UI_BLUEPRINT_CANCEL':
            last='Cabin blueprint placement cancelled.';continue
        if key.startswith('UI_BLUEPRINT_PLACE:'):
            _,x,y,turns=key.split(':')
            pending=getattr(term,'_homestead_placement',None)
            if not pending:
                last='Select a home in the Build menu first.'
                continue
            style=str(pending['style_id'])
            old=set(ctx.sim.state.homesteads)
            ctx.sim.execute(PlaceBlueprintCommand(ctx.player_id,style,int(x),int(y),int(turns)))
            placed=bool(set(ctx.sim.state.homesteads)-old)
            if placed:term._homestead_placement=None
            last=ctx.sim.log[-1].message if ctx.sim.log else ''
            continue
        if key.startswith('UI_WORLD_MENU:'):
            _,x,y=key.split(':')
            target=WorldPos(int(x),int(y),ctx.sim.player_pos.z)
            site=ctx.sim.homestead.at(target)
            player=ctx.sim.player_pos
            if site is not None and int(site['stage'])<4 and abs(target.x-player.x)+abs(target.y-player.y)<=8:
                result=_homestead_blueprint_panel(ctx,term,site['uid'])
            else:
                result=_world_context_menu(ctx,term,target)
            last='' if result==UI_BACK else result
            continue
        if key.startswith('UI_BUILDING_MENU:'):
            _,part,uid=key.split(':',2);result=_building_context_menu(ctx,term,uid,part);last='' if result==UI_BACK else result;continue
        if key.startswith('INTERIOR_MOVE:'):
            _,dx,dy=key.split(':');ctx.sim.execute(MoveCommand(ctx.player_id,int(dx),int(dy)));continue
        if key.startswith('INTERIOR_CONTEXT:'):
            term._interior_placing=None
            _,x,y=key.split(':');result=_interior_context_menu(ctx,term,int(x),int(y));last='' if result==UI_BACK else result;continue
        if key.startswith('INTERIOR_OBJECT:'):
            term._interior_placing=None
            _,kind,uid=key.split(':',2)
            actor=ctx.sim.interiors.player_presence()
            if actor:
                result=_interior_context_menu(ctx,term,actor.x,actor.y,kind,uid)
                last='' if result==UI_BACK else result
            continue
        if key.startswith('INTERIOR_PLACE:'):
            uid=getattr(term,'_interior_placing',None);term._interior_placing=None
            if uid:
                _,x,y=key.split(':');ctx.sim.execute(MoveFurnitureCommand(ctx.player_id,uid,int(x),int(y)))
                last=ctx.sim.log[-1].message if ctx.sim.log else ''
            continue
        intent=classify_key(key)
        if intent.kind=='quit':
            if _try_save(ctx,term):return 'quit'
            last='Save failed. Current changes remain in memory. Pause > Save game to retry.'
            continue
        if intent.kind=='pause':
            realtime.pause()
            choice=_pause_menu(ctx,term)
            if choice=='quit':return 'quit'
            if choice=='menu':return 'menu'
            if choice=='saved':last='Game saved.'
            realtime.resume()
            continue
        if intent.kind=='actions':
            if ctx.sim.interiors.player_presence() is not None:
                a=ctx.sim.interiors.player_presence();last=_interior_context_menu(ctx,term,a.x,a.y)
            else:last=_action_palette(ctx,term)
            continue
        if intent.kind=='stance':
            ctx.sim.execute(SetHuntingStanceCommand(ctx.player_id,str(intent.value)))
            last=ctx.sim.log[-1].message if ctx.sim.log else ''
            continue
        if intent.kind=='console':_world_console(ctx,term);continue
        if intent.kind=='settings':_settings(ctx,term);continue
        if ctx.sim.interiors.player_presence() is not None and intent.kind in {'gather','farm','vertical'}:
            last='That action requires outdoor ground. Right-click furniture for interior actions.';continue
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
        if ctx.sim.turn-autosave_attempt>=AUTOSAVE_TURNS:
            saved=_try_save(ctx,term,backup=False);autosave_attempt=ctx.sim.turn
            last='Autosaved.' if saved else 'Autosave failed. Current changes remain in memory. Pause > Save game to retry.'
    finally:
        if callable(action_presenter):ctx.sim._action_progress_callback=None
        if callable(install):install(None)
        if callable(install_free):
            install_free(None)
            ctx.sim.set_free_movement_enabled(False)
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
                while True:
                    try:
                        outcome=run_game(ctx,term)
                        break
                    except WindowCloseRequested:
                        if _try_save(ctx,term):
                            outcome='quit'
                            break
                        # Re-enter the same live context after a failed modal
                        # close; the database must stay open for retry/resume.
            except Exception as exc:
                # Session diagnostics are continuous, so a crash adds the full
                # traceback and state location to the same shareable JSONL log.
                try:
                    ctx.sim.debug.exception(
                        "run_game",exc,turn=int(ctx.sim.turn),minute=int(ctx.sim.clock.minute),
                        position=(ctx.sim.player_pos.x,ctx.sim.player_pos.y,ctx.sim.player_pos.z),
                        world=str(ctx.db.path),
                    )
                except Exception:
                    pass
                report=Path.cwd()/'WORLDSEED_CRASH.log'
                report.write_text(
                    f'WORLDSEED {ENGINE_VERSION} crash at {time.ctime()}\n'
                    f'world={ctx.db.path}\nturn={ctx.sim.turn}\n'
                    f'position={ctx.sim.player_pos}\nminute={ctx.sim.clock.minute}\n'
                    f'debug_log={debug_log_path(ctx.sim)}\n\n'
                    +traceback.format_exc(),
                    encoding='utf-8',
                )
                try:
                    _view_text(term,box('WORLDSEED ERROR',[
                        'The current session stopped because of an unexpected error.',
                        f'Crash summary: {report.name}',
                        f'Session debug log: {debug_log_path(ctx.sim)}',
                        'Send both files with the seed/coordinates when reporting the issue.'
                    ],min(110,term.size()[0]-2)))
                except Exception:
                    pass
                outcome='menu'
            finally:
                ctx.db.close()
            if outcome=='quit':return 0
            # 'menu' simply loops back into the retained terminal main menu.
    except WindowCloseRequested:
        return 0
    finally:
        term.restore()
