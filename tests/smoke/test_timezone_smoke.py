from __future__ import annotations
import unittest
from datetime import date,datetime,timezone
from src.core.time_provider import Clock

class FixedClock(Clock):
 def utc_now(self):return datetime(2026,1,2,2,30,tzinfo=timezone.utc)
class TimezoneSmokeTests(unittest.TestCase):
 def test_guayaquil_day_differs_safely_near_utc_midnight(self):
  clock=FixedClock();self.assertEqual(clock.local_today("America/Guayaquil"),date(2026,1,1));start,end=clock.local_day_utc_bounds(date(2026,1,1),"America/Guayaquil");self.assertEqual(start,datetime(2026,1,1,5,tzinfo=timezone.utc));self.assertEqual(end,datetime(2026,1,2,5,tzinfo=timezone.utc))

