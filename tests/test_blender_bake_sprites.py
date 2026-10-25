"""Bounds and output protection for the offline Blender authoring tool."""
import math
import tempfile
import unittest
from pathlib import Path

from tools.blender_bake_sprites import ROOT, normalization, validate_paths


class BlenderBakeContracts(unittest.TestCase):
    def test_normalization_preserves_proportions_and_grounds_center(self):
        points = [(-3, 2, -4), (1, 4, 4)]
        scale, offset = normalization(points)
        result = [tuple(p[i] * scale + offset[i] for i in range(3)) for p in points]
        self.assertEqual(result, [(-0.25, -0.125, 0), (0.25, 0.125, 1)])
        self.assertEqual(normalization(list(reversed(points))), (scale, offset))

    def test_empty_degenerate_and_nonfinite_geometry_fail(self):
        for points in ([], [(0, 0, 0)], [(0, math.nan, 1)], [(1, 2)]):
            with self.subTest(points=points), self.assertRaises(ValueError):
                normalization(points)

    def test_staging_never_overwrites_project_assets_or_prior_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "fixture.glb"
            source.write_bytes(b"test path validation only")
            for output in (ROOT / "worldseed/assets/bake", ROOT / "tests/bake", ROOT):
                with self.subTest(output=output), self.assertRaises(ValueError):
                    validate_paths(source, output)
            staged = Path(temp) / "staged"
            self.assertEqual(validate_paths(source, staged), (source.resolve(), staged.resolve()))
            staged.mkdir()
            (staged / "existing.png").write_bytes(b"keep")
            with self.assertRaises(ValueError):
                validate_paths(source, staged)
            self.assertEqual((staged / "existing.png").read_bytes(), b"keep")

    def test_resolved_symlink_cannot_redirect_staging_to_runtime_assets(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "fixture.glb"
            source.touch()
            link = Path(temp) / "redirect"
            try:
                link.symlink_to(ROOT / "worldseed/assets", target_is_directory=True)
            except OSError:
                self.skipTest("symlinks unavailable")
            with self.assertRaises(ValueError):
                validate_paths(source, link / "bake")
