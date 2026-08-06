"""Protocols implemented by detectors and inference backends."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.engine.contracts.detection import Detection, InferenceResult
from src.engine.contracts.inference_context import InferenceContext
from src.engine.contracts.prepared_frame import PreparedFrame


@runtime_checkable
class Detector(Protocol):
    def detect(
        self,
        prepared_frame: PreparedFrame,
        context: InferenceContext,
    ) -> tuple[Detection, ...]: ...


@runtime_checkable
class InferenceBackend(Protocol):
    @property
    def name(self) -> str: ...

    def infer(
        self,
        prepared_frame: PreparedFrame,
        context: InferenceContext,
    ) -> InferenceResult: ...
