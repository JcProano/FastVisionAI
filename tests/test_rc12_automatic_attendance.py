import sqlite3
import tempfile
import threading
import unittest
import uuid
import dataclasses
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from src.core.application_events import ApplicationEventBus, DetectionEventStoredEvent
from src.core.attendance import (
    AttendanceDayStatus, AttendanceEventType, AttendancePolicy, AttendanceRepository,
    AttendanceService, project_days,
)
from src.core.person_database import PersonCreateRequest, PersonRepository, PersonStatus
from src.core.detection_events import DetectionEventRepository
from src.core.reports import ReportPolicy, ReportService
from src.ui.attendance import AttendanceUIController
from src.ui.action_adapters import AutomaticAttendanceEventAdapter


class FixedClock:
    def local_day_utc_bounds(self, day, timezone_name):
        from src.core.time_provider import Clock
        return Clock().local_day_utc_bounds(day, timezone_name)


class RC12AutomaticAttendanceTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        root=Path(temporary.name);self.database=root/"attendance.db"
        self.people=PersonRepository(root/"people.db");self.people.initialize()
        self.person_id=str(uuid.uuid4())
        self.people.create(PersonCreateRequest(self.person_id,"1710034065","Ana","Activa"))
        self.people.set_status(self.person_id,PersonStatus.ACTIVE)
        self.repository=AttendanceRepository(self.database);self.repository.initialize()
        self.policy=AttendancePolicy(enabled=True,automatic_attendance_enabled=True,
            minimum_stable_observations=1,minimum_observation_seconds=0,
            duplicate_event_cooldown_seconds=60,minimum_time_between_check_in_out_seconds=300,
            policy_name="rc12_test",policy_version="1",timezone="America/Guayaquil",
            workday_start="08:00",workday_end="17:00",late_after="08:10",overtime_after="17:00")
        self.service=AttendanceService(self.repository,self.people,self.policy,clock=FixedClock())
        self.start=datetime(2026,1,5,13,0,tzinfo=timezone.utc)

    def consume(self,event_id,moment):
        return self.service.consume_detection_event(self.person_id,source_event_id=event_id,
            camera_id="Entrada principal",timestamp=moment)

    def test_toggle_too_soon_complete_and_persistent_idempotency(self):
        first=self.consume("event-1",self.start)
        self.assertEqual(first.record.event_type,AttendanceEventType.CHECK_IN)
        self.assertEqual(self.consume("event-2",self.start+timedelta(seconds=10)).reason,"duplicate_cooldown")
        second=self.consume("event-3",self.start+timedelta(minutes=5)).record
        self.assertEqual(second.event_type,AttendanceEventType.CHECK_OUT)
        self.assertEqual(self.consume("event-4",self.start+timedelta(hours=6)).reason,"day_complete")
        restarted=AttendanceService(AttendanceRepository(self.database),self.people,self.policy)
        self.assertEqual(restarted.consume_detection_event(self.person_id,source_event_id="event-1",
            timestamp=self.start).reason,"event_already_consumed")
        self.assertEqual(self.repository.count(),2)

    def test_manual_entry_coexists_and_manual_exit_without_entry_is_incomplete(self):
        self.service.manual_check_in(self.person_id,timestamp=self.start)
        result=self.consume("auto-out",self.start+timedelta(minutes=5))
        self.assertEqual(result.record.event_type,AttendanceEventType.CHECK_OUT)
        other=str(uuid.uuid4());self.people.create(PersonCreateRequest(other,"0926687856","Otra","Activa"));self.people.set_status(other,PersonStatus.ACTIVE)
        self.service.manual_check_out(other,timestamp=self.start)
        ignored=self.service.consume_detection_event(other,source_event_id="manual-order",timestamp=self.start+timedelta(minutes=10))
        self.assertEqual(ignored.reason,"manual_checkout_without_checkin")
        rows=self.repository.list(limit=100)
        projected=project_days(rows,self.policy,today=date(2026,1,5))
        broken=next(item for item in projected if item.person_id==other)
        self.assertEqual(broken.status,AttendanceDayStatus.INCOMPLETE)
        self.assertIsNone(broken.check_in_utc)

    def test_disabled_unknown_and_invalid_never_write(self):
        self.people.set_status(self.person_id,PersonStatus.DISABLED)
        self.assertEqual(self.consume("disabled",self.start).reason,"person_not_active")
        self.assertEqual(self.service.consume_detection_event("unknown",source_event_id="x",timestamp=self.start).reason,"invalid_person_id")
        self.assertEqual(self.repository.count(),0)

    def test_late_overtime_worked_and_local_day(self):
        self.consume("in",self.start+timedelta(minutes=20))
        self.consume("out",self.start+timedelta(hours=10))
        day=project_days(self.repository.list(),self.policy,today=date(2026,1,5))[0]
        self.assertEqual(day.local_date,date(2026,1,5))
        self.assertEqual(day.late_seconds,600)
        self.assertEqual(day.overtime_seconds,3600)
        self.assertEqual(day.worked_seconds,9*3600+40*60)

    def test_concurrent_events_never_duplicate_checkin(self):
        barrier=threading.Barrier(3);results=[]
        def worker(identifier):
            barrier.wait();results.append(self.consume(identifier,self.start))
        threads=[threading.Thread(target=worker,args=(f"race-{index}",)) for index in range(2)]
        for thread in threads:thread.start()
        barrier.wait()
        for thread in threads:thread.join()
        self.assertEqual(sum(row.event_type is AttendanceEventType.CHECK_IN for row in self.repository.list()),1)

    def test_adapter_only_consumes_persisted_registered_and_redacts_camera(self):
        bus=ApplicationEventBus();adapter=AutomaticAttendanceEventAdapter(self.service,bus)
        for recorded,kind,person,event_id in ((False,"REGISTERED_CANDIDATE",self.person_id,"a"),(True,"UNREGISTERED",None,"b")):
            adapter(DetectionEventStoredEvent(source="test",detection_event_id=event_id,
                person_id=person,detection_event_type=kind,camera_id="camera",recorded=recorded,timestamp=self.start))
        self.assertEqual(self.repository.count(),0)
        adapter(DetectionEventStoredEvent(source="test",detection_event_id="safe",person_id=self.person_id,
            detection_event_type="REGISTERED_CANDIDATE",camera_id="rtsp://user:secret@host/live",recorded=True,timestamp=self.start))
        self.assertNotIn("secret",self.repository.list()[0].camera_id)

    def test_schema_migrates_v1_without_rewriting_history(self):
        legacy=self.database.parent/"legacy.db";connection=sqlite3.connect(legacy)
        connection.execute("CREATE TABLE schema_version(version INTEGER NOT NULL)");connection.execute("INSERT INTO schema_version VALUES(1)")
        connection.execute("CREATE TABLE attendance_records(attendance_id TEXT PRIMARY KEY,person_id TEXT NOT NULL,event_type TEXT NOT NULL,timestamp TEXT NOT NULL,source_event_id TEXT,camera_id TEXT,session_id TEXT,created_at TEXT NOT NULL,notes TEXT)")
        connection.execute("INSERT INTO attendance_records VALUES(?,?,?,?,?,?,?,?,?)",("old",self.person_id,"CHECK_IN",self.start.isoformat(),None,None,None,self.start.isoformat(),None));connection.commit();connection.close()
        migrated=AttendanceRepository(legacy);self.assertEqual(migrated.initialize(),2)
        self.assertEqual(migrated.get_by_id("old").attendance_id,"old")
        with sqlite3.connect(legacy) as connection:self.assertIn("attendance_consumed_events",{row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")})

    def test_automatic_sqlite_failure_is_safe_and_unmarked(self):
        self.repository.consume_automatic_toggle=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("private"))
        result=self.consume("failure",self.start)
        self.assertEqual((result.eligible,result.reason),(False,"persistence_error"))
        self.assertEqual(self.repository.count(),0)

    def test_ui_filters_detail_rbac_and_safe_dto(self):
        self.consume("ui",self.start)
        controller=AttendanceUIController(self.service,self.repository,self.people)
        result=controller.day_list(day=date(2026,1,5),name="ana",cedula="1710034065",status="INCOMPLETE")
        self.assertEqual(result.total,1)
        self.assertFalse({field.name for field in dataclasses.fields(result.days[0])}&{
            "embedding","template","frame","image","thumbnail"})
        self.assertIsNotNone(controller.detail(self.person_id,date(2026,1,5)))
        controller.authorization=type("Denied",(),{"can":lambda self,_permission:False})()
        with self.assertRaises(PermissionError):controller.day_list(day=date(2026,1,5))

    def test_daily_and_monthly_reports_include_only_recorded_days(self):
        self.consume("report-in",self.start);self.consume("report-out",self.start+timedelta(hours=10))
        detection=DetectionEventRepository(self.database.parent/"events.db");detection.initialize()
        reports=ReportService(self.people,detection,self.repository,
            ReportPolicy(presentation_timezone="America/Guayaquil"),self.policy)
        daily=reports.attendance_daily_detail(date(2026,1,5))
        monthly=reports.attendance_monthly(2026,1,self.person_id)
        self.assertEqual(len(daily.days),1)
        self.assertEqual(monthly.people[0].days_present,1)
        self.assertEqual(monthly.people[0].incomplete_days,0)


if __name__=="__main__":unittest.main()
