"""Sequential multi-plugin InferenceBackend."""

from __future__ import annotations

import logging
import time

from src.engine.benchmark.manager import BenchmarkManager
from src.engine.contracts.detection import Detection, InferenceResult
from src.engine.contracts.inference_context import InferenceContext
from src.engine.contracts.metrics import InferenceMetrics
from src.engine.contracts.prepared_frame import PreparedFrame
from src.engine.plugins.contracts import LoadedPlugin

LOGGER = logging.getLogger(__name__)


class InferenceScheduler:
    def __init__(
        self,
        plugins: tuple[LoadedPlugin, ...],
        benchmark: BenchmarkManager,
        continue_on_error: bool = True,
    ) -> None:
        self._plugins = tuple(sorted(plugins, key=lambda item: (item.descriptor.priority, item.descriptor.id)))
        self._benchmark = benchmark
        self._continue_on_error = continue_on_error

    @property
    def name(self) -> str:
        return "scheduler"

    def infer(
        self,
        prepared_frame: PreparedFrame,
        context: InferenceContext,
    ) -> InferenceResult:
        started = time.monotonic()
        detections: list[Detection] = []
        attachments: dict[str, object] = {}
        backend_names: list[str] = []
        inference_ms = 0.0
        failures: dict[str, str] = {}

        for plugin in self._plugins:
            plugin_started = time.monotonic()
            try:
                result = plugin.backend.infer(prepared_frame, context)
            except Exception as exc:
                elapsed_ms = (time.monotonic() - plugin_started) * 1_000
                self._benchmark.record_plugin(plugin.descriptor.id, elapsed_ms, error=True)
                failures[plugin.descriptor.id] = str(exc)
                LOGGER.exception(
                    "Plugin %s failed; run_id=%s",
                    plugin.descriptor.id,
                    context.run_id,
                )
                if not self._continue_on_error:
                    raise
                continue
            elapsed_ms = (time.monotonic() - plugin_started) * 1_000
            self._benchmark.record_plugin(plugin.descriptor.id, elapsed_ms)
            detections.extend(result.detections)
            inference_ms += result.metrics.inference_ms
            backend_names.append(result.backend)
            attachments[plugin.descriptor.id] = dict(result.attachments)

        if failures:
            attachments["failures"] = failures
        total_ms = (time.monotonic() - started) * 1_000
        return InferenceResult(
            frame=prepared_frame.frame,
            detections=tuple(detections),
            metrics=InferenceMetrics(inference_ms=inference_ms, detection_count=len(detections)),
            latency_ms=total_ms,
            backend="scheduler:" + ",".join(backend_names),
            attachments=attachments,
        )

    def release(self) -> None:
        for plugin in reversed(self._plugins):
            release = getattr(plugin.backend, "release", None)
            if callable(release):
                try:
                    release()
                except Exception:
                    LOGGER.exception("Plugin %s release failed", plugin.descriptor.id)
