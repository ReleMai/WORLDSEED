from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Alert:
    severity: int
    category: str
    text: str
    subject: str = ""


def world_alerts(sim, limit: int | None = None) -> list[Alert]:
    """Derive a read-only alert inbox from authoritative simulation state.

    Alerts are deliberately *not* separate mutable game state.  They are a UI
    projection of causal facts, so opening the inbox cannot alter the world and
    old/stale warnings disappear automatically when their causes resolve.
    """
    p = sim.player_pos
    alerts: list[Alert] = []
    vit = sim.entities.try_get(sim.player_id, __import__('worldseed.entities.components', fromlist=['Vitals']).Vitals)
    if vit:
        if vit.hp <= max(20, vit.max_hp // 3): alerts.append(Alert(100, 'health', f'Critical injury: HP {vit.hp}/{vit.max_hp}.'))
        if vit.blood < 55: alerts.append(Alert(98, 'health', f'Dangerous blood loss: {vit.blood}/100.'))
        if vit.thirst >= 85: alerts.append(Alert(92, 'survival', f'Severe thirst: {vit.thirst}/100.'))
        if vit.hunger >= 90: alerts.append(Alert(88, 'survival', f'Severe hunger: {vit.hunger}/100.'))
        if vit.body_temp <= 22 or vit.body_temp >= 82: alerts.append(Alert(90, 'exposure', f'Dangerous body temperature: {vit.body_temp}/100.'))
    bleeding=sum(max(0,int(w.get('bleeding',0))) for w in sim.state.player_wounds)
    fractures=sum(1 for w in sim.state.player_wounds if w.get('fracture'))
    if bleeding:alerts.append(Alert(min(99,75+bleeding), 'wounds', f'Active bleeding total {bleeding}; treatment recommended.'))
    if fractures:alerts.append(Alert(72, 'wounds', f'{fractures} untreated/stabilized fracture(s) recorded.'))

    for fire in sim.state.fires.values():
        if fire.z==p.z:
            d=abs(fire.x-p.x)+abs(fire.y-p.y)
            if d<=20:alerts.append(Alert(max(55,92-d*2), 'fire', f'Fire {d} tiles away; intensity {fire.intensity}.', f'{fire.x},{fire.y},{fire.z}'))
    fluid=sim.environment.fluid_at(p)
    if fluid and fluid.amount>=120:alerts.append(Alert(80,'flood','You are standing in dangerously deep water.'))
    for c in sim.state.creatures.values():
        if c.hp<=0 or not c.notable or c.z!=p.z:continue
        d=abs(c.x-p.x)+abs(c.y-p.y)
        if d<=120 and c.uid in sim.known_creature_ids():
            name=c.name or (sim.registry.species.get(c.species_id).name if c.species_id in sim.registry.species else 'notable creature')
            alerts.append(Alert(max(50,90-d//3),'legend',f'Notable creature {name} is {d} tiles away; kills {c.kills}.',c.uid))
    known_towns=sim.known_settlement_ids();known_factions=sim.known_faction_ids()
    for town in sim.state.settlements.values():
        if town.uid not in known_towns:continue
        if town.food_stress>=70:alerts.append(Alert(min(90,55+town.food_stress//2),'famine',f'{town.name} is in severe food stress ({town.food_stress}/100).',town.uid))
        if town.homeless>max(3,town.population//10):alerts.append(Alert(48,'housing',f'{town.name} has {town.homeless} homeless residents.',town.uid))
    seen_wars=set()
    for f in sim.state.factions.values():
        if f.uid not in known_factions:continue
        for enemy in f.at_war:
            if enemy not in known_factions:continue
            pair=tuple(sorted((f.uid,enemy)))
            if pair in seen_wars:continue
            seen_wars.add(pair);other=sim.state.factions.get(enemy)
            alerts.append(Alert(66,'war',f'{f.name} is at war with {other.name if other else enemy}.',f.uid))
    for uid in sim.state.player_infections:
        inf=sim.state.infections.get(uid)
        if not inf:continue
        ddef=sim.registry.diseases.get(inf.disease_id);name=ddef.name if ddef else inf.disease_id
        sev=inf.severity if inf.stage=='symptomatic' else 0
        alerts.append(Alert(min(98,60+sev//2),'disease',f'You are {inf.stage} with {name}; severity {sev}.' if sev else f'You may be incubating {name}.',uid))
    for d in sim.state.diseases.values():
        if d.infected>0 and d.settlement_id in known_towns:
            town=sim.state.settlements.get(d.settlement_id);name=sim.registry.diseases[d.disease_id].name if d.disease_id in sim.registry.diseases else d.name or d.disease_id
            where=town.name if town else f'region ({d.region_x},{d.region_y})'
            alerts.append(Alert(min(92,45+d.severity//2+d.infected//10),'disease',f'{name}: {d.infected} active cases in {where}; {d.deaths} deaths; policy {d.policy}.',d.settlement_id or d.disease_id))
    # Travel is not omniscient. A migration warning requires a road the
    # character has actually learned, or a cohort physically close enough to
    # encounter near one of its endpoints.
    learned_routes={r.uid for r in sim.state.trade_routes.values() if r.uid in set(sim.state.discovered_routes)}
    route_pairs={(r.origin,r.destination) for r in sim.state.trade_routes.values() if r.uid in learned_routes}
    route_pairs |= {(b,a) for a,b in list(route_pairs)}
    traveling=0
    for c in sim.state.migration_cohorts.values():
        if c.status!='traveling':continue
        if (c.origin,c.destination) in route_pairs:traveling+=c.count
    if traveling:alerts.append(Alert(44,'migration',f'Word reaches you of {traveling} migrants or refugees traveling a road you know.'))
    near_arc=[]
    for key,a in sim.state.arcane_contamination.items():
        if a.intensity<35:continue
        try:x,y,z=(int(v) for v in key.split(','))
        except Exception:continue
        if z==p.z and abs(x-p.x)+abs(y-p.y)<=25:near_arc.append((a.intensity,x,y,a.kind))
    if near_arc:
        intensity,x,y,kind=max(near_arc)
        alerts.append(Alert(min(88,50+intensity//2),'arcane',f'{kind.title()} contamination intensity {intensity} detected near ({x},{y}).'))
    alerts.sort(key=lambda a:(-a.severity,a.category,a.text))
    return alerts if limit is None else alerts[:max(0,limit)]
