"""Public face similarity calibration API."""

from .contracts import (
    CalibrationPolicy, CalibrationQualitySummary, CalibrationReport, CalibrationSample,
    CalibrationSampleMetadata, CalibrationWarning, DistributionStatistics, EstimatedEER,
    ThresholdRates,
)
from .service import CalibrationError, CalibrationService

__all__ = [
    "CalibrationError", "CalibrationPolicy", "CalibrationQualitySummary",
    "CalibrationReport", "CalibrationSample", "CalibrationSampleMetadata",
    "CalibrationService", "CalibrationWarning", "DistributionStatistics",
    "EstimatedEER", "ThresholdRates",
]
from .recognition import (
    RecognitionCalibrationError, RecognitionCalibrationPolicy,
    analyze_recognition_calibration, sha256_file, validate_approved_calibration,
    write_json_atomic,
)

__all__ = [
    "RecognitionCalibrationError", "RecognitionCalibrationPolicy",
    "analyze_recognition_calibration", "sha256_file", "validate_approved_calibration",
    "write_json_atomic",
]
