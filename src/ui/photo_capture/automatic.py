"""Bounded best-frame selection for automatic person-photo capture."""

from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable


@dataclass(frozen=True, slots=True)
class AutomaticPhotoPolicy:
    mode: str = "automatic"
    stability_frames: int = 5
    countdown_seconds: float = 2.0
    minimum_quality_score: float = 75.0

    def __post_init__(self) -> None:
        if self.mode not in ("automatic", "manual"):
            raise ValueError("photo_capture.mode must be automatic or manual")
        if self.stability_frames <= 0 or self.countdown_seconds < 0:
            raise ValueError("photo capture stability must be positive and countdown non-negative")
        if not 0 <= self.minimum_quality_score <= 100:
            raise ValueError("photo capture minimum quality score must be within 0..100")


@dataclass(frozen=True, slots=True)
class AutomaticPhotoState:
    observations: int
    required_observations: int
    message: str
    quality_score: float | None
    captured_bytes: bytes | None = None


class AutomaticPhotoSelector:
    """Retains at most one best candidate and accepts it after stable countdown."""

    def __init__(self, policy: AutomaticPhotoPolicy, *,
                 monotonic: Callable[[], float] = time.monotonic) -> None:
        self.policy = policy
        self._monotonic = monotonic
        self.reset()

    def reset(self) -> None:
        self.observations = 0
        self.best_bytes: bytes | None = None
        self.best_quality: float | None = None
        self._deadline: float | None = None

    def observe(self, *, valid: bool, image_bytes: bytes | None,
                quality_score: float | None, rejection_message: str) -> AutomaticPhotoState:
        if not valid or image_bytes is None:
            self.reset()
            return AutomaticPhotoState(0, self.policy.stability_frames,
                                       rejection_message, quality_score)
        self.observations += 1
        if self.best_quality is None or (quality_score is not None and quality_score > self.best_quality):
            self.best_bytes = bytes(image_bytes)
            self.best_quality = quality_score
        if self.observations < self.policy.stability_frames:
            return AutomaticPhotoState(
                self.observations, self.policy.stability_frames,
                "Buena imagen detectada." if self.observations == 1 else "No se mueva...",
                quality_score,
            )
        now = self._monotonic()
        if self._deadline is None:
            self._deadline = now + self.policy.countdown_seconds
        remaining = max(0, int(self._deadline - now + .999))
        if now < self._deadline:
            return AutomaticPhotoState(
                self.observations, self.policy.stability_frames,
                f"Capturando automáticamente en {remaining}...", quality_score,
            )
        captured = self.best_bytes
        best_quality = self.best_quality
        self.reset()
        return AutomaticPhotoState(
            self.policy.stability_frames, self.policy.stability_frames,
            "Fotografía capturada.", best_quality, captured,
        )
