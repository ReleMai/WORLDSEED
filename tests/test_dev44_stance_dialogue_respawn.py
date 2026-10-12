import os
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.entities.components import Inventory, Position, Vitals
from worldseed.entities.store import EntityStore
from worldseed.sim.engine import Simulation
from worldseed.systems.dialogue import DialogueSystem
from worldseed.systems.hunting import HuntingSystem
from worldseed.systems.npc_knowledge import NPCKnowledgeSystem
from worldseed.systems.property_intrusion import CasingSystem
from worldseed.systems.respawn import nearby_land_spawn
from worldseed.systems.state import LivingWorldState, NPCState, SettlementState
from worldseed.ui.pygame_terminal import PygameTerminal
from worldseed.ui.widgets import MenuRow


class StanceKnowledgeRespawnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    def fixture(self):
        state = LivingWorldState()
        town = SettlementState('settlement:test', 'Mistwick', 0, 0, 100, 200, 33, 'culture:test', 'religion:test', 'faction:test')
        town.resource_specializations = ['farming', 'logging']
        town.crop_ids = ['core:corn', 'core:wheat']
        town.livestock_species_ids = ['core:pig']
        state.settlements[town.uid] = town
        npc = NPCState('npc:test', 'Tomas', 30, 'farmer', [], 100, 200, 0, town.uid, town.faction_id)
        state.npcs[npc.uid] = npc
        state.discovered_npcs = [npc.uid]
        state.introduced_npcs = [npc.uid]
        return state, town, npc

    def test_commands_reject_all_non_aggressive_stances_before_side_effects(self):
        sim = Simulation.__new__(Simulation)
        sim.state = LivingWorldState()
        sim._message = Mock()
        for stance in ('normal', 'stalk', 'crouch'):
            sim.state.player_hunting_stance = stance
            for method in ('_lockpick_door', '_lockpick_container', '_force_door'):
                getattr(sim, method)(SimpleNamespace())
        self.assertEqual(sim._message.call_count, 9)
        sim.state.player_hunting_stance = 'aggressive'
        self.assertTrue(sim._require_aggressive_stance())

    def test_leaving_aggressive_stance_stops_casing(self):
        hunting = HuntingSystem.__new__(HuntingSystem)
        hunting.state = LivingWorldState()
        self.assertIn('Aggressive Stance', hunting.set_player_stance('aggressive'))
        self.assertEqual(LivingWorldState.from_dict(hunting.state.to_dict()).player_hunting_stance, 'aggressive')
        hunting.state.player_casing_property_id = 'house:test'
        hunting.set_player_stance('crouch')
        self.assertEqual(hunting.state.player_casing_property_id, '')

    def test_no_buildings_are_caseable_while_the_mechanic_is_retired(self):
        self.assertFalse(CasingSystem.can_case(SimpleNamespace(enclosed=True, function='residence')))
        for function in ('farm_field', 'logging_camp', 'animal_pen', 'mine_site', 'monument'):
            self.assertFalse(CasingSystem.can_case(SimpleNamespace(enclosed=False, function=function)))
        self.assertFalse(CasingSystem.can_case(SimpleNamespace(enclosed=True, function='residence', destroyed=True)))

    def test_knowledge_browsing_is_observational_and_disclosure_is_explicit(self):
        state, town, npc = self.fixture()
        knowledge = NPCKnowledgeSystem(state, self.registry)
        before = state.to_dict()
        response, facts = knowledge.answer(npc, 'towns')
        self.assertIn('Mistwick', response)
        self.assertEqual(before, state.to_dict())
        knowledge.disclose(facts)
        self.assertIn(town.uid, state.discovered_settlements)
        self.assertIn('Corn', knowledge.answer(npc, 'plants')[0])
        self.assertIn('farming and logging', knowledge.answer(npc, 'resources')[0])

    def test_suspicious_npc_withholds_specific_facts_until_trusted(self):
        state, _, npc = self.fixture()
        npc.traits.append('suspicious')
        npc.knowledge.append('species:core:wolf')
        knowledge = NPCKnowledgeSystem(state, self.registry)
        self.assertEqual(knowledge.answer(npc, 'animals')[1], {})
        npc.relationships['player'] = {'trust': 8}
        response, facts = knowledge.answer(npc, 'animals')
        self.assertIn('Wolf', response)
        self.assertIn('core:wolf', facts['discovered_species'])

    def test_topics_expose_expertise_without_inventing_skill_gain(self):
        state, _, npc = self.fixture()
        npc.skills['farming'] = 5
        vitals = SimpleNamespace(hp=100, max_hp=100, pain=0, blood=100, hunger=0, thirst=0)
        scene = DialogueSystem(state, b'test').scene(npc, 600, vitals, topic='knowledge')
        self.assertEqual({o.key for o in scene.options}, {'animals', 'plants', 'resources', 'towns', 'skills', 'back'})
        before = state.to_dict()
        self.assertIn('farming (5)', NPCKnowledgeSystem(state, self.registry).answer(npc, 'skills')[0])
        self.assertEqual(before, state.to_dict())

    def test_nearby_successor_is_dry_and_avoids_blocked_cells(self):
        terrain = {'water': SimpleNamespace(passable=True, tags=['water']), 'land': SimpleNamespace(passable=True, tags=[])}
        land = {(101, 200), (102, 200)}
        found = nearby_land_spawn(WorldPos(100, 200, -3), lambda p: 'land' if (p.x, p.y) in land else 'water', terrain, lambda p: p.x != 101)
        self.assertEqual(found, WorldPos(102, 200, 0))

    def test_offshore_death_uses_known_land_and_all_water_is_bounded(self):
        terrain = {'water': SimpleNamespace(passable=True, tags=['water']), 'land': SimpleNamespace(passable=True, tags=[])}
        calls = []
        def query(p):
            calls.append(p)
            return 'land' if p == WorldPos(1900, 2000, 0) else 'water'
        found = nearby_land_spawn(WorldPos(2000, 2000), query, terrain, lambda _: True, [(1900, 2000)])
        self.assertEqual(found, WorldPos(1900, 2000))
        calls.clear()
        self.assertIsNone(nearby_land_spawn(WorldPos(2000, 2000), lambda p: calls.append(p) or 'water', terrain, lambda _: True))
        self.assertLess(len(calls), 5000)

    def test_extreme_temperature_damage_is_hourly_not_per_realtime_tick(self):
        sim=Simulation.__new__(Simulation)
        sim.state=LivingWorldState()
        sim.entities=EntityStore()
        sim.entities.spawn(preferred_id=1)
        sim.entities.add(1,Position(WorldPos(0,0,0)))
        sim.entities.add(1,Inventory())
        sim.entities.add(1,Vitals(hp=90,max_hp=100,body_temp=10,blood=100))
        sim.clock=SimpleNamespace(minute=60)
        sim.turn=5
        sim.interiors=None
        sim.world=SimpleNamespace(generator=SimpleNamespace(sample_fields=lambda *_: SimpleNamespace(temperature=40000)))
        sim.environment=SimpleNamespace(weather=SimpleNamespace(at=lambda *_: {'temp_delta':0}))
        sim.building=SimpleNamespace(room_at=lambda *_: {'sheltered':False},environmental_bonuses=lambda *_:{})
        sim.registry=SimpleNamespace(items={})
        sim.player_attribute=lambda *_:5
        sim.player_skill=lambda *_:0
        with patch('worldseed.systems.swimming.exposure',return_value=SimpleNamespace(mode='dry')):
            sim._update_vitals(1)
            self.assertEqual(sim.entities.get(1,Vitals).hp,89)
            self.assertEqual(sim.state.player_combat_log[-1]['source'],'Hypothermia')
            sim.clock.minute=60
            sim._update_vitals(0)
            self.assertEqual(sim.entities.get(1,Vitals).hp,89)
            sim.clock.minute=61
            sim._update_vitals(1)
            self.assertEqual(sim.entities.get(1,Vitals).hp,89)

    def test_death_preserves_dropped_goods_and_spawns_on_nearby_surface(self):
        sim = Simulation.__new__(Simulation)
        sim.state = LivingWorldState()
        sim.entities = EntityStore()
        sim.entities.spawn(preferred_id=1)
        sim.entities.add(1, Position(WorldPos(100, 200, -2)))
        sim.entities.add(1, Inventory({'core:wood': 3}))
        sim.entities.add(1, Vitals(hp=1,body_temp=5,blood=2))
        sim.state.player_infections=['player-infection:old']
        sim.state.infections['player-infection:old']=SimpleNamespace(disease_id='old')
        land = SimpleNamespace(passable=True, tags=[])
        water = SimpleNamespace(passable=True, tags=['water'])
        query = lambda p: 'land' if (p.x, p.y) == (101, 200) else 'water'
        sim.registry = SimpleNamespace(terrains={'land': land, 'water': water})
        sim.world = SimpleNamespace(generator=SimpleNamespace(terrain_at=query), tile_at=lambda p: SimpleNamespace(terrain=land if query(p)=='land' else water))
        sim.resources = SimpleNamespace(blocks_movement=lambda _: False)
        sim.building = SimpleNamespace(passable=lambda *_: True)
        sim.property_security = SimpleNamespace(blocks_player=lambda _: False)
        sim.environment = SimpleNamespace(fluid_passable=lambda _: True)
        sim.clock = SimpleNamespace(minute=1234)
        sim.history = SimpleNamespace(record=Mock())
        sim.hunting = HuntingSystem.__new__(HuntingSystem)
        sim.hunting.state = sim.state
        sim._message = Mock()
        sim._handle_death('test')
        self.assertEqual(sim.player_pos, WorldPos(101, 200, 0))
        self.assertEqual(sim.state.ground_piles['100,200,-2'].items, {'core:wood': 3})
        self.assertEqual(sim.entities.get(1, Inventory).count('core:wood'), 0)
        self.assertEqual(len(sim.state.legacy), 1)
        v=sim.entities.get(1,Vitals)
        self.assertEqual((v.hp,v.body_temp,v.blood),(v.max_hp,50,100))
        self.assertFalse(sim.state.player_infections)
        self.assertNotIn('player-infection:old',sim.state.infections)
        self.assertEqual((sim.state.player_fx,sim.state.player_fy),(0.5,0.5))

    def test_knowledge_tree_back_navigation_preserves_parent_route(self):
        from worldseed.app import _conversation_menu
        state, _, npc = self.fixture()
        vitals = SimpleNamespace(hp=100, max_hp=100, pain=0, blood=100, hunger=0, thirst=0)
        sim = SimpleNamespace(state=state, registry=self.registry, seed=b'test', clock=SimpleNamespace(minute=600), known_npc_ids=lambda: {npc.uid})
        ctx = SimpleNamespace(sim=sim, entities=SimpleNamespace(get=lambda *_: vitals), player_id=1)
        choices = iter(['knowledge', 'skills', 'back', 'goodbye'])
        routes = []
        def menu(term, nav, *args, **kwargs):
            routes.append(nav.current.route_id)
            return next(choices)
        with patch('worldseed.app._stack_menu', side_effect=menu):
            _conversation_menu(ctx, SimpleNamespace(), npc)
        self.assertEqual(routes, ['npc-dialogue', 'npc-dialogue:knowledge', 'npc-dialogue:knowledge', 'npc-dialogue'])


class DialogueLayoutTests(unittest.TestCase):
    def setUp(self):
        self.term = PygameTerminal(1280, 800)
        self.term.enter()
        self.addCleanup(self.term.restore)

    def test_long_text_wraps_using_actual_render_font(self):
        for width in (100, 240, 470):
            lines = self.term._wrap_pixel_text('TomasMorrow'*12 + ' Community standing +18. I keep thinking about the herd.', self.term.font, width)
            self.assertTrue(all(self.term.font.size(line)[0] <= width for line in lines))

    def test_all_paged_choices_and_inspect_have_hit_targets(self):
        term = self.term
        term._floating_panels['npc_dialogue'] = {'x': 12, 'y': 12, 'w': 640, 'h': 440}
        count = term.menu_page_size('npc_dialogue')
        rows = [MenuRow(str(i), 'Ask about topic ' + str(i)) for i in range(count)]
        term._present_npc_dialogue('Tomas Morrow', rows, 0, total=20, data={
            'speaker': 'Tomas Morrow', 'role': 'Herder', 'context': ['Night', 'Herder', 'Drink'],
            'relationship': {'trust': 4, 'affection': 3, 'familiarity': 21, 'community': 18},
            'response': 'A long story about this community and its people. '*100,
        })
        tokens = [token for _, token in term._pointer_targets]
        self.assertTrue(all(f'UI_SELECT:{i}' in tokens for i in range(count)))
        self.assertIn('UI_ACTION:inspect', tokens)
        self.assertIn('UI_ACTION:transcript_next', tokens)
        self.assertIn('PGDN', tokens)
