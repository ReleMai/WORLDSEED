"""Exact visibility optimization and inward darkzone rendering contracts."""
from random import Random
from unittest import TestCase
from unittest.mock import patch

from worldseed.systems import interior_visibility as sight
from worldseed.presentation.interior_clip_index import InteriorClipIndex
from worldseed.presentation.interior_darkzone import sight_boundary, darkzone_commands
from worldseed.systems.interior_state import InteriorRect


def reference_intersection(polygon,wall):
    a,b,c,d=wall
    box=((a,b),(c-1,b),(c-1,d-1),(a,d-1))
    axes=[(1,0),(0,1)]
    axes.extend((q[1]-p[1],p[0]-q[0]) for p,q in
                zip(polygon,(*polygon[1:],polygon[0])))
    for dx,dy in axes:
        p=[x*dx+y*dy for x,y in polygon]
        w=[x*dx+y*dy for x,y in box]
        if max(p)<min(w) or max(w)<min(p):return False
    return True


class IndoorSightPerformanceTests(TestCase):
    def test_optimized_wall_support_matches_exact_sat(self):
        rng=Random(72)
        for _ in range(1500):
            polygon=sight._hull(tuple((rng.randrange(-100,200),rng.randrange(-100,200)) for _ in range(5)))
            if len(polygon)<3:continue
            a,b=rng.randrange(-150,250),rng.randrange(-150,250)
            wall=(a,b,a+rng.randrange(1,90),b+rng.randrange(1,90))
            self.assertEqual(sight._intersects_wall(polygon,wall),reference_intersection(polygon,wall))

    def test_exact_cache_invalidates_on_player_walls_ambient_and_sources(self):
        from tests.test_gpu_interiors import GPUInteriorContracts
        from worldseed.systems.illumination import LightSource
        sim,plan,player,_=GPUInteriorContracts().fixture()
        sight._visible_floor_rects.cache_clear()
        args=(plan,player.x,player.y,720,50000)
        with patch.object(sight,'_trusted_rect_visible',wraps=sight._trusted_rect_visible) as query:
            first=sight.visible_floor_rects(*args)
            count=query.call_count
            self.assertTrue(first)
            self.assertIs(sight.visible_floor_rects(*args),first)
            self.assertEqual(query.call_count,count)
            for change in (
                    lambda:sight.visible_floor_rects(plan,player.x+1,player.y,720,50000),
                    lambda:sight.visible_floor_rects(plan,player.x,player.y,720,0),
                    lambda:sight.visible_floor_rects(*args,sources=(LightSource(2500,3000,2000,60000),))):
                before=query.call_count
                change()
                self.assertGreater(query.call_count,before)
            plan.walls.append(InteriorRect(1000,0,200,8000))
            changed=sight.visible_floor_rects(*args)
            self.assertNotEqual(first,changed)


class DarkzoneTests(TestCase):
    def test_coarse_fine_patch_edges_cancel_without_internal_grid_shadows(self):
        rectangles=((0,0,10,10),(10,0,20,5),(10,5,20,10))
        boundary=sight_boundary(rectangles)
        self.assertEqual(set(boundary),{('x',0,0,10,1),('x',20,0,10,-1),
            ('y',0,0,20,1),('y',10,0,20,-1)})

    def test_darkzone_never_admits_private_floor_and_has_smooth_inward_alpha(self):
        clips=((0.,0.,20.,20.),(20.,0.,40.,10.))
        commands=darkzone_commands(clips,InteriorClipIndex(clips,10.),30.)
        self.assertTrue(commands)
        for command in commands:
            self.assertEqual(len(command.clip_rects),1)
            a,b,c,d=command.clip_rects[0]
            self.assertTrue(any(x<=a<c<=x1 and y<=b<d<=y1 for x,y,x1,y1 in clips))
            alpha=command.rgba[3::4]
            self.assertGreater(max(alpha),240)
            self.assertLess(min(alpha),2)
            self.assertGreater(len(set(alpha)),24)

    def test_darkzone_respects_remaining_frame_budget(self):
        clips=((0.,0.,20.,20.),(30.,0.,40.,20.))
        index=InteriorClipIndex(clips,10.)
        self.assertEqual(darkzone_commands(clips,index,30.,budget=0),())
        self.assertEqual(len(darkzone_commands(clips,index,30.,budget=2)),2)

    def test_roof_admits_full_player_body_without_admitting_ground_or_npcs(self):
        from worldseed.presentation.gpu_scene_bridge import prepare_gpu_frame
        from worldseed.presentation.gpu_buildings import PreparedBuildingShell
        from worldseed.presentation.worldspace import WorldCamera,WorldFoot
        from worldseed.systems.building_shells import BuildingShell
        from tests.test_gpu_buildings import FakeMaterials
        shell=BuildingShell('roof','','residence','core:residence',
            ((2,2),(3,2),(2,3),(3,3)),(2,3),'roof:door',0,'rectangular',(2,2,3,3))
        camera=WorldCamera(WorldFoot(2.5,2.5,0),320,240,30)
        frame=prepare_gpu_frame(camera=camera,terrain_by={},resource_by={},resource_defs={},
            resource_style=lambda _: {},visible_cells=frozenset(),discovered_cells=frozenset(),
            viewer=camera.center,materials=FakeMaterials(),
            buildings=(PreparedBuildingShell(shell,frozenset({(2,2,0)})),))
        player=next(c for c in frame.scenery if c.visual_id=='actor:gpu-viewer')
        self.assertEqual(player.clip_rects,(player.bounds,))
        roof=next(c for c in frame.scenery if c.visual_id=='building:roof')
        self.assertGreater(roof.fade_radius,0.)
        self.assertEqual(roof.local_alpha,.08)
        self.assertFalse(frame.ground)
        self.assertFalse(any('npc:' in c.visual_id for c in frame.scenery))

    def test_native_gl_darkzone_keeps_unknown_black_and_softens_only_inner_edge(self):
        import sys
        try:
            import moderngl
            context=moderngl.create_standalone_context(require=330,
                **({} if sys.platform=='win32' else {'backend':'egl'}))
        except Exception as exc:
            self.skipTest('native/offscreen GL unavailable: '+type(exc).__name__)
        from worldseed.presentation.gl_worldspace import GLWorldspaceRenderer,SpriteCommand
        texture=context.texture((96,64),4)
        target=context.framebuffer(color_attachments=[texture])
        renderer=GLWorldspaceRenderer(context,96,64,texture_budget=65536)
        try:
            clips=((20.,10.,76.,52.),)
            floor=SpriteCommand('interior-floor:test','test-floor',1,
                bytes((160,130,90,255)),1,1,clips[0],clips)
            fog=darkzone_commands(clips,InteriorClipIndex(clips,16.),30.)
            report=renderer.draw((floor,*fog),target=target,clear=(0.,0.,0.,0.))
            pixels=target.read(components=4,alignment=1)
            def pixel(x,y):
                i=((63-y)*96+x)*4
                return pixels[i:i+4]
            for y in range(64):
                for x in range(96):
                    if not (20<=x<76 and 10<=y<52):
                        self.assertEqual(pixel(x,y),bytes(4))
            self.assertLess(pixel(20,30)[0],pixel(24,30)[0])
            self.assertLess(pixel(24,30)[0],pixel(48,30)[0])
            self.assertLessEqual(report.draw_calls,5)
        finally:
            renderer.close();target.release();texture.release();context.release()
