"""Read-only consolidation over the three existing SQLite repositories."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from src.core.attendance import AttendanceEventType, AttendanceQuery
from src.core.detection_events import DetectionEventQuery, DetectionEventType

from .contracts import (
    DailyReportDTO, DateRangeDayDTO, DateRangeReportDTO, DetectionSummaryDTO,
    PersonAttendanceReportDTO, RecentAttendanceDTO, RecentDetectionDTO, ReportError,
    ReportPolicy, ReportValidationError, SystemSummaryDTO,
)

_INS = {AttendanceEventType.CHECK_IN, AttendanceEventType.MANUAL_CHECK_IN}
_OUTS = {AttendanceEventType.CHECK_OUT, AttendanceEventType.MANUAL_CHECK_OUT}


class ReportService:
    def __init__(self, people, detections, attendance, policy: ReportPolicy) -> None:
        self.people = people; self.detections = detections
        self.attendance = attendance; self.policy = policy
        self.timezone = ZoneInfo(policy.presentation_timezone)

    def daily_report(self, day: date) -> DailyReportDTO:
        start, end = self._bounds(day, day)
        try:
            stats = self.people.stats()
            detection_rows, truncated = self._detection_rows(start, end)
            counts = _detection_counts(detection_rows)
            if self.policy.presentation_timezone == "UTC":
                # The repository aggregate is UTC-day based and is exact in this case.
                summary = self.attendance.daily_summary(day)
                check_ins, check_outs = summary.total_check_ins, summary.total_check_outs
                unique_people = summary.unique_people
                first_at, last_at = summary.first_event_at, summary.last_event_at
                attendance_count = check_ins + check_outs
                attendance_truncated = False
            else:
                # A local day may cross two UTC dates, so use the exact converted bounds.
                attendance_rows, attendance_truncated = self._attendance_rows(start, end)
                check_ins = sum(r.event_type in _INS for r in attendance_rows)
                check_outs = sum(r.event_type in _OUTS for r in attendance_rows)
                unique_people = len({r.person_id for r in attendance_rows})
                ordered = sorted(r.timestamp for r in attendance_rows)
                first_at = ordered[0] if ordered else None
                last_at = ordered[-1] if ordered else None
                attendance_count = len(attendance_rows)
            return DailyReportDTO(
                day, stats.total, stats.active, stats.disabled, stats.pending_biometric,
                len(detection_rows), counts["registered"], counts["unregistered"],
                counts["multiple"], check_ins, check_outs, unique_people,
                self._local(first_at), self._local(last_at),
                len(detection_rows) + attendance_count, truncated or attendance_truncated,
            )
        except ReportValidationError: raise
        except Exception as exc: raise ReportError("daily report could not be generated") from exc

    def date_range_report(self, date_from: date, date_to: date) -> DateRangeReportDTO:
        start, end = self._bounds(date_from, date_to)
        try:
            detections, d_truncated = self._detection_rows(start, end)
            attendance, a_truncated = self._attendance_rows(start, end)
            days = []
            current = date_from
            while current <= date_to:
                local_d = [row for row in detections if self._local(row.timestamp).date() == current]
                local_a = [row for row in attendance if self._local(row.timestamp).date() == current]
                days.append(DateRangeDayDTO(
                    current, len(local_d), len({r.person_id for r in local_d if r.person_id}),
                    sum(r.event_type in _INS for r in local_a),
                    sum(r.event_type in _OUTS for r in local_a),
                ))
                current += timedelta(days=1)
            return DateRangeReportDTO(
                date_from, date_to, tuple(days), len(detections) + len(attendance),
                d_truncated or a_truncated,
            )
        except ReportValidationError: raise
        except Exception as exc: raise ReportError("date range report could not be generated") from exc

    def person_report(
        self, person_id: str, date_from: date, date_to: date,
    ) -> PersonAttendanceReportDTO:
        start, end = self._bounds(date_from, date_to)
        try:
            person = self.people.get_by_person_id(person_id)
            if person is None: raise ReportValidationError("person does not exist")
            detections, dt = self._detection_rows(start, end, person_id=person_id)
            attendance, at = self._attendance_rows(start, end, person_id=person_id)
            detection_times = sorted(row.timestamp for row in detections)
            attendance_times = sorted(row.timestamp for row in attendance)
            return PersonAttendanceReportDTO(
                person.person_id, f"{person.first_name} {person.last_name}",
                _mask(person.cedula), person.status.value, date_from, date_to,
                len(detections), self._local(detection_times[0]) if detection_times else None,
                self._local(detection_times[-1]) if detection_times else None,
                sum(r.event_type in _INS for r in attendance),
                sum(r.event_type in _OUTS for r in attendance),
                self._local(attendance_times[0]) if attendance_times else None,
                self._local(attendance_times[-1]) if attendance_times else None,
                len(detections) + len(attendance), dt or at,
            )
        except ReportValidationError: raise
        except Exception as exc: raise ReportError("person report could not be generated") from exc

    def detection_summary(self, date_from: date, date_to: date) -> DetectionSummaryDTO:
        start, end = self._bounds(date_from, date_to)
        try:
            rows, truncated = self._detection_rows(start, end)
            counts = _detection_counts(rows)
            latest = tuple(RecentDetectionDTO(
                row.event_type.value, self._local(row.timestamp), row.person_id,
                row.display_name_snapshot,
            ) for row in rows[:10])
            return DetectionSummaryDTO(
                date_from, date_to, len(rows), counts["registered"], counts["unregistered"],
                counts["multiple"], counts["incompatible"],
                len({row.person_id for row in rows if row.person_id}), latest,
                len(rows), truncated,
            )
        except ReportValidationError: raise
        except Exception as exc: raise ReportError("detection report could not be generated") from exc

    def system_summary(self, day: date) -> SystemSummaryDTO:
        daily = self.daily_report(day); start, end = self._bounds(day, day)
        try:
            detections, dt = self._detection_rows(start, end)
            attendance, at = self._attendance_rows(start, end)
            return SystemSummaryDTO(
                day, daily.registered_people, daily.active_people, daily.disabled_people,
                daily.pending_people, daily.detection_events, daily.attendance_check_ins,
                daily.attendance_check_outs, daily.unique_attendance_people,
                tuple(RecentDetectionDTO(r.event_type.value, self._local(r.timestamp),
                                         r.person_id, r.display_name_snapshot)
                      for r in detections[:10]),
                tuple(RecentAttendanceDTO(r.event_type.value, self._local(r.timestamp),
                                          r.person_id, None) for r in attendance[:10]),
                len(detections) + len(attendance), daily.truncated or dt or at,
            )
        except Exception as exc: raise ReportError("system report could not be generated") from exc

    def _bounds(self, start_day: date, end_day: date) -> tuple[datetime, datetime]:
        if start_day > end_day:
            raise ReportValidationError("date range is invalid")
        start = datetime.combine(start_day, time.min, self.timezone)
        end = datetime.combine(end_day + timedelta(days=1), time.min, self.timezone)
        return start.astimezone(timezone.utc), end.astimezone(timezone.utc)

    def _detection_rows(self, start, end, *, person_id=None):
        return self._paged(self.detections, DetectionEventQuery, start, end, person_id)

    def _attendance_rows(self, start, end, *, person_id=None):
        return self._paged(self.attendance, AttendanceQuery, start, end, person_id)

    def _paged(self, repository, query_type, start, end, person_id):
        rows = []; offset = 0; page_size = min(500, self.policy.max_rows)
        # Existing repositories use <=; one microsecond below the exclusive bound
        # faithfully represents [start, end) for their ISO microsecond timestamps.
        inclusive_end = end - timedelta(microseconds=1)
        while len(rows) < self.policy.max_rows:
            limit = min(page_size, self.policy.max_rows - len(rows))
            page = repository.query(query_type(
                date_from=start, date_to=inclusive_end, person_id=person_id,
                limit=limit, offset=offset,
            ))
            rows.extend(page); offset += len(page)
            if len(page) < limit: return tuple(rows), False
        # Probe one row to distinguish an exact complete page from truncation.
        probe = repository.query(query_type(
            date_from=start, date_to=inclusive_end, person_id=person_id,
            limit=1, offset=offset,
        ))
        return tuple(rows), bool(probe)

    def _local(self, value: datetime | None) -> datetime | None:
        return None if value is None else value.astimezone(self.timezone)


def _detection_counts(rows) -> dict[str, int]:
    return {
        "registered": sum(r.event_type is DetectionEventType.REGISTERED_CANDIDATE for r in rows),
        "unregistered": sum(r.event_type is DetectionEventType.UNREGISTERED for r in rows),
        "multiple": sum(r.event_type is DetectionEventType.MULTIPLE_FACES for r in rows),
        "incompatible": sum(r.event_type is DetectionEventType.INCOMPATIBLE for r in rows),
    }


def _mask(cedula: str | None) -> str:
    return "N/D" if not cedula else "******" + cedula[-4:]
