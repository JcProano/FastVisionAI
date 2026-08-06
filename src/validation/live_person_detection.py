"""Headless-capable live USB validation for PersonDetectorPlugin."""

from __future__ import annotations

import argparse
import json
import signal
import threading
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Protocol

import cv2

from src.camera.camera_manager import CameraManager
from src.camera.camera_types import CameraConfig, CameraType, ReadStatus, ReconnectConfig
from src.camera.frame import Frame
from src.core.config_manager import PROJECT_ROOT, load_config
from src.engine.ai_manager import AIManager
from src.engine.benchmark.manager import BenchmarkManager
from src.engine.config import QueueConfig, QueuePolicy
from src.engine.contracts.detection import InferenceResult
from src.engine.contracts.inference_context import InferenceContext
from src.engine.models.manager import ModelManager
from src.engine.plugins.manager import PluginManager
from src.engine.plugins.services import PluginServices
from src.engine.preprocessor import MinimalPreprocessor
from src.engine.runtime.model_runtime import ModelRuntime
from src.engine.runtime.registry import RuntimeRegistry
from src.engine.scheduler.inference_scheduler import InferenceScheduler


class CameraLike(Protocol):
    connected: bool
    def open(self) -> bool: ...
    def read(self): ...
    def release(self) -> None: ...


class AIManagerLike(Protocol):
    def submit(self, frame: Frame) -> bool: ...
    def get_result(self, timeout: float | None = None) -> InferenceResult | None: ...
    def queue_metrics(self): ...
    def pipeline_metrics(self): ...


@dataclass(frozen=True, slots=True)
class LiveOptions:
    min_inference_interval: float = 0.2
    result_max_age: float = 1.5
    max_duration: float | None = None
    max_frames: int | None = None
    no_display: bool = False


@dataclass(frozen=True, slots=True)
class LiveMetrics:
    frames_captured: int
    frames_submitted: int
    frames_processed: int
    frames_dropped: int
    stale_results_omitted: int
    capture_fps: float
    inference_fps: float
    average_latency_ms: float
    actual_resolution: str
    camera_state: str


class ResolutionCapture:
    """VideoCapture-compatible adapter applying requested USB resolution."""

    def __init__(self, width: int, height: int) -> None:
        self._capture = cv2.VideoCapture()
        self._width = width
        self._height = height

    def set(self, property_id: int, value: float) -> bool:
        return self._capture.set(property_id, value)

    def open(self, source: int | str) -> bool:
        opened = self._capture.open(source)
        if opened:
            self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
            self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
        return opened

    def isOpened(self) -> bool:
        return self._capture.isOpened()

    def read(self):
        return self._capture.read()

    def release(self) -> None:
        self._capture.release()


def normalized_box_to_pixels(result: InferenceResult, width: int, height: int):
    boxes = []
    for detection in result.detections:
        box = detection.bounding_box
        boxes.append((
            max(0, min(width - 1, round(box.x1 * width))),
            max(0, min(height - 1, round(box.y1 * height))),
            max(0, min(width - 1, round(box.x2 * width))),
            max(0, min(height - 1, round(box.y2 * height))),
            detection,
        ))
    return boxes


def draw_overlay(image, result: InferenceResult | None, metrics: LiveMetrics) -> None:
    if result is not None:
        height, width = image.shape[:2]
        for x1, y1, x2, y2, detection in normalized_box_to_pixels(result, width, height):
            cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(image, f"person {detection.confidence:.2f}", (x1, max(18, y1 - 5)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    people = len(result.detections) if result else 0
    lines = [
        f"People: {people}", f"Capture FPS: {metrics.capture_fps:.2f}",
        f"Inference FPS: {metrics.inference_fps:.2f}",
        f"Latency: {metrics.average_latency_ms:.1f} ms", f"Dropped: {metrics.frames_dropped}",
    ]
    for index, text in enumerate(lines):
        cv2.putText(image, text, (10, 24 + index * 22), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (255, 255, 255), 2)


def run_capture_loop(
    camera: CameraLike,
    ai_manager: AIManagerLike,
    options: LiveOptions,
    cancelled: threading.Event,
) -> LiveMetrics:
    started = time.monotonic()
    last_submit = float("-inf")
    captured = submitted = stale = 0
    latest_result: InferenceResult | None = None
    resolution = "unknown"
    camera_state = "disconnected"
    if not camera.open():
        return LiveMetrics(0, 0, 0, 0, 0, 0, 0, 0, resolution, camera_state)
    camera_state = "connected"

    while not cancelled.is_set():
        now = time.monotonic()
        if options.max_duration is not None and now - started >= options.max_duration:
            break
        if options.max_frames is not None and captured >= options.max_frames:
            break
        read_result = camera.read()
        if read_result.status is not ReadStatus.FRAME or read_result.frame is None:
            camera_state = read_result.status.value
            break
        frame = read_result.frame
        captured += 1
        resolution = f"{frame.width}x{frame.height}"
        now = time.monotonic()
        if now - last_submit >= options.min_inference_interval:
            if ai_manager.submit(frame):
                submitted += 1
                last_submit = now

        while True:
            result = ai_manager.get_result(timeout=0)
            if result is None:
                break
            if now - result.frame.monotonic_timestamp > options.result_max_age:
                stale += 1
            else:
                latest_result = result
        if latest_result is not None and now - latest_result.frame.monotonic_timestamp > options.result_max_age:
            latest_result = None

        elapsed = max(time.monotonic() - started, 1e-9)
        pipeline = ai_manager.pipeline_metrics()
        queue = ai_manager.queue_metrics()
        live_metrics = LiveMetrics(
            captured, submitted, pipeline.frames_processed, queue.frames_dropped, stale,
            captured / elapsed, pipeline.frames_processed / elapsed,
            pipeline.average_pipeline_latency_ms, resolution, camera_state,
        )
        if not options.no_display:
            display = frame.image.copy()
            draw_overlay(display, latest_result, live_metrics)
            cv2.imshow("FastVisionAI Person Detection", display)
            if cv2.waitKey(1) & 0xFF == 27:
                cancelled.set()

    elapsed = max(time.monotonic() - started, 1e-9)
    pipeline = ai_manager.pipeline_metrics()
    queue = ai_manager.queue_metrics()
    return LiveMetrics(
        captured, submitted, pipeline.frames_processed, queue.frames_dropped, stale,
        captured / elapsed, pipeline.frames_processed / elapsed,
        pipeline.average_pipeline_latency_ms, resolution, camera_state,
    )


def parse_source(value: str) -> int | str:
    if value.isdigit():
        return int(value)
    path = Path(value)
    if path.parent == Path("/dev") and path.name.startswith("video"):
        return value
    raise argparse.ArgumentTypeError("source must be a USB index or /dev/videoX")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Live USB PersonDetectorPlugin validation")
    parser.add_argument("--source", type=parse_source, default=0)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--confidence", type=float, default=0.4)
    parser.add_argument("--image-size", type=int, default=640)
    parser.add_argument("--min-inference-interval", type=float, default=0.2)
    parser.add_argument("--result-max-age", type=float, default=1.5)
    parser.add_argument("--queue-capacity", type=int, default=2)
    parser.add_argument("--max-duration", type=float, default=None)
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument("--no-display", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    for name in ("width", "height", "image_size", "queue_capacity"):
        if getattr(args, name) <= 0:
            raise SystemExit(f"--{name.replace('_', '-')} must be positive")
    cancelled = threading.Event()
    previous = signal.signal(signal.SIGINT, lambda _signal, _frame: cancelled.set())
    config = load_config()
    person = next(item for item in config.pipeline.plugins.plugins if item.id == "person_detector")
    settings = dict(person.settings)
    settings.update(confidence=args.confidence, image_size=args.image_size)
    model_manager = ModelManager(PROJECT_ROOT)
    plugin_manager = PluginManager(PluginServices(model_manager))
    plugin_manager.discover()
    plugin_manager.configure({"person_detector": settings}, {"person_detector": person.priority})
    benchmark = BenchmarkManager()
    scheduler = InferenceScheduler(plugin_manager.load_enabled(), benchmark, continue_on_error=False)
    registry = RuntimeRegistry()
    registry.register("scheduler", lambda _settings: scheduler)
    alias = str(settings["model_alias"])
    runtime = ModelRuntime(registry, "scheduler", {"device": "auto", "model_aliases": [alias]}, model_manager=model_manager)
    runtime.prepare()
    ai_manager = AIManager(
        QueueConfig(args.queue_capacity, QueuePolicy.REALTIME, 0.0),
        MinimalPreprocessor(), runtime, InferenceContext(), benchmark,
    )
    ai_manager.start()
    camera = CameraManager(
        CameraConfig("usb_validation", CameraType.USB, args.source,
                     reconnect=ReconnectConfig(enabled=True, max_attempts=3, interval_seconds=0.5)),
        cancel_event=cancelled,
        capture_factory=lambda: ResolutionCapture(args.width, args.height),
    )
    options = LiveOptions(args.min_inference_interval, args.result_max_age,
                          args.max_duration, args.max_frames, args.no_display)
    try:
        metrics = run_capture_loop(camera, ai_manager, options, cancelled)
    finally:
        camera.release()
        ai_manager.stop(timeout=30)
        runtime.release()
        model_manager.unload_all()
        cv2.destroyAllWindows()
        signal.signal(signal.SIGINT, previous)
    final_pipeline = ai_manager.pipeline_metrics()
    final_queue = ai_manager.queue_metrics()
    elapsed = metrics.frames_captured / metrics.capture_fps if metrics.capture_fps > 0 else 0.0
    metrics = replace(
        metrics,
        frames_processed=final_pipeline.frames_processed,
        frames_dropped=final_queue.frames_dropped,
        inference_fps=(final_pipeline.frames_processed / elapsed if elapsed > 0 else 0.0),
        average_latency_ms=final_pipeline.average_pipeline_latency_ms,
        camera_state="released",
    )
    final = asdict(metrics)
    final.update(runtime_state=runtime.state.value,
                 model_state=model_manager.state(model_manager.resolve_alias(alias)).value)
    print(json.dumps(final, indent=2))
    return 0 if metrics.frames_captured > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
