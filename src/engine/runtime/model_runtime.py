from __future__ import annotations

import time
from dataclasses import replace
from enum import Enum
from typing import Any, Mapping

from src.engine.contracts.detection import InferenceResult
from src.engine.contracts.inference_context import InferenceContext
from src.engine.contracts.prepared_frame import PreparedFrame
from src.engine.events.bus import InternalEventBus
from src.engine.events.contracts import InferenceEvent, RuntimeEvent
from src.engine.runtime.registry import RuntimeRegistry
from src.engine.models.manager import ModelManager


class RuntimeState(str, Enum):
    CREATED = "created"
    INITIALIZED = "initialized"
    PREPARING = "preparing"
    READY = "ready"
    RUNNING = "running"
    RELEASING = "releasing"
    RELEASED = "released"
    FAILED = "failed"


class ModelRuntime:
    def __init__(self, registry: RuntimeRegistry, runtime_name: str, settings: Mapping[str, Any] | None = None, event_bus: InternalEventBus | None = None, model_manager: ModelManager | None = None) -> None:
        self.registry = registry
        self.runtime_name = runtime_name
        self.settings = settings or {}
        self.event_bus = event_bus
        self.model_manager = model_manager
        self._model_aliases = tuple(self.settings.get("model_aliases", ()))
        self._alias_revisions: dict[str, int] = {}
        requested_device = str(self.settings.get("device", "auto"))
        self.resolved_device = "cpu" if requested_device == "auto" else requested_device
        self.state = RuntimeState.CREATED
        self._backend = None
        self.state = RuntimeState.INITIALIZED

    @property
    def name(self) -> str:
        return f"runtime:{self.runtime_name}"

    def prepare(self) -> None:
        if self.state is not RuntimeState.INITIALIZED:
            raise RuntimeError(f"Cannot prepare runtime in state {self.state.value}")
        self.state = RuntimeState.PREPARING
        try:
            self._backend = self.registry.create(self.runtime_name, self.settings)
            if self.model_manager is not None:
                self._alias_revisions = {alias: self.model_manager.alias_revision(alias) for alias in self._model_aliases}
            prepare = getattr(self._backend, "prepare", None)
            if callable(prepare):
                prepare()
            self.state = RuntimeState.READY
            self._publish(RuntimeEvent(runtime_name=self.runtime_name, state=self.state.value))
        except Exception:
            self.state = RuntimeState.FAILED
            raise

    def infer(self, prepared_frame: PreparedFrame, context: InferenceContext) -> InferenceResult:
        if self.state is not RuntimeState.READY or self._backend is None:
            raise RuntimeError(f"Runtime is not ready: {self.state.value}")
        self._invalidate_if_models_changed()
        self.state = RuntimeState.RUNNING
        started = time.monotonic()
        try:
            runtime_context = replace(context, device=self.resolved_device)
            result = self._backend.infer(prepared_frame, runtime_context)
            self.state = RuntimeState.READY
            self._publish(InferenceEvent(run_id=context.run_id, runtime_name=self.runtime_name, success=True, latency_ms=(time.monotonic() - started) * 1000))
            return result
        except Exception:
            self.state = RuntimeState.FAILED
            self._publish(InferenceEvent(run_id=context.run_id, runtime_name=self.runtime_name, success=False, latency_ms=(time.monotonic() - started) * 1000))
            raise

    def release(self) -> None:
        if self.state is RuntimeState.RELEASED:
            return
        self.state = RuntimeState.RELEASING
        release = getattr(self._backend, "release", None)
        if callable(release):
            release()
        self._backend = None
        self.state = RuntimeState.RELEASED
        self._publish(RuntimeEvent(runtime_name=self.runtime_name, state=self.state.value))

    def _publish(self, event) -> None:
        if self.event_bus is not None:
            self.event_bus.publish(event)

    def _invalidate_if_models_changed(self) -> None:
        if self.model_manager is None:
            return
        changed = any(
            self.model_manager.alias_revision(alias) != self._alias_revisions.get(alias, 0)
            for alias in self._model_aliases
        )
        if changed:
            release = getattr(self._backend, "release", None)
            if callable(release):
                release()
            self._backend = self.registry.create(self.runtime_name, self.settings)
            prepare = getattr(self._backend, "prepare", None)
            if callable(prepare):
                prepare()
            self._alias_revisions = {
                alias: self.model_manager.alias_revision(alias) for alias in self._model_aliases
            }
