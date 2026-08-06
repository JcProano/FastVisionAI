"""Analyze an explicitly persisted calibration dataset without identity decisions."""

from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import asdict
from pathlib import Path

from src.core.config_manager import PROJECT_ROOT
from src.engine.calibration.contracts import CalibrationPolicy
from src.engine.calibration.dataset import CalibrationDatasetStore
from src.engine.calibration.service import CalibrationService


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze face calibration similarities")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--thresholds", type=float, nargs="+", required=True)
    parser.add_argument("--max-impostor-pairs", type=int)
    parser.add_argument("--impostor-sampling-seed", type=int, default=0)
    args = parser.parse_args()
    root = args.input if args.input.is_absolute() else PROJECT_ROOT / args.input
    groups = CalibrationDatasetStore(enabled=True).load(
        root / "manifest.json", root / "embeddings.npz"
    )
    policy = CalibrationPolicy(
        max_impostor_pairs=args.max_impostor_pairs,
        impostor_sampling_seed=args.impostor_sampling_seed,
    )
    report = CalibrationService(policy).calibrate(
        groups, args.thresholds, f"calibration-analysis-{uuid.uuid4()}",
        synthetic_validation=False,
    )
    # asdict(report) contains statistics and provenance only, never vectors.
    print(json.dumps(asdict(report), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
