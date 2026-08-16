"""Safe UI projections for detection history."""
from dataclasses import dataclass
from src.core.detection_events import DetectionEventDTO
from src.ui.identification import IdentityPersonDTO
from src.ui.thumbnails import ThumbnailDTO


@dataclass(frozen=True, slots=True)
class DetectionHistoryDTO:
    events: tuple[DetectionEventDTO, ...]
    total: int
    message: str


@dataclass(frozen=True, slots=True)
class DetectionHistoryOperationDTO:
    success: bool
    operation: str
    message: str
    affected: int = 0


@dataclass(frozen=True, slots=True)
class DetectionHistoryDetailDTO:
    event: DetectionEventDTO
    person: IdentityPersonDTO | None
    thumbnail: ThumbnailDTO | None
