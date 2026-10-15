"""G0/G1a observational 2.5D contract tests; pygame/GPU not required."""
from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import itertools
import unittest

from worldseed.presentation.worldspace import (
    CoverRegion, SceneVisibility, VisualLayer, WorldCamera, WorldFoot,
    WorldVisualInstance, project_scene, visual_sort_key, MAX_SCENE_INSTANCES,
)


def make_visual(name, x, y, layer=VisualLayer.UPRIGHT, *, z=0.0, width=0.8,
                height=1.5, physical=(), resource=None, parent=None,
                cover=None, room=None):
    return WorldVisualInstance(name, 'core:' + name.split(':')[0], WorldFoot(x, y, z),
                               width, height, 1.5, layer, tuple(physical),
                               resource_id=resource, parent_id=parent,
                               cover=cover, room_id=room)


def visibility(*, hidden=(), rooms=()):
    visible = {(x, y, 0) for x in range(-3, 9) for y in range(-3, 9)} - set(hidden)
    return SceneVisibility(frozenset(visible), allowed_rooms=frozenset(rooms))


def tree_scene():
    footprint = ((2, 2, 0),)
    crown = CoverRegion(((0.5, 0.5), (4.5, 0.5), (4.5, 4.5), (0.5, 4.5)))
    trunk = make_visual('oak:trunk', 2.5, 2.9, VisualLayer.GROUNDED,
                        width=1.0, height=2.2, physical=footprint,
                        resource='tree:original-save-uid')
    canopy = make_visual('oak:crown', 2.5, 2.9, VisualLayer.OVERHEAD,
                         width=4.0, height=3.8, resource='tree:original-save-uid',
                         parent=trunk.instance_id, cover=crown)
    shadow = make_visual('oak:shadow', 2.5, 2.9, VisualLayer.GROUND_SHADOW,
                         width=3.5, height=1.0, resource='tree:original-save-uid',
                         parent=trunk.instance_id)
    player = make_visual('player:main', 3.4, 2.25)
    npc = make_visual('npc:hidden', 1.2, 1.2)
    return trunk, canopy, shadow, player, npc


class WorldspaceSceneContractTests(unittest.TestCase):
    def setUp(self):
        self.camera = WorldCamera(WorldFoot(2.5, 2.5), 640, 480, 32)
        self.trunk, self.crown, self.shadow, self.player, self.npc = tree_scene()

    def scene(self, *items, vis=None, viewer='player:main', camera=None, **kwargs):
        return project_scene(items, camera or self.camera, vis or visibility(),
                             viewer_id=viewer, **kwargs)

    def test_immutable_visual_group_shares_legacy_tree_identity(self):
        group = (self.trunk, self.crown, self.shadow)
        self.assertEqual({part.resource_id for part in group}, {'tree:original-save-uid'})
        self.assertEqual({part.instance_id for part in group},
                         {'oak:trunk', 'oak:crown', 'oak:shadow'})
        with self.assertRaises(FrozenInstanceError):
            self.trunk.foot = WorldFoot(0, 0)
        self.assertEqual(self.crown.parent_id, self.trunk.instance_id)
        self.assertEqual(self.trunk.physical_cells, ((2, 2, 0),))
        self.assertEqual(self.crown.physical_cells, ())
        self.assertEqual(self.shadow.physical_cells, ())

    def test_passable_under_crown_without_walking_through_solid_trunk(self):
        actor = self.player.foot
        self.assertTrue(self.crown.cover.contains(actor))
        blockers = set(self.trunk.physical_cells) | set(self.crown.physical_cells)
        self.assertNotIn(actor.cell, blockers)
        self.assertIn((2, 2, 0), blockers)
        scene = self.scene(self.trunk, self.crown, self.shadow, self.player)
        self.assertEqual(scene.cover_fades[0].cover_instance_id, 'oak:crown')
        self.assertEqual(scene.cover_fades[0].viewer_instance_id, 'player:main')

    def test_single_local_canopy_fade_does_not_change_trunk_or_shadow(self):
        output = self.scene(self.trunk, self.shadow, self.crown, self.player)
        self.assertEqual(len(output.cover_fades), 1)
        fade = output.cover_fades[0]
        self.assertAlmostEqual(fade.local_alpha, 0.48)
        self.assertEqual(fade.radius_px, 28.8)
        self.assertEqual(fade.screen_center, self.camera.to_screen(self.player.foot))
        self.assertEqual({v.instance.instance_id for v in output.visuals},
                         {'oak:trunk', 'oak:crown', 'oak:shadow', 'player:main'})
        self.assertTrue(all(v.remembered_only is False for v in output.visuals))

    def test_no_cutout_for_nearby_but_outside_or_different_height(self):
        for other in (replace(self.player, foot=WorldFoot(5.1, 2)),
                      replace(self.player, foot=WorldFoot(3, 2, 2.0))):
            with self.subTest(foot=other.foot):
                self.assertFalse(self.scene(self.crown, other).cover_fades)
        self.assertTrue(self.crown.cover.contains(WorldFoot(0.5, 2.0)))

    def test_overhead_vs_foot_sorted_actor_in_front_and_behind(self):
        behind = replace(self.player, foot=WorldFoot(2.0, 1.9))
        front = replace(self.player, foot=WorldFoot(2.0, 3.9))
        for actor, ordering in ((behind, ['player:main', 'oak:trunk', 'oak:crown']),
                                (front, ['oak:trunk', 'player:main', 'oak:crown'])):
            output = self.scene(self.trunk, self.crown, actor)
            self.assertEqual([v.instance.instance_id for v in output.visuals], ordering)

    def test_stable_deterministic_order_with_permutation_and_ids(self):
        pair = (make_visual('a', 3.0, 3.0), make_visual('b', 3.0, 3.0))
        instances = (*pair, self.trunk, self.crown, self.player)
        expected = tuple(v.instance_id for v in sorted(instances, key=visual_sort_key))
        for order in itertools.permutations(instances):
            result = self.scene(*order)
            self.assertEqual(tuple(v.instance.instance_id for v in result.visuals), expected)
        with self.assertRaisesRegex(ValueError, 'duplicate visual'):
            self.scene(self.crown, self.crown)

    def test_hidden_or_remembered_npcs_do_not_leak_or_trigger_fade(self):
        npc = replace(self.npc, foot=WorldFoot(3.2, 3.2))
        private = visibility(hidden={(3, 3, 0)})
        scene = self.scene(self.trunk, self.crown, npc, vis=private, viewer=npc.instance_id)
        self.assertNotIn('npc:hidden', {v.instance.instance_id for v in scene.visuals})
        self.assertFalse(scene.cover_fades)
        remembered = SceneVisibility(private.current_cells, private.remembered_cells | {(3, 3, 0)})
        scene = self.scene(self.crown, npc, vis=remembered)
        self.assertNotIn('npc:hidden', {v.instance.instance_id for v in scene.visuals})
        ground = make_visual('terrain:base', 3.5, 3.5, VisualLayer.GROUND,
                             width=1, height=1)
        result = self.scene(ground, npc, vis=remembered)
        self.assertEqual([v.instance.instance_id for v in result.visuals], ['terrain:base'])
        self.assertTrue(result.visuals[0].remembered_only)

    def test_object_art_is_clipped_to_current_cells_not_remembered_neighbors(self):
        only = SceneVisibility(frozenset({(2, 2, 0)}), frozenset({(1, 2, 0)}))
        scene = self.scene(self.trunk, self.crown, vis=only)
        self.assertEqual({v.instance.instance_id for v in scene.visuals},
                         {'oak:trunk', 'oak:crown'})
        for visual in scene.visuals:
            self.assertEqual(len(visual.clip_rects), 1)
        # The tall crown never paints an undiscovered part of its large bounds.
        cx, cy = self.camera.to_screen(WorldFoot(2, 2))
        self.assertEqual(scene.visuals[-1].clip_rects[0], (cx, cy, cx+32, cy+32))

    def test_authoritative_stealth_gate_blocks_actor_even_when_cell_visible(self):
        concealed = replace(self.npc, foot=WorldFoot(3.0, 2.0),
                            authorized_visible=False)
        output = self.scene(concealed, self.crown, vis=visibility(),
                            viewer=concealed.instance_id)
        self.assertEqual([v.instance.instance_id for v in output.visuals], ['oak:crown'])
        self.assertFalse(output.cover_fades)
        with self.assertRaises(ValueError):
            replace(self.player, authorized_visible='yes')

    def test_synthetic_svg_and_manifest_are_reproducible(self):
        from tools.worldspace_scene_probe import build_demo, probe_record, probe_svg
        camera, scene = build_demo()
        a, b = probe_record(camera, scene), probe_record(*build_demo())
        self.assertEqual(a, b)
        self.assertEqual(len(a['visuals']), 5)
        self.assertEqual(len(a['fades']), 1)
        self.assertNotIn('npc:hidden', [v['id'] for v in a['visuals']])
        svg = probe_svg(camera, scene)
        self.assertIn('clipPath', svg)
        self.assertIn('fademask0', svg)
        self.assertIn('oak:', a['visuals'][0]['id'])
        self.assertEqual(svg, probe_svg(*build_demo()))
        self.assertNotEqual(a['sha256'], probe_record(*build_demo(800, 600, 1.5))['sha256'])

    def test_room_privacy_is_not_bypassed_by_cover_or_local_fade(self):
        private_roof = replace(self.crown, instance_id='roof:private', room_id='room:locked')
        private_npc = replace(self.npc, instance_id='npc:room', foot=WorldFoot(3, 2),
                              room_id='room:locked')
        scene = self.scene(private_roof, private_npc, self.player)
        self.assertEqual([v.instance.instance_id for v in scene.visuals], ['player:main'])
        self.assertFalse(scene.cover_fades)
        allowed = visibility(rooms={'room:locked'})
        scene = self.scene(private_roof, private_npc, self.player, vis=allowed)
        self.assertEqual(len(scene.cover_fades), 0)  # rooms do not match player
        self.assertIn('npc:room', [v.instance.instance_id for v in scene.visuals])

    def test_camera_fractional_follow_zoom_resize_roundtrip(self):
        actor = self.player.foot
        p = self.camera.to_screen(actor)
        moved = replace(self.camera, center=WorldFoot(2.625, 2.375))
        q = moved.to_screen(actor)
        self.assertAlmostEqual(q[0] - p[0], -4)
        self.assertAlmostEqual(q[1] - p[1], +4)
        for zoom, size in ((0.75, (640, 480)), (1.0, (640, 480)),
                           (1.5, (1920, 1080)), (2.0, (2560, 1440))):
            camera = replace(moved, zoom=zoom, width_px=size[0], height_px=size[1],
                             elevation_px_per_cell=9)
            screen = camera.to_screen(WorldFoot(3.125, 5.625, 2))
            world = camera.to_world(*screen, ground_z=2)
            self.assertAlmostEqual(world.x, 3.125)
            self.assertAlmostEqual(world.y, 5.625)
            self.assertEqual(world.z, 2)
            self.assertEqual(camera.to_screen(camera.center),
                             (size[0] * camera.anchor_x, size[1] * camera.anchor_y))

    def test_offscreen_trunk_can_still_show_overhanging_crown(self):
        cam = WorldCamera(WorldFoot(0, 0), 160, 160, 32)
        trunk = replace(self.trunk, foot=WorldFoot(4.1, 1.3))
        crown = replace(self.crown, foot=WorldFoot(4.1, 1.3))
        seen = SceneVisibility(frozenset({(4, 1, 0), (3, 0, 0), (2, 0, 0)}))
        result = self.scene(trunk, crown, camera=cam, vis=seen)
        self.assertNotIn('oak:trunk', {v.instance.instance_id for v in result.visuals})
        self.assertIn('oak:crown', {v.instance.instance_id for v in result.visuals})

    def test_bounded_dynamic_masks_and_instances(self):
        crowns = [replace(self.crown, instance_id=f'crown:{i}') for i in range(12)]
        scene = self.scene(*crowns, self.player)
        self.assertEqual(len(scene.cover_fades), 8)
        self.assertEqual([x.cover_instance_id for x in scene.cover_fades],
                         sorted(f'crown:{i}' for i in range(12))[:8])
        self.assertFalse(self.scene(*crowns, self.player, max_cutouts=0).cover_fades)
        with self.assertRaises(ValueError):
            self.scene(*[replace(self.player, instance_id=f'actor:{i}')
                          for i in range(MAX_SCENE_INSTANCES + 1)])
        with self.assertRaises(ValueError):
            self.scene(self.crown, self.player, fade_alpha=0)

    def test_validation_rejects_invalid_art_and_camera_contracts(self):
        with self.assertRaises(ValueError):
            WorldFoot(float('nan'), 0)
        with self.assertRaises(ValueError):
            replace(self.crown, width=float('inf'))
        with self.assertRaises(ValueError):
            replace(self.crown, cover=CoverRegion(((0, 0), (1, 1))))
        with self.assertRaises(ValueError):
            replace(self.trunk, cover=self.crown.cover)
        with self.assertRaises(ValueError):
            replace(self.camera, zoom=0)
        with self.assertRaises(ValueError):
            replace(self.camera, height_px=0)
        with self.assertRaises(ValueError):
            replace(self.trunk, revision=-1)


if __name__ == '__main__':
    unittest.main()
