"""Runtime diagnostics preserve engine state, save retry and observational UI."""
from dataclasses import asdict
import itertools
import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tests import test_interior_engine, test_save_retry
from worldseed import app
from worldseed.config import DATA_DIR
from worldseed.content.registry import ContentRegistry
from worldseed.entities.components import Inventory, Position, Vitals
from worldseed.profiling import RuntimeProfiler
from worldseed.sim.commands import DropCommand, MoveCommand, PickupCommand
from worldseed.systems.state import LivingWorldState


class ProfilingIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = ContentRegistry.load(DATA_DIR)

    def make_profiler(self, enabled=True):
        clock = Mock(side_effect=itertools.count(start=0.0, step=0.001)) if enabled else Mock(
            side_effect=AssertionError("disabled profiler clock called"))
        return RuntimeProfiler(enabled=enabled, max_stages=64, clock=clock)

    def make_save_context(self, *, enabled=True, failing_commit=False):
        directory = tempfile.TemporaryDirectory(prefix="worldseed-profiling-save-")
        self.addCleanup(directory.cleanup)
        ctx = test_save_retry.make_save_fixture(directory.name, self.registry,
                                                failing_commit=failing_commit)
        self.addCleanup(ctx.db.close)
        ctx.sim.profiler = self.make_profiler(enabled)
        return ctx

    def prepared_simulation(self, *, enabled):
        sim, plan = test_interior_engine.InteriorEngineTests.prepared_simulation(self)
        sim.profiler = self.make_profiler(enabled)
        sim.debug.profiler = sim.profiler
        # The constructor fixture skips unrelated geography. Mark that anchor
        # prepared so this test exercises the real bounded preparation guard.
        sim._nearby_region_key = (0, 0)
        sim._nearby_ecology_key = (0, 0, 0)
        return sim, plan

    def run_player_sequence(self, sim):
        results = [
            sim.execute(MoveCommand(sim.player_id, 1, -1)),
            sim.execute(DropCommand(sim.player_id, "core:wood", 2)),
            sim.execute(PickupCommand(sim.player_id)),
        ]
        sim.advance_realtime(1)
        sim.update_free_movement(0.025, 1.0, 0.0)
        sim._ensure_nearby_world(sim.player_pos)
        return {
            "results": [asdict(result) for result in results],
            "state": sim.state.to_dict(),
            "minute": sim.clock.minute,
            "turn": sim.turn,
            "position": asdict(sim.entities.get(sim.player_id, Position)),
            "inventory": dict(sim.entities.get(sim.player_id, Inventory).items),
            "vitals": asdict(sim.entities.get(sim.player_id, Vitals)),
            "messages": [asdict(event) for event in sim.log],
        }

    def test_profiling_preserves_real_command_realtime_and_preparation_results(self):
        disabled, _ = self.prepared_simulation(enabled=False)
        enabled, _ = self.prepared_simulation(enabled=True)
        before_disabled = disabled.state.to_dict()
        before_enabled = enabled.state.to_dict()
        self.assertEqual(before_disabled, before_enabled)
        self.assertEqual(self.run_player_sequence(disabled), self.run_player_sequence(enabled))
        disabled.profiler.clock.assert_not_called()
        self.assertEqual(disabled.profiler.snapshot()["stages"], {})
        stages = enabled.profiler.snapshot()["stages"]
        self.assertEqual(stages["simulation.command"]["count"], 3)
        self.assertEqual(stages["simulation.realtime"]["count"], 1)
        self.assertEqual(stages["simulation.free_movement"]["count"], 1)
        self.assertEqual(stages["preparation.total"]["count"], 1)

    def test_existing_debug_stages_feed_profiler_without_optional_clock_calls(self):
        sim, _ = self.prepared_simulation(enabled=True)
        before = sim.state.to_dict()
        with sim.debug.stage("fixture_ready"):
            pass
        problem = ValueError("preparation fixture failure")
        with self.assertRaises(ValueError) as caught:
            with sim.debug.stage("fixture_failed"):
                raise problem
        self.assertIs(caught.exception, problem)
        self.assertEqual(sim.state.to_dict(), before)
        stages = sim.profiler.snapshot()["stages"]
        self.assertEqual(stages["preparation.fixture_ready"]["count"], 1)
        self.assertEqual(stages["preparation.fixture_failed"]["count"], 1)
        # Existing stage clocks supply the duration directly to record().
        sim.profiler.clock.assert_not_called()

    def test_profiled_save_reports_all_phases_and_reload_preserves_state(self):
        ctx = self.make_save_context()
        pos, before = test_save_retry.SaveRetryTests.begin_pending_checkpoint(self, ctx)
        app._save(ctx)
        stages = ctx.sim.profiler.snapshot()["stages"]
        self.assertTrue({"save.total", "save.capture", "save.backup", "save.database",
                         "save.json", "save.sql", "save.commit"}.issubset(stages), stages)
        self.assertFalse(ctx.world.dirty_tiles)
        self.assertEqual(ctx.db.load_sim_state(), ctx.sim.state.to_dict())
        self.assertEqual(ctx.db.verify(), [])
        test_save_retry.SaveRetryTests.retry_and_reload(self, ctx, pos)

    def test_disabled_save_profiler_never_reads_clock(self):
        ctx = self.make_save_context(enabled=False)
        pos, before = test_save_retry.SaveRetryTests.begin_pending_checkpoint(self, ctx)
        app._save(ctx, backup=False)
        ctx.sim.profiler.clock.assert_not_called()
        self.assertEqual(ctx.sim.profiler.snapshot()["stages"], {})
        test_save_retry.SaveRetryTests.retry_and_reload(self, ctx, pos)

    def test_profiled_serialization_failure_preserves_pending_checkpoint_and_retry(self):
        ctx = self.make_save_context()
        pos, before = test_save_retry.SaveRetryTests.begin_pending_checkpoint(self, ctx)
        snapshot = ctx.sim.state.to_dict()
        snapshot["unserializable_probe"] = object()
        with patch.object(LivingWorldState, "to_dict", return_value=snapshot):
            with self.assertRaises(TypeError):
                app._save(ctx, backup=False)
        test_save_retry.SaveRetryTests.assert_pending_checkpoint(self, ctx, pos, before)
        self.assertEqual(ctx.sim.profiler.snapshot()["stages"]["save.json"]["count"], 2)
        test_save_retry.SaveRetryTests.retry_and_reload(self, ctx, pos)

    def test_profiled_commit_failure_preserves_pending_checkpoint_and_retry(self):
        ctx = self.make_save_context(failing_commit=True)
        pos, before = test_save_retry.SaveRetryTests.begin_pending_checkpoint(self, ctx)
        ctx.db.connection.fail_next_commit = True
        with self.assertRaisesRegex(sqlite3.OperationalError, "commit failure"):
            app._save(ctx, backup=False)
        self.assertFalse(ctx.db.connection.in_transaction)
        test_save_retry.SaveRetryTests.assert_pending_checkpoint(self, ctx, pos, before)
        self.assertEqual(ctx.sim.profiler.snapshot()["stages"]["save.commit"]["count"], 2)
        test_save_retry.SaveRetryTests.retry_and_reload(self, ctx, pos)

    def test_profiled_sql_failure_records_rollback_and_preserves_retry(self):
        ctx = self.make_save_context()
        pos, before = test_save_retry.SaveRetryTests.begin_pending_checkpoint(self, ctx)
        ctx.db.connection.execute(
            "CREATE TEMP TRIGGER fail_checkpoint_tile BEFORE INSERT ON tile_deltas "
            "BEGIN SELECT RAISE(ABORT, 'injected profiled SQL failure'); END"
        )
        try:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "profiled SQL failure"):
                app._save(ctx, backup=False)
        finally:
            ctx.db.connection.execute("DROP TRIGGER IF EXISTS fail_checkpoint_tile")
        self.assertFalse(ctx.db.connection.in_transaction)
        test_save_retry.SaveRetryTests.assert_pending_checkpoint(self, ctx, pos, before)
        stages = ctx.sim.profiler.snapshot()["stages"]
        self.assertEqual(stages["save.sql"]["count"], 2)
        self.assertEqual(stages["save.rollback"]["count"], 1)
        test_save_retry.SaveRetryTests.retry_and_reload(self, ctx, pos)

    def test_failed_diagnostic_clock_does_not_interrupt_save_or_acknowledgement(self):
        ctx = self.make_save_context()
        ctx.sim.profiler.clock = Mock(side_effect=RuntimeError("diagnostic clock failure"))
        pos, before = test_save_retry.SaveRetryTests.begin_pending_checkpoint(self, ctx)
        app._save(ctx, backup=False)
        self.assertFalse(ctx.world.dirty_tiles)
        self.assertEqual(ctx.db.verify(), [])
        self.assertEqual(ctx.sim.profiler.snapshot()["stages"], {})
        test_save_retry.SaveRetryTests.retry_and_reload(self, ctx, pos)

    def test_diagnostics_reports_percentiles_read_only_and_tolerates_bad_log_rows(self):
        ctx = self.make_save_context()
        ctx.sim.profiler.record("frame.total", 25.0)
        ctx.sim.profiler.record("frame.total", 125.0)
        ctx.sim.clock = SimpleNamespace(minute=ctx.sim.state.clock_minute)
        ctx.sim.player_pos = ctx.entities.get(ctx.player_id, Position).value
        path = Path(ctx.db.path.parent) / "corrupt-diagnostics.jsonl"
        path.write_text('not json\nnull\n[]\n23\n{"kind":"stage","name":"existing",'
                        '"elapsed_ms":200,"slow":true}\n', encoding="utf-8")
        ctx.sim.debug.path = path
        term = SimpleNamespace(size=lambda: (112, 40))
        state = ctx.sim.state.to_dict()
        samples = ctx.sim.profiler.snapshot()
        with patch.object(app, "_view_text") as shown:
            self.assertEqual(app._diagnostics_view(ctx, term), app.UI_BACK)
        text = shown.call_args.args[1]
        self.assertIn("frame.total", text)
        self.assertIn("p95", text.lower())
        self.assertIn("p99", text.lower())
        self.assertIn("existing", text)
        self.assertEqual(ctx.sim.state.to_dict(), state)
        self.assertEqual(ctx.sim.profiler.snapshot(), samples)


if __name__ == "__main__":
    unittest.main()
