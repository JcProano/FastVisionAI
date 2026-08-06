"""Static enrollment validation using explicitly synthetic photometric variants."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, replace
from pathlib import Path

import cv2
import numpy as np

from src.camera.frame import Frame
from src.core.config_manager import PROJECT_ROOT, load_config
from src.engine.alignment import FaceAligner
from src.engine.benchmark.manager import BenchmarkManager
from src.engine.contracts.inference_context import InferenceContext
from src.engine.embedding import FaceEmbeddingPlugin
from src.engine.enrollment import EnrollmentPolicy, EnrollmentResult, EnrollmentService
from src.engine.gallery import FaceGallery
from src.engine.models.manager import ModelManager
from src.engine.plugins.manager import PluginManager
from src.engine.plugins.services import PluginServices
from src.engine.preprocessor import MinimalPreprocessor
from src.engine.runtime.model_runtime import ModelRuntime
from src.engine.runtime.registry import RuntimeRegistry
from src.engine.scheduler.inference_scheduler import InferenceScheduler

SYNTHETIC_NOTICE = (
    "Photometric variants are not independent biometric captures and must not "
    "be used to calibrate real enrollment or recognition thresholds."
)


def run(input_path: Path, templates_per_identity: int = 3) -> dict[str, object]:
    if templates_per_identity != 3:
        raise ValueError("static validation currently requires exactly 3 variants")
    config = load_config()
    face_config = next(item for item in config.pipeline.plugins.plugins if item.id == "face_detector")
    embedding_config = next(
        item for item in config.pipeline.plugins.plugins if item.id == "face_embedding"
    )
    image = cv2.imread(str(input_path))
    if image is None:
        raise FileNotFoundError(f"Could not read input image: {input_path}")
    detection_models = ModelManager(PROJECT_ROOT)
    plugins = PluginManager(PluginServices(detection_models)); plugins.discover()
    plugins.configure({"face_detector": face_config.settings}, {"face_detector": 10})
    scheduler = InferenceScheduler(plugins.load_enabled(), BenchmarkManager(), False)
    registry = RuntimeRegistry(); registry.register("scheduler", lambda _settings: scheduler)
    alias = str(face_config.settings["model_alias"])
    runtime = ModelRuntime(
        registry, "scheduler", {"device": "auto", "model_aliases": [alias]},
        model_manager=detection_models,
    )
    runtime.prepare()
    frame = Frame.create(
        image, sequence_id=1, source_name=str(input_path),
        monotonic_timestamp=time.monotonic(), connection_id=1,
    )
    try:
        result = runtime.infer(
            MinimalPreprocessor().prepare(frame),
            InferenceContext(run_id="static-face-enrollment"),
        )
        aligned = FaceAligner().align_result(result)
    finally:
        runtime.release(); detection_models.unload_all()

    embedding_models = ModelManager(PROJECT_ROOT)
    embedder = FaceEmbeddingPlugin(embedding_config.settings, embedding_models)
    gallery = FaceGallery()
    # Explicit development-only consistency/diversity bounds for these variants.
    policy = EnrollmentPolicy(
        min_templates=3,
        max_templates=3,
        allow_low_quality=True,
        min_pairwise_similarity=0.50,
        max_pairwise_similarity=0.99999,
    )
    enrollment_results: list[EnrollmentResult] = []
    try:
        for face in aligned:
            if face.image is None:
                continue
            variants = tuple(
                replace(face, image=_brightness_variant(face.image, offset))
                for offset in (-24, 0, 24)
            )
            embeddings = embedder.embed(variants)
            enrollment_results.append(EnrollmentService(gallery, policy).enroll(
                f"temporary_enrollment_{face.face_index:03d}",
                f"Temporary Enrollment {face.face_index:03d}",
                embeddings,
                {"synthetic_validation": True, "source_face_index": face.face_index},
            ))
    finally:
        embedder.release(); embedding_models.unload_all()
    report = build_validation_report(enrollment_results, gallery, policy)
    report["detector_runtime_state"] = runtime.state.value
    report["embedding_model_state"] = embedding_models.state(
        embedding_models.resolve_alias(embedder.alias)
    ).value
    return report


def build_validation_report(
    results: list[EnrollmentResult], gallery: FaceGallery, policy: EnrollmentPolicy
) -> dict[str, object]:
    return {
        "synthetic_validation": True,
        "notice": SYNTHETIC_NOTICE,
        "policy": asdict(policy),
        "identities": [
            {
                "person_id": result.identity.person_id,
                "status": result.status.value,
                "accepted": [item.input_index for item in result.accepted_templates],
                "rejected": [
                    {"input_index": item.input_index,
                     "causes": [cause.value for cause in item.causes]}
                    for item in result.rejected_templates
                ],
                "causes": [cause.value for cause in result.causes],
                "pairwise": {
                    "comparisons": result.metrics.pairwise_comparisons,
                    "minimum": result.metrics.minimum_pairwise_similarity,
                    "average": result.metrics.average_pairwise_similarity,
                    "maximum": result.metrics.maximum_pairwise_similarity,
                },
            }
            for result in results
        ],
        "gallery_identities": len(gallery.list_identities()),
        "gallery_templates": len(gallery.templates()),
    }


def _brightness_variant(image: np.ndarray, offset: int) -> np.ndarray:
    return np.clip(image.astype(np.int16) + offset, 0, 255).astype(np.uint8)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate synthetic local face enrollment")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--templates-per-identity", type=int, default=3)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    input_path = args.input if args.input.is_absolute() else PROJECT_ROOT / args.input
    print(json.dumps(run(input_path.resolve(), args.templates_per_identity), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
