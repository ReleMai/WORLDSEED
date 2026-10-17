"""Windows crash regression, Alt sight semantics, roof occlusion, and wall art."""
from __future__ import annotations
from types import SimpleNamespace
from unittest import TestCase
from worldseed.systems.interior_visibility import _hull,_rect_visible,visible_floor_rects
from worldseed.presentation.interior_wall_art import wall_art
from worldseed.presentation.worldspace import WorldCamera,WorldFoot
from worldseed.presentation.gpu_buildings import PreparedBuildingShell
from worldseed.systems.building_shells import BuildingShell


class VisibilityAndArtRegressions(TestCase):
    def test_corrupt_nested_interior_point_fails_closed_not_windows_crash(self):
        # The actual Windows traceback ended in _cross subtracting tuples.
        self.assertEqual(_hull((((1,2),3),(4,5),(6,7))),())
        self.assertFalse(_rect_visible((1,2),3,(4,5,10,12),()))
        self.assertFalse(_rect_visible(1,2,((4,5),6,10,12),()))
        plan=SimpleNamespace(width=10000,height=7000,walls=[])
        self.assertEqual(visible_floor_rects(plan,(200,300),400,0,0),())

    def test_good_hull_and_room_geometry_still_work(self):
        self.assertTrue(_rect_visible(10,10,(200,200,300,300),()))
        self.assertFalse(_rect_visible(10,10,(200,200,300,300),
                         ((90,90,105,105),)))

    def test_structural_and_partition_art_is_tiled_at_physical_proportions(self):
        stone=wall_art('structural','core:wall_fieldstone',(0,0,12000,180))
        plaster=wall_art('partition','core:interior_wall_plaster',(0,0,12000,180))
        timber=wall_art('structural','core:wall_oak_panel',(0,0,180,8500))
        for item in (stone,plaster,timber):
            self.assertEqual(len(item[2]),item[3]*item[4]*4)
            self.assertLessEqual(max(item[3:]),512)
            self.assertGreater(len(set(item[2][::4])),5)
        self.assertGreater(stone[3],stone[4]*10)
        self.assertGreater(timber[4],timber[3]*10)
        self.assertNotEqual(stone[2],plaster[2])
        self.assertIs(wall_art('structural','core:wall_fieldstone',(0,0,12000,180)),stone)

    def test_render_flags_make_sight_circle_alt_only(self):
        import inspect
        from worldseed.ui.gpu_terminal import GpuTerminal
        source=inspect.getsource(GpuTerminal.present_game)
        self.assertIn('self._sight_overlay_keys',inspect.getsource(GpuTerminal._composite))
        self.assertIn('sight_mask=',source)
        self.assertNotIn('sight_radius=0.',source)
        event_source=inspect.getsource(GpuTerminal._filter_event)
        self.assertIn('pg.K_LALT',event_source)
        self.assertIn('pg.K_RALT',event_source)


class RoofViewerContracts(TestCase):
    def test_player_on_admitted_roof_cell_renders_without_revealing_terrain(self):
        from worldseed.presentation.gpu_scene_bridge import prepare_gpu_frame
        from tests.test_gpu_buildings import FakeMaterials
        shell=BuildingShell('root-roof','','residence','core:residence',
             ((2,2),(3,2),(2,3),(3,3)),(2,3),'root-roof:door',0,
             'rectangular',(2,2,3,3))
        admitted=frozenset({(2,2,0),(3,2,0),(2,3,0),(3,3,0)})
        row=PreparedBuildingShell(shell,admitted)
        camera=WorldCamera(WorldFoot(2.5,2.5,0),320,240,30)
        kwargs=dict(camera=camera,terrain_by={},resource_by={},resource_defs={},
            resource_style=lambda _: {},visible_cells=frozenset(),
            discovered_cells=frozenset(),viewer=WorldFoot(2.5,2.5,0),
            materials=FakeMaterials(),buildings=(row,),show_explored_memory=False)
        frame=prepare_gpu_frame(**kwargs)
        self.assertTrue(any(row.visual_id=='actor:gpu-viewer'
                            for row in frame.scenery))
        self.assertFalse(frame.ground)
        self.assertFalse(any('npc:' in row.visual_id for row in frame.scenery))
        self.assertTrue(any(row.visual_id=='building:root-roof' for row in frame.scenery))
        forbidden=prepare_gpu_frame(**{**kwargs,'buildings':()})
        self.assertEqual([row.visual_id for row in forbidden.scenery],['actor:gpu-viewer'])
        self.assertFalse(forbidden.ground)
