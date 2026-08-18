"""Controlled, operator-supervised capture of one temporary identity per session."""

from __future__ import annotations

import argparse
import json
import signal
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from src.camera.camera_manager import CameraManager
from src.camera.camera_types import CameraConfig, CameraType, ReadStatus, ReconnectConfig
from src.core.config_manager import PROJECT_ROOT, load_config
from src.engine.alignment import AlignmentQuality, FaceAligner
from src.engine.benchmark.manager import BenchmarkManager
from src.engine.calibration.contracts import (
    CalibrationDistance, CalibrationIllumination, CalibrationPose, CalibrationSample,
    CalibrationSampleMetadata, CalibrationSampleType,
)
from src.engine.calibration.dataset import CalibrationDatasetStore, require_capture_consent
from src.engine.contracts.inference_context import InferenceContext
from src.engine.embedding import FaceEmbeddingPlugin
from src.engine.embedding.contracts import FaceEmbedding
from src.engine.models.manager import ModelManager
from src.engine.plugins.manager import PluginManager
from src.engine.plugins.services import PluginServices
from src.engine.preprocessor import MinimalPreprocessor
from src.engine.runtime.model_runtime import ModelRuntime
from src.engine.runtime.registry import RuntimeRegistry
from src.engine.scheduler.inference_scheduler import InferenceScheduler


@dataclass(frozen=True, slots=True)
class CapturePolicy:
    min_samples: int
    target_samples: int
    min_capture_interval: float
    max_near_duplicate_similarity: float
    allow_low_quality: bool = False

    def __post_init__(self) -> None:
        if self.min_samples <= 0 or self.target_samples < self.min_samples:
            raise ValueError("capture sample limits are invalid")
        if self.min_capture_interval < 0:
            raise ValueError("capture interval cannot be negative")
        if not -1 <= self.max_near_duplicate_similarity <= 1:
            raise ValueError("near-duplicate similarity must be between -1 and 1")


class CaptureSampleSelector:
    """Apply quality, temporal separation and near-duplicate filters."""

    def __init__(self, policy: CapturePolicy) -> None:
        self.policy = policy
        self.accepted: list[FaceEmbedding] = []
        self._last_captured_at: float | None = None

    def consider(self, embedding: FaceEmbedding, captured_monotonic: float) -> bool:
        if (embedding.alignment_quality is AlignmentQuality.LOW_QUALITY and
                not self.policy.allow_low_quality):
            return False
        if (self._last_captured_at is not None and
                captured_monotonic - self._last_captured_at < self.policy.min_capture_interval):
            return False
        if any(_cosine(embedding.embedding, item.embedding) >=
               self.policy.max_near_duplicate_similarity for item in self.accepted):
            return False
        self.accepted.append(embedding)
        self._last_captured_at = captured_monotonic
        return True


def run_capture(args: argparse.Namespace) -> dict[str, object]:
    """Run real capture only when explicitly invoked by an operator."""
    require_capture_consent(
        save_data=args.save_data, save_images=args.save_images,
        consent_confirmed=args.consent_confirmed,
    )
    sample_type = CalibrationSampleType(args.sample_type)
    expected_identity = args.expected_identity
    if sample_type is CalibrationSampleType.GENUINE and not expected_identity:
        raise ValueError("--expected-identity is required for GENUINE capture")
    if sample_type is CalibrationSampleType.IMPOSTOR and expected_identity is not None:
        raise ValueError("--expected-identity is forbidden for IMPOSTOR capture")
    expected_confirmation = f"CONFIRM {sample_type.value}"
    if args.confirm_sample_type != expected_confirmation:
        raise ValueError(f"explicit confirmation required: {expected_confirmation}")
    print(f"TIPO DE MUESTRA: {sample_type.value}")
    gallery_manifest = json.loads(args.gallery_manifest.read_text(encoding="utf-8"))
    registered_ids = {str(item["person_id"])
                      for item in gallery_manifest.get("identities", [])}
    gallery_sources = {str(item["source_reference"])
                       for item in gallery_manifest.get("templates", [])
                       if item.get("source_reference")}
    if sample_type is CalibrationSampleType.GENUINE and expected_identity not in registered_ids:
        raise ValueError("--expected-identity is not registered in the reference gallery")
    if sample_type is CalibrationSampleType.IMPOSTOR and args.temporary_id in registered_ids:
        raise ValueError("impostor temporary id cannot be a registered identity")
    policy = CapturePolicy(
        args.min_samples, args.target_samples, args.min_capture_interval,
        args.max_near_duplicate_similarity, args.allow_low_quality,
    )
    selector = CaptureSampleSelector(policy)
    session_id = args.session_id or f"calibration-{uuid.uuid4()}"
    if session_id in gallery_sources or str(args.source) in gallery_sources:
        raise ValueError("evaluation run/source_reference overlaps enrollment")
    condition_id = args.condition_id or (
        f"{args.illumination}-{args.distance}-{args.pose}"
    )
    cancelled = threading.Event()
    previous = signal.signal(signal.SIGINT, lambda _sig, _frame: cancelled.set())
    camera = CameraManager(
        CameraConfig(
            "face_calibration", CameraType.USB, args.source,
            reconnect=ReconnectConfig(True, 3, 0.5),
        ), cancelled,
    )
    config = load_config()
    face_config = next(item for item in config.pipeline.plugins.plugins if item.id == "face_detector")
    embedding_config = next(
        item for item in config.pipeline.plugins.plugins if item.id == "face_embedding"
    )
    detection_models = ModelManager(PROJECT_ROOT)
    manager = PluginManager(PluginServices(detection_models))
    manager.discover()
    manager.configure({"face_detector": face_config.settings}, {"face_detector": 10})
    scheduler = InferenceScheduler(manager.load_enabled(), BenchmarkManager(), continue_on_error=False)
    registry = RuntimeRegistry()
    registry.register("scheduler", lambda _settings: scheduler)
    alias = str(face_config.settings["model_alias"])
    runtime = ModelRuntime(registry, "scheduler", {"device": "auto", "model_aliases": [alias]},
                           model_manager=detection_models)
    embedding_models = ModelManager(PROJECT_ROOT)
    embedding_plugin = FaceEmbeddingPlugin(embedding_config.settings, embedding_models)
    aligner = FaceAligner()
    samples: list[CalibrationSample] = []
    images: list[tuple[int, np.ndarray]] = []
    started = time.monotonic()
    try:
        runtime.prepare()
        if not camera.open():
            raise RuntimeError("camera source could not be opened")
        while not cancelled.is_set() and len(samples) < policy.target_samples:
            if args.max_duration is not None and time.monotonic() - started >= args.max_duration:
                break
            read = camera.read()
            if read.status is not ReadStatus.FRAME or read.frame is None:
                break
            frame = read.frame
            result = runtime.infer(
                MinimalPreprocessor().prepare(frame), InferenceContext(run_id=session_id)
            )
            aligned = aligner.align_result(result)
            # Exactly one face is accepted. There is no tracking or identity verification.
            processable = tuple(item for item in aligned if item.image is not None)
            if len(processable) == 1:
                embedding = embedding_plugin.embed(processable)[0]
                if selector.consider(embedding, frame.monotonic_timestamp):
                    metadata = CalibrationSampleMetadata(
                        session_id, args.temporary_id, frame.captured_at,
                        str(args.source), (frame.width, frame.height),
                        embedding.alignment_quality, embedding.model, embedding.version,
                        embedding.weights_sha256,
                        sample_type=sample_type, expected_identity=expected_identity,
                        calibration_session_id=session_id,
                        evaluation_sample_id=str(uuid.uuid4()), condition_id=condition_id,
                        illumination=CalibrationIllumination(args.illumination),
                        distance=CalibrationDistance(args.distance),
                        pose=CalibrationPose(args.pose),
                    )
                    samples.append(CalibrationSample(embedding.embedding, metadata))
                    if args.save_images:
                        images.append((embedding.face_index, processable[0].image.copy()))
            if not args.no_display:
                preview = frame.image.copy()
                cv2.putText(preview, f"accepted: {len(samples)}/{policy.target_samples}",
                            (10, 25), cv2.FONT_HERSHEY_SIMPLEX, .6, (0, 255, 0), 2)
                cv2.imshow("FastVisionAI Calibration Capture", preview)
                if cv2.waitKey(1) & 0xFF == 27:
                    cancelled.set()
    finally:
        camera.release()
        runtime.release()
        detection_models.unload_all()
        embedding_plugin.release()
        embedding_models.unload_all()
        cv2.destroyAllWindows()
        signal.signal(signal.SIGINT, previous)
    if len(samples) < policy.min_samples:
        raise RuntimeError("session ended before the required minimum sample count")
    output = PROJECT_ROOT / "data" / "calibration" / session_id
    if args.save_data:
        CalibrationDatasetStore(enabled=True).save(
            {args.temporary_id: tuple(samples)}, output / "manifest.json", output / "embeddings.npz",
            consent_confirmed=args.consent_confirmed, overwrite=args.overwrite,
        )
    if args.save_images:
        image_dir = output / "images"
        if image_dir.exists() and not args.overwrite:
            raise RuntimeError("calibration image target already exists")
        image_dir.mkdir(parents=True, exist_ok=True)
        for index, image in enumerate(images):
            cv2.imwrite(str(image_dir / f"aligned_{index:04d}.jpg"), image[1])
    return {
        "session_id": session_id, "temporary_identity_id": args.temporary_id,
        "sample_type": sample_type.value, "expected_identity": expected_identity,
        "condition_id": condition_id,
        "samples_accepted": len(samples), "operator_same_person_responsibility": True,
        "data_saved": bool(args.save_data), "images_saved": bool(args.save_images),
    }


def build_parser(sample_type: CalibrationSampleType | None = None) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operator-supervised face calibration capture")
    parser.add_argument("--temporary-id", required=True)
    parser.add_argument("--gallery-manifest", type=Path, required=True)
    if sample_type is None:
        parser.add_argument("--sample-type", choices=[item.value for item in CalibrationSampleType],
                            required=True)
    else:
        parser.set_defaults(sample_type=sample_type.value)
    parser.add_argument("--expected-identity")
    parser.add_argument("--confirm-sample-type", required=True,
                        help='Must be exactly "CONFIRM GENUINE" or "CONFIRM IMPOSTOR"')
    parser.add_argument("--condition-id")
    parser.add_argument("--illumination", choices=[item.value for item in CalibrationIllumination],
                        required=True)
    parser.add_argument("--distance", choices=[item.value for item in CalibrationDistance],
                        required=True)
    parser.add_argument("--pose", choices=[item.value for item in CalibrationPose], required=True)
    parser.add_argument("--session-id")
    parser.add_argument("--source", type=int, default=0)
    parser.add_argument("--min-samples", type=int, default=5)
    parser.add_argument("--target-samples", type=int, default=10)
    parser.add_argument("--min-capture-interval", type=float, default=1.0)
    parser.add_argument("--max-near-duplicate-similarity", type=float, required=True)
    parser.add_argument("--allow-low-quality", action="store_true")
    parser.add_argument("--max-duration", type=float)
    parser.add_argument("--no-display", action="store_true")
    parser.add_argument("--save-data", action="store_true")
    parser.add_argument("--save-images", action="store_true")
    parser.add_argument("--consent-confirmed", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser


def _cosine(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.clip(np.dot(left, right), -1.0, 1.0))


def main() -> int:
    import json
    print(json.dumps(run_capture(build_parser().parse_args()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
