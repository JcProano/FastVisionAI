"""Frame value object produced by the Camera Engine."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class Frame:
    """One captured image and source-independent capture metadata."""

    image: Any
    sequence_id: int
    source_name: str
    captured_at: datetime
    monotonic_timestamp: float
    width: int
    height: int
    connection_id: int

    @classmethod
    def create(
        cls,
        image: Any,
        *,
        sequence_id: int,
        source_name: str,
        monotonic_timestamp: float,
        connection_id: int,
    ) -> Frame:
        """Create a Frame and derive resolution from an OpenCV-like image."""

        shape = getattr(image, "shape", ())
        height = int(shape[0]) if len(shape) >= 2 else 0
        width = int(shape[1]) if len(shape) >= 2 else 0
        return cls(
            image=image,
            sequence_id=sequence_id,
            source_name=source_name,
            captured_at=datetime.now(timezone.utc),
            monotonic_timestamp=monotonic_timestamp,
            width=width,
            height=height,
            connection_id=connection_id,
        )

