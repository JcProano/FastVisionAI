"""Injectable clock for UTC persistence and local presentation days."""
from __future__ import annotations
import time
from datetime import date,datetime,time as datetime_time,timezone
from zoneinfo import ZoneInfo

class Clock:
 def utc_now(self)->datetime:return datetime.now(timezone.utc)
 def monotonic(self)->float:return time.monotonic()
 def local_today(self,timezone_name:str)->date:return self.utc_now().astimezone(ZoneInfo(timezone_name)).date()
 def local_day_utc_bounds(self,day:date,timezone_name:str)->tuple[datetime,datetime]:
  zone=ZoneInfo(timezone_name);start=datetime.combine(day,datetime_time.min,tzinfo=zone).astimezone(timezone.utc);following=date.fromordinal(day.toordinal()+1);end=datetime.combine(following,datetime_time.min,tzinfo=zone).astimezone(timezone.utc);return start,end

