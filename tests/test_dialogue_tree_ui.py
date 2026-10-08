import os
os.environ.setdefault('SDL_VIDEODRIVER','dummy')
os.environ.setdefault('SDL_AUDIODRIVER','dummy')

import unittest

from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.ui.widgets import MenuRow


@unittest.skipUnless(PygameTerminal.available(),'requires pygame-ce')
class DialogueTreeUITests(unittest.TestCase):
    def setUp(self):
        self.term=PygameTerminal(1280,800)
        self.term.enter();self.term.pg.event.clear()
        self.addCleanup(self.term.restore)

    def render(self,data,rows=None):
        self.term.present_feature_menu('npc_dialogue','Eda',rows or [MenuRow('water','Ask about water')],0,data=data)

    def topic_targets(self):
        return [(rect,token) for rect,token in self.term._pointer_targets if token.startswith('UI_ACTION:topic:')]

    def test_wrapped_link_fragments_dispatch_the_same_topic_after_resize(self):
        data={'speaker':'Eda','role':'Healer','topic_label':'Shelter',
              'spans':[{'text':'Come in from the rain. Ask about ','topic':''},
                       {'text':'VeryLongUnspacedShelterName'*8,'topic':'shelter'}]}
        for width,height in ((900,620),(640,440)):
            self.term._floating_panels['npc_dialogue']={'x':12,'y':12,'w':width,'h':height}
            self.render(data)
            targets=self.topic_targets()
            self.assertGreater(len(targets),1)
            for rect,token in targets:
                self.assertTrue(self.term._dialogue_text_rect.contains(rect))
                self.assertTrue(self.term.screen.get_rect().contains(rect))
                self.assertEqual(self.term._hit_token(rect.center),token)
            self.term.pg.event.clear()
            self.term.pg.event.post(self.term.pg.event.Event(self.term.pg.MOUSEBUTTONDOWN,button=1,pos=targets[0][0].center))
            self.assertEqual(self.term.read_key(),'UI_ACTION:topic:shelter')

    def test_unseen_topics_have_no_pointer_targets_and_reappear_on_their_page(self):
        data={'speaker':'Eda','spans':[{'text':'A full account of the road. '*120+'\n\n'},
                                     {'text':'flooded bridge','topic':'bridge'}]}
        self.render(data)
        self.assertFalse(self.topic_targets())
        pages=data['transcript_pages'];self.assertGreater(pages,1)
        seen=False
        for page in range(pages):
            data['transcript_page']=page;self.render(data)
            seen=seen or bool(self.topic_targets())
            self.assertTrue(all(self.term._dialogue_text_rect.contains(rect) for rect,_ in self.topic_targets()))
        self.assertTrue(seen)
        data['transcript_page']=0;self.render(data)
        self.assertFalse(self.topic_targets())

    def test_action_reply_keeps_linked_prose_and_page_counter_is_clamped(self):
        data={'speaker':'Eda','spans':[{'text':'Clean water','topic':'water'},
                                     {'text':' matters.\n\nRest here for a moment.'}],
              'response':'Thank you for the gift.'}
        self.render(data)
        self.assertIn('UI_ACTION:topic:water',{token for _,token in self.topic_targets()})
        visible=''.join(fragment['text'] for line in self.term._dialogue_visible_lines for fragment in line)
        self.assertIn('Thank you for the gift.',visible)
        data['transcript_page']=999999;self.render(data)
        self.assertEqual(data['transcript_page'],data['transcript_pages']-1)
        self.assertNotIn('UI_ACTION:transcript_next',{token for _,token in self.term._pointer_targets})

    def test_keyboard_topic_focus_reveals_words_on_another_page(self):
        data={'speaker':'Eda','spans':[{'text':'The road carries a long history. '*150},
                                     {'text':'bridge','topic':'bridge'}]}
        self.render(data);self.assertFalse(self.topic_targets())
        data['focused_topic']='bridge';self.render(data)
        self.assertGreater(data['transcript_page'],0)
        self.assertIn('UI_ACTION:topic:bridge',{token for _,token in self.topic_targets()})
        # An unchanged focus does not override explicit transcript navigation.
        data['transcript_page']=0;self.render(data)
        self.assertEqual(data['transcript_page'],0)

    def test_parent_path_dispatches_original_depth_and_all_keyboard_rows_fit(self):
        self.term._floating_panels['npc_dialogue']={'x':12,'y':12,'w':640,'h':440}
        count=self.term.menu_page_size('npc_dialogue')
        rows=[MenuRow(str(index),'Ask about topic '+str(index)) for index in range(count)]
        data={'speaker':'Eda','path':[{'index':index,'label':'Long parent topic '+str(index),'topic':str(index)} for index in range(12)],
              'thread':[{'label':'Earlier question','text':'A remembered answer.'}],
              'topic_label':'Latest question','opening':'Choose a word to follow.'}
        self.term.present_feature_menu('npc_dialogue','Eda',rows,0,total=20,data=data)
        tokens={token for _,token in self.term._pointer_targets}
        self.assertTrue(all(f'UI_SELECT:{index}' in tokens for index in range(count)))
        self.assertIn('UI_ACTION:path:0',tokens)
        self.assertIn('UI_ACTION:inspect',tokens);self.assertIn('PGDN',tokens)
        self.assertNotIn('UI_ACTION:path:11',tokens)

    def test_rich_wrapping_preserves_paragraphs_and_complete_unspaced_words(self):
        long_name='Morrow'*40
        spans=[{'text':'First paragraph.\n\n'+long_name,'topic':'history'}]
        lines=self.term._dialogue_rich_lines(spans,self.term.font,165)
        self.assertIn([],lines)
        recovered=''.join(fragment['text'] for line in lines for fragment in line)
        self.assertIn(long_name,recovered)
        for line in lines:
            self.assertLessEqual(sum(self.term.font.size(fragment['text'])[0] for fragment in line),165)
            self.assertTrue(all(fragment['topic']=='history' for fragment in line if fragment['text'].strip()))

    def test_hovering_and_leaving_a_keyword_only_requests_redraw(self):
        data={'speaker':'Eda','spans':[{'text':'water','topic':'water'}]}
        self.render(data);rect,_=self.topic_targets()[0]
        self.term.pg.event.clear()
        self.term.pg.event.post(self.term.pg.event.Event(self.term.pg.MOUSEMOTION,pos=rect.center,rel=(0,0),buttons=(0,0,0)))
        self.assertEqual(self.term.read_key(),'UI_REDRAW')
        self.render(data)
        self.term.pg.event.clear()
        self.term.pg.event.post(self.term.pg.event.Event(self.term.pg.MOUSEMOTION,pos=(1,1),rel=(0,0),buttons=(0,0,0)))
        self.assertEqual(self.term.read_key(),'UI_REDRAW')


if __name__=='__main__':
    unittest.main()
