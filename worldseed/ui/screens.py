from __future__ import annotations

from collections import Counter, defaultdict

from worldseed.content.registry import ContentRegistry
from worldseed.entities.components import Inventory, Vitals
from worldseed.sim.engine import Simulation
from worldseed.ui.widgets import panel as _panel

def _known_towns(sim:Simulation): return sim.known_settlements()
def _known_npcs(sim:Simulation): return sim.known_npcs()
def _known_factions(sim:Simulation): return sim.known_factions()
def _known_routes(sim:Simulation):
    known=sim.known_settlement_ids();routes=set(sim.state.discovered_routes)
    return [r for r in sim.state.trade_routes.values() if r.uid in routes and r.origin in known and r.destination in known]
def _known_books(sim:Simulation):
    owners={'player'}|sim.known_npc_ids()|sim.known_settlement_ids()
    library_ids={lib.uid for lib in sim.state.libraries.values() if lib.settlement_id in sim.known_settlement_ids()}
    return [b for b in sim.state.books.values() if b.owner in owners or b.owner in library_ids]
def _known_artifacts(sim:Simulation):
    owners={'player'}|sim.known_npc_ids()|sim.known_settlement_ids()
    return [a for a in sim.state.artifacts.values() if a.owner in owners or any(str(row.get('owner','')) in owners for row in a.provenance)]
def _known_graves(sim:Simulation):
    known=sim.known_npc_ids();tiles=sim.discovered_tiles_set
    return [g for g in sim.state.graves.values() if g.person_uid in known or f'{g.x},{g.y},{g.z}' in tiles]
def _known_culture_ids(sim:Simulation):
    ids={s.culture_id for s in _known_towns(sim)}|{n.culture_id for n in _known_npcs(sim)}
    ids|={f.culture_id for f in _known_factions(sim)}
    return {x for x in ids if x}
def _known_religion_ids(sim:Simulation):
    return {x for x in ({s.religion_id for s in _known_towns(sim)}|{n.religion_id for n in _known_npcs(sim)}) if x}
def _discovered_regions(sim:Simulation):
    regions=set()
    for key in sim.discovered_tiles_set:
        try:
            x,y,_=(int(v) for v in key.split(','));regions.add((x//512,y//512))
        except Exception:
            continue
    return regions
def _known_events(sim:Simulation):
    known=sim.known_event_ids();return [e for e in sim.state.history if e.uid in known]


def _bar(value:int, maximum:int=100, width:int=20, fill:str='#', empty:str='-')->str:
    maximum=max(1,maximum);value=max(0,min(maximum,value));n=round(width*value/maximum)
    return fill*n+empty*(width-n)


def _spark(values:list[int],width:int=18,unicode:bool=True)->str:
    if not values:return ''
    if len(values)>width:
        step=max(1,len(values)//width);values=[values[min(i*step,len(values)-1)] for i in range(width)]
    lo=min(values);hi=max(values)
    chars='▁▂▃▄▅▆▇█' if unicode else '.:-=+*#@'
    if hi==lo:return chars[len(chars)//2]*len(values)
    return ''.join(chars[min(len(chars)-1,(v-lo)*(len(chars)-1)//max(1,hi-lo))] for v in values)

def box(title:str,body:list[str],width:int=88,footer:str='Press Esc to return.') -> str:
    return _panel(title, [str(x) for x in body], width, footer)


def inventory_screen(reg:ContentRegistry,inv:Inventory,width:int=96,sim:Simulation|None=None)->str:
    body=[];tm=tv=0
    for iid,n in sorted(inv.items.items()):
        if iid not in reg.items:continue
        item=reg.items[iid];body.append(f"{item.name:<30} x{n:<5} {item.mass_g*n/1000:7.1f} kg  {item.volume_ml*n/1000:7.1f} L")
        tm+=item.mass_g*n;tv+=item.volume_ml*n
    body += ['',f'Total mass: {tm/1000:.1f} kg',f'Estimated volume: {tv/1000:.1f} L']
    if sim is not None:
        metal=sim.metallurgy.describe_owner_batches('player')
        if metal:body += ['', 'METAL BATCHES'] + metal[:12]
        artifacts=sim.artifacts.describe_owner('player')
        if artifacts:body += ['', 'INDIVIDUAL DURABLE ITEMS'] + artifacts[:16]
    return box('INVENTORY',body or ['Your pack is empty.'],width)


def item_detail_screen(reg:ContentRegistry,sim:Simulation,inv:Inventory,item_id:str,width:int=96)->str:
    item=reg.items.get(item_id)
    if not item:return box('ITEM',['Unknown item.'],width)
    count=inv.count(item_id)
    body=[item.name,f'Carried: {count}',f'Weight: {item.mass_g/1000:.2f} kg each']
    if item.description:body+=['',item.description]
    if item.flavor:body+=['',f'“{item.flavor}”']
    if item.material and item.material in reg.materials:
        m=reg.materials[item.material]
        def grade(v:int)->str:
            if v>=80:return 'exceptional'
            if v>=60:return 'strong'
            if v>=40:return 'moderate'
            if v>=20:return 'soft'
            return 'very soft'
        qualities=[]
        if m.hardness:qualities.append(f'{grade(m.hardness)} hardness')
        if m.toughness:qualities.append(f'{grade(m.toughness)} toughness')
        if m.edge>=50:qualities.append('holds an edge well')
        if m.corrosion>=50:qualities.append('prone to corrosion')
        if m.flammability>=60:qualities.append('burns readily')
        body+=['',f'Made chiefly from {m.name}.',(', '.join(qualities).capitalize()+'.') if qualities else 'A plain, workable material.']
    traits=[]
    if item.nutrition:traits.append(f'Satiety {item.nutrition}   Hydration {item.hydration}')
    if item.calories or item.protein or item.carbs or item.fat or item.fiber:traits.append(f'Nutrition: {item.calories} kcal | protein {item.protein} | carbs {item.carbs} | fat {item.fat} | fiber {item.fiber}')
    if item.food_groups:traits.append('Diet: '+', '.join(x.title() for x in item.food_groups))
    if item.tool_qualities:traits.append('Tool qualities: '+', '.join(f'{k.replace("_"," ")} {v}' for k,v in sorted(item.tool_qualities.items())))
    elif item.tool_power:traits.append(f'Tool effectiveness {item.tool_power}')
    if item.weapon_damage:traits.append(f'{item.damage_type.title()} damage {item.weapon_damage}' + (f' | range {item.range}' if item.range>1 else ''))
    if item.ammo_item and item.ammo_item in reg.items:traits.append(f'Ammunition: {reg.items[item.ammo_item].name}')
    if item.armor:traits.append(f'Protection {item.armor}')
    if item.insulation:traits.append(f'Warmth {item.insulation}')
    if item.spoilage_hours:traits.append(f'Keeps about {item.spoilage_hours//24} day(s) under ordinary conditions')
    if item.utility_roles:traits.append('Roles: '+', '.join(x.replace('_',' ') for x in item.utility_roles))
    if traits:body+=['','USE',*traits]
    if item.coverage:body.append('Covers: '+', '.join(x.replace('_',' ') for x in item.coverage))
    artifacts=[a for a in sim.state.artifacts.values() if a.owner=='player' and a.base_item==item_id]
    if artifacts:
        body+=['','INDIVIDUAL ITEMS']
        for a in artifacts[:12]:
            label=a.name or item.name;body.append(f'{label}: condition {a.condition}%, quality {a.quality}%')
            if a.components:
                body.append('  '+', '.join(f'{k.replace("_"," ")}: {str(v.get("material", "unknown")).split(":")[-1].replace("_"," ")}' for k,v in a.components.items()))
    return box(item.name.upper(),body,width)


def equipment_screen(sim:Simulation,reg:ContentRegistry,inv:Inventory,width:int=100)->str:
    vit=sim.entities.get(sim.player_id,Vitals)
    attrs=sim.state.player_attributes;skills=sim.state.player_skills;talents=sim.state.player_talents
    sex=str(getattr(sim.state,'player_sex','male')).title();appearance=int(getattr(sim.state,'player_sprite_index',0))+1
    body=[f'{sim.state.player_name}', f'Sex: {sex}    Appearance: {appearance:02d}', '', 'ATTRIBUTES', '  '+', '.join(f'{k.title()} {v}' for k,v in attrs.items()), '', 'SKILLS']
    trained=[f'{k.replace("_"," ").title()} {v}' for k,v in skills.items() if v>0]
    body+=['  '+(', '.join(trained) if trained else 'None trained'),'', 'TALENTS','  '+(', '.join(x.replace('_',' ').title() for x in talents) if talents else 'None'),'','CONDITION',f'Body temperature  [{_bar(vit.body_temp)}] {vit.body_temp}/100',f'Blood volume     [{_bar(vit.blood)}] {vit.blood}/100',f'Pain             [{_bar(vit.pain)}] {vit.pain}/100',f'Stamina          [{_bar(vit.stamina)}] {vit.stamina}/100','','COMBAT READY']
    ready=reg.items.get(sim.state.player_readied_weapon)
    if ready:
        body.append(f'Weapon: {ready.name} | {ready.weapon_class or ready.damage_type} | damage {ready.weapon_damage} | reach {ready.reach} | range {ready.range} | stamina {ready.stamina_cost}')
        if sim.state.player_aim_target:body.append(f'Aim: {sim.state.player_aim_zone} | steadiness {sim.state.player_aim_quality}/100')
    else:body.append('Weapon: unarmed')
    body+=['', 'EQUIPPED']
    if sim.state.player_equipment:
        for slot,iid in sorted(sim.state.player_equipment.items()):
            item=reg.items.get(iid);art=sim.state.artifacts.get(sim.state.player_equipped_artifacts.get(slot,''));detail=f' q{sim.artifacts.effective_quality(art)} cond {art.condition}%' if art else ''
            body.append(f'{slot:<12} {(item.name if item else iid):<30} armor {(item.armor if item else 0):>3}{detail}')
    else:body.append('Nothing equipped.')
    body+=['','ANATOMY']
    for part,hp in sim.state.player_body_parts.items():body.append(f'{part.replace("_"," "):<18} [{_bar(hp,100,16)}] {hp:>3}/100')
    active=[w for w in sim.state.player_wounds if int(w.get('severity',0))>0 or int(w.get('bleeding',0))>0 or w.get('fracture')]
    body+=['','WOUNDS']
    if active:
        for w in active[-14:]:body.append(f'{str(w.get("part","?")).replace("_"," "):<15} {w.get("tissue","?"):<8} sev {w.get("severity",0):>3} bleed {w.get("bleeding",0):>2}' + ('  FRACTURE' if w.get('fracture') else '') + ('  bandaged' if w.get('bandaged') else ''))
    else:body.append('No significant wounds.')
    return box('CHARACTER / EQUIPMENT / ANATOMY',body,width)



def health_screen(sim:Simulation,width:int=114)->str:
    vit=sim.entities.get(sim.player_id,Vitals)
    body=[f'PLAYER HEALTH  HP {vit.hp}/{vit.max_hp} | blood {vit.blood}/100 | pain {vit.pain}/100 | stamina {vit.stamina}/100',f'Active wounds {len(sim.state.player_wounds)} | Active infections {len(sim.state.player_infections)} | Immunities {len(sim.state.player_immunities)}','']
    totals=sim.nutrition.seven_day_totals(sim.clock.minute)
    body+=['NUTRITION & DIET',
           '  '+ ' | '.join(f'{g.title()} {int(sim.state.player_nutrition.get(g,0)):>3}/100' for g in ('protein','vegetable','grain','fruit','fats')),
           f'  Last 7 days: {totals["meals"]} eating events | {totals["calories"]} kcal | protein {totals["protein"]} | carbs {totals["carbs"]} | fat {totals["fat"]} | fiber {totals["fiber"]}']
    active_food=[k.replace('_',' ') for k,v in sim.state.player_food_effects.items() if int(v)>sim.clock.minute]
    body.append('  Food effects: '+(', '.join(active_food) if active_food else 'none'))
    recent=sim.state.player_diet_history[-6:]
    if recent:body+=['  Recent diet: '+', '.join(str(r.get('name','food')) for r in recent)]
    body+=['']
    if sim.state.player_infections:
        body.append('PLAYER INFECTIONS')
        for uid in sim.state.player_infections:
            inf=sim.state.infections.get(uid)
            if not inf:continue
            disease=sim.registry.diseases.get(inf.disease_id)
            body.append(f'{(disease.name if disease else inf.disease_id):<26} stage={inf.stage:<11} severity={inf.severity:>3} treated={inf.treated} source={inf.source}')
            if disease:body.append(f'  transmission={", ".join(disease.transmissions)} symptoms={", ".join(disease.symptoms)} incubation={disease.incubation_hours}h illness={disease.illness_hours}h')
    else:body.append('No active player infection.')
    body+=['','SETTLEMENT EPIDEMIOLOGY']
    towns=sorted(_known_towns(sim),key=lambda t:(-(sum(d.infected for d in sim.state.diseases.values() if d.settlement_id==t.uid)),t.name))
    for town in towns[:18]:
        obs=[d for d in sim.state.diseases.values() if d.settlement_id==town.uid and d.infected>0]
        infected=sum(d.infected for d in obs);deaths=sum(d.deaths for d in obs);prev=infected*100//max(1,town.population)
        meds=town.stocks.get('core:herbal_tonic',0);soap=town.stocks.get('core:soap',0)
        body.append(f'{town.name:<22} pop {town.population:<5} cases {infected:<4} ({prev:>2}%) deaths {deaths:<4} policy {town.health_policy:<10} Q{town.quarantine_level:<3} sanitation {town.sanitation:<3} healers {town.healer_capacity:<3} meds {meds:<3} soap {soap:<3}')
        for d in obs[:3]:
            ddef=sim.registry.diseases.get(d.disease_id);spark=_spark([int(r[1]) for r in d.trend[-24:]],14,sim.state.ui_unicode)
            body.append(f'  {(ddef.name if ddef else d.name or d.disease_id):<22} {spark:<14} inf {d.infected:<4} rec {d.recovered:<4} dead {d.deaths:<3} sev {d.severity:<3} strain {d.strain:+d}')
    if not towns:body.append('No known settlement health reports.')
    body+=['','Illness can spread through close contact, poor sanitation, food, water, animals and travel. What you know depends on places you have visited and people you have spoken with.']
    return box('HEALTH',body,width)

def help_screen(width:int=100)->str:
    body=[
        'MOVE',
        '  WASD / arrows   walk',
        '',
        'DO THINGS',
        '  Enter           nearby actions',
        '  G               gather or mine',
        '  I               inventory',
        '  L               look around',
        '  TAB             journal and world information',
        '  ESC             pause / back',
        '  Pause button    save, settings and quit',
        '',
        'MENUS',
        '  Mouse click     choose a card or button',
        '  Mouse wheel     page / scroll',
        '  Back / ESC      return (right-click also works)',
        '',
        'Nothing requires a quest. Explore, build, hunt, trade, study, settle, or leave everything behind and travel.',
    ]
    return box('HELP',body,width,'Click buttons • Wheel scrolls • Arrows/Enter remain available')

def look_screen(sim:Simulation,width:int=100,pos=None)->str:
    p=pos or sim.player_pos;t=sim.world.tile_at(p);room=sim.building.room_at(p);w=sim.environment.weather.at(sim.clock.minute,p.x,p.y)
    key=f'{p.x},{p.y},{p.z}';crop=sim.state.crops.get(key);soil=sim.state.soils.get(key);container=sim.state.containers.get(key);fluid=sim.state.fluids.get(key);fire=sim.state.fires.get(key);arc=sim.state.arcane_contamination.get(key)
    feature=sim.resources.description(p)
    body=[f'{feature}',f'Ground: {t.terrain.name}',f'Position: {p.x}, {p.y}, z {p.z}',f'Weather: {w["kind"].title()}']
    if room.get('sheltered'):body.append(f'Shelter: {room.get("classification","room")}')
    elif room.get('enclosed'):body.append('Shelter: enclosed, but open to the sky')
    survival=sim.player_skill('survival');natural=sim.player_skill('naturalism');mining=sim.player_skill('mining')
    if p.z==0 and (survival>=4 or natural>=4):
        environment = sim.world.environment_at(p)
        if environment is not None:
            body.extend(environment.ground_signs())
        else:
            body.append('Ground signs: detailed land survey unavailable here')
    if p.z<0 and mining>=4:
        tags=set(t.terrain.tags);body.append('Stone signs: '+('ore-bearing rock' if 'ore' in tags else 'workable rock' if 'rock' in tags else 'cave floor'))
        caves=getattr(sim.world.generator,'caves',None)
        if caves is not None:
            level=caves.level_info(abs(p.z))
            body.append(f'Geology: {level.band} — {level.rock}; moisture {level.moisture}')
            if mining>=6:
                body.append('Prospecting expectation: '+', '.join(level.ore_bias))
    site=sim.world.generator.sites.info(__import__('worldseed.core.coords',fromlist=['split_world']).split_world(p)[0])
    if site and site.uid in sim.known_site_ids():body.append(f'Known site: {site.name}')
    if 'shaft' in t.terrain.tags:
        up=p.z<0 and 'shaft' in sim.world.tile_at(p.moved(0,0,1)).terrain.tags;down='shaft' in sim.world.tile_at(p.moved(0,0,-1)).terrain.tags
        body.append('Passage: '+('up and down' if up and down else 'down' if down else 'up' if up else 'blocked'))
    creature=next((c for c in sim.state.creatures.values() if c.hp>0 and (c.x,c.y,c.z)==(p.x,p.y,p.z)),None)
    if creature:
        sp=sim.registry.species.get(creature.species_id)
        known=creature.species_id in sim.known_species_ids()
        label=sp.name if sp and known else 'Unknown animal'
        body.append(f'Animal: {label} — {creature.behavior.replace("_"," ")}')
        hunting=sim.player_skill('hunting')
        if hunting>=3 or survival>=4:
            condition=[]
            if creature.blood<75:condition.append('blood loss')
            if creature.pain>=35:condition.append('in visible pain')
            if any('leg' in str(w.get('part','')) and (w.get('fracture') or int(w.get('severity',0))>=35) for w in creature.wounds):condition.append('limping')
            if condition:body.append('Observed condition: '+', '.join(condition))
        if hunting>=7 and creature.wounds:
            body.append(f'Observed wounds: {len(creature.wounds)}; blood reserve appears {"critical" if creature.blood<35 else "low" if creature.blood<70 else "stable"}.')
    signs=sim.hunting.signs_at(p)
    for sign in signs[:4]:
        body.append('Sign: '+sim.hunting.describe_sign(sign,sim.player_skill('hunting'),survival,sim.clock.minute,species_known=sign.species_id in sim.known_species_ids()))
    carcass=next((c for c in sim.state.carcasses.values() if (c.x,c.y,c.z)==(p.x,p.y,p.z)),None)
    if carcass:
        sp=sim.registry.species.get(carcass.species_id);steps=[]
        steps.append('skinned' if carcass.skinned else 'hide intact')
        steps.append('butchered' if carcass.butchered else 'not butchered')
        steps.append('deboned' if carcass.deboned else 'bones remain')
        body.append(f'Carcass: {sp.name if sp else carcass.species_id} — quality {carcass.quality}% — '+', '.join(steps))
    if crop:
        stage='ready to harvest' if crop.mature else 'growing';body.append(f'Crop: {crop.crop_id.split(":")[-1].replace("_"," ")} — {stage}')
        if sim.player_skill('survival')>=4:body.append(f'Condition: health {crop.health}, moisture {crop.moisture}, disease {crop.disease}')
    if soil and sim.player_skill('survival')>=6:body.append(f'Soil: N {soil.nitrogen} / P {soil.phosphorus} / K {soil.potassium}, organic {soil.organic}')
    if container:
        mass,volume=sim.building.container_load(container);body.append(f'Storage: {sum(container.items.values())} item(s), {mass/1000:.1f} kg')
    if fluid:body.append('Water: shallow' if fluid.amount<80 else 'Water: deep' if fluid.amount>=120 else 'Water: knee-deep')
    if fire:body.append('Fire: weak' if fire.intensity<35 else 'Fire: strong' if fire.intensity<75 else 'Fire: raging')
    if arc and (sim.player_skill('arcana')>=3 or sim.has_talent('arcane_attuned')):body.append(f'You sense {arc.kind} residue here.')
    return box('LOOK',body,width)

def journal_screen(sim:Simulation,width:int=106)->str:
    body=[sim.state.player_name,'']
    if sim.state.player_rumors:
        body+=['THINGS YOU HAVE HEARD']+[f'• {x}' for x in sim.state.player_rumors[-12:]]
    else:
        body+=['Your journal is empty.']
    body+=['','DISCOVERED',f'Places: {len(sim.known_settlement_ids())}',f'People: {len(sim.known_npc_ids())}',f'Sites: {len(sim.known_site_ids())}',f'Events: {len(sim.known_event_ids())}']
    return box('JOURNAL',body,width)

def _region_ascii(sim:Simulation,w:int=31,h:int=13)->list[str]:
    p=sim.player_pos;prx,pry=p.x//512,p.y//512;hw=w//2;hh=h//2
    towns={(s.region_x,s.region_y):s for s in _known_towns(sim)};visited=sim.visited_settlement_ids();routes=_known_routes(sim);discovered_regions=_discovered_regions(sim)
    route_cells=set()
    for route in routes:
        for token in route.waypoints:
            try:route_cells.add(tuple(int(v) for v in token.split(',')))
            except Exception:pass
    chars=[]
    for sy in range(h):
        ry=pry+sy-hh;row=[]
        for sx in range(w):
            rx=prx+sx-hw
            if (rx,ry)==(prx,pry):ch='@'
            elif (rx,ry) in towns:ch='O' if towns[(rx,ry)].uid in visited else 'o'
            elif (rx,ry) in route_cells:ch='+'
            elif (rx,ry) in discovered_regions:ch='.'
            else:ch=' '
            row.append(ch)
        chars.append('|'+''.join(row)+'|')
    return chars

def world_screen(sim:Simulation,width:int=106)->str:
    p=sim.player_pos;visited=sim.visited_settlement_ids();map_rows=_region_ascii(sim);map_w=max((len(r) for r in map_rows),default=0);body=['@ you   O visited place   o place known by report   + known road', '+'+'-'*max(0,map_w-2)+'+']+map_rows+['+'+'-'*max(0,map_w-2)+'+','','KNOWN PLACES']
    towns=sorted(_known_towns(sim),key=lambda s:abs(s.x-p.x)+abs(s.y-p.y))
    if not towns:body.append('None.')
    for town in towns[:18]:
        dx,dy=town.x-p.x,town.y-p.y;direction='east' if abs(dx)>=abs(dy) and dx>0 else 'west' if abs(dx)>=abs(dy) else 'south' if dy>0 else 'north';dist=abs(dx)+abs(dy)
        distance='nearby' if dist<80 else 'a moderate journey' if dist<300 else 'far away'
        status='visited' if town.uid in visited else 'known by report'
        body.append(f'{town.name:<24} {direction}, {distance} — {status}')
    return box('MAP',body,width)

def history_screen(sim:Simulation,width:int=110)->str:
    events=sorted(_known_events(sim),key=lambda e:(e.minute,e.uid),reverse=True)[:36]
    body=['KNOWN CHRONICLE — latest first']+[f'Y{e.minute//(1440*120)+1:>3} D{(e.minute//1440)%120+1:>3} [{e.event_type:<20}] {e.summary}' for e in events]
    if not events:body.append('You have not learned any major historical events yet.')
    legends=[e for e in events if e.salience>=80][:8]
    if legends:body+=['','KNOWN LEGENDS']+[f'[{e.salience:>3}] {e.summary}' for e in legends]
    if sim.state.legacy:body+=['','PREVIOUS PLAYER CHARACTERS']+[f'{x.name}: {x.cause} at ({x.x},{x.y},{x.z})' for x in sim.state.legacy[-10:]]
    body+=['','Historical archives may contain events your character has not yet discovered. Books, witnesses, ruins and exploration can reveal them.']
    return box('HISTORY / DISCOVERED LEGENDS',body,width)

def faction_screen(sim:Simulation,width:int=110)->str:
    known_factions=sim.known_faction_ids();known_people=sim.known_npc_ids()
    body=['KNOWN FACTIONS']
    for f in _known_factions(sim):
        office=next((o for o in sim.state.offices.values() if o.faction_id==f.uid),None)
        holder='unknown ruler'
        if office and office.holder_uid in known_people and office.holder_uid in sim.state.npcs:holder=sim.state.npcs[office.holder_uid].name
        body.append(f'{f.name:<28} ruler {holder}')
        wars=[sim.state.factions[x].name for x in f.at_war if x in known_factions and x in sim.state.factions]
        if wars:body.append('   known wars: '+', '.join(wars))
    cultures=[sim.state.cultures[x] for x in sorted(_known_culture_ids(sim)) if x in sim.state.cultures]
    religions=[sim.state.religions[x] for x in sorted(_known_religion_ids(sim)) if x in sim.state.religions]
    body+=['','KNOWN CULTURES']+([f'{c.name}: values={", ".join(c.values)}; taboo={", ".join(c.taboos)}; craft={c.craft_bias}' for c in cultures] or ['None discovered.'])
    body+=['','KNOWN RELIGIONS']+([f'{r.name}: deity={r.deity}; domains={", ".join(r.domains)}; taboo={r.taboo}; ritual={r.ritual}' for r in religions] or ['None discovered.'])
    return box('SOCIETY / DISCOVERED FACTIONS',body,width)

def magic_screen(sim:Simulation,width:int=110)->str:
    known=[x for x in sim.state.magic_laws.values() if f'knowledge:{x.uid}' in sim.state.player_knowledge]
    body=['DISCOVERED MAGICAL LAWS']
    body += [f'{x.uid}: {x.source}+{x.form}; catalyst={x.catalyst}; stamina={x.stamina_cost}; potency={x.potency}; time={x.time_constraint}; terrain={x.terrain_constraint or "any"}; instability={x.instability}; residue={x.contamination}' for x in known] or ['No laws discovered. Experiment with source + form combinations.']
    body+=['',f'Traditions {len(sim.state.magic_traditions)}   Rituals {len(sim.state.rituals)}   Spells {len(sim.state.spells)}   Contaminated cells {len(sim.state.arcane_contamination)}   Myths {len(sim.state.myths)}']
    if sim.state.rituals:body+=['','RITUALS']+[f'{r.name}: {r.effect}; {r.duration_minutes}m; participants {r.min_participants}; catalysts {r.catalysts}' for r in list(sim.state.rituals.values())[:10]]
    body+=['','Sources: ember tide stone gale bloom shade star blood','Forms: project bind mend reveal ward shape']
    return box('ARCANE KNOWLEDGE',body,width)


def economy_screen(sim:Simulation,width:int=112)->str:
    visited=sim.visited_settlement_ids();towns=[s for s in _known_towns(sim) if s.uid in visited];body=['MARKETS YOU HAVE VISITED']
    if not towns:body.append('None.')
    for town in sorted(towns,key=lambda x:x.name):
        body+=['',town.name]
        prices=sorted(town.prices.items(),key=lambda kv:kv[1],reverse=True)[:8]
        if prices:body.append('  '+', '.join(f'{iid.split(":")[-1].replace("_"," ")} {price}c' for iid,price in prices))
    routes=_known_routes(sim);body+=['','TRADE ROADS YOU HAVE LEARNED']
    if not routes:body.append('None.')
    for route in sorted(routes,key=lambda r:(r.danger,r.distance,r.uid))[:16]:
        a=sim.state.settlements.get(route.origin);b=sim.state.settlements.get(route.destination);risk='safe' if route.danger<25 else 'uncertain' if route.danger<60 else 'dangerous'
        body.append(f'{a.name if a else "?"} ↔ {b.name if b else "?"} — {risk}')
    return box('TRADE',body,width)

def ecology_screen(sim:Simulation,width:int=108)->str:
    p=sim.player_pos;natural=sim.player_skill('naturalism');survival=sim.player_skill('survival');skill=max(natural,survival//2);cx,cy=p.x//256,p.y//256
    body=['WILDLIFE YOU RECOGNIZE']
    known=sim.known_species_ids();local=[c for c in sim.state.cohorts.values() if c.region_x==cx and c.region_y==cy and c.z==(0 if p.z>=0 else p.z) and c.species_id in known]
    if not local:body.append('You have no useful read on the wildlife here.')
    for cohort in sorted(local,key=lambda c:c.species_id):
        spec=sim.registry.species.get(cohort.species_id);name=spec.name if spec else cohort.species_id;report=f'{cx},{cy}:{cohort.species_id}' in sim.state.population_reports
        if skill>=8:
            low=max(0,cohort.count-cohort.count//5-2);high=cohort.count+cohort.count//5+2;estimate=f'roughly {low}-{high} in the surrounding country'
        elif skill>=5 or report:
            estimate='scarce' if cohort.count<8 else 'common' if cohort.count<30 else 'abundant'
        else:
            estimate='signs observed'
        body.append(f'{name:<28} {estimate}')
    body+=['','NEARBY']
    near=sorted((c for c in sim.state.creatures.values() if c.hp>0 and c.z==p.z and abs(c.x-p.x)+abs(c.y-p.y)<=40),key=lambda c:abs(c.x-p.x)+abs(c.y-p.y))[:10]
    if not near:body.append('Nothing obvious nearby.')
    known_creatures=sim.known_creature_ids()
    for c in near:
        spec=sim.registry.species.get(c.species_id);label=c.name if c.uid in known_creatures and c.name else spec.name if spec and c.species_id in known else 'Unknown animal';d=abs(c.x-p.x)+abs(c.y-p.y)
        extra=f' — about {d} tiles away' if survival>=3 else ''
        state=f' — {c.behavior.replace("_"," ")}' if max(sim.player_skill('hunting'),survival)>=3 else ''
        body.append(label+extra+state)
    signs=sim.hunting.nearby_signs(p,10)[:8]
    if signs:
        body+=['','RECENT SIGN']
        for sign in signs:
            d=abs(sign.x-p.x)+abs(sign.y-p.y)
            desc=sim.hunting.describe_sign(sign,sim.player_skill('hunting'),survival,sim.clock.minute,species_known=sign.species_id in known)
            body.append(f'{desc} ({d} tiles)')
    if skill<5:body+=['','Better Naturalism, Survival, Hunting, or information from local hunters can reveal more about abundance and sign.']
    return box('WILDLIFE',body,width)

def knowledge_screen(sim:Simulation,width:int=110)->str:
    body=[f'Player literacy: {sim.state.player_literacy}%','LANGUAGES']+[f'  {lang:<30} {fluency:>3}%' for lang,fluency in sorted(sim.state.player_languages.items())]
    body+=['','PLAYER KNOWLEDGE']+[f'  {x}' for x in sorted(sim.state.player_knowledge)[:32]]
    body+=['','LIBRARIES / SCHOOLS']
    known_towns=sim.known_settlement_ids()
    for lib in sim.state.libraries.values():
        if lib.settlement_id not in known_towns:continue
        town=sim.state.settlements.get(lib.settlement_id);body.append(f'{lib.name:<28} town={town.name if town else "known settlement":<20} books={len(lib.book_uids):>3}/{lib.capacity} condition={lib.condition}')
    for school in sim.state.knowledge_schools.values():
        if school.settlement_id in known_towns:body.append(f'{school.name:<28} focus={school.focus:<20} prestige={school.prestige:<3} members={len(school.member_uids)}')
    body+=['','KNOWN PHYSICAL BOOKS']+[f'{b.title:<36} by {b.author:<20} fact={b.knowledge} owner={b.owner}' for b in _known_books(sim)[:16]]
    return box('KNOWLEDGE / LANGUAGES / INSTITUTIONS',body,width)


def society_screen(sim:Simulation,width:int=112)->str:
    alive=[n for n in _known_npcs(sim) if n.alive]
    jobs=Counter(n.occupation for n in alive);religions=Counter(n.religion_id for n in alive);cultures=Counter(n.culture_id for n in alive)
    body=[f'Discovered named people alive: {len(alive)}   Known graves/tombs: {len(_known_graves(sim))}','', 'OCCUPATIONS: '+', '.join(f'{k}={v}' for k,v in jobs.most_common(12)),'CULTURES: '+', '.join(f'{k}={v}' for k,v in cultures.most_common(8)),'RELIGIONS: '+', '.join(f'{k}={v}' for k,v in religions.most_common(8)),'','NAMED PEOPLE']
    for n in sorted(alive,key=lambda n:(n.settlement_id,n.name))[:22]:
        town=sim.state.settlements.get(n.settlement_id);body.append(f'{n.name:<24} age {n.age:<3} {n.occupation:<12} goal={n.goal:<10} wealth={n.wealth:<4} town={town.name if town else n.settlement_id}')
    body+=['','RELIGIOUS INSTITUTIONS']+[f'{r.name}: influence {r.influence}, priests {len(r.priest_uids)}, doctrine={r.doctrine}' for r in sim.state.religious_institutions.values() if r.settlement_id in sim.known_settlement_ids()]
    return box('PEOPLE / SOCIETY',body,width)


def simulation_screen(sim:Simulation,width:int=112)->str:
    body=['SIMULATION FIDELITY']+sim.lod.describe(sim.player_pos)
    summary=sim.state.last_offline_summary or {}
    body+=['',f'Offline policy: {sim.state.offline_policy.upper()}   Last offline advance: {sim.state.last_offline_minutes} minutes   {summary}',f'Clock minute: {sim.clock.minute}   Turn: {sim.turn}   Chunk cache: {len(sim.world.cache)}/{sim.world.cache.max_chunks}   Dirty terrain tiles: {len(sim.world.dirty_tiles)}','', 'PERSISTENT STATE COUNTS',
           f'Realized macro-regions {len(sim.state.realized_regions)} | Known settlements {len(sim.known_settlement_ids())} | Known NPCs {len(sim.known_npc_ids())} | Cohorts {len(sim.state.cohorts)} | Creatures {len(sim.state.creatures)} | Known routes {len(_known_routes(sim))} | Caravans {len(sim.state.caravans)}',
           f'History {len(sim.state.history)} | Books {len(sim.state.books)} | Artifacts {len(sim.state.artifacts)} | Graves {len(sim.state.graves)} | Dungeons {len(sim.state.dungeon_sites)} | Infections {len(sim.state.infections)}',
           f'Crops {len(sim.state.crops)} | Structures {len(sim.state.structures)} | Roofs {len(sim.state.roofs)} | Fluids {len(sim.state.fluids)} | Fires {len(sim.state.fires)} | Arcane residue {len(sim.state.arcane_contamination)}','',
           'Tier A/B entities receive individual movement/AI. Tier C uses region/cohort state. Tier D uses aggregate boundaries. Tier E is generated only when realized.']
    loaded=getattr(sim,'loaded_mods',[]);mod_hash=getattr(sim,'mod_hash','none')
    body+=['',f'Data mods loaded: {len(loaded)}   hash={mod_hash}']+[f'  {x}' for x in loaded]
    return box('SIMULATION / PERFORMANCE / LOD',body,width)


def settlement_detail_screen(sim:Simulation,settlement_id:str,width:int=112)->str:
    s=sim.state.settlements.get(settlement_id)
    if not s or settlement_id not in sim.known_settlement_ids():return box('SETTLEMENT',['You have not discovered this settlement.'],width)
    fac=sim.state.factions.get(s.faction_id);culture=sim.state.cultures.get(s.culture_id);religion=sim.state.religions.get(s.religion_id)
    if settlement_id not in sim.visited_settlement_ids():
        body=[s.name,'', 'You know this place by report, but have not visited it.',
              'Details of its people, markets and institutions are still unknown.']
        if fac and s.faction_id in sim.known_faction_ids():body.append(f'Affiliation: {fac.name}')
        return box(f'KNOWN PLACE — {s.name}',body,width)
    body=[s.name,f'Faction: {fac.name if fac else "unknown"}',f'Culture: {culture.name if culture else "unknown"} | Religion: {religion.name if religion else "unknown"}','','MARKET']
    for iid,stock in sorted(s.stocks.items(),key=lambda kv:(-s.prices.get(kv[0],0),kv[0]))[:20]:body.append(f'{iid.split(":")[-1].replace("_"," "):<24} available {stock:>5}  price {s.prices.get(iid,0):>4}c')
    body+=['','RECENT PRICE MOVEMENT']
    histories=[]
    for iid,rows in s.market_history.items():
        if not rows:continue
        histories.append((max(int(r[1]) for r in rows[-30:]),iid,rows))
    for _,iid,rows in sorted(histories,reverse=True)[:10]:
        vals=[int(r[1]) for r in rows[-30:]]
        body.append(f'{iid.split(":")[-1].replace("_"," "):<20} {_spark(vals,24,sim.state.ui_unicode):<24} {vals[-1]:>4}c')
    if not histories:body.append('No recent market notes.')
    known_people=[n for n in sim.state.npcs.values() if n.settlement_id==s.uid and n.uid in sim.known_npc_ids() and n.alive]
    if known_people:
        body+=['','PEOPLE YOU KNOW']+[f'{n.name} — {n.occupation}' for n in sorted(known_people,key=lambda n:n.name)[:16]]
    return box(f'SETTLEMENT — {s.name}',body,width)


def npc_detail_screen(sim:Simulation,npc_uid:str,width:int=112)->str:
    n=sim.state.npcs.get(npc_uid)
    if not n or npc_uid not in sim.known_npc_ids():return box('PERSON RECORD',['You have not learned this person’s identity.'],width)
    town=sim.state.settlements.get(n.settlement_id);fac=sim.state.factions.get(n.faction_id);culture=sim.state.cultures.get(n.culture_id);religion=sim.state.religions.get(n.religion_id)
    known_people=sim.known_npc_ids();spouse=sim.state.npcs.get(n.spouse_uid) if n.spouse_uid in known_people else None;home=sim.state.properties.get(n.home_id);work=sim.state.properties.get(n.workplace_id)
    body=[f'{n.name} [{n.uid}]  {"ALIVE" if n.alive else "DECEASED"}',f'Age {n.age} | occupation {n.occupation} | HP {n.hp} | wealth {n.wealth}c',f'Position ({n.x},{n.y},z{n.z}) | settlement {town.name if town else n.settlement_id or "none"}',f'Faction {fac.name if fac else n.faction_id or "none"} | culture {culture.name if culture else n.culture_id or "none"} | religion {religion.name if religion else n.religion_id or "none"}',f'Traits: {", ".join(n.traits) if n.traits else "none"}',f'Needs: hunger {n.hunger} thirst {n.thirst} rest {n.rest} | goal {n.goal} ({n.goal_score})',f'Infections: {len(n.infections)} | immunities: {len(n.immunities)} | disease history: {", ".join(n.disease_history[-6:]) if n.disease_history else "none"}','', 'HOUSEHOLD / WORK',f'Spouse: {spouse.name if spouse else "none"}',f'Parents: {", ".join(sim.state.npcs[x].name for x in n.parents if x in known_people and x in sim.state.npcs) or "unknown / none"}',f'Children: {", ".join(sim.state.npcs[x].name for x in n.children if x in known_people and x in sim.state.npcs) or "unknown / none"}',f'Home: {home.kind+" / "+home.uid if home else n.home_id or "none"}',f'Workplace: {work.kind+" / "+work.uid if work else n.workplace_id or "none"}','', 'LANGUAGE / KNOWLEDGE',f'Literacy: {n.literacy}%']
    body += [f'  {lang}: {pct}%' for lang,pct in sorted(n.language_fluency.items())] or ['  no recorded language fluency']
    body += ['Knowledge: '+(', '.join(n.knowledge[:20]) if n.knowledge else 'none'),'','CURRENT TASKS']
    body += [f'  {t}' for t in n.tasks[:10]] or ['  no queued tasks']
    body += ['','RELATIONSHIPS']
    rels=[]
    for uid,r in n.relationships.items():
        if uid not in known_people:continue
        other=sim.state.npcs.get(uid);score=r.get('affection',0)+r.get('trust',0)+r.get('respect',0)-r.get('fear',0)
        rels.append((score,other.name if other else 'known person',r))
    for score,name,r in sorted(rels,key=lambda x:(-abs(x[0]),x[1]))[:10]:body.append(f'{name:<24} aff {r.get("affection",0):>4} trust {r.get("trust",0):>4} fear {r.get("fear",0):>3} respect {r.get("respect",0):>4} familiarity {r.get("familiarity",0):>3}')
    if not rels:body.append('No strong recorded relationships.')
    body+=['','MEMORIES']
    for m in n.memories[-12:]:body.append(str(m))
    if not n.memories:body.append('No persistent memories.')
    return box(f'PERSON — {n.name}',body,width)


def route_detail_screen(sim:Simulation,route_uid:str,width:int=112)->str:
    r=sim.state.trade_routes.get(route_uid)
    if not r or route_uid not in set(sim.state.discovered_routes):return box('TRADE ROAD',['You have not learned this road.'],width)
    a=sim.state.settlements.get(r.origin);b=sim.state.settlements.get(r.destination)
    known=sim.known_settlement_ids()
    if r.origin not in known or r.destination not in known:return box('TRADE ROAD',['You know a road exists, but not enough to identify both ends.'],width)
    risk='usually quiet' if r.danger<25 else 'uncertain' if r.danger<60 else 'dangerous'
    journey='short' if r.distance<3 else 'several days' if r.distance<8 else 'long'
    body=[f'{a.name if a else "?"} ↔ {b.name if b else "?"}',f'Journey: {journey} | reputation: {risk}']
    visited=sim.visited_settlement_ids()
    if r.origin in visited and r.destination in visited and a and b:
        body+=['','PRICES YOU HAVE SEEN']
        goods=sorted(set(a.prices)|set(b.prices));diffs=[]
        for iid in goods:
            pa=a.prices.get(iid,0);pb=b.prices.get(iid,0);diffs.append((abs(pb-pa),iid,pa,pb))
        for _,iid,pa,pb in sorted(diffs,reverse=True)[:12]:body.append(f'{iid.split(":")[-1].replace("_"," "):<22} {a.name[:16]:<16} {pa:>3}c | {b.name[:16]:<16} {pb:>3}c')
    else:
        body+=['','Visit both ends to compare their markets.']
    return box('TRADE ROAD',body,width)


def faction_detail_screen(sim:Simulation,faction_uid:str,width:int=112)->str:
    f=sim.state.factions.get(faction_uid)
    if not f or faction_uid not in sim.known_faction_ids():return box('FACTION',['You have not learned this faction.'],width)
    culture=sim.state.cultures.get(f.culture_id);office=next((o for o in sim.state.offices.values() if o.faction_id==f.uid),None);holder=sim.state.npcs.get(office.holder_uid) if office and office.holder_uid in sim.known_npc_ids() else None
    towns=[s for s in _known_towns(sim) if s.faction_id==f.uid]
    claims=[c for c in sim.state.claims.values() if c.claimant_id==f.uid and c.active]
    body=[f'{f.name} [{f.uid}]',f'Culture: {culture.name if culture else f.culture_id} | power {f.power} | treasury {f.treasury}c',f'Manpower {f.manpower} | military supply {f.military_supply} | war exhaustion {f.war_exhaustion}',f'Ruler: {holder.name if holder else "vacant"} | office: {office.title if office else "none"} | succession: {office.succession_rule if office else "n/a"}',f'Laws: {f.laws or "none"}','', 'RELATIONS']
    for uid,val in sorted(f.relations.items(),key=lambda kv:kv[1]):
        if uid in sim.known_faction_ids():body.append(f'{sim.state.factions[uid].name if uid in sim.state.factions else "known faction":<28} {val:>4}'+('  WAR' if uid in f.at_war else ''))
    body+=['','SETTLEMENTS']+[f'{s.name:<24} pop {s.population:<5} wealth {s.wealth:>6}c stress {s.food_stress:>3}' for s in sorted(towns,key=lambda s:-s.population)]
    body+=['','ACTIVE CLAIMS']+[f'{c.target_type}:{c.target_id} basis={c.basis} strength={c.strength}' for c in claims] if claims else ['','ACTIVE CLAIMS','None.']
    return box(f'FACTION — {f.name}',body,width)



def disease_detail_screen(sim:Simulation,outbreak_uid:str,width:int=112)->str:
    d=sim.state.diseases.get(outbreak_uid)
    if not d or d.settlement_id not in sim.known_settlement_ids():return box('OUTBREAK RECORD',['You have not learned of this outbreak.'],width)
    ddef=sim.registry.diseases.get(d.disease_id);town=sim.state.settlements.get(d.settlement_id)
    body=[f'{(ddef.name if ddef else d.name or d.disease_id)} [{outbreak_uid}]',f'Settlement: {town.name if town else d.settlement_id or "unknown"} | region ({d.region_x},{d.region_y})',f'Active {d.infected} | recovered {d.recovered} | deaths {d.deaths} | immune estimate {d.immune}',f'Severity {d.severity} | contagiousness {d.contagiousness} | strain {d.strain:+d} | policy {d.policy}',f'First minute {d.first_minute} | last minute {d.last_minute}']
    if ddef:
        body+=['', 'PATHOGEN PROFILE',f'Transmission: {", ".join(ddef.transmissions)}',f'Incubation {ddef.incubation_hours}h | illness {ddef.illness_hours}h | immunity {ddef.immunity_days}d | environmental survival {ddef.environmental_survival_hours}h',f'Mortality baseline {ddef.mortality_permille/10:.1f}% | symptoms: {", ".join(ddef.symptoms)} | seasonal bias: {", ".join(ddef.season_bias) or "none"}']
    if town:
        body+=['','PUBLIC HEALTH',f'Policy {town.health_policy} | quarantine {town.quarantine_level}/100 | sanitation {town.sanitation}/100 | healer capacity {town.healer_capacity}',f'Medicine: tonic {town.stocks.get("core:herbal_tonic",0)} | soap {town.stocks.get("core:soap",0)} | wealth {town.wealth}c']
    if d.trend:
        body+=['','CASE TREND',_spark([int(x[1]) for x in d.trend],48,sim.state.ui_unicode),f'Oldest sample minute {d.trend[0][0]} | newest {d.trend[-1][0]}']
    named=[]
    for inf in sim.state.infections.values():
        if inf.disease_id!=d.disease_id or inf.host_type!='npc' or inf.stage=='recovered':continue
        npc=sim.state.npcs.get(inf.host_id)
        if npc and npc.settlement_id==d.settlement_id and npc.uid in sim.known_npc_ids():named.append((npc,inf))
    body+=['','NAMED CASES']
    body += [f'{npc.name:<24} {inf.stage:<11} sev {inf.severity:<3} treated={inf.treated} source={inf.source}' for npc,inf in named[:18]] or ['No named representative currently carries this infection.']
    return box(f'OUTBREAK — {(ddef.name if ddef else d.disease_id)}',body,width)

def artifact_detail_screen(sim:Simulation,artifact_uid:str,width:int=112)->str:
    a=sim.state.artifacts.get(artifact_uid)
    if not a or artifact_uid not in {x.uid for x in _known_artifacts(sim)}:return box('ARTIFACT',['You have not discovered this artifact.'],width)
    body=[f'{a.name} [{a.uid}]',f'Base item {a.base_item} | material {a.material} | quality {a.quality} | condition {a.condition}%',f'Creator {a.creator} | current owner {a.owner} | created minute {a.created_minute}',f'Temperature {a.temperature_c}C | contamination {a.contamination}','', 'COMPONENTS']
    body += [f'{slot:<16} {meta}' for slot,meta in a.components.items()] or ['No component graph recorded.']
    body+=['','PROVENANCE']
    for row in a.provenance[-20:]:body.append(str(row))
    if not a.provenance:body+=['No ownership provenance recorded.']
    body+=['','HISTORY']+[f'  {x}' for x in a.history[-20:]]
    return box(f'ARTIFACT — {a.name}',body,width)


def book_detail_screen(sim:Simulation,book_uid:str,width:int=112)->str:
    b=sim.state.books.get(book_uid)
    if not b or book_uid not in {x.uid for x in _known_books(sim)}:return box('BOOK',['You have not discovered this book.'],width)
    culture=sim.state.cultures.get(b.culture_id)
    body=[f'"{b.title}" [{b.uid}]',f'Author: {b.author} | owner/location: {b.owner}',f'Knowledge: {b.knowledge}',f'Culture: {culture.name if culture else b.culture_id} | language: {b.language_id or b.culture_id}',f'Condition {b.condition}% | created minute {b.created_minute}',f'Copied from: {b.copied_from_uid or "original manuscript"}']
    return box(f'BOOK — {b.title}',body,width)


def dungeon_detail_screen(sim:Simulation,site_uid:str,width:int=112)->str:
    d=sim.state.dungeon_sites.get(site_uid)
    if not d or site_uid not in sim.known_site_ids():return box('HISTORICAL SITE',['You have not discovered this site.'],width)
    info=sim.world.generator.sites.info(__import__('worldseed.core.coords',fromlist=['ChunkKey']).ChunkKey(d.chunk_x,d.chunk_y,d.z))
    alive=[sim.state.creatures[u] for u in d.occupant_uids if u in sim.state.creatures and sim.state.creatures[u].hp>0]
    body=[f'{d.name} [{d.uid}]',f'Chunk ({d.chunk_x},{d.chunk_y},z{d.z}) | activated minute {d.activated_minute}',f'Generated type: {info.site_type if info else "unknown"} | builder: {info.builder if info else "unknown"} | age: {info.age_years if info else "?"} years | danger: {info.danger if info else "?"}',f'Controller: {d.current_controller or "unclaimed"} | cleared={d.cleared} | loot seeded={d.loot_seeded}',f'Locks open {sum(d.locks.values())}/{len(d.locks)} | traps sprung {sum(d.traps.values())}/{len(d.traps)} | living occupants {len(alive)}','','OCCUPATION TIMELINE']
    body += [str(x) for x in d.occupation_history[-16:]] or ['No recorded occupation changes.']
    if alive:
        known_species=sim.known_species_ids();known_creatures=sim.known_creature_ids()
        def occ_label(c):
            if c.uid in known_creatures and c.name:return c.name
            spec=sim.registry.species.get(c.species_id)
            return spec.name if spec and c.species_id in known_species else 'Unknown creature'
        body+=['','OCCUPANTS']+[f'{occ_label(c)}: hp {c.hp}, kills {c.kills}, notable {c.notable}' for c in alive]
    return box(f'SITE — {d.name}',body,width)


def event_detail_screen(sim:Simulation,event_uid:str,width:int=112)->str:
    e=next((x for x in sim.state.history if x.uid==event_uid),None)
    if not e or event_uid not in {x.uid for x in _known_events(sim)}:return box('HISTORICAL EVENT',['You have not learned this event, or it is archived.'],width)
    year=e.minute//(1440*120)+1;day=(e.minute//1440)%120+1
    body=[f'{e.event_type.upper()}  [{e.uid}]',f'Year {year}, day {day}, minute {e.minute} | salience {e.salience}',f'Region ({e.region_x},{e.region_y})','',e.summary,'','SUBJECTS']
    for uid in e.subjects:
        label=uid
        if uid in sim.known_npc_ids() and uid in sim.state.npcs:label=f'{uid} — {sim.state.npcs[uid].name}'
        elif uid in sim.known_settlement_ids() and uid in sim.state.settlements:label=f'{uid} — {sim.state.settlements[uid].name}'
        elif uid in sim.known_faction_ids() and uid in sim.state.factions:label=f'{uid} — {sim.state.factions[uid].name}'
        elif uid in {x.uid for x in _known_artifacts(sim)} and uid in sim.state.artifacts:label=f'{uid} — {sim.state.artifacts[uid].name}'
        else:label='unknown subject'
        body.append(label)
    body+=['','CAUSES']+[f'  {uid}' for uid in e.causes]
    if not e.causes:body.append('  no explicit causal references')
    return box('HISTORICAL EVENT RECORD',body,width)


def grave_detail_screen(sim:Simulation,grave_uid:str,width:int=112)->str:
    g=sim.state.graves.get(grave_uid)
    if not g or grave_uid not in {x.uid for x in _known_graves(sim)}:return box('GRAVE',['You have not discovered this grave.'],width)
    person=sim.state.npcs.get(g.person_uid)
    body=[f'{g.grave_type.title()} of {g.person_name} [{g.uid}]',f'Location ({g.x},{g.y},z{g.z}) | death minute {g.death_minute}',f'Linked person record: {person.uid if person else g.person_uid}',f'Epitaph: {g.epitaph or "none"}']
    if person:body += ['',f'Occupation: {person.occupation} | age {person.age} | culture {person.culture_id} | religion {person.religion_id}',f'Children: {", ".join(person.children) or "none"}']
    return box(f'{g.grave_type.upper()} — {g.person_name}',body,width)


def alerts_screen(sim:Simulation,width:int=112)->str:
    from worldseed.ui.alerts import world_alerts
    alerts=world_alerts(sim)
    body=[f'Active derived alerts: {len(alerts)}','Severity is calculated from current causal world state; alerts disappear when causes resolve.','']
    if not alerts:body.append('No urgent world or character conditions detected.')
    else:
        for a in alerts:body.append(f'[{a.severity:>3}] {a.category.upper():<11} {a.text}' + (f'  <{a.subject}>' if a.subject else ''))
    return box('ALERTS / WORLD INBOX',body,width)
