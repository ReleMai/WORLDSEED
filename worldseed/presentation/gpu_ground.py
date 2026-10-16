"""Continuous ground materials from detached, admitted terrain only.

The GPU evaluates appearance in world coordinates. Cell identities, collision,
water depth, discovery and resources remain authoritative simulation data.
One ground quad samples its admitted material neighborhood; no edge overlays or
per-frame baked terrain surfaces are created. Unknown neighbors use the center
material and cannot contribute a hidden terrain color.
"""
from __future__ import annotations

# Cardinal then diagonal, matching the shader's fixed fragment sampler slots.
GROUND_NEIGHBORS = ((-1,0),(1,0),(0,-1),(0,1),(-1,-1),(1,-1),(-1,1),(1,1))
HARD_FEATURE_TAGS = frozenset(('shaft','ore','loot','ruin'))
BLEND_WIDTH = .42


def natural_ground(terrain_id, definitions):
    if not definitions:return False
    definition=definitions.get(terrain_id)
    if definition is None:return False
    tags=frozenset(getattr(definition,'tags',()) or ())
    return bool(tags & {'surface','underground'}) and not tags & HARD_FEATURE_TAGS


def _palette(source):
    raw=source[2]
    stride=max(1,len(raw)//4//256)
    samples=[raw[index:index+4] for index in range(0,len(raw),stride*4)
             if raw[index+3]>=128]
    if not samples:return(.3,.3,.3)
    return tuple(sum(pixel[channel] for pixel in samples)/(255.*len(samples))
                 for channel in range(3))


def _material(materials, terrain_id, definitions):
    from .gpu_scene_bridge import terrain_source
    from .gl_worldspace import GroundTexture
    # A material has one canonical authored source. Per-cell random art variants
    # create mismatched edge colors even for adjacent identical terrain IDs.
    source=materials.asset(terrain_source(terrain_id,0,0,
        visuals=getattr(materials,'_visuals',None),terrain_defs=definitions))
    def derive():
        return GroundTexture(*source,_palette(source))
    cache=getattr(materials,'_read',None)
    return cache(('continuous-ground',source[0],source[1]),derive) if cache else derive()


def ground_material(materials, cell, terrain_id, terrain_by, admitted, definitions):
    """Return (canonical source, immutable blend) for a natural ground cell.

    ``admitted`` is one visibility class: current sight or explored memory.
    An unexplored neighbor is never queried from a world/content generator.
    Hard features remain crisp, including newly modded ore/ruin definitions.
    """
    if not natural_ground(terrain_id,definitions):return None
    from .gl_worldspace import GroundBlend
    center=_material(materials,terrain_id,definitions)
    x,y,z=cell
    neighbors=[]
    soft=[]
    for dx,dy in GROUND_NEIGHBORS:
        key=(x+dx,y+dy,z)
        neighbor_id=terrain_by.get(key) if key in admitted else None
        allowed=neighbor_id is not None and natural_ground(neighbor_id,definitions)
        if allowed:
            left=definitions[terrain_id];right=definitions[neighbor_id]
            # Keep solid cave walls / hard traversal barriers visually exact.
            allowed=bool(getattr(left,'passable',True))==bool(getattr(right,'passable',True))
        soft.append(bool(allowed))
        neighbors.append(_material(materials,neighbor_id,definitions) if allowed else center)
    blend=GroundBlend((x,y),tuple(neighbors),tuple(BLEND_WIDTH if value else 0. for value in soft[:4]),center.color)
    source=(center.texture_id,center.revision,center.rgba,center.image_w,center.image_h)
    return source,blend
