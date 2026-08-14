"""Deterministic camera/biometric adapter for UI development without hardware."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import numpy as np

from src.camera.frame import Frame
from src.engine.alignment import AlignmentQuality
from src.engine.capture_quality import CapturePose, GuidedCaptureResult, GuidedCaptureState
from src.engine.capture_quality.contracts import GuidedQualityMetrics
from src.engine.embedding.contracts import FaceEmbedding
from src.engine.face_quality.contracts import FaceQualityScore, QualityBand
from src.ui.contracts import RuntimeStatusDTO, VisualFrameDTO
from src.camera.camera_types import CameraConfig
from src.ui.runtime_adapter import CameraAdapterError, InferenceAdapterError, ProcessingStep


class MockUIRuntimeAdapter:
    def __init__(self, *, fail_camera_at: set[int] | None = None,
                 fail_inference_at: set[int] | None = None, delay: float = .01,
                 multiple_at: set[int] | None = None,
                 thumbnail_capture_enabled: bool = False) -> None:
        self.fail_camera_at = fail_camera_at or set()
        self.fail_inference_at = fail_inference_at or set()
        self.multiple_at = multiple_at or set()
        self.delay = delay
        self.sequence = 0
        self.closed = False
        self.opened = False
        self.thumbnail_capture_enabled = thumbnail_capture_enabled
        self.thumbnail_capture_active = False

    def open(self) -> bool:
        self.opened = True
        return True

    def new_evaluator(self) -> None:
        pass

    def set_thumbnail_capture(self, enabled: bool) -> None:
        self.thumbnail_capture_active = self.thumbnail_capture_enabled and enabled

    def process(self, requested_pose: CapturePose) -> ProcessingStep:
        time.sleep(self.delay)
        self.sequence += 1
        if self.sequence in self.fail_camera_at:
            raise CameraAdapterError("mock camera failure")
        if self.sequence in self.fail_inference_at:
            raise InferenceAdapterError("mock inference failure")
        width, height = 320, 240
        image = np.zeros((height, width, 3), dtype=np.uint8)
        image[:, :, 1] = 40
        raw = image[:, :, ::-1].copy().tobytes(order="C")
        visual = VisualFrameDTO(width, height, raw, self.sequence)
        count = 2 if self.sequence in self.multiple_at else 1
        metrics = GuidedQualityMetrics(.95, .2, .2, 1, .01, .01, 120, 50, 200,
                                       0, 0, 10, 10, 1)
        score = FaceQualityScore(
            90, 95, 90, 90, 100, 95, 90, 90, 90, 100, QualityBand.EXCELLENT,
            "mock-quality", "1", (), "mock-run", 0,
        )
        if count != 1:
            guided = GuidedCaptureResult(
                GuidedCaptureState.MULTIPLE_FACES, (GuidedCaptureState.MULTIPLE_FACES,),
                False, False, False, False, GuidedQualityMetrics(), requested_pose,
                CapturePose.UNKNOWN, None, "mock-run", datetime.now(timezone.utc), None, score,
            )
        else:
            frame = Frame.create(image, sequence_id=self.sequence, source_name="mock-camera",
                                 monotonic_timestamp=time.monotonic(), connection_id=1)
            vector = np.zeros(512, np.float32)
            vector[0] = 1
            vector[(self.sequence % 4) + 1] = self.sequence * 1e-4
            vector /= np.linalg.norm(vector)
            embedding = FaceEmbedding(
                frame, "mock-run", 0, vector, 512, 1, AlignmentQuality.VALID,
                1, "mock", "w600k_mbf", "buffalo_sc-v0.7", "mock-sha",
            )
            guided = GuidedCaptureResult(
                GuidedCaptureState.ACCEPTED, (GuidedCaptureState.ACCEPTED,), True,
                True, True, True, metrics, requested_pose, requested_pose, 0,
                "mock-run", datetime.now(timezone.utc), embedding, score,
            )
        thumbnail_bytes = None
        if self.thumbnail_capture_active and guided.accepted:
            import cv2
            aligned = np.full((112, 112, 3), 80 + self.sequence % 80, np.uint8)
            encoded, payload = cv2.imencode(".png", aligned)
            if encoded:
                thumbnail_bytes = payload.tobytes()
        return ProcessingStep(visual, count, guided, thumbnail_bytes)

    def status(self) -> RuntimeStatusDTO:
        return RuntimeStatusDTO("connected" if self.opened else "disconnected",
                                "initialized", "loaded", "loaded")

    def switch_camera(self, config: CameraConfig) -> bool:
        self.opened = True
        return True

    def retry_camera(self) -> bool:
        return self.open()

    def close(self) -> None:
        self.closed = True
        self.opened = False
