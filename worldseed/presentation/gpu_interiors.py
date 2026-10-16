"""Detached live interiors, using the engine's physical walls and illumination.

One local metre is one world-space visual unit.  Visibility rectangles are
conservative: the complete triangle fan from the viewer to a floor rectangle
must avoid every authoritative wall.  Unlike point sampling, this cannot paint
through a thin wall or disclose a sliver of a private room.  This affects only
presentation; movement, interaction, doors and inventories stay in the engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from collections import Counter
from math import ceil, floor

from worldseed.systems.illumination import (indoor_actor_visible, indoor_light,
    indoor_sources, interior_ambient)
from worldseed.systems.interior_state import UNIT
from worldseed.systems.interior_visibility import (GRID, _rect_visible,
    visible_floor_rects, remembered_floor_rects)
from .gl_worldspace import MAX_COMMANDS, SpriteCommand
from .worldspace import WorldFoot

MAX_INTERIOR_WALLS = 256
MAX_INTERIOR_FIXTURES = 512
MAX_INTERIOR_ROOMS = 128
MAX_INTERIOR_TILES = 1024
MAX_INTERIOR_ACTORS = 256
_CONTACT_RGBA = bytes(channel for y in range(12) for x in range(32)
    for channel in (20, 15, 10, max(0, int(65*(1-((x-15.5)/16)**2-((y-5.5)/6)**2)))))


@dataclass(frozen=True, slots=True)
class InteriorTile:
    bounds: tuple[int, int, int, int]
    light: int
    room_name: str = ''


@dataclass(frozen=True, slots=True)
class InteriorObject:
    uid: str
    kind: str
    content_id: str
    bounds: tuple[float, float, float, float]
    height_ratio: float = 1.
    flat: bool = False
    solid: bool = False

    @property
    def piece_id(self):
        return self.content_id

    @property
    def direction(self):
        return self.content_id

    @property
    def x(self):
        return round(self.bounds[0]*UNIT)

    @property
    def y(self):
        return round(self.bounds[1]*UNIT)

    @property
    def w(self):
        return round((self.bounds[2]-self.bounds[0])*UNIT)

    @property
    def h(self):
        return round((self.bounds[3]-self.bounds[1])*UNIT)


@dataclass(frozen=True, slots=True)
class InteriorActorView:
    uid: str
    content_id: str
    foot: WorldFoot


@dataclass(frozen=True, slots=True)
class PreparedInterior:
    space_id: str
    name: str
    function: str
    floor_material: str
    wall_material: str
    floor_index: int
    floor_count: int
    tiles: tuple[InteriorTile, ...]
    walls: tuple[tuple[int, int, int, int], ...]
    objects: tuple[InteriorObject, ...]
    actors: tuple[InteriorActorView, ...]
    memory_tiles: tuple[InteriorTile, ...] = ()
    # Full source wall bounds, clipped to floor patches already explored.
    memory_walls: tuple[tuple[tuple[int,int,int,int],
                              tuple[tuple[int,int,int,int], ...]], ...] = ()
    memory_objects: tuple[InteriorObject, ...] = ()

    def hit_test(self, x: float, y: float):
        """Observational stable IDs; commands still revalidate physical reach."""
        if not any(a <= x*UNIT < c and b <= y*UNIT < d
                   for tile in self.tiles for a, b, c, d in (tile.bounds,)):
            return None
        return next((row for row in reversed(self.objects)
                     if row.bounds[0] <= x < row.bounds[2]
                     and row.bounds[1] <= y < row.bounds[3]), None)


def _overlap(a, b):
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


def _union_rects(rects):
    """Disjoint scissor strips prevent repeated alpha along wall fragments."""
    events={}
    for a,b,c,d in rects:
        if a < c and b < d:
            events.setdefault(b,[]).append((a,c,1))
            events.setdefault(d,[]).append((a,c,-1))
    active=Counter()
    strips=[]
    previous_y=None
    for y,changes in sorted(events.items()):
        if previous_y is not None and y > previous_y:
            intervals=[]
            for (a,c),count in sorted(active.items()):
                if count <= 0:
                    continue
                if intervals and a <= intervals[-1][1]:
                    intervals[-1]=(intervals[-1][0],max(c,intervals[-1][1]))
                else:
                    intervals.append((a,c))
            for a,c in intervals:
                strips.append((a,previous_y,c,y))
        for a,c,delta in changes:
            active[(a,c)]+=delta
            if active[(a,c)] == 0:
                del active[(a,c)]
        previous_y=y
    return tuple(strips)


def capture_interior(sim, camera):
    """Capture the entered, already-prepared floor; never prepare/open a room."""
    player, plan = sim.interiors.player_presence(), sim.interiors.current_plan()
    if player is None or plan is None or player.space_id != plan.uid:
        return None
    if (len(plan.walls) > MAX_INTERIOR_WALLS
            or len(plan.furniture) > MAX_INTERIOR_FIXTURES
            or len(plan.rooms) > MAX_INTERIOR_ROOMS
            or len(getattr(plan, 'stairs', ())) > 32
            or len(getattr(plan, 'piles', ())) > 128):
        return None  # oversized unsupported plans fail closed
    walls = tuple((w.x, w.y, w.x+w.w, w.y+w.h) for w in plan.walls)
    corner = camera.to_world(0, 0, ground_z=camera.center.z)
    far = camera.to_world(camera.width_px, camera.height_px, ground_z=camera.center.z)
    left, top = max(0, floor(corner.x*UNIT)), max(0, floor(corner.y*UNIT))
    right, bottom = min(plan.width, ceil(far.x*UNIT)), min(plan.height, ceil(far.y*UNIT))
    minute = sim.clock.minute
    ambient = interior_ambient(getattr(sim, 'environment', None), minute, plan)
    sources = indoor_sources(plan)
    tiles = []
    for rect in visible_floor_rects(plan,player.x,player.y,minute,ambient,sources,
                                    viewport=(left,top,right,bottom)):
        cx,cy=(rect[0]+rect[2])//2,(rect[1]+rect[3])//2
        room=next((r.name for r in plan.rooms if r.rect.contains(cx,cy)), '')
        light=indoor_light(plan,cx,cy,minute,ambient_light=ambient,sources=sources)
        tiles.append(InteriorTile(rect,light,room))
    if len(tiles) > MAX_INTERIOR_TILES:
        raise ValueError('interior viewport tile budget exceeded')

    # Remembered floor is independent of current light and LOS. Project only
    # the saved local cells, excluding cells intersecting live sight. Never
    # enumerate other buildings or expose their current furniture/actors.
    memory_tiles = []
    live_by_cell={}
    for tile in tiles:
        live_by_cell.setdefault((tile.bounds[0]//GRID,tile.bounds[1]//GRID),[]).append(tile)
    # Subtract live fragments exactly. A partially visible fine fragment must
    # not erase the rest of an already remembered coarse floor cell.
    for rect in remembered_floor_rects(plan):
        if not _overlap(rect,(left,top,right,bottom)):
            continue
        parts=[rect]
        for tile in live_by_cell.get((rect[0]//GRID,rect[1]//GRID),()):
            if not _overlap(rect,tile.bounds):
                continue
            next_parts=[]
            for a,b,c,d in parts:
                x,y,x1,y1=tile.bounds
                ix,iy,ix1,iy1=max(a,x),max(b,y),min(c,x1),min(d,y1)
                if ix >= ix1 or iy >= iy1:
                    next_parts.append((a,b,c,d))
                    continue
                next_parts.extend(part for part in ((a,b,c,iy),(a,iy1,c,d),
                    (a,iy,ix,iy1),(ix1,iy,c,iy1)) if part[0]<part[2] and part[1]<part[3])
            parts=next_parts
        for part in parts:
            cx,cy=(part[0]+part[2])//2,(part[1]+part[3])//2
            room=next((r.name for r in plan.rooms if r.rect.contains(cx,cy)), '')
            memory_tiles.append(InteriorTile(part,0,room))
    if len(memory_tiles) + len(tiles) > MAX_INTERIOR_TILES:
        # Keep the live LOS budget intact; memory is a presentation fallback.
        # Prioritize the closest remembered fragments when a huge viewport
        # exceeds the combined GPU command budget.
        memory_tiles.sort(key=lambda tile: (
            ((tile.bounds[0]+tile.bounds[2])//2-player.x)**2
            + ((tile.bounds[1]+tile.bounds[3])//2-player.y)**2,
            tile.bounds[1],tile.bounds[0]))
        memory_tiles = memory_tiles[:max(0,MAX_INTERIOR_TILES-len(tiles))]

    memory_walls = []
    old_walls=getattr(plan,'observed_walls',None)
    known_walls=walls if old_walls is None else tuple((w.x,w.y,w.x+w.w,w.y+w.h) for w in old_walls)
    for wall in known_walls:
        patches = []
        for tile in memory_tiles:
            a,b,c,d = tile.bounds
            # Only paint the part of the wall that borders remembered floor.
            adjacent = (a-250,b-250,c+250,d+250)
            clip = (max(wall[0],adjacent[0]),max(wall[1],adjacent[1]),
                    min(wall[2],adjacent[2]),min(wall[3],adjacent[3]))
            if clip[0] < clip[2] and clip[1] < clip[3]:
                patches.append(clip)
        if patches:
            memory_walls.append((wall, _union_rects(patches)))

    def admitted(rect):
        return any(_overlap(rect, tile.bounds) for tile in tiles)

    visible_walls = []
    # Only the exposed face of each authoritative wall is projected. Other
    # walls still occlude it; a wall never authorizes the floor behind itself.
    for index, wall in enumerate(walls):
        a, b, c, d = wall
        if not _overlap(wall, (left, top, right, bottom)):
            continue
        if a <= player.x < c:
            near = b-1 if player.y < b else d
            face = (a, near, c, near+1)
        elif b <= player.y < d:
            near = a-1 if player.x < a else c
            face = (near, b, near+1, d)
        else:
            # A corner can be seen on both axes; a conservative adjacent strip
            # suffices and avoids a diagonal peek into the neighboring room.
            near = b-1 if player.y < b else d
            face = (a, near, c, near+1)
        other = walls[:index]+walls[index+1:]
        if (max(abs(player.x-a), abs(player.y-b)) <= 12000
                and _rect_visible(player.x, player.y, face, other)):
            visible_walls.append(wall)

    from worldseed.systems.interior_furnishing import furniture_visual
    objects = []
    for fixture in plan.furniture:
        rect = (fixture.x, fixture.y, fixture.x+fixture.w, fixture.y+fixture.h)
        if admitted(rect):
            style = furniture_visual(fixture.piece_id)
            objects.append(InteriorObject(fixture.uid, 'furniture', fixture.piece_id,
                tuple(value/UNIT for value in rect), style['height_ratio'],
                style['flat'], bool(fixture.solid)))
    for stair in getattr(plan, 'stairs', ()):
        rect = (stair.x, stair.y, stair.x+stair.w, stair.y+stair.h)
        if admitted(rect):
            objects.append(InteriorObject(stair.uid, 'stairs', stair.direction,
                tuple(value/UNIT for value in rect), flat=True))
    if getattr(plan, 'floor_index', 0) == 0:
        rect = (plan.entry_x-500, plan.entry_y-700, plan.entry_x+500, plan.entry_y+200)
        if admitted(rect):
            objects.append(InteriorObject(plan.door_uid, 'exit', 'wood_open',
                tuple(value/UNIT for value in rect)))
    for pile in getattr(plan, 'piles', ()):
        if pile.items and admitted((pile.x-150, pile.y-150, pile.x+150, pile.y+150)):
            item = next((iid for iid, amount in pile.items.items() if amount > 0), None)
            if item:
                objects.append(InteriorObject(pile.uid, 'pile', item,
                    ((pile.x-300)/UNIT, (pile.y-300)/UNIT,
                     (pile.x+300)/UNIT, (pile.y+300)/UNIT), flat=True))
    current_uids={row.uid for row in objects}
    memory_objects=[]
    for row in getattr(plan,'observed_objects',())[:672]:
        rect=(row.x,row.y,row.x+row.w,row.y+row.h)
        if row.uid not in current_uids and any(_overlap(rect,tile.bounds) for tile in memory_tiles):
            memory_objects.append(InteriorObject(row.uid,row.kind,row.content_id,
                tuple(value/UNIT for value in rect),row.height_ratio,row.flat,row.solid))
    actors = []
    for uid, actor in sim.interiors.actors_in_space(plan.uid):
        if uid == 'player':
            continue
        npc = sim.state.npcs.get(uid)
        if npc is None or not npc.alive or npc.hp <= 0:
            continue
        if indoor_actor_visible(plan, player.x, player.y, actor.x, actor.y,
                minute, ambient_light=ambient):
            actors.append(InteriorActorView('npc:'+uid, 'core:npc:'+npc.sex
                if npc.sex in ('male', 'female') else 'core:npc',
                WorldFoot(actor.x/UNIT, actor.y/UNIT, camera.center.z)))
        if len(actors) >= MAX_INTERIOR_ACTORS:
            raise ValueError('interior actor budget exceeded')
    return PreparedInterior(plan.uid, plan.name, plan.function,
        getattr(plan, 'floor_material', ''), getattr(plan, 'wall_material', ''),
        getattr(plan, 'floor_index', 0), getattr(plan, 'floor_count', 1),
        tuple(tiles), tuple(visible_walls), tuple(objects), tuple(actors),
        tuple(memory_tiles), tuple(memory_walls), tuple(memory_objects))


def _texture(materials, category, content_id):
    supplied = getattr(materials, 'interior', None)
    if supplied is not None:
        return supplied(category, content_id)
    from .visuals import VisualRegistry
    if materials._visuals is None:
        materials._visuals = VisualRegistry.load_default()
    visuals = materials._visuals
    path = visuals.resolve(visuals.ref(category, content_id))
    if path is None and category == 'interior_textures':
        path = visuals.resolve(visuals.ref('interiors', content_id))
    if path is None and category == 'interiors':
        path = visuals.resolve(visuals.ref('settlement_pieces', content_id))
    if path is None:
        path = visuals.special('unknown')
    return materials.asset(path) if path is not None else None


def prepare_interior_frame(scene, camera, viewer, materials, *,
                           show_explored_memory=True):
    """Static asset sprites and small light quads, never a software world frame."""
    from .gpu_scene_bridge import GPUPreparedFrame
    from .visuals import VisualRegistry
    visuals = getattr(materials, '_visuals', None) or VisualRegistry.load_default()
    _floor_id, wall_id = visuals.interior_materials(scene.function,
        floor_material=scene.floor_material, wall_material=scene.wall_material)
    z = camera.center.z

    def screen_rect(rect, factor=1.):
        a, b, c, d = (value/factor for value in rect)
        return (*camera.to_screen(WorldFoot(a, b, z)),
                *camera.to_screen(WorldFoot(c, d, z)))

    clips = tuple(screen_rect(tile.bounds, UNIT) for tile in scene.tiles)
    memory_clips=tuple(screen_rect(tile.bounds,UNIT) for tile in scene.memory_tiles)
    def floor_source_bounds(tile):
        a,b,_,_=tile.bounds
        x,y=a//GRID*GRID,b//GRID*GRID
        a,b,c,d=screen_rect((x,y,x+GRID,y+GRID),UNIT)
        # Shared source edges can land exactly on pixel centres at an odd
        # viewport height. A tiny mesh apron avoids float raster cracks;
        # mandatory exact sight scissors remain the sole pixel admission.
        return (a-.01,b-.01,c+.01,d+.01)
    def admitted_clips(bounds, remembered=False):
        # Restrict work to intersecting sight patches. Passing every floor
        # patch to every sprite used to multiply draw operations in big rooms.
        return tuple((max(a,bounds[0]),max(b,bounds[1]),
                      min(c,bounds[2]),min(d,bounds[3]))
                     for a,b,c,d in (memory_clips if remembered else clips)
                     if _overlap((a,b,c,d),bounds))
    ground, scenery = [], []
    if show_explored_memory:
        for index, tile in enumerate(scene.memory_tiles):
            room_floor, _ = visuals.interior_materials(scene.function, tile.room_name,
                floor_material=scene.floor_material, wall_material=scene.wall_material)
            source = _texture(materials, 'interior_textures', room_floor)
            if source:
                bounds = screen_rect(tile.bounds, UNIT)
                ground.append(SpriteCommand('interior-memory-floor:'+str(index),
                    *source, floor_source_bounds(tile), (bounds,), opacity=.62, remembered=True))
    for index, tile in enumerate(scene.tiles):
        room_floor, _ = visuals.interior_materials(scene.function, tile.room_name,
            floor_material=scene.floor_material, wall_material=scene.wall_material)
        source = _texture(materials, 'interior_textures', room_floor)
        if source:
            ground.append(SpriteCommand('interior-floor:'+str(index), *source,
                floor_source_bounds(tile), (clips[index],)))
    if show_explored_memory:
        source = _texture(materials, 'interior_textures', wall_id) if scene.memory_walls else None
        if source:
            for index, (rect, parts) in enumerate(scene.memory_walls):
                scenery.append(((-3., 'memory-wall:'+str(index)), SpriteCommand(
                    'interior-memory-wall:'+str(index), *source,
                    screen_rect(rect, UNIT),
                    tuple(screen_rect(part, UNIT) for part in parts), opacity=.62, remembered=True)))
    for index, rect in enumerate(scene.walls):
        source = _texture(materials, 'interior_textures', wall_id)
        if source:
            bounds = screen_rect(rect, UNIT)
            wall_parts=[]
            for tile in scene.tiles:
                a,b,c,d=tile.bounds
                expanded=screen_rect((a-250,b-250,c+250,d+250),UNIT)
                if _overlap(bounds,expanded):
                    wall_parts.append((max(bounds[0],expanded[0]),max(bounds[1],expanded[1]),
                                       min(bounds[2],expanded[2]),min(bounds[3],expanded[3])))
            if not wall_parts:
                continue
            scenery.append(((-1., 'wall:'+str(index)), SpriteCommand('interior-wall:'+str(index),
                *source, bounds, _union_rects(wall_parts))))
    object_rows=tuple((row,False) for row in scene.objects)
    if show_explored_memory:
        object_rows+=tuple((row,True) for row in scene.memory_objects)
    for row,remembered in object_rows:
        category = {'furniture': 'interiors', 'stairs': 'interior_stairs',
                    'exit': 'building_doors', 'pile': 'items'}[row.kind]
        source = _texture(materials, category, row.content_id)
        if source is None:
            continue
        x0, y0, x1, y1 = screen_rect(row.bounds)
        width, height = x1-x0, (y1-y0)*row.height_ratio
        ratio = min(width/source[3], height/source[4])
        sw, sh = source[3]*ratio, source[4]*ratio
        cx = (x0+x1)/2
        bounds = (cx-sw/2, y1-sh, cx+sw/2, y1)
        object_clips=admitted_clips(bounds,remembered)
        if not object_clips:
            continue
        depth = -2. if row.flat else row.bounds[3]
        if row.solid and not remembered:
            shadow = ('interior-contact', 1, _CONTACT_RGBA, 32, 12)
            shadow_bounds=(x0+width*.05, y1-camera.scale*.12,
                           x1-width*.05, y1+camera.scale*.08)
            scenery.append(((depth-.001, row.uid), SpriteCommand(
                'interior-shadow:'+row.uid, *shadow,
                shadow_bounds, admitted_clips(shadow_bounds))))
        prefix='interior-memory-object:' if remembered else 'interior:'
        scenery.append(((depth, row.uid), SpriteCommand(prefix+row.uid,
            *source, bounds, object_clips,opacity=.62 if remembered else 1.,remembered=remembered)))
    for row in (InteriorActorView('player', 'core:player', viewer), *scene.actors):
        source = materials.player() if row.uid == 'player' else materials.actor(row.content_id)
        if source is not None:
            x, y = camera.to_screen(row.foot)
            width, height = camera.scale*.75, camera.scale*1.5
            scenery.append(((row.foot.y, row.uid), SpriteCommand('interior-actor:'+row.uid,
                *source, (x-width/2, y-height, x+width/2, y),
                admitted_clips((x-width/2, y-height, x+width/2, y)))))
    scenery.sort(key=lambda row: row[0])
    commands = [command for _, command in scenery]
    # Light is sampled by the shared wall-occluded engine authority. These
    # constant-source quads add darkness only within already-authorized floor.
    shade = ('interior-shade', 1, bytes((8, 12, 20, 255)), 1, 1)
    for index, tile in enumerate(scene.tiles):
        alpha = (65535-tile.light)*.55/65535
        a,b,c,d=clips[index]
        commands.append(SpriteCommand('interior-light:'+str(index), *shade,
            (a-.01,b-.01,c+.01,d+.01), (clips[index],), opacity=alpha))
    if len(ground)+len(commands) > MAX_COMMANDS:
        raise ValueError('interior draw budget exceeded')
    return GPUPreparedFrame(tuple(ground), tuple(commands), 0, len(ground))
