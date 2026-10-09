import os

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from dataclasses import FrozenInstanceError
import importlib.util
import random
import unittest
from unittest.mock import patch

from worldseed.presentation import portraits

from worldseed.presentation.portraits import (
    PortraitComposer,
    portrait_catalog,
    portrait_spec,
    render_portrait,
    validate_portrait_catalog,
)
from worldseed.systems.state import LivingWorldState, NPCState


class PortraitIdentityTests(unittest.TestCase):
    def test_same_identity_is_deterministic_and_generation_order_independent(self):
        identifiers = [f'npc:portrait:{index}' for index in range(64)]
        forward = {uid: portrait_spec(b'portrait-world', uid, 'female') for uid in identifiers}
        backward = {uid: portrait_spec(b'portrait-world', uid, 'female') for uid in reversed(identifiers)}
        self.assertEqual(forward, backward)
        self.assertEqual(forward[identifiers[0]], portrait_spec(b'portrait-world', identifiers[0], 'female'))

    def test_seed_identity_and_sex_are_separate_deterministic_domains(self):
        baseline = portrait_spec(b'portrait-world', 'npc:portrait:one', 'male')
        changed = (
            portrait_spec(b'another-world', 'npc:portrait:one', 'male'),
            portrait_spec(b'portrait-world', 'npc:portrait:two', 'male'),
            portrait_spec(b'portrait-world', 'npc:portrait:one', 'female'),
        )
        for spec in changed:
            self.assertNotEqual(baseline.facial_identity, spec.facial_identity)

    def test_catalog_order_does_not_change_identity_and_feature_domains_are_isolated(self):
        catalog = portrait_catalog()
        baseline = portrait_spec(b'portrait-world', 'npc:portrait:order', 'female')
        for section in ('parts', 'palettes'):
            for group, entries in catalog[section].items():
                catalog[section][group] = dict(reversed(list(entries.items())))
        with patch.object(portraits, '_catalog', return_value=catalog):
            self.assertEqual(baseline, portrait_spec(b'portrait-world', 'npc:portrait:order', 'female'))
        # Authoring one part cannot shift the unrelated feature RNG domains.
        catalog['parts']['hair']['core:additional_crop'] = dict(catalog['parts']['hair']['core:crop'])
        with patch.object(portraits, '_catalog', return_value=catalog):
            updated = portrait_spec(b'portrait-world', 'npc:portrait:order', 'female')
        for name in baseline.__dataclass_fields__:
            if name != 'hair':
                self.assertEqual(getattr(baseline, name), getattr(updated, name), name)

    def test_aging_preserves_facial_identity_and_base_hair_palette(self):
        specs = [portrait_spec(b'portrait-world', 'npc:portrait:aging', 'female', age=age)
                 for age in (12, 35, 80)]
        self.assertEqual(len({spec.age_stage for spec in specs}), 3)
        self.assertEqual(len({spec.facial_identity for spec in specs}), 1)
        self.assertEqual(len({spec.hair_palette for spec in specs}), 1)

    def test_large_population_has_diverse_composites(self):
        specs = [portrait_spec(b'portrait-population', f'npc:{index}', 'female' if index % 2 else 'male')
                 for index in range(500)]
        self.assertGreater(len({spec.facial_identity for spec in specs}), 480)
        for feature in ('head', 'nose', 'eyes', 'brows', 'mouth', 'hair', 'skin_palette'):
            self.assertGreater(len({getattr(spec, feature) for spec in specs}), 1, feature)

    def test_descriptor_is_immutable_and_does_not_consume_global_randomness(self):
        before = random.getstate()
        spec = portrait_spec(b'portrait-world', 'npc:portrait:immutable', 'male')
        self.assertEqual(before, random.getstate())
        with self.assertRaises(FrozenInstanceError):
            spec.hair = 'changed'

    def test_catalog_rejects_missing_required_data(self):
        validate_portrait_catalog(portrait_catalog())
        for invalid in (None, [], {}, {'version': -1}):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    validate_portrait_catalog(invalid)

    def test_catalog_is_isolated_and_rejects_invalid_pools_weights_and_colors(self):
        original = portrait_catalog()
        copy = portrait_catalog()
        copy['parts']['head'].clear()
        self.assertEqual(portrait_catalog(), original)
        malformed = []
        empty = portrait_catalog()
        empty['parts']['eyes'] = {}
        malformed.append(empty)
        missing = portrait_catalog()
        del missing['parts']['nose']
        malformed.append(missing)
        invalid_id = portrait_catalog()
        pool = invalid_id['parts']['head']
        pool['not a namespaced id'] = pool.pop(next(iter(pool)))
        malformed.append(invalid_id)
        for weight in (-1, 1.5):
            invalid_weight = portrait_catalog()
            variant = next(iter(invalid_weight['parts']['head'].values()))
            variant['weights']['male'] = weight
            malformed.append(invalid_weight)
        invalid_color = portrait_catalog()
        palette = next(iter(invalid_color['palettes']['skin'].values()))
        palette['colors'][0][0] = 256
        malformed.append(invalid_color)
        for invalid in malformed:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    validate_portrait_catalog(invalid)

    def test_catalog_rejects_missing_geometry_invalid_dimensions_and_styles(self):
        for group, parameter, invalid in (
            ('head', 'width', None), ('head', 'width', 0),
            ('ears', 'height', -1), ('brows', 'thick', 0),
            ('neck', 'width', True), ('hair', 'style', 'unsupported'),
        ):
            catalog = portrait_catalog()
            definition = next(iter(catalog['parts'][group].values()))
            if invalid is None:
                del definition[parameter]
            else:
                definition[parameter] = invalid
            with self.subTest(group=group, parameter=parameter, value=invalid):
                with self.assertRaises(ValueError):
                    validate_portrait_catalog(catalog)


@unittest.skipUnless(importlib.util.find_spec('pygame'), 'requires pygame-ce')
class PortraitRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pygame
        cls.pg = pygame

    def pixels(self, surface):
        return self.pg.image.tobytes(surface, 'RGBA')

    def test_composed_image_has_transparency_and_reproducible_pixels(self):
        spec = portrait_spec(b'portrait-world', 'npc:portrait:render', 'female')
        first = render_portrait(spec, 128)
        second = render_portrait(portrait_spec(b'portrait-world', 'npc:portrait:render', 'female'), 128)
        self.assertEqual(first.get_size(), (128, 128))
        self.assertTrue(first.get_flags() & self.pg.SRCALPHA)
        self.assertEqual(self.pixels(first), self.pixels(second))
        alpha = self.pixels(first)[3::4]
        self.assertIn(0, alpha)
        self.assertIn(255, alpha)

    def test_distinct_composites_and_age_stages_change_rendered_image(self):
        population = [render_portrait(portrait_spec(b'portrait-images', f'npc:{index}',
                                                    'female' if index % 2 else 'male'), 96)
                      for index in range(20)]
        self.assertEqual(len({self.pixels(surface) for surface in population}), 20)
        aging = [render_portrait(portrait_spec(b'portrait-world', 'npc:portrait:aging', 'male', age=age), 96)
                 for age in (12, 35, 80)]
        self.assertEqual(len({self.pixels(surface) for surface in aging}), 3)

    def test_repeated_frames_reuse_surface_and_cache_is_bounded(self):
        composer = PortraitComposer(max_entries=4)
        spec = portrait_spec(b'portrait-world', 'npc:portrait:cached', 'female')
        surface = composer.render(spec, 128)
        render_count = composer.render_count
        for _ in range(30):
            self.assertIs(composer.render(portrait_spec(b'portrait-world', 'npc:portrait:cached', 'female'), 128), surface)
        self.assertEqual(composer.render_count, render_count)
        small = composer.render(spec, 64)
        self.assertIsNot(small, surface)
        self.assertEqual(small.get_size(), (64, 64))
        elder = composer.render(portrait_spec(b'portrait-world', 'npc:portrait:cached', 'female', age=80), 128)
        self.assertIsNot(elder, surface)
        self.assertNotEqual(self.pixels(elder), self.pixels(surface))
        for index in range(20):
            composer.render(portrait_spec(b'portrait-world', f'npc:cache:{index}', 'male'), 64)
            self.assertLessEqual(composer.cache_size, 4)
        composer.clear()
        self.assertEqual(composer.cache_size, 0)

    def test_presenting_a_portrait_does_not_mutate_npc_or_simulation_state(self):
        state = LivingWorldState()
        npc = NPCState('npc:portrait:state', 'Eda', 35, 'healer', ['patient'], 1, 2, 0, '', '')
        state.npcs[npc.uid] = npc
        before = state.to_dict()
        rng_before = random.getstate()
        composer = PortraitComposer(max_entries=4)
        for size in (64, 128, 96, 128):
            composer.render(portrait_spec(b'portrait-state', npc.uid, npc.sex, age=npc.age), size)
        self.assertEqual(state.to_dict(), before)
        self.assertEqual(random.getstate(), rng_before)

    def test_byte_budget_evicts_least_recent_portraits_and_skips_oversized_images(self):
        composer = PortraitComposer(max_entries=10, max_bytes=2 * 64 * 64 * 4)
        specs = [portrait_spec(b'portrait-budget', f'npc:{index}', 'female') for index in range(3)]
        first = composer.render(specs[0], 64)
        second = composer.render(specs[1], 64)
        self.assertIs(composer.render(specs[0], 64), first)
        composer.render(specs[2], 64)
        self.assertEqual(composer.cache_size, 2)
        self.assertLessEqual(composer.cache_bytes, composer.max_bytes)
        self.assertIs(composer.render(specs[0], 64), first)
        self.assertIsNot(composer.render(specs[1], 64), second)
        size_before, bytes_before = composer.cache_size, composer.cache_bytes
        oversized = composer.render(specs[0], 128)
        self.assertEqual((composer.cache_size, composer.cache_bytes), (size_before, bytes_before))
        self.assertIsNot(composer.render(specs[0], 128), oversized)
        composer.clear()
        self.assertEqual((composer.cache_size, composer.cache_bytes), (0, 0))


if __name__ == '__main__':
    unittest.main()
