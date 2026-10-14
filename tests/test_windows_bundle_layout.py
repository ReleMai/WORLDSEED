"""Enforce that a source archive is never confused with a Windows bundle."""
from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.verify_windows_bundle import validate_bundle
from run_worldseed import _enable_bundled_playtest_profiling


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

    def test_bundled_playtest_records_timing_even_if_exe_is_launched_directly(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            exe = root / 'WORLDSEED.exe'
            marker = root / 'PLAYTEST_BUILD.json'
            marker.write_text(json.dumps({'commit':'a'*40, 'build_kind':'windows-one-dir'}))
            with (patch.object(sys, 'frozen', True, create=True),
                  patch.object(sys, 'executable', str(exe)),
                  patch.dict(os.environ, {'WORLDSEED_PROFILE': '0'})):
                self.assertTrue(_enable_bundled_playtest_profiling())
                self.assertEqual(os.environ['WORLDSEED_PROFILE'], '1')
                marker.write_text(json.dumps({'commit':'bad', 'build_kind':'windows-one-dir'}))
                os.environ['WORLDSEED_PROFILE'] = '0'
                self.assertFalse(_enable_bundled_playtest_profiling())
                self.assertEqual(os.environ['WORLDSEED_PROFILE'], '0')
            marker.write_text(json.dumps({'commit':'a'*40, 'build_kind':'windows-one-dir'}))
            with (patch.object(sys, 'frozen', False, create=True),
                  patch.object(sys, 'executable', str(exe)),
                  patch.dict(os.environ, {'WORLDSEED_PROFILE': '0'})):
                self.assertFalse(_enable_bundled_playtest_profiling())
                self.assertEqual(os.environ['WORLDSEED_PROFILE'], '0')

    def test_source_archive_never_passes_windows_build_check(self):
        with TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / 'RUN_WORLDSEED.bat').write_text('python run_worldseed.py', encoding='utf-8')
            (folder / 'run_worldseed.py').write_text('print("source")', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'WORLDSEED.exe'):
                validate_bundle(folder, minimum_exe_bytes=16)


if __name__ == '__main__':
    unittest.main()
