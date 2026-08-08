from __future__ import annotations
import time,uuid
from datetime import datetime,timezone
from typing import Callable
from src.core.person_database import PersonRepository,PersonStatus
from .contracts import *
from .policy import AttendancePolicy
from .repository import AttendanceRepository

class AttendanceService:
    def __init__(self,repository:AttendanceRepository,people:PersonRepository,policy:AttendancePolicy,*,monotonic:Callable[[],float]=time.monotonic,utcnow:Callable[[],datetime]=lambda:datetime.now(timezone.utc)):
        self.repository=repository;self.people=people;self.policy=policy;self._monotonic=monotonic;self._utcnow=utcnow;self._observations={}
    def manual_check_in(self,person_id,**kwargs):return self._manual(person_id,AttendanceEventType.MANUAL_CHECK_IN,**kwargs)
    def manual_check_out(self,person_id,**kwargs):return self._manual(person_id,AttendanceEventType.MANUAL_CHECK_OUT,**kwargs)
    def _manual(self,person_id,event_type,*,timestamp=None,camera_id=None,notes=None):
        if not self.policy.enabled:return AttendanceOperationResult(False,False,"attendance_disabled")
        if not self.policy.allow_manual_events:return AttendanceOperationResult(False,False,"manual_events_disabled")
        if not self._active(person_id):return AttendanceOperationResult(False,False,"person_not_active")
        moment=timestamp or self._utcnow(); latest=self.repository.query(AttendanceQuery(person_id=person_id,event_type=event_type,limit=1))
        if latest and (moment-latest[0].timestamp).total_seconds()<self.policy.duplicate_event_cooldown_seconds:return AttendanceOperationResult(False,False,"duplicate_cooldown")
        try:
            record=AttendanceRecord(str(uuid.uuid4()),person_id,event_type,moment,None,camera_id,None,self._utcnow(),notes);self.repository.create(record)
            return AttendanceOperationResult(True,True,"recorded",record)
        except Exception:return AttendanceOperationResult(False,False,"persistence_error")
    def evaluate_observation(self,person_id,*,source_event_id=None,camera_id=None,timestamp=None):
        if not self.policy.enabled:return AttendanceEvaluationResult(False,None,"attendance_disabled",False)
        if not self.policy.automatic_attendance_enabled:return AttendanceEvaluationResult(False,None,"automatic_attendance_disabled",False)
        if not self._active(person_id):return AttendanceEvaluationResult(False,None,"person_not_active",True)
        now=self._monotonic();first,count=self._observations.get(person_id,(now,0));count+=1;self._observations[person_id]=(first,count)
        latest=self.repository.latest_for_person(person_id); proposed=_next(latest.event_type if latest else None)
        if count<self.policy.minimum_stable_observations or now-first<self.policy.minimum_observation_seconds:return AttendanceEvaluationResult(False,proposed,"observation_not_stable",True)
        moment=timestamp or self._utcnow()
        if latest and (moment-latest.timestamp).total_seconds()<self.policy.minimum_time_between_check_in_out_seconds:return AttendanceEvaluationResult(False,proposed,"minimum_interval",True)
        try:
            record=AttendanceRecord(str(uuid.uuid4()),person_id,proposed,moment,source_event_id,camera_id,None,self._utcnow());self.repository.create(record);self._observations.pop(person_id,None)
            return AttendanceEvaluationResult(True,proposed,"recorded",True,record)
        except Exception:return AttendanceEvaluationResult(False,proposed,"persistence_error",True)
    def _active(self,person_id):
        try:r=self.people.get_by_person_id(person_id);return r is not None and r.status is PersonStatus.ACTIVE
        except Exception:return False
def _next(last):
    if last in {AttendanceEventType.CHECK_IN,AttendanceEventType.MANUAL_CHECK_IN}:return AttendanceEventType.CHECK_OUT
    return AttendanceEventType.CHECK_IN

