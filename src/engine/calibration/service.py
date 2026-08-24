"""Legacy facade for the explicit biometric-calibration use case."""

from __future__ import annotations

from typing import Mapping, Sequence

from src.core.biometrics.application import CalibrateBiometricsUseCase
from src.core.biometrics.domain.calibration import (
    CalibrationError,
    CalibrationPolicy,
    CalibrationReport,
    CalibrationSample,
)
from src.core.biometrics.infrastructure import NumpyCalibrationAnalyzer


class CalibrationService:
    def __init__(self, policy: CalibrationPolicy | None = None) -> None:
        self.policy = policy or CalibrationPolicy()
        self._use_case = CalibrateBiometricsUseCase(
            NumpyCalibrationAnalyzer(self.policy)
        )

    def calibrate(
        self,
        embedding_groups: Mapping[str, Sequence[CalibrationSample]],
        thresholds: Sequence[float],
        run_id: str,
        *,
        synthetic_validation: bool = False,
    ) -> CalibrationReport:
        return self._use_case.execute(
            embedding_groups,
            thresholds,
            run_id,
            synthetic_validation=synthetic_validation,
        )


__all__ = ["CalibrationError", "CalibrationService"]
