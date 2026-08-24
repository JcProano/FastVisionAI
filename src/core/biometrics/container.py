"""Composition container for biometric recognition and enrollment adapters."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from src.engine.calibration import validate_approved_calibration
from src.engine.enrollment import EnrollmentPolicy, EnrollmentService
from src.engine.gallery import FaceGallery, FaceMatcher, MatchPolicy
from src.engine.recognition import RecognitionPolicy, RecognitionService

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class BiometricsComponents:
    gallery: FaceGallery
    recognition: RecognitionService
    enrollment: EnrollmentService
    calibration_invalid: bool


class BiometricsContainer:
    @staticmethod
    def build(
        config: dict[str, object],
        project_root: Path,
        gallery: FaceGallery | None = None,
    ) -> BiometricsComponents:
        enrollment_config = config["enrollment"]
        recognition_config = config["recognition"]
        matcher_config = config["matcher"]
        if not isinstance(enrollment_config, dict):
            raise ValueError("enrollment configuration must be an object")
        if not isinstance(recognition_config, dict):
            raise ValueError("recognition configuration must be an object")
        if not isinstance(matcher_config, dict):
            raise ValueError("matcher configuration must be an object")
        gallery = gallery if gallery is not None else FaceGallery()
        automatic = bool(
            recognition_config.get("automatic_decision_enabled")
        )
        if not automatic and (
            recognition_config.get("match_threshold") is not None
            or recognition_config.get("ambiguity_margin") is not None
        ):
            raise ValueError(
                "disabled recognition requires null threshold and ambiguity_margin"
            )
        calibration_invalid = False
        if automatic:
            calibration_file = config.get("recognition_calibration_file")
            try:
                if not isinstance(calibration_file, str) or not calibration_file.strip():
                    raise ValueError("missing calibration file")
                calibration_path = Path(calibration_file)
                if not calibration_path.is_absolute():
                    calibration_path = project_root / calibration_path
                validate_approved_calibration(
                    calibration_path, gallery, recognition_config
                )
            except Exception:
                LOGGER.error(
                    "RECONOCIMIENTO DESACTIVADO — CALIBRACIÓN INVÁLIDA"
                )
                automatic = False
                calibration_invalid = True
        matcher = FaceMatcher(
            top_k=int(matcher_config["top_k"]),
            policy=MatchPolicy(
                automatic_decision_enabled=False, threshold=None
            ),
        )
        recognition_policy = RecognitionPolicy(
            automatic_decision_enabled=automatic,
            match_threshold=(
                recognition_config.get("match_threshold")
                if automatic
                else None
            ),
            ambiguity_margin=(
                recognition_config.get("ambiguity_margin")
                if automatic
                else None
            ),
            top_k=int(recognition_config["top_k"]),
            minimum_quality_score=recognition_config[
                "minimum_quality_score"
            ],
            allow_low_quality=bool(
                recognition_config["allow_low_quality"]
            ),
            policy_name=str(recognition_config["policy_name"]),
            policy_version=str(recognition_config["policy_version"]),
        )
        recognition = RecognitionService(gallery, matcher, recognition_policy)
        enrollment_policy = EnrollmentPolicy(
            min_templates=int(enrollment_config["min_templates"]),
            max_templates=int(enrollment_config["max_templates"]),
            allow_low_quality=bool(enrollment_config["allow_low_quality"]),
            min_pairwise_similarity=enrollment_config[
                "min_pairwise_similarity"
            ],
            max_pairwise_similarity=enrollment_config[
                "max_pairwise_similarity"
            ],
            reject_exact_duplicates=bool(
                enrollment_config["reject_exact_duplicates"]
            ),
        )
        enrollment = EnrollmentService(gallery, enrollment_policy)
        return BiometricsComponents(
            gallery, recognition, enrollment, calibration_invalid
        )
