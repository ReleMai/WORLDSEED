import contextlib
import hashlib
import io
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from tools import soak_matrix
from tools.workspace_preflight import check_snapshot


class DevelopmentWorkflowTests(unittest.TestCase):
    def test_snapshot_rejects_partial_modified_and_wrong_baseline(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'a.txt').write_bytes(b'hello')
            manifest = {'commit': 'abc', 'tree': [{'path': 'a.txt', 'sha': hashlib.sha1(b'blob 5\0hello').hexdigest()}]}
            self.assertEqual([], check_snapshot(root, manifest, 'abc'))
            self.assertTrue(check_snapshot(root, manifest, 'new'))
            (root / 'a.txt').write_bytes(b'changed')
            self.assertIn('modified: a.txt', check_snapshot(root, manifest, 'abc'))
            (root / 'a.txt').unlink()
            self.assertIn('missing: a.txt', check_snapshot(root, manifest, 'abc'))

    def test_snapshot_paths_cannot_escape_root(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest = {'commit': 'abc', 'tree': [{'path': '../outside', 'sha': 'anything'}]}
            self.assertIn('unsafe snapshot path: ../outside', check_snapshot(Path(temp), manifest, 'abc'))

    def test_long_soak_requires_explicit_opt_in(self):
        with patch('sys.argv', ['soak', '--years', '25']), patch.object(soak_matrix, 'run_one') as run:
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                soak_matrix.main()
            self.assertEqual(2, error.exception.code)
            run.assert_not_called()

    def test_soak_progress_stays_off_json_stdout_and_stops(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with soak_matrix.progress('seed', interval=.01) as report:
                report('simulation')
                time.sleep(.04)
            snapshot = err.getvalue()
            time.sleep(.03)
        self.assertEqual('', out.getvalue())
        self.assertIn('SOAK RUNNING seed: simulation', snapshot)
        self.assertEqual(snapshot, err.getvalue())

    def test_soak_default_is_one_seed_year_and_json_is_valid(self):
        with patch('sys.argv', ['soak', '--json']), patch.object(soak_matrix, 'run_one', return_value={'errors': []}) as run:
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(0, soak_matrix.main())
            run.assert_called_once_with('matrix-0', 1, 'full', False)
            self.assertEqual('{"errors": []}\n', out.getvalue())


if __name__ == '__main__':
    unittest.main()
