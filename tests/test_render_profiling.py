"""Bounded renderer timing and observational checks on prepared SDL scenes."""
import copy
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from worldseed.ui.pygame_terminal import PygameTerminal, _RenderTimings


class RenderTimingsTests(unittest.TestCase):
    def test_disabled_does_not_access_clock_or_record(self):
        class DisabledProfiler:
            enabled = False

            @property
            def clock(self):
                raise AssertionError('disabled profiling accessed its clock')

            def record(self, *args):
                raise AssertionError('disabled profiling recorded a sample')

        timings = _RenderTimings(DisabledProfiler())
        self.assertIsNone(timings.start())
        timings.sample('render.terrain_cache', None)
        timings.mark('render.prepare')
        timings.finish()

    def test_interleaved_phases_are_one_sample_each(self):
        profiler = SimpleNamespace(enabled=True, clock=Mock(side_effect=[0, .001, .003, .008, .010]),
                                   record=Mock())
        timings = _RenderTimings(profiler)
        timings.mark('render.prepare')
        timings.mark('render.effects')
        timings.mark('render.effects')
        timings.mark('render.present')
        timings.finish()
        samples = {call.args[0]: call.args[1] for call in profiler.record.call_args_list}
        self.assertEqual(profiler.record.call_count, 4)
        self.assertAlmostEqual(samples['render.prepare'], 1.0)
        self.assertAlmostEqual(samples['render.effects'], 7.0)
        self.assertAlmostEqual(samples['render.present'], 2.0)
        self.assertAlmostEqual(samples['render.frame'], 10.0)

    def test_clock_and_record_failures_leave_drawing_free_to_continue(self):
        for clock in (Mock(side_effect=RuntimeError('clock unavailable')),
                      Mock(side_effect=[0, .001, RuntimeError('clock unavailable')]),
                      Mock(side_effect=[0, .001, .002]),
                      Mock(return_value='invalid-clock'), Mock(return_value=float('nan'))):
            with self.subTest(clock=clock):
                profiler = SimpleNamespace(enabled=True, clock=clock,
                                           record=Mock(side_effect=RuntimeError('diagnostics unavailable')))
                timings = _RenderTimings(profiler)
                timings.mark('render.prepare')
                timings.mark('render.present')
                timings.finish()


@unittest.skipUnless(PygameTerminal.available(), 'pygame optional for terminal-only environments')
class RenderProfilingTests(unittest.TestCase):
    def setUp(self):
        from worldseed.config import DATA_DIR
        from worldseed.content.registry import ContentRegistry
        from worldseed.core.coords import ChunkKey, WorldPos
        from worldseed.entities.components import Inventory, Position, Vitals
        from worldseed.entities.store import EntityStore
        from worldseed.persistence.database import WorldDatabase
        from worldseed.sim.engine import Simulation
        from worldseed.systems.state import LivingWorldState
        from worldseed.world.chunk import Chunk
        from worldseed.world.generator import WorldGenerator
        from worldseed.world.world import World

        env = patch.dict(os.environ, {'SDL_VIDEODRIVER': 'dummy', 'SDL_AUDIODRIVER': 'dummy'})
        env.start()
        self.addCleanup(env.stop)
        self.term = PygameTerminal(800, 520)
        self.term.enter()
        self.addCleanup(self.term.restore)
        self.term.clock = SimpleNamespace(tick=Mock(return_value=0))
        folder = tempfile.TemporaryDirectory(prefix='worldseed-render-profile-')
        self.addCleanup(folder.cleanup)
        seed = b'render-profile-prepared'
        self.registry = ContentRegistry.load(DATA_DIR)
        self.database = WorldDatabase.create(Path(folder.name) / 'scene.db', 'Render timing fixture', seed.hex())
        self.addCleanup(self.database.close)
        self.world = World(WorldGenerator(seed, self.registry), self.registry, self.database)
        chunk = Chunk.empty(ChunkKey(0, 0, 0))
        ground = self.registry.terrain_index('core:grass')
        for index in range(len(chunk.terrain)):
            chunk.terrain[index] = ground
        self.world.cache.put(chunk.key, chunk)
        self.entities = EntityStore()
        self.player_id = self.entities.spawn(preferred_id=1)
        self.entities.add(self.player_id, Position(WorldPos(0, 0, 0)))
        self.entities.add(self.player_id, Inventory())
        self.entities.add(self.player_id, Vitals())
        state = LivingWorldState(discovered_tiles=['0,0,0'], clock_minute=720)
        # The fixture is already prepared. Construction must not generate the
        # unrelated regional world merely to exercise a drawing boundary.
        with patch.object(Simulation, '_ensure_nearby_world'):
            self.sim = Simulation(self.world, self.entities, self.registry, 0, state, seed)
        self.sim._visible_tile_set = {'0,0,0'}

    def _snapshot(self):
        return copy.deepcopy((self.sim.state.to_dict(), self.sim.clock.minute, self.sim.turn,
                              self.entities._components, self.world.dirty_tiles,
                              self.world.revision))

    def _render(self):
        from worldseed.core.rng import PCG32
        # Prepared render paths may use deterministic hashes for visual choice,
        # but must not consume gameplay RNG, generate terrain or advance play.
        with patch.object(self.term.pg.time, 'get_ticks', return_value=640), \
                patch.object(self.world.generator, 'generate_chunk', side_effect=AssertionError('render generated terrain')), \
                patch.object(self.sim.region_planner, 'plan', side_effect=AssertionError('render planned regions')), \
                patch.object(self.sim, 'execute', side_effect=AssertionError('render dispatched gameplay')), \
                patch.object(self.sim, '_discover', side_effect=AssertionError('render discovered terrain')), \
                patch.object(PCG32, 'u32', side_effect=AssertionError('render consumed gameplay RNG')):
            self.term.present_game(self.registry, self.world, self.entities, self.sim, self.player_id)
        return self.term.pg.image.tobytes(self.term.screen, 'RGB')

    def test_surface_profile_is_observational_and_disabled_never_reads_clock(self):
        from worldseed.profiling import RuntimeProfiler

        before = self._snapshot()
        disabled_clock = Mock(side_effect=AssertionError('disabled profiler clock called'))
        self.sim.profiler = RuntimeProfiler(enabled=False, clock=disabled_clock)
        baseline = self._render()
        disabled_clock.assert_not_called()
        self.sim.profiler = RuntimeProfiler(enabled=True)
        profiled = self._render()
        self.assertEqual(profiled, baseline)
        self.assertEqual(self._snapshot(), before)
        stages = self.sim.profiler.snapshot()['stages']
        self.assertEqual(set(stages), {'render.prepare', 'render.terrain_cache', 'render.terrain',
                                      'render.objects_actors', 'render.effects', 'render.ui',
                                      'render.present', 'render.frame'})
        self.assertTrue(all(stage['count'] == 1 for stage in stages.values()))
        self.term.clock.tick.assert_called_with(120)

    def test_unchanged_discovered_base_does_not_rescan_terrain(self):
        from worldseed.core.coords import WorldPos

        self._render()
        stable,left,top,surface,_=self.term._base_scroll_state
        _,z,cols,rows,tile_px,_=stable
        known=self.sim.discovered_tiles_set
        old_stamp=self.term._base_scroll_discovery_stamp
        with patch.object(self.world,'tile_at',side_effect=AssertionError('rescanned unchanged base')):
            reused=self.term._build_base_layer(self.world,known,z,left,top,cols,rows,tile_px)
        self.assertIs(reused,surface)
        self.assertEqual(old_stamp,self.term._base_scroll_discovery_stamp)

        # A newly revealed neighbor changes terrain blending. Do not reuse a
        # stale base even if a later removal preserves the discovery count.
        unknown_cells=[
            f'{x},{y},{z}'
            for y in range(max(0,top),min(32,top+rows))
            for x in range(max(0,left),min(32,left+cols))
            if f'{x},{y},{z}' not in known
        ]
        self.assertGreaterEqual(len(unknown_cells),2)
        first,second=unknown_cells[:2]
        known.add(first)
        with patch.object(self.world,'tile_at',wraps=self.world.tile_at) as read:
            self.term._build_base_layer(self.world,known,z,left,top,cols,rows,tile_px)
            self.assertGreater(read.call_count,0)
        self.assertNotEqual(old_stamp,self.term._base_scroll_discovery_stamp)
        previous=self.term._base_scroll_discovery_stamp
        # Same-count replacement is still a new discovery revision.
        known.discard(first)
        known.add(second)
        self.assertNotEqual(previous,(id(known.tiles),known.tiles.revision))
        with patch.object(self.world,'tile_at',wraps=self.world.tile_at) as read:
            self.term._build_base_layer(self.world,known,z,left,top,cols,rows,tile_px)
            self.assertGreater(read.call_count,0)
        self.world.set_terrain(WorldPos(0,0,0),'core:rock')
        with patch.object(self.world,'tile_at',wraps=self.world.tile_at) as read:
            self.term._build_base_layer(self.world,known,z,left,top,cols,rows,tile_px)
            self.assertGreater(read.call_count,0)

    def test_terrain_projection_reuses_readonly_cell_classification(self):
        from worldseed.core.coords import WorldPos

        baseline=self._render()
        first=getattr(self.term,'_terrain_overlay_projection_cache',None)
        self.assertIsNotNone(first)
        self.assertEqual(self._render(),baseline)
        second=self.term._terrain_overlay_projection_cache
        self.assertIs(first,second)
        # A gameplay-authoritative tile edit invalidates the projection.
        self.world.set_terrain(WorldPos(0,0,0),'core:rock')
        self._render()
        third=self.term._terrain_overlay_projection_cache
        self.assertIsNot(third,second)
        self.assertNotEqual(third[0],second[0])
        # Visibility and viewport changes also force recomputation, even if
        # counts happen to be identical across consecutive frames.
        self.sim._visible_tile_set=set()
        self._render()
        self.assertIsNot(self.term._terrain_overlay_projection_cache,third)

    def test_interior_profile_preserves_state_and_excludes_pacing_wait(self):
        from tests.test_interiors import sample_plan
        from worldseed.profiling import RuntimeProfiler
        from worldseed.systems.interior_state import InteriorActor

        plan = sample_plan()
        self.sim.state.interiors[plan.uid] = plan
        self.sim.state.interior_actors['player'] = InteriorActor(plan.uid, plan.entry_x, plan.entry_y)
        before = self._snapshot()
        virtual_time = [0.0]
        self.sim.profiler = RuntimeProfiler(enabled=True, clock=lambda: virtual_time[0])

        def flip():
            virtual_time[0] += .025

        def pace(fps):
            self.assertEqual(fps, 120)
            virtual_time[0] += 10.0

        self.term.clock.tick.side_effect = pace
        with patch.object(self.term.pg.display, 'flip', side_effect=flip):
            self._render()
        self.assertEqual(self._snapshot(), before)
        stages = self.sim.profiler.snapshot()['stages']
        self.assertEqual(set(stages), {'render.prepare', 'render.terrain', 'render.objects_actors',
                                      'render.effects', 'render.ui', 'render.present', 'render.frame'})
        self.assertAlmostEqual(stages['render.present']['worst_ms'], 25.0)
        self.assertAlmostEqual(stages['render.frame']['worst_ms'], 25.0)
        self.assertAlmostEqual(virtual_time[0], 10.025)

    def test_failed_diagnostics_do_not_interrupt_surface_render_or_change_pixels(self):
        from worldseed.profiling import RuntimeProfiler

        self.sim.profiler = RuntimeProfiler(enabled=False)
        baseline = self._render()
        before = self._snapshot()
        for profiler in (SimpleNamespace(enabled=True, clock=Mock(side_effect=RuntimeError('clock failed')),
                                         record=Mock()),
                         SimpleNamespace(enabled=True, clock=lambda: 0.0,
                                         record=Mock(side_effect=RuntimeError('record failed')))):
            with self.subTest(profiler=profiler):
                self.sim.profiler = profiler
                self.assertEqual(self._render(), baseline)
                self.assertEqual(self._snapshot(), before)

    def test_combat_animation_reports_intentional_wait_outside_ordinary_frame(self):
        from worldseed.profiling import RuntimeProfiler

        virtual_time = [0.0]
        profiler = RuntimeProfiler(enabled=True, clock=lambda: virtual_time[0])
        self.sim.visual_effects = [{'uid': 1, 'kind': 'projectile',
                                   'source': (0, 0, 0), 'target': (1, 1, 0)}]
        before = self._snapshot()
        self.term.screen.fill((43, 59, 71))
        pixels = self.term.pg.image.tobytes(self.term.screen, 'RGB')

        def animation_pace(fps):
            self.assertEqual(fps, 120)
            virtual_time[0] += .060

        self.term.clock.tick.side_effect = animation_pace
        timings = _RenderTimings(profiler)
        timings.mark('render.prepare')
        with patch.object(self.term.pg.time, 'get_ticks', side_effect=[0, 0, 120]):
            self.term._play_combat_effects(self.sim, self.term.pg.Rect(0, 0, 100, 100),
                                          0, 0, 20, 0, timings=timings)
        timings.mark('render.effects')
        virtual_time[0] += .002
        timings.mark('render.present')
        timings.finish()
        stages = profiler.snapshot()['stages']
        self.assertAlmostEqual(stages['render.action_animation']['worst_ms'], 120.0)
        self.assertAlmostEqual(stages['render.effects']['worst_ms'], 0.0)
        self.assertAlmostEqual(stages['render.frame']['worst_ms'], 2.0)
        self.assertEqual(self.term.pg.image.tobytes(self.term.screen, 'RGB'), pixels)
        self.assertEqual(self._snapshot(), before)

    def test_runtime_menu_and_feature_totals_include_pacing_explicitly(self):
        from worldseed.profiling import RuntimeProfiler

        virtual_time = [0.0]
        self.term._profiler = RuntimeProfiler(enabled=True, clock=lambda: virtual_time[0])
        before = self._snapshot()

        def pace(fps):
            self.assertEqual(fps, 120)
            virtual_time[0] += .050

        self.term.clock.tick.side_effect = pace
        self.term.present_menu('Pause', ['Continue'], 0)
        self.term.present_feature_menu('inventory_home', 'Inventory', ['Items'], 0)
        stages = self.term._profiler.snapshot()['stages']
        self.assertEqual(set(stages), {'render.menu_total', 'render.panel_total'})
        self.assertAlmostEqual(stages['render.menu_total']['worst_ms'], 50.0)
        self.assertAlmostEqual(stages['render.panel_total']['worst_ms'], 50.0)
        self.assertEqual(self._snapshot(), before)


if __name__ == '__main__':
    unittest.main()
