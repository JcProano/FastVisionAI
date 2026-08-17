import dataclasses
import inspect
import unittest
from concurrent.futures import Future
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from src.core.application_events import (
    ApplicationEventBus, AttendanceRecordedEvent, DetectionEventStoredEvent,
)
from src.ui.dashboard import DashboardRefreshCoordinator, ProfessionalDashboardController
from src.ui.dashboard.professional_contracts import DashboardLiveStateDTO
from src.ui.thumbnails import ThumbnailDTO
from src.ui.tk_app import LocalFaceTkApp


NOW=datetime(2026,1,5,13,0,tzinfo=timezone.utc)


class FixedClock:
    def utc_now(self):return NOW
    def local_today(self,_zone):return date(2026,1,5)
    def local_day_utc_bounds(self,_day,_zone):return NOW.replace(hour=5),NOW.replace(hour=5)+__import__('datetime').timedelta(days=1)


class DashboardFakes:
    def __init__(self,thumbnail=True):
        self.recognitions=tuple(SimpleNamespace(person_id=f"p{i}",display_name=f"Persona {i}",timestamp=NOW,similarity=.9) for i in range(7))
        self.days=tuple(SimpleNamespace(person_id=f"p{i}",display_name=f"Persona {i}",check_in=NOW,check_out=None,status="PRESENT") for i in range(7))
        self.detection=SimpleNamespace(list=lambda **_kwargs:SimpleNamespace(events=self.recognitions[:5]))
        summary=SimpleNamespace(present=4,late=2)
        self.attendance=SimpleNamespace(day_list=lambda **_kwargs:SimpleNamespace(days=self.days),attendance_today=lambda:summary,
            service=SimpleNamespace(policy=SimpleNamespace(automatic_attendance_enabled=True)))
        daily=SimpleNamespace(registered_candidate_events=11,attendance_check_ins=6)
        self.reports=SimpleNamespace(service=SimpleNamespace(daily_report=lambda _day:daily))
        self.identity=SimpleNamespace(get_thumbnail=lambda person_id:ThumbnailDTO(person_id,thumbnail,1 if thumbnail else 0,1 if thumbnail else 0,"PNG",b"x" if thumbnail else None))
        self.health=SimpleNamespace(snapshot=lambda:SimpleNamespace(components=(SimpleNamespace(component="events_database",level=SimpleNamespace(value="OK")),)))


class ProfessionalDashboardControllerTests(unittest.TestCase):
    def controller(self,thumbnail=True,authorization=None):
        values=DashboardFakes(thumbnail)
        return ProfessionalDashboardController(values.detection,values.attendance,values.reports,
            values.identity,authorization,values.health,clock=FixedClock()),values

    def test_statistics_recent_limits_statuses_and_missing_thumbnail(self):
        controller,_=self.controller(False)
        value=controller.snapshot(DashboardLiveStateDTO("CONNECTED","RUNNING","MATCHED",9),refresh_statistics=True)
        self.assertEqual((value.people_present,value.recognitions_today,value.check_ins_today,value.late_today),(4,11,6,2))
        self.assertEqual((len(value.recent_recognitions),len(value.recent_attendance)),(5,5))
        self.assertFalse(value.recent_recognitions[0].photo.available)
        self.assertEqual((value.camera_state,value.recognition_state,value.attendance_state),("Conectada","Activo","Activa"))

    def test_camera_recognition_attendance_variants_and_degraded_health(self):
        controller,values=self.controller();values.attendance.service.policy.automatic_attendance_enabled=False
        values.health.snapshot=lambda:SimpleNamespace(components=(SimpleNamespace(component="attendance_database",level=SimpleNamespace(value="ERROR")),))
        value=controller.snapshot(DashboardLiveStateDTO("RECONNECTING","STOPPED","PAUSED",0),refresh_statistics=True)
        self.assertEqual((value.camera_state,value.database_state,value.recognition_state,value.attendance_state),("Reconectando","Degradada","Pausado","Desactivada"))
        stopped=controller.snapshot(DashboardLiveStateDTO("DISCONNECTED","STOPPED","NOT_EVALUATED",0),refresh_statistics=True)
        self.assertEqual((stopped.camera_state,stopped.recognition_state),("Desconectada","Detenido"))

    def test_rbac_and_dto_have_no_biometric_or_internal_identity_fields(self):
        denied=SimpleNamespace(can=lambda permission:permission.value=="VIEW_DASHBOARD")
        controller,_=self.controller(authorization=denied)
        value=controller.snapshot(DashboardLiveStateDTO(),refresh_statistics=True)
        self.assertEqual(value.recent_recognitions,())
        self.assertIsNone(value.people_present)
        names={field.name for cls in (type(value),)+tuple(type(item) for item in value.recent_recognitions) for field in dataclasses.fields(cls)}
        self.assertFalse(names&{"embedding","template","frame","person_id","path","url"})
        forbidden=SimpleNamespace(can=lambda _permission:False)
        controller,_=self.controller(authorization=forbidden)
        with self.assertRaises(PermissionError):controller.snapshot(DashboardLiveStateDTO(),refresh_statistics=True)


class FakeRoot:
    def __init__(self):self.callbacks={};self.cancelled=[];self.next=0;self.attributes_calls=[]
    def after(self,delay,callback):self.next+=1;self.callbacks[self.next]=(delay,callback);return self.next
    def after_cancel(self,value):self.cancelled.append(value);self.callbacks.pop(value,None)
    def run(self,identifier=None):
        key=identifier or min(self.callbacks);_delay,callback=self.callbacks.pop(key);callback()
    def attributes(self,*values):self.attributes_calls.append(values)


class ControlledExecutor:
    def __init__(self):self.futures=[];self.calls=0;self.closed=False
    def submit(self,fn,*args,**kwargs):self.calls+=1;future=Future();future.set_running_or_notify_cancel();self.futures.append((future,fn,args,kwargs));return future
    def complete(self,index=0):
        future,fn,args,kwargs=self.futures[index];future.set_result(fn(*args,**kwargs))
    def shutdown(self,**_kwargs):self.closed=True


class RefreshCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.root=FakeRoot();self.executor=ControlledExecutor();self.clock=[0.0]
        controller,_=ProfessionalDashboardControllerTests().controller()
        self.values=[];self.coordinator=DashboardRefreshCoordinator(self.root,controller,
            lambda:DashboardLiveStateDTO("CONNECTED","RUNNING","MATCHED",2),self.values.append,
            dashboard_seconds=5,statistics_seconds=10,monotonic=lambda:self.clock[0],executor=self.executor)

    def test_single_inflight_slow_query_does_not_accumulate_and_frequencies(self):
        self.coordinator.start();self.root.run();self.assertEqual(self.executor.calls,1)
        self.root.run();self.assertEqual(self.executor.calls,1)
        self.executor.complete();self.root.run();self.assertEqual(len(self.values),1)
        delay=next(iter(self.root.callbacks.values()))[0];self.assertEqual(delay,5000)
        self.clock[0]=5;self.root.run();self.assertEqual(self.executor.calls,2)
        self.assertFalse(self.executor.futures[1][3]["refresh_statistics"])
        self.executor.complete(1);self.root.run();self.clock[0]=10;self.root.run()
        self.assertTrue(self.executor.futures[2][3]["refresh_statistics"])

    def test_events_only_invalidate_and_close_is_idempotent_with_no_callback(self):
        bus=ApplicationEventBus();bus.subscribe(DetectionEventStoredEvent,self.coordinator.invalidate);bus.subscribe(AttendanceRecordedEvent,self.coordinator.invalidate)
        self.coordinator.start();self.root.run();self.assertEqual(self.executor.calls,1)
        bus.publish(DetectionEventStoredEvent(source="test",detection_event_id="e",person_id="p",detection_event_type="REGISTERED_CANDIDATE",camera_id="camera",recorded=True,timestamp=NOW))
        bus.publish(AttendanceRecordedEvent(source="test",attendance_id="a",person_id="p",attendance_event_type="CHECK_IN",camera_id="camera",source_event_id="e",timestamp=NOW))
        self.assertTrue(self.coordinator.invalidated);self.assertEqual(self.executor.calls,1)
        self.coordinator.close();self.coordinator.close();self.executor.complete()
        self.assertEqual(self.values,[]);self.assertTrue(self.executor.closed)

    def test_failure_preserves_snapshot_and_marks_database_degraded(self):
        self.coordinator.start();self.root.run();self.executor.complete();self.root.run()
        previous=self.values[-1];self.clock[0]=5;self.root.run()
        future,_,_,_=self.executor.futures[1];future.set_exception(RuntimeError("private"));self.root.run()
        self.assertEqual(self.values[-1].database_state,"Degradada")
        self.assertEqual(self.values[-1].recent_recognitions,previous.recent_recognitions)


class DashboardTkBehaviorTests(unittest.TestCase):
    def test_fullscreen_f11_escape_and_responsive_grid_are_declared(self):
        app=LocalFaceTkApp.__new__(LocalFaceTkApp);app.root=FakeRoot();app._fullscreen=False
        self.assertEqual(app.toggle_fullscreen(),"break");self.assertTrue(app._fullscreen)
        self.assertEqual(app.exit_fullscreen(),"break");self.assertFalse(app._fullscreen)
        source=inspect.getsource(LocalFaceTkApp.__init__)
        self.assertIn('root.bind("<F11>"',source);self.assertIn('root.bind("<Escape>"',source)
        self.assertIn("columnconfigure",source);self.assertIn("rowconfigure",source)


if __name__=="__main__":unittest.main()
