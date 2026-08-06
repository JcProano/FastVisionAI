"""Immutable benchmark snapshots."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PluginBenchmarkSnapshot:
    plugin_id: str
    invocations: int
    errors: int
    total_time_ms: float
    average_time_ms: float
    minimum_time_ms: float
    maximum_time_ms: float


@dataclass(frozen=True, slots=True)
class BenchmarkSnapshot:
    frames_started: int
    frames_completed: int
    frames_dropped: int
    fps: float
    total_time_ms: float
    average_latency_ms: float
    minimum_latency_ms: float
    maximum_latency_ms: float
    average_queue_wait_ms: float
    total_queue_wait_ms: float
    plugins: tuple[PluginBenchmarkSnapshot, ...]
