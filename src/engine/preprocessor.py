"""Minimal model-independent frame preprocessor."""

from __future__ import annotations

from src.engine.contracts.frame import Frame
from src.engine.contracts.prepared_frame import PreparedFrame


class InvalidFrameError(ValueError):
    pass


class MinimalPreprocessor:
    def prepare(self, frame: Frame) -> PreparedFrame:
        image = frame.image
        if image is None or getattr(image, "size", 0) == 0:
            raise InvalidFrameError(f"Frame {frame.sequence_id} has an empty image")
        shape = getattr(image, "shape", ())
        if len(shape) < 2 or int(shape[0]) <= 0 or int(shape[1]) <= 0:
            raise InvalidFrameError(f"Frame {frame.sequence_id} has invalid dimensions")
        return PreparedFrame(
            frame=frame,
            image=image,
            width=int(shape[1]),
            height=int(shape[0]),
        )
