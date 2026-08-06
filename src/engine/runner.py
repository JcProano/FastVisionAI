"""Limited, headless synthetic demonstration of the initial AI pipeline."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict

import numpy as np

from src.camera.frame import Frame
from src.core.config_manager import PROJECT_ROOT, load_config
from src.core.logger import configure_logging
from src.engine.ai_manager import AIManager
from src.engine.benchmark.manager import BenchmarkManager
from src.engine.contracts.inference_context import InferenceContext
from src.engine.plugins.manager import PluginManager
from src.engine.preprocessor import MinimalPreprocessor
from src.engine.scheduler.inference_scheduler import InferenceScheduler
from src.engine.events.bus import EventBus
from src.engine.runtime.model_runtime import ModelRuntime
from src.engine.runtime.registry import RuntimeRegistry
from src.engine.models.manager import ModelManager
from src.engine.plugins.services import PluginServices


def run(frame_count: int | None = None) -> int:
    config = load_config()
    configure_logging(config.log_level, config.log_file)
    count = config.pipeline.synthetic_frame_count if frame_count is None else frame_count
    benchmark = BenchmarkManager()
    model_manager = ModelManager(PROJECT_ROOT)
    plugin_manager = PluginManager(
        PluginServices(model_manager),
        tuple((PROJECT_ROOT / directory).resolve() for directory in config.pipeline.plugins.directories),
    )
    plugin_manager.discover()
    enabled = {
        plugin.id: plugin.settings
        for plugin in config.pipeline.plugins.plugins
        if plugin.enabled
    }
    priorities = {plugin.id: plugin.priority for plugin in config.pipeline.plugins.plugins}
    plugin_manager.configure(enabled, priorities)
    scheduler = InferenceScheduler(
        plugin_manager.load_enabled(),
        benchmark,
        continue_on_error=config.pipeline.plugins.continue_on_error,
    )
    event_bus = EventBus()
    runtime_registry = RuntimeRegistry()
    runtime_registry.register("scheduler", lambda _settings: scheduler)
    runtime = ModelRuntime(
        runtime_registry,
        config.pipeline.runtime.name,
        config.pipeline.runtime.settings,
        event_bus,
        model_manager,
    )
    runtime.prepare()
    manager = AIManager(
        config.pipeline.queue,
        MinimalPreprocessor(),
        runtime,
        context=InferenceContext(),
        benchmark=benchmark,
    )
    manager.start()
    accepted = 0
    started = time.monotonic()
    for sequence_id in range(1, count + 1):
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        frame = Frame.create(
            image,
            sequence_id=sequence_id,
            source_name="synthetic",
            monotonic_timestamp=time.monotonic(),
            connection_id=1,
        )
        accepted += int(manager.submit(frame))

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        processed = manager.pipeline_metrics().frames_processed
        dropped = manager.queue_metrics().frames_dropped
        if processed + dropped >= accepted:
            break
        time.sleep(0.01)
    clean_stop = manager.stop()
    runtime.release()
    model_manager.unload_all()
    output = {
        "requested_frames": count,
        "accepted_frames": accepted,
        "elapsed_ms": round((time.monotonic() - started) * 1_000, 3),
        "clean_stop": clean_stop,
        "pipeline": asdict(manager.pipeline_metrics()),
        "queue": asdict(manager.queue_metrics()),
        "benchmark": asdict(benchmark.snapshot()),
        "runtime_state": runtime.state.value,
    }
    print(json.dumps(output, indent=2))
    return 0 if clean_stop else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthetic FastVisionAI pipeline demo")
    parser.add_argument("--frames", type=int, default=None)
    args = parser.parse_args()
    if args.frames is not None and args.frames < 0:
        parser.error("--frames must be non-negative")
    return run(args.frames)


if __name__ == "__main__":
    raise SystemExit(main())
