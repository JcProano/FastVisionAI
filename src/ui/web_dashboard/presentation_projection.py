"""Projection of recognition events into safe, time-bounded web dialogs."""

from __future__ import annotations

import time

from src.ui.identification_semantics import (
    IdentificationVisualState,
    identification_visual_state,
)
from src.ui.operational_semantics import (
    OperationalPresentationState,
    operational_title,
)


class WebPresentationProjection:
    def __init__(
        self,
        *,
        presentation_provider,
        operational_state_provider,
        identity_provider,
        resources,
        monotonic=time.monotonic,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._presentation_provider = presentation_provider
        self._operational_state_provider = operational_state_provider
        self._identity_provider = identity_provider
        self._resources = resources
        self._monotonic = monotonic
        self._timeout = float(timeout_seconds)
        self._current_key = None
        self._started_at = float("-inf")
        self._dismissed_key = None

    def dismiss(self) -> None:
        self._dismissed_key = self._current_key
        self._started_at = float("-inf")

    def payload(self) -> dict[str, object]:
        dto = self._safe_presentation()
        if dto is None:
            return {"active": False}

        operational = self._operational_state(dto)
        if operational is OperationalPresentationState.GALLERY_UNREGISTERED:
            return {
                "active": False,
                "kind": "GALLERY_UNREGISTERED",
                "title": "PERSONA NO REGISTRADA",
                "name": None,
                "photo": None,
                "similarity": None,
                "status": "GALERÍA SIN IDENTIDADES",
                "warning": "No existen rostros registrados en la galería.",
                "details": [],
                "remaining_seconds": 0,
            }
        if (
            operational is not None
            and operational
            is not OperationalPresentationState.RECOGNITION_RESULT
        ):
            title = operational_title(operational)
            return {
                "active": False,
                "kind": operational.value,
                "title": title,
                "name": None,
                "photo": None,
                "similarity": None,
                "status": title,
                "warning": None,
                "details": [],
                "remaining_seconds": 0,
            }

        state = str(getattr(dto, "recognition_state", "")).upper()
        evaluated = getattr(dto, "evaluated", None)
        person_id = getattr(dto, "candidate_person_id", None)
        visual_state = identification_visual_state(
            state, evaluated, person_id
        )
        valid = (
            visual_state is not IdentificationVisualState.NOT_PRESENTABLE
            or state in {"NO_GALLERY", "INCOMPATIBLE"}
        )
        if not valid:
            return _not_evaluated_payload(dto, state)

        remaining = self._remaining_seconds((state, person_id))
        if remaining <= 0:
            return {"active": False}

        name = getattr(dto, "candidate_display_name", None)
        photo = None
        details = []
        if person_id and self._identity_provider is not None:
            token = self._resources.person_token(person_id)
            photo = f"/api/thumbnails/{token}"
        if visual_state is IdentificationVisualState.IDENTIFIED:
            person = self._identity_provider.get_person(person_id)
            if person:
                name = person.display_name
                details = _person_details(person)
            title, status, warning = (
                "PERSONA IDENTIFICADA",
                "IDENTIFICADO",
                None,
            )
        elif visual_state is IdentificationVisualState.UNREGISTERED:
            title, status, warning = (
                "PERSONA NO REGISTRADA",
                "NO REGISTRADA",
                "No existe una identidad registrada para este rostro.",
            )
            name, photo = None, None
        elif visual_state is IdentificationVisualState.BIOMETRIC_CANDIDATE:
            title, status, warning = (
                "CANDIDATO BIOMÉTRICO",
                "NO EVALUADO — SISTEMA PENDIENTE DE CALIBRACIÓN",
                "El candidato más cercano no constituye una identificación.",
            )
        elif state == "NO_GALLERY":
            title, status, warning = "GALERÍA VACÍA", "NO EVALUADO", None
        else:
            title, status, warning = (
                "MODELO BIOMÉTRICO INCOMPATIBLE",
                "NO EVALUADO",
                None,
            )

        blocking = visual_state in {
            IdentificationVisualState.IDENTIFIED,
            IdentificationVisualState.UNREGISTERED,
        }
        return {
            "active": blocking,
            "kind": state,
            "title": title,
            "name": name,
            "photo": photo,
            "similarity": getattr(dto, "similarity", None),
            "status": status,
            "warning": warning,
            "details": details,
            "remaining_seconds": remaining,
        }

    def _safe_presentation(self):
        if self._presentation_provider is None:
            return None
        try:
            return self._presentation_provider()
        except Exception:
            return None

    def _operational_state(self, dto):
        if self._operational_state_provider is None:
            return None
        return self._operational_state_provider(dto)

    def _remaining_seconds(self, key) -> float:
        now = self._monotonic()
        if key != self._current_key:
            self._current_key = key
            self._started_at = now
            if key != self._dismissed_key:
                self._dismissed_key = None
        if key == self._dismissed_key:
            return 0
        return max(0, self._timeout - (now - self._started_at))


def _not_evaluated_payload(dto, state: str) -> dict[str, object]:
    return {
        "active": False,
        "kind": state,
        "title": "NO EVALUADO",
        "name": None,
        "photo": None,
        "similarity": getattr(dto, "similarity", None),
        "status": state or "NOT_EVALUATED",
        "warning": None,
        "details": [],
        "remaining_seconds": 0,
    }


def _person_details(person) -> list[dict[str, str]]:
    fields = (
        ("Cédula", person.external_identifier),
        ("Cargo", person.position),
        ("Departamento", person.department),
        ("Empresa", person.company),
        ("Teléfono", person.phone),
        ("Correo", person.email),
    )
    return [
        {"label": label, "value": value or "N/D"} for label, value in fields
    ]
