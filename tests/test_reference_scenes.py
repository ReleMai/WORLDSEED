"""Real-renderer QA fixtures stay repeatable, bounded and observational."""
from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
os.environ.setdefault('SDL_AUDIODRIVER', 'dummy')

from tools.reference_scene_fixtures import SCENES, build_fixture
from tools.reference_scenes import (
    frozen_visual_clock, main, run_scene, service_events, validate_settings,
)
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.core.coords import WorldPos
from worldseed.ui.pygame_terminal import PygameTerminal


class ReferenceSettingsTests(unittest.TestCase):
    def test_cli_bounds_reject_unbounded_work_before_fixture_build(self):
        settings = dict(frames=1, warmup=0, width=1280, height=720, zoom=28,
                        distant_npcs=0, seed='reference')
        validate_settings(**settings)
        for name, invalid in (('frames', 0), ('frames', 601), ('warmup', -1),
                              ('warmup', 121), ('width', 639), ('width', 3841),
                              ('height', 479), ('height', 2161), ('zoom', 1),
                              ('distant_npcs', -1), ('distant_npcs', 50001),
                              ('frames', True), ('seed', ''), ('seed', 'x'*257)):
            with self.subTest(name=name, invalid=invalid), self.assertRaises(ValueError):
                validate_settings(**(settings | {name: invalid}))
        with patch('tools.reference_scenes.build_fixture') as build:
            with self.assertRaises(SystemExit) as error:
                main(['--frames', '601', '--output-dir', '/tmp/unused-reference-test'])
            self.assertEqual(error.exception.code, 2)
            build.assert_not_called()

    def test_quit_and_escape_stop_at_event_boundary(self):
        pg = SimpleNamespace(QUIT=1, KEYDOWN=2, K_ESCAPE=27, VIDEORESIZE=3,
                             WINDOWRESIZED=4, NOEVENT=0,
                             event=SimpleNamespace(get=lambda: [SimpleNamespace(type=1)]))
        self.assertFalse(service_events(SimpleNamespace(pg=pg)))
        pg.event.get = lambda: [SimpleNamespace(type=2, key=27)]
        self.assertFalse(service_events(SimpleNamespace(pg=pg)))
        pg.event.get = lambda: [SimpleNamespace(type=2, key=99)]
        self.assertTrue(service_events(SimpleNamespace(pg=pg)))

    def test_visual_clock_restored_on_failure(self):
        original = lambda: 1234
        pg = SimpleNamespace(time=SimpleNamespace(get_ticks=original))
        with self.assertRaisesRegex(RuntimeError, 'body failed'):
            with frozen_visual_clock(pg):
                self.assertEqual(pg.time.get_ticks(), 1600)
                raise RuntimeError('body failed')
        self.assertIs(pg.time.get_ticks, original)


class PreparedFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    def test_village_uses_production_plan_portals_and_observational_queries(self):
        with TemporaryDirectory() as directory:
            fixture = build_fixture('village_street', self.registry, Path(directory))
            try:
                physical = fixture.sim.settlement_physicalization
                skeleton = physical.skeleton_for('reference:town')
                self.assertGreater(len(skeleton.structures), 40)
                self.assertEqual(fixture.plan_fingerprint, skeleton.fingerprint)
                self.assertEqual(fixture.counts()['planned_structures'], len(skeleton.structures))
                center = fixture.sim.player_pos
                for npc in fixture.sim.state.npcs.values():
                    self.assertIn(npc, fixture.sim.npcs.indexed_npcs_in_rect(npc.x, npc.y, npc.x, npc.y, npc.z))
                self.assertTrue(physical.passable(center, True))
                self.assertIsNone(physical.shell_at(center))
                before = fixture.authority_fingerprint()
                for structure in skeleton.structures:
                    if not structure.enclosed:
                        continue
                    shell = physical.shell_at(WorldPos(*structure.footprint[0]))
                    self.assertEqual(shell.uid, structure.uid)
                    self.assertEqual(fixture.sim.property_security.door_by_id(shell.door_uid).property_id,
                                     structure.uid)
                    self.assertTrue(physical.passable(physical.frontage_for(structure.uid), True))
                self.assertEqual(before, fixture.authority_fingerprint())
                with self.assertRaisesRegex(RuntimeError, 'raw generation'):
                    fixture.world.tile_at(WorldPos(1000000, 1000000))
                with self.assertRaisesRegex(RuntimeError, 'raw generation'):
                    fixture.sim.settlement_planner.plan(None, 'missing', 10)
                self.assertEqual(len(fixture.db.load_sim_state()['npcs']), 24)
                self.assertGreater(fixture.state_json_bytes, 100000)
                self.assertEqual(fixture.db.verify(), [])
            finally:
                fixture.close()


@unittest.skipUnless(PygameTerminal.available(), 'pygame optional')
class ReferenceRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    def test_six_scenes_use_real_renderer_without_mutation_or_generation(self):
        with TemporaryDirectory() as directory:
            output = Path(directory)
            player_save = output/'player-save.db'
            player_save.write_bytes(b'player save must survive')
            reports = {}
            for scene in SCENES:
                with self.subTest(scene=scene):
                    report = run_scene(scene, output_dir=output, frames=2, warmup=1,
                                       headless=True, png=True, registry=self.registry)
                    reports[scene] = report
                    self.assertEqual(report['frames_measured'], 2)
                    self.assertTrue(report['authority_unchanged'])
                    self.assertEqual(report['fixture_mode'], 'prepared-synthetic-qa')
                    self.assertEqual(report['driver'], 'dummy')
                    self.assertEqual(report['size'], [1280, 720])
                    self.assertGreater(report['save_bytes'], report['state_json_bytes'])
                    self.assertTrue(Path(report['png']).exists())
                    self.assertEqual(json.loads((output/f'{scene}.json').read_text()), report)
                    stages = report['timings']['stages']
                    for stage in ('reference.iteration', 'render.frame', 'render.prepare',
                                  'render.terrain', 'render.objects_actors', 'render.effects',
                                  'render.ui', 'render.present'):
                        self.assertEqual(stages[stage]['count'], 2, stage)
                        self.assertGreaterEqual(stages[stage]['p99_ms'], stages[stage]['p50_ms'])
                    if scene == 'open_panel':
                        self.assertEqual(stages['render.panel']['count'], 2)
            self.assertGreater(reports['interior']['state_counts']['interiors'], 0)
            self.assertEqual(reports['camp']['state_counts']['structures'], 3)
            self.assertEqual(reports['large_save']['state_counts']['distant_npcs'], 1000)
            self.assertEqual(reports['large_save']['plan_fingerprint'], reports['village_street']['plan_fingerprint'])
            self.assertGreater(reports['large_save']['state_json_bytes'], reports['village_street']['state_json_bytes'])
            self.assertEqual(player_save.read_bytes(), b'player save must survive')

    def test_frozen_scene_pixels_and_state_repeat_across_independent_runs(self):
        with TemporaryDirectory() as directory:
            first = run_scene('forest', output_dir=Path(directory)/'first', frames=2, warmup=1,
                              headless=True, registry=self.registry)
            second = run_scene('forest', output_dir=Path(directory)/'second', frames=3, warmup=2,
                               headless=True, registry=self.registry)
            self.assertEqual(first['pixel_sha256'], second['pixel_sha256'])
            self.assertEqual(first['authority_fingerprint'], second['authority_fingerprint'])

    def test_allocation_report_and_explicit_zero_distant_override(self):
        with TemporaryDirectory() as directory:
            report = run_scene('large_save', output_dir=directory, frames=1, warmup=1,
                               distant_npcs=0, headless=True, allocations=True,
                               registry=self.registry)
            self.assertEqual(report['state_counts']['distant_npcs'], 0)
            self.assertIsNone(report['png'])
            self.assertGreaterEqual(report['allocations']['peak_bytes'], report['allocations']['current_bytes'])
            self.assertEqual(report['allocations']['peak_scope'], 'measured_frames')

    def test_idle_movement_probe_records_actual_update_without_mutation(self):
        with TemporaryDirectory() as directory:
            report = run_scene('forest', output_dir=directory, frames=3, warmup=1,
                               distant_npcs=1000, headless=True, idle_movement_probe=True,
                               registry=self.registry)
            self.assertTrue(report['authority_unchanged'])
            self.assertTrue(report['idle_movement_probe'])
            self.assertEqual(report['state_counts']['distant_npcs'], 1000)
            self.assertEqual(report['timings']['stages']['simulation.free_movement']['count'], 3)

    def test_event_interruption_reports_zero_frames_and_restores_pygame(self):
        with TemporaryDirectory() as directory, patch('tools.reference_scenes.service_events', return_value=False):
            report = run_scene('forest', output_dir=directory, frames=2, warmup=1,
                               headless=True, registry=self.registry)
            self.assertTrue(report['interrupted'])
            self.assertEqual(report['frames_measured'], 0)
            self.assertIsNone(report['pixel_sha256'])
            self.assertFalse(report['timings']['stages'])


if __name__ == '__main__':
    unittest.main()
