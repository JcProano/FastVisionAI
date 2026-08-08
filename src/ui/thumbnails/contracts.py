"""Presentation-only thumbnail contracts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ThumbnailDTO:
    person_id: str
    available: bool
    width: int
    height: int
    format: str
    image_bytes: bytes | None = None


@dataclass(frozen=True, slots=True)
class ThumbnailSample:
    """Internal, short-lived enrollment candidate; never a public UI event."""

    sample_index: int
    requested_pose: str
    quality_score: float
    image_bytes: bytes

