"""Move generated building cargo indoors without replacing its inventory."""


def move_storage_indoors(state, container, structure):
    if not structure.enclosed or structure.destroyed or not structure.footprint:
        return False
    key='indoor-storage:'+container.uid
    occupied=state.containers.get(key)
    if occupied is not None and occupied is not container:
        return False
    for old_key in [k for k,c in state.containers.items() if c is container and k!=key]:
        del state.containers[old_key]
    state.containers[key]=container
    x,y=structure.entrance or structure.footprint[0]
    container.x,container.y,container.z=int(x),int(y),0
    if not container.interior_space_id:
        container.interior_space_id='interior:'+structure.uid
        container.interior_furniture_uid='storage-furniture:'+container.uid
    refresh=getattr(state.containers, 'refresh_key', None)
    if callable(refresh):refresh(key)
    if not container.profile_id:
        container.profile_id='core:supply_crate'
    return True
