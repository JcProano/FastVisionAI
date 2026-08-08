"""Scalar-only DTOs for the local dashboard presentation boundary."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class DashboardMetricState(str, Enum):
    OK = "OK"
    WARNING = "WARNING"
    REJECTED = "REJECTED"
    NOT_AVAILABLE = "NOT_AVAILABLE"


@dataclass(frozen=True, slots=True)
class DashboardSystemDTO:
    camera_state: str = "N/D"
    runtime_state: str = "N/D"
    yunet_state: str = "N/D"
    arcface_state: str = "N/D"
    recognition_state: str = "NOT_EVALUATED"


@dataclass(frozen=True, slots=True)
class DashboardMetricsDTO:
    frames_received: int = 0
    frames_processed: int = 0
    visual_frames_dropped: int = 0
    faces_detected_total: int = 0
    faces_detected_current: int = 0
    embeddings_generated: int = 0
    effective_capture_fps: float | None = None
    effective_processing_fps: float | None = None
    uptime_seconds: float = 0.0
    inference_latency_ms: float | None = None


@dataclass(frozen=True, slots=True)
class DashboardRecognitionDTO:
    message: str = "Sin candidatos registrados"
    display_name: str | None = None
    similarity: float | None = None
    state: str = "NO_GALLERY"
    decision: str = "NOT_EVALUATED"
    person_id: str | None = None


@dataclass(frozen=True, slots=True)
class DashboardGalleryDTO:
    identities: int = 0
    templates: int = 0
    state: str = "idle"


@dataclass(frozen=True, slots=True)
class DashboardQualityMetricDTO:
    name: str
    value: float | str | None
    state: DashboardMetricState


@dataclass(frozen=True, slots=True)
class DashboardQualityDTO:
    score: float | None = None
    band: str | None = None
    metrics: tuple[DashboardQualityMetricDTO, ...] = ()


@dataclass(frozen=True, slots=True)
class DashboardEventDTO:
    timestamp: datetime
    event_type: str
    display_name: str | None
    similarity: float | None
    quality_score: float | None
    message: str


@dataclass(frozen=True, slots=True)
class DashboardConfigurationDTO:
    source: str
    resolution: str
    mirrored_source: bool
    guided_profile: str
    quality_profile: str
    target_samples: int
    persistence_enabled_by_default: bool
    load_on_startup: bool
    recognition_policy: str
    recognition_policy_version: str
    automatic_decision_enabled: bool
    match_threshold: str = "N/D"
    ambiguity_margin: str = "N/D"
