"""Authoritative, bounded 500-unit indoor exploration visibility.

Never mutates a plan, consults exterior terrain, or discovers private rooms.
The same conservative convex wall-fan test used for GPU sight gates saved
indoor floor memory. A single integer cell index identifies one fixed 0.5m
square of a *specific* persisted InteriorPlan (and thus a specific floor).
"""
from __future__ import annotations

from math import ceil
from functools import lru_cache

from worldseed.systems.illumination import detection_scale, indoor_light, segment_clear

GRID = 500
MAX_MEMORY_CELLS = 4096
MAX_SIGHT_RADIUS = 12000
DETAIL_GRID = GRID//4
MAX_SIGHT_RECTS = 1024
# Interior geometry is still wall-occluded. Do not reuse NPC detection scale
# for the player's near-black navigation: that kept even firelit rooms at ~3m.
MIN_PLAYER_SIGHT_RADIUS = 5500


def player_sight_radius(light):
    return max(MIN_PLAYER_SIGHT_RADIUS,
        MAX_SIGHT_RADIUS*detection_scale(light)//65535)


def _cross(a, b, c):
    return (b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])


def _scalar_xy(points):
    # Corrupted/legacy geometry can contain nested tuple coordinates.
    # A malformed observation must not crash an active Windows game.
    return all(isinstance(point, tuple) and len(point)==2 and
               all(type(value) in (int,float) for value in point)
               for point in points)


def _hull(points):
    if not _scalar_xy(points):
        return ()  # fail closed; never reveal hidden floor using bad geometry
    return _trusted_hull(points)


def _trusted_hull(points):
    """Internal hull after request validation, without repeating type scans."""
    points = sorted(set(points))
    halves = []
    for values in (points, list(reversed(points))):
        half = []
        for point in values:
            while len(half) > 1 and _cross(half[-2], half[-1], point) <= 0:
                half.pop()
            half.append(point)
        halves.append(half[:-1])
    return tuple(halves[0] + halves[1])


def _intersects_wall(polygon, wall):
    ax, ay, bx, by = wall
    bx -= 1
    by -= 1
    axes = [(1, 0), (0, 1)]
    axes.extend((b[1]-a[1], a[0]-b[0])
                for a, b in zip(polygon, (*polygon[1:], polygon[0])))
    for dx, dy in axes:
        # An axis-aligned wall's extrema are its signed support corners.
        # Avoid allocating/projecting four wall vertices for every SAT axis.
        low = (ax if dx >= 0 else bx)*dx + (ay if dy >= 0 else by)*dy
        high = (bx if dx >= 0 else ax)*dx + (by if dy >= 0 else ay)*dy
        first = polygon[0][0]*dx + polygon[0][1]*dy
        pmin = pmax = first
        for x,y in polygon[1:]:
            value=x*dx+y*dy
            if value < pmin:pmin=value
            if value > pmax:pmax=value
        if pmax < low or high < pmin:
            return False
    return True


def _rect_visible(px, py, bounds, walls):
    """An entire floor rectangle must have an unobstructed wall fan."""
    if not isinstance(bounds, tuple) or len(bounds)!=4:
        return False
    a, b, c, d = bounds
    if not _scalar_xy(((px,py),(a,b),(c,d))):
        return False
    return _trusted_rect_visible(px,py,bounds,walls)


def _trusted_rect_visible(px,py,bounds,walls):
    a,b,c,d=bounds
    polygon = _trusted_hull(((px, py), (a, b), (c-1, b), (c-1, d-1), (a, d-1)))
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


def grid_columns(plan):
    return (plan.width + GRID - 1)//GRID


def grid_rect(plan, index):
    """Saved cell indices are plan-local; invalid or oversized values stay hidden."""
    cols = grid_columns(plan)
    if cols <= 0 or type(index) is not int or index < 0:
        return None
    x, y = (index % cols)*GRID, (index // cols)*GRID
    if x >= plan.width or y >= plan.height:
        return None
    return (x, y, min(plan.width, x+GRID), min(plan.height, y+GRID))


def visible_grid_cells(plan, px, py, minute, ambient_light, sources=()):
    """Compute only the bounded viewer neighborhood, not all saved floors.

    These deterministic whole-rectangle checks are at least as conservative as
    the renderer's wall/light admission. No actor, fixture or room name is saved.
    """
    cols = grid_columns(plan)
    rows = (plan.height + GRID - 1)//GRID
    if not 0 < cols*rows <= MAX_MEMORY_CELLS or len(plan.walls) > 256:
        return ()
    walls = tuple((w.x, w.y, w.x+w.w, w.y+w.h) for w in plan.walls)
    r = MAX_SIGHT_RADIUS
    discovered = []
    for cy in range(max(0,(py-r)//GRID), min(rows,(py+r)//GRID+2)):
        for cx in range(max(0,(px-r)//GRID), min(cols,(px+r)//GRID+2)):
            rect = grid_rect(plan, cy*cols+cx)
            if rect is None:
                continue
            a,b,c,d=rect
            corners=((a,b),(c-1,b),(c-1,d-1),(a,d-1))
            # Reject on maximum sight radius before evaluating expensive lighting.
            if any((x-px)**2+(y-py)**2 > r*r for x,y in corners):
                continue
            if not _rect_visible(px,py,rect,walls):
                continue
            authorized=True
            for x,y in corners:
                light=indoor_light(plan,x,y,minute,ambient_light=ambient_light,sources=sources)
                radius=player_sight_radius(light)
                if (x-px)**2+(y-py)**2>radius*radius:
                    authorized=False
                    break
            if authorized:
                discovered.append(cy*cols+cx)
    return tuple(discovered)


def visible_floor_rects(plan, px, py, minute, ambient_light, sources=(), *, viewport=None):
    """World-aligned LOS patches, refined only along walls and sight edges.

    A patch is admitted only when its complete convex fan clears every wall.
    Refining rejected boundary patches removes large stair steps without
    sampling away thin partitions or granting sight through a private room.
    The returned geometry is pure and shared by observation and presentation.
    """
    if not _scalar_xy(((px,py),)):
        return ()  # no malformed interior sight request may reach the hull
    cols = grid_columns(plan)
    rows = (plan.height+GRID-1)//GRID
    if not 0 < cols*rows <= MAX_MEMORY_CELLS or len(plan.walls) > 256:
        return ()
    walls = tuple((w.x,w.y,w.x+w.w,w.y+w.h) for w in plan.walls)
    # Two recent exact requests cover simulation observation and rendering.
    # Geometry and lights are value keys: edits invalidate immediately, and
    # no plan/state object survives in this bounded ephemeral cache.
    return _visible_floor_rects(plan.width,plan.height,walls,px,py,
        ambient_light,tuple(sources)[:64],viewport)


@lru_cache(maxsize=2)
def _visible_floor_rects(width,height,walls,px,py,ambient_light,sources,viewport):
    from types import SimpleNamespace
    from worldseed.systems.illumination import lighting_catalog, source_strength
    plan=SimpleNamespace(width=width,height=height,
        walls=tuple(SimpleNamespace(x=a,y=b,w=c-a,h=d-b) for a,b,c,d in walls))
    cols=(width+GRID-1)//GRID
    rows=(height+GRID-1)//GRID
    ambient=max(0,min(65535,int(ambient_light)))*lighting_catalog()['indoor_ambient_percent']//100
    ambient_radius=player_sight_radius(ambient)
    minute=0  # supplied ambient is authoritative; indoor_light does not read time
    left,top,right,bottom = viewport or (0,0,plan.width,plan.height)
    left,top = max(0,left,px-MAX_SIGHT_RADIUS), max(0,top,py-MAX_SIGHT_RADIUS)
    right,bottom = min(plan.width,right,px+MAX_SIGHT_RADIUS+1), min(plan.height,bottom,py+MAX_SIGHT_RADIUS+1)
    lights = {}
    clear_points = {}
    def clear_point(x,y):
        key=(x,y)
        if key not in clear_points:
            clear_points[key]=segment_clear(plan,px,py,x,y)
        return clear_points[key]
    def in_reach(x,y):
        distance = (x-px)**2+(y-py)**2
        if distance > MAX_SIGHT_RADIUS**2:
            return False
        # Point lights can only increase reach. Near-floor navigation already
        # fits inside the ambient radius, regardless of lamp occlusion.
        if distance <= ambient_radius*ambient_radius:
            return True
        key=(x,y)
        if key not in lights:
            # Most floor corners lie beyond every lamp's finite influence.
            # Their ambient radius is constant; no light/LOS query is needed.
            if not any(source_strength(s,x,y) for s in sources):
                lights[key]=ambient_radius
            else:
                light=indoor_light(plan,x,y,minute,ambient_light=ambient_light,sources=sources)
                lights[key]=player_sight_radius(light)
        return distance <= lights[key]**2
    admitted=[]
    def visit(rect):
        a,b,c,d=rect
        if c <= left or a >= right or d <= top or b >= bottom:
            return
        corners=((a,b),(c-1,b),(c-1,d-1),(a,d-1))
        if all(in_reach(x,y) for x,y in corners) and _trusted_rect_visible(px,py,rect,walls):
            admitted.append(rect)
            return
        if max(c-a,d-b) <= DETAIL_GRID:
            return
        # Hidden rooms normally fail here, avoiding a recursive scan of their
        # entire floor. This rejection is conservative: missing a narrow
        # sliver can hide pixels, but cannot reveal an unobserved one.
        probes=(*corners,((a+c)//2,(b+d)//2))
        if not any(in_reach(x,y) and clear_point(x,y) for x,y in probes):
            return
        mid_x,min_y = min(c,a+(c-a+1)//2), min(d,b+(d-b+1)//2)
        for x0,x1 in ((a,mid_x),(mid_x,c)):
            for y0,y1 in ((b,min_y),(min_y,d)):
                if x0 < x1 and y0 < y1:
                    visit((x0,y0,x1,y1))
    for cy in range(max(0,top//GRID), min(rows,(bottom+GRID-1)//GRID)):
        for cx in range(max(0,left//GRID), min(cols,(right+GRID-1)//GRID)):
            visit(grid_rect(plan,cy*cols+cx))
    if len(admitted) > MAX_SIGHT_RECTS:
        admitted.sort(key=lambda r: (((r[0]+r[2])//2-px)**2+((r[1]+r[3])//2-py)**2,r))
        admitted=admitted[:MAX_SIGHT_RECTS]
    return tuple(sorted(admitted,key=lambda r:(r[1],r[0],r[3],r[2])))


def remember_floor_rects(plan, rects):
    """Compact observed geometry at a simulation boundary; never from a view."""
    cols=grid_columns(plan)
    known=set(plan.explored_cells)
    detail=dict(plan.explored_detail)
    for a,b,c,d in rects:
        index=(b//GRID)*cols+a//GRID
        if index in known:
            continue
        base=grid_rect(plan,index)
        if base is None:
            continue
        if (a,b,c,d) == base:
            known.add(index)
            detail.pop(str(index),None)
            continue
        mask=detail.get(str(index),0)
        for sy in range(4):
            for sx in range(4):
                x,y=base[0]+sx*DETAIL_GRID,base[1]+sy*DETAIL_GRID
                x1,y1=min(base[2],x+DETAIL_GRID),min(base[3],y+DETAIL_GRID)
                # Odd modded plan dimensions can create smaller edge cells.
                # Remember only complete subcells, never round discovery out.
                if a <= x < x1 <= c and b <= y < y1 <= d:
                    mask |= 1 << (sy*4+sx)
        if mask == 65535:
            known.add(index)
            detail.pop(str(index),None)
        elif mask and 0 <= index < MAX_MEMORY_CELLS:
            detail[str(index)]=mask
    plan.explored_cells=sorted(known)[:MAX_MEMORY_CELLS]
    plan.explored_detail=detail


def remembered_floor_rects(plan):
    """Read only saved geometry, without consulting live walls or furniture."""
    known=set(getattr(plan,'explored_cells',()))
    for index in sorted(known):
        rect=grid_rect(plan,index)
        if rect:
            yield rect
    for index,mask in sorted(getattr(plan,'explored_detail',{}).items(),key=lambda row:int(row[0])):
        if int(index) in known:
            continue
        rect=grid_rect(plan,int(index))
        if rect is None:
            continue
        a,b,c,d=rect
        for sy in range(4):
            for sx in range(4):
                if mask & (1 << (sy*4+sx)):
                    sub=(a+sx*DETAIL_GRID,b+sy*DETAIL_GRID,min(c,a+(sx+1)*DETAIL_GRID),min(d,b+(sy+1)*DETAIL_GRID))
                    if sub[0] < sub[2] and sub[1] < sub[3]:
                        yield sub
