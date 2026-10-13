"""Pure timing diagnostics: bounds, exact statistics and exception isolation."""
import json
import unittest
from unittest.mock import Mock

from worldseed.profiling import (
    RuntimeProfiler, measure_if_enabled, profiled, runtime_profile_enabled,
)


class RuntimeProfilingTests(unittest.TestCase):
    def test_disabled_context_is_reused_without_clock_or_samples(self):
        clock = Mock(side_effect=AssertionError("disabled timer called"))
        profiler = RuntimeProfiler(clock=clock)
        context = profiler.measure("simulation")
        for _ in range(100):
            self.assertIs(profiler.measure("frame"), context)
            with context:
                profiler.record("frame", 1000.0)
        clock.assert_not_called()
        self.assertEqual(profiler.snapshot()["stages"], {})
        self.assertEqual(profiler._stages, {})

    def test_context_records_clock_seconds_as_milliseconds(self):
        clock = Mock(side_effect=[10.0, 10.025, 11.0, 11.125])
        profiler = RuntimeProfiler(enabled=True, clock=clock)
        with profiler.measure("simulation"):
            pass
        with profiler.measure("simulation"):
            pass
        stage = profiler.snapshot()["stages"]["simulation"]
        self.assertEqual(stage["count"], 2)
        self.assertAlmostEqual(stage["p50_ms"], 75.0)
        self.assertAlmostEqual(stage["worst_ms"], 125.0)
        self.assertEqual(stage["over_100ms_count"], 1)
        self.assertEqual(clock.call_count, 4)

    def test_percentiles_interpolate_and_report_stalls_strictly_above_100(self):
        profiler = RuntimeProfiler(enabled=True)
        for elapsed in (0.0, 100.0, 200.0, 300.0, 400.0):
            profiler.record("frame", elapsed)
        stage = profiler.snapshot()["stages"]["frame"]
        self.assertEqual(stage, {
            "count": 5,
            "window_count": 5,
            "p50_ms": 200.0,
            "p95_ms": 380.0,
            "p99_ms": 396.0,
            "mean_ms": 200.0,
            "worst_ms": 400.0,
            "lifetime_worst_ms": 400.0,
            "over_100ms_count": 3,
            "lifetime_over_100ms_count": 3,
        })

    def test_rolling_window_preserves_lifetime_statistics(self):
        profiler = RuntimeProfiler(enabled=True, max_samples=3)
        for elapsed in (500.0, 200.0, 5.0, 10.0, 15.0):
            profiler.record("frame", elapsed)
        stage = profiler.snapshot()["stages"]["frame"]
        self.assertEqual(stage["count"], 5)
        self.assertEqual(stage["window_count"], 3)
        self.assertEqual(stage["p50_ms"], 10.0)
        self.assertEqual(stage["mean_ms"], 10.0)
        self.assertEqual(stage["worst_ms"], 15.0)
        self.assertEqual(stage["lifetime_worst_ms"], 500.0)
        self.assertEqual(stage["over_100ms_count"], 0)
        self.assertEqual(stage["lifetime_over_100ms_count"], 2)

    def test_sample_and_stage_retention_are_bounded_after_many_samples(self):
        profiler = RuntimeProfiler(enabled=True, max_samples=7, max_stages=2)
        for _ in range(1000):
            profiler.record("frame", 1.0)
            profiler.record("ui", 2.0)
        for index in range(1000):
            profiler.record(f"overflow-{index}", 3.0)
        profiler.record("frame", 9.0)
        report = profiler.snapshot()
        self.assertEqual(set(report["stages"]), {"frame", "ui"})
        self.assertEqual(report["dropped_stages"], 1000)
        self.assertEqual(report["stages"]["frame"]["count"], 1001)
        for stage in profiler._stages.values():
            self.assertEqual(len(stage.samples), 7)
            self.assertEqual(stage.samples.maxlen, 7)
        self.assertEqual(report["stages"]["frame"]["worst_ms"], 9.0)

    def test_snapshot_is_detached_json_ready_and_observational(self):
        profiler = RuntimeProfiler(enabled=True, max_samples=2)
        profiler.record("frame", 4.0)
        before = tuple(profiler._stages["frame"].samples)
        report = profiler.snapshot()
        self.assertEqual(json.loads(json.dumps(report)), report)
        report["stages"]["frame"]["count"] = -1
        report["stages"].clear()
        self.assertEqual(profiler.snapshot()["stages"]["frame"]["count"], 1)
        self.assertEqual(tuple(profiler._stages["frame"].samples), before)

    def test_body_exception_is_preserved_and_duration_is_recorded(self):
        profiler = RuntimeProfiler(enabled=True, clock=Mock(side_effect=[2.0, 2.01]))
        problem = RuntimeError("gameplay failure")
        with self.assertRaises(RuntimeError) as caught:
            with profiler.measure("simulation"):
                raise problem
        self.assertIs(caught.exception, problem)
        self.assertEqual(profiler.snapshot()["stages"]["simulation"]["count"], 1)

    def test_disabled_context_preserves_body_exception(self):
        problem = RuntimeError("gameplay failure")
        with self.assertRaises(RuntimeError) as caught:
            with RuntimeProfiler().measure("simulation"):
                raise problem
        self.assertIs(caught.exception, problem)

    def test_optional_helper_uses_no_op_for_missing_and_disabled_profilers(self):
        clock = Mock(side_effect=AssertionError("disabled timer called"))
        disabled = RuntimeProfiler(clock=clock)
        self.assertIs(measure_if_enabled(None, "frame"), disabled.measure("frame"))
        self.assertIs(measure_if_enabled(disabled, "frame"), disabled.measure("frame"))
        with measure_if_enabled(None, "frame"):
            pass
        with measure_if_enabled(disabled, "frame"):
            pass
        clock.assert_not_called()
        enabled = RuntimeProfiler(enabled=True, clock=Mock(side_effect=[0.0, 0.005]))
        with measure_if_enabled(enabled, "frame"):
            pass
        self.assertEqual(enabled.snapshot()["stages"]["frame"]["worst_ms"], 5.0)

    def test_decorator_missing_or_disabled_profiler_directly_calls_method(self):
        class Example:
            @profiled("command")
            def command(self, value, *, increment=0):
                """Original documentation."""
                return value + increment

        instance = Example()
        self.assertEqual(instance.command(4, increment=3), 7)
        self.assertEqual(instance.command.__name__, "command")
        self.assertEqual(instance.command.__doc__, "Original documentation.")
        instance.profiler = RuntimeProfiler(clock=Mock(side_effect=AssertionError("timer")))
        instance.profiler.measure = Mock(side_effect=AssertionError("measure"))
        self.assertEqual(instance.command(4, increment=3), 7)
        instance.profiler.clock.assert_not_called()
        instance.profiler.measure.assert_not_called()

    def test_decorator_enabled_preserves_return_exception_and_custom_attribute(self):
        class Example:
            @profiled("command", attribute="timings")
            def command(self, failure=None):
                if failure is not None:
                    raise failure
                return "command result"

        instance = Example()
        instance.timings = RuntimeProfiler(enabled=True,
                                          clock=Mock(side_effect=[0.0, 0.005, 1.0, 1.007]))
        self.assertEqual(instance.command(), "command result")
        problem = RuntimeError("command failed")
        with self.assertRaises(RuntimeError) as caught:
            instance.command(problem)
        self.assertIs(caught.exception, problem)
        self.assertEqual(instance.timings.snapshot()["stages"]["command"]["count"], 2)

    def test_decorator_rejects_invalid_static_configuration(self):
        with self.assertRaises(ValueError):
            profiled("")
        with self.assertRaises(ValueError):
            profiled("frame", attribute="")

    def test_clock_failure_cannot_block_work_or_mask_body_exception(self):
        for times in ([RuntimeError("clock failed")], [1.0, RuntimeError("clock failed")],
                      [float("nan")], [2.0, 1.0], [1.0, float("inf")]):
            with self.subTest(times=times):
                profiler = RuntimeProfiler(enabled=True, clock=Mock(side_effect=times))
                reached = []
                problem = RuntimeError("gameplay failure")
                with self.assertRaises(RuntimeError) as caught:
                    with profiler.measure("frame"):
                        reached.append(True)
                        raise problem
                self.assertEqual(reached, [True])
                self.assertIs(caught.exception, problem)
                self.assertEqual(profiler.snapshot()["stages"], {})

    def test_invalid_enabled_record_inputs_leave_samples_unchanged(self):
        profiler = RuntimeProfiler(enabled=True)
        for name in (None, 1, "", "   ", "a" * 129):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    profiler.record(name, 1.0)
                with self.assertRaises(ValueError):
                    profiler.measure(name)
        for elapsed in (-1, float("nan"), float("inf"), -float("inf"), None, "4", True):
            with self.subTest(elapsed=elapsed):
                with self.assertRaises(ValueError):
                    profiler.record("frame", elapsed)
        self.assertEqual(profiler.snapshot()["stages"], {})

    def test_invalid_constructor_bounds_and_clock(self):
        for label in ("max_samples", "max_stages"):
            for value in (0, -1, 1.5, True, "10", None):
                with self.subTest(label=label, value=value):
                    with self.assertRaises(ValueError):
                        RuntimeProfiler(**{label: value})
        with self.assertRaises(ValueError):
            RuntimeProfiler(clock=None)

    def test_very_large_finite_samples_remain_json_ready(self):
        profiler = RuntimeProfiler(enabled=True)
        profiler.record("frame", 1e308)
        profiler.record("frame", 1e308)
        report = profiler.snapshot()
        self.assertEqual(report["stages"]["frame"]["mean_ms"], 1e308)
        json.dumps(report, allow_nan=False)

    def test_runtime_opt_in_is_explicit_and_does_not_change_inputs(self):
        args = ["worldseed", "--profile-runtime", "--terminal"]
        environment = {"WORLDSEED_PROFILE": "0"}
        self.assertTrue(runtime_profile_enabled(args, environment))
        self.assertEqual(args, ["worldseed", "--profile-runtime", "--terminal"])
        self.assertEqual(environment, {"WORLDSEED_PROFILE": "0"})
        self.assertTrue(runtime_profile_enabled([], {"WORLDSEED_PROFILE": "1"}))
        for value in ("0", "true", "yes", "", " 1 "):
            with self.subTest(value=value):
                self.assertFalse(runtime_profile_enabled([], {"WORLDSEED_PROFILE": value}))
        self.assertFalse(runtime_profile_enabled(["--profile-runtime=false"], {}))
        self.assertFalse(runtime_profile_enabled([], {}))


if __name__ == "__main__":
    unittest.main()
