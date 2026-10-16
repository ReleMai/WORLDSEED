"""Recovered gameplay errors remain discoverable independently of the EXE."""
from __future__ import annotations

import contextlib
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import traceback
import unittest
from unittest.mock import patch

from worldseed.debug import write_crash_report


class CrashReportPathTests(unittest.TestCase):
    def test_full_traceback_is_kept_in_primary_report_and_logs_copy(self):
        try:
            raise TypeError('indoor render ordering failed')
        except TypeError:
            text = traceback.format_exc()
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            primary = write_crash_report(text, root)
            self.assertEqual(root / 'WORLDSEED_CRASH.log', primary)
            self.assertEqual(text, primary.read_text())
            self.assertEqual(text, (root / 'logs' / 'WORLDSEED_CRASH.log').read_text())
            # This is one bounded latest report, not an unbounded per-frame log.
            write_crash_report('next traceback', root)
            self.assertEqual('next traceback', primary.read_text())
            self.assertEqual(2, len(list(root.rglob('*.log'))))

    def test_failed_convenience_copy_preserves_primary_and_recovery(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = io.StringIO()
            with patch.object(Path, 'mkdir', side_effect=OSError('read-only logs')), \
                 contextlib.redirect_stderr(output):
                primary = write_crash_report('original full traceback', root)
            self.assertEqual('original full traceback', primary.read_text())
            self.assertIn('logs copy failed', output.getvalue())
            self.assertIn(str(primary), output.getvalue())


if __name__ == '__main__':
    unittest.main()
