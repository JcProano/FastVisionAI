"""Framework-free test doubles for biometric application ports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class FakeIdentity:
    person_id: str
    display_name: str
    metadata: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class FakeEmbedding:
    face_index: int = 0
    dimension: int = 3
    model: str = "fake-model"
    version: str = "1"
    weights_sha256: str = "a" * 64
    alignment_quality: str = "valid"
    run_id: str = "run-1"
    key: str = "embedding-1"


@dataclass(frozen=True)
class FakeTemplate:
    identity: FakeIdentity
    dimension: int
    model: str
    model_version: str
    weights_sha256: str


@dataclass(frozen=True)
class FakeIndexedTemplate:
    index: int
    template: FakeTemplate
    fingerprint: str


class InMemoryBiometricGallery:
    def __init__(self) -> None:
        self.identities: dict[str, FakeIdentity] = {}
        self.items: list[FakeIndexedTemplate] = []
        self.fail_add = False

    def list_identities(self) -> tuple[FakeIdentity, ...]:
        return tuple(self.identities[key] for key in sorted(self.identities))

    def templates(
        self, person_id: str | None = None
    ) -> tuple[FakeIndexedTemplate, ...]:
        if person_id is None:
            return tuple(self.items)
        return tuple(
            item
            for item in self.items
            if item.template.identity.person_id == person_id
        )

    def register_identity(self, identity: FakeIdentity) -> None:
        if identity.person_id in self.identities:
            raise ValueError("identity already exists")
        self.identities[identity.person_id] = identity

    def add_template(
        self,
        person_id: str,
        embedding: FakeEmbedding,
        source_reference: str | None = None,
    ) -> int:
        del source_reference
        if self.fail_add:
            raise RuntimeError("simulated template write failure")
        identity = self.identities[person_id]
        index = len(self.items)
        self.items.append(
            FakeIndexedTemplate(
                index,
                FakeTemplate(
                    identity,
                    embedding.dimension,
                    embedding.model,
                    embedding.version,
                    embedding.weights_sha256,
                ),
                embedding.key,
            )
        )
        return index

    def remove_identity(self, person_id: str) -> bool:
        identity = self.identities.pop(person_id, None)
        if identity is None:
            return False
        self.items = [
            item
            for item in self.items
            if item.template.identity.person_id != person_id
        ]
        self.items = [
            FakeIndexedTemplate(index, item.template, item.fingerprint)
            for index, item in enumerate(self.items)
        ]
        return True


class FakeIdentityFactory:
    def create(
        self,
        person_id: str,
        display_name: str,
        metadata: Mapping[str, Any] | None,
    ) -> FakeIdentity:
        return FakeIdentity(person_id, display_name, metadata)


class FakeEmbeddingMath:
    def fingerprint(self, embedding: FakeEmbedding) -> str:
        return embedding.key

    def similarity(self, left: FakeEmbedding, right: FakeEmbedding) -> float:
        return 0.8 if left.key != right.key else 1.0


@dataclass(frozen=True)
class FakeMatcherPolicy:
    automatic_decision_enabled: bool = False
    threshold: float | None = None


@dataclass(frozen=True)
class FakeMatchCandidate:
    identity: FakeIdentity
    similarity: float
    rank: int


@dataclass(frozen=True)
class FakeMatchResult:
    candidates: tuple[FakeMatchCandidate, ...]
    decision: str = "not_evaluated"


class FakeMatcher:
    def __init__(
        self, candidates: tuple[FakeMatchCandidate, ...] = (), top_k: int = 5
    ) -> None:
        self.candidates = candidates
        self.top_k = top_k
        self.policy = FakeMatcherPolicy()
        self.calls = 0

    def match(self, query: FakeEmbedding, gallery: object) -> FakeMatchResult:
        del query, gallery
        self.calls += 1
        return FakeMatchResult(self.candidates)


class FakeGalleryPersistence:
    def __init__(self) -> None:
        self.export_calls: list[tuple[object, Path, Path, bool]] = []
        self.import_calls: list[tuple[object, Path, Path]] = []

    def export(
        self,
        gallery: object,
        manifest_path: Path,
        npz_path: Path,
        *,
        overwrite: bool = False,
    ) -> None:
        self.export_calls.append((gallery, manifest_path, npz_path, overwrite))

    def import_into(
        self, gallery: object, manifest_path: Path, npz_path: Path
    ) -> None:
        self.import_calls.append((gallery, manifest_path, npz_path))
