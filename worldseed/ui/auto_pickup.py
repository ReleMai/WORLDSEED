"""Safe right-click path-to-pickup over already visible, prepared outdoor cells."""
from __future__ import annotations
from worldseed.core.coords import WorldPos
from worldseed.sim.commands import MoveCommand, PickupCommand
from worldseed.systems.pathfinding import local_path
from worldseed.systems.state import pos_key

MAX_AUTO_MOVES=24

def _prepared_passable(sim,pos,visible):
    if pos_key(pos.x,pos.y,pos.z) not in visible:return False
    tile=sim.world.prepared_tile_at(pos)
    if tile is None:return False
    terrain=sim.registry.terrains.get(tile.terrain_id)
    if terrain is None or not terrain.passable:return False
    if sim.settlement_physicalization.shell_at(pos) is not None:return False
    if sim.resources.blocks_movement(pos) and not sim.settlement_physicalization.clears_natural_feature(pos):
        return False
    if not sim.building.passable(pos,True):return False
    if sim.property_security.blocks_player(pos):return False
    if not sim.environment.fluid_passable(pos):return False
    return True

def execute_visible_pickup(sim,actor,target:WorldPos,*,item_id='',nearby=False):
    """Only plan and walk; every actual move and transfer is engine-authoritative."""
    if sim.interiors.player_presence() is not None:
        return 'Leave the interior before collecting outdoor ground items.'
    if target.z!=sim.player_pos.z:
        return 'The target is on another level.'
    origin=sim.player_pos
    if abs(target.x-origin.x)+abs(target.y-origin.y)>14:
        return 'Move closer to collect those items.'
    if pos_key(target.x,target.y,target.z) not in sim.visible_tiles_set:
        return 'Move closer until those items are in sight.'
    targets=[target]
    if nearby and item_id:
        extra=[]
        for y in range(target.y-2,target.y+3):
            for x in range(target.x-2,target.x+3):
                q=WorldPos(x,y,target.z)
                if q==target or pos_key(x,y,target.z) not in sim.visible_tiles_set:continue
                pile=sim.state.ground_piles.get(pos_key(x,y,target.z))
                if pile is not None and pile.items.get(item_id,0)>0:
                    extra.append(q)
        extra.sort(key=lambda q:(abs(q.x-target.x)+abs(q.y-target.y),q.y,q.x))
        targets.extend(extra[:7])
    moves=0;collected=0
    for destination in targets:
        pile=sim.state.ground_piles.get(pos_key(destination.x,destination.y,destination.z))
        if not pile or not pile.items or (item_id and not pile.items.get(item_id,0)):
            continue
        if sim.combat_active():
            return 'Automatic pickup stopped: combat requires your attention.'
        now=sim.player_pos
        if abs(destination.x-now.x)+abs(destination.y-now.y)>1:
            # Re-plan using only current LOS and cached resident terrain. Never
            # open undiscovered cells or persist speculative path geometry.
            visible=sim.visible_tiles_set
            path=local_path(now,destination,lambda q:_prepared_passable(sim,q,visible),
                            max_nodes=320,goal_radius=1)
            if not path or len(path)-1>MAX_AUTO_MOVES-moves:
                return ('Collected '+str(collected)+' pile(s); remaining path blocked.'
                        if collected else 'No safe visible path to those items.')
            for step in path[1:]:
                before=sim.player_pos
                sim.execute(MoveCommand(actor,step.x-before.x,step.y-before.y))
                moves+=1
                if sim.player_pos!=step:
                    return 'Automatic pickup stopped by an obstacle.'
                if sim.combat_active():
                    return 'Automatic pickup stopped: combat requires your attention.'
        p=sim.player_pos
        dx,dy=destination.x-p.x,destination.y-p.y
        if abs(dx)+abs(dy)>1:
            return 'Automatic pickup stopped before reaching the items.'
        sim.execute(PickupCommand(actor,dx,dy,item_id))
        collected+=1
    return (f'Collected from {collected} ground pile(s).' if collected
            else 'Those items are no longer available.')
