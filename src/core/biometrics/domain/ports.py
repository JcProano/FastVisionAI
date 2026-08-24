"""Framework-independent ports for biometric application workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from .calibration import CalibrationReport, CalibrationSample


class BiometricEmbeddingPort(Protocol):
    run_id: str
    face_index: int
    dimension: int
    model: str
    version: str
    weights_sha256: str
    alignment_quality: object


class FaceQualityScorePort(Protocol):
    total_score: float
    quality_band: object


class BiometricIdentityPort(Protocol):
    person_id: str
    display_name: str
    metadata: Mapping[str, Any] | None


class BiometricTemplatePort(Protocol):
    identity: BiometricIdentityPort
    dimension: int
    model: str
    model_version: str
    weights_sha256: str


class IndexedBiometricTemplatePort(Protocol):
    index: int
    template: BiometricTemplatePort
    fingerprint: str


class BiometricGalleryPort(Protocol):
    def list_identities(self) -> tuple[BiometricIdentityPort, ...]: ...
    def templates(
        self, person_id: str | None = None
    ) -> tuple[IndexedBiometricTemplatePort, ...]: ...
    def register_identity(self, identity: BiometricIdentityPort) -> None: ...
    def add_template(
        self,
        person_id: str,
        embedding: BiometricEmbeddingPort,
        source_reference: str | None = None,
    ) -> int: ...
    def remove_identity(self, person_id: str) -> bool: ...


class MatcherPolicyPort(Protocol):
    automatic_decision_enabled: bool
    threshold: float | None


class MatchCandidatePort(Protocol):
    identity: BiometricIdentityPort
    similarity: float
    rank: int


class MatchResultPort(Protocol):
    candidates: tuple[MatchCandidatePort, ...]
    decision: object


class FaceMatcherPort(Protocol):
    top_k: int
    policy: MatcherPolicyPort

    def match(
        self, query: BiometricEmbeddingPort, gallery: BiometricGalleryPort
    ) -> MatchResultPort: ...


class BiometricIdentityFactoryPort(Protocol):
    def create(
        self,
        person_id: str,
        display_name: str,
        metadata: Mapping[str, Any] | None,
    ) -> BiometricIdentityPort: ...


class EmbeddingMathPort(Protocol):
    def fingerprint(self, embedding: BiometricEmbeddingPort) -> str: ...
    def similarity(
        self, left: BiometricEmbeddingPort, right: BiometricEmbeddingPort
    ) -> float: ...


class CalibrationAnalyzerPort(Protocol):
    def calibrate(
        self,
        embedding_groups: Mapping[str, Sequence[CalibrationSample]],
        thresholds: Sequence[float],
        run_id: str,
        *,
        synthetic_validation: bool = False,
    ) -> CalibrationReport: ...


class GalleryPersistencePort(Protocol):
    def export(
        self,
        gallery: BiometricGalleryPort,
        manifest_path: Path,
        npz_path: Path,
        *,
        overwrite: bool = False,
    ) -> None: ...

    def import_into(
        self,
        gallery: BiometricGalleryPort,
        manifest_path: Path,
        npz_path: Path,
    ) -> None: ...
