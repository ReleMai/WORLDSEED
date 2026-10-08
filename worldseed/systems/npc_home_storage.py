"""Physical access to an NPC's existing home and workplace inventories."""
from __future__ import annotations

from worldseed.core.coords import WorldPos
from worldseed.systems.furniture_storage import storage_preference


class NPCStorageAccess:
    def __init__(self, state, world, physicalization, interiors, goods=None):
        self.state = state
        self.world = world
        self.physicalization = physicalization
        self.interiors = interiors
        self.goods = goods

    def own_storages(self, npc, town):
        properties = {str(npc.home_id), str(npc.workplace_id)} - {""}
        return sorted((c for c in self.state.containers.values()
                       if c.settlement_id == town.uid and c.property_id in properties),
                      key=lambda c: (c.property_id != npc.home_id, c.uid))

    def home_storage(self, npc, item_ids=()):
        return self.property_storage(npc,npc.home_id,item_ids)

    def property_storage(self,npc,property_id,item_ids=()):
        if not property_id:
            return None
        if self.interiors is not None:
            self.interiors.prepare_workplace(property_id)
        item_ids=tuple(item_ids)
        rows = sorted((c for c in self.state.containers.values()
                       if c.property_id == property_id and c.settlement_id == npc.settlement_id),
                      key=lambda c: (not bool(c.interior_space_id),
                                     storage_preference(c,item_ids,self.goods.registry) if self.goods else 0,
                                     -c.capacity_volume_ml,c.uid))
        for container in rows:
            if item_ids and self.goods and not any(self.goods.container_fit(container,iid)>0 for iid in item_ids):
                continue
            if not container.interior_space_id:
                return container
            if self._interior_target(npc, container) is not None:
                return container
        return None

    def repair_indoor_route(self,npc):
        """Upgrade saved outdoor cargo walks after their container moves inside."""
        task=npc.tasks[0]
        if task.get('kind') not in {'move','perform'} or task.get('interior_storage_door_uid'):
            return True
        action_task=npc.tasks[1] if task.get('kind')=='move' and len(npc.tasks)>1 else task
        uid=task.get('container_uid') or action_task.get('container_uid')
        if action_task.get('action')=='workplace_pickup':
            shipment=self.state.workplace_shipments.get(action_task.get('shipment_uid',''))
            if shipment is not None:uid=shipment.source_uid
        if not uid:return True
        container=next((c for c in self.state.containers.values() if c.uid==uid),None)
        if container is None or not container.interior_space_id or self.in_reach(npc,container):return True
        steps=self.transfer_tasks(npc,container,action_task.get('action',''),action_task.get('items',{}))
        if not steps:return False
        action_task.update(storage_task=True,container_uid=container.uid)
        if task.get('kind')=='move':
            task.update(steps[0]);task.pop('_local_path',None);task.pop('_local_path_goal',None)
        elif npc.uid not in self.state.interior_actors:
            npc.tasks.insert(0,steps[0])
            return False
        return True

    def _interior_target(self, npc, container):
        if self.interiors is None or container.property_id not in {npc.home_id, npc.workplace_id}:
            return None
        plan = self.state.interiors.get(container.interior_space_id)
        if plan is None:
            self.interiors.prepare_workplace(container.property_id)
            plan = self.state.interiors.get(container.interior_space_id)
        if plan is None:
            return None
        fixture = next((f for f in plan.furniture if f.uid == container.interior_furniture_uid), None)
        target = self.interiors.fixture_use_position(plan, fixture)
        return (plan, target) if target is not None else None

    def use_position(self, npc, container):
        candidates = []
        for dx, dy in ((0, -1), (-1, 0), (1, 0), (0, 1)):
            pos = WorldPos(container.x + dx, container.y + dy, container.z)
            if not self.world.is_passable(pos):
                continue
            if self.physicalization is not None and not self.physicalization.passable(pos, True):
                continue
            security = getattr(getattr(self.interiors, "sim", None), "property_security", None)
            if security is not None and security.blocks_actor(pos, npc.uid):
                continue
            candidates.append(pos)
        return min(candidates, key=lambda p: (abs(npc.x-p.x)+abs(npc.y-p.y), p.y, p.x)) if candidates else None

    def transfer_tasks(self, npc, container, action, items, **meta):
        if container.property_id not in {npc.home_id, npc.workplace_id}:
            return []
        shared = dict(meta, storage_task=True, profession_task=True, container_uid=container.uid)
        perform = dict(shared, kind="perform", action=action, items=items)
        if container.interior_space_id:
            indoor = self._interior_target(npc, container)
            if indoor is None:
                return []
            plan, _ = indoor
            ground = self.state.interiors.get("interior:" + plan.building_id, plan)
            frontage = getattr(self.physicalization, 'frontage_for', lambda _: None)(plan.building_id)
            target = frontage or WorldPos(ground.exterior_x, ground.exterior_y, ground.exterior_z)
            move = dict(shared, kind="move", x=target.x, y=target.y,
                        z=target.z, exact=True, physical_path=True,
                        interior_storage_door_uid=ground.door_uid)
        else:
            target = self.use_position(npc, container)
            if target is None:
                return []
            move = dict(shared, kind="move", x=target.x, y=target.y, z=target.z,
                        exact=True, physical_path=True)
        return [move, perform]

    def in_reach(self, npc, container):
        actor = getattr(self.state, "interior_actors", {}).get(npc.uid)
        if container.interior_space_id:
            if self.interiors is None or actor is None or actor.space_id != container.interior_space_id:
                return False
            plan = self.state.interiors.get(actor.space_id)
            fixture = next((f for f in plan.furniture if f.uid == container.interior_furniture_uid), None) if plan else None
            return bool(fixture and self.interiors._furniture_reachable(plan, actor, fixture, 900))
        return actor is None and npc.z == container.z and max(abs(npc.x-container.x), abs(npc.y-container.y)) <= 1
