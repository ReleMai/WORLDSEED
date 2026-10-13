"""Stable cabin portals derived from authoritative player construction sites.

Only completion/load prepares a door. Interior creation belongs to explicit
entry; observation never manufactures doors, furniture or settlement plans.
"""
from __future__ import annotations

from worldseed.systems.homestead_blueprints import doorway, door_uid, footprint
from worldseed.systems.state import DoorSecurityState
from worldseed.world.regional_plan import StructurePlanState


def ensure_access(sim, site) -> DoorSecurityState | None:
    """Bind one persistent door to a completed site without resetting its lock."""
    if int(site.get("stage", 0)) != 4:
        return None
    uid = door_uid(site)
    x, y, z = doorway(site)[0]
    door = sim.state.door_security.get(uid)
    if door is None:
        door = DoorSecurityState(uid, "", site["uid"], x, y, z,
                                 owner_uid=site.get("owner_uid", "player"))
        sim.state.door_security[uid] = door
    else:
        door.property_id = site["uid"]
        door.x, door.y, door.z = x, y, z
        door.owner_uid = site.get("owner_uid", "player")
    return door


def structure_projection(site) -> StructurePlanState:
    """Adapt a site to existing interior geometry without a second building list."""
    inside, _ = doorway(site)
    return StructurePlanState(
        site["uid"], "", "core:house", "residence",
        footprint=[(x, y) for x, y, _ in footprint(site)],
        entrance=inside[:2], orientation=int(site["orientation"]),
        owner_uid=site.get("owner_uid", "player"),
        construction_stage="complete", building_type="log_cabin",
        enclosed=True, roof_percent=100,
    )
