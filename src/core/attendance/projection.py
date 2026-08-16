"""Read-only local-day projections over the immutable attendance event ledger."""
from __future__ import annotations
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .contracts import (
    AttendanceDayRecord, AttendanceDayStatus, AttendanceEventType,
    AttendanceMonthlyPersonSummary, AttendanceRecord, AttendanceTodaySummary,
)
from .policy import AttendancePolicy

_INS = {AttendanceEventType.CHECK_IN, AttendanceEventType.MANUAL_CHECK_IN}
_OUTS = {AttendanceEventType.CHECK_OUT, AttendanceEventType.MANUAL_CHECK_OUT}
_MANUAL = {AttendanceEventType.MANUAL_CHECK_IN, AttendanceEventType.MANUAL_CHECK_OUT}


def project_days(rows: tuple[AttendanceRecord, ...], policy: AttendancePolicy,
                 *, today: date | None = None) -> tuple[AttendanceDayRecord, ...]:
    zone = ZoneInfo(policy.timezone); grouped: dict[tuple[str, date], list[AttendanceRecord]] = {}
    for row in rows:
        grouped.setdefault((row.person_id, row.timestamp.astimezone(zone).date()), []).append(row)
    projected = tuple(_day(person_id, day, tuple(sorted(items, key=lambda x: (x.timestamp, getattr(x,"attendance_id","")))),
                           policy, today=today)
                      for (person_id, day), items in grouped.items())
    return tuple(sorted(projected, key=lambda item: (item.local_date, item.updated_at), reverse=True))


def _day(person_id: str, day: date, rows: tuple[AttendanceRecord, ...],
         policy: AttendancePolicy, *, today: date | None) -> AttendanceDayRecord:
    ins = tuple(row for row in rows if row.event_type in _INS)
    outs = tuple(row for row in rows if row.event_type in _OUTS)
    check_in = ins[0] if ins else None
    valid_outs = tuple(row for row in outs if check_in and row.timestamp >= check_in.timestamp)
    check_out = valid_outs[-1] if valid_outs else None
    worked = max(0, int((check_out.timestamp-check_in.timestamp).total_seconds())) if check_in and check_out else 0
    zone = ZoneInfo(policy.timezone)
    late = 0
    if check_in:
        local_in = check_in.timestamp.astimezone(zone)
        boundary = datetime.combine(day, policy.late_time, tzinfo=zone)
        late = max(0, int((local_in-boundary).total_seconds()))
    overtime = 0
    if check_out:
        local_out = check_out.timestamp.astimezone(zone)
        boundary = datetime.combine(day, policy.overtime_time, tzinfo=zone)
        overtime = max(0, int((local_out-boundary).total_seconds()))
    manual = any(row.event_type in _MANUAL for row in rows)
    if outs and not check_in: status = AttendanceDayStatus.INCOMPLETE
    elif manual: status = AttendanceDayStatus.MANUAL_ADJUSTMENT
    elif check_in and check_out: status = AttendanceDayStatus.COMPLETED
    elif today is not None and day < today: status = AttendanceDayStatus.INCOMPLETE
    elif late: status = AttendanceDayStatus.LATE
    else: status = AttendanceDayStatus.PRESENT
    return AttendanceDayRecord(
        person_id, day, None if check_in is None else check_in.timestamp,
        None if check_out is None else check_out.timestamp,
        None if check_in is None else ("MANUAL" if check_in.event_type in _MANUAL else "AUTOMATIC_FACE"),
        None if check_out is None else ("MANUAL" if check_out.event_type in _MANUAL else "AUTOMATIC_FACE"),
        worked, late, overtime, status,
        getattr(rows[0],"created_at",rows[0].timestamp),
        getattr(rows[-1],"created_at",rows[-1].timestamp),
        None if check_in is None else getattr(check_in,"camera_id",None),
        None if check_out is None else getattr(check_out,"camera_id",None),
    )


def today_summary(days: tuple[AttendanceDayRecord, ...], latest: tuple[AttendanceRecord, ...],
                  day: date) -> AttendanceTodaySummary:
    return AttendanceTodaySummary(day, len(days), sum(item.check_out_utc is not None for item in days),
        sum(item.check_in_utc is not None and item.check_out_utc is None for item in days),
        sum(item.late_seconds > 0 for item in days), latest[:5])


def monthly_summary(days: tuple[AttendanceDayRecord, ...], person_id: str,
                    year: int, month: int) -> AttendanceMonthlyPersonSummary:
    selected = tuple(item for item in days if item.person_id == person_id
                     and item.local_date.year == year and item.local_date.month == month)
    return AttendanceMonthlyPersonSummary(person_id,year,month,len(selected),
        sum(item.late_seconds>0 for item in selected),sum(item.worked_seconds for item in selected),
        sum(item.overtime_seconds for item in selected),
        sum(item.status is AttendanceDayStatus.INCOMPLETE for item in selected))
