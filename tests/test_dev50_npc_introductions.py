"""An exchange of names is a command, not a side effect of opening chat."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from worldseed.app import _conversation_menu, _npc_profile_data, _npc_profile_menu
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Position, Vitals
from worldseed.entities.store import EntityStore
from worldseed.persistence.database import WorldDatabase
from worldseed.persistence.validation import validate_sim_state
from worldseed.sim.commands import IntroduceNPCCommand, TalkCommand
from worldseed.sim.engine import Simulation
from worldseed.systems.dialogue import DialogueSystem
from worldseed.systems.state import LivingWorldState, NPCState
from worldseed.ui.renderer import Renderer
from worldseed.ui.pygame_terminal import PygameTerminal


class RecordingTerm:
    mouse_ui = True

    def __init__(self, keys):
        self.keys = iter(keys)
        self.frames = []

    def size(self):
        return 60, 24

    def menu_page_size(self, presentation):
        return 3

    def present_feature_menu(self, presentation, title, rows, selected, **kwargs):
        self.frames.append((presentation, title, [r.key for r in rows], selected, kwargs))

    def read_key(self):
        return next(self.keys)


class NPCIntroductionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    def fixture(self):
        sim = Simulation.__new__(Simulation)
        sim.state = LivingWorldState(player_name='Mara', clock_minute=600)
        npc = NPCState('npc:test', 'Tomas Mere', 38, 'priest', ['suspicious'], 1, 0, 0, '', '',
                       hp=60, home_id='private:home', workplace_id='private:work',
                       backstory={'formative_event': 'secret history'})
        npc.relationships['player'] = {'trust': 37, 'affection': 25, 'familiarity': 80}
        sim.state.npcs[npc.uid] = npc
        sim.registry = self.registry
        sim.seed = b'introductions'
        sim.clock = SimpleNamespace(minute=600)
        sim.turn = 0
        sim.log = []
        sim._message = lambda message: sim.log.append(SimpleNamespace(message=message))
        sim.entities = EntityStore()
        sim.entities.spawn(preferred_id=1)
        sim.entities.add(1, Position(WorldPos(0, 0, 0)))
        sim.entities.add(1, Inventory())
        sim.entities.add(1, Vitals())
        sim.interiors = SimpleNamespace(player_presence=lambda: None)
        sim.settlement_physicalization = SimpleNamespace(structure_by_id=lambda _: SimpleNamespace(function='residence'))
        sim.debug = Mock()
        sim.crafting = Mock()
        sim._advance_time = Mock()
        sim._post_action = Mock()
        ctx = SimpleNamespace(sim=sim, player_id=1, entities=sim.entities, registry=self.registry)
        return sim, npc, ctx

    def test_starting_chat_does_not_reveal_identity_or_grant_relationship(self):
        sim, npc, _ = self.fixture()
        before = sim.state.to_dict()
        sim.begin_conversation(npc.uid)
        self.assertEqual(sim.state.to_dict(), before)
        self.assertIn('stranger', sim.log[-1].message.lower())
        self.assertNotIn(npc.name, sim.log[-1].message)
        self.assertNotIn(npc.occupation, sim.log[-1].message)

    def test_default_dialogue_query_obeys_authoritative_introduction_state(self):
        sim, npc, _ = self.fixture()
        scene=DialogueSystem(sim.state,sim.seed).scene(npc,600,Vitals(),topic='knowledge')
        self.assertEqual(scene.topic,'introduction')
        self.assertEqual(scene.speaker,'Stranger')

    def test_introduction_scene_hides_all_private_facts_even_with_topic_override(self):
        sim, npc, _ = self.fixture()
        before = sim.state.to_dict()
        scene = DialogueSystem(sim.state, sim.seed).scene(npc, 600, Vitals(), known=False, topic='personal')
        self.assertEqual(scene.speaker, 'Stranger')
        self.assertEqual(scene.topic, 'introduction')
        self.assertEqual(scene.relationship, ())
        self.assertEqual({o.key for o in scene.options}, {'introduce', 'inspect', 'goodbye'})
        for private in (npc.name, npc.occupation, 'secret history', 'suspicious'):
            self.assertNotIn(private.lower(), str(scene).lower())
        self.assertEqual(before, sim.state.to_dict())

    def test_real_command_path_exchanges_names_and_unlocks_topics(self):
        sim, npc, _ = self.fixture()
        sim.execute(TalkCommand(1, 1, 0))
        self.assertNotIn(npc.uid, sim.known_npc_ids())
        sim.execute(IntroduceNPCCommand(1, npc.uid))
        self.assertIn(npc.uid, sim.state.introduced_npcs)
        self.assertIn(npc.uid, sim.known_npc_ids())
        self.assertIn('Mara', sim.log[-1].message)
        self.assertIn('Tomas Mere', sim.log[-1].message)
        self.assertEqual(next(m for m in npc.memories if m['type'] == 'introduction')['player_name'], 'Mara')
        scene = DialogueSystem(sim.state, sim.seed).scene(npc, 600, Vitals(), known=True, introduced=True)
        self.assertIn('knowledge', {o.key for o in scene.options})
        # Zero-duration chat commands leave advancement to the realtime driver.
        sim._advance_time.assert_not_called()
        self.assertEqual(sim.clock.minute,600)

    def test_repeat_introduction_is_idempotent_even_in_a_later_time_bucket(self):
        sim, npc, _ = self.fixture()
        sim.introduce_npc(npc.uid)
        before = sim.state.to_dict()
        sim.clock.minute = 900
        sim.introduce_npc(npc.uid)
        self.assertEqual(before, sim.state.to_dict())

    def test_name_learned_by_testimony_is_not_a_personal_introduction(self):
        sim, npc, _ = self.fixture()
        sim.state.discovered_npcs = [npc.uid]
        scene = DialogueSystem(sim.state, sim.seed).scene(npc, 600, Vitals(), known=True, introduced=False)
        self.assertEqual(scene.speaker, 'Stranger')
        self.assertEqual(scene.topic, 'introduction')
        sim.begin_conversation(npc.uid)
        self.assertNotIn(npc.name, sim.log[-1].message)

    def test_live_sidebar_and_hover_do_not_identify_a_name_known_from_testimony(self):
        sim,npc,_=self.fixture()
        sim.state.discovered_npcs=[npc.uid]
        sim.resources=SimpleNamespace(description=lambda _: 'Open ground')
        sim.state.player_stealth_mode=True
        before=sim.state.to_dict()
        renderer=Renderer(self.registry,use_color=False)
        with patch('worldseed.ui.renderer.world_alerts',return_value=[]):
            text='\n'.join(renderer._sidebar(sim,'Grass',Inventory(),Vitals(),{},80,80,None,
                                            {'seen_by':[npc.uid]}))
        self.assertIn('Stranger sees you',text)
        self.assertIn('Stranger d1',text)
        self.assertNotIn(npc.name,text)
        self.assertNotIn(npc.occupation,text)
        term=PygameTerminal.__new__(PygameTerminal)
        term._hover_context={'z':0,'known':{'1,0,0'},'known_npcs':sim.introduced_npc_ids(),
                             'sim':sim,'registry':self.registry,
                             'world':SimpleNamespace(tile_at=lambda _:SimpleNamespace(terrain=SimpleNamespace(name='Grass',tags=[]))),
                             'npc_by':{(1,0,0):npc},'creature_by':{},'structure_by':{},'crop_by':{},
                             'resource_by':{},'pile_by':{}}
        lines=term._hover_lines_for(1,0)
        self.assertIn('Stranger',lines)
        self.assertNotIn(npc.name,lines)
        self.assertEqual(before,sim.state.to_dict())
        self.assertIn(npc.uid,sim.known_npc_ids())
        self.assertNotIn(npc.uid,sim.introduced_npc_ids())
        sim.introduce_npc(npc.uid)
        self.assertIn(npc.uid,sim.introduced_npc_ids())

    def test_remote_and_other_space_introductions_do_not_disclose_identity(self):
        sim, npc, _ = self.fixture()
        npc.x = 20
        self.assertFalse(sim.introduce_npc(npc.uid))
        self.assertFalse(sim.state.discovered_npcs)
        npc.x = 1
        sim.state.interior_actors[npc.uid] = SimpleNamespace(space_id='room:a', x=1000, y=1000)
        self.assertFalse(sim.introduce_npc(npc.uid))
        self.assertFalse(sim.state.discovered_npcs)

    def test_intro_command_is_allowed_inside_the_same_interior(self):
        sim, npc, _ = self.fixture()
        actor = SimpleNamespace(space_id='room:a', x=1000, y=1000)
        sim.interiors.player_presence = lambda: actor
        sim.state.interior_actors[npc.uid] = SimpleNamespace(space_id='room:a', x=1300, y=1500)
        sim.execute(IntroduceNPCCommand(1, npc.uid))
        self.assertIn(npc.uid, sim.state.introduced_npcs)

    def test_unknown_inspect_only_contains_visible_appearance_and_injuries(self):
        sim, npc, _ = self.fixture()
        before = sim.state.to_dict()
        data = _npc_profile_data(sim, npc, 'appearance')
        self.assertEqual(data['summary']['name'], 'Stranger')
        self.assertEqual(set(data['tabs']), {'appearance', 'overview'})
        self.assertIn('Visible wounds', str(data['tabs']['appearance']))
        for private in (npc.name, npc.occupation, 'secret history', 'private:', 'suspicious'):
            self.assertNotIn(private, str(data))
        self.assertEqual(before, sim.state.to_dict())

    def test_unknown_inspect_route_can_be_closed_without_identity_discovery(self):
        sim, npc, ctx = self.fixture()
        before = sim.state.to_dict()
        term = RecordingTerm(['ESC'])
        _npc_profile_menu(ctx, term, npc.uid)
        self.assertEqual(term.frames[0][1], 'Stranger')
        self.assertEqual(term.frames[0][2], ['appearance', 'overview'])
        self.assertEqual(before, sim.state.to_dict())

    def test_leaving_first_conversation_does_not_discover_or_modify_npc(self):
        sim, npc, ctx = self.fixture()
        before = sim.state.to_dict()
        term = RecordingTerm(['ESC'])
        _conversation_menu(ctx, term, npc)
        self.assertEqual(term.frames[0][1], 'Stranger')
        self.assertEqual(term.frames[0][2], ['introduce', 'goodbye'])
        self.assertEqual(before, sim.state.to_dict())

    def test_intro_then_nested_topic_esc_preserves_parent_selection(self):
        sim, npc, ctx = self.fixture()
        term = RecordingTerm(['UI_SELECT:0', 'UI_SELECT:1', 'ESC', 'ESC'])
        _conversation_menu(ctx, term, npc)
        self.assertEqual([f[1] for f in term.frames], ['Stranger', 'Tomas Mere', 'KNOWLEDGE', 'Tomas Mere'])
        self.assertEqual(term.frames[-1][3], 1)
        self.assertEqual(term.frames[2][4]['total'], 6)
        self.assertIn(npc.uid, sim.state.introduced_npcs)

    def test_unknown_inspect_from_chat_esc_returns_to_unnamed_chat(self):
        sim, npc, ctx = self.fixture()
        before = sim.state.to_dict()
        term = RecordingTerm(['UI_ACTION:inspect', 'ESC', 'ESC'])
        _conversation_menu(ctx, term, npc)
        self.assertEqual([f[1] for f in term.frames], ['Stranger', 'Stranger', 'Stranger'])
        self.assertEqual(before, sim.state.to_dict())

    def test_intro_record_round_trip_and_legacy_missing_field(self):
        sim, npc, _ = self.fixture()
        sim.introduce_npc(npc.uid)
        raw = sim.state.to_dict()
        self.assertEqual(LivingWorldState.from_dict(raw).to_dict(), raw)
        del raw['introduced_npcs']
        self.assertEqual(LivingWorldState.from_dict(raw).introduced_npcs, [npc.uid])
        raw['introduced_npcs'] = []
        self.assertEqual(LivingWorldState.from_dict(raw).introduced_npcs, [])

    def test_save_verifier_rejects_bad_intro_data_and_accepts_real_round_trip(self):
        sim, npc, _ = self.fixture()
        sim.introduce_npc(npc.uid)
        raw = sim.state.to_dict()
        self.assertFalse(validate_sim_state(raw))
        raw['introduced_npcs'] = [npc.uid, npc.uid]
        self.assertIn('duplicate NPC introductions', validate_sim_state(raw))
        raw['introduced_npcs'] = ['npc:unknown']
        self.assertIn('introduced NPC identity is not discovered', validate_sim_state(raw))
        with tempfile.TemporaryDirectory() as directory:
            db = WorldDatabase.create(Path(directory) / 'intro.db', 'Introductions', b'introductions'.hex())
            try:
                db.save_state(turn=sim.turn, tile_deltas={}, player_id=1, position=sim.player_pos,
                              inventory={}, sim_state=sim.state.to_dict())
                self.assertFalse(db.verify())
                loaded = LivingWorldState.from_dict(db.load_sim_state())
                self.assertEqual(loaded.introduced_npcs, [npc.uid])
                self.assertEqual(loaded.npcs[npc.uid].memories[-1]['player_name'], 'Mara')
            finally:
                db.close()


if __name__ == '__main__':
    unittest.main()
