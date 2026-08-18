"""Generate the non-activating RC17 recognition report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.engine.calibration import (
    RecognitionCalibrationPolicy, analyze_recognition_calibration, write_json_atomic,
)
from src.engine.gallery import FaceGallery
from src.engine.gallery.persistence import GalleryPersistence
from src.validation.analyze_face_calibration import load_calibration_input


def main() -> int:
    parser = argparse.ArgumentParser(
        description="RC17 reference/evaluation analysis; never activates recognition")
    parser.add_argument("--gallery-manifest", type=Path, required=True)
    parser.add_argument("--gallery-archive", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--policy-file", type=Path,
                        default=Path("config/recognition_calibration_policy.pc.json"))
    parser.add_argument("--minimum-genuine-samples", type=int,
                        default=None)
    parser.add_argument("--minimum-genuine-sessions", type=int,
                        default=None)
    parser.add_argument("--minimum-impostor-samples", type=int,
                        default=None)
    parser.add_argument("--minimum-impostor-subjects", type=int,
                        default=None)
    parser.add_argument("--maximum-far", type=float, default=None)
    parser.add_argument("--maximum-frr", type=float, default=None)
    parser.add_argument("--minimum-distribution-margin", type=float,
                        default=None)
    args = parser.parse_args()
    gallery = FaceGallery()
    GalleryPersistence(enabled=True).import_into(
        gallery, args.gallery_manifest, args.gallery_archive)
    raw_policy = json.loads(args.policy_file.read_text(encoding="utf-8"))
    names = (
        "minimum_genuine_samples", "minimum_genuine_sessions",
        "minimum_impostor_samples", "minimum_impostor_subjects", "maximum_far",
        "maximum_frr", "minimum_distribution_margin",
    )
    values = {name: (getattr(args, name) if getattr(args, name) is not None
                     else raw_policy[name]) for name in names}
    policy = RecognitionCalibrationPolicy(
        **values, policy_version=str(raw_policy["policy_version"]))
    report = analyze_recognition_calibration(
        gallery, load_calibration_input(args.evaluation), policy)
    write_json_atomic(args.output, report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
