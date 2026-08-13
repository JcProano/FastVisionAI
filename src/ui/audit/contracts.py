"""Safe UI projections for administrative audit."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True,slots=True)
class AuditListDTO:
    records:tuple[object,...];total:int;message:str

@dataclass(frozen=True,slots=True)
class AuditUIResult:
    success:bool;message:str;count:int=0

@dataclass(frozen=True,slots=True)
class AuditDashboardDTO:
    total:int|None;successes:int|None;failures:int|None;latest_timestamp_utc:datetime|None

