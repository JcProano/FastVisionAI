import unittest

from src.core.biometrics.application import CalibrateBiometricsUseCase


class FakeAnalyzer:
    def __init__(self) -> None:
        self.arguments = None
        self.report = object()

    def calibrate(
        self, groups, thresholds, run_id, *, synthetic_validation=False
    ):
        self.arguments = (groups, thresholds, run_id, synthetic_validation)
        return self.report


class CalibrateBiometricsUseCaseTests(unittest.TestCase):
    def test_delegates_analysis_without_owning_numerical_infrastructure(self) -> None:
        analyzer = FakeAnalyzer()
        use_case = CalibrateBiometricsUseCase(analyzer)
        groups = {"person-1": ()}

        result = use_case.execute(
            groups, (0.7, 0.8), "run-1", synthetic_validation=True
        )

        self.assertIs(result, analyzer.report)
        self.assertEqual(
            analyzer.arguments, (groups, (0.7, 0.8), "run-1", True)
        )


if __name__ == "__main__":
    unittest.main()
