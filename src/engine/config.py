"""Typed configuration for the initial inference engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class QueuePolicy(str, Enum):
    REALTIME = "realtime"
    VIDEO_FILE = "video_file"


@dataclass(frozen=True, slots=True)
class QueueConfig:
    capacity: int = 4
    policy: QueuePolicy = QueuePolicy.REALTIME
    wait_timeout_seconds: float = 0.5


@dataclass(frozen=True, slots=True)
class SimulatedDetectorConfig:
    detection_count: int = 1
    class_name: str = "person"
    confidence: float = 0.9
    latency_ms: float = 0.0
    fail: bool = False


@dataclass(frozen=True, slots=True)
class PluginConfig:
    id: str
    enabled: bool = True
    priority: int = 100
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PluginManagerConfig:
    directories: tuple[str, ...] = ("plugins",)
    continue_on_error: bool = True
    plugins: tuple[PluginConfig, ...] = ()


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    name: str = "scheduler"
    settings: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    queue: QueueConfig = field(default_factory=QueueConfig)
    detector: SimulatedDetectorConfig = field(default_factory=SimulatedDetectorConfig)
    plugins: PluginManagerConfig = field(default_factory=PluginManagerConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    synthetic_frame_count: int = 20
