"""Project authoritative storage identities into prepared indoor furniture.

Called on explicit preparation/entry, never hover or rendering. Existing saved
furniture positions are preserved; only missing storage projections are added.
"""
from worldseed.systems.container_profiles import container_profile
from worldseed.systems.interior_state import ACTOR_RADIUS, InteriorFurniture, InteriorRect
from worldseed.systems.interior_furnishing import (
    furniture_base_piece, furniture_variant, fixture_slot_candidates, slot_placement_clear,
)


def bind_storage(plan, containers, actors=()):
    from worldseed.systems.interiors import exit_reachable, position_clear
    rows=sorted((c for c in containers if c.interior_space_id==plan.uid),key=lambda c:c.uid)
    occupants=tuple(actor for actor in actors if actor.space_id==plan.uid)
    occupied=[InteriorRect(actor.x-ACTOR_RADIUS,actor.y-ACTOR_RADIUS,
                           ACTOR_RADIUS*2,ACTOR_RADIUS*2) for actor in occupants]
    bound={c.interior_furniture_uid for c in rows
           if any(f.uid==c.interior_furniture_uid for f in plan.furniture)}
    for container in rows:
        style=container_profile(container.profile_id)
        if style is None:continue
        fixture=next((f for f in plan.furniture if f.uid==container.interior_furniture_uid),None)
        if fixture is None:
            # Bind a real chest/cabinet already in the building before adding
            # another silhouette. Neither path creates another item inventory.
            fixture=next((f for f in plan.furniture if furniture_base_piece(f.piece_id)==style.piece_id and f.uid not in bound),None)
        if fixture is None:
            rooms={room.uid:room for room in plan.rooms}
            preferred=next((room.uid for room in sorted(plan.rooms,key=lambda r:r.uid)
                            if any(word in room.name.lower() for word in style.rooms)),"")
            for room_uid,slot,x,y in fixture_slot_candidates(plan,style.piece_id,preferred,
                                                            width=style.width,depth=style.height):
                room=rooms[room_uid]
                rect=room.rect
                if (x<rect.x+400 or y<rect.y+400 or x+style.width>rect.x+rect.w-400
                        or y+style.height>rect.y+rect.h-400):continue
                piece_id=furniture_variant(style.piece_id,container.uid) if plan.version>=4 else style.piece_id
                candidate=InteriorFurniture("storage-furniture:"+container.uid,piece_id,x,y,
                                            style.width,style.height,container.owner,container.uid)
                if not slot_placement_clear(plan,candidate,occupants):continue
                # Saved furniture and actors remain untouched. Missing storage
                # binds only to explicit wall slots with a connected approach.
                if any(candidate.rect.overlaps(rect) for rect in occupied):continue
                plan.furniture.append(candidate)
                probes=[(r.rect.x+r.rect.w//2,r.rect.y+r.rect.h-400) for r in plan.rooms]
                probes += [(actor.x,actor.y) for actor in occupants]
                safe=all(position_clear(plan,*p) and exit_reachable(plan,*p) for p in probes)
                if safe:fixture=candidate;break
                plan.furniture.pop()
        if fixture is not None:
            container.interior_furniture_uid=fixture.uid
            bound.add(fixture.uid)
        else:
            # Occupied or fully furnished legacy rooms can temporarily have
            # no safe slot. Keep the real inventory indoors, but explicitly
            # pending/unreachable until a later preparation finds a vacancy.
            container.interior_furniture_uid=""
    return {c.interior_furniture_uid:c for c in rows
            if any(f.uid==c.interior_furniture_uid for f in plan.furniture)}
