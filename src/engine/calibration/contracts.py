"""Compatibility exports for Biometrics calibration domain contracts."""

from src.core.biometrics.domain.calibration import (
    CalibrationDistance,
    CalibrationIllumination,
    CalibrationPolicy,
    CalibrationPose,
    CalibrationQualitySummary,
    CalibrationReport,
    CalibrationSample,
    CalibrationSampleMetadata,
    CalibrationSampleType,
    CalibrationWarning,
    DistributionStatistics,
    EstimatedEER,
    ThresholdRates,
)

__all__ = [
    name
    for name in globals()
    if name.startswith("Calibration")
    or name in {"DistributionStatistics", "EstimatedEER", "ThresholdRates"}
]
