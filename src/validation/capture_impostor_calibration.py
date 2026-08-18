"""Dedicated RC17 external-impostor evaluation capture command."""

from src.engine.calibration.contracts import CalibrationSampleType
from src.validation.capture_face_calibration import build_parser, run_capture


def main() -> int:
    import json
    args = build_parser(CalibrationSampleType.IMPOSTOR).parse_args()
    print(json.dumps(run_capture(args), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
