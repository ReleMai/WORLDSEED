"""Discovery-safe indoor Look over a prepared continuous-space plan."""
from worldseed.systems.illumination import (
    indoor_actor_visible, indoor_light, interior_ambient, light_description,
)
from worldseed.ui.widgets import panel


def interior_look_screen(sim, registry, width=88):
    plan, actor = sim.interiors.current_plan(), sim.interiors.player_presence()
    if plan is None or actor is None:
        return panel('INTERIOR LOOK', ['You are not indoors.'], width)
    minute = getattr(sim.clock, 'minute', 720)
    ambient = interior_ambient(getattr(sim, 'environment', None), minute, plan)
    room = next((r for r in plan.rooms if r.rect.x <= actor.x < r.rect.x+r.rect.w
                 and r.rect.y <= actor.y < r.rect.y+r.rect.h), None)
    light = indoor_light(plan, actor.x, actor.y, minute, ambient_light=ambient)
    rows = [plan.name,
            f'Floor {getattr(plan,"floor_index",0)+1} / {getattr(plan,"floor_count",1)}',
            'Room: ' + (room.name if room else 'Passage'),
            f'Lighting: {light_description(light)} ({light*100//65535}%)',
            '', 'VISIBLE FURNISHINGS']
    visible = []
    for fixture in sorted(plan.furniture, key=lambda f: (f.y, f.x, f.uid)):
        if indoor_actor_visible(plan, actor.x, actor.y, fixture.x+fixture.w//2,
                                fixture.y+fixture.h//2, minute, ambient_light=ambient):
            definition = registry.settlement_pieces.get(fixture.piece_id)
            visible.append(definition.name if definition else 'Unfamiliar furnishing')
    rows.extend(visible or ['No furnishings are visible from this position.'])
    rows.extend(['', 'Right-click a visible furnishing to inspect, use, or reposition it.',
                 'Storage contents are learned by opening accessible containers.',
                 'Leave through the entrance door.' if getattr(plan,'floor_index',0)==0
                 else 'Use the stairs to return to the ground-floor entrance.'])
    return panel('INTERIOR LOOK', rows, width, 'Esc back')
