import os
os.environ.setdefault("SDL_VIDEODRIVER","dummy")
os.environ.setdefault("SDL_AUDIODRIVER","dummy")

import unittest

from worldseed.presentation.visuals import VisualRegistry
from worldseed.ui.pygame_terminal import PygameTerminal


class Dev38NaturalContainerArtTests(unittest.TestCase):
    def test_manifest_defines_five_variants_per_natural_container(self):
        visuals=VisualRegistry.load_default()
        expected={
            "core:hollow_log_cache":0,
            "core:rotten_stump_cache":1,
            "core:rock_crevice_cache":2,
        }
        paths=set()
        for feature_id,row in expected.items():
            style=visuals.resource_style(feature_id)
            self.assertEqual(style.get("atlas_row"),row)
            self.assertEqual(style.get("atlas_columns"),5)
            self.assertEqual(style.get("variants"),5)
            self.assertEqual(style.get("atlas_frame"),64)
            self.assertTrue(style.get("smooth"))
            path=visuals.resource_atlas_path(feature_id)
            self.assertIsNotNone(path)
            self.assertTrue(path.exists())
            paths.add(path)
        self.assertEqual(len(paths),1)

    @unittest.skipUnless(PygameTerminal.available(),"requires pygame-ce")
    def test_atlas_dimensions_and_seeded_coordinate_selection(self):
        term=PygameTerminal(800,520);term.enter()
        try:
            path=term._visuals.resource_atlas_path("core:hollow_log_cache")
            atlas=term.pg.image.load(str(path))
            self.assertEqual(atlas.get_size(),(320,192))
            expected={
                "core:hollow_log_cache":0,
                "core:rotten_stump_cache":1,
                "core:rock_crevice_cache":2,
            }
            for feature_id,row in expected.items():
                first=term._resource_visual(feature_id,12,34,0)
                second=term._resource_visual(feature_id,12,34,0)
                self.assertEqual(first,second)
                self.assertEqual(first[0],"atlas")
                self.assertEqual(first[3],row)
                self.assertEqual(first[4],64)
                variants={term._resource_visual(feature_id,x,7,0)[2] for x in range(128)}
                self.assertGreaterEqual(len(variants),4)
                self.assertTrue(variants.issubset(set(range(5))))
        finally:
            term.restore()


if __name__=="__main__":
    unittest.main()
