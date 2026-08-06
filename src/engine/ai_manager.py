"""Initial coordinator for Frame Queue, preprocessing and inference."""

from __future__ import annotations

import logging
import queue
import threading
import time

from src.engine.benchmark.manager import BenchmarkManager
from src.engine.config import QueueConfig
from src.engine.contracts.detection import InferenceResult
from src.engine.contracts.detector import InferenceBackend
from src.engine.contracts.frame import Frame
from src.engine.contracts.inference_context import InferenceContext
from src.engine.contracts.metrics import PipelineMetrics
from src.engine.frame_queue import FrameQueue, FrameQueueMetrics
from src.engine.preprocessor import InvalidFrameError, MinimalPreprocessor

LOGGER = logging.getLogger(__name__)


class AIManager:
    def __init__(
        self,
        queue_config: QueueConfig,
        preprocessor: MinimalPreprocessor,
        backend: InferenceBackend,
        context: InferenceContext | None = None,
        benchmark: BenchmarkManager | None = None,
    ) -> None:
        self.frame_queue = FrameQueue(queue_config.capacity, queue_config.policy)
        self._submit_timeout = queue_config.wait_timeout_seconds
        self._preprocessor = preprocessor
        self._backend = backend
        self._context = context or InferenceContext()
        self._benchmark = benchmark
        self._results: queue.Queue[InferenceResult] = queue.Queue()
        self._cancelled = threading.Event()
        self._worker: threading.Thread | None = None
        self._lock = threading.Lock()
        self._submitted = 0
        self._processed = 0
        self._preprocessing_errors = 0
        self._inference_errors = 0
        self._latency_total_ms = 0.0

    @property
    def running(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def start(self) -> None:
        if self.running:
            return
        if self._cancelled.is_set():
            raise RuntimeError("AIManager cannot restart after stop")
        self._worker = threading.Thread(target=self._run, name="ai-manager", daemon=False)
        self._worker.start()

    def submit(self, frame: Frame) -> bool:
        if self._cancelled.is_set():
            return False
        accepted = self.frame_queue.put(frame, timeout=self._submit_timeout)
        if accepted:
            with self._lock:
                self._submitted += 1
        if self._benchmark is not None:
            self._benchmark.update_frames_dropped(self.frame_queue.metrics().frames_dropped)
        return accepted

    def get_result(self, timeout: float | None = None) -> InferenceResult | None:
        try:
            return self._results.get(timeout=timeout)
        except queue.Empty:
            return None

    def stop(self, timeout: float = 5.0) -> bool:
        self._cancelled.set()
        self.frame_queue.cancel()
        worker = self._worker
        if worker is not None:
            worker.join(timeout)
        return worker is None or not worker.is_alive()

    def pipeline_metrics(self) -> PipelineMetrics:
        with self._lock:
            average = self._latency_total_ms / self._processed if self._processed else 0.0
            return PipelineMetrics(
                frames_submitted=self._submitted,
                frames_processed=self._processed,
                preprocessing_errors=self._preprocessing_errors,
                inference_errors=self._inference_errors,
                average_pipeline_latency_ms=average,
                average_queue_wait_ms=(
                    self._benchmark.snapshot().average_queue_wait_ms
                    if self._benchmark is not None
                    else 0.0
                ),
            )

    def queue_metrics(self) -> FrameQueueMetrics:
        return self.frame_queue.metrics()

    def _run(self) -> None:
        while not self._cancelled.is_set():
            queued = self.frame_queue.get_with_wait(timeout=0.1)
            if queued is None:
                continue
            frame, queue_wait_ms = queued
            started = time.monotonic()
            if self._benchmark is not None:
                self._benchmark.record_frame_started(queue_wait_ms)
            try:
                prepared = self._preprocessor.prepare(frame)
            except InvalidFrameError as exc:
                with self._lock:
                    self._preprocessing_errors += 1
                LOGGER.warning("Frame descartado por preprocesamiento: %s", exc)
                continue
            try:
                result = self._backend.infer(prepared, self._context)
            except Exception as exc:  # Backends are an isolation boundary.
                with self._lock:
                    self._inference_errors += 1
                LOGGER.exception("Fallo de inferencia aislado: %s", exc)
                continue
            latency_ms = (time.monotonic() - started) * 1_000
            self._results.put(result)
            with self._lock:
                self._processed += 1
                self._latency_total_ms += latency_ms
            if self._benchmark is not None:
                self._benchmark.record_frame_completed(latency_ms)
