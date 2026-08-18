"""RC17 reference/evaluation calibration without automatic threshold selection."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from src.engine.calibration.contracts import CalibrationSample, CalibrationSampleType
from src.engine.gallery import FaceGallery


class RecognitionCalibrationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RecognitionCalibrationPolicy:
    """Operational defaults; they are safeguards, not scientifically optimal values."""
    minimum_genuine_samples: int = 12
    minimum_genuine_sessions: int = 2
    minimum_impostor_samples: int = 20
    minimum_impostor_subjects: int = 2
    maximum_far: float = 0.01
    maximum_frr: float = 0.10
    minimum_distribution_margin: float = 0.02
    policy_version: str = "rc17-1.0"

    def __post_init__(self) -> None:
        if min(self.minimum_genuine_samples, self.minimum_genuine_sessions,
               self.minimum_impostor_samples, self.minimum_impostor_subjects) <= 0:
            raise ValueError("calibration minimums must be positive")
        if not 0 <= self.maximum_far <= 1 or not 0 <= self.maximum_frr <= 1:
            raise ValueError("maximum FAR/FRR must be within 0..1")
        if not -2 <= self.minimum_distribution_margin <= 2:
            raise ValueError("minimum distribution margin must be within -2..2")


def analyze_recognition_calibration(
    gallery: FaceGallery,
    groups: Mapping[str, Sequence[CalibrationSample]],
    policy: RecognitionCalibrationPolicy | None = None,
) -> dict[str, object]:
    policy = policy or RecognitionCalibrationPolicy()
    templates = gallery.templates()
    if not templates:
        raise RecognitionCalibrationError("reference gallery is empty")
    provenance = _template_provenance(templates[0].template)
    if any(_template_provenance(item.template) != provenance for item in templates):
        raise RecognitionCalibrationError("reference gallery has mixed provenance")

    identities = {item.template.identity.person_id for item in templates}
    genuine: list[float] = []
    impostor: list[float] = []
    genuine_margins: list[float] = []
    genuine_sessions: set[str] = set()
    impostor_subjects: set[str] = set()
    coverage = {"illumination": set(), "distance": set(), "pose": set()}
    sample_ids: set[str] = set()
    for subject, samples in sorted(groups.items()):
        for sample in samples:
            meta = sample.metadata
            if meta.sample_type is None:
                raise RecognitionCalibrationError("evaluation sample has no RC17 sample_type")
            if _sample_provenance(sample) != provenance:
                raise RecognitionCalibrationError("evaluation model provenance is incompatible")
            if not meta.evaluation_sample_id or meta.evaluation_sample_id in sample_ids:
                raise RecognitionCalibrationError("evaluation_sample_id is missing or duplicated")
            sample_ids.add(meta.evaluation_sample_id)
            vector = _vector(sample)
            if any(np.array_equal(vector, item.template.embedding) for item in templates):
                raise RecognitionCalibrationError(
                    "gallery template cannot be used as an evaluation sample")
            gallery_sources = {item.template.source_reference for item in templates
                               if item.template.source_reference}
            if meta.session_id in gallery_sources or meta.source_identifier in gallery_sources:
                raise RecognitionCalibrationError(
                    "evaluation session/source_reference overlaps enrollment")
            scores: dict[str, float] = {}
            for item in templates:
                identity = item.template.identity.person_id
                score = float(np.clip(np.dot(vector, item.template.embedding), -1.0, 1.0))
                scores[identity] = max(scores.get(identity, -1.0), score)
            if meta.illumination is not None:
                coverage["illumination"].add(meta.illumination.value)
            if meta.distance is not None:
                coverage["distance"].add(meta.distance.value)
            if meta.pose is not None:
                coverage["pose"].add(meta.pose.value)
            if meta.sample_type is CalibrationSampleType.GENUINE:
                if meta.expected_identity not in identities:
                    raise RecognitionCalibrationError("genuine expected_identity is not in gallery")
                genuine.append(scores[meta.expected_identity])
                genuine_sessions.add(meta.calibration_session_id or meta.session_id)
                alternatives = [value for key, value in scores.items()
                                if key != meta.expected_identity]
                if alternatives:
                    genuine_margins.append(scores[meta.expected_identity] - max(alternatives))
            else:
                impostor.append(max(scores.values()))
                impostor_subjects.add(subject)
    if not genuine:
        raise RecognitionCalibrationError("genuine evaluation samples are required")
    if not impostor:
        raise RecognitionCalibrationError("external impostor samples are required")

    minimum_genuine = min(genuine)
    maximum_impostor = max(impostor)
    distribution_margin = minimum_genuine - maximum_impostor
    thresholds = sorted(set(genuine + impostor))
    matrix = [_threshold_row(value, genuine, impostor) for value in thresholds]
    minimums_met = (
        len(genuine) >= policy.minimum_genuine_samples
        and len(genuine_sessions) >= policy.minimum_genuine_sessions
        and len(impostor) >= policy.minimum_impostor_samples
        and len(impostor_subjects) >= policy.minimum_impostor_subjects
    )
    supported = [row for row in matrix if row["far"] <= policy.maximum_far
                 and row["frr"] <= policy.maximum_frr]
    candidate_supported = bool(
        minimums_met and distribution_margin > 0
        and distribution_margin >= policy.minimum_distribution_margin and supported
    )
    missing_coverage = {
        key: sorted(expected - values) for key, (expected, values) in {
            "illumination": ({"NORMAL", "LOW", "SIDE"}, coverage["illumination"]),
            "distance": ({"NEAR", "OPERATIONAL", "FAR"}, coverage["distance"]),
            "pose": ({"FRONTAL", "SLIGHT_LEFT", "SLIGHT_RIGHT"}, coverage["pose"]),
        }.items()
    }
    report = {
        "schema_version": 1, "report_type": "RC17_RECOGNITION_CALIBRATION",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_name": provenance[1], "model_version": provenance[2],
        "weights_sha256": provenance[3], "embedding_dimension": provenance[0],
        "reference_identities": len(identities), "reference_templates": len(templates),
        "genuine_samples": len(genuine), "impostor_samples": len(impostor),
        "genuine_sessions": len(genuine_sessions),
        "impostor_subjects": len(impostor_subjects),
        "genuine_similarities": genuine, "impostor_similarities": impostor,
        "genuine_statistics": _statistics(genuine),
        "impostor_statistics": _statistics(impostor),
        "minimum_genuine_similarity": minimum_genuine,
        "maximum_impostor_similarity": maximum_impostor,
        "distribution_margin": distribution_margin,
        "ambiguity_analysis": (_statistics(genuine_margins) if len(identities) > 1 else None),
        "ambiguity_note": (None if len(identities) > 1 else
                           "N/D: one registered identity; no second-best identity exists."),
        "coverage": {key: sorted(value) for key, value in coverage.items()},
        "missing_coverage": missing_coverage,
        "policy": asdict(policy), "minimums_met": minimums_met,
        "threshold_matrix": matrix,
        "supported_thresholds": [row["threshold"] for row in supported]
                                if candidate_supported else [],
        "candidate_supported": candidate_supported,
    }
    return report


def write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    os.close(descriptor)
    temporary = Path(name)
    try:
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_approved_calibration(
    artifact_path: Path, gallery: FaceGallery, recognition: Mapping[str, object],
) -> dict[str, object]:
    try:
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RecognitionCalibrationError("CALIBRACIÓN INVÁLIDA") from exc
    templates = gallery.templates()
    if not templates:
        raise RecognitionCalibrationError("CALIBRACIÓN INVÁLIDA: gallery empty")
    first = templates[0].template
    expected = (artifact.get("model_name"), artifact.get("model_version"),
                artifact.get("weights_sha256"))
    actual = (first.model, first.model_version, first.weights_sha256)
    if actual != expected or any(
        (item.template.model, item.template.model_version, item.template.weights_sha256) != actual
        for item in templates
    ):
        raise RecognitionCalibrationError("CALIBRACIÓN INVÁLIDA: biometric provenance")
    threshold = artifact.get("selected_threshold")
    margin = artifact.get("selected_ambiguity_margin")
    if threshold is None or recognition.get("match_threshold") != threshold:
        raise RecognitionCalibrationError("CALIBRACIÓN INVÁLIDA: threshold mismatch")
    if recognition.get("ambiguity_margin") != margin:
        raise RecognitionCalibrationError("CALIBRACIÓN INVÁLIDA: ambiguity margin mismatch")
    if not artifact.get("source_report_sha256") or not artifact.get("approved_at"):
        raise RecognitionCalibrationError("CALIBRACIÓN INVÁLIDA: approval provenance")
    return artifact


def _threshold_row(threshold: float, genuine: list[float], impostor: list[float]):
    tp = sum(value >= threshold for value in genuine)
    fn = len(genuine) - tp
    fp = sum(value >= threshold for value in impostor)
    tn = len(impostor) - fp
    return {"threshold": threshold, "tp": tp, "fn": fn, "fp": fp, "tn": tn,
            "tar": tp / len(genuine), "frr": fn / len(genuine),
            "far": fp / len(impostor)}


def _statistics(values: list[float]) -> dict[str, object]:
    data = np.asarray(values, dtype=np.float64)
    return {"count": len(values), "minimum": float(data.min()),
            "mean": float(data.mean()), "median": float(np.median(data)),
            "maximum": float(data.max()), "standard_deviation": float(data.std()),
            "percentiles": {str(p): float(np.percentile(data, p))
                            for p in (1, 5, 25, 50, 75, 95, 99)}}


def _vector(sample: CalibrationSample) -> np.ndarray:
    value = np.asarray(sample.embedding)
    if value.dtype != np.float32 or value.ndim != 1 or not np.isfinite(value).all():
        raise RecognitionCalibrationError("invalid evaluation embedding")
    if not math.isclose(float(np.linalg.norm(value)), 1.0, abs_tol=1e-5):
        raise RecognitionCalibrationError("evaluation embedding must be L2-normalized")
    return value


def _sample_provenance(sample: CalibrationSample):
    return (_vector(sample).size, sample.metadata.model, sample.metadata.version,
            sample.metadata.weights_sha256)


def _template_provenance(template):
    return (template.dimension, template.model, template.model_version,
            template.weights_sha256)
