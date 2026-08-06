"""Explicit, optional JSON+NPZ development persistence for biometric templates."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from src.engine.alignment.contracts import AlignmentQuality
from src.engine.gallery.contracts import FaceIdentity, FaceTemplate
from src.engine.gallery.gallery import FaceGallery

SCHEMA_VERSION = 1


class GalleryPersistenceError(RuntimeError):
    pass


class PersistenceDisabledError(GalleryPersistenceError):
    pass


@dataclass(frozen=True, slots=True)
class ImportLimits:
    max_identities: int = 10_000
    max_templates: int = 100_000
    max_dimension: int = 4_096


class GalleryPersistence:
    def __init__(self, enabled: bool = False, limits: ImportLimits | None = None) -> None:
        self.enabled = enabled
        self.limits = limits or ImportLimits()

    def export(
        self,
        gallery: FaceGallery,
        manifest_path: Path,
        npz_path: Path,
        *,
        overwrite: bool = False,
    ) -> None:
        self._require_enabled()
        if not overwrite and (manifest_path.exists() or npz_path.exists()):
            raise GalleryPersistenceError("export target already exists")
        identities = gallery.list_identities()
        templates = gallery.templates()
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        npz_path.parent.mkdir(parents=True, exist_ok=True)
        arrays = {f"template_{item.index:08d}": item.template.embedding for item in templates}
        npz_temp = _temporary_path(npz_path)
        manifest_temp = _temporary_path(manifest_path)
        try:
            with npz_temp.open("wb") as stream:
                np.savez_compressed(stream, **arrays)
            npz_digest = _sha256(npz_temp)
            manifest = {
                "schema_version": SCHEMA_VERSION,
                "npz_file": npz_path.name,
                "npz_sha256": npz_digest,
                "identities": [
                    {
                        "person_id": identity.person_id,
                        "display_name": identity.display_name,
                        "metadata": dict(identity.metadata) if identity.metadata is not None else None,
                    }
                    for identity in identities
                ],
                "templates": [
                    {
                        "template_index": item.index,
                        "array_key": f"template_{item.index:08d}",
                        "person_id": item.template.identity.person_id,
                        "dimension": item.template.dimension,
                        "model": item.template.model,
                        "model_version": item.template.model_version,
                        "weights_sha256": item.template.weights_sha256,
                        "created_at": item.template.created_at.isoformat(),
                        "quality": item.template.quality.value,
                        "source_reference": item.template.source_reference,
                    }
                    for item in templates
                ],
            }
            manifest_temp.write_text(
                json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
            )
            os.replace(npz_temp, npz_path)
            os.replace(manifest_temp, manifest_path)
        except Exception:
            npz_temp.unlink(missing_ok=True)
            manifest_temp.unlink(missing_ok=True)
            raise

    def import_into(self, gallery: FaceGallery, manifest_path: Path, npz_path: Path) -> None:
        self._require_enabled()
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise GalleryPersistenceError("invalid gallery manifest") from exc
        self._validate_manifest_header(manifest, npz_path)
        identities_data = _list_field(manifest, "identities")
        templates_data = _list_field(manifest, "templates")
        if len(identities_data) > self.limits.max_identities:
            raise GalleryPersistenceError("identity import limit exceeded")
        if len(templates_data) > self.limits.max_templates:
            raise GalleryPersistenceError("template import limit exceeded")

        temporary = FaceGallery()
        try:
            for raw_identity in identities_data:
                item = _mapping(raw_identity, "identity")
                temporary.register_identity(FaceIdentity(
                    str(item["person_id"]), str(item["display_name"]), item.get("metadata")
                ))
            expected_keys: set[str] = set()
            with np.load(npz_path, allow_pickle=False) as archive:
                for expected_index, raw_template in enumerate(templates_data):
                    item = _mapping(raw_template, "template")
                    if int(item["template_index"]) != expected_index:
                        raise GalleryPersistenceError("template indices are not contiguous")
                    key = str(item["array_key"])
                    if key in expected_keys or key not in archive.files:
                        raise GalleryPersistenceError("invalid or duplicate NPZ array key")
                    expected_keys.add(key)
                    dimension = int(item["dimension"])
                    if dimension <= 0 or dimension > self.limits.max_dimension:
                        raise GalleryPersistenceError("template dimension exceeds import limits")
                    person_id = str(item["person_id"])
                    identities = {value.person_id: value for value in temporary.list_identities()}
                    identity = identities.get(person_id)
                    if identity is None:
                        raise GalleryPersistenceError("template references unknown identity")
                    template = FaceTemplate(
                        identity=identity,
                        embedding=np.asarray(archive[key]),
                        dimension=dimension,
                        model=str(item["model"]),
                        model_version=str(item["model_version"]),
                        weights_sha256=str(item["weights_sha256"]),
                        created_at=datetime.fromisoformat(str(item["created_at"])),
                        quality=AlignmentQuality(str(item["quality"])),
                        source_reference=(
                            None if item.get("source_reference") is None
                            else str(item["source_reference"])
                        ),
                    )
                    index = temporary.add_template(person_id, template)
                    if index != expected_index:
                        raise GalleryPersistenceError("template index mismatch")
                if expected_keys != set(archive.files):
                    raise GalleryPersistenceError("NPZ contains unexpected arrays")
        except GalleryPersistenceError:
            raise
        except Exception as exc:
            raise GalleryPersistenceError("gallery import validation failed") from exc
        # Transaction boundary: the active gallery changes only after all validation succeeds.
        gallery.replace_from(temporary)

    def _validate_manifest_header(self, manifest: Any, npz_path: Path) -> None:
        root = _mapping(manifest, "manifest")
        if root.get("schema_version") != SCHEMA_VERSION:
            raise GalleryPersistenceError("unsupported gallery schema")
        if root.get("npz_file") != npz_path.name:
            raise GalleryPersistenceError("manifest NPZ filename mismatch")
        expected = root.get("npz_sha256")
        if not isinstance(expected, str) or expected != _sha256(npz_path):
            raise GalleryPersistenceError("NPZ integrity verification failed")

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise PersistenceDisabledError("gallery persistence is disabled")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise GalleryPersistenceError("could not read persistence artifact") from exc
    return digest.hexdigest()


def _temporary_path(target: Path) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    os.close(descriptor)
    return Path(name)


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GalleryPersistenceError(f"{name} must be an object")
    return value


def _list_field(root: dict[str, Any], name: str) -> list[Any]:
    value = root.get(name)
    if not isinstance(value, list):
        raise GalleryPersistenceError(f"{name} must be a list")
    return value
