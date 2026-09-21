import unittest

from worldseed.presentation.local_terrain import (
    DIRECTIONS_8, can_blend, terrain_family, transition_profile, transition_signature,
)


class LocalTerrainTransitionRuleTests(unittest.TestCase):
    def test_all_eight_directions_exist(self):
        self.assertEqual([d for d, _, _ in DIRECTIONS_8], [
            'north', 'south', 'west', 'east',
            'northwest', 'northeast', 'southwest', 'southeast',
        ])

    def test_natural_materials_blend_but_hard_features_do_not(self):
        self.assertTrue(can_blend('core:grass', 'core:forest'))
        self.assertTrue(can_blend('core:sand', 'core:water'))
        self.assertTrue(can_blend('core:rock', 'core:tundra'))
        self.assertFalse(can_blend('core:grass', 'core:ruin_wall'))
        self.assertFalse(can_blend('core:grass', 'core:iron_vein'))
        self.assertFalse(can_blend('core:grass', None))

    def test_visual_families_avoid_needless_blur(self):
        self.assertEqual(terrain_family('core:river'), 'water')
        self.assertEqual(terrain_family('core:river_shallow'), 'water')
        self.assertEqual(terrain_family('core:floodplain'), 'grass')
        self.assertTrue(can_blend('core:river', 'core:water'))
        self.assertTrue(can_blend('core:ocean_shallow','core:ocean_shelf'))
        self.assertTrue(can_blend('core:grass', 'core:floodplain'))
        depth,alpha=transition_profile('core:grass','core:floodplain')
        self.assertGreaterEqual(depth,7)
        self.assertLess(alpha,110)

    def test_transition_profiles_prefer_soft_shorelines(self):
        shore = transition_profile('core:sand', 'core:water')
        rock_edge = transition_profile('core:rock', 'core:tundra')
        tilled = transition_profile('core:tilled_soil', 'core:grass')
        self.assertGreater(shore[0], rock_edge[0])
        self.assertGreater(shore[1], rock_edge[1])
        self.assertLessEqual(tilled[0], shore[0])

    def test_signature_contains_cardinals_and_corners(self):
        neighbors = {
            'north': 'core:forest', 'south': 'core:sand',
            'west': 'core:rock', 'east': 'core:water',
            'northwest': 'core:scrub', 'northeast': 'core:tundra',
            'southwest': 'core:floodplain', 'southeast': 'core:ruin_wall',
        }
        sig = dict(transition_signature('core:grass', neighbors))
        for direction in ('north', 'south', 'west', 'east', 'northwest', 'northeast'):
            self.assertIsNotNone(sig[direction])
        # Same-family ecotones feather softly; hard authored features stay crisp.
        self.assertIsNotNone(sig['southwest'])
        self.assertIsNone(sig['southeast'])


if __name__ == '__main__':
    unittest.main()
