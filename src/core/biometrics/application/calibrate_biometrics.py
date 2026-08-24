"""Use case for executing an explicit biometric calibration analysis."""

from __future__ import annotations

from typing import Mapping, Sequence

from ..domain.calibration import CalibrationReport, CalibrationSample
from ..domain.ports import CalibrationAnalyzerPort


class CalibrateBiometricsUseCase:
    def __init__(self, analyzer: CalibrationAnalyzerPort) -> None:
        self._analyzer = analyzer

    def execute(
        self,
        embedding_groups: Mapping[str, Sequence[CalibrationSample]],
        thresholds: Sequence[float],
        run_id: str,
        *,
        synthetic_validation: bool = False,
    ) -> CalibrationReport:
        return self._analyzer.calibrate(
            embedding_groups,
            thresholds,
            run_id,
            synthetic_validation=synthetic_validation,
        )
