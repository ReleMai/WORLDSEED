"""Regression checks for CI progress reporting and failure propagation."""
import os
import contextlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from tools.run_ci_check import run
from tools.validate_image_assets import image_issues
from PIL import Image


class CIDiagnosticsTests(unittest.TestCase):
    def test_process_containment_startup_error_is_reported(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), patch('tools.run_ci_check.ProcessTree', side_effect=OSError('containment unavailable')):
            self.assertEqual(1, run('startup-error', [sys.executable, '-c', 'pass'], 1))
        self.assertIn('containment unavailable', output.getvalue())

    def check_command(self, command, timeout=.3):
        return subprocess.run(
            [sys.executable, '-u', str(Path(__file__).resolve().parents[1] / 'tools' / 'run_ci_check.py'),
             '--name', 'deadline', '--timeout', str(timeout), '--heartbeat', '.1', '--',
             sys.executable, '-c', command], capture_output=True, text=True, timeout=6)

    def test_closed_output_does_not_disable_deadline(self):
        started = time.monotonic()
        result = self.check_command('import os,time; os.close(1); os.close(2); time.sleep(20)')
        self.assertEqual(124, result.returncode, result.stdout + result.stderr)
        self.assertLess(time.monotonic() - started, 4)

    def test_exited_parent_with_live_child_times_out_and_cleans_descendants(self):
        with tempfile.TemporaryDirectory() as temp:
            marker = Path(temp) / 'escaped.txt'
            child = f'import time,pathlib; time.sleep(1.5); pathlib.Path({str(marker)!r}).touch()'
            command = f'import subprocess,sys; subprocess.Popen([sys.executable,"-c",{child!r}])'
            result = self.check_command(command)
            self.assertEqual(124, result.returncode, result.stdout + result.stderr)
            time.sleep(1.6)
            self.assertFalse(marker.exists(), 'descendant survived timeout cleanup')

    def test_output_without_newlines_is_drained(self):
        result = self.check_command('import sys; sys.stdout.write("x"*200000+"TAIL")', timeout=3)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('TAIL', result.stdout)

    def test_nonfinite_deadlines_are_rejected(self):
        for timeout, heartbeat in [(float('nan'), 1), (float('inf'), 1), (1, float('nan'))]:
            with self.assertRaises(ValueError):
                run('invalid', [sys.executable], timeout, heartbeat)

    def test_success_and_failure_are_reported_with_original_exit_code(self):
        with tempfile.TemporaryDirectory() as temp:
            summary = Path(temp) / 'summary.md'
            previous = os.environ.get('GITHUB_STEP_SUMMARY')
            os.environ['GITHUB_STEP_SUMMARY'] = str(summary)
            try:
                # Expected failures must not become false GitHub error annotations.
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(run('good', [sys.executable, '-c', 'print("item passed")'], 5, .05), 0)
                    self.assertEqual(run('bad', [sys.executable, '-c', 'print("item failed"); raise SystemExit(7)'], 5, .05), 7)
                self.assertIn('CHECK bad: FAIL', output.getvalue())
            finally:
                if previous is None:
                    os.environ.pop('GITHUB_STEP_SUMMARY', None)
                else:
                    os.environ['GITHUB_STEP_SUMMARY'] = previous
            self.assertIn('good: PASS', summary.read_text())
            self.assertIn('bad: FAIL', summary.read_text())

    def test_stalled_check_exits_124_and_reports_heartbeat(self):
        command = [sys.executable, '-u', str(Path(__file__).resolve().parents[1] / 'tools' / 'run_ci_check.py'),
                   '--name', 'stall', '--timeout', '0.3', '--heartbeat', '0.05', '--',
                   sys.executable, '-c', 'import time; time.sleep(30)']
        result = subprocess.run(command, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 124, result.stdout + result.stderr)
        self.assertIn('CHECK RUNNING stall', result.stdout)
        self.assertIn('CHECK TIMEOUT stall', result.stdout)
        self.assertIn('CHECK stall: TIMEOUT', result.stdout)

    def test_image_audit_decodes_and_deduplicates_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            good = root / 'good.png'
            palette = root / 'palette.png'
            broken = root / 'broken.png'
            Image.new('RGBA', (24, 24), (100, 50, 20, 0)).save(good)
            Image.new('P', (24, 24)).save(palette)
            data = bytearray(good.read_bytes())
            data[data.index(b'IDAT') + 8] ^= 0xFF
            broken.write_bytes(data)
            count, issues = image_issues([good, good, palette, broken], root=root)
            self.assertEqual(count, 3)
            self.assertTrue(any('palette.png: mode=P' in line for line in issues), issues)
            self.assertTrue(any('broken.png: PNG decode failed' in line for line in issues), issues)


if __name__ == '__main__':
    unittest.main()
