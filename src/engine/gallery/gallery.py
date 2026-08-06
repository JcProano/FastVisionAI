"""Thread-safe, in-memory face template gallery."""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

from src.engine.embedding.contracts import FaceEmbedding
from src.engine.gallery.contracts import FaceIdentity, FaceTemplate


class FaceGalleryError(RuntimeError):
    pass


class DuplicateIdentityError(FaceGalleryError):
    pass


class IdentityNotFoundError(FaceGalleryError):
    pass


class DuplicateTemplateError(FaceGalleryError):
    pass


class GalleryCompatibilityError(FaceGalleryError):
    pass


@dataclass(frozen=True, slots=True)
class IndexedTemplate:
    index: int
    template: FaceTemplate
    fingerprint: str


class FaceGallery:
    def __init__(self) -> None:
        self._identities: dict[str, FaceIdentity] = {}
        self._templates: list[IndexedTemplate] = []
        self._fingerprints: set[str] = set()
        self._provenance: tuple[int, str, str, str] | None = None
        self._lock = threading.RLock()

    def register_identity(self, identity: FaceIdentity) -> None:
        with self._lock:
            if identity.person_id in self._identities:
                raise DuplicateIdentityError(f"identity already exists: {identity.person_id}")
            self._identities[identity.person_id] = identity

    def add_template(
        self,
        person_id: str,
        embedding: FaceEmbedding | FaceTemplate,
        source_reference: str | None = None,
    ) -> int:
        with self._lock:
            identity = self._identities.get(person_id)
            if identity is None:
                raise IdentityNotFoundError(f"unknown identity: {person_id}")
            template = (
                _template_from_embedding(identity, embedding, source_reference)
                if isinstance(embedding, FaceEmbedding)
                else _rebind_template(identity, embedding)
            )
            provenance = _provenance(template)
            if self._provenance is not None and provenance != self._provenance:
                raise GalleryCompatibilityError("template biometric provenance is incompatible")
            fingerprint = _template_fingerprint(template)
            if fingerprint in self._fingerprints:
                raise DuplicateTemplateError("exact template already exists")
            index = len(self._templates)
            self._templates.append(IndexedTemplate(index, template, fingerprint))
            self._fingerprints.add(fingerprint)
            if self._provenance is None:
                self._provenance = provenance
            return index

    def remove_identity(self, person_id: str) -> bool:
        with self._lock:
            if self._identities.pop(person_id, None) is None:
                return False
            retained = [
                item for item in self._templates if item.template.identity.person_id != person_id
            ]
            self._templates = [
                IndexedTemplate(index, item.template, item.fingerprint)
                for index, item in enumerate(retained)
            ]
            self._fingerprints = {item.fingerprint for item in self._templates}
            self._provenance = _provenance(self._templates[0].template) if self._templates else None
            return True

    def list_identities(self) -> tuple[FaceIdentity, ...]:
        with self._lock:
            return tuple(self._identities[key] for key in sorted(self._identities))

    def templates(self, person_id: str | None = None) -> tuple[IndexedTemplate, ...]:
        with self._lock:
            if person_id is None:
                return tuple(self._templates)
            return tuple(
                item for item in self._templates if item.template.identity.person_id == person_id
            )

    def replace_from(self, validated: FaceGallery) -> None:
        identities = validated.list_identities()
        templates = validated.templates()
        with self._lock:
            self._identities = {item.person_id: item for item in identities}
            self._templates = list(templates)
            self._fingerprints = {item.fingerprint for item in templates}
            self._provenance = _provenance(templates[0].template) if templates else None

    def __len__(self) -> int:
        with self._lock:
            return len(self._identities)


def _template_from_embedding(
    identity: FaceIdentity, embedding: FaceEmbedding, source_reference: str | None
) -> FaceTemplate:
    return FaceTemplate(
        identity=identity,
        embedding=embedding.embedding,
        dimension=embedding.dimension,
        model=embedding.model,
        model_version=embedding.version,
        weights_sha256=embedding.weights_sha256,
        created_at=datetime.now(timezone.utc),
        quality=embedding.alignment_quality,
        source_reference=source_reference,
    )


def _rebind_template(identity: FaceIdentity, template: FaceTemplate) -> FaceTemplate:
    if template.identity.person_id != identity.person_id:
        raise GalleryCompatibilityError("template identity does not match target identity")
    return FaceTemplate(
        identity, template.embedding, template.dimension, template.model,
        template.model_version, template.weights_sha256, template.created_at,
        template.quality, template.source_reference,
    )


def _provenance(template: FaceTemplate) -> tuple[int, str, str, str]:
    return (
        template.dimension, template.model, template.model_version, template.weights_sha256
    )


def _template_fingerprint(template: FaceTemplate) -> str:
    vector = np.ascontiguousarray(template.embedding, dtype=np.float32)
    digest = hashlib.sha256()
    digest.update(template.dimension.to_bytes(8, "big", signed=False))
    for value in (template.model, template.model_version, template.weights_sha256):
        encoded = value.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "big"))
        digest.update(encoded)
    digest.update(vector.tobytes(order="C"))
    return digest.hexdigest()
