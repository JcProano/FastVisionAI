"""Small helpers shared by attendance use cases."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from ..domain.models import AttendanceEventType
from ..domain.ports import PersonReaderPort


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def is_active_person(people: PersonReaderPort, person_id: str) -> bool:
    try:
        record = people.get_by_person_id(person_id)
        if record is None:
            return False
        status = getattr(record.status, "value", record.status)
        return status == "ACTIVE"
    except Exception:
        return False


def is_canonical_uuid(value: str) -> bool:
    try:
        parsed = uuid.UUID(str(value))
        return str(parsed) == str(value).strip().lower()
    except (TypeError, ValueError, AttributeError):
        return False


def next_automatic_event(
    last: AttendanceEventType | None,
) -> AttendanceEventType:
    if last in {
        AttendanceEventType.CHECK_IN,
        AttendanceEventType.MANUAL_CHECK_IN,
    }:
        return AttendanceEventType.CHECK_OUT
    return AttendanceEventType.CHECK_IN
