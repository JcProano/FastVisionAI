import unittest
from datetime import date, datetime, timezone
from types import SimpleNamespace

from src.core.attendance import AttendanceDailySummary, AttendanceEventType
from src.core.detection_events import DetectionEventType
from src.core.person_database import PersonStatus
from src.core.reports import ReportError, ReportPolicy, ReportService, ReportValidationError


class Repo:
    def __init__(self, rows=()): self.rows = tuple(rows); self.queries = []; self.writes = 0
    def query(self, query):
        self.queries.append(query)
        values = [row for row in self.rows
                  if (query.date_from is None or row.timestamp >= query.date_from)
                  and (query.date_to is None or row.timestamp <= query.date_to)
                  and (query.person_id is None or row.person_id == query.person_id)]
        return tuple(values[query.offset:query.offset + query.limit])
    def create(self, *_): self.writes += 1
    update = delete = set_status = create


class People(Repo):
    def __init__(self, person=None): super().__init__(); self.person = person; self.stats_calls = 0
    def stats(self):
        self.stats_calls += 1
        return SimpleNamespace(total=3, active=1, disabled=1, pending_biometric=1)
    def get_by_person_id(self, person_id): return self.person


def detection(moment, kind=DetectionEventType.UNREGISTERED, person_id=None):
    return SimpleNamespace(timestamp=moment, event_type=kind, person_id=person_id,
                           display_name_snapshot=None)


def attendance(moment, kind=AttendanceEventType.CHECK_IN, person_id="p"):
    return SimpleNamespace(timestamp=moment, event_type=kind, person_id=person_id)


class AttendanceRepo(Repo):
    def __init__(self, rows=()): super().__init__(rows); self.summary_calls = 0
    def daily_summary(self, day):
        self.summary_calls += 1
        return AttendanceDailySummary(day, 1, 2, 1, None, None)


class ReportServiceTests(unittest.TestCase):
    def service(self, detections=(), attendance_rows=(), person=None, max_rows=5000,
                timezone_name="America/Guayaquil"):
        people = People(person); det = Repo(detections); att = AttendanceRepo(attendance_rows)
        return ReportService(people, det, att, ReportPolicy(
            max_rows=max_rows, presentation_timezone=timezone_name,
        )), people, det, att

    def test_daily_empty_uses_stats_and_attendance_summary(self):
        service, people, _, attendance_repo = self.service(timezone_name="UTC")
        result = service.daily_report(date(2026, 1, 1))
        self.assertEqual(
            (result.detection_events, result.active_people, result.disabled_people,
             result.pending_people), (0, 1, 1, 1),
        )
        self.assertEqual((people.stats_calls, attendance_repo.summary_calls), (1, 1))

    def test_local_midnight_uses_exclusive_utc_bounds(self):
        rows = (
            detection(datetime(2026, 1, 1, 4, 59, 59, tzinfo=timezone.utc)),
            detection(datetime(2026, 1, 1, 5, 0, 0, tzinfo=timezone.utc)),
            detection(datetime(2026, 1, 2, 4, 59, 59, 999999, tzinfo=timezone.utc)),
            detection(datetime(2026, 1, 2, 5, 0, 0, tzinfo=timezone.utc)),
        )
        service, _, repository, _ = self.service(rows)
        result = service.daily_report(date(2026, 1, 1))
        self.assertEqual(result.detection_events, 2)
        query = repository.queries[0]
        self.assertEqual(query.date_from, datetime(2026, 1, 1, 5, tzinfo=timezone.utc))
        self.assertLess(query.date_to, datetime(2026, 1, 2, 5, tzinfo=timezone.utc))

    def test_detection_aggregation_person_mask_and_range(self):
        moment = datetime(2026, 1, 1, 15, tzinfo=timezone.utc)
        rows = (detection(moment, DetectionEventType.REGISTERED_CANDIDATE, "p"),
                detection(moment, DetectionEventType.MULTIPLE_FACES))
        person = SimpleNamespace(person_id="p", first_name="Test", last_name="Person",
                                 cedula="1710034065", status=PersonStatus.ACTIVE)
        service, *_ = self.service(rows, (attendance(moment),), person)
        summary = service.detection_summary(date(2026, 1, 1), date(2026, 1, 1))
        self.assertEqual((summary.registered_candidates, summary.multiple_faces), (1, 1))
        report = service.person_report("p", date(2026, 1, 1), date(2026, 1, 1))
        self.assertEqual(report.masked_cedula, "******4065")
        self.assertEqual(report.detection_count, 1)
        self.assertEqual(len(service.date_range_report(date(2026, 1, 1), date(2026, 1, 2)).days), 2)

    def test_pagination_and_truncation(self):
        moment = datetime(2026, 1, 1, 15, tzinfo=timezone.utc)
        service, _, repository, _ = self.service(
            tuple(detection(moment) for _ in range(601)), max_rows=550,
        )
        result = service.detection_summary(date(2026, 1, 1), date(2026, 1, 1))
        self.assertEqual(result.rows_considered, 550); self.assertTrue(result.truncated)
        self.assertEqual([q.offset for q in repository.queries], [0, 500, 550])

    def test_invalid_range_failure_and_no_writes(self):
        service, people, detections, attendance_repo = self.service()
        with self.assertRaises(ReportValidationError):
            service.date_range_report(date(2026, 2, 1), date(2026, 1, 1))
        self.assertEqual((people.writes, detections.writes, attendance_repo.writes), (0, 0, 0))
        people.stats = lambda: (_ for _ in ()).throw(OSError())
        with self.assertRaises(ReportError): service.daily_report(date(2026, 1, 1))


if __name__ == "__main__": unittest.main()
