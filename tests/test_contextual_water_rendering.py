from pathlib import Path
import unittest

from worldseed.presentation.local_terrain import contextual_display_id, edge_overlay_kind
from worldseed.presentation.visuals import VisualRegistry


class ContextualWaterRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.visuals = VisualRegistry.load_default()
        cls.root = Path('worldseed')

    def test_contextual_display_ids_distinguish_water_classes(self):
        self.assertEqual(contextual_display_id('core:river_shallow', {}), 'render:freshwater_shallow')
        self.assertEqual(contextual_display_id('core:river', {}), 'render:freshwater_deep')
        self.assertEqual(contextual_display_id('core:water', {'west': 'core:grass'}), 'render:ocean_shallow')
        self.assertEqual(contextual_display_id('core:water', {'west': 'core:river'}), 'render:estuary_mix')
        self.assertEqual(contextual_display_id('core:water', {'west': 'core:water'}), 'render:ocean_deep')

    def test_edge_overlay_logic_distinguishes_coasts_and_riverbanks(self):
        self.assertEqual(edge_overlay_kind('core:sand', 'core:water'), 'land_beach')
        self.assertEqual(edge_overlay_kind('core:grass', 'core:water'), 'land_shore')
        self.assertEqual(edge_overlay_kind('core:rock', 'core:water'), 'land_rock_shore')
        self.assertEqual(edge_overlay_kind('core:grass', 'core:river'), 'land_riverbank_soft')
        self.assertEqual(edge_overlay_kind('core:sand', 'core:river_shallow'), 'land_riverbank_bare')
        self.assertEqual(edge_overlay_kind('core:water', 'core:grass'), 'water_ocean_shore')
        self.assertEqual(edge_overlay_kind('core:water', 'core:river'), 'water_estuary')
        self.assertEqual(edge_overlay_kind('core:river', 'core:grass'), 'water_river_edge')

    def test_contextual_water_assets_exist_with_multiple_variants(self):
        for terrain_id in (
            'render:ocean_deep', 'render:ocean_shallow', 'render:estuary_mix',
            'render:freshwater_deep', 'render:freshwater_shallow',
        ):
            with self.subTest(terrain_id=terrain_id):
                ref = self.visuals.ref('terrain', terrain_id)
                self.assertEqual(len(ref.paths), 10)
                for raw in ref.paths:
                    path = self.root / raw
                    self.assertTrue(path.exists(), path)
                    self.assertGreater(path.stat().st_size, 200, path)


if __name__ == '__main__':
    unittest.main()
