"""G1b real-prepared resource projection (pure contracts + guarded fixture)."""
from __future__ import annotations

import importlib.util
from dataclasses import FrozenInstanceError
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from worldseed.presentation.worldspace import WorldCamera, WorldFoot, VisualLayer
from worldseed.presentation.worldspace_adapter import (
    PreparedActor, PREVIEW_CROWN_PROFILES, prepare_worldspace_scene,
)


def actor(uid='player', x=2.5, y=2.5, *, viewer=True, allowed=True, room=None):
    return PreparedActor(uid, 'core:human', WorldFoot(x, y),
                         authorized_visible=allowed, is_viewer=viewer, room_id=room)


def feature(fid='core:oak_tree', stage='mature'):
    return SimpleNamespace(feature_id=fid, stage=stage)


class PreparedAdapterContracts(unittest.TestCase):
    def setUp(self):
        self.camera = WorldCamera(WorldFoot(2.5, 2.5), 320, 240, 28)
        self.current = frozenset((x, y, 0) for x in range(-5, 10) for y in range(-5, 10))
        self.defs = {
            'core:oak_tree': SimpleNamespace(tags=('tree',), blocks_movement=True),
            'core:pine_tree': SimpleNamespace(tags=('tree',), blocks_movement=True),
            'core:berry_bush': SimpleNamespace(tags=('forage',), blocks_movement=False),
        }
        self.styles = lambda fid: {'width': 1.4, 'height': 1.9}

    def build(self, *, resources=None, actors=None, current=None, discovered=(), camera=None):
        return prepare_worldspace_scene(
            camera=camera or self.camera, resource_by=resources if resources is not None else {
                (2, 2, 0): (feature(), 'existing-software-sprite-ref')},
            resource_defs=self.defs, resource_style=self.styles,
            current_cells=self.current if current is None else current,
            discovered_cells=discovered, actors=actors or (actor(),), z=0,
        )

    def test_one_existing_tree_uid_has_separate_shadow_crown_and_solid_trunk(self):
        scene = self.build()
        tree = [i for i in scene.instances if i.resource_id is not None]
        self.assertEqual(len(tree), 3)
        self.assertEqual(len({i.resource_id for i in tree}), 1)
        self.assertEqual({i.layer for i in tree},
                         {VisualLayer.GROUNDED, VisualLayer.OVERHEAD, VisualLayer.GROUND_SHADOW})
        base = next(i for i in tree if i.layer == VisualLayer.GROUNDED)
        canopy = next(i for i in tree if i.layer == VisualLayer.OVERHEAD)
        shadow = next(i for i in tree if i.layer == VisualLayer.GROUND_SHADOW)
        self.assertEqual(base.physical_cells, ((2, 2, 0),))
        self.assertEqual(canopy.physical_cells, ())
        self.assertEqual(shadow.physical_cells, ())
        self.assertEqual(canopy.parent_id, base.instance_id)
        self.assertEqual(len(scene.projection.cover_fades), 1)
        self.assertEqual(scene.projection.cover_fades[0].cover_instance_id, canopy.instance_id)
        self.assertEqual(base.resource_id, 'feature:0:2:2:core:oak_tree')
        with self.assertRaises(FrozenInstanceError):
            base.resource_id = 'alternate-tree'

    def test_stump_and_sapling_keep_legacy_resource_identity_without_mature_crown(self):
        original = self.build()
        original_uid = next(i.resource_id for i in original.instances if i.resource_id)
        for stage in ('stump', 'sapling'):
            scene = self.build(resources={(2, 2, 0): (feature(stage=stage), 'same-asset-ref')})
            parts = [i for i in scene.instances if i.resource_id]
            self.assertEqual(len(parts), 1)
            self.assertEqual(parts[0].resource_id, original_uid)
            self.assertEqual(parts[0].physical_cells, ())
            self.assertFalse(scene.projection.cover_fades)
        depleted = self.build(resources={(2, 2, 0): (feature(stage='depleted'), None)})
        self.assertFalse([i for i in depleted.instances if i.resource_id])

    def test_oak_and_pine_are_distinct_preview_coverage_only(self):
        self.assertNotEqual(PREVIEW_CROWN_PROFILES['core:oak_tree'],
                            PREVIEW_CROWN_PROFILES['core:pine_tree'])
        scene = self.build(resources={(2, 2, 0): (feature('core:pine_tree'), 'atlas-ref')})
        crown = next(i for i in scene.instances if i.layer == VisualLayer.OVERHEAD)
        self.assertTrue(crown.cover.contains(actor().foot))
        self.assertNotIn((3, 2, 0), crown.physical_cells)

    def test_non_tree_and_blocked_definition_use_existing_physical_authority(self):
        nonblock = self.build(resources={(2, 2, 0): (feature('core:berry_bush'), 'ref')})
        self.assertEqual(len(nonblock.instances), 2)
        self.assertEqual(nonblock.instances[0].physical_cells, ())
        self.defs['core:oak_tree'].blocks_movement = False
        tree = self.build()
        self.assertTrue(all(not i.physical_cells for i in tree.instances))

    def test_never_include_unknown_resource_unseen_npc_or_private_room(self):
        seen = frozenset({(2, 2, 0)})
        scene = self.build(current=seen,
                           actors=(actor(), actor('hidden', 2.5, 2.5, viewer=False, allowed=False),
                                   actor('private', 2.5, 2.5, viewer=False, room='sealed')),
                           resources={(2, 2, 0): (feature(), 'path'),
                                      (3, 2, 0): (feature('core:pine_tree'), 'path')})
        ids = [i.instance_id for i in scene.instances]
        self.assertTrue(any('oak_tree' in i for i in ids))
        self.assertFalse(any('pine_tree' in i for i in ids))
        self.assertNotIn('actor:hidden', ids)
        self.assertNotIn('actor:private', ids)
        for view in scene.projection.visuals:
            for clip in view.clip_rects:
                self.assertEqual((clip[2]-clip[0], clip[3]-clip[1]), (28.0, 28.0))

    def test_discovered_memory_never_authorizes_tree_or_actor(self):
        scene = self.build(current=frozenset({(3, 2, 0)}),
                           discovered=frozenset({(2, 2, 0)}),
                           actors=(actor(x=3.5, y=2.5),))
        self.assertEqual(len(scene.instances), 1)
        self.assertFalse(scene.projection.cover_fades)
        self.assertIn((2, 2, 0), scene.visibility.remembered_cells)

    def test_fractional_projection_is_continuous_and_deterministic(self):
        before = self.build()
        shifted = WorldCamera(WorldFoot(2.625, 2.375), 320, 240, 28)
        after = self.build(camera=shifted)
        bfoot = next(v.screen_foot for v in before.projection.visuals
                     if v.instance.instance_id == 'actor:player')
        afoot = next(v.screen_foot for v in after.projection.visuals
                     if v.instance.instance_id == 'actor:player')
        self.assertAlmostEqual(afoot[0]-bfoot[0], -3.5)
        self.assertAlmostEqual(afoot[1]-bfoot[1], +3.5)
        self.assertEqual(after, self.build(camera=shifted))

    def test_visibility_lookup_is_local_membership_not_global_discovery_scan(self):
        class NoIteration:
            def __init__(self, keys): self.keys = keys; self.checks = 0
            def __contains__(self, key):
                self.checks += 1
                return key in self.keys
            def __iter__(self): raise AssertionError('global discovery scan forbidden')
        now = NoIteration(self.current)
        memory = NoIteration(self.current)
        scene = self.build(current=now, discovered=memory)
        self.assertTrue(scene.projection.cover_fades)
        self.assertLess(now.checks, 1024)
        self.assertEqual(memory.checks, 0)

    def test_legacy_pos_key_string_visibility_matches_production_contract(self):
        # WORLDSEED's sim discovery uses "x,y,z", not tuple world keys.
        encoded = frozenset(f'{x},{y},{z}' for x, y, z in self.current)
        string_scene = prepare_worldspace_scene(
            camera=self.camera,
            resource_by={(2, 2, 0): (feature(), None)},
            resource_defs=self.defs, resource_style=self.styles,
            current_cells=encoded, discovered_cells=frozenset(),
            visibility_key=lambda x, y, z: f'{x},{y},{z}',
            actors=(actor(),),
        )
        self.assertEqual(string_scene, self.build())

    def test_bad_snapshot_and_viewer_are_rejected_without_fallback_visibility(self):
        with self.assertRaisesRegex(ValueError, 'viewer'):
            self.build(actors=(actor('npc', viewer=False),))
        with self.assertRaisesRegex(ValueError, 'viewer'):
            self.build(actors=(actor(allowed=False),))
        with self.assertRaisesRegex(ValueError, 'snapshot'):
            self.build(resources={(2, 2, 1): (feature(), None) for _ in (0,)},
                       camera=WorldCamera(WorldFoot(2.5, 2.5, 1), 320, 240, 28))
        with self.assertRaisesRegex(ValueError, 'viewport'):
            self.build(camera=WorldCamera(WorldFoot(2.5, 2.5), 3840, 2160, 16))


@unittest.skipUnless(importlib.util.find_spec('worldseed.persistence') is not None,
                     'requires full repository production systems')
class PreparedRealForestFixtureTests(unittest.TestCase):
    """Real ResourceSystem/prepared chunks; guard prohibits on-demand generation."""

    def test_prepared_forest_is_observational_and_tree_sources_are_identical(self):
        from tools.reference_scene_fixtures import build_fixture
        from worldseed.config import DATA_DIR
        from worldseed.content.registry import ContentRegistry
        from worldseed.core.coords import WorldPos
        from worldseed.systems.state import pos_key
        from worldseed.presentation.visuals import VisualRegistry

        reg = ContentRegistry.load(DATA_DIR)
        with TemporaryDirectory() as work:
            fixture = build_fixture('forest', reg, Path(work), width=640, height=480, zoom=28)
            try:
                sim = fixture.sim
                viewer = sim.player_pos
                before = fixture.authority_fingerprint()
                resources = {}
                for y in range(viewer.y-10, viewer.y+11):
                    for x in range(viewer.x-10, viewer.x+11):
                        if pos_key(x,y,0) not in sim.visible_tiles_set:
                            continue
                        fv = sim.resources.feature_at(WorldPos(x,y,0))
                        if fv and fv.stage != 'depleted':
                            resources[(x,y,0)] = (fv, None)
                self.assertTrue(any('tree' in v[0].feature_id for v in resources.values()))
                camera = WorldCamera(WorldFoot(viewer.x+0.5, viewer.y+0.5), 640, 480, 28)
                params = dict(camera=camera, resource_by=resources, resource_defs=reg.resources,
                              resource_style=VisualRegistry.load_default().resource_style,
                              current_cells=sim.visible_tiles_set,
                              discovered_cells=sim.discovered_tiles_set,
                              visibility_key=pos_key,
                              actors=(actor(x=viewer.x+0.5, y=viewer.y+0.5),))
                sample = prepare_worldspace_scene(**params)
                self.assertEqual(sample, prepare_worldspace_scene(**params))
                for item in sample.instances:
                    if item.layer == VisualLayer.OVERHEAD:
                        self.assertEqual(item.physical_cells, ())
                        self.assertIn(item.parent_id, {r.instance_id for r in sample.instances})
                        self.assertTrue(item.resource_id.startswith('feature:0:'))
                self.assertEqual(before, fixture.authority_fingerprint())
            finally:
                fixture.close()


if __name__ == '__main__':
    unittest.main()
