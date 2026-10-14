"""Snapshot optimization keeps retry-safe detached checkpoint semantics."""
from copy import deepcopy
from dataclasses import asdict, dataclass
import unittest

from tools.save_capture_probe import measure, prepared_state
from worldseed.systems.state import LivingWorldState, NPCState


class SaveCaptureSnapshotTests(unittest.TestCase):
    def test_memoized_actor_snapshot_equals_full_legacy_snapshot(self):
        state=prepared_state(5)
        self.assertEqual(state.checkpoint_snapshot(),deepcopy(state.to_dict()))
        self.assertEqual(state.to_dict()['npcs'],
                         {uid:asdict(npc) for uid,npc in state.npcs.items()})

    def test_nested_mutable_dataclass_and_tuple_payload_fallback(self):
        @dataclass
        class Nested:
            code: str
            amounts: list[int]
        state=prepared_state(1)
        actor=next(iter(state.npcs.values()))
        actor.tasks=[{'steps':[1,{'nested':Nested('item',[3,5])}]}]
        actor.memories=[{'path':(2,3),'history':[{'result':'ok'}]}]
        actual=state.to_dict()['npcs'][actor.uid]
        expected=asdict(actor)
        self.assertEqual(actual,expected)
        actor.tasks[0]['steps'][1]['nested'].amounts[0]=99
        self.assertEqual(actual['tasks'][0]['steps'][1]['nested']['amounts'],[3,5])

    def test_new_serialization_preserves_key_and_value_types(self):
        state=prepared_state(2)
        actor=next(iter(state.npcs.values()))
        actor.inventory={'core:stone':7}
        actor.relationships={'friend':{'trust':9}}
        actor.traits=['curious','patient']
        actual=state.to_dict()['npcs'][actor.uid]
        self.assertEqual(actual,asdict(actor))
        self.assertIsNot(actual['inventory'],actor.inventory)
        self.assertIsNot(actual['relationships']['friend'],actor.relationships['friend'])
        self.assertIsNot(actual['traits'],actor.traits)

    def test_nested_actor_data_remains_detached_from_live_state(self):
        state=prepared_state(2)
        actor=state.npcs['probe:npc:00000']
        snapshot=state.checkpoint_snapshot()
        actor.inventory['core:stone']=90
        actor.memories[0]['note']='live state changed'
        state.npcs['probe:npc:00001'].x=-600
        state.player_wounds.append({'kind':'new live wound'})
        saved=snapshot['npcs']['probe:npc:00000']
        self.assertEqual(saved['inventory'],{'core:stone':0})
        self.assertEqual(saved['memories'][0]['note'],'distant actor')
        self.assertEqual(snapshot['npcs']['probe:npc:00001']['x'],10001)
        self.assertEqual(snapshot['player_wounds'],[])
        saved['inventory']['core:stone']=200
        saved['memories'][0]['note']='snapshot changed'
        self.assertEqual(actor.inventory['core:stone'],90)
        self.assertEqual(actor.memories[0]['note'],'live state changed')

    def test_all_other_nested_state_fields_keep_deepcopy_semantics(self):
        state=LivingWorldState(player_name='snapshot')
        state.player_wounds=[{'site':'left', 'details':{'depth':2}}]
        state.homesteads={'h':{'stored':{'core:stone':4},'nested':{'value':[1]}}}
        snap=state.checkpoint_snapshot()
        state.player_wounds[0]['details']['depth']=8
        state.homesteads['h']['nested']['value'].append(2)
        self.assertEqual(snap['player_wounds'][0]['details']['depth'],2)
        self.assertEqual(snap['homesteads']['h']['nested']['value'],[1])

    def test_synthetic_probe_checks_payloads_without_timing_thresholds(self):
        report=measure(3,1)
        self.assertEqual(report['npc_count'],3)
        self.assertTrue(report['identity_verified'])
        self.assertGreater(report['json_payload_bytes'],100)
        with self.assertRaises(ValueError):
            measure(2,0)
        with self.assertRaises(ValueError):
            prepared_state(20001)


if __name__=='__main__':
    unittest.main()
