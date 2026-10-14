"""Pure fixture-manifest regressions (no world generation or pygame dependency)."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tools.m3_reference_scenes import SCENES, build_manifest, capture_suite, compare_manifests


def fake_report(name: str, png: str = '') -> dict:
    return {
        'scene': name, 'fixture_mode': 'prepared-synthetic-qa',
        'fixture_version': 1, 'seed': 'worldseed-reference-v1',
        'size': [1280, 720], 'zoom_tile_px': 28,
        'pygame': '2.5.8', 'driver': 'dummy', 'headless': True,
        'frames_measured': 2, 'authority_unchanged': True, 'interrupted': False,
        'authority_fingerprint': name + '-state',
        'pixel_sha256': ('%064x' % (SCENES.index(name) + 1)),
        'png': png or ('/tmp/' + name + '.png'),
    }


class M3ReferenceManifestTests(unittest.TestCase):
    def test_complete_suite_has_four_unique_immutable_capture_ids(self):
        report = build_manifest([fake_report(scene) for scene in SCENES])
        self.assertEqual(list(report['scenes']), list(SCENES))
        self.assertEqual(report['status'], 'candidate-unreviewed')
        self.assertTrue(all(row['png'].startswith('pass-1/') for row in report['scenes'].values()))
        self.assertEqual(compare_manifests(report, report, require_reviewed=False), [])
        self.assertIn('approved', compare_manifests(report, report)[0])

    def test_partial_duplicate_interrupted_or_mutating_capture_rejected(self):
        base = [fake_report(s) for s in SCENES]
        for rows in (base[:-1], [base[0]] * 4):
            with self.assertRaises(ValueError):
                build_manifest(rows)
        for key, value in [('authority_unchanged', False), ('interrupted', True),
                           ('pixel_sha256', None), ('frames_measured', 0),
                           ('png', '/tmp/other.png')]:
            rows = [dict(row) for row in base]
            rows[0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                build_manifest(rows)

    def test_review_requirement_and_pixel_drift_detection(self):
        original = build_manifest([fake_report(scene) for scene in SCENES])
        approved = json.loads(json.dumps(original))
        approved['status'] = 'approved'
        self.assertEqual(compare_manifests(original, approved), [])
        modified = json.loads(json.dumps(original))
        modified['scenes']['camp']['pixel_sha256'] = 'f' * 64
        self.assertTrue(any('camp: pixel_sha256' in msg
                            for msg in compare_manifests(modified, approved)))

    def test_bounded_repeat_capture_detects_changed_pixels(self):
        with TemporaryDirectory() as d:
            def runner(scene, folder):
                Path(folder, scene + '.png').write_bytes(b'test image placeholder')
                return fake_report(scene, str(Path(folder, scene + '.png')))
            report = capture_suite(Path(d), runner, passes=2)
            self.assertEqual(report['passes_verified'], 2)
            self.assertEqual(json.loads(Path(d, 'candidate-manifest.json').read_text()), report)
            def drifting(scene, folder):
                row = runner(scene, folder)
                if folder.name == 'pass-2' and scene == 'camp':
                    row['pixel_sha256'] = 'e' * 64
                return row
            with self.assertRaisesRegex(ValueError, 'repeat scene instability'):
                capture_suite(Path(d) / 'bad', drifting, passes=2)
            with self.assertRaises(ValueError):
                capture_suite(Path(d) / 'invalid', runner, passes=3)


if __name__ == '__main__':
    unittest.main()
