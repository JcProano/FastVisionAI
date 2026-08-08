"""Live guided face capture validation; no recognition or identity decisions."""

from __future__ import annotations

import argparse
import json
import signal
import threading
import time
import uuid
from collections import Counter
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Callable, Protocol

import cv2

from src.camera.camera_manager import CameraManager
from src.camera.camera_types import CameraConfig, CameraType, ReadStatus, ReconnectConfig
from src.camera.frame import Frame
from src.core.config_manager import PROJECT_ROOT, load_config
from src.engine.alignment import FaceAligner
from src.engine.alignment.contracts import AlignedFace
from src.engine.benchmark.manager import BenchmarkManager
from src.engine.calibration.contracts import CalibrationSample, CalibrationSampleMetadata
from src.engine.calibration.dataset import CalibrationDatasetStore, require_capture_consent
from src.engine.capture_quality import (
    FaceCaptureQualityEvaluator, GuidedCapturePlan, GuidedCapturePolicy,
    GuidedCaptureResult, GuidedCaptureState, GuidedProfileDiagnosticCollector,
)
from src.engine.contracts.detection import InferenceResult
from src.engine.contracts.inference_context import InferenceContext
from src.engine.embedding import FaceEmbeddingPlugin
from src.engine.embedding.contracts import FaceEmbedding
from src.engine.face_quality import FaceQualityScorer, load_face_quality_profile
from src.engine.face_quality.contracts import FaceQualityScore
from src.engine.models.manager import ModelManager
from src.engine.plugins.manager import PluginManager
from src.engine.plugins.services import PluginServices
from src.engine.preprocessor import MinimalPreprocessor
from src.engine.runtime.model_runtime import ModelRuntime
from src.engine.runtime.registry import RuntimeRegistry
from src.engine.scheduler.inference_scheduler import InferenceScheduler


@dataclass(frozen=True, slots=True)
class GuidedProfile:
    profile_name: str
    profile_version: str
    policy: GuidedCapturePolicy


@dataclass(frozen=True, slots=True)
class GuidedOptions:
    target_samples: int | None
    max_duration: float | None
    no_display: bool


@dataclass(frozen=True, slots=True)
class AcceptedCapture:
    sample_index: int
    result: GuidedCaptureResult
    aligned_face: AlignedFace


@dataclass(frozen=True, slots=True)
class GuidedCaptureSummary:
    profile_name: str
    profile_version: str
    frames_evaluated: int
    visually_valid_candidates: int
    visual_rejections: int
    temporal_rejections: int
    embeddings_calculated: int
    embedding_failures: int
    near_duplicate_rejections: int
    samples_accepted: int
    rejections_by_cause: dict[str, int]
    average_quality_score: float
    minimum_quality_score: float
    maximum_quality_score: float
    accepted_sample_scores: tuple[dict[str, object], ...]
    quality_profile_name: str
    quality_profile_version: str
    poses_covered: tuple[str, ...]
    duration_seconds: float
    data_saved: bool
    images_saved: bool
    camera_state: str
    detector_runtime_state: str
    detector_model_state: str
    embedding_model_state: str


class CameraLike(Protocol):
    def open(self) -> bool: ...
    def read(self) -> Any: ...
    def release(self) -> None: ...


InferenceFunction = Callable[[Frame, str], InferenceResult]
AlignmentFunction = Callable[[InferenceResult], tuple[AlignedFace, ...]]
EmbeddingFunction = Callable[[AlignedFace], FaceEmbedding]
ResultObserver = Callable[[GuidedCaptureResult, int], None]


def load_guided_profile(path: Path) -> GuidedProfile:
    try:
        root = json.loads(path.read_text(encoding="utf-8"))
        name = str(root["profile_name"])
        version = str(root["profile_version"])
        limits = root["limits"]
        if not name or not version or not isinstance(limits, dict):
            raise ValueError
        return GuidedProfile(name, version, GuidedCapturePolicy(**limits))
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("invalid guided capture profile") from exc


def validate_runtime_options(options: GuidedOptions) -> None:
    if options.target_samples is None or options.target_samples <= 0:
        raise ValueError("--target-samples must be a finite positive integer")
    if options.max_duration is not None and options.max_duration <= 0:
        raise ValueError("--max-duration must be positive")
    if options.no_display and options.max_duration is None and options.target_samples <= 0:
        raise ValueError("--no-display requires --max-duration or a finite --target-samples")


def validate_persistence_options(*, save_data: bool, save_images: bool,
                                 consent_confirmed: bool) -> None:
    if save_images and not save_data:
        raise ValueError("--save-images requires --save-data")
    require_capture_consent(save_data=save_data, save_images=save_images,
                            consent_confirmed=consent_confirmed)


def run_guided_loop(
    camera: CameraLike,
    infer: InferenceFunction,
    align: AlignmentFunction,
    embed: EmbeddingFunction,
    evaluator: FaceCaptureQualityEvaluator,
    plan: GuidedCapturePlan,
    options: GuidedOptions,
    cancelled: threading.Event,
    run_id: str,
    quality_scorer: FaceQualityScorer | None = None,
    result_observer: ResultObserver | None = None,
) -> tuple[list[AcceptedCapture], Counter[str], float, str]:
    validate_runtime_options(options)
    accepted: list[AcceptedCapture] = []
    rejected: Counter[str] = Counter()
    quality_total = 0.0
    started = time.monotonic()
    camera_state = "disconnected"
    if not camera.open():
        return accepted, rejected, 0.0, camera_state
    camera_state = "connected"
    while not cancelled.is_set() and not plan.completed:
        if options.max_duration is not None and time.monotonic() - started >= options.max_duration:
            break
        read = camera.read()
        if read.status is not ReadStatus.FRAME or read.frame is None:
            camera_state = read.status.value
            break
        frame = read.frame
        inference = infer(frame, run_id)
        try:
            aligned = align(inference)
        except Exception:
            aligned = ()
        current_step = plan.current
        result = evaluator.evaluate(
            inference.detections, aligned, current_step.requested_pose, run_id,
            frame.monotonic_timestamp, embed, timestamp=frame.captured_at,
        )
        if quality_scorer is not None:
            aligned_status = aligned[0].status if len(aligned) == 1 else None
            confidence = inference.detections[0].confidence if len(inference.detections) == 1 else None
            score = quality_scorer.score(
                result.quality_metrics, result.requested_pose, result.estimated_pose,
                result.reasons, aligned_status, confidence, result.run_id, result.face_index,
            )
            # Scoring is informational: all original policy fields remain unchanged.
            result = replace(result, face_quality_score=score)
        if result_observer is not None:
            result_observer(result, len(inference.detections))
        if result.accepted:
            aligned_face = next(item for item in aligned if item.face_index == result.face_index)
            accepted.append(AcceptedCapture(len(accepted), result, aligned_face))
            quality_total += (
                result.face_quality_score.total_score if result.face_quality_score is not None
                else result.quality_metrics.quality_score * 100.0
            )
            plan.accept()
        else:
            rejected.update(reason.value for reason in result.reasons)
        if not options.no_display:
            display = frame.image.copy()
            message = guidance_message(result, current_step.instruction)
            cv2.putText(display, message, (10, 28), cv2.FONT_HERSHEY_SIMPLEX,
                        .65, (0, 255, 0) if result.accepted else (0, 180, 255), 2)
            cv2.putText(display, f"{len(accepted)}/{plan.target_samples}", (10, 56),
                        cv2.FONT_HERSHEY_SIMPLEX, .6, (255, 255, 255), 2)
            if result.face_quality_score is not None:
                cv2.putText(
                    display,
                    f"Score: {result.face_quality_score.total_score:.1f}/100  "
                    f"Quality: {result.face_quality_score.quality_band.value.upper()}",
                    (10, 84), cv2.FONT_HERSHEY_SIMPLEX, .55, (255, 255, 255), 2,
                )
            cv2.imshow("FastVisionAI Guided Face Capture", display)
            if cv2.waitKey(1) & 0xFF == 27:
                cancelled.set()
    duration = time.monotonic() - started
    average_quality = quality_total / len(accepted) if accepted else 0.0
    return accepted, rejected, average_quality, camera_state


def guidance_message(result: GuidedCaptureResult, requested_instruction: str) -> str:
    if result.accepted:
        return "Muestra aceptada"
    messages = {
        GuidedCaptureState.NO_FACE: "Mire al frente",
        GuidedCaptureState.MULTIPLE_FACES: "Debe aparecer una sola persona",
        GuidedCaptureState.FACE_TOO_SMALL: "Acérquese",
        GuidedCaptureState.FACE_OFF_CENTER: "Centre el rostro",
        GuidedCaptureState.POSE_NOT_REQUESTED: requested_instruction,
        GuidedCaptureState.TOO_SOON: "Manténgase quieto",
        GuidedCaptureState.BLURRY: "Manténgase quieto",
    }
    return messages.get(result.primary_state, result.primary_state.value.replace("_", " "))


def persist_accepted(
    captures: list[AcceptedCapture], output: Path, temporary_id: str, session_id: str,
    *, save_data: bool, save_images: bool, consent_confirmed: bool, overwrite: bool,
) -> None:
    validate_persistence_options(save_data=save_data, save_images=save_images,
                                 consent_confirmed=consent_confirmed)
    if not save_data:
        return
    if not captures:
        return
    samples = []
    for capture in captures:
        embedding = capture.result.embedding
        if embedding is None:
            continue
        frame = embedding.frame
        samples.append(CalibrationSample(embedding.embedding, CalibrationSampleMetadata(
            session_id, temporary_id, frame.captured_at, frame.source_name,
            (frame.width, frame.height), embedding.alignment_quality,
            embedding.model, embedding.version, embedding.weights_sha256,
            face_quality_score=(None if capture.result.face_quality_score is None else
                                capture.result.face_quality_score.total_score),
            face_quality_band=(None if capture.result.face_quality_score is None else
                               capture.result.face_quality_score.quality_band.value),
            quality_profile_name=(None if capture.result.face_quality_score is None else
                                  capture.result.face_quality_score.profile_name),
            quality_profile_version=(None if capture.result.face_quality_score is None else
                                     capture.result.face_quality_score.profile_version),
        )))
    CalibrationDatasetStore(enabled=True).save(
        {temporary_id: tuple(samples)}, output / "manifest.json", output / "embeddings.npz",
        consent_confirmed=consent_confirmed, overwrite=overwrite,
    )
    if save_images:
        image_dir = output / "images"
        if image_dir.exists() and not overwrite:
            raise ValueError("guided capture image target already exists")
        image_dir.mkdir(parents=True, exist_ok=True)
        metadata = []
        for capture in captures:
            filename = f"sample_{capture.sample_index:04d}_face_{capture.result.face_index}.jpg"
            cv2.imwrite(str(image_dir / filename), capture.aligned_face.image)
            metadata.append({
                "filename": filename, "sample_index": capture.sample_index,
                "face_index": capture.result.face_index, "run_id": capture.result.run_id,
                "face_quality_score": (None if capture.result.face_quality_score is None else
                                       capture.result.face_quality_score.total_score),
                "quality_band": (None if capture.result.face_quality_score is None else
                                 capture.result.face_quality_score.quality_band.value),
            })
        (image_dir / "metadata.json").write_text(
            json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Guided face-quality capture validation")
    parser.add_argument("--temporary-id", required=True)
    parser.add_argument("--source", type=int, default=0)
    parser.add_argument("--target-samples", type=int, default=9)
    parser.add_argument("--max-duration", type=float)
    parser.add_argument("--no-display", action="store_true")
    parser.add_argument("--save-data", action="store_true")
    parser.add_argument("--save-images", action="store_true")
    parser.add_argument("--consent-confirmed", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--policy-file", type=Path,
                        default=Path("config/guided_capture.dev.json"))
    parser.add_argument("--quality-profile-file", type=Path,
                        default=Path("config/face_quality.dev.json"))
    return parser


def main(*, diagnostics_enabled: bool = False) -> int:
    args = build_parser().parse_args()
    if diagnostics_enabled and (args.save_data or args.save_images):
        raise SystemExit("diagnostic mode does not permit --save-data or --save-images")
    options = GuidedOptions(args.target_samples, args.max_duration, args.no_display)
    validate_runtime_options(options)
    validate_persistence_options(save_data=args.save_data, save_images=args.save_images,
                                 consent_confirmed=args.consent_confirmed)
    profile_path = args.policy_file if args.policy_file.is_absolute() else PROJECT_ROOT / args.policy_file
    profile = load_guided_profile(profile_path)
    diagnostics = (
        GuidedProfileDiagnosticCollector(profile.policy, profile.profile_name,
                                         profile.profile_version)
        if diagnostics_enabled else None
    )
    quality_profile_path = (
        args.quality_profile_file if args.quality_profile_file.is_absolute()
        else PROJECT_ROOT / args.quality_profile_file
    )
    quality_scorer = FaceQualityScorer(load_face_quality_profile(quality_profile_path))
    run_id = f"guided-{uuid.uuid4()}"
    output = args.output or Path("data/guided_capture") / run_id
    output = output if output.is_absolute() else PROJECT_ROOT / output
    cancelled = threading.Event()
    previous = signal.signal(signal.SIGINT, lambda _sig, _frame: cancelled.set())
    config = load_config()
    face_config = next(item for item in config.pipeline.plugins.plugins if item.id == "face_detector")
    embedding_config = next(item for item in config.pipeline.plugins.plugins if item.id == "face_embedding")
    detection_models = ModelManager(PROJECT_ROOT)
    plugin_manager = PluginManager(PluginServices(detection_models)); plugin_manager.discover()
    plugin_manager.configure({"face_detector": face_config.settings}, {"face_detector": 10})
    scheduler = InferenceScheduler(plugin_manager.load_enabled(), BenchmarkManager(), False)
    registry = RuntimeRegistry(); registry.register("scheduler", lambda _settings: scheduler)
    alias = str(face_config.settings["model_alias"])
    runtime = ModelRuntime(registry, "scheduler", {"device": "auto", "model_aliases": [alias]},
                           model_manager=detection_models)
    embedding_models = ModelManager(PROJECT_ROOT)
    embedding_plugin = FaceEmbeddingPlugin(embedding_config.settings, embedding_models)
    camera = CameraManager(CameraConfig(
        "guided_face_capture", CameraType.USB, args.source,
        reconnect=ReconnectConfig(True, 3, .5)), cancelled)
    evaluator = FaceCaptureQualityEvaluator(profile.policy)
    plan = GuidedCapturePlan(args.target_samples)
    started = time.monotonic()
    try:
        runtime.prepare()
        captures, rejected, average_quality, camera_state = run_guided_loop(
            camera,
            lambda frame, rid: runtime.infer(MinimalPreprocessor().prepare(frame),
                                             InferenceContext(run_id=rid)),
            lambda result: FaceAligner().align_result(result),
            lambda face: embedding_plugin.embed((face,))[0], evaluator, plan, options,
            cancelled, run_id, quality_scorer,
            None if diagnostics is None else diagnostics.record,
        )
        persist_accepted(captures, output, args.temporary_id, run_id,
                         save_data=args.save_data, save_images=args.save_images,
                         consent_confirmed=args.consent_confirmed, overwrite=args.overwrite)
    finally:
        camera.release(); runtime.release(); detection_models.unload_all()
        embedding_plugin.release(); embedding_models.unload_all(); cv2.destroyAllWindows()
        signal.signal(signal.SIGINT, previous)
    stage_metrics = evaluator.metrics()
    scores = tuple(
        capture.result.face_quality_score.total_score for capture in captures
        if capture.result.face_quality_score is not None
    )
    safe_scores = tuple({
        "sample_index": capture.sample_index,
        "face_index": capture.result.face_index,
        "run_id": capture.result.run_id,
        "score": capture.result.face_quality_score.total_score,
        "quality_band": capture.result.face_quality_score.quality_band.value,
        "profile_name": capture.result.face_quality_score.profile_name,
        "profile_version": capture.result.face_quality_score.profile_version,
    } for capture in captures if capture.result.face_quality_score is not None)
    summary = GuidedCaptureSummary(
        profile.profile_name, profile.profile_version, stage_metrics.frames_evaluated,
        stage_metrics.visually_valid_candidates, stage_metrics.visual_rejections,
        stage_metrics.temporal_rejections, stage_metrics.embeddings_calculated,
        stage_metrics.embedding_failures, stage_metrics.near_duplicate_rejections,
        len(captures), dict(sorted(rejected.items())), average_quality,
        min(scores) if scores else 0.0, max(scores) if scores else 0.0,
        safe_scores, quality_scorer.profile.profile_name,
        quality_scorer.profile.profile_version,
        plan.covered_poses(), time.monotonic() - started, bool(args.save_data),
        bool(args.save_images), "released", runtime.state.value,
        detection_models.state(detection_models.resolve_alias(alias)).value,
        embedding_models.state(embedding_models.resolve_alias(embedding_plugin.alias)).value,
    )
    payload: object = asdict(summary)
    if diagnostics is not None:
        payload = {
            "guided_capture_summary": asdict(summary),
            "profile_diagnostics": asdict(diagnostics.report()),
        }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
