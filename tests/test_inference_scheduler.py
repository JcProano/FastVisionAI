from __future__ import annotations

import unittest

import numpy as np

from src.camera.frame import Frame
from src.engine.benchmark.manager import BenchmarkManager
from src.engine.capabilities.contracts import Capability
from src.engine.contracts.detection import InferenceResult
from src.engine.contracts.inference_context import InferenceContext
from src.engine.contracts.metrics import InferenceMetrics
from src.engine.plugins.contracts import LoadedPlugin, PluginDescriptor
from src.engine.preprocessor import MinimalPreprocessor
from src.engine.scheduler.inference_scheduler import InferenceScheduler


class RecordingBackend:
    def __init__(self, name: str, calls: list[str], fail: bool = False) -> None:
        self._name = name
        self.calls = calls
        self.fail = fail

    @property
    def name(self) -> str:
        return self._name

    def infer(self, prepared_frame, context: InferenceContext) -> InferenceResult:
        self.calls.append(self.name)
        if self.fail:
            raise RuntimeError(f"{self.name} failed")
        return InferenceResult(
            frame=prepared_frame.frame,
            detections=(),
            metrics=InferenceMetrics(),
            latency_ms=0,
            backend=self.name,
            attachments={"run_id": context.run_id},
        )


def descriptor(plugin_id: str, priority: int) -> PluginDescriptor:
    return PluginDescriptor(
        id=plugin_id,
        name=plugin_id,
        version="1",
        api_version="1.0",
        author="test",
        description="test",
        backend="test",
        capabilities=(Capability("testing", "development", True),),
        priority=priority,
        enabled=True,
    )


class InferenceSchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        image = np.zeros((20, 30, 3), dtype=np.uint8)
        self.frame = Frame.create(
            image,
            sequence_id=1,
            source_name="test",
            monotonic_timestamp=0,
            connection_id=1,
        )
        self.prepared = MinimalPreprocessor().prepare(self.frame)

    def test_executes_by_priority_and_aggregates_attachments(self) -> None:
        calls: list[str] = []
        plugins = (
            LoadedPlugin(descriptor("late", 20), RecordingBackend("late", calls)),
            LoadedPlugin(descriptor("early", 10), RecordingBackend("early", calls)),
        )
        benchmark = BenchmarkManager()
        result = InferenceScheduler(plugins, benchmark).infer(
            self.prepared, InferenceContext(run_id="run-1")
        )
        self.assertEqual(calls, ["early", "late"])
        self.assertIs(result.frame, self.frame)
        self.assertEqual(result.backend, "scheduler:early,late")
        self.assertEqual(result.attachments["early"], {"run_id": "run-1"})
        self.assertEqual(len(benchmark.snapshot().plugins), 2)

    def test_plugin_failure_is_recorded_and_next_plugin_runs(self) -> None:
        calls: list[str] = []
        plugins = (
            LoadedPlugin(descriptor("bad", 1), RecordingBackend("bad", calls, fail=True)),
            LoadedPlugin(descriptor("good", 2), RecordingBackend("good", calls)),
        )
        benchmark = BenchmarkManager()
        result = InferenceScheduler(plugins, benchmark, continue_on_error=True).infer(
            self.prepared, InferenceContext(run_id="failure-run")
        )
        self.assertEqual(calls, ["bad", "good"])
        self.assertIn("bad", result.attachments["failures"])
        bad = next(item for item in benchmark.snapshot().plugins if item.plugin_id == "bad")
        self.assertEqual(bad.errors, 1)


if __name__ == "__main__":
    unittest.main()
