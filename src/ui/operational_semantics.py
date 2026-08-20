"""Shared operational presentation precedence for Tk and Web dashboards."""
from __future__ import annotations

from enum import Enum


class OperationalPresentationState(str, Enum):
    CAMERA_DISCONNECTED = "CAMERA_DISCONNECTED"
    VIDEO_NO_SIGNAL = "VIDEO_NO_SIGNAL"
    NO_FACE = "NO_FACE"
    RECOGNITION_UNAVAILABLE = "RECOGNITION_UNAVAILABLE"
    GALLERY_EMPTY = "GALLERY_EMPTY"
    GALLERY_UNREGISTERED = "GALLERY_UNREGISTERED"
    RECOGNITION_RESULT = "RECOGNITION_RESULT"


OPERATIONAL_TITLES = {
    OperationalPresentationState.CAMERA_DISCONNECTED: "CÁMARA DESCONECTADA",
    OperationalPresentationState.VIDEO_NO_SIGNAL: "VIDEO SIN SEÑAL",
    OperationalPresentationState.NO_FACE: "SIN ROSTRO",
    OperationalPresentationState.RECOGNITION_UNAVAILABLE:
        "RECONOCIMIENTO NO DISPONIBLE / ESPERANDO ROSTRO VÁLIDO",
    OperationalPresentationState.GALLERY_EMPTY: "GALERÍA VACÍA",
    OperationalPresentationState.GALLERY_UNREGISTERED: "PERSONA NO REGISTRADA",
}


def operational_presentation_state(
    *, camera_state: object, frame_available: bool, monitoring: object,
    gallery_identity_count: int,
) -> OperationalPresentationState:
    """Resolve operational UI state before interpreting recognition output."""
    camera = str(camera_state).strip().upper()
    connected = camera in {"CONNECTED", "CONNECTADA", "CONECTADA", "RUNNING", "OPEN"}
    if not connected:
        return OperationalPresentationState.CAMERA_DISCONNECTED
    if not frame_available:
        return OperationalPresentationState.VIDEO_NO_SIGNAL
    ui_state = str(getattr(getattr(monitoring, "state", None), "value",
                           getattr(monitoring, "state", ""))).upper()
    if ui_state == "NO_FACE":
        return OperationalPresentationState.NO_FACE
    recognition = str(getattr(monitoring, "recognition_state", "")).upper()
    if recognition == "NO_GALLERY":
        valid_single_face = ui_state == "MONITORING"
        return (OperationalPresentationState.GALLERY_UNREGISTERED
                if gallery_identity_count == 0 and valid_single_face
                else OperationalPresentationState.GALLERY_EMPTY
                if gallery_identity_count == 0
                else OperationalPresentationState.RECOGNITION_UNAVAILABLE)
    if (recognition in {"", "NOT_EVALUATED"}
            and getattr(monitoring, "candidate_person_id", None) is None):
        return OperationalPresentationState.RECOGNITION_UNAVAILABLE
    return OperationalPresentationState.RECOGNITION_RESULT


def operational_title(state: OperationalPresentationState) -> str | None:
    return OPERATIONAL_TITLES.get(state)
