"""Single-image validation of the real YuNet pipeline; no camera is opened."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Mapping

import cv2

from src.camera.frame import Frame
from src.core.config_manager import PROJECT_ROOT, load_config
from src.engine.benchmark.manager import BenchmarkManager
from src.engine.contracts.detection import InferenceResult
from src.engine.contracts.inference_context import InferenceContext
from src.engine.models.manager import ModelManager
from src.engine.plugins.manager import PluginManager
from src.engine.plugins.services import PluginServices
from src.engine.preprocessor import MinimalPreprocessor
from src.engine.runtime.model_runtime import ModelRuntime
from src.engine.runtime.registry import RuntimeRegistry
from src.engine.scheduler.inference_scheduler import InferenceScheduler


def annotate(image: Any, result: InferenceResult) -> Any:
    output = image.copy()
    height, width = output.shape[:2]
    for detection in result.detections:
        box = detection.bounding_box
        x1, y1 = round(box.x1 * width), round(box.y1 * height)
        x2, y2 = round(box.x2 * width), round(box.y2 * height)
        cv2.rectangle(output, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(
            output,
            f"face {detection.confidence:.2f}",
            (x1, max(15, y1 - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 0),
            1,
            cv2.LINE_AA,
        )
    return output


def run(input_path: Path, output_path: Path) -> dict[str, object]:
    config = load_config()
    configured = next(
        (item for item in config.pipeline.plugins.plugins if item.id == "face_detector"),
        None,
    )
    if configured is None:
        raise RuntimeError("face_detector is not configured")

    image = cv2.imread(str(input_path))
    if image is None:
        raise FileNotFoundError(f"Could not read input image: {input_path}")

    settings: Mapping[str, Any] = configured.settings
    model_manager = ModelManager(PROJECT_ROOT)
    plugin_manager = PluginManager(PluginServices(model_manager))
    plugin_manager.discover()
    # This local configuration enables only FaceDetectorPlugin for one image.
    plugin_manager.configure({"face_detector": settings}, {"face_detector": configured.priority})
    benchmark = BenchmarkManager()
    scheduler = InferenceScheduler(plugin_manager.load_enabled(), benchmark, continue_on_error=False)
    registry = RuntimeRegistry()
    registry.register("scheduler", lambda _settings: scheduler)
    alias = str(settings["model_alias"])
    runtime = ModelRuntime(
        registry,
        "scheduler",
        {"device": "auto", "model_aliases": [alias]},
        model_manager=model_manager,
    )
    runtime.prepare()
    frame = Frame.create(
        image,
        sequence_id=1,
        source_name=str(input_path),
        monotonic_timestamp=time.monotonic(),
        connection_id=1,
    )
    started = time.monotonic()
    report: dict[str, object]
    try:
        result = runtime.infer(
            MinimalPreprocessor().prepare(frame),
            InferenceContext(run_id="static-face-validation"),
        )
        elapsed_ms = (time.monotonic() - started) * 1_000
        output = annotate(image, result)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(output_path), output):
            raise OSError(f"Could not write output image: {output_path}")
        plugin_data = result.attachments.get("face_detector", {})
        landmarks = plugin_data.get("landmarks", ())
        report = {
            "faces": len(result.detections),
            "resolution": [frame.width, frame.height],
            "load_time_ms": round(float(plugin_data.get("load_time_ms", 0.0)), 3),
            "inference_time_ms": round(result.metrics.inference_ms, 3),
            "total_latency_ms": round(elapsed_ms, 3),
            "run_id": plugin_data.get("run_id"),
            "weights_sha256": plugin_data.get("weights_sha256"),
            "detections": [
                {
                    "confidence": round(detection.confidence, 6),
                    "bounding_box": {
                        "x1": round(detection.bounding_box.x1, 6),
                        "y1": round(detection.bounding_box.y1, 6),
                        "x2": round(detection.bounding_box.x2, 6),
                        "y2": round(detection.bounding_box.y2, 6),
                        "normalized": detection.bounding_box.normalized,
                    },
                    "landmarks": landmarks[index] if index < len(landmarks) else (),
                }
                for index, detection in enumerate(result.detections)
            ],
            "output": str(output_path),
        }
    finally:
        runtime.release()
        model_manager.unload_all()
    report["runtime_state"] = runtime.state.value
    report["model_state"] = model_manager.state(model_manager.resolve_alias(alias)).value
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate YuNet on one local image")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/face_validation/result.jpg"),
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    input_path = args.input if args.input.is_absolute() else PROJECT_ROOT / args.input
    output_path = args.output if args.output.is_absolute() else PROJECT_ROOT / args.output
    print(json.dumps(run(input_path.resolve(), output_path.resolve()), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
