"""Professional local dashboard presentation contracts and projections."""

from .contracts import (
    DashboardConfigurationDTO, DashboardEventDTO, DashboardGalleryDTO,
    DashboardMetricsDTO, DashboardMetricState, DashboardQualityDTO,
    DashboardQualityMetricDTO, DashboardRecognitionDTO, DashboardSystemDTO,
)
from .state import DashboardStateStore
from .professional_contracts import *
from .professional_controller import ProfessionalDashboardController
from .refresh_coordinator import DashboardRefreshCoordinator

__all__ = [
    "DashboardConfigurationDTO", "DashboardEventDTO", "DashboardGalleryDTO",
    "DashboardMetricsDTO", "DashboardMetricState", "DashboardQualityDTO",
    "DashboardQualityMetricDTO", "DashboardRecognitionDTO", "DashboardStateStore",
    "DashboardSystemDTO",
    "DashboardPhotoDTO", "RecentRecognitionRowDTO", "RecentAttendanceRowDTO",
    "DashboardLiveStateDTO", "DashboardSnapshotDTO",
    "ProfessionalDashboardController", "DashboardRefreshCoordinator",
]
