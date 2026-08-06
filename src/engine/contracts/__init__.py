"""Public contracts for inference components."""

from src.engine.contracts.detection import BoundingBox, Detection, InferenceResult
from src.engine.contracts.detector import Detector, InferenceBackend
from src.engine.contracts.frame import Frame
from src.engine.contracts.inference_context import InferenceContext
from src.engine.contracts.metrics import InferenceMetrics, PipelineMetrics
from src.engine.contracts.prepared_frame import PreparedFrame

__all__ = [
    "BoundingBox",
    "Detection",
    "Detector",
    "Frame",
    "InferenceBackend",
    "InferenceContext",
    "InferenceMetrics",
    "InferenceResult",
    "PipelineMetrics",
    "PreparedFrame",
]
