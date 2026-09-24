from __future__ import annotations

from collections import defaultdict

from worldseed.core.rng import hash_u64
from worldseed.systems.settlement_planner import analyze_building
from worldseed.world.regional_plan import BuildingPiecePlan, StructurePlanState, stable_plan_uid


def _pick(registry, seed: bytes, category: str, *, tags=(), materials=(), key=()):
    required=set(tags);materials=set(materials)
    rows=[p for p in registry.settlement_pieces.values()
          if p.category==category and required.issubset(set(p.tags))
          and (not materials or p.material in materials)]
    if not rows:
        rows=[p for p in registry.settlement_pieces.values()
              if p.category==category and required.issubset(set(p.tags))]
    if not rows:raise ValueError(f"No settlement piece for {category} {sorted(required)}")
    rows=sorted(rows,key=lambda p:p.id)
    return rows[hash_u64(seed,"settlement-building-piece",category,*key)%len(rows)]


def _road_cells(skeleton, road_id: str):
    for road in skeleton.roads:
        if road.uid==road_id:return {tuple(p) for p in road.polyline}
    return {tuple(p) for road in skeleton.roads for p in road.polyline}


def _best_rect(parcel, roads, sizes):
    cells={tuple(p) for p in parcel.cells}
    if not cells:return None
    xs=[x for x,_ in cells];ys=[y for _,y in cells]
    cx=sum(xs)//len(xs);cy=sum(ys)//len(ys);roads=roads or cells
    for width,height in sizes:
        rows=[]
        for top in range(min(ys),max(ys)-height+2):
            for left in range(min(xs),max(xs)-width+2):
                rect={(x,y) for y in range(top,top+height) for x in range(left,left+width)}
                if not rect.issubset(cells):continue
                perimeter={p for p in rect if p[0] in (left,left+width-1) or p[1] in (top,top+height-1)}
                road_dist=min(abs(x-rx)+abs(y-ry) for x,y in perimeter for rx,ry in roads)
                rows.append((road_dist,abs(left+width//2-cx)+abs(top+height//2-cy),top,left,rect))
        if rows:
            row=min(rows,key=lambda r:r[:4]);return row[4],(row[3],row[2],width,height)
    return None


def _entrance(bounds, roads):
    left,top,width,height=bounds
    perimeter=[(x,y) for y in range(top,top+height) for x in range(left,left+width)
               if x in (left,left+width-1) or y in (top,top+height-1)]
    roads=roads or {(left+width//2,top-1)}
    return min(perimeter,key=lambda p:(min(abs(p[0]-x)+abs(p[1]-y) for x,y in roads),p[1],p[0]))


def _orientation(pos,bounds):
    left,top,width,height=bounds;x,y=pos
    if y==top:return 0
    if x==left+width-1:return 1
    if y==top+height-1:return 2
    return 3


def _partition(bounds):
    left,top,width,height=bounds
    if width<7 or height<7:return set(),set()
    if width>=height:
        x=left+width//2;door=(x,top+height//2)
        walls={(x,y) for y in range(top+1,top+height-1) if (x,y)!=door}
    else:
        y=top+height//2;door=(left+width//2,y)
        walls={(x,y) for x in range(left+1,left+width-1) if (x,y)!=door}
    return walls,{door}


def _materials(plan,function):
    if plan.archetype=="mining" or plan.rank in {"town","city"}:
        walls=("stone","timber","plank");floors=("stone","plank","packed_earth");roofs=("slate","stone","clay","wood")
    elif plan.archetype=="forest":
        walls=("timber","plank","wattle");floors=("plank","packed_earth");roofs=("wood","timber","thatch")
    else:
        walls=("wattle","timber","plank","stone");floors=("packed_earth","plank","clay");roofs=("thatch","reed","wood","clay")
    if function=="barn":roofs=("timber","thatch","reed","wood")
    return walls,floors,roofs


def _function(parcel):
    if parcel.kind=="residential":return "residence"
    if parcel.kind=="farm":return "barn"
    return {"mine_approach":"mine_workshop","logging_yard":"logging_workshop",
            "fishery":"fishery","trade_workyard":"trade_workshop",
            "mill_workyard":"mill_workshop","general_workyard":"workshop"}.get(parcel.purpose,"workshop")


def _fixture_specs(function):
    return {
      "residence":[("furniture",("bed",),"sleep"),("furniture",("hearth",),"cooking"),
                   ("furniture",("storage",),"storage"),("furniture",("table",),"dining")],
      "mine_workshop":[("mine",("station","mine"),"mine"),("workshop",("masonry",),"masonry"),
                       ("mine",("storage","mine"),"storage")],
      "logging_workshop":[("workshop",("carpentry",),"carpentry"),("workshop",("station",),"workshop"),
                          ("furniture",("storage",),"storage")],
      "mill_workshop":[("workshop",("milling",),"milling"),("furniture",("storage",),"storage"),
                       ("furniture",("table",),"workshop")],
      "fishery":[("workshop",("butchery",),"workshop"),("furniture",("storage",),"storage"),
                 ("agriculture",("drying",),"storage")],
      "trade_workshop":[("civic",("market",),"market"),("furniture",("storage",),"storage"),
                        ("furniture",("table",),"shop")],
      "barn":[("agriculture",("stable","livestock"),"stable"),("agriculture",("livestock","storage"),"stable"),
              ("agriculture",("storage","granary"),"storage")],
    }.get(function,[("workshop",("station",),"workshop"),("furniture",("storage",),"storage"),
                    ("furniture",("table",),"workshop")])


def _add_piece(out,structure_uid,piece,pos,room_id="",orientation=0):
    x,y=pos;uid=stable_plan_uid("piece",structure_uid,f"{piece.id}:{piece.layer}:{x}:{y}",[(x,y)])
    row=BuildingPiecePlan(uid,structure_uid,piece.id,x,y,piece.layer,orientation,room_id);out.append(row);return row


def _build_one(skeleton,registry,seed,parcel,slot):
    function=_function(parcel)
    sizes=((7,7),(5,5),(4,4)) if function=="residence" else (((7,5),(5,5),(4,4)) if function=="barn" else ((7,7),(6,6),(5,5)))
    roads=_road_cells(skeleton,parcel.access_road_id);chosen=_best_rect(parcel,roads,sizes)
    if chosen is None:return None,[],[]
    rect,bounds=chosen;entrance=_entrance(bounds,roads);left,top,width,height=bounds
    perimeter={p for p in rect if p[0] in (left,left+width-1) or p[1] in (top,top+height-1)}
    partition_walls,internal_doors=_partition(bounds)
    walls=(perimeter-{entrance})|partition_walls;doors={entrance}|internal_doors;interior=rect-perimeter
    suid=stable_plan_uid("structure",skeleton.plan.uid,f"{function}:{slot}",sorted(rect,key=lambda p:(p[1],p[0])))
    wp,fp,rp=_materials(skeleton.plan,function)
    wall_piece=_pick(registry,seed,"wall",materials=wp,key=(suid,"wall"))
    floor_piece=_pick(registry,seed,"floor",materials=fp,key=(suid,"floor"))
    roof_piece=_pick(registry,seed,"roof",materials=rp,key=(suid,"roof"))
    door_piece=_pick(registry,seed,"opening",tags=("door",),key=(suid,"door"))
    placements=[]
    for p in sorted(walls,key=lambda p:(p[1],p[0])):_add_piece(placements,suid,wall_piece,p,orientation=_orientation(p,bounds) if p in perimeter else 0)
    for p in sorted(doors,key=lambda p:(p[1],p[0])):_add_piece(placements,suid,door_piece,p,orientation=_orientation(p,bounds) if p in perimeter else 0)
    for p in sorted(interior,key=lambda p:(p[1],p[0])):
        _add_piece(placements,suid,floor_piece,p);_add_piece(placements,suid,roof_piece,p)

    available=sorted(interior-partition_walls-internal_doors,key=lambda p:(p[1],p[0]))
    targets=[]
    for i in (0,len(available)-1,len(available)//2,max(0,len(available)//3)):
        if available and available[i] not in targets:targets.append(available[i])
    fixture_tags={};workplace_role=""
    for i,(category,tags,semantic) in enumerate(_fixture_specs(function)):
        if i>=len(targets):break
        try:piece=_pick(registry,seed,category,tags=tags,key=(suid,"fixture",i))
        except ValueError:continue
        p=targets[i];_add_piece(placements,suid,piece,p)
        fixture_tags.setdefault(p,set()).update(piece.room_tags or piece.tags);fixture_tags[p].add(semantic)
        if piece.workplace_role and not workplace_role:workplace_role=piece.workplace_role

    analysis=analyze_building(suid,wall_cells=walls,door_cells=doors,roof_cells=interior,floor_cells=interior,fixture_tags=fixture_tags)
    room_by_cell={}
    for room in analysis.rooms:
        for p in room.cells:room_by_cell[p]=room
    for placement in placements:
        room=room_by_cell.get((placement.x,placement.y))
        if room:
            placement.room_id=room.uid;piece=registry.settlement_pieces.get(placement.piece_id)
            if piece and piece.category in {"furniture","workshop","agriculture","mine","civic"}:room.fixture_ids.append(placement.uid)
    for room in analysis.rooms:room.fixture_ids=sorted(set(room.fixture_ids))
    content_id="core:generated_"+function
    structure=StructurePlanState(
        uid=suid,settlement_plan_id=skeleton.plan.uid,content_id=content_id,function=function,
        footprint=sorted(rect,key=lambda p:(p[1],p[0])),entrance=entrance,orientation=_orientation(entrance,bounds),
        workplace_role=workplace_role,parcel_id=parcel.uid,piece_ids=[p.uid for p in placements],
        building_type=analysis.building_type,enclosed=analysis.enclosed,interior_area=analysis.interior_area,
        room_ids=[r.uid for r in analysis.rooms])
    return structure,list(analysis.rooms),placements


def populate_settlement_buildings(skeleton,registry,seed: bytes):
    structures=[];rooms=[];pieces=[];farm_done=False;slot=0
    for parcel in sorted(skeleton.parcels,key=lambda p:p.uid):
        if parcel.kind not in {"residential","industrial","farm"}:continue
        if parcel.kind=="farm":
            if farm_done:continue
            farm_done=True
        structure,new_rooms,new_pieces=_build_one(skeleton,registry,seed,parcel,slot);slot+=1
        if structure is None:continue
        structures.append(structure);rooms.extend(new_rooms);pieces.extend(new_pieces);parcel.structure_ids.append(structure.uid)
    skeleton.structures=structures;skeleton.rooms=rooms;skeleton.pieces=pieces
    plan=skeleton.plan;plan.structure_site_ids=[s.uid for s in structures];plan.room_ids=[r.uid for r in rooms];plan.piece_ids=[p.uid for p in pieces]
    room_map={r.uid:r for r in rooms}
    plan.housing_capacity=sum(max(2,2+2*sum(1 for rid in s.room_ids if room_map.get(rid) and room_map[rid].kind=="bedroom"))
                              for s in structures if s.function=="residence")
    capacity=defaultdict(int)
    for s in structures:
        if s.workplace_role:capacity[s.workplace_role]+=2
        elif s.function=="barn":capacity["farmer"]+=2
    plan.workplace_capacity=dict(sorted(capacity.items()))
    return skeleton
