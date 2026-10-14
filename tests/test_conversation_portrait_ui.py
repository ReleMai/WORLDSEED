"""Conversation identity remains compact, stable and discovery-safe."""
import os
os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')

import unittest

from worldseed.presentation.portraits import portrait_spec
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.ui.widgets import MenuRow


class RecordingFont:
    def __init__(self,font,rendered):
        self.font=font;self.rendered=rendered

    def render(self,text,*args,**kwargs):
        self.rendered.append(str(text))
        return self.font.render(text,*args,**kwargs)

    def __getattr__(self,name):
        return getattr(self.font,name)


@unittest.skipUnless(PygameTerminal.available(),'requires pygame-ce')
class ConversationPortraitUITests(unittest.TestCase):
    def setUp(self):
        self.term=PygameTerminal(1280,800)
        self.term.enter();self.term.pg.event.clear()
        self.addCleanup(self.term.restore)
        self.rendered=[]
        for name in ('font','small_font','title_font'):
            setattr(self.term,name,RecordingFont(getattr(self.term,name),self.rendered))
        self.portrait=portrait_spec(b'conversation-ui','npc:eda','female',35)

    def dialogue(self,**changes):
        data={'speaker':'Eda','role':'Healer','portrait':self.portrait,
              'time_paused':True,'context':('Evening','Healer'),
              'relationship':{'trust':12,'familiarity':24},
              'spans':[{'text':'Ask about the ','topic':''},{'text':'river','topic':'river'}]}
        data.update(changes)
        self.term.present_feature_menu('npc_dialogue','Private fallback name',[
            MenuRow('river','Ask about the river'),MenuRow('goodbye','Goodbye'),
        ],0,data=data)
        return data

    def profile(self,name='Eda'):
        data={'portrait':self.portrait,'active_tab':'overview',
              'summary':{'name':name,'age':35,'occupation':'Healer','settlement':'Millford','activity':'Idle'},
              'tabs':{'overview':[('Home','Millford')]}}
        self.term.present_feature_menu('npc_profile','Private fallback name',[
            MenuRow('overview','Overview'),
        ],0,data=data)

    def portrait_pixels(self):
        rect=self.term._npc_portrait_rect
        self.assertTrue(self.term.screen.get_rect().contains(rect))
        return self.term.pg.image.tobytes(self.term.screen.subsurface(rect),'RGBA')

    def test_single_character_name_single_inspect_control_and_visible_pause(self):
        self.dialogue()
        self.assertEqual(self.rendered.count('Eda'),1)
        self.assertEqual(self.rendered.count('INSPECT'),1)
        self.assertIn('TIME PAUSED',self.rendered)
        self.assertEqual(sum(token=='UI_ACTION:inspect' for _,token in self.term._pointer_targets),1)
        self.assertNotIn('Private fallback name',self.rendered)
        self.rendered.clear();self.profile()
        self.assertEqual(self.rendered.count('Eda'),1)
        self.assertNotIn('Private fallback name',self.rendered)

    def test_portrait_pixels_match_profile_nested_topics_and_resize(self):
        self.dialogue();expected=self.portrait_pixels()
        self.profile();self.assertEqual(expected,self.portrait_pixels())
        for width,height in ((640,440),(900,620)):
            self.term._floating_panels['npc_dialogue']={'x':12,'y':12,'w':width,'h':height}
            self.dialogue(topic_label='Flooded bridge',
                          thread=[{'label':'Earlier topic','text':'An earlier answer.'}])
            self.assertEqual(expected,self.portrait_pixels())

    def test_narrow_portrait_layout_keeps_all_paged_replies_and_keywords_clickable(self):
        for width,height in ((640,440),(900,620)):
            self.term._floating_panels['npc_dialogue']={'x':12,'y':12,'w':width,'h':height}
            count=self.term.menu_page_size('npc_dialogue')
            rows=[MenuRow(str(index),'Ask about topic '+str(index)) for index in range(count)]
            data={'speaker':'Eda','portrait':self.portrait,'time_paused':True,
                  'spans':[{'text':'river','topic':'river'}]}
            self.term.present_feature_menu('npc_dialogue','Eda',rows,0,total=count+1,data=data)
            tokens={token for _,token in self.term._pointer_targets}
            self.assertTrue(all(f'UI_SELECT:{index}' in tokens for index in range(count)))
            self.assertIn('PGDN',tokens)
            linked=[rect for rect,token in self.term._pointer_targets if token=='UI_ACTION:topic:river']
            self.assertTrue(linked)
            for rect in linked:
                self.assertTrue(self.term._dialogue_text_rect.contains(rect))
                self.assertTrue(self.term.screen.get_rect().contains(rect))
            self.portrait_pixels()

    def test_unknown_person_uses_visible_stranger_identity_in_both_panels(self):
        self.dialogue(speaker='Stranger',role='Unknown person',relationship={})
        self.assertEqual(self.rendered.count('Stranger'),1)
        self.assertNotIn('Eda',self.rendered)
        self.assertNotIn('Private fallback name',self.rendered)
        expected=self.portrait_pixels()
        self.rendered.clear();self.profile(name='Stranger')
        self.assertEqual(self.rendered.count('Stranger'),1)
        self.assertNotIn('Eda',self.rendered)
        self.assertNotIn('Private fallback name',self.rendered)
        self.assertEqual(expected,self.portrait_pixels())

    def test_maximized_portrait_popup_uses_supported_composer_size(self):
        """The old 520px popup crashed a 1920px Windows session (limit 512)."""
        from unittest.mock import patch
        self.dialogue()
        pg=self.term.pg
        self.term.screen=pg.display.set_mode((1920,1080))
        with patch.object(pg.event,'wait',return_value=pg.event.Event(pg.KEYDOWN,key=pg.K_ESCAPE)):
            self.term._show_portrait_popup()
        self.assertIn((self.portrait,520),self.term._portrait_composer._surfaces)
        self.assertEqual(self.term._portrait_composer._surfaces[(self.portrait,520)].get_size(),(520,520))

    def test_profile_overview_does_not_repeat_identity_cards_or_traits(self):
        overview=[('Age','35'),('Occupation','Healer'),('Settlement','Millford'),
                  ('Current activity','Idle'),('Traits','Patient'),
                  ('Scheduled now','Morning work'),('00:00–05:30','Sleep'),
                  ('05:30–11:00','Gather')]
        data={'portrait':self.portrait,'active_tab':'overview',
              'summary':{'name':'Eda','age':35,'occupation':'Healer','settlement':'Millford',
                         'activity':'Idle','traits':['Patient']},
              'tabs':{'overview':overview}}
        self.term.present_feature_menu('npc_profile','Eda',[MenuRow('overview','Overview')],0,data=data)
        for value in ('35','Healer','Millford','Idle','Patient'):
            self.assertEqual(self.rendered.count(value),1,value)
        self.assertNotIn('Traits: Patient',self.rendered)
        self.assertIn('Morning work',self.rendered)
        self.assertIn('00:00–05:30',self.rendered)
        self.assertIn('05:30–11:00',self.rendered)
        self.assertEqual(data['tabs']['overview'],overview)


if __name__=='__main__':
    unittest.main()
