"""Transactional controller for safe local management of registered people."""

from __future__ import annotations

import json
import math
import threading
from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.engine.embedding.contracts import FaceEmbedding
from src.engine.enrollment import EnrollmentService
from src.engine.face_quality.contracts import FaceQualityScore
from src.engine.gallery import FaceGallery, FaceIdentity
from src.engine.gallery.persistence import GalleryPersistence
from src.ui.form_validation import validate_identity_fields
from src.ui.people.contracts import (
    PeopleListDTO, PeopleManagerState, PeopleOperationResultDTO,
    PersonDetailsDTO, PersonSummaryDTO,
)

QUALITY_KEY = "face_quality_templates"
QUALITY_SCHEMA = "1.0"


class PeopleManagerController:
    def __init__(
        self, gallery: FaceGallery, enrollment: EnrollmentService,
        persistence: GalleryPersistence, manifest_path: Path, archive_path: Path,
    ) -> None:
        if enrollment.gallery is not gallery:
            raise ValueError("people manager must share EnrollmentService gallery")
        self.gallery = gallery
        self.enrollment = enrollment
        self.persistence = persistence
        self.manifest_path = manifest_path
        self.archive_path = archive_path
        self._state = PeopleManagerState.IDLE
        self._pending_import: FaceGallery | None = None
        self._additional_person_id: str | None = None
        self._replacement_person_id: str | None = None
        self._lock = threading.RLock()

    @property
    def state(self) -> PeopleManagerState:
        with self._lock:
            return self._state

    def list_people(self, query: str = "") -> PeopleListDTO:
        with self._lock:
            normalized = " ".join(query.casefold().split())
            people = tuple(
                summary for summary in self._summaries()
                if not normalized or normalized in " ".join(filter(None, (
                    summary.first_name, summary.last_name, summary.display_name,
                    summary.external_identifier,
                ))).casefold()
            )
            return PeopleListDTO(
                self._state, query, people, len(self.gallery.list_identities()),
                len(self.gallery.templates()),
            )

    def details(self, person_id: str) -> PersonDetailsDTO:
        with self._lock:
            summary = self._summary(self._identity(person_id))
            items = _quality_items(self._identity(person_id).metadata)
            return PersonDetailsDTO(
                summary,
                tuple(sorted({str(item["profile_name"]) for item in items
                              if item.get("profile_name")})),
                tuple(sorted({str(item["profile_version"]) for item in items
                              if item.get("profile_version")})),
            )

    def update_person(
        self, person_id: str, first_name: str, last_name: str,
        external_identifier: str | None,
    ) -> PeopleOperationResultDTO:
        with self._lock:
            self._require_idle()
            self._state = PeopleManagerState.EDITING
            try:
                first, last, external = validate_identity_fields(
                    first_name, last_name, external_identifier
                )
                identity = self._identity(person_id)
                metadata = _metadata(identity.metadata)
                metadata.update(first_name=first, last_name=last,
                                external_identifier=external)
                replacement = FaceIdentity(person_id, f"{first} {last}", metadata)
                temporary = _rebuild(self.gallery, identity_overrides={person_id: replacement})
                self.gallery.replace_from(temporary)
                return self._ok("edit", "Identidad actualizada en memoria.", person_id)
            except Exception:
                self._state = PeopleManagerState.ERROR
                return self._fail("edit", "No se pudo editar la identidad.", person_id)
            finally:
                if self._state is not PeopleManagerState.ERROR:
                    self._state = PeopleManagerState.IDLE

    def delete_person(self, person_id: str, *, confirmed: bool) -> PeopleOperationResultDTO:
        with self._lock:
            self._require_idle()
            identity = self._identity(person_id)
            count = len(self.gallery.templates(person_id))
            if not confirmed:
                return PeopleOperationResultDTO(
                    PeopleManagerState.IDLE, False, "delete", "Eliminación cancelada.",
                    person_id, count,
                )
            self._state = PeopleManagerState.DELETING
            try:
                temporary = _rebuild(self.gallery, excluded={identity.person_id})
                self.gallery.replace_from(temporary)
            except Exception:
                self._state = PeopleManagerState.ERROR
                return self._fail("delete", "No se pudo eliminar la identidad.", person_id)
            self._state = PeopleManagerState.IDLE
            return PeopleOperationResultDTO(
                PeopleManagerState.IDLE, True, "delete",
                "Identidad y templates eliminados en memoria.", person_id, count,
            )

    def begin_additional(self, person_id: str) -> PeopleOperationResultDTO:
        with self._lock:
            self._require_idle()
            try:
                self._identity(person_id)
            except KeyError:
                self._state = PeopleManagerState.ERROR
                return self._fail(
                    "additional_start", "La identidad seleccionada no existe.", person_id
                )
            self._state = PeopleManagerState.ENROLLING_MORE
            self._additional_person_id = person_id
            return self._ok("additional_start", "Captura adicional iniciada.", person_id)

    def begin_replacement(self, person_id: str) -> PeopleOperationResultDTO:
        result=self.begin_additional(person_id)
        if result.success:self._replacement_person_id=person_id
        return result

    def cancel_additional(self) -> PeopleOperationResultDTO:
        with self._lock:
            person_id = self._additional_person_id
            self._additional_person_id = None
            self._replacement_person_id = None
            self._state = PeopleManagerState.IDLE
            return self._ok("additional_cancel", "Captura adicional cancelada.", person_id)

    def complete_additional(
        self, person_id: str,
        samples: Sequence[tuple[FaceEmbedding, FaceQualityScore | None]],
    ) -> PeopleOperationResultDTO:
        with self._lock:
            if self._state is not PeopleManagerState.ENROLLING_MORE or (
                self._additional_person_id != person_id
            ):
                return self._fail("additional", "No existe una captura adicional activa.", person_id)
            try:
                replacing=self._replacement_person_id == person_id
                temporary = _rebuild(
                    self.gallery,excluded={person_id} if replacing else set(),
                    identity_overrides={person_id:self._identity(person_id)} if replacing else {},
                    additions={person_id: tuple(samples)},
                )
                self.gallery.replace_from(temporary)
                self._additional_person_id = None
                self._replacement_person_id = None
                self._state = PeopleManagerState.IDLE
                return PeopleOperationResultDTO(
                    PeopleManagerState.IDLE, True, "additional",
                    ("Templates faciales reemplazados en memoria." if replacing else
                     "Templates adicionales agregados en memoria."), person_id, len(samples),
                )
            except Exception:
                self._additional_person_id = None
                self._replacement_person_id = None
                self._state = PeopleManagerState.ERROR
                return self._fail(
                    "additional", "Los templates adicionales no superaron la validación.",
                    person_id,
                )

    def delete_persisted_identity(self, person_id: str) -> PeopleOperationResultDTO:
        """Atomically persist a gallery without one identity, then activate it."""
        with self._lock:
            identities={item.person_id for item in self.gallery.list_identities()}
            if person_id not in identities:
                return self._ok("delete", "La persona no tenía identidad biométrica.", person_id)
            count=len(self.gallery.templates(person_id))
            temporary=_rebuild(self.gallery,excluded={person_id})
            try:
                self.persistence.export(
                    temporary,self.manifest_path,self.archive_path,overwrite=True,
                )
                self.gallery.replace_from(temporary)
                return PeopleOperationResultDTO(
                    PeopleManagerState.IDLE,True,"delete",
                    "Identidad biométrica eliminada y galería actualizada.",person_id,count,
                    len(self.gallery.list_identities()),len(self.gallery.templates()),
                )
            except Exception:
                return self._fail("delete","No se pudo persistir la eliminación biométrica.",person_id)

    def save_changes(self, *, overwrite_confirmed: bool = False) -> PeopleOperationResultDTO:
        return self.export_gallery(
            self.manifest_path, self.archive_path,
            overwrite_confirmed=overwrite_confirmed, operation="save",
        )

    def export_gallery(
        self, manifest: Path, archive: Path, *, overwrite_confirmed: bool = False,
        operation: str = "export",
    ) -> PeopleOperationResultDTO:
        with self._lock:
            self._require_idle()
            self._state = (PeopleManagerState.SAVING if operation == "save"
                           else PeopleManagerState.EXPORTING)
            try:
                self.persistence.export(
                    self.gallery, manifest, archive, overwrite=overwrite_confirmed
                )
                self._state = PeopleManagerState.IDLE
                return self._ok(operation, "Galería exportada correctamente.")
            except Exception:
                self._state = PeopleManagerState.ERROR
                return self._fail(operation, "No se pudo exportar la galería.")

    def prepare_import(self, manifest: Path, archive: Path) -> PeopleOperationResultDTO:
        with self._lock:
            self._require_idle()
            self._state = PeopleManagerState.IMPORTING
            temporary = FaceGallery()
            try:
                self.persistence.import_into(temporary, manifest, archive)
                self._pending_import = temporary
                return PeopleOperationResultDTO(
                    PeopleManagerState.IMPORTING, True, "import_preview",
                    "Galería validada; confirme para reemplazar la galería activa.",
                    identity_count=len(temporary.list_identities()),
                    template_count=len(temporary.templates()),
                )
            except Exception:
                self._pending_import = None
                self._state = PeopleManagerState.ERROR
                return self._fail("import_preview", "La galería seleccionada no es válida.")

    def confirm_import(self, *, confirmed: bool) -> PeopleOperationResultDTO:
        with self._lock:
            pending = self._pending_import
            if self._state is not PeopleManagerState.IMPORTING or pending is None:
                return self._fail("import", "No existe una importación validada pendiente.")
            self._pending_import = None
            if not confirmed:
                self._state = PeopleManagerState.IDLE
                return PeopleOperationResultDTO(
                    PeopleManagerState.IDLE, False, "import", "Importación cancelada."
                )
            self.gallery.replace_from(pending)
            self._state = PeopleManagerState.IDLE
            return PeopleOperationResultDTO(
                PeopleManagerState.IDLE, True, "import", "Galería reemplazada correctamente.",
                identity_count=len(self.gallery.list_identities()),
                template_count=len(self.gallery.templates()),
            )

    def close(self) -> None:
        with self._lock:
            self._pending_import = None
            if self._state is PeopleManagerState.ENROLLING_MORE:
                self._additional_person_id = None
            self._state = PeopleManagerState.IDLE

    def _summaries(self) -> tuple[PersonSummaryDTO, ...]:
        return tuple(self._summary(item) for item in self.gallery.list_identities())

    def _summary(self, identity: FaceIdentity) -> PersonSummaryDTO:
        metadata = _metadata(identity.metadata)
        first, last = _names(identity)
        templates = self.gallery.templates(identity.person_id)
        owned = {item.index for item in templates}
        scores = [float(item["score"]) for item in _quality_items(metadata)
                  if item.get("template_index") in owned and _valid_score(item.get("score"))]
        created = min((item.template.created_at for item in templates), default=None)
        return PersonSummaryDTO(
            identity.person_id, first, last, identity.display_name,
            metadata.get("external_identifier"), len(templates), len(scores),
            len(templates) - len(scores), sum(scores) / len(scores) if scores else None,
            min(scores) if scores else None, max(scores) if scores else None, created,
        )

    def _identity(self, person_id: str) -> FaceIdentity:
        for identity in self.gallery.list_identities():
            if identity.person_id == person_id:
                return identity
        raise KeyError("unknown person_id")

    def _require_idle(self) -> None:
        if self._state is PeopleManagerState.ERROR:
            self._state = PeopleManagerState.IDLE
        if self._state is not PeopleManagerState.IDLE:
            raise RuntimeError("people manager is busy")

    def _ok(self, operation: str, message: str,
            person_id: str | None = None) -> PeopleOperationResultDTO:
        return PeopleOperationResultDTO(self._state, True, operation, message, person_id)

    def _fail(self, operation: str, message: str,
              person_id: str | None = None) -> PeopleOperationResultDTO:
        return PeopleOperationResultDTO(PeopleManagerState.ERROR, False, operation,
                                        message, person_id)


def _rebuild(
    source: FaceGallery, *, identity_overrides: dict[str, FaceIdentity] | None = None,
    additions: dict[str, tuple[tuple[FaceEmbedding, FaceQualityScore | None], ...]] | None = None,
    excluded: set[str] | None = None,
) -> FaceGallery:
    overrides = identity_overrides or {}
    additions = additions or {}
    excluded = excluded or set()
    identities = {item.person_id: item for item in source.list_identities()
                  if item.person_id not in excluded}
    identities.update(overrides)
    if any(person_id not in identities for person_id in additions):
        raise KeyError("unknown identity")
    existing = tuple(item for item in source.templates()
                     if item.template.identity.person_id not in excluded)
    old_to_new = {item.index: new for new, item in enumerate(existing)}
    quality_by_person: dict[str, list[dict[str, Any]]] = {}
    for person_id, identity in identities.items():
        metadata_source = overrides.get(person_id, identity)
        owned = {item.index for item in source.templates(person_id)}
        quality_by_person[person_id] = [] if person_id in excluded else [
            {**item, "template_index": old_to_new[int(item["template_index"])]}
            for item in _quality_items(metadata_source.metadata)
            if item.get("template_index") in owned
        ]
    next_index = len(existing)
    for person_id, samples in additions.items():
        for _embedding, score in samples:
            if score is not None:
                quality_by_person[person_id].append(_quality_item(next_index, score))
            next_index += 1
    temporary = FaceGallery()
    for person_id in sorted(identities):
        base = overrides.get(person_id, identities[person_id])
        metadata = _metadata(base.metadata)
        metadata[QUALITY_KEY] = {
            "schema_version": QUALITY_SCHEMA,
            "items": quality_by_person[person_id],
        }
        temporary.register_identity(FaceIdentity(
            base.person_id, base.display_name, metadata
        ))
    for item in existing:
        temporary.add_template(item.template.identity.person_id, item.template)
    for person_id, samples in additions.items():
        for embedding, _score in samples:
            temporary.add_template(person_id, embedding, source_reference="additional-enrollment")
    return temporary


def _quality_item(index: int, score: FaceQualityScore) -> dict[str, Any]:
    return {
        "template_index": index,
        "score": score.total_score,
        "quality_band": score.quality_band.value,
        "profile_name": score.profile_name,
        "profile_version": score.profile_version,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }


def record_template_quality_scores(
    gallery: FaceGallery, person_id: str,
    scores: Sequence[tuple[int, FaceQualityScore]],
) -> None:
    """Atomically attach safe score metadata to existing template indices."""
    identities = {item.person_id: item for item in gallery.list_identities()}
    identity = identities.get(person_id)
    if identity is None:
        raise KeyError("unknown identity")
    owned = {item.index for item in gallery.templates(person_id)}
    if any(index not in owned for index, _score in scores):
        raise ValueError("quality score references a foreign template")
    metadata = _metadata(identity.metadata)
    replacements = {index: _quality_item(index, score) for index, score in scores}
    retained = [item for item in _quality_items(metadata)
                if item.get("template_index") not in replacements]
    metadata[QUALITY_KEY] = {
        "schema_version": QUALITY_SCHEMA,
        "items": sorted((*retained, *replacements.values()),
                        key=lambda item: int(item["template_index"])),
    }
    temporary = _rebuild(gallery, identity_overrides={person_id: FaceIdentity(
        person_id, identity.display_name, metadata
    )})
    gallery.replace_from(temporary)


def _quality_items(metadata: Any) -> tuple[dict[str, Any], ...]:
    root = _metadata(metadata).get(QUALITY_KEY)
    if not isinstance(root, dict) or root.get("schema_version") != QUALITY_SCHEMA:
        return ()
    items = root.get("items")
    if not isinstance(items, list):
        return ()
    allowed = {"template_index", "score", "quality_band", "profile_name",
               "profile_version", "recorded_at"}
    return tuple(dict(item) for item in items
                 if isinstance(item, dict) and set(item) <= allowed)


def _metadata(value: Any) -> dict[str, Any]:
    return json.loads(json.dumps(dict(value) if value is not None else {}, sort_keys=True))


def _names(identity: FaceIdentity) -> tuple[str, str]:
    metadata = _metadata(identity.metadata)
    first = str(metadata.get("first_name") or "").strip()
    last = str(metadata.get("last_name") or "").strip()
    if not first or not last:
        parts = identity.display_name.split(maxsplit=1)
        first = first or parts[0]
        last = last or (parts[1] if len(parts) > 1 else "")
    return first, last


def _valid_score(value: Any) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(value) and 0 <= value <= 100
