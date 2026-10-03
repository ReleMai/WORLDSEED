"""Project authoritative storage identities into prepared indoor furniture.

Called on explicit preparation/entry, never hover or rendering. Existing saved
furniture positions are preserved; only missing storage projections are added.
"""
from worldseed.systems.container_profiles import container_profile
from worldseed.systems.interior_state import ACTOR_RADIUS, InteriorFurniture, InteriorRect


def bind_storage(plan, containers, actors=()):
    from worldseed.systems.interiors import placement_clear, exit_reachable, position_clear
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
            fixture=next((f for f in plan.furniture if f.piece_id==style.piece_id and f.uid not in bound),None)
        if fixture is None:
            rooms=sorted(plan.rooms,key=lambda r:(not any(word in r.name.lower() for word in style.rooms),r.uid))
            for room in rooms:
                rect=room.rect
                for row in range(6):
                    for col in range(6):
                        x,y=rect.x+425+col*(style.width+450),rect.y+425+row*(style.height+450)
                        if x+style.width>rect.x+rect.w-400 or y+style.height>rect.y+rect.h-900:continue
                        candidate=InteriorFurniture("storage-furniture:"+container.uid,style.piece_id,x,y,
                                                    style.width,style.height,container.owner,container.uid)
                        if not placement_clear(plan,candidate.rect):continue
                        # Legacy interiors may already contain the player or
                        # resting NPCs. Adding a cupboard must not bury them or
                        # demand a compensating teleport on the next tick.
                        if any(candidate.rect.overlaps(rect) for rect in occupied):continue
                        # Keep circulation/escape paths valid, not just overlap.
                        plan.furniture.append(candidate)
                        probes=[(r.rect.x+r.rect.w//2,r.rect.y+r.rect.h-400) for r in plan.rooms]
                        probes += [(actor.x,actor.y) for actor in occupants]
                        safe=all(position_clear(plan,*p) and exit_reachable(plan,*p) for p in probes)
                        if safe:fixture=candidate;break
                        plan.furniture.pop()
                    if fixture is not None:break
                if fixture is not None:break
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
