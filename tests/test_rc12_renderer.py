from pathlib import Path
import unittest


class RC12RendererTests(unittest.TestCase):
    def test_mouse_motion_uses_hover_fast_path(self):
        src=Path('worldseed/ui/pygame_terminal.py').read_text(encoding='utf-8')
        self.assertIn('self._refresh_hover_only()',src)
        self.assertNotIn("return '__HOVER__'",src)
        self.assertIn('pg.display.update(damage)',src)

    def test_renderer_caches_static_view_layers(self):
        src=Path('worldseed/ui/pygame_terminal.py').read_text(encoding='utf-8')
        self.assertIn('def _build_base_layer',src)
        self.assertIn('rendered_known',src)
        self.assertIn('def _resource_view',src)
        self.assertIn('sim.resources.revision',src)
        self.assertIn('overlay_keys=set(resource_by)',src)

    def test_local_terrain_autotiling_uses_all_eight_discovered_neighbors(self):
        src=Path('worldseed/ui/pygame_terminal.py').read_text(encoding='utf-8')
        rules=Path('worldseed/presentation/local_terrain.py').read_text(encoding='utf-8')
        self.assertIn('for direction,ndx,ndy in DIRECTIONS_8',src)
        self.assertIn('if pos_key(nwx,nwy,z) not in known:continue',src)
        self.assertIn('def _terrain_transition_mask',src)
        self.assertIn('def _terrain_surface',src)
        for direction in ('north', 'south', 'west', 'east', 'northwest', 'northeast', 'southwest', 'southeast'):
            self.assertIn(direction,rules)

    def test_expensive_scanline_blend_disabled_by_default(self):
        src=Path('worldseed/ui/pygame_terminal.py').read_text(encoding='utf-8')
        self.assertIn('self._scanlines_enabled = False',src)
        self.assertIn('if not self._scanlines_enabled:return',src)

    def test_discovery_uses_per_pass_occlusion_cache(self):
        src=Path('worldseed/sim/engine.py').read_text(encoding='utf-8')
        self.assertIn('opaque_cache={}',src)
        self.assertIn('self._visible_from(pos,target,opaque_cache)',src)


if __name__=='__main__':
    unittest.main()
