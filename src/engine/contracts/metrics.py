"""Immutable metric snapshots emitted by the inference engine."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InferenceMetrics:
    preprocessing_ms: float = 0.0
    inference_ms: float = 0.0
    detection_count: int = 0


@dataclass(frozen=True, slots=True)
class PipelineMetrics:
    frames_submitted: int = 0
    frames_processed: int = 0
    preprocessing_errors: int = 0
    inference_errors: int = 0
    average_pipeline_latency_ms: float = 0.0
    average_queue_wait_ms: float = 0.0
