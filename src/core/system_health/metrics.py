"""Bounded monotonic rolling performance observations."""
from __future__ import annotations
import sys,threading,time
from collections import deque
from datetime import datetime,timezone
from .contracts import PerformanceMetricsDTO

class RollingPerformanceMetrics:
 def __init__(self,window_seconds:float=5.0,*,monotonic=time.monotonic,utcnow=lambda:datetime.now(timezone.utc),memory_reader=None):
  if window_seconds<=0:raise ValueError("performance window must be positive")
  self.window_seconds=window_seconds;self._monotonic=monotonic;self._utcnow=utcnow;self._memory_reader=memory_reader or memory_usage_mb;self._timestamps=deque();self._queue_depth=None;self._dropped=None;self._lock=threading.RLock()
 def observe_frame(self,timestamp:float|None=None)->None:
  value=self._monotonic() if timestamp is None else timestamp
  with self._lock:self._timestamps.append(float(value));self._trim(float(value))
 def observe_counters(self,*,queue_depth:int|None,dropped_frames:int|None)->None:
  with self._lock:self._queue_depth=queue_depth;self._dropped=dropped_frames
 @property
 def last_frame_monotonic(self)->float|None:
  with self._lock:return self._timestamps[-1] if self._timestamps else None
 def snapshot(self)->PerformanceMetricsDTO:
  now=self._monotonic()
  with self._lock:
   self._trim(now);values=tuple(self._timestamps);depth=self._queue_depth;dropped=self._dropped
  intervals=[b-a for a,b in zip(values,values[1:]) if b>=a]
  fps=(len(intervals)/sum(intervals)) if intervals and sum(intervals)>0 else None
  interval=(sum(intervals)/len(intervals)*1000) if intervals else None
  try:memory=self._memory_reader()
  except Exception:memory=None
  return PerformanceMetricsDTO(fps,interval,None,None,depth,dropped,memory,self._utcnow())
 def _trim(self,now):
  cutoff=now-self.window_seconds
  while self._timestamps and self._timestamps[0]<cutoff:self._timestamps.popleft()

def memory_usage_mb()->float|None:
 try:
  import resource
  value=float(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
  if value<0:return None
  return value/(1024*1024 if sys.platform=="darwin" else 1024)
 except (ImportError,AttributeError,ValueError,OSError):return None
