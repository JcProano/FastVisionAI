"""Shared, non-biometric identification presentation semantics for every UI."""
from __future__ import annotations

from enum import Enum


class IdentificationVisualState(str, Enum):
    IDENTIFIED = "IDENTIFIED"
    BIOMETRIC_CANDIDATE = "BIOMETRIC_CANDIDATE"
    UNREGISTERED = "UNREGISTERED"
    NOT_PRESENTABLE = "NOT_PRESENTABLE"


def identification_visual_state(
    recognition_state: object, evaluated: object, candidate_person_id: object,
) -> IdentificationVisualState:
    """Classify presentation state without interpreting top-1 or similarity."""
    state = str(recognition_state).upper()
    if state == "MATCH" and evaluated is True and candidate_person_id is not None:
        return IdentificationVisualState.IDENTIFIED
    if state == "NOT_EVALUATED" and evaluated is False and candidate_person_id is not None:
        return IdentificationVisualState.BIOMETRIC_CANDIDATE
    if state == "UNKNOWN" and evaluated is True and candidate_person_id is None:
        return IdentificationVisualState.UNREGISTERED
    return IdentificationVisualState.NOT_PRESENTABLE


def is_confirmed_match(
    recognition_state: object, evaluated: object, candidate_person_id: object,
) -> bool:
    return identification_visual_state(
        recognition_state, evaluated, candidate_person_id,
    ) is IdentificationVisualState.IDENTIFIED
