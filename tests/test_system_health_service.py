import unittest
from datetime import datetime,timezone
from src.core.system_health import *
class Provider:
 component="good"
 def check(self):return ComponentHealthDTO("good",HealthLevel.OK,"ok",datetime.now(timezone.utc))
class Bad:
 component="bad"
 def check(self):raise RuntimeError("internal")
class Metrics:
 def snapshot(self):return PerformanceMetricsDTO(None,None,None,None,None,None,None,datetime.now(timezone.utc))
 def observe_frame(self,_timestamp=None):pass
 def observe_counters(self,**_kwargs):pass
class ServiceTests(unittest.TestCase):
 def test_uptime_and_provider_failure_isolation(self):
  now=[10.0];service=SystemHealthService((Provider(),Bad()),Metrics(),monotonic=lambda:now[0]);now[0]=15;snapshot=service.snapshot();self.assertEqual(snapshot.uptime_seconds,5);self.assertEqual(len(snapshot.components),2);self.assertEqual(snapshot.overall_level,HealthLevel.ERROR)
 def test_external_provider_not_under_global_lock(self):
  service=SystemHealthService((Provider(),),Metrics());self.assertEqual(service.snapshot().overall_level,HealthLevel.OK)
