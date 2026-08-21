"""Biometric runtime boundary used by the UI worker, never by Tkinter directly."""

from __future__ import annotations

import threading
import uuid
import logging
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

import cv2

from src.camera.camera_manager import CameraManager
from src.camera.camera_types import CameraConfig, CameraType, ReadStatus, ReconnectConfig
from src.camera.source_discovery.selection import classify_camera_source
from src.core.config_manager import PROJECT_ROOT, load_config
from src.engine.alignment import FaceAligner
from src.engine.alignment.contracts import AlignmentStatus
from src.engine.benchmark.manager import BenchmarkManager
from src.engine.capture_quality import (
    CapturePose, FaceCaptureQualityEvaluator, GuidedCapturePolicy, GuidedCaptureResult,
)
from src.engine.contracts.inference_context import InferenceContext
from src.engine.embedding import FaceEmbeddingPlugin
from src.engine.embedding.contracts import FaceEmbedding
from src.engine.face_quality import FaceQualityScorer, load_face_quality_profile
from src.engine.models.manager import ModelManager
from src.engine.plugins.manager import PluginManager
from src.engine.plugins.services import PluginServices
from src.engine.preprocessor import MinimalPreprocessor
from src.engine.runtime.model_runtime import ModelRuntime
from src.engine.runtime.registry import RuntimeRegistry
from src.engine.scheduler.inference_scheduler import InferenceScheduler
from src.ui.contracts import RuntimeStatusDTO, VisualFrameDTO

LOGGER = logging.getLogger(__name__)


def _log_detection_diagnostic(inference, frame, run_id: str) -> None:
    """Log scalar detection provenance without mutating the inference result."""
    if len(inference.detections) == 1:
        return
    values = []
    for index, detection in enumerate(inference.detections):
        box = detection.bounding_box
        x1, y1, x2, y2 = (box.x1, box.y1, box.x2, box.y2)
        if not box.normalized:
            x1, x2 = x1 / frame.width, x2 / frame.width
            y1, y2 = y1 / frame.height, y2 / frame.height
        values.append({
            "index": index,
            "confidence": round(detection.confidence, 6),
            "bbox": (
                round(x1, 6), round(y1, 6), round(x2, 6), round(y2, 6),
            ),
        })
    LOGGER.debug(
        "face_detection_diag frame_id=%d frame_ts=%.6f run_id=%s "
        "detection_count=%d inference_ms=%.3f detections=%s",
        frame.sequence_id, frame.monotonic_timestamp, run_id,
        len(inference.detections), inference.metrics.inference_ms, tuple(values),
    )


def _log_enrollment_quality_diagnostic(
    inference, frame, guided: GuidedCaptureResult, policy: GuidedCapturePolicy,
) -> None:
    """Log existing scalar quality/pose values for relevant one-face rejections."""
    reasons = tuple(reason.value for reason in guided.reasons)
    relevant = {
        "low_detection_confidence", "face_too_small",
        "low_interocular_distance", "pose_not_requested",
    }
    if len(inference.detections) != 1 or not relevant.intersection(reasons):
        return
    detection = inference.detections[0]
    box = detection.bounding_box
    x1, y1, x2, y2 = box.x1, box.y1, box.x2, box.y2
    if not box.normalized:
        x1, x2 = x1 / frame.width, x2 / frame.width
        y1, y2 = y1 / frame.height, y2 / frame.height
    width, height = max(0.0, x2 - x1), max(0.0, y2 - y1)
    metrics = guided.quality_metrics
    score = guided.face_quality_score
    LOGGER.debug(
        "enrollment_quality_diag frame_id=%d step=%s face_count=1 "
        "detection_confidence=%.6f min_detection_confidence=%.6f "
        "bbox_width=%.6f bbox_height=%.6f bbox_area=%.6f "
        "face_ratio=%s min_face_ratio=%.6f interocular_ratio=%s "
        "min_interocular_ratio=%.6f eye_nose_yaw_ratio=%s "
        "mouth_nose_yaw_ratio=%s expected_pose=%s detected_pose=%s "
        "quality_score=%s quality_state=%s reasons=%s",
        frame.sequence_id, guided.requested_pose.value, detection.confidence,
        policy.min_detection_confidence, width, height, width * height,
        _diag_float(metrics.relative_face_size), policy.min_relative_face_size,
        _diag_float(metrics.normalized_interocular_distance),
        policy.min_interocular_distance, _diag_float(metrics.eye_nose_yaw_ratio),
        _diag_float(metrics.mouth_nose_yaw_ratio), guided.requested_pose.value,
        guided.estimated_pose.value, _diag_float(None if score is None else score.total_score),
        "N/D" if score is None else score.quality_band.value, reasons,
    )


def _diag_float(value: float | None) -> str:
    return "N/D" if value is None else f"{value:.6f}"


class CameraAdapterError(RuntimeError):
    pass


class InferenceAdapterError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ProcessingStep:
    visual: VisualFrameDTO
    face_count: int
    guided: GuidedCaptureResult
    aligned_face_bytes: bytes | None = None
    # This is deliberately separate from guided.embedding: the latter is an
    # enrollment sample and is therefore subject to capture cadence/diversity.
    monitoring_embedding: FaceEmbedding | None = None
    frame_id: int | None = None


class UIRuntimeAdapter(Protocol):
    def open(self) -> bool: ...
    def process(self, requested_pose: CapturePose) -> ProcessingStep: ...
    def new_evaluator(self) -> None: ...
    def set_thumbnail_capture(self, enabled: bool) -> None: ...
    def reject_enrollment_candidate(self, guided) -> bool: ...
    def restore_enrollment_candidate(self, guided) -> bool: ...
    def status(self) -> RuntimeStatusDTO: ...
    def switch_camera(self, config: CameraConfig) -> bool: ...
    def retry_camera(self) -> bool: ...
    def close(self) -> None: ...


class RealUIRuntimeAdapter:
    """Owns camera and biometric resources while exposing only safe presentation data."""

    def __init__(
        self, *, source: int | str, policy: GuidedCapturePolicy,
        quality_profile_path: Path, cancel_event: threading.Event,
        thumbnail_capture_enabled: bool = False,
    ) -> None:
        config = load_config()
        face = next(item for item in config.pipeline.plugins.plugins if item.id == "face_detector")
        embedding = next(item for item in config.pipeline.plugins.plugins if item.id == "face_embedding")
        self._detector_models = ModelManager(PROJECT_ROOT)
        plugins = PluginManager(PluginServices(self._detector_models))
        plugins.discover()
        plugins.configure({"face_detector": face.settings}, {"face_detector": face.priority})
        scheduler = InferenceScheduler(plugins.load_enabled(), BenchmarkManager(), False)
        registry = RuntimeRegistry()
        registry.register("scheduler", lambda _settings: scheduler)
        self._detector_alias = str(face.settings["model_alias"])
        self._runtime = ModelRuntime(
            registry, "scheduler", {"device": "auto", "model_aliases": [self._detector_alias]},
            model_manager=self._detector_models,
        )
        self._embedding_models = ModelManager(PROJECT_ROOT)
        self._embedding = FaceEmbeddingPlugin(embedding.settings, self._embedding_models)
        self._cancel_event = cancel_event
        self._camera = CameraManager(
            CameraConfig("local_face_ui", classify_camera_source(source), source,
                         reconnect=ReconnectConfig(True, 3, .5)), cancel_event,
        )
        self._aligner = FaceAligner()
        self._quality = FaceQualityScorer(load_face_quality_profile(quality_profile_path))
        self._policy = policy
        self._evaluator = FaceCaptureQualityEvaluator(policy)
        self._preprocessor = MinimalPreprocessor()
        self._run_id = f"ui-{uuid.uuid4()}"
        self._closed = False
        self._thumbnail_capture_configured = thumbnail_capture_enabled
        self._thumbnail_capture_active = False

    def open(self) -> bool:
        self._runtime.prepare()
        return self._camera.open()

    def switch_camera(self, config: CameraConfig) -> bool:
        """Replace the sole owned camera after releasing it; runtime remains untouched."""
        self._camera.release()
        self._camera = CameraManager(config, self._cancel_event)
        return self._camera.open()

    def retry_camera(self) -> bool:
        return self._camera.open()

    def new_evaluator(self) -> None:
        self._evaluator = FaceCaptureQualityEvaluator(self._policy)

    def set_thumbnail_capture(self, enabled: bool) -> None:
        self._thumbnail_capture_active = self._thumbnail_capture_configured and enabled

    def reject_enrollment_candidate(self, guided) -> bool:
        return self._evaluator.reject_last_accepted(guided)

    def restore_enrollment_candidate(self, guided) -> bool:
        return self._evaluator.restore_accepted(guided)

    def process(self, requested_pose: CapturePose) -> ProcessingStep:
        read = self._camera.read()
        if read.status is not ReadStatus.FRAME or read.frame is None:
            raise CameraAdapterError(f"camera unavailable: {read.status.value}")
        frame = read.frame
        try:
            inference = self._runtime.infer(
                self._preprocessor.prepare(frame), InferenceContext(run_id=self._run_id)
            )
            _log_detection_diagnostic(inference, frame, self._run_id)
            aligned = self._aligner.align_result(inference)
            # The evaluator only asks for an embedding after its enrollment
            # gates have passed.  Cache the result so monitoring can reuse it,
            # or request it once for a biometrically usable aligned face which
            # enrollment rejected for a capture-specific reason.
            monitoring_embedding: FaceEmbedding | None = None
            embedding_attempted = False

            def embedding_for_face(face):
                nonlocal monitoring_embedding, embedding_attempted
                if not embedding_attempted:
                    embedding_attempted = True
                    monitoring_embedding = self._embedding.embed((face,))[0]
                if monitoring_embedding is None:
                    raise ValueError("embedding generation failed")
                return monitoring_embedding

            guided = self._evaluator.evaluate(
                inference.detections, aligned, requested_pose, self._run_id,
                frame.monotonic_timestamp, embedding_for_face,
                timestamp=frame.captured_at,
            )
            if (len(inference.detections) == 1 and len(aligned) == 1
                    and aligned[0].status is AlignmentStatus.ALIGNED
                    and aligned[0].image is not None and not embedding_attempted):
                try:
                    embedding_for_face(aligned[0])
                except Exception:
                    # A monitoring failure is represented on the step; it is
                    # not a reason to tear down the live inference session.
                    monitoring_embedding = None
            aligned_status = aligned[0].status if len(aligned) == 1 else None
            confidence = inference.detections[0].confidence if len(inference.detections) == 1 else None
            score = self._quality.score(
                guided.quality_metrics, requested_pose, guided.estimated_pose,
                guided.reasons, aligned_status, confidence, guided.run_id, guided.face_index,
            )
            guided = replace(guided, face_quality_score=score)
            _log_enrollment_quality_diagnostic(inference, frame, guided, self._policy)
        except Exception as exc:
            raise InferenceAdapterError("biometric inference failed") from exc
        display = frame.image.copy()
        for detection in inference.detections:
            box = detection.bounding_box
            x1, y1, x2, y2 = (
                int(box.x1 * frame.width), int(box.y1 * frame.height),
                int(box.x2 * frame.width), int(box.y2 * frame.height),
            ) if box.normalized else tuple(map(int, (box.x1, box.y1, box.x2, box.y2)))
            cv2.rectangle(display, (x1, y1), (x2, y2), (0, 220, 0), 2)
            cv2.putText(display, f"{detection.confidence:.2f}", (x1, max(18, y1 - 5)),
                        cv2.FONT_HERSHEY_SIMPLEX, .5, (0, 220, 0), 1)
        if guided.face_quality_score is not None:
            cv2.putText(display, f"Score {guided.face_quality_score.total_score:.1f} "
                        f"{guided.face_quality_score.quality_band.value.upper()}",
                        (10, 25), cv2.FONT_HERSHEY_SIMPLEX, .6, (255, 255, 255), 2)
        rgb = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
        visual = VisualFrameDTO(frame.width, frame.height, rgb.tobytes(order="C"), frame.sequence_id)
        thumbnail_bytes = None
        if self._thumbnail_capture_active and guided.visual_quality_passed and len(aligned) == 1:
            encoded, payload = cv2.imencode(".png", aligned[0].image)
            if encoded:
                thumbnail_bytes = payload.tobytes()
        return ProcessingStep(
            visual, len(inference.detections), guided, thumbnail_bytes,
            monitoring_embedding, frame.sequence_id,
        )

    def status(self) -> RuntimeStatusDTO:
        return RuntimeStatusDTO(
            "connected" if self._camera.connected else "disconnected", self._runtime.state.value,
            self._detector_models.state(
                self._detector_models.resolve_alias(self._detector_alias)
            ).value,
            self._embedding_models.state(
                self._embedding_models.resolve_alias(self._embedding.alias)
            ).value,
        )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._camera.cancel()
        self._camera.release()
        self._runtime.release()
        self._detector_models.unload_all()
        self._embedding.release()
        self._embedding_models.unload_all()
