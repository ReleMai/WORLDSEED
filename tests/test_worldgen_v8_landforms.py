from __future__ import annotations

import unittest

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.world.generator import WorldGenerator
from worldseed.world.landforms import LANDFORM_ALGORITHM, LandformSampler, Q


class WorldgenV8LandformPrototypeTests(unittest.TestCase):
    def test_landform_sampling_is_deterministic_and_bounded(self):
        coords = (
            (-4097, -2049), (-1536, 0), (-1, -1), (0, 0),
            (511, 1025), (2048, -3072), (8191, 4097),
        )
        a = LandformSampler(b"v8-landform-test")
        b = LandformSampler(b"v8-landform-test")
        one = [a.sample(x, y) for x, y in coords]
        two = [b.sample(x, y) for x, y in coords]
        self.assertEqual(one, two)
        for row in one:
            self.assertEqual(row.algorithm, LANDFORM_ALGORITHM)
            for value in (
                row.continentalness, row.tectonic_uplift, row.mountain_chain,
                row.structural_valley, row.basin, row.plateau,
                row.roughness, row.elevation,
            ):
                self.assertGreaterEqual(value, 0)
                self.assertLessEqual(value, Q)

    def test_prototype_contains_large_scale_landform_diversity(self):
        sampler = LandformSampler(b"v8-province-diversity")
        samples = {
            (x, y): sampler.sample(x, y)
            for y in range(-12288, 12289, 256)
            for x in range(-12288, 12289, 256)
        }
        provinces = {row.province for row in samples.values()}
        self.assertTrue({
            "oceanic_plain", "lowland", "upland", "mountain_chain",
            "basin", "plateau",
        }.issubset(provinces))
        ocean_fraction = sum(row.ocean for row in samples.values()) / len(samples)
        self.assertGreaterEqual(ocean_fraction, 0.08)
        self.assertLessEqual(ocean_fraction, 0.65)

    def test_major_mountain_strength_forms_connected_belts(self):
        sampler = LandformSampler(b"v8-range-coherence")
        step = 128
        values = {
            (x, y): sampler.sample(x, y).mountain_chain
            for y in range(-8192, 8193, step)
            for x in range(-8192, 8193, step)
        }
        high = [point for point, value in values.items() if value >= 32000]
        connected = 0
        for x, y in high:
            if any(
                values.get((x + dx, y + dy), 0) >= 32000
                for dx, dy in ((step, 0), (-step, 0), (0, step), (0, -step))
            ):
                connected += 1
        self.assertGreater(len(high), 20)
        self.assertGreaterEqual(connected * 100, len(high) * 85)

    def test_world_generator_exposes_prototype_without_changing_v7_fields(self):
        registry = ContentRegistry.load(DATA_DIR)
        gen = WorldGenerator(b"v8-non-authoritative", registry, version=7)
        pos = WorldPos(913, -1441, 0)
        before = gen.sample_fields(pos)
        proto = gen.prototype_landform_at(pos.x, pos.y)
        after = gen.sample_fields(pos)
        self.assertEqual(before, after)
        self.assertEqual(proto, LandformSampler(b"v8-non-authoritative").sample(pos.x, pos.y))


if __name__ == "__main__":
    unittest.main()
