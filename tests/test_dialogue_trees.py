import copy
from dataclasses import FrozenInstanceError
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from worldseed.systems.dialogue import DialogueOption, DialogueSpan, DialogueSystem
from worldseed.systems.dialogue_tree import load_dialogue_tree, validate_dialogue_data
from worldseed.systems.state import LivingWorldState, NPCState, SettlementState
from worldseed.core.coords import WorldPos
from worldseed.persistence.database import WorldDatabase


class DialogueTreeTests(unittest.TestCase):
    def fixture(self):
        state = LivingWorldState()
        town = SettlementState('settlement:test', 'Undiscovered Town', 0, 0, 0, 0, 80,
                               'culture:test', 'religion:test', 'faction:test')
        state.settlements[town.uid] = town
        npc = NPCState('npc:test', 'Eda', 35, 'healer', ['patient'], 0, 0, 0,
                       town.uid, town.faction_id)
        state.npcs[npc.uid] = npc
        state.discovered_npcs = [npc.uid]
        state.introduced_npcs = [npc.uid]
        npc.relationships['player'] = {'trust': 50, 'familiarity': 50, 'affection': 10}
        vitals = SimpleNamespace(hp=100, max_hp=100, pain=0, blood=100,
                                 hunger=10, thirst=10, stamina=100, body_temp=50)
        return state, town, npc, vitals, DialogueSystem(state, b'dialogue-tree-test')

    def test_extensive_immutable_tree_and_four_levels(self):
        tree = load_dialogue_tree()
        self.assertGreaterEqual(len(tree.nodes), 40)
        topic = 'area.roads.crossings.flood.waterline'
        self.assertIn(topic, tree.nodes)
        depth = 0
        while topic in tree.nodes:
            depth += 1
            topic = tree.nodes[topic].parent
        self.assertGreaterEqual(depth, 4)
        with self.assertRaises(TypeError):
            tree.nodes['invented'] = tree.nodes['work']
        with self.assertRaises(FrozenInstanceError):
            tree.nodes['work'].label = 'changed'
        with self.assertRaises(FrozenInstanceError):
            DialogueSpan('word', 'area').text = 'changed'
        self.assertIs(tree, load_dialogue_tree())

    def test_every_topic_is_deterministic_observational_and_spans_are_exact(self):
        state, _, npc, vitals, system = self.fixture()
        before = state.to_dict()
        for topic in ('root', 'area', 'personal', 'relations', 'knowledge', *load_dialogue_tree().nodes):
            first = system.scene(npc, 600, vitals, topic=topic, facts={'player.wealth': 200})
            second = system.scene(npc, 600, vitals, topic=topic, facts={'player.wealth': 200})
            self.assertEqual(first, second, topic)
            self.assertEqual(''.join(span.text for span in first.spans), first.opening, topic)
            for span in first.spans:
                if span.topic:
                    self.assertTrue(load_dialogue_tree().allows(span.topic, system._facts(npc, state.settlements[npc.settlement_id], 600, vitals, {})), span.topic)
            self.assertNotIn('Undiscovered Town', first.opening)
        self.assertEqual(before, state.to_dict())

    def test_root_link_words_follow_injury_hunger_notoriety_and_wealth(self):
        state, town, npc, vitals, system = self.fixture()
        normal = system.scene(npc, 600, vitals, facts={'player.wealth': 0})
        self.assertTrue({'area', 'personal', 'relations', 'knowledge', 'work', 'economy'} <=
                        {span.topic for span in normal.spans})
        self.assertFalse({'health', 'crime', 'needs'} & {span.topic for span in normal.spans})
        vitals.blood = 50
        vitals.hunger = 80
        state.player_crime_heat[town.uid] = 50
        changed = system.scene(npc, 600, vitals, facts={'player.wealth': 500, 'environment.rain': 80})
        self.assertTrue({'health', 'crime', 'needs'} <= {span.topic for span in changed.spans})
        self.assertNotEqual(normal.opening, changed.opening)

    def test_private_descendants_cannot_bypass_gates_or_disclose_backstory_names(self):
        state, _, npc, vitals, system = self.fixture()
        npc.relationships['player']['trust'] = 0
        npc.backstory = {'birthplace': 'Secret Silverhaven', 'formative_event': 'Hidden Lord Eldan'}
        npc.wants = ['Secret Sister Meriel']
        for prefix in ('personal.family', 'personal.history', 'relations.confidence'):
            for topic in load_dialogue_tree().nodes:
                if topic == prefix or topic.startswith(prefix + '.'):
                    scene = system.scene(npc, 600, vitals, topic=topic, facts={'player.trust': 100, 'relationship.trust': 100})
                    self.assertIn('not know one another', scene.opening)
                    self.assertFalse(any(span.topic for span in scene.spans))
                    self.assertEqual([o.key for o in scene.options], ['back'])
        npc.relationships['player']['trust'] = 100
        for topic in ('root', 'personal', 'personal.history'):
            scene = system.scene(npc, 600, vitals, topic=topic)
            self.assertNotIn('Silverhaven', scene.opening)
            self.assertNotIn('Eldan', scene.opening)
            self.assertNotIn('Meriel', scene.opening)

    def test_actual_authored_storylets_react_to_independent_simulation_causes(self):
        cases = [
            ('area.dangers', {}, {'environment.storm': True}, None),
            ('economy.wealth', {'player.wealth': 20}, {'player.wealth': 500}, None),
            ('knowledge.learning.evidence', {'player.attributes.perception': 5}, {'player.attributes.perception': 9}, None),
            ('knowledge.plants', {'player.skills.foraging': 0}, {'player.skills.foraging': 6}, None),
            ('personal.wellbeing', {}, {}, lambda state, town, npc, vitals: npc.needs.update(rest=80)),
            ('relations.listen', {'npc.memories.player_valence': 0}, {'npc.memories.player_valence': -20}, None),
            ('knowledge.resources', {'household.fuel_shortage': 0}, {'household.fuel_shortage': 4}, None),
            ('knowledge.towns', {}, {'faction.at_war': True}, None),
            ('knowledge.towns.sanitation', {}, {}, lambda state, town, npc, vitals: setattr(town, 'sanitation', 10)),
            ('knowledge.towns.housing', {}, {}, lambda state, town, npc, vitals: setattr(town, 'homeless', 5)),
            ('knowledge.towns', {}, {}, lambda state, town, npc, vitals: setattr(town, 'quarantine_level', 1)),
            ('work.professions.guard', {}, {}, lambda state, town, npc, vitals: setattr(town, 'border_pressure', 60)),
        ]
        for topic, before_facts, after_facts, mutate in cases:
            state, town, npc, vitals, system = self.fixture()
            town.housing_capacity = town.population
            if topic == 'work.professions.guard':npc.occupation = 'guard'
            baseline = system.scene(npc, 600, vitals, topic=topic, facts=before_facts)
            if mutate:mutate(state, town, npc, vitals)
            changed = system.scene(npc, 600, vitals, topic=topic, facts=after_facts)
            self.assertNotEqual(baseline.opening, changed.opening, topic)
            self.assertEqual(''.join(span.text for span in changed.spans), changed.opening)

    def test_introduction_does_not_touch_private_attributes(self):
        state, _, npc, vitals, system = self.fixture()
        stranger = SimpleNamespace(uid=npc.uid)
        before = state.to_dict()
        scene = system.scene(stranger, 600, vitals, known=False, introduced=False,
                             topic='personal.history', facts={'player.wealth': 100})
        self.assertEqual(scene.speaker, 'Stranger')
        self.assertEqual(scene.relationship, ())
        self.assertEqual(scene.spans, ())
        self.assertEqual({o.key for o in scene.options}, {'introduce', 'inspect', 'goodbye'})
        self.assertEqual(before, state.to_dict())

    def test_relationship_rewards_cannot_be_farmed_by_topic_alias_or_pruning(self):
        state, _, npc, _, system = self.fixture()
        npc.relationships['npc:friend'] = {'trust': 37, 'respect': 12}
        first = DialogueOption('listen', 'Listen', '', trust_delta=1, familiarity_delta=3)
        second = DialogueOption('different_tree.listen', 'Listen again', '', trust_delta=1)
        self.assertTrue(system.apply_option(npc, first, 600))
        trust = npc.relationships['player']['trust']
        npc.memories = [{'type': 'unrelated', 'minute': 600}] * 40
        self.assertFalse(system.apply_option(npc, second, 600))
        loaded = LivingWorldState.from_dict(state.to_dict())
        self.assertEqual(loaded.npcs[npc.uid].relationships['npc:friend'], {'trust': 37, 'respect': 12})
        self.assertEqual(loaded.npcs[npc.uid].relationships['player']['dialogue_positive_bucket'], 3)
        self.assertFalse(DialogueSystem(loaded, b'test').apply_option(loaded.npcs[npc.uid], first, 601))
        self.assertEqual(npc.relationships['player']['trust'], trust)
        self.assertTrue(system.apply_option(npc, second, 800))
        self.assertLessEqual(len(npc.memories), 40)
        self.assertTrue(npc.memories[-1]['marker'].startswith('dialogue:v2:npc:test:player:'))

    def test_spent_reward_budget_never_suppresses_hostile_penalties(self):
        _, _, npc, _, system = self.fixture()
        self.assertTrue(system.apply_option(npc, DialogueOption('listen', 'Listen', '', trust_delta=1, affection_delta=1, familiarity_delta=3), 600))
        relationship = dict(npc.relationships['player'])
        attack = DialogueOption('attack', 'Attack', '', 'hostile', -20, 'attack', affection_delta=-15, familiarity_delta=5)
        self.assertTrue(system.apply_option(npc, attack, 600))
        self.assertEqual(npc.relationships['player']['trust'], relationship['trust']-20)
        self.assertEqual(npc.relationships['player']['affection'], relationship['affection']-15)
        self.assertEqual(npc.relationships['player']['familiarity'], relationship['familiarity'])
        self.assertFalse(system.apply_option(npc, attack, 600))

    def test_relationship_budget_checkpoint_passes_save_verifier(self):
        state, town, npc, _, system = self.fixture()
        town.faction_id = npc.faction_id = ''
        choice = DialogueOption('listen', 'Listen', '', trust_delta=1, familiarity_delta=3)
        system.apply_option(npc, choice, 600)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'dialogue.db'
            database = WorldDatabase.create(path, 'Dialogue regression', b'test'.hex())
            try:
                database.save_state(turn=600, tile_deltas={}, player_id=1,
                                    position=WorldPos(0, 0, 0), inventory={},
                                    vitals={'hp': 100, 'max_hp': 100}, sim_state=state.to_dict())
                self.assertEqual(database.verify(), [])
            finally:
                database.close()
            reopened = WorldDatabase.open(path)
            try:
                loaded = LivingWorldState.from_dict(reopened.load_sim_state())
                self.assertEqual(reopened.verify(), [])
                self.assertFalse(DialogueSystem(loaded, b'test').apply_option(loaded.npcs[npc.uid], choice, 601))
            finally:
                reopened.close()

    def test_fallback_community_does_not_scan_population(self):
        state, town, _, _, _ = self.fixture()
        class IndexedDict(dict):
            def values(self):
                raise AssertionError('unbounded population scan')
        state.npcs = IndexedDict(state.npcs)
        self.assertEqual(DialogueSystem.settlement_standing(state, town.uid), 30)


class DialogueDataValidationTests(unittest.TestCase):
    def data(self):
        return {'version': 1, 'nodes': [
            {'id': 'work', 'parent': 'root', 'label': 'Work',
             'paragraphs': ['Work has causes.'], 'links': [],
             'variants': [{'id': 'wet', 'priority': 10,
                           'requirements': {'fact': 'environment.rain', 'op': 'gte', 'value': 1},
                           'paragraphs': ['Wet work has different causes.']}]}
        ]}

    def test_bad_ids_references_cycles_and_types_are_rejected(self):
        mutations = [lambda r: r['nodes'].append(copy.deepcopy(r['nodes'][0])),
                     lambda r: r['nodes'][0].update(id='../private'),
                     lambda r: r['nodes'][0].update(parent='missing'),
                     lambda r: r['nodes'][0].update(parent='work'),
                     lambda r: r['nodes'][0].update(paragraphs='plain text'),
                     lambda r: r['nodes'][0].update(links=[{'phrase': 'causes', 'topic': 'missing'}]),
                     lambda r: r['nodes'][0]['variants'][0].update(priority=True),
                     lambda r: r['nodes'][0]['variants'][0].update(requirements={'fact': 'environment.rain', 'op': 'gte', 'value': 'rain'}),
                     lambda r: r['nodes'][0]['variants'][0].update(requirements={'fact': 'environment.rain', 'op': [], 'value': 1})]
        for mutation in mutations:
            raw = self.data()
            mutation(raw)
            with self.assertRaises(ValueError):
                validate_dialogue_data(raw)

    def test_causal_selection_and_negated_unknown_fail_closed(self):
        raw = self.data()
        raw['nodes'][0]['requirements'] = {'not': {'fact': 'player.wanted', 'op': 'eq', 'value': True}}
        tree = validate_dialogue_data(raw)
        self.assertFalse(tree.allows('work', {}))
        self.assertFalse(tree.allows('work', {'player.wanted': None}))
        self.assertTrue(tree.allows('work', {'player.wanted': False}))
        self.assertFalse(tree.allows('work', {'player.wanted': True}))
        self.assertEqual(tree.paragraphs('work', {}, b'test', 'npc:test', 600), ('Work has causes.',))
        self.assertEqual(tree.paragraphs('work', {'environment.rain': 2}, b'test', 'npc:test', 600), ('Wet work has different causes.',))

    def test_ties_are_deterministic_and_independent_of_json_order(self):
        raw = self.data()
        raw['nodes'][0]['variants'].append({'id': 'rain', 'priority': 10,
                                          'requirements': {'fact': 'environment.rain', 'op': 'gte', 'value': 1},
                                          'paragraphs': ['Rain changes work.']})
        first = validate_dialogue_data(raw)
        raw['nodes'][0]['variants'].reverse()
        second = validate_dialogue_data(raw)
        self.assertEqual(first.paragraphs('work', {'environment.rain': 2}, b'test', 'npc:test', 600),
                         second.paragraphs('work', {'environment.rain': 2}, b'test', 'npc:test', 600))


if __name__ == '__main__':
    unittest.main()
