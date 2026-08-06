"""CLI for non-decisional calibration overlap diagnostics."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from src.core.config_manager import PROJECT_ROOT
from src.engine.calibration.diagnostics import CalibrationDiagnosticService, DiagnosticPolicy
from src.validation.analyze_face_calibration import load_calibration_input


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Diagnose overlap in face calibration scores")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--near-duplicate-similarity", type=float, default=.98)
    parser.add_argument("--centroid-min-similarity", type=float, default=.20)
    parser.add_argument("--outlier-iqr-multiplier", type=float, default=1.5)
    parser.add_argument("--identity-pair-warning-similarity", type=float, default=.80)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = args.input if args.input.is_absolute() else PROJECT_ROOT / args.input
    groups = load_calibration_input(root)
    policy = DiagnosticPolicy(
        args.near_duplicate_similarity, args.centroid_min_similarity,
        args.outlier_iqr_multiplier, args.identity_pair_warning_similarity,
    )
    report = CalibrationDiagnosticService(policy).analyze(groups)
    # The report contains references, qualities and similarities, never vectors.
    print(json.dumps(asdict(report), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
