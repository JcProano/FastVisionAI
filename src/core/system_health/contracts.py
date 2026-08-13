"""Safe immutable contracts for observational system health."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class HealthLevel(str,Enum):OK="OK";WARNING="WARNING";ERROR="ERROR";DISABLED="DISABLED";UNKNOWN="UNKNOWN"
@dataclass(frozen=True,slots=True)
class ComponentHealthDTO:component:str;level:HealthLevel;message:str;checked_at:datetime
@dataclass(frozen=True,slots=True)
class SystemHealthDTO:overall_level:HealthLevel;components:tuple[ComponentHealthDTO,...];uptime_seconds:float;generated_at:datetime
@dataclass(frozen=True,slots=True)
class PerformanceMetricsDTO:
 fps:float|None;frame_interval_ms:float|None;processing_latency_ms:float|None
 inference_latency_ms:float|None;queue_depth:int|None;dropped_frames:int|None
 memory_usage_mb:float|None;generated_at:datetime
