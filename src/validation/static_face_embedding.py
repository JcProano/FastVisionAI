"""Static detector -> aligner -> embedding validation without identity matching."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

import cv2

from src.camera.frame import Frame
from src.core.config_manager import PROJECT_ROOT, load_config
from src.engine.alignment import FaceAligner
from src.engine.benchmark.manager import BenchmarkManager
from src.engine.contracts.inference_context import InferenceContext
from src.engine.embedding import FaceEmbeddingPlugin
from src.engine.models.manager import ModelManager
from src.engine.plugins.manager import PluginManager
from src.engine.plugins.services import PluginServices
from src.engine.preprocessor import MinimalPreprocessor
from src.engine.runtime.model_runtime import ModelRuntime
from src.engine.runtime.registry import RuntimeRegistry
from src.engine.scheduler.inference_scheduler import InferenceScheduler


def run(input_path: Path) -> dict[str, object]:
    config = load_config()
    face_config = next(item for item in config.pipeline.plugins.plugins if item.id == "face_detector")
    embedding_config = next(
        item for item in config.pipeline.plugins.plugins if item.id == "face_embedding"
    )
    image = cv2.imread(str(input_path))
    if image is None:
        raise FileNotFoundError(f"Could not read input image: {input_path}")

    detection_models = ModelManager(PROJECT_ROOT)
    plugin_manager = PluginManager(PluginServices(detection_models))
    plugin_manager.discover()
    plugin_manager.configure(
        {"face_detector": face_config.settings}, {"face_detector": face_config.priority}
    )
    scheduler = InferenceScheduler(
        plugin_manager.load_enabled(), BenchmarkManager(), continue_on_error=False
    )
    registry = RuntimeRegistry()
    registry.register("scheduler", lambda _settings: scheduler)
    detector_alias = str(face_config.settings["model_alias"])
    runtime = ModelRuntime(
        registry, "scheduler", {"device": "auto", "model_aliases": [detector_alias]},
        model_manager=detection_models,
    )
    runtime.prepare()
    frame = Frame.create(
        image, sequence_id=1, source_name=str(input_path),
        monotonic_timestamp=time.monotonic(), connection_id=1,
    )
    try:
        detection_result = runtime.infer(
            MinimalPreprocessor().prepare(frame),
            InferenceContext(run_id="static-face-embedding"),
        )
        aligned_faces = FaceAligner().align_result(detection_result)
    finally:
        runtime.release()
        detection_models.unload_all()

    # A separate manager prevents the ArcFace loader from replacing YuNet's
    # backend loader in the current one-loader-per-backend registry.
    embedding_models = ModelManager(PROJECT_ROOT)
    embedding_plugin = FaceEmbeddingPlugin(embedding_config.settings, embedding_models)
    try:
        embeddings = embedding_plugin.embed(aligned_faces)
        report = {
            "run_id": "static-face-embedding",
            "faces_detected": len(detection_result.detections),
            "faces_aligned": sum(face.image is not None for face in aligned_faces),
            "embeddings": [
                {
                    "face_index": item.face_index,
                    "dimension": item.dimension,
                    "l2_norm": item.l2_norm,
                    "alignment_quality": item.alignment_quality.value,
                    "inference_time_ms": item.inference_time_ms,
                    "backend": item.backend,
                    "model": item.model,
                    "version": item.version,
                    "weights_sha256": item.weights_sha256,
                }
                for item in embeddings
            ],
            "metrics": asdict(embedding_plugin.metrics()),
        }
    finally:
        embedding_plugin.release()
        embedding_models.unload_all()
    report["detector_runtime_state"] = runtime.state.value
    report["embedding_model_state"] = embedding_models.state(
        embedding_models.resolve_alias(embedding_plugin.alias)
    ).value
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate static face embedding generation")
    parser.add_argument("--input", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    input_path = args.input if args.input.is_absolute() else PROJECT_ROOT / args.input
    print(json.dumps(run(input_path.resolve()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
