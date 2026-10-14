"""Enforce that a source archive is never confused with a Windows bundle."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.verify_windows_bundle import validate_bundle


class WindowsBundleLayoutTests(unittest.TestCase):
    def test_source_root_does_not_masquerade_as_compiled_game(self):
        root = Path(__file__).resolve().parents[1]
        for name in ('PLAY_WORLDSEED_TEST.bat', 'EXPORT_WORLDSEED_REPORT.bat'):
            self.assertFalse((root / name).exists(), name + ' must only be copied into the Windows build')
            self.assertTrue((root / 'packaging' / 'windows' / name).is_file())

    def test_verified_bundle_needs_exe_internal_and_launcher(self):
        with TemporaryDirectory() as temporary:
            folder = Path(temporary)
            with self.assertRaisesRegex(ValueError, 'missing'):
                validate_bundle(folder, minimum_exe_bytes=16)
            (folder / '_internal').mkdir()
            (folder / '_internal' / 'base_library.zip').write_bytes(b'library')
            (folder / 'WORLDSEED.exe').write_bytes(b'MZ' + b'\0' * 64)
            for script in ('PLAY_WORLDSEED_TEST.bat', 'EXPORT_WORLDSEED_REPORT.bat'):
                (folder / script).write_text('WORLDSEED.exe', encoding='utf-8')
            (folder / 'README_PLAYTEST.txt').write_text('Readme', encoding='utf-8')
            (folder / 'PLAYTEST_BUILD.json').write_text(json.dumps({
                'commit': '1'*40, 'build_kind': 'windows-one-dir'
            }), encoding='utf-8')
            good = validate_bundle(folder, minimum_exe_bytes=16)
            self.assertEqual(good['executable'], 'WORLDSEED.exe')
            self.assertEqual(good['commit'], '1'*40)
            (folder / '_internal' / 'base_library.zip').unlink()
            with self.assertRaisesRegex(ValueError, '_internal'):
                validate_bundle(folder, minimum_exe_bytes=16)

    def test_source_archive_never_passes_windows_build_check(self):
        with TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / 'RUN_WORLDSEED.bat').write_text('python run_worldseed.py', encoding='utf-8')
            (folder / 'run_worldseed.py').write_text('print("source")', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'WORLDSEED.exe'):
                validate_bundle(folder, minimum_exe_bytes=16)


if __name__ == '__main__':
    unittest.main()
