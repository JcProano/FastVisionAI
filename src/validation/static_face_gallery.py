"""Static temporary-identity gallery validation without identity assignment."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2

from src.camera.frame import Frame
from src.core.config_manager import PROJECT_ROOT, load_config
from src.engine.alignment import FaceAligner
from src.engine.benchmark.manager import BenchmarkManager
from src.engine.contracts.inference_context import InferenceContext
from src.engine.embedding import FaceEmbeddingPlugin
from src.engine.gallery import FaceGallery, FaceIdentity, FaceMatcher
from src.engine.models.manager import ModelManager
from src.engine.plugins.manager import PluginManager
from src.engine.plugins.services import PluginServices
from src.engine.preprocessor import MinimalPreprocessor
from src.engine.runtime.model_runtime import ModelRuntime
from src.engine.runtime.registry import RuntimeRegistry
from src.engine.scheduler.inference_scheduler import InferenceScheduler


def run(input_path: Path, top_k: int = 2) -> dict[str, object]:
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
        detected = runtime.infer(
            MinimalPreprocessor().prepare(frame),
            InferenceContext(run_id="static-face-gallery"),
        )
        aligned = FaceAligner().align_result(detected)
    finally:
        runtime.release()
        detection_models.unload_all()

    embedding_models = ModelManager(PROJECT_ROOT)
    embedder = FaceEmbeddingPlugin(embedding_config.settings, embedding_models)
    try:
        embeddings = embedder.embed(aligned)
        gallery = FaceGallery()
        for embedding in embeddings:
            person_id = f"temporary_face_{embedding.face_index:03d}"
            gallery.register_identity(FaceIdentity(
                person_id, f"Temporary Face {embedding.face_index:03d}", {"temporary": True}
            ))
            gallery.add_template(
                person_id, embedding, source_reference=f"bus-face-{embedding.face_index}"
            )
        matches = [FaceMatcher(top_k=top_k).match(item, gallery) for item in embeddings]
        report = {
            "gallery": {
                "identities": len(gallery.list_identities()),
                "templates": len(gallery.templates()),
                "persistence_enabled": False,
            },
            "queries": [
                {
                    "face_index": match.query.face_index,
                    "run_id": match.query.run_id,
                    "decision": match.decision.value,
                    "best_candidate": (
                        match.best_candidate.identity.person_id
                        if match.best_candidate is not None else None
                    ),
                    "candidates": [
                        {
                            "rank": candidate.rank,
                            "person_id": candidate.identity.person_id,
                            "template_index": candidate.template_index,
                            "similarity": candidate.similarity,
                            "quality": candidate.quality.value,
                            "model_compatible": candidate.model_compatibility.compatible,
                        }
                        for candidate in match.candidates
                    ],
                }
                for match in matches
            ],
            "identity_assignment_performed": False,
        }
    finally:
        embedder.release()
        embedding_models.unload_all()
    report["detector_runtime_state"] = runtime.state.value
    report["embedding_model_state"] = embedding_models.state(
        embedding_models.resolve_alias(embedder.alias)
    ).value
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate an in-memory temporary face gallery")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--top-k", type=int, default=2)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.top_k <= 0:
        raise SystemExit("--top-k must be positive")
    input_path = args.input if args.input.is_absolute() else PROJECT_ROOT / args.input
    print(json.dumps(run(input_path.resolve(), args.top_k), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
