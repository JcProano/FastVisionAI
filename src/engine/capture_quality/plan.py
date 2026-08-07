"""Deterministic operator instruction plan for guided capture."""

from __future__ import annotations

from dataclasses import dataclass

from src.engine.capture_quality.contracts import CapturePose


@dataclass(frozen=True, slots=True)
class CapturePlanStep:
    key: str
    requested_pose: CapturePose
    instruction: str


DEFAULT_STEPS = (
    CapturePlanStep("frontal", CapturePose.FRONTAL, "Mire al frente"),
    CapturePlanStep("slight_left", CapturePose.SLIGHT_LEFT,
                    "Gire ligeramente a la izquierda"),
    CapturePlanStep("slight_right", CapturePose.SLIGHT_RIGHT,
                    "Gire ligeramente a la derecha"),
    # Neutral expression is an operator instruction, not an inferred attribute.
    CapturePlanStep("frontal_neutral", CapturePose.FRONTAL,
                    "Mire al frente con expresión neutra"),
)


class GuidedCapturePlan:
    def __init__(self, target_samples: int, steps=DEFAULT_STEPS) -> None:
        if target_samples <= 0 or not steps:
            raise ValueError("guided capture plan must be finite and non-empty")
        self.target_samples = target_samples
        self.steps = tuple(steps)
        self.accepted_count = 0

    @property
    def completed(self) -> bool:
        return self.accepted_count >= self.target_samples

    @property
    def current(self) -> CapturePlanStep:
        if self.completed:
            return self.steps[(self.target_samples - 1) % len(self.steps)]
        return self.steps[self.accepted_count % len(self.steps)]

    def accept(self) -> CapturePlanStep:
        if self.completed:
            raise RuntimeError("guided capture plan is already complete")
        accepted = self.current
        self.accepted_count += 1
        return accepted

    def covered_poses(self) -> tuple[str, ...]:
        return tuple(self.steps[index % len(self.steps)].key for index in range(self.accepted_count))

