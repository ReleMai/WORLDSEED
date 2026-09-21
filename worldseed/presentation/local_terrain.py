"""Presentation-only local terrain transition and contextual water rules.

The world generator remains authoritative.  This module only decides how the
pygame renderer may visually blend already-known neighboring terrain textures,
which contextual water art to use, and which shoreline/riverbank overlays may
be drawn.  No simulation, movement, discovery, or terrain IDs are changed by
these helpers.
"""
from __future__ import annotations

DIRECTIONS_8 = (
    ('north', 0, -1), ('south', 0, 1), ('west', -1, 0), ('east', 1, 0),
    ('northwest', -1, -1), ('northeast', 1, -1),
    ('southwest', -1, 1), ('southeast', 1, 1),
)

AUTOTILE_TERRAINS = frozenset({
    'core:grass', 'core:forest', 'core:scrub', 'core:sand', 'core:rock',
    'core:tundra', 'core:floodplain', 'core:wetland', 'core:tilled_soil',
    'core:water', 'core:river', 'core:river_shallow', 'core:cave_floor',
    'core:berry_thicket',
})

# The renderer configures this catalog from ContentRegistry.  That makes terrain
# blending data-driven: newly added/modded ground terrains automatically enter
# the mesher when their tags describe a surface/underground ground material.
# The fallback static set above preserves headless/test behavior before a
# registry has been attached.
_DYNAMIC_TAGS: dict[str, frozenset[str]] = {}
_DYNAMIC_AUTOTILE: frozenset[str] = frozenset()

def configure_terrain_catalog(terrains) -> None:
    global _DYNAMIC_TAGS, _DYNAMIC_AUTOTILE
    tags = {tid: frozenset(getattr(td, 'tags', ()) or ()) for tid, td in terrains.items()}
    # Authored masonry must remain crisp just like shafts/ore; without this,
    # attaching the live catalog silently changes the legacy hard-edge rule.
    excluded = {'shaft', 'loot', 'ore', 'ruin'}
    blendable = {
        tid for tid, row in tags.items()
        if ('surface' in row or 'underground' in row) and not (row & excluded)
    }
    _DYNAMIC_TAGS = tags
    _DYNAMIC_AUTOTILE = frozenset(blendable)

def _tags(terrain_id: str) -> frozenset[str]:
    return _DYNAMIC_TAGS.get(terrain_id, frozenset())

def _autotile_set() -> frozenset[str]:
    return _DYNAMIC_AUTOTILE or AUTOTILE_TERRAINS

WATER_FAMILY = frozenset({'core:water', 'core:river', 'core:river_shallow'})
GRASS_FAMILY = frozenset({'core:grass', 'core:floodplain'})
RIVER_FAMILY = frozenset({'core:river', 'core:river_shallow'})
LAND_FAMILY = AUTOTILE_TERRAINS - WATER_FAMILY
CONTEXTUAL_WATER_DISPLAY_IDS = frozenset({
    'render:ocean_deep', 'render:ocean_shallow', 'render:estuary_mix',
    'render:freshwater_deep', 'render:freshwater_shallow',
})


PHYSICAL_WATER_DISPLAY = {
    'core:ocean_wade':'render:ocean_wade', 'core:ocean_shallow':'render:ocean_shallow',
    'core:ocean_shelf':'render:ocean_shelf', 'core:ocean_deep':'render:ocean_deep',
    'core:estuary_shallow':'render:estuary_mix', 'core:estuary_deep':'render:estuary_deep',
    'core:lake_shallow':'render:freshwater_shallow', 'core:lake_deep':'render:freshwater_deep',
    'core:stream':'render:stream', 'core:river_rapids':'render:rapids',
}
WATER_FAMILY = WATER_FAMILY | frozenset(PHYSICAL_WATER_DISPLAY)
RIVER_FAMILY = RIVER_FAMILY | frozenset({'core:stream','core:river_rapids'})
OCEAN_FAMILY = frozenset({'core:water','core:ocean_wade','core:ocean_shallow','core:ocean_shelf','core:ocean_deep','core:estuary_shallow','core:estuary_deep'})
AUTOTILE_TERRAINS = AUTOTILE_TERRAINS | WATER_FAMILY | frozenset({'core:shore','core:riverbank'})
LAND_FAMILY = AUTOTILE_TERRAINS - WATER_FAMILY
CONTEXTUAL_WATER_DISPLAY_IDS = CONTEXTUAL_WATER_DISPLAY_IDS | frozenset(PHYSICAL_WATER_DISPLAY.values())


def terrain_family(terrain_id: str) -> str:
    if terrain_id in WATER_FAMILY or 'water' in _tags(terrain_id):
        return 'water'
    if terrain_id in GRASS_FAMILY:
        return 'grass'
    tags = _tags(terrain_id)
    if 'floodplain' in tags:return 'grass'
    if terrain_id == 'core:sand' or 'sand' in tags or 'shore' in tags or 'riverbank' in tags:return 'sand'
    if terrain_id == 'core:wetland' or 'wetland' in tags:return 'wetland'
    if terrain_id == 'core:tilled_soil' or 'farm' in tags:return 'farm'
    if 'rock' in tags:return 'rock'
    if 'underground' in tags:return 'underground'
    if 'vegetation' in tags:return 'vegetation'
    if 'soil' in tags:return 'soil'
    return terrain_id


def is_water(terrain_id: str | None) -> bool:
    return terrain_id in WATER_FAMILY


def is_river(terrain_id: str | None) -> bool:
    return terrain_id in RIVER_FAMILY


def is_open_water(terrain_id: str | None) -> bool:
    return terrain_id in OCEAN_FAMILY


def is_blendable_land(terrain_id: str | None) -> bool:
    return bool(terrain_id and terrain_id in _autotile_set() and not is_water(terrain_id))


def contextual_display_id(center_id: str, neighbor_ids: dict[str, str | None]) -> str:
    """Return the presentation terrain id for context-sensitive water art."""
    if center_id in PHYSICAL_WATER_DISPLAY:return PHYSICAL_WATER_DISPLAY[center_id]
    if center_id == 'core:river_shallow':
        return 'render:freshwater_shallow'
    if center_id == 'core:river':
        return 'render:freshwater_deep'
    if center_id == 'core:water':
        values = tuple(neighbor_ids.values())
        if any(is_river(v) for v in values):
            return 'render:estuary_mix'
        if any(v and not is_water(v) for v in values):
            return 'render:ocean_shallow'
        return 'render:ocean_deep'
    return center_id


def can_blend(center_id: str, neighbor_id: str | None) -> bool:
    """Return whether a discovered neighboring texture may feather inward.

    Different ground IDs in the same material family *do* blend.  This is
    important for grassland/floodplain ecotones and future tagged terrain: a
    family match means the boundary should be softer, not disabled.
    """
    if not neighbor_id or center_id == neighbor_id:
        return False
    auto = _autotile_set()
    if center_id not in auto or neighbor_id not in auto:
        return False
    return True


def transition_profile(center_id: str, neighbor_id: str) -> tuple[int, int]:
    """Return (depth_px_at_28, alpha) for a natural terrain transition."""
    a = terrain_family(center_id)
    b = terrain_family(neighbor_id)
    pair = frozenset((a, b))
    if a == b:
        # Same-family ecotones (especially grassland <-> floodplain) receive a
        # wider, low-alpha feather so they read as one continuous ground cover.
        return (9 if a in {'grass','soil'} else 7, 86 if a in {'grass','soil'} else 104)
    if 'water' in pair:
        if 'sand' in pair or 'wetland' in pair:
            return (9, 148)
        if 'rock' in pair or 'underground' in pair:
            return (6, 112)
        return (7, 124)
    if 'sand' in pair:
        if 'grass' in pair or 'vegetation' in pair or 'soil' in pair:
            return (7, 102)
        if 'rock' in pair:
            return (5, 92)
        return (6, 96)
    if 'wetland' in pair:
        return (7, 118)
    if 'farm' in pair:
        return (5, 88)
    if 'rock' in pair or 'underground' in pair:
        return (4, 82)
    return (6, 98)


def edge_overlay_kind(center_id: str, neighbor_id: str | None) -> str | None:
    """Return presentation overlay type for pretty coasts and river banks."""
    if not neighbor_id or center_id == neighbor_id:
        return None
    if center_id in OCEAN_FAMILY and is_river(neighbor_id):
        return 'water_estuary'
    if center_id in OCEAN_FAMILY and is_blendable_land(neighbor_id):
        return 'water_ocean_shore'
    if center_id in RIVER_FAMILY and is_blendable_land(neighbor_id):
        return 'water_river_edge'
    if not is_blendable_land(center_id):
        return None
    if neighbor_id in OCEAN_FAMILY:
        if center_id in {'core:sand','core:shore'}:
            return 'land_beach'
        if center_id in {'core:rock', 'core:cave_floor'}:
            return 'land_rock_shore'
        return 'land_shore'
    if neighbor_id in RIVER_FAMILY:
        if center_id in {'core:rock', 'core:cave_floor', 'core:sand'}:
            return 'land_riverbank_bare'
        return 'land_riverbank_soft'
    return None


def edge_overlay_signature(center_id: str, neighbor_ids: dict[str, str | None]) -> tuple:
    return tuple((direction, edge_overlay_kind(center_id, neighbor_ids.get(direction)))
                 for direction, _, _ in DIRECTIONS_8)


def transition_signature(center_id: str, neighbor_ids: dict[str, str | None]) -> tuple:
    """Stable eight-direction signature used by the renderer's composed cache."""
    return tuple((direction, neighbor_ids.get(direction) if can_blend(center_id, neighbor_ids.get(direction)) else None)
                 for direction, _, _ in DIRECTIONS_8)
