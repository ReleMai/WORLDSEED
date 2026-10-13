"""Bounded, opt-in wall-clock diagnostics, independent of simulation state.

Only ``snapshot`` sorts samples or calculates percentiles. Recording keeps a
fixed number of named stages and rolling samples; it performs no file I/O.
Elapsed durations are milliseconds, while an injected clock returns seconds.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from functools import wraps
import math
import os
import sys
import time
from typing import Callable, Mapping, Sequence


class _NoMeasurement:
    """One reusable context for disabled diagnostics, with no timer calls."""

    __slots__ = ()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


_NO_MEASUREMENT = _NoMeasurement()


@dataclass(slots=True)
class _StageSamples:
    samples: deque[float]
    count: int = 0
    lifetime_worst_ms: float = 0.0
    lifetime_over_100ms_count: int = 0


class _Measurement:
    __slots__ = ("_profiler", "_name", "_started")

    def __init__(self, profiler: RuntimeProfiler, name: str):
        self._profiler = profiler
        self._name = name
        self._started: float | None = None

    def __enter__(self):
        try:
            started = float(self._profiler.clock())
            self._started = started if math.isfinite(started) else None
        except Exception:
            # Diagnostics must not prevent the measured work from running.
            self._started = None
        return self

    def __exit__(self, exc_type, exc, traceback):
        if self._started is not None:
            try:
                elapsed_ms = (float(self._profiler.clock()) - self._started) * 1000.0
                self._profiler.record(self._name, elapsed_ms)
            except Exception:
                # Clock failures/backwards jumps must not mask a body exception.
                pass
        return False


def _percentile(ordered: list[float], fraction: float) -> float:
    """Linearly interpolate a percentile over the retained rolling samples."""
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


class RuntimeProfiler:
    """Collect bounded timing samples when explicitly enabled.

    ``count`` and ``lifetime_*`` statistics cover all accepted samples for a
    stage. Other statistics cover at most ``max_samples`` recent durations.
    Stage overflow drops new stage samples and increments ``dropped_stages``;
    already admitted stages continue collecting samples. A profiler belongs to
    one runtime thread and requires no simulation state or random source.

    Explicit invalid inputs raise ``ValueError`` when enabled. Timing contexts
    suppress diagnostic failures while preserving any exception from the body.
    Disabled calls do no validation, timing, sample allocation, or recording.
    """

    def __init__(
        self,
        enabled: bool = False,
        max_samples: int = 1024,
        max_stages: int = 32,
        clock: Callable[[], float] = time.perf_counter,
    ):
        for label, value in (("max_samples", max_samples), ("max_stages", max_stages)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{label} must be a positive integer")
        if not callable(clock):
            raise ValueError("clock must be callable")
        self.enabled = bool(enabled)
        self.max_samples = max_samples
        self.max_stages = max_stages
        self.clock = clock
        self._stages: dict[str, _StageSamples] = {}
        self._dropped_stages = 0

    @staticmethod
    def _validate_name(name: str) -> None:
        if not isinstance(name, str) or not name.strip() or len(name) > 128:
            raise ValueError("stage name must be a nonempty string of at most 128 characters")

    def measure(self, name: str):
        """Measure a block; disabled profilers return the same no-op context."""
        if not self.enabled:
            return _NO_MEASUREMENT
        self._validate_name(name)
        return _Measurement(self, name)

    def record(self, name: str, elapsed_ms: float) -> None:
        """Record one finite nonnegative duration, subject to fixed bounds."""
        if not self.enabled:
            return
        self._validate_name(name)
        try:
            elapsed = float(elapsed_ms)
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("elapsed_ms must be finite and nonnegative") from exc
        if isinstance(elapsed_ms, (str, bytes, bool)) or not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError("elapsed_ms must be finite and nonnegative")
        stage = self._stages.get(name)
        if stage is None:
            if len(self._stages) >= self.max_stages:
                self._dropped_stages += 1
                return
            stage = _StageSamples(deque(maxlen=self.max_samples))
            self._stages[name] = stage
        stage.samples.append(elapsed)
        stage.count += 1
        stage.lifetime_worst_ms = max(stage.lifetime_worst_ms, elapsed)
        if elapsed > 100.0:
            stage.lifetime_over_100ms_count += 1

    def snapshot(self) -> dict:
        """Return a detached, JSON-ready report without modifying samples."""
        stages = {}
        for name, stage in self._stages.items():
            ordered = sorted(stage.samples)
            stages[name] = {
                "count": stage.count,
                "window_count": len(ordered),
                "p50_ms": _percentile(ordered, 0.50),
                "p95_ms": _percentile(ordered, 0.95),
                "p99_ms": _percentile(ordered, 0.99),
                "mean_ms": math.fsum(value / len(ordered) for value in ordered),
                "worst_ms": ordered[-1],
                "lifetime_worst_ms": stage.lifetime_worst_ms,
                "over_100ms_count": sum(value > 100.0 for value in ordered),
                "lifetime_over_100ms_count": stage.lifetime_over_100ms_count,
            }
        return {
            "enabled": self.enabled,
            "max_samples": self.max_samples,
            "max_stages": self.max_stages,
            "dropped_stages": self._dropped_stages,
            "stages": stages,
        }


def runtime_profile_enabled(
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Read the explicit runtime flag/environment opt-in without changing them."""
    args = sys.argv if argv is None else argv
    environment = os.environ if environ is None else environ
    return "--profile-runtime" in args or environment.get("WORLDSEED_PROFILE") == "1"


def measure_if_enabled(profiler: RuntimeProfiler | None, name: str):
    """Use a runtime profiler when present, otherwise reuse the no-op context."""
    if profiler is None or not profiler.enabled:
        return _NO_MEASUREMENT
    return profiler.measure(name)


def profiled(stage: str, attribute: str = "profiler"):
    """Time an instance method without requiring lightweight fixtures to profile.

    Missing or disabled profilers directly call the wrapped method. The
    decorator preserves the method's name/docstring and exception behavior.
    """
    RuntimeProfiler._validate_name(stage)
    if not isinstance(attribute, str) or not attribute:
        raise ValueError("profiler attribute must be a nonempty string")

    def decorate(method):
        @wraps(method)
        def measured(self, *args, **kwargs):
            profiler = getattr(self, attribute, None)
            if profiler is None or not profiler.enabled:
                return method(self, *args, **kwargs)
            with profiler.measure(stage):
                return method(self, *args, **kwargs)

        return measured

    return decorate
