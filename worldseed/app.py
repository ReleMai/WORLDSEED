from __future__ import annotations
from dataclasses import asdict, dataclass
from pathlib import Path
import secrets,sys,time,traceback
from worldseed.config import AUTOSAVE_TURNS,DATA_DIR,DEFAULT_SAVE_DIR,ENGINE_VERSION,RESOURCEGEN_VERSION,INITIAL_PREGEN_CHUNK_RADIUS,LOAD_WARM_CHUNK_RADIUS,CHUNK_SIZE
from worldseed.content.registry import ContentRegistry
from worldseed.content.mods import ModManager, ModError
from worldseed.core.coords import WorldPos, split_world
from worldseed.core.rng import PCG32, derive_seed
from worldseed.entities.components import Inventory,PlayerControlled,Position,Renderable,Vitals
from worldseed.entities.store import EntityStore
from worldseed.persistence.database import WorldDatabase
from worldseed.sim.commands import *
from worldseed.sim.engine import Simulation
from worldseed.systems.state import LivingWorldState, pos_key
from worldseed.systems.resources import ResourceSystem
from worldseed.systems.generation import ProceduralSocietyGenerator
from worldseed.systems.settlement_planner import SettlementSkeletonPlanner, settlement_rank_for_population
from worldseed.world.region_blocks import RegionBlockPlanner
from worldseed.ui.renderer import Renderer
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
    civilization=RegionalCivilizationPlanner(world,getattr(world,"settlement_plan_version",1))
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
                if not civilization.profile(rx,ry).settlement_present:continue
                rng=PCG32(derive_seed(seed,"settlement",rx,ry))
                pop=25+rng.randbelow(110)
                target=VillageTarget(rx,ry,pop)
                row=(abs(rx)+abs(ry),ry,rx,target)
                (villages if settlement_rank_for_population(pop)=='village' else others).append(row)
        if len(villages)>=max(3,limit//2):break
    ordered=sorted(villages,key=lambda row:(row[0],row[1],row[2]))
    ordered+=sorted(others,key=lambda row:(row[0],row[1],row[2]))
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
        from worldseed.config import SETTLEMENT_PLAN_VERSION
        world.settlement_plan_version=SETTLEMENT_PLAN_VERSION
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
    p=ctx.entities.get(ctx.player_id,Position).value;inv=ctx.entities.get(ctx.player_id,Inventory);v=ctx.entities.get(ctx.player_id,Vitals);ctx.sim.state.last_offline_wall_time=time.time()
    # Rotating full-database backups are intentionally reserved for explicit
    # save/menu/quit checkpoints. Copying an ever-growing generated-world DB on
    # every routine autosave caused increasingly long apparent freezes during
    # exploration. Autosave still commits all authoritative state atomically.
    if backup and ctx.db.path.exists() and ctx.db.path.stat().st_size>0:
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
    lines+=['','Move around the exterior to survey access. Entering rooms reveals only the spaces and storage you physically reach.']
    _view_text(term,box('CASING NOTES',lines,screen_width(term.size()[0],96)))
    return UI_BACK


def _steal_property_storage_action(ctx:GameContext,term:Terminal,container)->str:
    sim=ctx.sim;reg=ctx.registry;pid=ctx.player_id
    if not sim.state.player_stealth_mode or sim.state.player_casing_property_id!=container.property_id:
        return 'Case this property in stealth mode before attempting storage theft.'
    intel=sim.casing.intel_for(container.property_id)
    if intel is None or container.uid not in intel.storage_uids:
        return 'You have not located this storage while casing the property.'
    if abs(container.x-sim.player_pos.x)+abs(container.y-sim.player_pos.y)>1 or container.z!=sim.player_pos.z:
        return 'Move next to the storage before attempting theft.'
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
    sim=ctx.sim;reg=ctx.registry;inv=ctx.entities.get(ctx.player_id,Inventory);stations=sim.building.nearby_station_ids(sim.player_pos);water=_nearby_water(sim) or inv.count('core:clean_water')>0
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
            for item in sorted(reg.items.values(),key=lambda q:(q.category,q.name)):
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

def _storage_menu_terminal(ctx:GameContext,term:Terminal,container_uid:str|None=None)->str:
    sim=ctx.sim;reg=ctx.registry;pid=ctx.player_id;inv=ctx.entities.get(pid,Inventory)
    c=next((row for row in sim.state.containers.values() if row.uid==container_uid),None) if container_uid else sim.building.nearby_container(sim.player_pos)
    if not c and container_uid:
        _view_text(term,box('STORAGE',['That container is no longer available.'],screen_width(term.size()[0],88)));return UI_BACK
    if not c:
        _view_text(term,box('STORAGE',['No accessible container is adjacent to you.'],screen_width(term.size()[0],88)));return UI_BACK
    if c.kind=='property' and c.owner!='player' and c.access!='public':
        _view_text(term,box('PRIVATE STORAGE',['This storage belongs to someone else. Locate it while casing the property to expose theft actions.'],screen_width(term.size()[0],88)));return UI_BACK
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
    if container.kind=='property' and container.owner!='player' and container.access!='public':
        _view_text(term,box('PRIVATE STORAGE',['This storage belongs to someone else. Locate it while casing the property to expose theft actions.'],screen_width(term.size()[0],88)));return UI_BACK
    uid=container.uid
    nav=NavigationStack(RouteState('container-inventory','CONTAINER STORAGE'))
    action_amount=1;last_selected=None;status=''
    while True:
        container=next((row for row in sim.state.containers.values() if row.uid==uid),None)
        if not container:return status or UI_BACK
        inv=ctx.entities.get(pid,Inventory)
        pack_data=_inventory_ui_data(reg,inv,sim)
        container_data=_inventory_ui_data(reg,Inventory(dict(container.items)),sim,False)
        entries={};rows=[]
        pack_rows=[];container_rows=[]
        for iid,meta in sorted(pack_data['items'].items(),key=lambda kv:kv[1]['name']):
            key=f'pack|{iid}';entries[key]={**meta,'side':'pack','iid':iid};pack_rows.append((key,f"{meta['name']} x{meta['count']}"))
        for iid,meta in sorted(container_data['items'].items(),key=lambda kv:kv[1]['name']):
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
        subtitle=status or 'Click either side • right-click for actions • Shift-click transfers the full stack. Natural containers can also be moved or broken apart.'
        status=''
        choice=_stack_menu(term,nav,rows,subtitle=subtitle,presentation='container_inventory',presentation_data=data)
        if choice is None:return UI_BACK
        if choice=='__BACK__':continue
        if not choice.startswith('UI_ACTION:'):
            last_selected=choice;action_amount=1;continue
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
            else:sim.execute(TakeFromContainerCommand(pid,iid,amount,uid))
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
    home=sim.settlement_physicalization.structure_by_id(npc.home_id) if npc.home_id else None
    work=sim.settlement_physicalization.structure_by_id(npc.workplace_id) if npc.workplace_id else None
    name=npc.name if npc.uid in known else 'Stranger'
    occupation=npc.occupation.replace('_',' ').title() if npc.uid in known else 'Unknown'
    summary={
        'name':name,'age':npc.age if npc.uid in known else None,'occupation':occupation,
        'settlement':town.name if town and town.uid in sim.known_settlement_ids() else 'Unknown',
        'activity':str(npc.goal or 'idle').replace('_',' ').title(),
        'home':home.function.replace('_',' ').title() if home else '',
        'workplace':work.function.replace('_',' ').title() if work else '',
        'traits':[str(v).title() for v in npc.traits] if familiarity>=16 else [],
        'familiarity':familiarity,
    }
    tabs={}
    overview=[
        ('Age',str(npc.age) if npc.uid in known else 'Unknown'),
        ('Occupation',occupation),
        ('Settlement',summary['settlement']),
        ('Current activity',summary['activity']),
    ]
    if summary['home']:overview.append(('Home',summary['home']))
    if summary['workplace']:overview.append(('Workplace',summary['workplace']))
    if familiarity>=16 and npc.traits:overview.append(('Traits',', '.join(x.title() for x in npc.traits)))
    if familiarity>=24 and npc.wants:overview.append(('Wants',', '.join(str(x) for x in npc.wants[:3])))
    if familiarity>=32 and npc.backstory:
        for key in ('birthplace','upbringing','formative_event','ambition'):
            if npc.backstory.get(key):
                overview.append((key.replace('_',' ').title(),str(npc.backstory[key]).capitalize()))
    tabs['overview']=overview

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
    tabs['relations']=relations[:8] or [('Relations','No known relationships')]

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

    return {'summary':summary,'tabs':tabs,'active_tab':active_tab}


def _npc_profile_menu(ctx:GameContext,term:Terminal,npc_uid:str)->str:
    sim=ctx.sim;npc=sim.state.npcs.get(npc_uid)
    if npc is None or not npc.alive:return UI_BACK
    if npc.uid not in sim.known_npc_ids():
        return 'Talk to this person before viewing their profile.'
    tabs=(('overview','Overview'),('family','Family'),('relations','Relations'),('needs','Needs'),('history','History'))
    active='overview'
    while True:
        initial=next((i for i,row in enumerate(tabs) if row[0]==active),0)
        data=_npc_profile_data(sim,npc,active)
        summary=data['summary']
        subtitle=f"{summary['occupation']} · {summary['settlement']} · {summary['activity']}"
        choice=_select(
            term,npc.name,list(tabs),initial=initial,subtitle=subtitle,
            presentation='npc_profile',presentation_data=data,
        )
        if not choice:return UI_BACK
        active=choice
        if not getattr(term,'mouse_ui',False):
            page=_npc_profile_data(sim,npc,active)['tabs'].get(active,())
            lines=[]
            for row in page:
                if active=='needs':
                    lines.append(f'{row[0]}: {row[1]}')
                else:
                    lines.append(f'{row[0]}: {row[1]}')
            _view_text(term,'\n'.join(lines) or 'No known information.',title=f'{npc.name} · {active.title()}')


def _world_context_menu(ctx:GameContext,term:Terminal,target:WorldPos)->str:
    """Context actions for a right-clicked world tile; only mutations enforce reach."""
    sim=ctx.sim;p=sim.player_pos
    if target.z!=p.z:return UI_BACK
    distance=abs(target.x-p.x)+abs(target.y-p.y)
    rows=[]
    container=sim.building.container_at(target)
    pile=sim.state.ground_piles.get(pos_key(target.x,target.y,target.z))
    creature=next((c for c in sim.state.creatures.values() if c.hp>0 and (c.x,c.y,c.z)==(target.x,target.y,target.z)),None)
    npc=next((n for n in sim.state.npcs.values() if n.alive and (n.x,n.y,n.z)==(target.x,target.y,target.z)),None)
    physical=sim.settlement_physicalization.cell_at(target)
    planned=sim.settlement_physicalization.structure_by_id(physical.structure_id) if physical and physical.structure_id else None
    door=sim.property_security.door_at(target)
    signs=sim.hunting.signs_at(target)
    home=sim.hunting.home_at(target)
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
        known=npc.uid in sim.known_npc_ids()
        label=npc.name if known else 'Stranger'
        if known:rows.append(('inspect_npc',f'Inspect {label} — {npc.occupation.replace("_"," ")}'))
        else:rows.append(('observe_npc','Observe person — identity unknown'))
        if distance<=1:rows.append(('talk_npc',f'Talk to {label}'))
    private_storage=bool(container and container.kind=='property' and container.owner!='player' and container.access!='public')
    if door is not None and distance<=1:
        if door.locked and not door.forced and not sim.property_security.authorized_player(door):
            intel=sim.casing.intel_for(door.property_id)
            lock_known=bool(intel and door.uid in intel.lock_uids)
            lock_label=sim.property_security.lock_band(door.lock_level) if lock_known else 'unknown'
            rows.append(('inspect_property_door',f'Inspect locked door — lock {lock_label}'))
            inv=ctx.entities.get(ctx.player_id,Inventory)
            if inv.count('core:lockpick')>0:
                rows.append(('lockpick_property_door',f'Pick lock — {lock_label}'))
            else:
                rows.append(('lockpick_property_door','Pick lock — requires Lockpick'))
            rows.append(('force_property_door',f'Force entry — door condition {door.condition}%'))
        elif door.forced:
            rows.append(('inspect_property_door',f'Inspect forced doorway — condition {door.condition}%'))
    if planned is not None:
        building_label=str(planned.function).replace('_',' ').title()
        active_case=str(sim.state.player_casing_property_id or '')
        if active_case==planned.uid:
            rows.append(('review_casing',f'Review casing notes — {building_label}'))
            rows.append(('stop_casing','Stop casing this property'))
        elif distance<=2:
            rows.append(('begin_casing',f'Begin casing from here — {building_label}'))
        if planned.function=='market' and sim.state.player_stealth_mode and distance<=2:
            rows.append(('steal_market_here','Steal from market stock'))
    if private_storage and distance<=1:
        intel=sim.casing.intel_for(container.property_id)
        if (
            sim.state.player_stealth_mode
            and sim.state.player_casing_property_id==container.property_id
            and intel is not None and container.uid in intel.storage_uids
        ):
            rows.append(('steal_property_storage',f'Steal from {container.name}'))
    if signs:
        rows.append(('inspect_sign',f'Inspect animal sign — {len(signs)} trace(s) on this tile'))
    if home and home.discovered:
        rows.append(('inspect_home',f'Inspect {home.kind} — animal shelter'))
        if distance<=1:rows.append(('search_home',f'Search {home.kind} — {sum(home.stored_items.values())} cached item(s)'))
    if distance<=1 and sim.resources.is_harvestable(target):
        rows.append(('gather',f'Gather — {sim.resources.description(target)}'))
    if distance<=3 and sim.fishing.is_fishable(target):
        region=sim.fishing.region_at(target)
        rows.append(('fish',f'Fish — {sim.world.tile_at(target).terrain.name} / {region.structure.replace("_"," ")}'))
    if distance<=1 and pile and pile.items:
        count=sum(max(0,int(n)) for n in pile.items.values())
        rows.append(('pickup',f'Pick up ground items — {count} item(s)'))
    if distance<=1 and container and not private_storage:
        rows.append(('open',f'Open {container.name or "container"}'))
    rows.append(('examine','Examine tile and contents'))
    subtitle='Right-click world actions.' + (' Move closer for pickup/gather/container actions.' if distance>1 else '')
    choice=_select(term,f'WORLD ACTIONS {target.x},{target.y}',rows,subtitle=subtitle,
                   presentation='world_context',presentation_data={'target':(target.x,target.y,target.z)})
    if not choice:return UI_BACK
    if choice=='inspect_property_door' and door is not None:
        intel=sim.casing.intel_for(door.property_id)
        lock_known=bool(intel and door.uid in intel.lock_uids)
        lock_desc=sim.property_security.lock_band(door.lock_level) if lock_known else 'unknown; case the doorway closely to assess it'
        status='forced open' if door.forced else 'locked' if door.locked else 'unlocked'
        _view_text(term,box('PROPERTY DOOR',[
            f'Access: {door.access.title()}',
            f'Status: {status.title()}',
            f'Lock: {lock_desc}',
            f'Door condition: {door.condition}%',
        ],screen_width(term.size()[0],92)))
        return UI_BACK
    if choice=='lockpick_property_door' and door is not None:
        sim.execute(LockpickDoorCommand(ctx.player_id,door.uid))
        return sim.log[-1].message if sim.log else ''
    if choice=='force_property_door' and door is not None:
        sim.execute(ForceDoorCommand(ctx.player_id,door.uid))
        return sim.log[-1].message if sim.log else ''
    if choice=='begin_casing' and planned is not None:
        sim.execute(StartCasingCommand(ctx.player_id,planned.uid))
        return sim.log[-1].message if sim.log else ''
    if choice=='review_casing' and planned is not None:
        return _casing_notes(ctx,term,planned.uid)
    if choice=='stop_casing':
        sim.execute(StopCasingCommand(ctx.player_id))
        return sim.log[-1].message if sim.log else ''
    if choice=='steal_property_storage' and container:
        return _steal_property_storage_action(ctx,term,container)
    if choice=='steal_market_here' and planned is not None and physical is not None:
        town=sim.state.settlements.get(physical.settlement_id)
        if town:return _steal_market_action(ctx,term,town)
        return UI_BACK
    if choice=='inspect_npc' and npc:
        return _npc_profile_menu(ctx,term,npc.uid)
    if choice=='observe_npc' and npc:
        return 'Talk to this person to learn who they are.'
    if choice=='talk_npc' and npc:
        sim.execute(TalkCommand(ctx.player_id,target.x-p.x,target.y-p.y))
        return sim.log[-1].message if sim.log else ''
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
    for iid,n in inv.items.items():
        item=reg.items.get(iid)
        if not item or n<=0:continue
        cat=item.category or 'misc';categories[cat]=categories.get(cat,0)+n
        material=reg.materials.get(item.material) if item.material else None
        material_name=material.name if material else ''
        detail=[]
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
            for artifact in durable[:3]:
                detail.append(f'{artifact.name or item.name}: condition {artifact.condition}% | quality {artifact.quality}%')
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

def _recipe_ui_data(reg:ContentRegistry,sim:Simulation,inv:Inventory,recipes)->dict:
    stations=sim.building.nearby_station_ids(sim.player_pos)
    rows={}
    for r in recipes:
        missing=sim.crafting.missing_requirements(r.id,inv,stations)
        outputs=[{'id':iid,'name':reg.items[iid].name if iid in reg.items else iid,'qty':n,
                  'description':reg.items[iid].description if iid in reg.items else '',
                  'roles':list(reg.items[iid].utility_roles) if iid in reg.items else [],
                  'unit_mass_kg':reg.items[iid].mass_g/1000 if iid in reg.items else 0}
                 for iid,n in r.outputs.items()]
        inputs=[{'id':iid,'name':reg.items[iid].name if iid in reg.items else iid,'need':n,'have':inv.count(iid)} for iid,n in r.inputs.items()]
        inputs.extend({'id':iid,'name':(reg.items[iid].name if iid in reg.items else iid)+' (catalyst)','need':n,'have':inv.count(iid)} for iid,n in r.catalysts.items())
        rows[r.id]={
            'name':r.name,'category':r.category or 'general','description':r.description or '',
            'minutes':r.minutes,'difficulty':r.difficulty,'skill':r.skill,
            'station':reg.structures[r.station].name if r.station and r.station in reg.structures else '',
            'ready':not missing,'missing':list(missing),'outputs':outputs,'inputs':inputs,
            'new':r.id in set(getattr(sim.state,'player_unseen_recipes',[])),
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
            'id':rid,'name':r.name if status=='known' else 'Undiscovered technique','category':r.category or 'general','status':status,
            'parents':[x for x in parents.split(', ') if x],
            'outputs':[iid for iid in r.outputs if iid in reg.items],
            'minutes':r.minutes,
        })
    return {'nodes':nodes,'known':sum(1 for n in nodes if n['status']=='known'),'total':len(nodes)}


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
    nav=NavigationStack(RouteState('inventory','INVENTORY'))
    action_amount=1;last_selected=None;status='';active_filter='all'
    while True:
        inv=ctx.entities.get(pid,Inventory);route=nav.current
        data=_inventory_ui_data(reg,inv,sim)
        visible_items=[(iid,meta) for iid,meta in data['items'].items() if active_filter=='all' or meta.get('category')==active_filter]
        rows=[(iid,f"{meta['name']} x{meta['count']}") for iid,meta in sorted(visible_items,key=lambda kv:kv[1]['name'])]
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
        data.update({'selected_item_id':selected_iid,'action_amount':action_amount,'active_filter':active_filter,'filter_categories':sorted(data.get('categories',{}))})
        subtitle=status or 'Click to inspect • right-click for actions • Shift-click stores the full stack when a container is nearby.'
        status=''
        choice=_stack_menu(term,nav,rows,subtitle=subtitle,presentation='inventory_unified',presentation_data=data)
        if choice is None:return UI_BACK
        if choice=='__BACK__':continue
        if not choice.startswith('UI_ACTION:'):
            if choice!='__empty__':
                action_amount=1;last_selected=choice
            continue
        action=choice.split(':',1)[1]
        if action.startswith('filter:'):
            active_filter=action.split(':',1)[1] or 'all';route.selected=0;last_selected=None;action_amount=1;continue
        # Hover can change select_menu's retained row immediately before an
        # inline action click, so resolve the active item from the route again.
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

def _crafting_menu_graphical(ctx:GameContext,term:Terminal)->str:
    """One retained, movable crafting surface with recipe and discovery tabs."""
    sim=ctx.sim;reg=ctx.registry;pid=ctx.player_id
    tab='recipes';categories=sorted({r.category or 'general' for r in reg.recipes.values()})
    initial=sim.crafting.discovered_recipes(ctx.entities.get(pid,Inventory))
    category=(initial[0].category or 'general') if initial else ('primitive' if 'primitive' in categories else (categories[0] if categories else 'general'))
    category_page=categories.index(category)//12 if category in categories else 0
    recipe_state=RouteState('crafting-recipes','CRAFTING')
    pot_state=RouteState('crafting-pot','DISCOVERY')
    placed=[];status=''
    while True:
        inv=ctx.entities.get(pid,Inventory)
        if tab=='recipes':
            known=[r for r in sim.crafting.discovered_recipes(inv) if (r.category or 'general')==category]
            known.sort(key=lambda r:r.name)
            rows=[(r.id,r.name) for r in known] or [('__none__','No recipes in this category')]
            recipe_state.selected=max(0,min(recipe_state.selected,len(rows)-1))
            data=_recipe_ui_data(reg,sim,inv,known)
            unseen=set(getattr(sim.state,'player_unseen_recipes',[]));new_categories=sorted({reg.recipes[rid].category or 'general' for rid in unseen if rid in reg.recipes})
            data.update({'categories':categories,'category':category,'category_page':category_page,'new_categories':new_categories})
            choice=_select(term,'CRAFTING',rows,state=recipe_state,presentation='crafting_unified',
                           subtitle=status or 'Browse techniques and inspect exactly what each recipe produces.',presentation_data=data)
            status=''
            if choice is None:return UI_BACK
            if choice=='UI_ACTION:tab:discovery':tab='discovery';continue
            if choice=='UI_ACTION:tab:index':tab='index';continue
            if choice.startswith('UI_ACTION:category_page:'):
                page_size=6
                delta=1 if choice.endswith(':next') else -1
                category_page=max(0,min(category_page+delta,max(0,(len(categories)-1)//page_size)))
                continue
            if choice.startswith('UI_ACTION:category:'):
                category=choice.split(':',2)[2];recipe_state.selected=0;continue
            if choice in reg.recipes:
                sim.state.player_unseen_recipes=[rid for rid in sim.state.player_unseen_recipes if rid!=choice]
                continue
            if choice=='UI_ACTION:craft':
                rid=rows[recipe_state.selected][0]
                if rid in reg.recipes:
                    sim.execute(CraftCommand(pid,rid))
                    status=sim.log[-1].message if sim.log else ''
                continue
            continue
        if tab=='index':
            carried=[iid for iid,n in inv.items.items() if n>0 and iid in reg.items]
            carried.sort(key=lambda iid:reg.items[iid].name)
            if not carried:tab='discovery';status='Gather a material to see its possible recipes.';continue
            pot_state.selected=min(pot_state.selected,len(carried)-1)
            iid=carried[pot_state.selected]
            pool=sim.crafting.recipe_pool_for_item(iid)
            index_rows=[(r.id,(r.name if sim.crafting.recipe_is_discovered(r.id) else 'Undiscovered technique')+
                         f'  •  {r.category.replace("_"," ").title()}') for r in pool]
            if not index_rows:index_rows=[('__none__','No catalog recipes use this item')]
            choice=_select(term,'ITEM DISCOVERIES',index_rows,presentation='crafting_index',
                           presentation_data={'item_name':reg.items[iid].name,
                                              'known':sum(sim.crafting.recipe_is_discovered(r.id) for r in pool)},
                           subtitle='Possible recipes for the selected carried item.')
            if choice is None:return UI_BACK
            if choice=='UI_ACTION:tab:recipes':tab='recipes'
            elif choice=='UI_ACTION:tab:discovery':tab='discovery'
            continue
        entries={}
        for iid,n in sorted(inv.items.items(),key=lambda pair:reg.items[pair[0]].name if pair[0] in reg.items else pair[0]):
            if iid not in reg.items or n<=0:continue
            pool=sim.crafting.recipe_pool_for_item(iid)
            if not pool:continue
            entries[iid]={'name':reg.items[iid].name,'count':n,'pool_count':len(pool),
                          'known_recipes':[r.name for r in pool if sim.crafting.recipe_is_discovered(r.id)]}
        rows=[(iid,v['name']) for iid,v in entries.items()] or [('__none__','Gather materials to experiment')]
        pot_state.selected=max(0,min(pot_state.selected,len(rows)-1))
        from collections import Counter
        counts=Counter(placed);exact=sim.crafting.pot_candidates(tuple(placed),inv)
        known_exact=[r.name for r in reg.recipes.values()
                     if r.id in set(sim.state.player_discovered_recipes) and counts
                     and counts==Counter(sim.crafting.discovery_signature(r))]
        close=False
        if counts and not exact and not known_exact:
            for r in reg.recipes.values():
                if r.id in set(sim.state.player_discovered_recipes):continue
                if r.knowledge and r.knowledge not in sim.state.player_knowledge:continue
                sig=Counter(sim.crafting.discovery_signature(r))
                if sig and all(counts[i]<=sig.get(i,0) for i in counts):close=True;break
        mix_state='green' if exact else ('yellow' if close else 'red')
        data={'items':entries,'selected_items':tuple(placed),'candidates':len(exact),'known_exact':known_exact,'mix_state':mix_state}
        choice=_select(term,'EXPERIMENT GRID',rows,state=pot_state,presentation='discovery_pot',
                       subtitle=status or 'Combine up to five carried materials. The grid color shows how close the mix is to a discoverable recipe.',presentation_data=data)
        status=''
        if choice is None:return UI_BACK
        if choice=='UI_ACTION:tab:recipes':tab='recipes';continue
        if choice=='UI_ACTION:tab:index':tab='index';continue
        if choice.startswith('UI_ACTION:remove_slot:'):
            try:idx=int(choice.rsplit(':',1)[1])
            except ValueError:continue
            if 0<=idx<len(placed):placed.pop(idx)
            continue
        if choice=='UI_ACTION:clear':placed.clear();continue
        if choice=='UI_ACTION:mix':
            # The command validates quantities and chooses the recipe. The UI
            # animates only after the simulation reports a successful result.
            before=set(sim.state.player_discovered_recipes)
            ingredients=tuple(placed)
            sim.execute(DiscoveryPotCommand(pid,ingredients))
            status=sim.log[-1].message if sim.log else ''
            new=set(sim.state.player_discovered_recipes)-before
            if new:
                rid=next(iter(new));anim=getattr(term,'animate_discovery_pot',None)
                if callable(anim):anim(ingredients,reg.recipes[rid].name)
                placed.clear()
            continue
        if choice in entries:
            if len(placed)>=5:status='The experiment grid holds at most five items.'
            elif placed.count(choice)>=inv.count(choice):status='You do not carry another one of those.'
            else:placed.append(choice)


def _crafting_menu(ctx:GameContext,term:Terminal)->str:
    """Discovery-first crafting browser.

    The terminal backend keeps full keyboard parity while the pygame backend
    renders these top-level routes as graphical tabs/cards. All discovery
    mutation is performed by simulation commands; opening this UI is read-only.
    """
    if getattr(term,'mouse_ui',False) and callable(getattr(term,'present_feature_menu',None)):
        return _crafting_menu_graphical(ctx,term)
    sim=ctx.sim;reg=ctx.registry;pid=ctx.player_id;inv=ctx.entities.get(pid,Inventory)
    while True:
        known=sorted(sim.crafting.discovered_recipes(inv),key=lambda r:(r.category or 'general',r.name))
        ideas=sim.crafting.researchable_recipes(inv)
        discovered_items=set(sim.state.player_discovered_items)
        rows=[
            ('recipes',f'Discovered Recipes — {len(known)} known'),
            ('ideas','Experiment Grid — combine 1–5 carried items'),
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
            body=['Handled materials give clues. Combine carried materials in the experiment grid to uncover a matching recipe.','']
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
        buildable=[st for st in reg.structures.values() if 'natural_only' not in st.tags]
        groups=sorted(set(_structure_group(st) for st in buildable))
        group=_select(term,'CONSTRUCTION',[(g,f'{g.title()} — {sum(1 for st in buildable if _structure_group(st)==g)} plans') for g in groups])
        if not group:return UI_BACK
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
            price=sim.player_trade_price(town.uid,iid,mode=='buy')
            maximum=min(town.stocks.get(iid,0),inv.count('core:copper_coin')//max(1,price)) if mode=='buy' else inv.count(iid)
            quantities=[q for q in (1,5,10) if q<=maximum]
            if maximum>0 and maximum not in quantities:quantities.append(maximum)
            qrows=[]
            for q in quantities:
                total=q*price;local_name,units=sim.economy.currency_quote(town.uid,total)
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
        key=term.read_key()
        if key.startswith('UI_WORLD_MENU:'):
            _,x,y=key.split(':');result=_world_context_menu(ctx,term,WorldPos(int(x),int(y),ctx.sim.player_pos.z));last='' if result==UI_BACK else result;continue
        intent=classify_key(key)
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
            _save(ctx,backup=False);autosave=ctx.sim.turn;last='Autosaved.'
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
            except Exception:
                # Preserve an actionable traceback instead of leaving a playtest
                # with only a transient window freeze/close. Do not claim
                # recovery of corrupted state; return to the world selector
                # after recording diagnostics.
                report=Path.cwd()/'WORLDSEED_CRASH.log'
                report.write_text(
                    f'WORLDSEED {ENGINE_VERSION} crash at {time.ctime()}\n'
                    f'world={ctx.db.path}\nturn={ctx.sim.turn}\n'
                    f'position={ctx.sim.player_pos}\nminute={ctx.sim.clock.minute}\n\n'
                    +traceback.format_exc(),
                    encoding='utf-8',
                )
                try:
                    _view_text(term,box('WORLDSEED ERROR',[
                        'The current session stopped because of an unexpected error.',
                        f'Crash details were written to {report.name}.',
                        'Please keep that file with the seed/coordinates when reporting the issue.'
                    ],min(96,term.size()[0]-2)))
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
