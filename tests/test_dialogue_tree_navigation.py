"""Real widget input preserves nested dialogue without changing the world."""
from __future__ import annotations

import copy
import unittest
from types import SimpleNamespace

from worldseed.app import _conversation_menu
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Position, Vitals
from worldseed.entities.store import EntityStore
from worldseed.systems.state import LivingWorldState, NPCState, SettlementState
from worldseed.ui.widgets import visible_len


ROAD_PATH = (
    'root', 'area', 'area.roads', 'area.roads.crossings',
    'area.roads.crossings.flood', 'area.roads.crossings.flood.waterline',
)


class RecordingDialogueTerm:
    """A graphical-style backend using the production widget key loop."""

    mouse_ui = True

    def __init__(self, keys, capacity=3):
        self.keys = iter(keys)
        self.capacity = capacity
        self.frames = []

    def size(self):
        return 60, 24

    def menu_page_size(self, presentation):
        return self.capacity

    def present_feature_menu(self, presentation, title, rows, selected, **kwargs):
        self.frames.append({
            'presentation': presentation, 'title': title,
            'rows': [row.key for row in rows], 'selected': selected,
            **copy.deepcopy(kwargs),
        })

    def read_key(self):
        try:
            key = next(self.keys)
        except StopIteration:
            raise AssertionError('Dialogue requested input after the scripted exit') from None
        return key(self.frames[-1]) if callable(key) else key


class PlainDialogueTerm:
    """A small terminal that pages until the final transcript marker appears."""

    def __init__(self, cols, rows):
        self.geometry = (cols, rows)
        self.frames = []
        self.reached_end = False
        self.returned_previous = False

    def size(self):
        return self.geometry

    def present(self, text):
        self.frames.append(text)

    def read_key(self):
        if len(self.frames) > 150:
            raise AssertionError('Terminal transcript failed to reach its final page')
        if not self.reached_end:
            self.reached_end = 'ENDTRANSCRIPT' in self.frames[-1]
            return '[' if self.reached_end else ']'
        self.returned_previous = True
        return 'ESC'


class DialogueTreeNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    def fixture(self, *, introduced=True):
        state = LivingWorldState(player_name='Mara', clock_minute=600)
        town = SettlementState(
            'settlement:test', 'Mistwick', 0, 0, 100, 200, 80,
            'culture:test', 'religion:test', 'faction:test',
            stocks={'core:wood': 90}, food_stress=58, unemployment=39,
            border_pressure=40, patrol_pressure=60,
            resource_specializations=['farming', 'logging'],
            crop_ids=['core:wheat'], livestock_species_ids=['core:pig'],
        )
        npc = NPCState(
            'npc:test', 'Tomas Mere', 38, 'farmer', ['suspicious'],
            101, 200, 0, town.uid, town.faction_id,
            home_id='private:home', workplace_id='private:work',
            backstory={'formative_event': 'secret family history'},
            skills={'farming': 7}, needs={'rest': 65}, wants=['safe harvest'],
        )
        npc.relationships['player'] = {'trust': 37, 'affection': 25, 'familiarity': 80}
        state.settlements[town.uid] = town
        state.npcs[npc.uid] = npc
        state.discovered_npcs = [npc.uid]
        if introduced:
            state.introduced_npcs = [npc.uid]
        entities = EntityStore()
        entities.spawn(preferred_id=1)
        entities.add(1, Position(WorldPos(100, 200)))
        entities.add(1, Inventory({'core:wood': 2}))
        entities.add(1, Vitals())

        def unexpected_command(*args, **kwargs):
            raise AssertionError('Browsing dialogue invoked a simulation command')

        # Missing world/environment/knowledge adapters are intentional: chat
        # must remain usable in older saves and the minimal terminal backend.
        sim = SimpleNamespace(
            state=state, registry=self.registry, seed=b'dialogue-navigation',
            clock=SimpleNamespace(minute=600), entities=entities,
            player_pos=WorldPos(100, 200), log=[],
            known_npc_ids=lambda: set(state.discovered_npcs),
            execute=unexpected_command, begin_conversation=unexpected_command,
        )
        ctx = SimpleNamespace(sim=sim, entities=entities, player_id=1, registry=self.registry)
        return sim, npc, ctx

    def test_five_inline_layers_escape_restores_each_parent_without_mutation(self):
        sim, npc, ctx = self.fixture()
        before = sim.state.to_dict()
        keys = [f'UI_ACTION:topic:{topic}' for topic in ROAD_PATH[1:]] + ['ESC'] * len(ROAD_PATH)
        term = RecordingDialogueTerm(keys)
        _conversation_menu(ctx, term, npc)
        expected = list(ROAD_PATH) + list(reversed(ROAD_PATH[:-1]))
        self.assertEqual([frame['data']['topic'] for frame in term.frames], expected)
        for frame in term.frames:
            data = frame['data']
            depth = ROAD_PATH.index(data['topic']) + 1
            self.assertEqual([row['index'] for row in data['path']], list(range(depth)))
            self.assertEqual([row['topic'] for row in data['path']], list(ROAD_PATH[:depth]))
            self.assertEqual(len(data['thread']), depth - 1)
        child = term.frames[1]['data']
        self.assertEqual(child['thread'][0]['text'], term.frames[0]['data']['opening'])
        self.assertEqual(before, sim.state.to_dict())
        self.assertEqual(sim.clock.minute, 600)

    def test_breadcrumb_returns_across_several_layers_and_restores_selection(self):
        sim, npc, ctx = self.fixture()
        before = sim.state.to_dict()
        term = RecordingDialogueTerm(
            ['UI_HOVER:1'] + [f'UI_ACTION:topic:{topic}' for topic in ROAD_PATH[1:]]
            + ['UI_ACTION:path:0', 'ESC']
        )
        _conversation_menu(ctx, term, npc)
        self.assertEqual(term.frames[-2]['data']['topic'], ROAD_PATH[-1])
        restored = term.frames[-1]
        self.assertEqual(restored['data']['topic'], 'root')
        self.assertEqual(restored['selected'], 1)
        self.assertEqual(len(restored['data']['path']), 1)
        self.assertEqual(restored['data']['thread'], [])
        self.assertEqual(before, sim.state.to_dict())

    def test_tab_and_enter_follow_a_keyword_without_clicking_a_choice(self):
        sim, npc, ctx = self.fixture()
        before = sim.state.to_dict()
        term = RecordingDialogueTerm(['\t', '\r', 'ESC', 'ESC'])
        _conversation_menu(ctx, term, npc)
        self.assertEqual([frame['data']['topic'] for frame in term.frames],
                         ['root', 'root', 'area', 'root'])
        self.assertEqual(term.frames[1]['data']['focused_topic'], 'area')
        self.assertEqual(before, sim.state.to_dict())

    def test_parent_response_text_page_and_selection_survive_child_navigation(self):
        sim, npc, ctx = self.fixture()
        before = sim.state.to_dict()
        response = 'An earlier answer about the river and its working people. ' * 100
        term = RecordingDialogueTerm([
            'UI_HOVER:1', ']', 'UI_ACTION:topic:area', ']',
            'UI_ACTION:topic:area.roads', 'ESC', 'ESC', 'ESC',
        ])
        result = _conversation_menu(ctx, term, npc, response)
        restored = term.frames[-1]
        self.assertEqual(restored['data']['topic'], 'root')
        self.assertEqual(restored['data']['response'], response)
        self.assertEqual(restored['data']['transcript_page'], 1)
        self.assertEqual(restored['selected'], 1)
        area_frames = [frame for frame in term.frames if frame['data']['topic'] == 'area']
        self.assertEqual(area_frames[-1]['data']['transcript_page'], 1)
        self.assertEqual(result, response)
        self.assertEqual(before, sim.state.to_dict())

    def test_forged_stale_and_malformed_pointer_tokens_cannot_open_unoffered_topics(self):
        sim, npc, ctx = self.fixture()
        before = sim.state.to_dict()
        term = RecordingDialogueTerm([
            'UI_ACTION:topic:personal.history',
            'UI_ACTION:topic:area',
            'UI_ACTION:topic:personal',
            'UI_ACTION:topic:unknown.topic',
            'UI_ACTION:path:-1', 'UI_ACTION:path:999', 'UI_ACTION:path:garbage',
            'UI_ACTION:topic:area.roads', 'ESC', 'ESC', 'ESC',
        ])
        _conversation_menu(ctx, term, npc)
        topics = [frame['data']['topic'] for frame in term.frames]
        self.assertEqual(topics, ['root', 'root'] + ['area'] * 6 + ['area.roads', 'area', 'root'])
        self.assertEqual(before, sim.state.to_dict())

    def test_legacy_answer_belongs_to_its_route_and_is_restored_after_inline_branch(self):
        sim, npc, ctx = self.fixture()
        before = sim.state.to_dict()

        def choose_danger(frame):
            return f"UI_SELECT:{frame['rows'].index('danger')}"

        term = RecordingDialogueTerm([
            'UI_ACTION:topic:area', choose_danger,
            'UI_ACTION:topic:area.roads', 'ESC', 'ESC', 'ESC',
        ], capacity=20)
        _conversation_menu(ctx, term, npc)
        area_frames = [frame for frame in term.frames if frame['data']['topic'] == 'area']
        answer = area_frames[1]['data']['response']
        self.assertTrue(answer)
        self.assertEqual(area_frames[-1]['data']['response'], answer)
        self.assertEqual(term.frames[-1]['data']['response'], '')
        self.assertEqual(before, sim.state.to_dict())

    def test_previously_displayed_private_link_is_rechecked_when_trust_changes(self):
        sim, npc, ctx = self.fixture()
        changed_state = []

        def lose_trust_and_refresh(frame):
            self.assertIn('relations.confidence', {span['topic'] for span in frame['data']['spans']})
            npc.relationships['player']['trust'] = 0
            changed_state.append(sim.state.to_dict())
            return 'UI_ACTION:transcript_next'

        term = RecordingDialogueTerm([
            'UI_ACTION:topic:relations', lose_trust_and_refresh,
            'UI_ACTION:topic:relations.confidence', 'ESC', 'ESC',
        ])
        _conversation_menu(ctx, term, npc)
        self.assertEqual([frame['data']['topic'] for frame in term.frames],
                         ['root', 'relations', 'relations', 'relations', 'root'])
        self.assertEqual(changed_state[0], sim.state.to_dict())

    def test_unintroduced_npc_cannot_leak_private_incoming_answer_or_inline_topics(self):
        sim, npc, ctx = self.fixture(introduced=False)
        before = sim.state.to_dict()
        private_answer = f'{npc.name}, a {npc.occupation}, speaks of secret family history and private:home.'
        term = RecordingDialogueTerm([
            'UI_ACTION:topic:area', 'UI_ACTION:topic:personal.history',
            'UI_ACTION:path:0', 'ESC',
        ])
        _conversation_menu(ctx, term, npc, private_answer)
        for frame in term.frames:
            data = frame['data']
            self.assertEqual(frame['title'], 'Stranger')
            self.assertEqual(frame['rows'], ['introduce', 'inspect', 'goodbye'])
            self.assertFalse(any(span.get('topic') for span in data['spans']))
            for private in (npc.name, npc.occupation, 'secret family history', 'private:home'):
                self.assertNotIn(private, str(data))
        self.assertEqual(before, sim.state.to_dict())

    def test_terminal_reflows_and_pages_entire_answer_at_small_geometries(self):
        for cols, rows in ((40, 16), (28, 12)):
            with self.subTest(cols=cols, rows=rows):
                sim, npc, ctx = self.fixture()
                before = sim.state.to_dict()
                response = 'STARTTRANSCRIPT ' + 'A crossing carries carts only while its foundations hold. ' * 45 + ' ENDTRANSCRIPT'
                term = PlainDialogueTerm(cols, rows)
                _conversation_menu(ctx, term, npc, response)
                self.assertTrue(term.reached_end)
                self.assertTrue(term.returned_previous)
                self.assertGreater(len(term.frames), 2)
                shown = '\n'.join(term.frames)
                self.assertIn('STARTTRANSCRIPT', shown)
                self.assertIn('ENDTRANSCRIPT', shown)
                for frame in term.frames:
                    self.assertLessEqual(len(frame.splitlines()), rows)
                    self.assertTrue(all(visible_len(line) <= cols for line in frame.splitlines()))
                self.assertNotIn('ENDTRANSCRIPT', term.frames[-1])
                self.assertEqual(before, sim.state.to_dict())


if __name__ == '__main__':
    unittest.main()
