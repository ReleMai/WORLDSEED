"""Headless previews of actual deterministic dialogue scenes and nested UI.

Run ``python tools/preview_dev60_dialogue.py`` from the repository. The fixture
uses carried copper, real settlement/NPC fields and an observational weather
query; the preview never starts or advances the simulation.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from types import SimpleNamespace

os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')
os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT','1')

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))

from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Position, Vitals
from worldseed.entities.store import EntityStore
from worldseed.systems.dialogue import DialogueSystem
from worldseed.systems.dialogue_context import build_dialogue_facts
from worldseed.systems.state import LivingWorldState, NPCState, SettlementState
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.ui.widgets import MenuRow


def fixture():
    minute=13*60
    state=LivingWorldState(clock_minute=minute,player_name='Mara')
    town=SettlementState('settlement:preview','Millford',0,0,10,20,80,'','','',
                         food_stress=62,unemployment=18,housing_capacity=90,
                         stocks={'core:grain':6,'core:wood':32})
    npc=NPCState('npc:preview:farmer','Tomas Morrow',38,'farmer',['patient'],10,20,0,town.uid,'',
                 skills={'farming':6},routine_phase='work',needs={'security':44,'social':28})
    npc.relationships['player']={'trust':14,'affection':9,'familiarity':36}
    state.settlements[town.uid]=town;state.npcs[npc.uid]=npc
    state.discovered_npcs.append(npc.uid);state.introduced_npcs.append(npc.uid)
    entities=EntityStore();entities.spawn(preferred_id=1)
    entities.add(1,Position(WorldPos(10,20,0)))
    entities.add(1,Inventory({'core:copper_coin':500}))
    vitals=Vitals(hp=100,hunger=20,thirst=15)
    entities.add(1,vitals)
    weather={'kind':'storm','rain':8,'wetness':85,'wind':60,'storm_intensity':80,'visibility':55}
    sim=SimpleNamespace(state=state,seed=b'dev60-dialogue-preview',clock=SimpleNamespace(minute=minute),
                        environment=SimpleNamespace(weather=SimpleNamespace(at=lambda *_:dict(weather))),
                        npcs=SimpleNamespace(nearby_npcs=lambda *_args,**_kwargs:(npc,)),
                        entities=entities,player_id=1)
    ctx=SimpleNamespace(sim=sim,entities=entities,player_id=1)
    return ctx,npc,vitals


def capture(term,scenes,output,panel,*,crop=False):
    scene=scenes[-1]
    term._floating_panels['npc_dialogue']=dict(panel)
    capacity=term.menu_page_size('npc_dialogue')
    rows=[MenuRow(option.key,option.label) for option in scene.options]
    data={'speaker':scene.speaker,'role':scene.role,'opening':scene.opening,
          'spans':[{'text':span.text,'topic':span.topic} for span in scene.spans],
          'context':scene.context,'relationship':dict(scene.relationship),'topic':scene.topic,
          'topic_label':scene.topic_label,'transcript_page':0,
          'path':[{'index':index,'label':ancestor.topic_label,'topic':ancestor.topic}
                  for index,ancestor in enumerate(scenes)],
          'thread':[{'topic':ancestor.topic,'label':ancestor.topic_label,'text':ancestor.opening}
                    for ancestor in scenes[:-1]]}
    term.present_feature_menu('npc_dialogue',scene.speaker,rows[:capacity],0,
                              total=len(rows),data=data)
    surface=term.screen
    if crop:
        geometry=term._floating_panels['npc_dialogue']
        surface=surface.subsurface(term.pg.Rect(geometry['x'],geometry['y'],geometry['w'],geometry['h']))
    term.pg.image.save(surface,str(output))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts',help='directory for the two PNG previews')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    ctx,npc,vitals=fixture();before=ctx.sim.state.to_dict()
    inventory_before=dict(ctx.entities.get(1,Inventory).items)
    facts=build_dialogue_facts(ctx,npc)
    dialogue=DialogueSystem(ctx.sim.state,ctx.sim.seed)
    topics=('root','area','area.roads','area.roads.crossings','area.roads.crossings.flood')
    scenes=[dialogue.scene(npc,ctx.sim.clock.minute,vitals,known=True,topic=topic,
                           introduced=True,facts=facts) for topic in topics]
    if any(scene.topic!=topic for scene,topic in zip(scenes,topics)):
        raise RuntimeError('The authored dialogue tree is missing a required preview topic.')
    term=PygameTerminal(1280,800);term.enter()
    paths=[args.output/'dev60-dialogue-root.png',args.output/'dev60-dialogue-deep.png']
    try:
        capture(term,scenes[:1],paths[0],{'x':48,'y':40,'w':1184,'h':720})
        capture(term,scenes,paths[1],{'x':24,'y':24,'w':640,'h':440},crop=True)
    finally:
        term.restore()
    if ctx.sim.state.to_dict()!=before or ctx.entities.get(1,Inventory).items!=inventory_before:
        raise AssertionError('Dialogue preview changed authoritative fixture state.')
    for path in paths:print(path.resolve())


if __name__=='__main__':
    main()
