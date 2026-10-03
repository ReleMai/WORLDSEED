"""Versioned access repairs over stable generated settlement identities.

These sparse deltas are prepared on settlement activation, never from render or
inspection. The rebuildable base cache remains byte-for-byte unchanged; doors,
locks, buildings and contents retain their original IDs.
"""
from __future__ import annotations

from dataclasses import asdict

from worldseed.core.canonical import canonical_hash
from worldseed.world.regional_plan import RoadSegmentPlan, stable_plan_uid


ACCESS_REPAIR_REVISION = 1
_FENCES = {"field_fence", "pen_fence", "yard_fence"}
_PROPS = _FENCES | {"yard_fixture", "worksite_fixture", "managed_tree_plot"}


def _fingerprint(skeleton):
    payload=skeleton.to_dict();payload.pop("fingerprint",None)
    return canonical_hash(payload)


def apply_access_delta(skeleton, cache_source):
    """Apply a previously recorded repair without terrain queries or writes."""
    loader=getattr(cache_source,"load_physical_plan_delta",None)
    row=loader(skeleton.plan.uid) if callable(loader) else None
    if not row or row.get("plan_kind")!="settlement_access":return skeleton
    payload=row.get("payload",{})
    if payload.get("base_fingerprint")!=skeleton.fingerprint:return skeleton
    from worldseed.systems.settlement_planner import SettlementSkeleton
    result=SettlementSkeleton.from_dict(skeleton.to_dict())
    structures={s.uid:s for s in result.structures}
    for uid,cells in payload.get("footprints",{}).items():
        if uid in structures:structures[uid].footprint=[tuple(map(int,p)) for p in cells]
    for uid,cell in payload.get("entrances",{}).items():
        if uid in structures:structures[uid].entrance=tuple(map(int,cell))
    removed=set(payload.get("removed_pieces",()))
    result.pieces=[p for p in result.pieces if p.uid not in removed]
    for piece in result.pieces:
        if piece.uid in payload.get("piece_cells",{}):
            piece.x,piece.y=map(int,payload["piece_cells"][piece.uid])
    for structure in result.structures:
        structure.piece_ids=[uid for uid in structure.piece_ids if uid not in removed]
    for road in result.roads:
        if road.uid in payload.get("road_cells",{}):
            road.polyline=[tuple(map(int,cell)) for cell in payload["road_cells"][road.uid]]
    known={r.uid for r in result.roads}
    for raw in payload.get("added_roads",()):
        if raw["uid"] in known:continue
        raw=dict(raw);raw["polyline"]=[tuple(map(int,p)) for p in raw["polyline"]]
        result.roads.append(RoadSegmentPlan(**raw));known.add(raw["uid"])
    for parcel in result.parcels:
        if parcel.uid in payload.get("parcel_access",{}):parcel.access_road_id=payload["parcel_access"][parcel.uid]
    if "gateways" in payload:result.plan.gateway_cells=[tuple(map(int,p)) for p in payload["gateways"]]
    result.plan.road_segment_ids=[r.uid for r in result.roads]
    result.plan.plan_revision=max(result.plan.plan_revision,ACCESS_REPAIR_REVISION)
    cells={tuple(p) for p in result.plan.common_cells}
    cells.update(tuple(p) for parcel in result.parcels for p in parcel.cells)
    cells.update(tuple(p) for road in result.roads for p in road.polyline)
    if cells:result.plan.atlas_bounds=(min(x for x,_ in cells),min(y for _,y in cells),max(x for x,_ in cells),max(y for _,y in cells))
    result.fingerprint=_fingerprint(result)
    return result


def prepare_access_repairs(skeleton, world, registry):
    """Record one bounded v10/v11 repair, preserving the original base plan."""
    cache=world.delta_source
    loader=getattr(cache,"load_physical_plan_delta",None)
    storer=getattr(cache,"store_physical_plan_delta",None)
    if not callable(loader) or not callable(storer) or skeleton.plan.version not in {10,11}:return skeleton
    existing=loader(skeleton.plan.uid)
    if existing and existing.get("plan_kind")=="settlement_access":return apply_access_delta(skeleton,cache)
    # Do not overwrite an unrelated authoritative mutation sharing this ID.
    if existing:return skeleton
    from worldseed.systems.settlement_planner import SettlementSkeletonPlanner
    planner=SettlementSkeletonPlanner(world,version=12)
    closed={tuple(p) for s in skeleton.structures if s.enclosed for p in s.footprint}
    roads={tuple(p) for r in skeleton.roads for p in r.polyline}
    pieces_by={}
    for piece in skeleton.pieces:pieces_by.setdefault(piece.structure_plan_id,[]).append(piece)
    payload={"base_fingerprint":skeleton.fingerprint,"entrances":{},"piece_cells":{},
             "removed_pieces":[],"added_roads":[],"road_cells":{},"parcel_access":{},"footprints":{}}
    removed=set()
    # Only generated obstacles may be cleared; player structures and inventory
    # are not part of this base skeleton and cannot be deleted by a repair.
    hard={tuple((p.x,p.y)) for p in skeleton.pieces
          if p.role not in _PROPS and not registry.settlement_pieces[p.piece_id].passable}
    fixtures={(p.x,p.y) for p in skeleton.pieces if p.role in {"yard_fixture","worksite_fixture","managed_tree_plot"}
              and not registry.settlement_pieces[p.piece_id].passable}
    for structure in sorted(skeleton.structures,key=lambda s:s.uid):
        if structure.destroyed or structure.entrance is None:continue
        owned=pieces_by.get(structure.uid,())
        door=next((p for p in owned if p.role=="entrance"),None)
        cells=set(map(tuple,structure.footprint))
        boundary={p for p in cells if any((p[0]+dx,p[1]+dy) not in cells for dx,dy in ((0,1),(1,0),(0,-1),(-1,0)))}
        interior=cells-boundary
        if structure.enclosed and door is not None:
            blocked=(closed-cells)|cells|(hard-cells)
            options=[]
            cx=(min(x for x,_ in cells)+max(x for x,_ in cells))//2
            for x,y in sorted(boundary,key=lambda p:(p[1],p[0])):
                outside=(x,y+1)
                # Separate-level interiors no longer require a walkable tile
                # behind an exterior portal. A chamfered facade edge is usable
                # when a neighboring old lot leaves no central apron.
                if outside in cells or (x,y-1) not in cells or outside in blocked or not planner._legal(*outside):continue
                path=planner._service_path(outside,roads,blocked,limit=32)
                if any(p in roads for p in path):options.append((len(path),abs(x-cx),y,x,(x,y),path))
            stripped=set()
            if not options:
                # Old lots may touch along the entire south facade. Inset only
                # that exterior wall by one cell, inside the original parcel,
                # retaining at least a 4x4 shell and the independent interior.
                bottom=max(y for _,y in cells)
                candidate={p for p in cells if p[1]<bottom}
                if max(y for _,y in candidate)-min(y for _,y in candidate)+1 < 4:continue
                if any(p.role in {"fixture","interior_door","partition"} and (p.x,p.y) in cells-candidate for p in owned):continue
                changed_boundary={p for p in candidate if any((p[0]+dx,p[1]+dy) not in candidate for dx,dy in ((0,1),(1,0),(0,-1),(-1,0)))}
                changed_blocked=(closed-cells)|candidate|(hard-cells)
                for x,y in sorted(changed_boundary,key=lambda p:(p[1],p[0])):
                    outside=(x,y+1)
                    if outside in candidate or (x,y-1) not in candidate or outside in changed_blocked or not planner._legal(*outside):continue
                    path=planner._service_path(outside,roads,changed_blocked,limit=32)
                    if any(p in roads for p in path):options.append((len(path),abs(x-cx),y,x,(x,y),path))
                if not options:continue
                stripped=cells-candidate
                payload["footprints"][structure.uid]=sorted(candidate,key=lambda p:(p[1],p[0]))
                closed.difference_update(cells);closed.update(candidate)
                hard.difference_update(stripped)
            *_,gate,path=min(options,key=lambda r:r[:4])
            if gate!=tuple(structure.entrance):
                wall=next((p for p in owned if p.role=="wall" and (p.x,p.y)==gate),None)
                if wall is None and stripped and tuple(structure.entrance) not in stripped:
                    wall=next((p for p in owned if p.role=="wall" and (p.x,p.y) in stripped),None)
                if wall is None and not stripped:continue
                if wall is not None:payload["piece_cells"][wall.uid]=list(structure.entrance)
                payload["piece_cells"][door.uid]=list(gate)
                threshold=next((p for p in owned if p.role=="threshold" and (p.x,p.y)==tuple(structure.entrance)),None)
                if threshold:payload["piece_cells"][threshold.uid]=list(gate)
                payload["entrances"][structure.uid]=list(gate)
            removed.update(p.uid for p in owned if (p.x,p.y) in stripped and p.uid not in payload["piece_cells"]
                           and p.role in {"wall","floor","roof","threshold"})
        elif structure.function=="animal_pen":
            door=next((p for p in owned if p.role=="pen_gate"),None)
            if door is None:continue
            options=[]
            for x,y in sorted(boundary,key=lambda p:(p[1],p[0])):
                for dx,dy in ((0,1),(1,0),(0,-1),(-1,0)):
                    outside=(x+dx,y+dy);inside=(x-dx,y-dy)
                    if outside in cells or inside not in interior or inside in fixtures or outside in closed or not planner._legal(*outside):continue
                    blocked=(closed|hard|cells)-{(x,y)}
                    path=planner._service_path((x,y),roads-{tuple(structure.entrance)},blocked,limit=48)
                    if any(p in roads for p in path):options.append((len(path),y,x,(x,y),path))
            if not options:continue
            *_,gate,path=min(options,key=lambda r:r[:3])
            if gate!=tuple(structure.entrance):
                fence=next((p for p in owned if p.role=="pen_fence" and (p.x,p.y)==gate),None)
                if fence is None:continue
                payload["piece_cells"][fence.uid]=list(structure.entrance)
                payload["piece_cells"][door.uid]=list(gate)
                payload["entrances"][structure.uid]=list(gate)
                # The former corner is now a real fence again. Remove only its
                # terminal spur cell, not the connected road behind it.
                old_gate=tuple(structure.entrance)
                for road in skeleton.roads:
                    if road.route_id or road.crossing_ids:continue
                    path_cells=list(road.polyline)
                    if len(path_cells)>1 and tuple(path_cells[0])==old_gate:path_cells=path_cells[1:]
                    if len(path_cells)>1 and tuple(path_cells[-1])==old_gate:path_cells=path_cells[:-1]
                    if path_cells!=road.polyline:payload["road_cells"][road.uid]=path_cells
                roads.discard(old_gate)
        else:continue
        # Clear only blockers on this new, real service path; retain doors and
        # their lock identity rather than silently unlocking an obstacle.
        path_set=set(path)
        removed.update(p.uid for p in skeleton.pieces if p.role in _PROPS and p.uid not in payload["piece_cells"] and (p.x,p.y) in path_set
                       and not registry.settlement_pieces[p.piece_id].passable)
        if len(path)>1:
            uid=stable_plan_uid("road",skeleton.plan.uid,f"access-repair:{structure.uid}",path)
            payload["added_roads"].append(asdict(RoadSegmentPlan(uid=uid,settlement_plan_id=skeleton.plan.uid,
                road_class="service_path",polyline=path,width=1,surface="packed_earth")))
            roads.update(path)
            for parcel in skeleton.parcels:
                if structure.uid in parcel.structure_ids:payload["parcel_access"][parcel.uid]=uid
    payload["removed_pieces"]=sorted(removed)
    # Cut only unused suffixes of unbound gateway roads. Real selected strategic
    # routes, frontage, production access and road intersections remain intact.
    nearby={tuple(p) for parcel in skeleton.parcels for p in parcel.cells}
    nearby|={(x+dx,y+dy) for x,y in tuple(nearby) for dx,dy in ((0,1),(1,0),(0,-1),(-1,0))}
    gateways=set(map(tuple,skeleton.plan.gateway_cells))
    for road in skeleton.roads:
        if road.route_id or road.crossing_ids or not road.polyline or tuple(road.polyline[-1]) not in gateways:continue
        others={tuple(p) for r in skeleton.roads if r.uid!=road.uid for p in r.polyline}
        others.update(tuple(p) for r in payload["added_roads"] for p in r["polyline"])
        keep=max((i for i,p in enumerate(road.polyline) if tuple(p) in nearby|others),default=1)
        if keep<len(road.polyline)-2:
            path=road.polyline[:keep+1];payload["road_cells"][road.uid]=path
            gateways.discard(tuple(road.polyline[-1]));gateways.add(tuple(path[-1]))
    payload["gateways"]=sorted(gateways,key=lambda p:(p[1],p[0]))
    storer(skeleton.plan.uid,"settlement_access",ACCESS_REPAIR_REVISION,payload)
    commit=getattr(cache,"commit_generated",None)
    if callable(commit):commit()
    return apply_access_delta(skeleton,cache)
