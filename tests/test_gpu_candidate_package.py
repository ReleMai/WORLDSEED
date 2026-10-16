"""The candidate must be an executable distribution with honest driver evidence."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import run_worldseed_gpu as launcher
from tools.package_gpu_playtest import NAME, LAUNCHERS, build_command, validate_bundle, write_archive
from tools.smoke_gpu_bundle import smoke, unsupported_context
from worldseed.presentation.gl_worldspace import GPUBackendUnavailable


def fake_bundle(root):
    (root / (NAME + '.exe')).write_bytes(b'MZ' + b'\0' * 1048576)
    (root / 'GPU_BUILD.json').write_text(json.dumps({
        'commit': 'a' * 40, 'build_kind': 'windows-gpu-candidate-one-dir'}))
    for name in LAUNCHERS:
        (root / name).write_text(NAME + '.exe')
    (root / 'README_GPU_TEST.txt').write_text('OpenGL 3.3 candidate')
    for name in ('data/terrain.json', 'assets/shaders/worldspace_sprite.vert',
                 'assets/shaders/worldspace_sprite.frag', 'assets/shaders/worldspace_post.vert',
                 'assets/shaders/worldspace_post.frag',
                 'assets/sprites/worldspace/trees/manifest.json',
                 'assets/sprites/worldspace/trees/tree_layers.b85'):
        path = root / '_internal' / 'worldseed' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('fixture')


def rejected_context(version='1.1.0'):
    return {'stage': 'rejected', 'events': [{'stage': 'preflight', 'evidence': {
        'native': {'version': version, 'current_context': '0x40000',
                   'renderer': 'GDI Generic', 'vendor': 'Microsoft Corporation'}}}]}


class GpuCandidatePackageTests(unittest.TestCase):
    def test_bundle_is_distinct_from_source_and_legacy_and_has_all_shaders(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            with self.assertRaisesRegex(ValueError, 'WORLDSEED_GPU.exe'):
                validate_bundle(folder)
            fake_bundle(folder)
            result = validate_bundle(folder)
            self.assertEqual(NAME + '.exe', result['executable'])
            self.assertFalse(result['native_hardware_accepted'])
            (folder / '_internal/worldseed/assets/shaders/worldspace_post.frag').unlink()
            with self.assertRaisesRegex(ValueError, 'worldspace_post.frag'):
                validate_bundle(folder)

    def test_bundle_excludes_player_databases_and_requires_exact_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            fake_bundle(folder)
            (folder / 'player.db').write_bytes(b'private')
            with self.assertRaisesRegex(ValueError, 'runtime/development'):
                validate_bundle(folder)
            (folder / 'player.db').unlink()
            (folder / 'GPU_BUILD.json').write_text(json.dumps({
                'commit': 'main', 'build_kind': 'windows-gpu-candidate-one-dir'}))
            with self.assertRaisesRegex(ValueError, 'exact commit'):
                validate_bundle(folder)

    def test_freezer_collects_native_backend_all_content_and_new_entrypoint(self):
        command = build_command(Path('dist'), Path('work'))
        self.assertIn('glcontext.wgl', command)
        self.assertIn('_moderngl', command)
        self.assertIn('moderngl', command)
        self.assertIn('glcontext', command)
        self.assertTrue(command[-1].endswith('run_worldseed_gpu.py'))
        additions = [command[i+1] for i, value in enumerate(command) if value == '--add-data']
        self.assertTrue(any(value.endswith(';worldseed/assets') for value in additions))
        self.assertTrue(any(value.endswith(';worldseed/data') for value in additions))

    def test_archive_contains_executable_and_assets_with_reproducible_checksum(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / NAME
            folder.mkdir()
            fake_bundle(folder)
            destination = Path(temporary) / 'candidate.zip'
            first = write_archive(folder, destination)
            self.assertEqual(first, write_archive(folder, destination))
            with zipfile.ZipFile(destination) as archive:
                self.assertIsNone(archive.testzip())
                self.assertIn(NAME + '/WORLDSEED_GPU.exe', archive.namelist())
                self.assertIn(NAME + '/_internal/worldseed/assets/shaders/worldspace_post.frag',
                              archive.namelist())
            self.assertIn(first, destination.with_suffix('.zip.sha256').read_text())

    def test_default_launcher_reuses_live_engine_and_qa_is_explicit(self):
        with patch('tools.worldseed_gpu_gameplay.run', return_value={'frames': 2}) as run:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(0, launcher.main(['--frames', '2']))
            self.assertIsNone(run.call_args.kwargs['prepared_scene'])
            self.assertNotIn('qa_weather', run.call_args.kwargs)
            with contextlib.redirect_stdout(io.StringIO()):
                launcher.main(['--prepared-scene', 'village_street', '--qa-weather', 'snow',
                               '--qa-season', 'winter', '--qa-time', 'noon'])
            self.assertEqual('village_street', run.call_args.kwargs['prepared_scene'])
            self.assertEqual('snow', run.call_args.kwargs['qa_weather'])
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            launcher.main(['--qa-weather', 'snow'])

    def test_launch_failure_retains_error_details_and_no_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / 'session.json'
            with patch('tools.worldseed_gpu_gameplay.run', side_effect=GPUBackendUnavailable('GL 1.1')):
                with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                    self.assertEqual(3, launcher.main(['--report', str(report)]))
            result = json.loads(report.read_text())
            self.assertEqual('gpu-candidate-unavailable', result['status'])
            self.assertFalse(result['native_hardware_accepted'])
            self.assertIn('GPUBackendUnavailable', report.with_suffix('.error.log').read_text())

    def test_unsupported_smoke_cannot_accept_crashes_or_unknown_versions(self):
        result = {'status': 'gpu-candidate-unavailable', 'error_type': 'GPUBackendUnavailable'}
        self.assertTrue(unsupported_context(result, rejected_context(), 3))
        self.assertFalse(unsupported_context(result, rejected_context(), -1073741819))
        self.assertFalse(unsupported_context(result, rejected_context('4.6'), 3))
        self.assertFalse(unsupported_context(result, rejected_context(''), 3))
        self.assertFalse(unsupported_context(result, {'stage': 'failed'}, 3))

    def test_smoke_launches_actual_executable_and_separates_rejection(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'evidence'
            def child(command, **kwargs):
                if '--selfcheck' in command:
                    return subprocess.CompletedProcess(command, 0,
                        'pg banner\n{"status": "gpu-bundle-selfcheck-ok"}', '')
                (output / 'render.json').write_text(json.dumps({
                    'status': 'gpu-candidate-unavailable', 'error_type': 'GPUBackendUnavailable'}))
                (output / 'render.context.json').write_text(json.dumps(rejected_context()))
                return subprocess.CompletedProcess(command, 3, 'unsupported GL', '')
            with patch('tools.smoke_gpu_bundle.subprocess.run', side_effect=child) as run:
                result = smoke(Path(temporary) / 'WORLDSEED_GPU.exe', output)
            self.assertEqual(2, run.call_count)
            self.assertEqual('unsupported-hosted-driver-rejected', result['render_status'])
            self.assertFalse(result['native_hardware_accepted'])
            self.assertTrue((output / 'SMOKE_RESULT.json').exists())

    def test_real_bundle_source_selfcheck_does_not_start_a_window_or_world(self):
        try:
            import pygame
            import moderngl
            import glcontext
        except ImportError:
            self.skipTest('optional GPU/pygame dependencies unavailable')
        with patch('pygame.display.set_mode', side_effect=AssertionError('window')):
            with patch('worldseed.app._load_context', side_effect=AssertionError('world')):
                result = launcher.self_check()
        self.assertEqual(12, result['tree_layers'])
        self.assertEqual(4, result['shaders'])
        self.assertFalse(result['native_hardware_accepted'])
        self.assertFalse(result['player_saves_opened'])


if __name__ == '__main__':
    unittest.main()
