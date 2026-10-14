"""M2 benchmark summary does not misrepresent synthetic renderer throughput."""
import unittest

from tools.m2_validation import summarize


def fake_scene(scene, npc, movement=1.0):
    return {
        'scene':scene,'frames_measured':40,'size':[1280,720],
        'save_bytes':123,'state_json_bytes':456,
        'authority_unchanged':True,'interrupted':False,
        'state_counts':{'npcs':npc},
        'hardware':{'python':'3.11'},'build_identity':{'git_revision':'test'},
        'timings':{'stages':{
            'render.frame':{'count':40,'p50_ms':9.0,'p95_ms':11.0,
                            'p99_ms':13.0,'worst_ms':14.0,'over_100ms_count':0},
            'simulation.free_movement':{'count':40,'p50_ms':movement,
                                         'p95_ms':movement*1.2},
        }},
    }


class M2ValidationTests(unittest.TestCase):
    def test_scaling_threshold_computes_relative_not_absolute_ms(self):
        report=summarize({'scenes':[fake_scene('forest',0)]},
                         [fake_scene('large_save',1000,1.0),
                          fake_scene('large_save',10000,1.3)],
                         {'results':[]})
        self.assertAlmostEqual(report['movement_p50_ratio_10000_over_1000'],1.3)
        self.assertFalse(report['movement_within_proposed_20_percent'])
        self.assertTrue(report['not_live_1080p_certification'])
        self.assertEqual(report['reference_scenes'][0]['frame']['p95_ms'],11)

    def test_does_not_claim_scaling_success_without_samples(self):
        report=summarize({'scenes':[]},[],{'results':[]})
        self.assertIsNone(report['movement_p50_ratio_10000_over_1000'])
        self.assertFalse(report['movement_within_proposed_20_percent'])


if __name__=='__main__':
    unittest.main()
