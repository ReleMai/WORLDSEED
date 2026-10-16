"""W1 live snapshots preserve simulation authority and bounded disclosure."""
from __future__ import annotations

from contextlib import contextmanager, ExitStack
from dataclasses import FrozenInstanceError
from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import patch

from tools.reference_scene_fixtures import build_fixture
from worldseed.config import DATA_DIR, CHUNK_SIZE
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos, split_world
from worldseed.entities.components import Position
from worldseed.presentation.live_gpu_scene import capture_live_scene, player_foot
from worldseed.presentation.worldspace import WorldCamera, WorldFoot
from worldseed.presentation.worldspace_adapter import MAX_PREPARED_ACTORS
from worldseed.systems.interior_state import InteriorActor
from worldseed.systems.exterior_memory import observe_exterior
from worldseed.systems.state import CreatureState, FireCell, NPCState, RoofState, pos_key


PIXELS = b'\x70\x90\x44\xff' * 16


class FakeAssets:
    """Pure material service; these tests need no SDL or OpenGL context."""

    def asset(self, path):
        return ('terrain:' + path.name, 1, PIXELS, 4, 4)

    def tree(self, species, layer, season):
        return (f'{species}:{layer}:{season}', 1, PIXELS, 4, 4)

    def player(self):
        return ('player', 1, PIXELS, 4, 4)

    def actor(self, content_id):
        return ('actor:' + content_id, 1, PIXELS, 4, 4)

    def interior(self, category, content_id):
        return (category + ':' + content_id, 1, PIXELS, 4, 4)


def unexpected(*args, **kwargs):
    raise AssertionError('rendering must not prepare, scan or mutate the simulation')


class MembershipOnly:
    """An observational consumer may query membership, never lifetime entries."""

    def __init__(self, values):
        self.values = frozenset(values)

    def __contains__(self, value):
        return value in self.values

    __iter__ = unexpected


class IndexedOnlyDict(dict):
    values = items = __iter__ = unexpected


class LiveGpuSceneContracts(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    @contextmanager
    def fixture(self, name='forest', **kwargs):
        with tempfile.TemporaryDirectory() as directory:
            fixture = build_fixture(name, self.registry, Path(directory),
                                    width=640, height=480, zoom=28, **kwargs)
            try:
                yield fixture
            finally:
                fixture.close()

    def camera(self, sim, *, z=None):
        p = sim.player_pos
        return WorldCamera(WorldFoot(p.x + .5, p.y + .5, p.z if z is None else z),
                           640, 480, 28)

    def frame(self, snapshot):
        return snapshot.gpu_frame(materials=FakeAssets(), registry=self.registry,
                                  resource_style=lambda _: {'width': 1.3, 'height': 1.9})

    def npc(self, sim, uid, cell=(256, 256, 0), **kwargs):
        npc = NPCState(uid, 'Private name', 30, 'farmer', [], *cell, '', '', **kwargs)
        sim.state.npcs[uid] = npc
        return npc

    def feature(self, sim, cell, feature_id):
        pos = WorldPos(*cell)
        key, lx, ly = split_world(pos)
        cache_key = (key.x, key.y, sim.resources._season(sim.clock.minute))
        values = list(sim.resources._feature_chunk_cache[cache_key])
        values[ly * CHUNK_SIZE + lx] = feature_id
        sim.resources._cache_feature_chunk(cache_key, tuple(values))

    def test_real_forest_capture_and_projection_are_observational(self):
        with self.fixture() as fixture:
            sim = fixture.sim
            self.npc(sim, 'local', fx=.125, fy=.875)
            sim.npcs.rebuild_spatial_index()
            sim.state.creatures['deer'] = CreatureState('deer', 'core:deer', 257, 256, 0, 45)
            sim.state.fires['fire'] = FireCell(256, 257, 0, 65, 80)
            sim.state.player_stealth_mode = True
            before = fixture.authority_fingerprint()
            world_order = tuple(sim.world.cache._chunks)
            feature_order = tuple(sim.resources._feature_chunk_cache)
            misses = set(sim.resources._feature_chunk_misses)
            queries = []
            fixture.db.connection.set_trace_callback(queries.append)
            try:
                with ExitStack() as guards:
                    for owner, name in ((sim.world, 'tile_at'), (sim.world.cache, 'get'),
                                        (sim.resources, 'feature_at'),
                                        (sim.resources, '_load_prepared_feature_chunk'),
                                        (sim.npcs, 'rebuild_spatial_index'),
                                        (type(sim.state), 'to_dict'),
                                        (fixture, 'authority_fingerprint')):
                        guards.enter_context(patch.object(owner, name, unexpected))
                    snapshot = capture_live_scene(sim, self.camera(sim))
                    frame = self.frame(snapshot)
                    fx = snapshot.atmosphere(1.25)
            finally:
                fixture.db.connection.set_trace_callback(None)
            self.assertTrue(frame.ground)
            self.assertTrue(any(command.texture_id.startswith('actor:')
                                for command in frame.scenery))
            self.assertEqual(fx.minute, sim.clock.minute)
            self.assertEqual(queries, [])
            self.assertEqual(world_order, tuple(sim.world.cache._chunks))
            self.assertEqual(feature_order, tuple(sim.resources._feature_chunk_cache))
            self.assertEqual(misses, sim.resources._feature_chunk_misses)
            self.assertEqual(before, fixture.authority_fingerprint())

    def test_frozen_snapshot_remains_detached_after_simulation_changes(self):
        with self.fixture() as fixture:
            sim = fixture.sim
            sim.state.player_fx, sim.state.player_fy = .125, .875
            npc = self.npc(sim, 'local', fx=.25, fy=.75)
            sim.npcs.rebuild_spatial_index()
            weather = {'kind': 'snow', 'rain': 6, 'fog': 25, 'cloud_cover': 80,
                       'wind_dx': 1024, 'wind_dy': -512, 'wind_speed': 50}
            with patch.object(sim.environment, 'visual_conditions', return_value=(weather, None)):
                snapshot = capture_live_scene(sim, self.camera(sim))
            frame, atmosphere = self.frame(snapshot), snapshot.atmosphere(2.)
            self.assertEqual(snapshot.viewer, WorldFoot(256.125, 256.875, 0))
            self.assertEqual(snapshot.actors[0].foot, WorldFoot(256.25, 256.75, 0))
            self.assertAlmostEqual(atmosphere.snow, .6)
            self.assertEqual(atmosphere.rain, 0.)
            self.assertEqual((atmosphere.wind_x, atmosphere.wind_y), (.5, -.25))
            with self.assertRaises(FrozenInstanceError):
                snapshot.minute = 0
            npc.x, npc.fx = 300, .9
            sim._visible_tile_set.clear()
            sim.clock.advance(200)
            sim.world.cache._chunks.clear()
            sim.resources._feature_chunk_cache.clear()
            weather.update(kind='rain', rain=0, fog=100)
            with patch.object(sim.world, 'prepared_tile_at', unexpected), \
                    patch.object(sim.resources, 'prepared_feature_at', unexpected):
                self.assertEqual(frame, self.frame(snapshot))
                self.assertEqual(atmosphere, snapshot.atmosphere(2.))
            self.assertFalse(any(hasattr(actor, 'name') or hasattr(actor, 'inventory')
                                 for actor in snapshot.actors))

    def test_production_circular_sight_and_tree_los_authorize_exact_live_cells(self):
        from worldseed.sim.engine import Simulation
        with self.fixture() as fixture:
            sim = fixture.sim
            # The prepared fixture suppresses startup discovery; invoke the real
            # simulation path once before capture, as a gameplay update does.
            # Its initial prepared view represents an earlier observation. New
            # memory never reconstructs hidden props from today's live state.
            observe_exterior(sim,{tuple(map(int,token.split(',')))
                                  for token in sim.visible_tiles_set})
            Simulation._discover(sim, sim.player_pos)
            current = frozenset(tuple(map(int, token.split(',')))
                                for token in sim.visible_tiles_set)
            radius = sim.visibility_radius(sim.player_pos)
            self.assertGreater(len(current), 1)
            self.assertTrue(all((x-256)**2 + (y-256)**2 <= radius**2
                                for x, y, _ in current))
            before = fixture.authority_fingerprint()
            with patch.object(sim, '_discover', unexpected), \
                    patch.object(sim.world, 'tile_at', unexpected), \
                    patch.object(sim.resources, 'feature_at', unexpected):
                snapshot = capture_live_scene(sim, self.camera(sim))
                frame = self.frame(snapshot)
            self.assertTrue(snapshot.current_cells)
            self.assertLessEqual(snapshot.current_cells, current)
            self.assertTrue(snapshot.remembered_cells)
            self.assertEqual(set(dict(snapshot.terrain)),
                             snapshot.current_cells | snapshot.remembered_cells)
            self.assertEqual(len(frame.ground),
                             len(snapshot.current_cells | snapshot.remembered_cells))
            self.assertEqual(frame.visible_ground_cells, len(snapshot.current_cells))
            for x, y, z in snapshot.remembered_cells:
                remembered = next(command for command in frame.ground
                                  if command.visual_id == f'ground:{z}:{x}:{y}')
                self.assertAlmostEqual(remembered.opacity, .62)
                self.assertFalse(any(command.visual_id.startswith(f'feature:{z}:{x}:{y}:')
                                     for command in frame.scenery))
            blinded = snapshot.gpu_frame(
                materials=FakeAssets(), registry=self.registry,
                resource_style=lambda _: {'width': 1.3, 'height': 1.9},
                show_explored_memory=False)
            self.assertEqual(len(blinded.ground), len(snapshot.current_cells))
            self.assertTrue(all(command.opacity == 1 for command in blinded.ground))
            self.assertEqual(before, fixture.authority_fingerprint())

    def test_unknown_memory_and_missing_cache_never_reveal_live_geometry(self):
        with self.fixture() as fixture:
            sim = fixture.sim
            current, missing, memory = (256, 256, 0), (255, 256, 0), (257, 256, 0)
            self.feature(sim, current, 'core:oak_tree')
            self.feature(sim, memory, 'core:pine_tree')
            observe_exterior(sim,{memory})
            sim._visible_tile_set = MembershipOnly(pos_key(*cell) for cell in (current, missing))
            sim._discovered_tile_set = MembershipOnly(pos_key(*cell) for cell in (current, missing, memory))
            missing_key, _, _ = split_world(WorldPos(*missing))
            sim.world.cache._chunks.pop(missing_key)
            tile_at = sim.world.prepared_tile_at
            reads = []

            def admitted_tile(pos):
                cell = (pos.x, pos.y, pos.z)
                self.assertIn(cell, (current, missing))
                reads.append(cell)
                return tile_at(pos)

            with patch.object(sim.world, 'prepared_tile_at', admitted_tile), \
                    patch.object(sim.world.cache, 'get', unexpected), \
                    patch.object(sim.resources, '_load_prepared_feature_chunk', unexpected):
                snapshot = capture_live_scene(sim, self.camera(sim))
            self.assertEqual(snapshot.current_cells, frozenset((current,)))
            self.assertEqual(snapshot.remembered_cells, frozenset((memory,)))
            self.assertEqual(set(dict(snapshot.terrain)), {current, memory})
            self.assertEqual({cell for cell, _ in snapshot.resources}, {current})
            self.assertEqual(dict(snapshot.remembered_resources)[memory].feature_id,'core:pine_tree')
            frame = self.frame(snapshot)
            self.assertEqual(len(frame.ground), 2)
            self.assertEqual(frame.visible_ground_cells, 1)
            self.assertTrue(any('pine' in command.texture_id and command.visual_id.startswith('memory:')
                                for command in frame.scenery))
            self.assertGreaterEqual(len(reads), 3)
            # Losing the already prepared resource map preserves known ground;
            # it must not trigger disk reads, raw feature choice or generation.
            key, _, _ = split_world(WorldPos(*current))
            sim.resources._feature_chunk_cache.pop((key.x, key.y, snapshot.season))
            snapshot = capture_live_scene(sim, self.camera(sim))
            self.assertTrue(snapshot.terrain)
            self.assertEqual(snapshot.resources, ())

    def test_actor_queries_use_indexes_and_preserve_sight_life_elevation_and_roofs(self):
        with self.fixture(distant_npcs=80) as fixture:
            sim = fixture.sim
            self.npc(sim, 'living', fx=.2, fy=.8)
            self.npc(sim, 'dead', alive=False)
            self.npc(sim, 'zero-hp', hp=0)
            self.npc(sim, 'inside')
            self.npc(sim, 'hidden', (260, 256, 0))
            self.npc(sim, 'roofed', (258, 256, 0))
            self.npc(sim, 'other-level', (256, 256, 1))
            sim.state.interior_actors['inside'] = InteriorActor('private:room', 100, 100)
            sim.state.roofs[pos_key(258, 256, 0)] = RoofState('core:thatch_roof', 258, 256, 0)
            sim._visible_tile_set.discard(pos_key(260, 256, 0))
            for uid, x, z, hp in (('living', 257, 0, 50), ('dead', 257, 0, 0),
                                  ('hidden', 260, 0, 50), ('roofed', 258, 0, 50),
                                  ('other-level', 256, 1, 50), ('distant', 100000, 0, 50)):
                sim.state.creatures[uid] = CreatureState(uid, 'core:deer', x, 256, z, hp)
            sim.npcs.rebuild_spatial_index()
            sim.state.npcs = IndexedOnlyDict(sim.state.npcs)
            with patch.object(sim.state.creatures, 'values', unexpected), \
                    patch.object(sim.state.creatures, 'items', unexpected), \
                    patch.object(sim.npcs, 'rebuild_spatial_index', unexpected):
                snapshot = capture_live_scene(sim, self.camera(sim))
            self.assertEqual({actor.uid for actor in snapshot.actors},
                             {'npc:living', 'creature:living'})
            self.assertEqual(next(actor.foot for actor in snapshot.actors if actor.uid == 'npc:living'),
                             WorldFoot(256.2, 256.8, 0))
            self.assertNotIn((258, 256, 0), snapshot.current_cells)
            # A collapsed roof no longer conceals its exterior cell.
            sim.state.roofs[pos_key(258, 256, 0)].condition = 0
            self.assertIn((258, 256, 0), capture_live_scene(sim, self.camera(sim)).current_cells)

    def test_real_planned_shells_stay_closed_and_entered_interior_is_local(self):
        with self.fixture('village_street') as fixture:
            sim = fixture.sim
            camera = self.camera(sim)
            from worldseed.presentation.gpu_scene_bridge import cell_bounds
            left, top, right, bottom = cell_bounds(camera)
            roof = next((x, y, 0) for (x, y) in sim.settlement_physicalization._cells
                        if left <= x < right and top <= y < bottom
                        and sim.settlement_physicalization.shell_at(WorldPos(x, y, 0)) is not None)
            self.npc(sim, 'private-resident', roof)
            sim.npcs.rebuild_spatial_index()
            sim.state.fires['private-fire'] = FireCell(*roof, 80, 80)
            sim.state.creatures['private-pet'] = CreatureState('private-pet', 'core:deer', *roof, 50)
            snapshot = capture_live_scene(sim, camera)
            self.assertNotIn(roof, snapshot.current_cells | snapshot.remembered_cells)
            self.assertFalse(any(actor.uid in ('npc:private-resident', 'creature:private-pet')
                                 for actor in snapshot.actors))
            self.assertFalse(any(fire.cell == roof for fire in snapshot.fires))
        with self.fixture('interior') as fixture:
            sim = fixture.sim
            before = fixture.authority_fingerprint()
            with patch.object(sim.world, 'prepared_tile_at', unexpected), \
                    patch.object(sim.npcs, 'indexed_npcs_in_rect', unexpected):
                snapshot = capture_live_scene(sim, self.camera(sim))
                frame = self.frame(snapshot)
            self.assertTrue(snapshot.interior)
            self.assertEqual((snapshot.terrain, snapshot.resources, snapshot.actors,
                              snapshot.fires, snapshot.weather), ((), (), (), (), ()))
            self.assertIsNotNone(snapshot.interior_scene)
            self.assertTrue(frame.commands)
            self.assertEqual(before, fixture.authority_fingerprint())

    def test_fires_require_current_prepared_cell_fuel_and_correct_level(self):
        with self.fixture('camp') as fixture:
            sim = fixture.sim
            sim.state.fires.clear()
            for key, x, z, intensity, fuel in (('live', 256, 0, 68, 50),
                    ('spent', 257, 0, 80, 0), ('dark', 258, 0, 0, 50),
                    ('hidden', 260, 0, 80, 50), ('other-level', 256, 1, 80, 50),
                    ('distant', 100000, 0, 80, 50)):
                sim.state.fires[key] = FireCell(x, 256, z, intensity, fuel)
            sim._visible_tile_set.discard(pos_key(260, 256, 0))
            with patch.object(sim.state.fires, 'values', unexpected), \
                    patch.object(sim.state.fires, 'items', unexpected):
                snapshot = capture_live_scene(sim, self.camera(sim))
            self.assertEqual([(fire.cell, fire.intensity) for fire in snapshot.fires],
                             [((256, 256, 0), 68)])
            fx = snapshot.atmosphere()
            self.assertEqual(len(fx.lights), 1)
            light = fx.lights[0]
            self.assertEqual((light.x, light.y), snapshot.camera.to_screen(WorldFoot(256.5, 256.5, 0)))
            self.assertLessEqual(light.radius, snapshot.camera.scale * .5)
            self.assertAlmostEqual(light.strength, .8)
            sim.entities.get(sim.player_id, Position).value = WorldPos(256, 256, -1)
            with patch.object(sim.environment, 'visual_conditions', unexpected):
                underground = capture_live_scene(sim, self.camera(sim))
            self.assertEqual(underground.weather, ())
            self.assertEqual(underground.fires, ())

    def test_harvest_stages_keep_resource_identity_and_remove_full_tree_layers(self):
        with self.fixture() as fixture:
            sim = fixture.sim
            stump, sapling = (256, 256, 0), (257, 256, 0)
            self.feature(sim, stump, 'core:oak_tree')
            self.feature(sim, sapling, 'core:pine_tree')
            sim.state.resource_depletion[pos_key(*stump)] = sim.clock.minute - 1
            sim.state.resource_depletion[pos_key(*sapling)] = sim.clock.minute - 50 * 1440
            snapshot = capture_live_scene(sim, self.camera(sim))
            resources = dict(snapshot.resources)
            self.assertEqual((resources[stump].feature_id, resources[stump].stage),
                             ('core:oak_tree', 'stump'))
            self.assertEqual((resources[sapling].feature_id, resources[sapling].stage),
                             ('core:pine_tree', 'sapling'))
            frame = self.frame(snapshot)
            for cell, fid, stage, asset in ((stump, 'core:oak_tree', 'stump', 'rotten_stump_cache.png'),
                                          (sapling, 'core:pine_tree', 'sapling', 'logging_sapling.png')):
                x, y, z = cell
                prefix = f'feature:{z}:{x}:{y}:{fid}'
                commands = [command for command in frame.scenery if command.visual_id.startswith(prefix)]
                self.assertEqual(len(commands), 1)
                self.assertEqual(commands[0].visual_id, prefix + f':{stage}:base')
                self.assertTrue(commands[0].texture_id.endswith(asset))
            self.assertEqual(sim.world.prepared_tile_at(WorldPos(*stump)).terrain_id, 'core:forest')

    def test_rejects_excess_viewport_actor_resource_and_fire_budgets(self):
        with self.fixture() as fixture:
            sim = fixture.sim
            with self.assertRaisesRegex(ValueError, 'world-cell budget'):
                capture_live_scene(sim, WorldCamera(WorldFoot(256, 256, 0), 3840, 2160, 10))
            with self.assertRaisesRegex(ValueError, 'elevation'):
                capture_live_scene(sim, self.camera(sim, z=1))
            for i in range(MAX_PREPARED_ACTORS):
                self.npc(sim, f'crowd:{i}')
            sim.npcs.rebuild_spatial_index()
            with self.assertRaisesRegex(ValueError, 'actor budget'):
                capture_live_scene(sim, self.camera(sim))
            sim.state.npcs.clear()
            sim.npcs.rebuild_spatial_index()
            with patch('worldseed.presentation.live_gpu_scene.MAX_PREPARED_RESOURCES', 1):
                with self.assertRaisesRegex(ValueError, 'resource budget'):
                    capture_live_scene(sim, self.camera(sim))
            for i in range(33):
                sim.state.fires[f'fire:{i}'] = FireCell(256, 256, 0, 50, 50)
            with self.assertRaisesRegex(ValueError, 'fire budget'):
                capture_live_scene(sim, self.camera(sim))
            sim.state.player_fx = float('nan')
            with self.assertRaisesRegex(ValueError, 'fraction must be finite'):
                player_foot(sim)
