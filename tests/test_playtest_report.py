"""Privacy, bounded parsing and offline-export contracts of Windows playtests."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import zipfile

from worldseed.playtest_report import (
    export_report, percentile, report_payload, safe_label, summarize_jsonl,
)


class PlaytestReportTests(unittest.TestCase):
    def test_redacts_raw_text_paths_and_player_names(self):
        lines = [
            json.dumps({'kind':'ui_input','key':'UI_ACTION:rename:/Users/Alice/secret'}),
            json.dumps({'kind':'session_start','world':'C:\\Users\\Alice\\saves\\Secret.db'}),
            json.dumps({'kind':'exception','where':'run_game','error':"RuntimeError('Private name')",
                        'traceback':'C:\\Users\\Alice\\mygame.py'}),
            json.dumps({'kind':'stage','name':'region_activation','elapsed_ms':41.5,'slow':True}),
            json.dumps({'kind':'command_end','command':'MoveCommand','turn':14,'minute':321}),
            json.dumps({'kind':'profile_summary','profile':{'stages':{'render.frame':{
                'count':120, 'p95_ms':32.1, 'lifetime_worst_ms':77.9}}}}),
        ]
        report = summarize_jsonl(lines)
        text = json.dumps(report)
        for secret in ('Alice','secret','Secret.db','Private name','mygame.py'):
            self.assertNotIn(secret, text)
        self.assertEqual(report['exceptions'][0]['exception_type'],'RuntimeError')
        self.assertEqual(report['runtime_profile']['render.frame']['p95_ms'],32.1)
        self.assertEqual(report['profile_status'],'captured')
        self.assertEqual(report['input_categories']['ui_action'],1)
        self.assertEqual(report['last_progress']['turn'],14)

    def test_bounded_aggregation_and_invalid_values(self):
        self.assertIsNone(percentile([], 0.95))
        self.assertEqual(percentile([10, 20, 30], 0.95),29.0)
        self.assertEqual(safe_label('C:\\Users\\Private'),'redacted')
        data=summarize_jsonl(['{oops',json.dumps({'kind':'stage','name':'tick','elapsed_ms':-3}),
                              json.dumps({'kind':'stage','name':'tick','elapsed_ms':50})])
        self.assertEqual(data['events_read'],2)
        self.assertEqual(data['stage_timings']['tick']['samples'],1)

    def test_save_cost_is_reported_across_full_session_without_private_paths(self):
        events = [json.dumps({'kind':'save','backup':False,'elapsed_ms':amount,
                              'world':'C:\\\\Users\\\\Alice\\\\private.db'})
                  for amount in (192.0, 200.0, 214.0)]
        events += [json.dumps({'kind':'save','backup':True,'elapsed_ms':450.0})]
        events += [json.dumps({'kind':'realtime_advance'}) for _ in range(300)]
        result = summarize_jsonl(events)
        self.assertEqual(result['profile_status'], 'not_recorded')
        self.assertEqual(result['save_timings']['autosave']['samples'], 3)
        self.assertEqual(result['save_timings']['autosave']['p50_ms'], 200.0)
        self.assertEqual(result['save_timings']['autosave']['over_100ms'], 3)
        self.assertEqual(result['save_timings']['checkpoint']['worst_ms'], 450.0)
        self.assertEqual(result['save_timings']['checkpoint']['samples'], 1)
        self.assertNotIn('Alice', json.dumps(result))
        self.assertEqual(result['event_counts']['save'], 4)

    def test_export_has_only_sanitized_report_and_instructions(self):
        with TemporaryDirectory() as temporary:
            root=Path(temporary)
            folder=root/'logs';folder.mkdir()
            (folder/'WORLDSEED_DEBUG_20261014_123456_99.jsonl').write_text(
                json.dumps({'kind':'ui_input','key':'my personal test phrase'})+'\n'+
                json.dumps({'kind':'stage','name':'render','elapsed_ms':18.0})+'\n')
            (root/'WORLDSEED_CRASH.log').write_text('C:\\Users\\Alice\\private')
            (root/'saves').mkdir()
            (root/'saves'/'private.db').write_bytes(b'PRIVATE_SAVE_BYTES')
            output=export_report(root)
            with zipfile.ZipFile(output) as z:
                self.assertEqual(set(z.namelist()),{'report.json','HOW_TO_SHARE.txt'})
                contents=z.read('report.json').decode()
                for secret in ('personal test phrase','Alice','PRIVATE_SAVE_BYTES','private.db'):
                    self.assertNotIn(secret,contents)
                payload=json.loads(contents)
                self.assertTrue(payload['crash_file_present'])
                self.assertTrue(payload['session_found'])
                self.assertFalse(payload['privacy']['automatic_upload'])
                self.assertEqual(payload['session']['stage_timings']['render']['p95_ms'],18.0)
                self.assertEqual(report_payload(root)['schema'],'worldseed-playtest-report-v1')


if __name__=='__main__':
    unittest.main()
