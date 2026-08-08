"""Professional local dashboard presentation contracts and projections."""

from .contracts import (
    DashboardConfigurationDTO, DashboardEventDTO, DashboardGalleryDTO,
    DashboardMetricsDTO, DashboardMetricState, DashboardQualityDTO,
    DashboardQualityMetricDTO, DashboardRecognitionDTO, DashboardSystemDTO,
)
from .state import DashboardStateStore

__all__ = [
    "DashboardConfigurationDTO", "DashboardEventDTO", "DashboardGalleryDTO",
    "DashboardMetricsDTO", "DashboardMetricState", "DashboardQualityDTO",
    "DashboardQualityMetricDTO", "DashboardRecognitionDTO", "DashboardStateStore",
    "DashboardSystemDTO",
]
