"""Explicit RC17 approval; writes a calibration artifact and a separate active profile."""

from __future__ import annotations

import argparse
import copy
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from src.engine.calibration import sha256_file, write_json_atomic
from src.engine.gallery import FaceGallery
from src.engine.gallery.persistence import GalleryPersistence


class CalibrationApprovalError(ValueError):
    pass


def approve(
    report_path: Path, threshold: float, ambiguity_margin: float | None,
    gallery_manifest: Path, gallery_archive: Path, safe_profile: Path,
    artifact_path: Path, active_profile_path: Path,
) -> tuple[dict[str, object], dict[str, object]]:
    if artifact_path.exists() or active_profile_path.exists():
        raise CalibrationApprovalError(
            "approval targets already exist; overwrite is never implicit")
    if not report_path.is_file():
        raise CalibrationApprovalError("source report does not exist")
    if not math.isfinite(threshold) or not -1 <= threshold <= 1:
        raise CalibrationApprovalError("threshold must be finite and within -1..1")
    if ambiguity_margin is not None and (
        not math.isfinite(ambiguity_margin) or not 0 <= ambiguity_margin <= 2
    ):
        raise CalibrationApprovalError("ambiguity margin must be finite and within 0..2")
    report_bytes_hash = sha256_file(report_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if not report.get("candidate_supported"):
        raise CalibrationApprovalError("report does not support threshold approval")
    if threshold not in report.get("supported_thresholds", []):
        raise CalibrationApprovalError("threshold is not an exactly supported candidate")
    gallery = FaceGallery()
    GalleryPersistence(enabled=True).import_into(gallery, gallery_manifest, gallery_archive)
    templates = gallery.templates()
    if not templates:
        raise CalibrationApprovalError("reference gallery is empty")
    first = templates[0].template
    actual = (first.model, first.model_version, first.weights_sha256)
    expected = (report.get("model_name"), report.get("model_version"),
                report.get("weights_sha256"))
    if actual != expected or any(
        (item.template.model, item.template.model_version, item.template.weights_sha256) != actual
        for item in templates
    ):
        raise CalibrationApprovalError("model provenance changed after analysis")
    row = next(item for item in report["threshold_matrix"]
               if item["threshold"] == threshold)
    artifact = {
        "schema_version": 1, "model_name": actual[0], "model_version": actual[1],
        "weights_sha256": actual[2],
        "dataset_summary": {
            "reference_identities": report["reference_identities"],
            "reference_templates": report["reference_templates"],
            "genuine_sessions": report["genuine_sessions"],
            "impostor_subjects": report["impostor_subjects"],
            "coverage": report["coverage"],
        },
        "selected_threshold": threshold,
        "selected_ambiguity_margin": ambiguity_margin,
        "estimated_far": row["far"], "estimated_frr": row["frr"],
        "estimated_tar": row["tar"],
        "distribution_margin": report["distribution_margin"],
        "genuine_sample_count": report["genuine_samples"],
        "impostor_sample_count": report["impostor_samples"],
        "source_report_sha256": report_bytes_hash,
        "approved_at": datetime.now(timezone.utc).isoformat(),
        "policy_version": report["policy"]["policy_version"],
    }
    profile = copy.deepcopy(json.loads(safe_profile.read_text(encoding="utf-8")))
    if profile["matcher"].get("automatic_decision_enabled") or \
            profile["matcher"].get("threshold") is not None:
        raise CalibrationApprovalError("safe profile FaceMatcher must remain non-deciding")
    profile["profile_name"] = "local_face_validation_pc_recognition"
    profile["recognition_calibration_file"] = str(artifact_path)
    profile["recognition"].update({
        "automatic_decision_enabled": True, "match_threshold": threshold,
        "ambiguity_margin": ambiguity_margin, "policy_name": "rc17_recognition_approved",
        "policy_version": report["policy"]["policy_version"],
    })
    write_json_atomic(artifact_path, artifact)
    write_json_atomic(active_profile_path, profile)
    return artifact, profile


def main() -> int:
    parser = argparse.ArgumentParser(description="Approve an RC17 threshold explicitly")
    parser.add_argument("--source-report", type=Path, required=True)
    parser.add_argument("--threshold", type=float, required=True)
    parser.add_argument("--ambiguity-margin", type=float)
    parser.add_argument("--gallery-manifest", type=Path, required=True)
    parser.add_argument("--gallery-archive", type=Path, required=True)
    parser.add_argument("--safe-profile", type=Path,
                        default=Path("config/local_face_validation.pc.json"))
    parser.add_argument("--artifact", type=Path,
                        default=Path("config/recognition_calibration.pc.json"))
    parser.add_argument("--active-profile", type=Path,
                        default=Path("config/local_face_validation.pc.recognition.json"))
    parser.add_argument("--confirm", required=True,
                        help='Must be exactly "APPROVE RC17"')
    args = parser.parse_args()
    if args.confirm != "APPROVE RC17":
        raise CalibrationApprovalError("explicit approval confirmation is required")
    artifact, _ = approve(
        args.source_report, args.threshold, args.ambiguity_margin,
        args.gallery_manifest, args.gallery_archive, args.safe_profile,
        args.artifact, args.active_profile)
    print(json.dumps(artifact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
