"""Thread-safe benchmark aggregation without persistence dependencies."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from src.engine.benchmark.contracts import BenchmarkSnapshot, PluginBenchmarkSnapshot


@dataclass(slots=True)
class _PluginStats:
    times: list[float] = field(default_factory=list)
    errors: int = 0


class BenchmarkManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started_at = time.monotonic()
        self._frames_started = 0
        self._latencies: list[float] = []
        self._queue_waits: list[float] = []
        self._frames_dropped = 0
        self._plugins: dict[str, _PluginStats] = {}

    def record_frame_started(self, queue_wait_ms: float = 0.0) -> None:
        with self._lock:
            self._frames_started += 1
            self._queue_waits.append(max(0.0, queue_wait_ms))

    def record_frame_completed(self, latency_ms: float) -> None:
        with self._lock:
            self._latencies.append(max(0.0, latency_ms))

    def record_plugin(self, plugin_id: str, elapsed_ms: float, error: bool = False) -> None:
        with self._lock:
            stats = self._plugins.setdefault(plugin_id, _PluginStats())
            stats.times.append(max(0.0, elapsed_ms))
            stats.errors += int(error)

    def update_frames_dropped(self, count: int) -> None:
        with self._lock:
            self._frames_dropped = max(0, count)

    def snapshot(self) -> BenchmarkSnapshot:
        with self._lock:
            elapsed_ms = (time.monotonic() - self._started_at) * 1_000
            completed = len(self._latencies)
            fps = completed / (elapsed_ms / 1_000) if elapsed_ms > 0 else 0.0
            plugins = tuple(
                PluginBenchmarkSnapshot(
                    plugin_id=plugin_id,
                    invocations=len(stats.times),
                    errors=stats.errors,
                    total_time_ms=sum(stats.times),
                    average_time_ms=sum(stats.times) / len(stats.times) if stats.times else 0.0,
                    minimum_time_ms=min(stats.times, default=0.0),
                    maximum_time_ms=max(stats.times, default=0.0),
                )
                for plugin_id, stats in sorted(self._plugins.items())
            )
            return BenchmarkSnapshot(
                frames_started=self._frames_started,
                frames_completed=completed,
                frames_dropped=self._frames_dropped,
                fps=fps,
                total_time_ms=elapsed_ms,
                average_latency_ms=sum(self._latencies) / completed if completed else 0.0,
                minimum_latency_ms=min(self._latencies, default=0.0),
                maximum_latency_ms=max(self._latencies, default=0.0),
                average_queue_wait_ms=(
                    sum(self._queue_waits) / len(self._queue_waits) if self._queue_waits else 0.0
                ),
                total_queue_wait_ms=sum(self._queue_waits),
                plugins=plugins,
            )

    def reset(self) -> None:
        with self._lock:
            self._started_at = time.monotonic()
            self._frames_started = 0
            self._latencies.clear()
            self._queue_waits.clear()
            self._frames_dropped = 0
            self._plugins.clear()
