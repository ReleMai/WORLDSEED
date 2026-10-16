"""Detached live interiors, using the engine's physical walls and illumination.

One local metre is one world-space visual unit.  Visibility rectangles are
conservative: the complete triangle fan from the viewer to a floor rectangle
must avoid every authoritative wall.  Unlike point sampling, this cannot paint
through a thin wall or disclose a sliver of a private room.  This affects only
presentation; movement, interaction, doors and inventories stay in the engine.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor

from worldseed.systems.illumination import (detection_scale, indoor_actor_visible, indoor_light,
    indoor_sources, interior_ambient)
from worldseed.systems.interior_state import UNIT
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

    def hit_test(self, x: float, y: float):
        """Observational stable IDs; commands still revalidate physical reach."""
        if not any(a <= x*UNIT < c and b <= y*UNIT < d
                   for tile in self.tiles for a, b, c, d in (tile.bounds,)):
            return None
        return next((row for row in reversed(self.objects)
                     if row.bounds[0] <= x < row.bounds[2]
                     and row.bounds[1] <= y < row.bounds[3]), None)


def _cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def _hull(points):
    points = sorted(set(points))
    halves = []
    for values in (points, list(reversed(points))):
        half = []
        for point in values:
            while len(half) > 1 and _cross(half[-2], half[-1], point) <= 0:
                half.pop()
            half.append(point)
        halves.append(half[:-1])
    return tuple(halves[0]+halves[1])


def _intersects_wall(polygon, wall):
    """Exact convex polygon / closed integer wall SAT intersection."""
    ax, ay, bx, by = wall
    box = ((ax, ay), (bx-1, ay), (bx-1, by-1), (ax, by-1))
    axes = [(1, 0), (0, 1)]
    axes.extend((b[1]-a[1], a[0]-b[0])
                for a, b in zip(polygon, (*polygon[1:], polygon[0])))
    for dx, dy in axes:
        values = tuple(x*dx+y*dy for x, y in polygon)
        other = tuple(x*dx+y*dy for x, y in box)
        if max(values) < min(other) or max(other) < min(values):
            return False
    return True


def _rect_visible(px, py, bounds, walls):
    a, b, c, d = bounds
    polygon = _hull(((px, py), (a, b), (c-1, b), (c-1, d-1), (a, d-1)))
    if len(polygon) < 3:
        return False
    left, right = min(px, a), max(px, c-1)
    top, bottom = min(py, b), max(py, d-1)
    for wall in walls:
        x, y, x1, y1 = wall
        if x > right or x1-1 < left or y > bottom or y1-1 < top:
            continue
        if _intersects_wall(polygon, wall):
            return False
    return True


def _overlap(a, b):
    return a[0] < b[2] and a[2] > b[0] and a[1] < b[3] and a[3] > b[1]


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
    # Adaptive conservative rectangles cap both work and draw commands. They
    # never approximate wall collision or grant extra sight at a wider zoom.
    step = max(500, ceil(max(1, right-left)/32), ceil(max(1, bottom-top)/24))
    minute = sim.clock.minute
    ambient = interior_ambient(getattr(sim, 'environment', None), minute, plan)
    sources = indoor_sources(plan)
    tiles = []
    for y in range(top, bottom, step):
        for x in range(left, right, step):
            rect = (x, y, min(right, x+step), min(bottom, y+step))
            # Shared gameplay light determines sight reach. A far corner must
            # also be admitted; the exact wall test protects the whole area.
            corners = ((rect[0], rect[1]), (rect[2]-1, rect[1]),
                       (rect[2]-1, rect[3]-1), (rect[0], rect[3]-1))
            visible = True
            for tx, ty in corners:
                light = indoor_light(plan, tx, ty, minute,
                                     ambient_light=ambient, sources=sources)
                radius = max(1000, 12000*detection_scale(light)//65535)
                if (tx-player.x)**2+(ty-player.y)**2 > radius*radius:
                    visible = False
                    break
            if not visible:
                continue
            if not _rect_visible(player.x, player.y, rect, walls):
                continue
            cx, cy = (rect[0]+rect[2])//2, (rect[1]+rect[3])//2
            room = next((r.name for r in plan.rooms if r.rect.contains(cx, cy)), '')
            light = indoor_light(plan, cx, cy, minute, ambient_light=ambient, sources=sources)
            tiles.append(InteriorTile(rect, light, room))
    if len(tiles) > MAX_INTERIOR_TILES:
        raise ValueError('interior viewport tile budget exceeded')

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
        tuple(tiles), tuple(visible_walls), tuple(objects), tuple(actors))


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


def prepare_interior_frame(scene, camera, viewer, materials):
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
    ground, scenery = [], []
    for index, tile in enumerate(scene.tiles):
        room_floor, _ = visuals.interior_materials(scene.function, tile.room_name,
            floor_material=scene.floor_material, wall_material=scene.wall_material)
        source = _texture(materials, 'interior_textures', room_floor)
        if source:
            ground.append(SpriteCommand('interior-floor:'+str(index), *source,
                clips[index], (clips[index],)))
    for index, rect in enumerate(scene.walls):
        source = _texture(materials, 'interior_textures', wall_id)
        if source:
            bounds = screen_rect(rect, UNIT)
            scenery.append(((-1., index), SpriteCommand('interior-wall:'+str(index),
                *source, bounds, (bounds,))))
    for row in scene.objects:
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
        depth = -2. if row.flat else row.bounds[3]
        if row.solid:
            shadow = ('interior-contact', 1, _CONTACT_RGBA, 32, 12)
            scenery.append(((depth-.001, row.uid), SpriteCommand(
                'interior-shadow:'+row.uid, *shadow,
                (x0+width*.05, y1-camera.scale*.12,
                 x1-width*.05, y1+camera.scale*.08), clips)))
        scenery.append(((depth, row.uid), SpriteCommand('interior:'+row.uid,
            *source, bounds, clips)))
    for row in (InteriorActorView('player', 'core:player', viewer), *scene.actors):
        source = materials.player() if row.uid == 'player' else materials.actor(row.content_id)
        if source is not None:
            x, y = camera.to_screen(row.foot)
            width, height = camera.scale*.75, camera.scale*1.5
            scenery.append(((row.foot.y, row.uid), SpriteCommand('interior-actor:'+row.uid,
                *source, (x-width/2, y-height, x+width/2, y), clips)))
    scenery.sort(key=lambda row: row[0])
    commands = [command for _, command in scenery]
    # Light is sampled by the shared wall-occluded engine authority. These
    # constant-source quads add darkness only within already-authorized floor.
    shade = ('interior-shade', 1, bytes((8, 12, 20, 255)), 1, 1)
    for index, tile in enumerate(scene.tiles):
        alpha = (65535-tile.light)*.75/65535
        commands.append(SpriteCommand('interior-light:'+str(index), *shade,
            clips[index], (clips[index],), opacity=alpha))
    if len(ground)+len(commands) > MAX_COMMANDS:
        raise ValueError('interior draw budget exceeded')
    return GPUPreparedFrame(tuple(ground), tuple(commands), 0, len(ground))
