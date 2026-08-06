"""Real static detection followed by deterministic five-point face alignment."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

import cv2

from src.camera.frame import Frame
from src.core.config_manager import PROJECT_ROOT, load_config
from src.engine.alignment import AlignmentStatus, FaceAligner
from src.engine.alignment.face_aligner import TEMPLATE_VERSION
from src.engine.benchmark.manager import BenchmarkManager
from src.engine.contracts.inference_context import InferenceContext
from src.engine.models.manager import ModelManager
from src.engine.plugins.manager import PluginManager
from src.engine.plugins.services import PluginServices
from src.engine.preprocessor import MinimalPreprocessor
from src.engine.runtime.model_runtime import ModelRuntime
from src.engine.runtime.registry import RuntimeRegistry
from src.engine.scheduler.inference_scheduler import InferenceScheduler


def draw_diagnostic(image, result, aligned_faces):
    diagnostic = image.copy()
    height, width = diagnostic.shape[:2]
    plugin_data = result.attachments["face_detector"]
    landmarks = plugin_data["landmarks"]
    for index, (detection, aligned) in enumerate(zip(result.detections, aligned_faces)):
        box = detection.bounding_box
        x1, y1 = round(box.x1 * width), round(box.y1 * height)
        x2, y2 = round(box.x2 * width), round(box.y2 * height)
        color = (0, 255, 0) if aligned.status is AlignmentStatus.ALIGNED else (0, 0, 255)
        cv2.rectangle(diagnostic, (x1, y1), (x2, y2), color, 2)
        for point_index, (x, y) in enumerate(landmarks[index]):
            cv2.circle(diagnostic, (round(x * width), round(y * height)), 3, color, -1)
            cv2.putText(
                diagnostic, str(point_index), (round(x * width) + 3, round(y * height) - 3),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1,
            )
        cv2.putText(
            diagnostic,
            f"#{index} {detection.confidence:.2f} {aligned.quality.value}",
            (x1, max(15, y1 - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
        )
    return diagnostic


def run(input_path: Path, output_directory: Path) -> dict[str, object]:
    config = load_config()
    face_config = next(item for item in config.pipeline.plugins.plugins if item.id == "face_detector")
    image = cv2.imread(str(input_path))
    if image is None:
        raise FileNotFoundError(f"Could not read input image: {input_path}")

    model_manager = ModelManager(PROJECT_ROOT)
    plugin_manager = PluginManager(PluginServices(model_manager))
    plugin_manager.discover()
    plugin_manager.configure(
        {"face_detector": face_config.settings}, {"face_detector": face_config.priority}
    )
    benchmark = BenchmarkManager()
    scheduler = InferenceScheduler(plugin_manager.load_enabled(), benchmark, continue_on_error=False)
    registry = RuntimeRegistry()
    registry.register("scheduler", lambda _settings: scheduler)
    alias = str(face_config.settings["model_alias"])
    runtime = ModelRuntime(
        registry, "scheduler", {"device": "auto", "model_aliases": [alias]},
        model_manager=model_manager,
    )
    runtime.prepare()
    frame = Frame.create(
        image, sequence_id=1, source_name=str(input_path),
        monotonic_timestamp=time.monotonic(), connection_id=1,
    )
    aligner = FaceAligner()
    report: dict[str, object]
    try:
        result = runtime.infer(
            MinimalPreprocessor().prepare(frame),
            InferenceContext(run_id="static-face-alignment"),
        )
        aligned_faces = aligner.align_result(result)
        output_directory.mkdir(parents=True, exist_ok=True)
        saved_faces: list[str] = []
        for aligned in aligned_faces:
            if aligned.status is not AlignmentStatus.ALIGNED or aligned.image is None:
                continue
            path = output_directory / f"face_{aligned.face_index:03d}.jpg"
            if not cv2.imwrite(str(path), aligned.image):
                raise OSError(f"Could not write aligned face: {path}")
            saved_faces.append(str(path))
        diagnostic_path = output_directory / "diagnostic.jpg"
        if not cv2.imwrite(str(diagnostic_path), draw_diagnostic(image, result, aligned_faces)):
            raise OSError(f"Could not write diagnostic image: {diagnostic_path}")
        report = {
            "template_version": TEMPLATE_VERSION,
            "run_id": "static-face-alignment",
            "faces": [
                {
                    "face_index": item.face_index,
                    "confidence": item.confidence,
                    "status": item.status.value,
                    "quality": item.quality.value,
                    "error": item.error,
                    "alignment_time_ms": round(item.alignment_time_ms, 3),
                    "normalized_interocular_distance": item.normalized_interocular_distance,
                    "relative_face_size": item.relative_face_size,
                    "visible_box_ratio": item.visible_box_ratio,
                    "transform_matrix": (
                        item.transform_matrix.tolist() if item.transform_matrix is not None else None
                    ),
                    "inverse_transform_matrix": (
                        item.inverse_transform_matrix.tolist()
                        if item.inverse_transform_matrix is not None else None
                    ),
                }
                for item in aligned_faces
            ],
            "metrics": asdict(aligner.metrics()),
            "saved_faces": saved_faces,
            "diagnostic": str(diagnostic_path),
        }
    finally:
        runtime.release()
        model_manager.unload_all()
    report["runtime_state"] = runtime.state.value
    report["model_state"] = model_manager.state(model_manager.resolve_alias(alias)).value
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Detect and align faces in one local image")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/face_alignment"))
    return parser


def main() -> int:
    args = build_parser().parse_args()
    input_path = args.input if args.input.is_absolute() else PROJECT_ROOT / args.input
    output_dir = args.output_dir if args.output_dir.is_absolute() else PROJECT_ROOT / args.output_dir
    print(json.dumps(run(input_path.resolve(), output_dir.resolve()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
