from pathlib import Path
import json
import unittest

from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.presentation.visuals import VisualRegistry
from worldseed.ui.pygame_terminal import PygameTerminal


class RC8VisualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg=ContentRegistry.load(DATA_DIR)
        cls.vis=VisualRegistry.load_default()

    def test_visual_coverage_complete(self):
        self.assertEqual([],self.vis.coverage_issues(self.reg))

    def test_every_species_has_multiple_variants(self):
        for cid in self.reg.species:
            self.assertGreaterEqual(len(self.vis.ref('species',cid).paths),4,cid)

    def test_npc_variation_pool_is_large(self):
        self.assertGreaterEqual(len(self.vis.npc_paths()),24)

    def test_procedural_species_have_fallback_variants(self):
        self.assertGreaterEqual(len(self.vis.procedural_species_paths()),8)

    def test_all_visual_files_exist_and_are_nonempty(self):
        for p in self.vis.iter_asset_paths():
            self.assertTrue(p.exists(),p)
            self.assertGreater(p.stat().st_size,80,p)

    def test_atlas_index_covers_primary_visual_categories(self):
        base=Path(__file__).resolve().parents[1]/'worldseed'/'assets'
        idx=json.loads((base/'atlas_index.json').read_text(encoding='utf-8'))
        for kind in ['items','terrain','resources','structures','crops','species','npc']:
            self.assertIn(kind,idx['atlases'])
            self.assertTrue((Path(__file__).resolve().parents[1]/'worldseed'/idx['atlases'][kind]['image']).exists())

    def test_pygame_backend_import_is_optional(self):
        # The module must remain importable on headless CI even when pygame-ce
        # is unavailable. Runtime construction is what requires pygame-ce.
        self.assertIsInstance(PygameTerminal.available(),bool)


if __name__=='__main__': unittest.main()

class RC9PresentationContractTests(unittest.TestCase):
    def test_pygame_terminal_declares_zoom_and_hover_helpers(self):
        from pathlib import Path
        src = Path('worldseed/ui/pygame_terminal.py').read_text(encoding='utf-8')
        self.assertIn("self._tile_px = min(56, self._tile_px + 4)", src)
        self.assertIn("self._tile_px = max(16, self._tile_px - 4)", src)
        self.assertIn("def _draw_hover_tooltip", src)
        self.assertIn("if hpk in known", src)
