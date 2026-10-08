"""Functions and inventories projected from existing, persistent furnishings.

ContainerState remains the sole inventory authority. Preparation binds old
containers first; additional usable furniture receives an empty inventory, never
another allocation from town stock or a copy of its neighbour's contents.
"""
from functools import lru_cache
import json

from worldseed.config import DATA_DIR
from worldseed.systems.container_profiles import container_profile
from worldseed.systems.interior_furnishing import furniture_base_piece
from worldseed.systems.state import ContainerState


@lru_cache(maxsize=1)
def catalog():
    raw=json.loads((DATA_DIR/'furniture_storage.json').read_text(encoding='utf-8'))
    if raw.get('version')!=1 or not isinstance(raw.get('pieces'),dict):
        raise ValueError('Invalid furniture storage catalog')
    for piece,row in raw['pieces'].items():
        if (not piece.startswith('core:') or container_profile(row.get('profile','')) is None
                or not isinstance(row.get('purpose'),str) or not row['purpose'].strip()
                or any(type(row.get(k)) is not int or row[k]<=0 for k in ('mass_g','volume_ml'))):
            raise ValueError('Invalid furniture storage function: '+piece)
    return raw['pieces']


def storage_function(piece_id):
    rows=catalog()
    return rows.get(piece_id) or rows.get(furniture_base_piece(piece_id))


def materialize_storage(state,plan,registry):
    """Called after furnishing preparation; never from a UI or hover query."""
    existing={c.interior_furniture_uid:c for c in state.containers.values()
              if c.interior_space_id==plan.uid and c.interior_furniture_uid}
    primary=next((c for c in state.containers.values() if c.property_id==plan.building_id),None)
    container_ids={c.uid for c in state.containers.values()}
    for fixture in sorted(plan.furniture,key=lambda f:f.uid):
        rule=storage_function(fixture.piece_id)
        if rule is None or fixture.uid in existing:
            continue
        if fixture.piece_id not in registry.settlement_pieces:
            raise ValueError('Unknown storage furnishing: '+fixture.piece_id)
        uid='furniture-storage:'+fixture.uid
        key='indoor-storage:'+uid
        # A bound object retains identity through save/load, ownership changes
        # and free furniture repositioning. Do not replace a displaced inventory.
        if uid in container_ids:
            continue
        profile=container_profile(rule['profile'])
        owner=primary.owner if primary else fixture.owner_uid or plan.owner_uid
        prop=state.properties.get(plan.building_id)
        if prop is not None:owner=prop.owner_uid
        name=registry.settlement_pieces[fixture.piece_id].name
        state.containers[key]=ContainerState(
            uid,plan.exterior_x,plan.exterior_y,plan.exterior_z,owner,
            rule['mass_g'],rule['volume_ml'],items={},name=name,kind='property',movable=False,
            source_id=profile.source_id,settlement_id=primary.settlement_id if primary else '',
            property_id=plan.building_id,access='private',profile_id=profile.uid,
            interior_space_id=plan.uid,interior_furniture_uid=fixture.uid,
        )


def storage_preference(container,item_ids,registry):
    """Soft placement preferences; player storage remains general-purpose."""
    profile=container_profile(container.profile_id)
    if profile is None:return 4
    score=0
    for iid in item_ids:
        item=getattr(registry,'items',{}).get(iid)
        desired='core:household_chest'
        if iid.endswith('_seed') or iid=='core:flour':desired='core:grain_bin'
        elif item is not None and getattr(item,'food_groups',()):desired='core:pantry_cabinet'
        elif iid in {'core:clean_water','core:small_ale'}:desired='core:inn_barrel'
        elif iid in {'core:book','core:parchment'}:desired='core:archive_bookcase'
        elif iid in {'core:soap','core:herbal_tonic','core:medicinal_herb'}:desired='core:medicine_cabinet'
        elif iid in {'core:woven_cloth','core:leather','core:fiber'} or getattr(item,'equip_slot',''):
            desired='core:wardrobe'
        score += 0 if profile.uid==desired else 1 if iid in profile.loot else 2 if profile.uid=='core:household_chest' else 4
    return score
