"""Regression checks for CI progress reporting and failure propagation."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools.run_ci_check import run
from tools.validate_image_assets import image_issues
from PIL import Image


class CIDiagnosticsTests(unittest.TestCase):
    def test_success_and_failure_are_reported_with_original_exit_code(self):
        with tempfile.TemporaryDirectory() as temp:
            summary = Path(temp) / 'summary.md'
            previous = os.environ.get('GITHUB_STEP_SUMMARY')
            os.environ['GITHUB_STEP_SUMMARY'] = str(summary)
            try:
                self.assertEqual(run('good', [sys.executable, '-c', 'print("item passed")'], 5, .05), 0)
                self.assertEqual(run('bad', [sys.executable, '-c', 'print("item failed"); raise SystemExit(7)'], 5, .05), 7)
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
