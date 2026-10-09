import os
os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')

import unittest
from types import SimpleNamespace

from worldseed.systems.dialogue import DialogueSystem
from worldseed.systems.state import LivingWorldState, NPCState, SettlementState
from worldseed.ui.router import classify_key
from worldseed.ui.widgets import MenuRow
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.app import _learn_area_from_npc


class DialogueMovementPhaseTests(unittest.TestCase):
    def fixture(self):
        state=LivingWorldState()
        town=SettlementState('settlement:test','Millford',0,0,0,0,80,'culture:test','religion:test','faction:test')
        state.settlements[town.uid]=town
        npc=NPCState('npc:healer','Eda',35,'healer',['patient'],0,0,0,town.uid,town.faction_id)
        state.npcs[npc.uid]=npc
        state.discovered_npcs=[npc.uid];state.introduced_npcs=[npc.uid]
        return state,town,npc,DialogueSystem(state,b'dialogue-test')

    def test_dialogue_reacts_to_health_time_and_crime(self):
        state,town,npc,dialogue=self.fixture()
        healthy=SimpleNamespace(hp=100,max_hp=100,pain=0,blood=100,hunger=10,thirst=10)
        hurt=SimpleNamespace(hp=35,max_hp=100,pain=60,blood=55,hunger=10,thirst=10)
        normal=dialogue.scene(npc,12*60,healthy,True)
        injured=dialogue.scene(npc,12*60,hurt,True)
        self.assertNotIn('Player visibly hurt',normal.context)
        self.assertIn('Player visibly hurt',injured.context)
        self.assertIn('health',{o.key for o in injured.options})
        state.player_crime_heat[town.uid]=50
        wanted=dialogue.scene(npc,23*60,hurt,True)
        self.assertIn('Wanted / watched',wanted.context)
        self.assertIn('crime',{o.key for o in wanted.options})
        self.assertIn('Night',wanted.context)
        self.assertTrue({'area','personal','relations','trade','inspect','attack'}.issubset({o.key for o in wanted.options}))
        self.assertEqual(next(o for o in wanted.options if o.key=='area').next_topic,'area')

    def test_dialogue_variants_are_deterministic(self):
        state,town,npc,dialogue=self.fixture()
        vit=SimpleNamespace(hp=100,max_hp=100,pain=0,blood=100,hunger=10,thirst=10)
        a=dialogue.scene(npc,600,vit,True)
        b=dialogue.scene(npc,600,vit,True)
        self.assertEqual(a,b)

    def test_movement_hud_tokens_route_without_shadowing_wasd(self):
        self.assertEqual(classify_key('UI_MOVE:walk').kind,'movement_mode')
        self.assertEqual(classify_key('UI_MOVE:run').value,'run')
        self.assertEqual(classify_key('UI_MOVE:stealth').value,'stealth')
        self.assertEqual(classify_key('w').kind,'move')

    def test_learned_region_intel_round_trips(self):
        state,_,npc,_=self.fixture()
        state.learned_regions['0,0']={'region_x':0,'region_y':0,'source_npc_uid':npc.uid,'resources':['Grain']}
        loaded=LivingWorldState.from_dict(state.to_dict())
        self.assertEqual(loaded.learned_regions['0,0']['source_npc_uid'],npc.uid)
        self.assertEqual(loaded.learned_regions['0,0']['resources'],['Grain'])

    def test_area_knowledge_requires_willingness_and_records_testimony(self):
        state,town,npc,_=self.fixture();town.stocks={'core:grain':40}
        sim=SimpleNamespace(state=state,seed=b'dialogue-test',clock=SimpleNamespace(minute=900))
        ctx=SimpleNamespace(sim=sim,registry=SimpleNamespace(items={'core:grain':SimpleNamespace(name='Grain')}))
        npc.relationships['player']={'trust':-100,'familiarity':0}
        refused=_learn_area_from_npc(ctx,npc)
        self.assertIn('not ready',refused);self.assertFalse(state.learned_regions)
        npc.relationships['player']={'trust':100,'familiarity':100}
        learned=_learn_area_from_npc(ctx,npc)
        self.assertIn('local boundary',learned)
        self.assertEqual(state.learned_regions['0,0']['source_npc_uid'],npc.uid)
        self.assertEqual(state.learned_regions['0,0']['resources'],['Grain'])


@unittest.skipUnless(PygameTerminal.available(),'requires pygame-ce')
class DialoguePanelRenderTests(unittest.TestCase):
    def setUp(self):
        self.term=PygameTerminal(1280,800);self.term.enter();self.term.pg.event.clear()

    def tearDown(self):
        self.term.restore()

    def test_dialogue_panel_has_transcript_choices_and_inspect_button(self):
        rows=[MenuRow('area','Ask about the area'),MenuRow('chat','Just chat'),MenuRow('trade','Trade'),MenuRow('attack','Attack')]
        self.term.present_feature_menu('npc_dialogue','Eda',rows,0,subtitle='Choose a response.',data={
            'speaker':'Eda','role':'Healer','opening':'You look tired.','response':'The road is quiet.',
            'context':('Evening','Healer'),'npc_uid':'npc:eda',
        })
        tokens={token for _,token in self.term._pointer_targets}
        self.assertIn('UI_SELECT:3',tokens)
        self.assertEqual(sum(token=='UI_ACTION:inspect' for _,token in self.term._pointer_targets),1)
        self.assertEqual(self.term._floating_panel_id,'npc_dialogue')


if __name__=='__main__':
    unittest.main()
