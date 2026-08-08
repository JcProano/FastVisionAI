"""Thread-safe tracker for one camera/session observation sequence."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable

from .contracts import (
    StabilityObservation, StabilityPolicy, StabilityResult, StabilityState,
    StabilityValidationError,
)


class StabilityTracker:
    def __init__(
        self, policy: StabilityPolicy, *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.policy = policy
        self._monotonic = monotonic
        self._lock = threading.RLock()
        self._candidate: str | None = None
        self._count = 0
        self._first_seen: float | None = None
        self._last_seen: float | None = None
        self._similarities: list[float] = []
        self._last_input_timestamp: float | None = None
        self._result = self._empty("disabled" if not policy.enabled else "no_observation")

    def observe(self, observation: StabilityObservation) -> StabilityResult:
        with self._lock:
            timestamp = (
                observation.timestamp_monotonic
                if observation.timestamp_monotonic is not None else self._monotonic()
            )
            if timestamp < 0:
                raise StabilityValidationError("monotonic timestamp is invalid")
            if self._last_input_timestamp is not None and timestamp < self._last_input_timestamp:
                raise StabilityValidationError("monotonic timestamp moved backwards")
            if not self.policy.enabled:
                self._last_input_timestamp = timestamp
                self._result = self._empty("disabled")
                return self._result

            # Validation and timestamp checks happen before any sequence mutation.
            self._last_input_timestamp = timestamp
            if observation.face_count == 0:
                state = StabilityState.LOST if self._candidate is not None else StabilityState.NO_OBSERVATION
                person_id = self._candidate
                self._clear_sequence()
                self._result = self._empty(
                    "observation_lost" if state is StabilityState.LOST else "no_observation",
                    state=state, person_id=person_id,
                )
                return self._result
            if observation.face_count > 1:
                if self.policy.reset_on_multiple_faces:
                    self._clear_sequence()
                self._result = self._result_for(
                    StabilityState.MULTIPLE_FACES, observation.similarity,
                    "multiple_faces",
                )
                return self._result
            if observation.recognition_state == "INCOMPATIBLE":
                self._clear_sequence()
                self._result = self._empty(
                    "incompatible_observation", state=StabilityState.INCOMPATIBLE,
                )
                return self._result
            if observation.person_id is None:
                state = StabilityState.LOST if self._candidate is not None else StabilityState.NO_OBSERVATION
                person_id = self._candidate
                self._clear_sequence()
                self._result = self._empty(
                    "candidate_unavailable", state=state, person_id=person_id,
                )
                return self._result
            if (
                self.policy.minimum_similarity is not None
                and observation.similarity is not None
                and observation.similarity < self.policy.minimum_similarity
            ):
                self._clear_sequence()
                self._result = self._empty(
                    "similarity_below_stability_minimum",
                    state=StabilityState.STABILIZING,
                    person_id=observation.person_id,
                    current_similarity=observation.similarity,
                )
                return self._result

            if self._candidate is not None and observation.person_id != self._candidate:
                # Candidate observations never transfer between people. The new candidate
                # is seeded even when reset_on_candidate_change is false; that flag is
                # retained for policy compatibility, while isolation is mandatory.
                self._seed(observation.person_id, timestamp, observation.similarity)
                changed = self._result_for(
                    StabilityState.CHANGED, observation.similarity, "candidate_changed",
                )
                self._result = self._result_for(
                    StabilityState.STABILIZING, observation.similarity, "stabilizing",
                )
                return changed

            if (
                self._last_seen is not None
                and timestamp - self._last_seen > self.policy.maximum_gap_seconds
            ):
                self._seed(observation.person_id, timestamp, observation.similarity)
                self._result = self._result_for(
                    StabilityState.STABILIZING, observation.similarity,
                    "continuity_gap_reset",
                )
                return self._result

            if self._candidate is None:
                self._seed(observation.person_id, timestamp, observation.similarity)
            else:
                self._count += 1
                self._last_seen = timestamp
                if observation.similarity is not None:
                    self._similarities.append(observation.similarity)
            duration = self._duration()
            stable = (
                self._count >= self.policy.minimum_observations
                and duration >= self.policy.minimum_duration_seconds
            )
            self._result = self._result_for(
                StabilityState.STABLE if stable else StabilityState.STABILIZING,
                observation.similarity,
                "temporal_continuity_stable" if stable else "stabilizing",
            )
            return self._result

    def reset(self) -> StabilityResult:
        with self._lock:
            self._clear_sequence()
            self._last_input_timestamp = None
            self._result = self._empty("reset")
            return self._result

    def snapshot(self) -> StabilityResult:
        with self._lock:
            return self._result

    def _seed(self, person_id: str, timestamp: float, similarity: float | None) -> None:
        self._candidate = person_id
        self._count = 1
        self._first_seen = timestamp
        self._last_seen = timestamp
        self._similarities = [] if similarity is None else [similarity]

    def _clear_sequence(self) -> None:
        self._candidate = None
        self._count = 0
        self._first_seen = None
        self._last_seen = None
        self._similarities.clear()

    def _duration(self) -> float:
        if self._first_seen is None or self._last_seen is None:
            return 0.0
        return max(0.0, self._last_seen - self._first_seen)

    def _result_for(
        self, state: StabilityState, current_similarity: float | None, reason: str,
    ) -> StabilityResult:
        average = (
            sum(self._similarities) / len(self._similarities)
            if self._similarities else None
        )
        return StabilityResult(
            state, self._candidate, self._count, self._duration(), current_similarity,
            average, min(self._similarities) if self._similarities else None,
            max(self._similarities) if self._similarities else None,
            self._first_seen, self._last_seen, reason,
            self.policy.policy_name, self.policy.policy_version,
        )

    def _empty(
        self, reason: str, *, state: StabilityState = StabilityState.NO_OBSERVATION,
        person_id: str | None = None, current_similarity: float | None = None,
    ) -> StabilityResult:
        return StabilityResult(
            state, person_id, 0, 0.0, current_similarity, None, None, None,
            None, None, reason, self.policy.policy_name, self.policy.policy_version,
        )
