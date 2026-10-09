"""Headless, observational previews of paused conversation and profile UI.

Run ``python tools/preview_dev61_conversations.py`` from the repository.
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

from tools.preview_dev60_dialogue import fixture
from worldseed.app import _npc_portrait, _npc_profile_data
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.entities.components import Inventory
from worldseed.systems.dialogue import DialogueSystem
from worldseed.systems.dialogue_context import build_dialogue_facts
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.ui.widgets import MenuRow


def capture_dialogue(term,scenes,portrait,path,geometry):
    scene=scenes[-1]
    term._floating_panels['npc_dialogue']=dict(geometry)
    capacity=term.menu_page_size('npc_dialogue')
    rows=[MenuRow(option.key,option.label) for option in scene.options if option.action!='inspect']
    data={'speaker':scene.speaker,'role':scene.role,'opening':scene.opening,
          'spans':[{'text':span.text,'topic':span.topic} for span in scene.spans],
          'context':scene.context,'relationship':dict(scene.relationship),'topic':scene.topic,
          'topic_label':scene.topic_label,'portrait':portrait,'time_paused':True,
          'path':[{'index':index,'label':ancestor.topic_label,'topic':ancestor.topic}
                  for index,ancestor in enumerate(scenes)],
          'thread':[{'topic':ancestor.topic,'label':ancestor.topic_label,'text':ancestor.opening}
                    for ancestor in scenes[:-1]]}
    term.present_feature_menu('npc_dialogue',scene.speaker,rows[:capacity],0,total=len(rows),data=data)
    rect=term.pg.Rect(geometry['x'],geometry['y'],geometry['w'],geometry['h'])
    term.pg.image.save(term.screen.subsurface(rect),str(path))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts')
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    ctx,npc,vitals=fixture();sim=ctx.sim
    npc.sex='male'
    sim.registry=ContentRegistry.load(DATA_DIR)
    sim.known_npc_ids=lambda:set(sim.state.introduced_npcs)
    sim.known_settlement_ids=lambda:set(sim.state.settlements)
    sim.player_skill=lambda key:int(sim.state.player_skills.get(key,0))
    sim.settlement_physicalization=SimpleNamespace(structure_by_id=lambda _:None)
    before=sim.state.to_dict();inventory_before=dict(ctx.entities.get(1,Inventory).items)
    portrait=_npc_portrait(sim,npc)
    dialogue=DialogueSystem(sim.state,sim.seed);facts=build_dialogue_facts(ctx,npc)
    topics=('root','area','area.roads','area.roads.crossings','area.roads.crossings.flood')
    scenes=[dialogue.scene(npc,sim.clock.minute,vitals,known=True,topic=topic,introduced=True,facts=facts)
            for topic in topics]
    if any(scene.topic!=topic for scene,topic in zip(scenes,topics)):
        raise RuntimeError('A required preview topic is unavailable.')
    paths=[args.output/'dev61-conversation.png',args.output/'dev61-conversation-narrow.png',
           args.output/'dev61-npc-profile.png']
    term=PygameTerminal(1280,800);term.enter()
    try:
        capture_dialogue(term,scenes[:1],portrait,paths[0],{'x':48,'y':40,'w':1184,'h':720})
        capture_dialogue(term,scenes,portrait,paths[1],{'x':24,'y':24,'w':640,'h':440})
        data=_npc_profile_data(sim,npc,'overview')
        if data['portrait']!=portrait:raise AssertionError('Chat/profile identities differ.')
        geometry={'x':100,'y':80,'w':1000,'h':620}
        term._floating_panels['npc_profile']=dict(geometry)
        rows=[MenuRow(tab,tab.title()) for tab in data['tabs']]
        selected=next(index for index,row in enumerate(rows) if row.key=='overview')
        term.present_feature_menu('npc_profile',npc.name,rows,selected,data=data)
        rect=term.pg.Rect(geometry['x'],geometry['y'],geometry['w'],geometry['h'])
        term.pg.image.save(term.screen.subsurface(rect),str(paths[2]))
    finally:term.restore()
    if sim.state.to_dict()!=before or ctx.entities.get(1,Inventory).items!=inventory_before:
        raise AssertionError('Preview changed authoritative state.')
    for path in paths:print(path.resolve())


if __name__=='__main__':main()
