"""Conversation entrypoints hold the real driver across every nested route."""
from __future__ import annotations

import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tests import test_dev50_npc_introductions as introductions
from worldseed.app import _conversation_menu, _npc_profile_data, _talk_action
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.entities.components import Inventory
from worldseed.sim.realtime import RealtimeSimulationDriver
from worldseed.systems.state import NPCState
from worldseed.ui.pointer import WindowCloseRequested
from worldseed.ui.terminal import Terminal


class ClockedTerminal(Terminal):
    """Drive production clock scopes while supplying deterministic input."""

    def __init__(self, case, sim, clock, driver, keys):
        super().__init__()
        self.case = case
        self.sim = sim
        self.clock = clock
        self.driver = driver
        self.keys = iter(keys)
        self.frames = []
        self.reads = []
        self.frozen = self.snapshot()
        self.set_realtime_callback(driver.pump)

    def snapshot(self):
        return (self.sim.clock.minute,
                tuple((npc.uid, npc.x, npc.y, npc.z) for npc in self.sim.state.npcs.values()))

    def size(self):
        return 80, 26

    def present(self, text):
        self.frames.append({'presentation': 'terminal', 'text': text})

    def read_key(self):
        # Reading can take many real minutes. Neither callback pumping nor a
        # direct driver pump may move the actors while the route owns a hold.
        self.clock.now += 300
        self.case.assertFalse(self._pump_realtime())
        self.case.assertEqual(self.driver.pump(), 0)
        self.case.assertEqual(self.snapshot(), self.frozen)
        self.reads.append((self.frames[-1]['presentation'], self.driver._pause_depth))
        try:
            key = next(self.keys)
        except StopIteration:
            raise AssertionError('Conversation requested input after scripted exit') from None
        if isinstance(key, BaseException):
            raise key
        return key(self.frames[-1]) if callable(key) else key


class GraphicalClockedTerminal(ClockedTerminal):
    mouse_ui = True

    def menu_page_size(self, presentation):
        return 20

    def present_menu(self, title, rows, selected, **kwargs):
        self.frames.append({'presentation': 'menu', 'title': title,
                            'rows': [row.key for row in rows], 'selected': selected,
                            **copy.deepcopy(kwargs)})

    def present_feature_menu(self, presentation, title, rows, selected, **kwargs):
        self.frames.append({'presentation': presentation, 'title': title,
                            'rows': [row.key for row in rows], 'selected': selected,
                            **copy.deepcopy(kwargs)})

    def present_feature_document(self, presentation, title, lines, **kwargs):
        self.frames.append({'presentation': presentation, 'title': title,
                            'lines': list(lines), **copy.deepcopy(kwargs)})

    def present_document(self, title, lines, **kwargs):
        self.frames.append({'presentation': 'document', 'title': title,
                            'lines': list(lines), **copy.deepcopy(kwargs)})


class Dev61ConversationIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    def fixture(self, *, introduced=True, second_npc=False):
        fixture = introductions.NPCIntroductionTests()
        fixture.registry = self.registry
        sim, npc, ctx = fixture.fixture()
        if introduced:
            sim.state.discovered_npcs = [npc.uid]
            sim.state.introduced_npcs = [npc.uid]
        if second_npc:
            other = NPCState('npc:second', 'Elin Wren', 42, 'merchant', [], 0, 1, 0, '', '')
            sim.state.npcs[other.uid] = other
        sim.entities.get(1, Inventory).add('core:clean_water', 1)
        clock = SimpleNamespace(now=0.0)
        advances = []

        def advance(minutes):
            advances.append(minutes)
            sim.clock.minute += minutes
            sim.state.clock_minute = sim.clock.minute
            for person in sim.state.npcs.values():
                person.x += minutes
            return minutes

        sim.advance_realtime = advance
        driver = RealtimeSimulationDriver(sim, seconds_per_game_minute=1)
        driver.resume(clock.now)
        return sim, npc, ctx, clock, driver, advances

    def assert_resumes_without_catchup(self, term, clock, driver, advances):
        self.assertEqual(getattr(term, '_realtime_pause_depth', 0), 0)
        self.assertEqual(driver._pause_depth, 0)
        self.assertFalse(term._pump_realtime())
        self.assertEqual(advances, [])
        clock.now += 0.5
        self.assertFalse(term._pump_realtime())
        clock.now += 0.5
        self.assertTrue(term._pump_realtime())
        self.assertEqual(advances, [1])

    def test_driver_stays_frozen_through_nested_inspection_and_cancelled_gift(self):
        sim, npc, ctx, clock, driver, advances = self.fixture()
        before = sim.state.to_dict()

        def choose(key):
            return lambda frame: f"UI_SELECT:{frame['rows'].index(key)}"

        term = GraphicalClockedTerminal(self, sim, clock, driver, [
            'UI_ACTION:topic:area', 'UI_ACTION:inspect', choose('belongings'), 'ESC', 'ESC', 'ESC',
            'UI_ACTION:topic:relations', choose('gift'), 'ESC', 'ESC', 'ESC',
        ])
        with patch('worldseed.sim.realtime.time.monotonic', side_effect=lambda: clock.now):
            _conversation_menu(ctx, term, npc)
            self.assertEqual(before, sim.state.to_dict())
            self.assertTrue(any(frame['presentation'] == 'npc_profile' for frame in term.frames))
            self.assertTrue(any(frame.get('title') == 'OFFER A GIFT' for frame in term.frames))
            self.assertTrue(any('lines' in frame for frame in term.frames))
            chats = [frame for frame in term.frames if frame['presentation'] == 'npc_dialogue']
            self.assertTrue(all(frame['data']['time_paused'] for frame in chats))
            self.assertTrue(all('inspect' not in frame['rows'] for frame in chats))
            self.assert_resumes_without_catchup(term, clock, driver, advances)
        sim._advance_time.assert_not_called()

    def test_npc_picker_and_header_inspection_share_the_conversation_hold(self):
        sim, npc, ctx, clock, driver, advances = self.fixture(introduced=False, second_npc=True)
        before = sim.state.to_dict()
        term = GraphicalClockedTerminal(self, sim, clock, driver, [
            'UI_SELECT:1', 'UI_ACTION:inspect', 'ESC', 'ESC',
        ])
        with patch('worldseed.sim.realtime.time.monotonic', side_effect=lambda: clock.now):
            _talk_action(ctx, term)
            self.assertEqual(term.frames[0]['title'], 'TALK TO')
            self.assertEqual(term.reads[0], ('menu', 1))
            self.assertTrue(all(depth >= 2 for _, depth in term.reads[1:]))
            self.assertTrue(any(frame['presentation'] == 'npc_profile' for frame in term.frames))
            self.assertEqual(before, sim.state.to_dict())
            self.assert_resumes_without_catchup(term, clock, driver, advances)
        sim._advance_time.assert_not_called()

    def test_exceptions_and_window_close_unwind_entrypoint_clock_holds(self):
        for entrypoint in (_conversation_menu, _talk_action):
            for exception in (RuntimeError, WindowCloseRequested):
                with self.subTest(entrypoint=entrypoint.__name__, exception=exception.__name__):
                    sim, npc, ctx, clock, driver, advances = self.fixture(introduced=False, second_npc=True)
                    keys = ['UI_SELECT:0'] if entrypoint is _talk_action else []
                    keys.append(exception('close conversation while reading'))
                    term = GraphicalClockedTerminal(self, sim, clock, driver, keys)
                    before = sim.state.to_dict()
                    with patch('worldseed.sim.realtime.time.monotonic', side_effect=lambda: clock.now):
                        with self.assertRaises(exception):
                            if entrypoint is _conversation_menu:
                                entrypoint(ctx, term, npc)
                            else:
                                entrypoint(ctx, term)
                        self.assertEqual(before, sim.state.to_dict())
                        self.assert_resumes_without_catchup(term, clock, driver, advances)

    def test_chat_and_profile_share_stable_portrait_without_stranger_identity_leaks(self):
        sim, npc, ctx, clock, driver, advances = self.fixture(introduced=False)
        before = sim.state.to_dict()
        term = GraphicalClockedTerminal(self, sim, clock, driver, ['UI_ACTION:inspect', 'ESC', 'ESC'])
        with patch('worldseed.sim.realtime.time.monotonic', side_effect=lambda: clock.now):
            _conversation_menu(ctx, term, npc, f'{npc.name} is a {npc.occupation} with secret history.')
        chat = next(frame for frame in term.frames if frame['presentation'] == 'npc_dialogue')
        profile = next(frame for frame in term.frames if frame['presentation'] == 'npc_profile')
        self.assertIsNotNone(chat['data']['portrait'])
        self.assertEqual(chat['data']['portrait'], profile['data']['portrait'])
        self.assertEqual(chat['data']['portrait'], _npc_profile_data(sim, npc, 'appearance')['portrait'])
        for frame in term.frames:
            self.assertEqual(frame['title'], 'Stranger')
            for private in (npc.name, npc.occupation, 'secret history', 'private:home'):
                self.assertNotIn(private, str(frame))
        self.assertEqual(before, sim.state.to_dict())
        self.assertEqual(advances, [])

    def test_terminal_inspection_choice_remains_available_with_clock_held(self):
        sim, npc, ctx, clock, driver, advances = self.fixture(introduced=False)
        before = sim.state.to_dict()
        term = ClockedTerminal(self, sim, clock, driver, ['ESC'])
        with patch('worldseed.sim.realtime.time.monotonic', side_effect=lambda: clock.now):
            _conversation_menu(ctx, term, npc)
            self.assertIn('Inspect', term.frames[0]['text'])
            self.assertEqual(term.frames[0]['text'].count('Inspect'), 1)
            self.assertEqual(before, sim.state.to_dict())
            self.assert_resumes_without_catchup(term, clock, driver, advances)


if __name__ == '__main__':
    unittest.main()
