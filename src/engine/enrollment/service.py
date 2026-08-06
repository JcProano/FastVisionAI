"""Deterministic and transactional enrollment into FaceGallery."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any, Mapping, Sequence

import numpy as np

from src.engine.alignment.contracts import AlignmentQuality
from src.engine.embedding.contracts import FaceEmbedding
from src.engine.enrollment.contracts import (
    AcceptedEnrollmentTemplate, EnrollmentCause, EnrollmentMetrics,
    EnrollmentPolicy, EnrollmentResult, EnrollmentStatus, RejectedEnrollmentTemplate,
)
from src.engine.gallery.contracts import FaceIdentity
from src.engine.gallery.gallery import FaceGallery


class EnrollmentService:
    """Validate a complete batch before writing and verify rollback on failure."""

    def __init__(self, gallery: FaceGallery, policy: EnrollmentPolicy | None = None) -> None:
        self.gallery = gallery
        self.policy = policy or EnrollmentPolicy()
        self._lock = threading.Lock()

    def enroll(
        self,
        person_id: str,
        display_name: str,
        embeddings: Sequence[FaceEmbedding],
        metadata: Mapping[str, Any] | None = None,
    ) -> EnrollmentResult:
        started = time.monotonic()
        identity = FaceIdentity(person_id, display_name, _copy_metadata(metadata))
        with self._lock:
            before = _gallery_signature(self.gallery)
            if any(item.person_id == person_id for item in self.gallery.list_identities()):
                causes = [EnrollmentCause.IDENTITY_ALREADY_EXISTS]
                if _gallery_signature(self.gallery) != before:
                    causes.append(EnrollmentCause.ROLLBACK_FAILED)
                return self._result(
                    identity, (), (), tuple(causes),
                    EnrollmentStatus.REJECTED, len(embeddings), (), started,
                )

            accepted: list[tuple[int, FaceEmbedding]] = []
            rejected: list[RejectedEnrollmentTemplate] = []
            similarities: list[float] = []
            provenance = _gallery_provenance(self.gallery)
            fingerprints = {item.fingerprint for item in self.gallery.templates()}
            for input_index, embedding in enumerate(embeddings):
                causes: list[EnrollmentCause] = []
                candidate_provenance = _embedding_provenance(embedding)
                if provenance is not None:
                    causes.extend(_provenance_causes(provenance, candidate_provenance))
                if (
                    embedding.alignment_quality is AlignmentQuality.LOW_QUALITY
                    and not self.policy.allow_low_quality
                ):
                    causes.append(EnrollmentCause.LOW_QUALITY)
                fingerprint = _embedding_fingerprint(embedding)
                if self.policy.reject_exact_duplicates and fingerprint in fingerprints:
                    causes.append(EnrollmentCause.EXACT_DUPLICATE)
                if not causes and len(accepted) >= self.policy.max_templates:
                    causes.append(EnrollmentCause.MAX_TEMPLATES_EXCEEDED)
                if not causes:
                    pair_values = [
                        _cosine(embedding.embedding, previous.embedding)
                        for _, previous in accepted
                    ]
                    similarities.extend(pair_values)
                    if (
                        self.policy.min_pairwise_similarity is not None
                        and any(value < self.policy.min_pairwise_similarity for value in pair_values)
                    ):
                        causes.append(EnrollmentCause.INSUFFICIENT_SIMILARITY)
                    if (
                        self.policy.max_pairwise_similarity is not None
                        and any(value > self.policy.max_pairwise_similarity for value in pair_values)
                    ):
                        causes.append(EnrollmentCause.INSUFFICIENT_DIVERSITY)
                if causes:
                    rejected.append(RejectedEnrollmentTemplate(
                        input_index, embedding.face_index, tuple(dict.fromkeys(causes))
                    ))
                    continue
                if provenance is None:
                    provenance = candidate_provenance
                accepted.append((input_index, embedding))
                fingerprints.add(fingerprint)

            general: list[EnrollmentCause] = []
            if len(accepted) < self.policy.min_templates:
                general.append(EnrollmentCause.INSUFFICIENT_ACCEPTED_TEMPLATES)
                if _gallery_signature(self.gallery) != before:
                    general.append(EnrollmentCause.ROLLBACK_FAILED)
                return self._result(
                    identity, accepted, rejected, tuple(general), EnrollmentStatus.REJECTED,
                    len(embeddings), similarities, started,
                )

            gallery_indices: list[int] = []
            try:
                self.gallery.register_identity(identity)
                for input_index, embedding in accepted:
                    gallery_indices.append(self.gallery.add_template(
                        person_id, embedding, source_reference=f"enrollment-input-{input_index}"
                    ))
            except Exception:
                general.append(EnrollmentCause.TRANSACTION_FAILED)
                rollback_error = False
                try:
                    self.gallery.remove_identity(person_id)
                except Exception:
                    rollback_error = True
                if rollback_error or _gallery_signature(self.gallery) != before:
                    general.append(EnrollmentCause.ROLLBACK_FAILED)
                return self._result(
                    identity, accepted, rejected, tuple(general), EnrollmentStatus.REJECTED,
                    len(embeddings), similarities, started,
                )

            accepted_contracts = tuple(
                AcceptedEnrollmentTemplate(input_index, embedding.face_index,
                                           embedding.alignment_quality, gallery_index)
                for (input_index, embedding), gallery_index in zip(accepted, gallery_indices)
            )
            return self._result_contract(
                identity, accepted_contracts, tuple(rejected), (), EnrollmentStatus.ENROLLED,
                len(embeddings), similarities, started,
            )

    def _result(
        self, identity, accepted, rejected, causes, status, received, similarities, started
    ) -> EnrollmentResult:
        accepted_contracts = tuple(
            AcceptedEnrollmentTemplate(index, embedding.face_index,
                                       embedding.alignment_quality, None)
            for index, embedding in accepted
        )
        return self._result_contract(
            identity, accepted_contracts, tuple(rejected), causes, status,
            received, similarities, started,
        )

    def _result_contract(
        self, identity, accepted, rejected, causes, status, received, similarities, started
    ) -> EnrollmentResult:
        rejected_causes = [cause for item in rejected for cause in item.causes]
        metrics = EnrollmentMetrics(
            templates_received=received,
            templates_accepted=len(accepted),
            templates_rejected=len(rejected),
            low_quality_rejected=rejected_causes.count(EnrollmentCause.LOW_QUALITY),
            exact_duplicates_rejected=rejected_causes.count(EnrollmentCause.EXACT_DUPLICATE),
            incompatible_rejected=sum(cause in _INCOMPATIBLE for cause in rejected_causes),
            diversity_rejected=sum(
                cause in {EnrollmentCause.INSUFFICIENT_DIVERSITY,
                          EnrollmentCause.INSUFFICIENT_SIMILARITY}
                for cause in rejected_causes
            ),
            max_limit_rejected=rejected_causes.count(EnrollmentCause.MAX_TEMPLATES_EXCEEDED),
            pairwise_comparisons=len(similarities),
            minimum_pairwise_similarity=min(similarities) if similarities else None,
            average_pairwise_similarity=(sum(similarities) / len(similarities) if similarities else None),
            maximum_pairwise_similarity=max(similarities) if similarities else None,
            elapsed_ms=(time.monotonic() - started) * 1_000,
        )
        return EnrollmentResult(identity, accepted, rejected, causes, status, metrics)


_INCOMPATIBLE = {
    EnrollmentCause.INCOMPATIBLE_DIMENSION, EnrollmentCause.INCOMPATIBLE_MODEL,
    EnrollmentCause.INCOMPATIBLE_VERSION, EnrollmentCause.INCOMPATIBLE_WEIGHTS,
}


def _copy_metadata(metadata: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if metadata is None:
        return None
    try:
        return json.loads(json.dumps(dict(metadata), sort_keys=True))
    except (TypeError, ValueError) as exc:
        raise ValueError("metadata must be JSON-compatible") from exc


def _gallery_signature(gallery: FaceGallery) -> tuple[object, ...]:
    identities = tuple(
        (item.person_id, item.display_name,
         json.dumps(dict(item.metadata), sort_keys=True) if item.metadata is not None else None)
        for item in gallery.list_identities()
    )
    templates = tuple(
        (item.index, item.template.identity.person_id, item.fingerprint)
        for item in gallery.templates()
    )
    return identities, templates


def _gallery_provenance(gallery: FaceGallery) -> tuple[int, str, str, str] | None:
    templates = gallery.templates()
    if not templates:
        return None
    template = templates[0].template
    return template.dimension, template.model, template.model_version, template.weights_sha256


def _embedding_provenance(embedding: FaceEmbedding) -> tuple[int, str, str, str]:
    return embedding.dimension, embedding.model, embedding.version, embedding.weights_sha256


def _provenance_causes(expected, actual) -> list[EnrollmentCause]:
    causes = []
    for matches, cause in zip(
        (expected[0] == actual[0], expected[1] == actual[1],
         expected[2] == actual[2], expected[3] == actual[3]),
        (EnrollmentCause.INCOMPATIBLE_DIMENSION, EnrollmentCause.INCOMPATIBLE_MODEL,
         EnrollmentCause.INCOMPATIBLE_VERSION, EnrollmentCause.INCOMPATIBLE_WEIGHTS),
    ):
        if not matches:
            causes.append(cause)
    return causes


def _embedding_fingerprint(embedding: FaceEmbedding) -> str:
    vector = np.ascontiguousarray(embedding.embedding, dtype=np.float32)
    digest = hashlib.sha256()
    digest.update(embedding.dimension.to_bytes(8, "big"))
    for value in (embedding.model, embedding.version, embedding.weights_sha256):
        encoded = value.encode(); digest.update(len(encoded).to_bytes(4, "big")); digest.update(encoded)
    digest.update(vector.tobytes(order="C"))
    return digest.hexdigest()


def _cosine(left: np.ndarray, right: np.ndarray) -> float:
    return max(-1.0, min(1.0, float(np.dot(left, right))))
