"""Anti-repetition controller for safe experimental identification presentation."""

from __future__ import annotations

import time
import threading
from datetime import datetime, timezone
from typing import Callable

from src.ui.contracts import MonitoringDTO, UIState

from .contracts import (
    IdentificationPopupDTO, IdentificationPopupPolicy, IdentificationPopupType,
    IdentityInfoProvider,
)


class IdentificationPresentationController:
    def __init__(
        self, policy: IdentificationPopupPolicy, provider: IdentityInfoProvider, *,
        monotonic: Callable[[], float] = time.monotonic,
        utcnow: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.policy = policy
        self.provider = provider
        self._monotonic = monotonic
        self._utcnow = utcnow
        self._stable_key: tuple[str, str | None] | None = None
        self._stable_frames = 0
        self._registered_last: dict[str, float] = {}
        self._unknown_last = float("-inf")
        self._suspended = False
        self._registered_paused_until = float("-inf")
        self._lock = threading.RLock()

    def suspend(self) -> None:
        with self._lock:
            self._suspended = True
            self._reset_stability()

    def resume(self) -> None:
        with self._lock:
            self._suspended = False
            self._reset_stability()

    def unknown_dismissed(self) -> None:
        """Start unknown cooldown only after its presentation has closed."""
        with self._lock:
            self._unknown_last = self._monotonic()
            self._reset_stability()

    def registered_pause_remaining_seconds(self) -> float:
        """Return the monotonic presentation pause without altering camera/runtime."""
        with self._lock:
            return max(0.0, self._registered_paused_until - self._monotonic())

    def clear_registered_pause(self) -> None:
        with self._lock:
            self._registered_paused_until = float("-inf")
            self._reset_stability()

    def observe(self, event: MonitoringDTO) -> IdentificationPopupDTO:
        with self._lock:
            return self._observe_locked(event)

    def observe_action(
        self, action: str, person_id: str | None, recognition_state: str,
        similarity: float | None, message: str | None = None,
    ) -> IdentificationPopupDTO:
        """Consume a PII-free executor request; provider resolution stays here."""
        if action == "SHOW_REGISTERED_POPUP":
            if person_id is None:
                raise ValueError("registered popup action requires person_id")
            event = MonitoringDTO(
                UIState.MONITORING, message or "Candidato experimental", "candidate",
                similarity, "deshabilitada / NOT_EVALUATED", True,
                recognition_state=recognition_state, candidate_person_id=person_id,
            )
        elif action == "SHOW_UNREGISTERED_POPUP":
            if person_id is not None:
                raise ValueError("unregistered popup action requires no person_id")
            event = MonitoringDTO(
                UIState.MONITORING, message or "Sin candidato registrado", None,
                similarity, "deshabilitada / NOT_EVALUATED", True,
                recognition_state=recognition_state,
            )
        else:
            raise ValueError("unsupported popup action")
        with self._lock:
            return self._observe_locked(event, message)

    def _observe_locked(
        self, event: MonitoringDTO, message: str | None = None,
    ) -> IdentificationPopupDTO:
        if not self.policy.enabled or self._suspended:
            return self._suppressed(event, "Presentación suspendida")
        if self._monotonic() < self._registered_paused_until:
            self._reset_stability()
            return self._suppressed(event, "Reconocimiento temporalmente pausado")
        if event.state in {UIState.NO_FACE, UIState.MULTIPLE_FACES}:
            self._reset_stability()
            return self._suppressed(event, "Se requiere exactamente un rostro")

        registered = (
            event.recognition_state == "NOT_EVALUATED"
            and event.candidate_person_id is not None
            and event.candidate_display_name is not None
        )
        unregistered = (
            event.candidate_person_id is None
            and event.recognition_state in {
                "UNKNOWN", "NO_GALLERY", "INCOMPATIBLE", "NOT_EVALUATED",
            }
        )
        if not registered and not unregistered:
            self._reset_stability()
            return self._suppressed(event, "Estado no presentable")

        key = ("registered", event.candidate_person_id) if registered else (
            "unregistered", event.recognition_state,
        )
        if key != self._stable_key:
            self._stable_key = key
            self._stable_frames = 1
        else:
            self._stable_frames += 1
        if self._stable_frames < self.policy.candidate_stability_frames:
            return self._suppressed(event, "Esperando estabilidad")

        now = self._monotonic()
        if registered:
            assert event.candidate_person_id is not None
            previous = self._registered_last.get(event.candidate_person_id, float("-inf"))
            if now - previous < self.policy.registered_cooldown_seconds:
                return self._suppressed(event, "Cooldown activo")
            person = self.provider.get_person(event.candidate_person_id)
            if person is None:
                return self._suppressed(event, "La persona ya no está disponible")
            thumbnail = self.provider.get_thumbnail(event.candidate_person_id)
            self._registered_last[event.candidate_person_id] = now
            self._registered_paused_until = now + self.policy.registered_pause_seconds
            self._reset_stability()
            return IdentificationPopupDTO(
                IdentificationPopupType.REGISTERED_CANDIDATE,
                person.person_id, person.display_name, person.external_identifier,
                event.similarity, "NOT_EVALUATED", thumbnail.available,
                "Candidato experimental registrado", self._utcnow(),
                getattr(person, "address", None), getattr(person, "phone", None),
                getattr(person, "email", None), getattr(person, "status", None),
            )

        if now - self._unknown_last < self.policy.unknown_cooldown_seconds:
            return self._suppressed(event, "Cooldown activo")
        return IdentificationPopupDTO(
            IdentificationPopupType.UNREGISTERED, None, None, None, None,
            event.recognition_state, False,
            message or "No existe una identidad local disponible para este rostro.",
            self._utcnow(),
        )

    def _suppressed(self, event: MonitoringDTO, message: str) -> IdentificationPopupDTO:
        return IdentificationPopupDTO(
            IdentificationPopupType.SUPPRESSED, None, None, None, None,
            event.recognition_state, False, message, self._utcnow(),
        )

    def _reset_stability(self) -> None:
        self._stable_key = None
        self._stable_frames = 0
