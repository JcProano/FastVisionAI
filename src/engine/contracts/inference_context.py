"""Extensible inference execution context."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4


@dataclass(slots=True)
class InferenceContext:
    """Reserved for future ONNX Runtime, TensorRT and DeepStream state."""

    run_id: str = ""
    device: str = "auto"

    def __post_init__(self) -> None:
        if not self.run_id:
            self.run_id = str(uuid4())
