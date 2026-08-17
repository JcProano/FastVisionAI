"""Safe, read-only contracts for the professional operational dashboard."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class DashboardPhotoDTO:
    available: bool
    width: int = 0
    height: int = 0
    format: str = "NONE"
    image_bytes: bytes | None = field(default=None, repr=False)


@dataclass(frozen=True, slots=True)
class RecentRecognitionRowDTO:
    photo: DashboardPhotoDTO
    display_name: str
    local_time: str
    similarity: float | None


@dataclass(frozen=True, slots=True)
class RecentAttendanceRowDTO:
    photo: DashboardPhotoDTO
    display_name: str
    check_in_local: str | None
    check_out_local: str | None
    status: str


@dataclass(frozen=True, slots=True)
class DashboardLiveStateDTO:
    camera_state: str = "N/D"
    runtime_state: str = "N/D"
    recognition_state: str = "NOT_EVALUATED"
    gallery_identities: int = 0


@dataclass(frozen=True, slots=True)
class DashboardSnapshotDTO:
    people_present: int | None
    recognitions_today: int | None
    check_ins_today: int | None
    late_today: int | None
    recent_recognitions: tuple[RecentRecognitionRowDTO, ...]
    recent_attendance: tuple[RecentAttendanceRowDTO, ...]
    camera_state: str
    database_state: str
    gallery_identities: int
    recognition_state: str
    attendance_state: str
    generated_at: datetime

    def __post_init__(self) -> None:
        if len(self.recent_recognitions) > 5 or len(self.recent_attendance) > 5:
            raise ValueError("dashboard recent rows cannot exceed five")
        if self.generated_at.tzinfo is None:
            raise ValueError("dashboard generated_at must be timezone-aware")
