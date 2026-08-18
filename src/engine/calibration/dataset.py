"""Opt-in JSON+NPZ storage for non-production calibration sessions."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from src.engine.alignment.contracts import AlignmentQuality
from src.engine.calibration.contracts import (
    CalibrationDistance, CalibrationIllumination, CalibrationPose, CalibrationSample,
    CalibrationSampleMetadata, CalibrationSampleType,
)

SCHEMA_VERSION = 1


class CalibrationDatasetError(RuntimeError):
    pass


class ConsentRequiredError(CalibrationDatasetError):
    pass


@dataclass(frozen=True, slots=True)
class DatasetLimits:
    max_identities: int = 1_000
    max_samples: int = 100_000
    max_dimension: int = 4_096


@dataclass(frozen=True, slots=True)
class SessionDeletionResult:
    deleted: tuple[Path, ...]
    not_found: tuple[Path, ...]
    secure_erasure_claimed: bool = False


class CalibrationDatasetStore:
    """Explicit persistence. It is disabled unless constructed with enabled=True."""

    def __init__(self, enabled: bool = False, limits: DatasetLimits | None = None) -> None:
        self.enabled = enabled
        self.limits = limits or DatasetLimits()

    def save(
        self,
        groups: Mapping[str, Sequence[CalibrationSample]],
        manifest_path: Path,
        npz_path: Path,
        *,
        consent_confirmed: bool,
        overwrite: bool = False,
    ) -> None:
        self._require_enabled()
        if not consent_confirmed:
            raise ConsentRequiredError("explicit consent is required to save calibration data")
        if not overwrite and (manifest_path.exists() or npz_path.exists()):
            raise CalibrationDatasetError("calibration target already exists")
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        npz_path.parent.mkdir(parents=True, exist_ok=True)
        arrays: dict[str, np.ndarray] = {}
        records: list[dict[str, Any]] = []
        for identity in sorted(groups):
            for index, sample in enumerate(groups[identity]):
                key = f"sample_{len(records):08d}"
                vector = _validated_vector(sample.embedding, self.limits.max_dimension)
                if identity != sample.metadata.temporary_identity_id:
                    raise CalibrationDatasetError("sample identity does not match dataset group")
                arrays[key] = vector
                meta = sample.metadata
                records.append({
                    "array_key": key, "dimension": int(vector.size),
                    "session_id": meta.session_id,
                    "temporary_identity_id": meta.temporary_identity_id,
                    "captured_at": meta.captured_at.isoformat(),
                    "source_identifier": meta.source_identifier,
                    "resolution": list(meta.resolution),
                    "alignment_quality": meta.alignment_quality.value,
                    "model": meta.model, "version": meta.version,
                    "weights_sha256": meta.weights_sha256,
                    "face_quality_score": meta.face_quality_score,
                    "face_quality_band": meta.face_quality_band,
                    "quality_profile_name": meta.quality_profile_name,
                    "quality_profile_version": meta.quality_profile_version,
                    "sample_type": None if meta.sample_type is None else meta.sample_type.value,
                    "expected_identity": meta.expected_identity,
                    "calibration_session_id": meta.calibration_session_id,
                    "evaluation_sample_id": meta.evaluation_sample_id,
                    "condition_id": meta.condition_id,
                    "illumination": None if meta.illumination is None else meta.illumination.value,
                    "distance": None if meta.distance is None else meta.distance.value,
                    "pose": None if meta.pose is None else meta.pose.value,
                })
        if len(groups) > self.limits.max_identities or len(records) > self.limits.max_samples:
            raise CalibrationDatasetError("calibration dataset exceeds configured limits")
        npz_temp = _temporary(npz_path)
        json_temp = _temporary(manifest_path)
        npz_backup = _temporary(npz_path) if overwrite and npz_path.exists() else None
        json_backup = _temporary(manifest_path) if overwrite and manifest_path.exists() else None
        if npz_backup is not None:
            shutil.copy2(npz_path, npz_backup)
        if json_backup is not None:
            shutil.copy2(manifest_path, json_backup)
        npz_replaced = manifest_replaced = False
        try:
            with npz_temp.open("wb") as stream:
                np.savez_compressed(stream, **arrays)
            manifest = {
                "schema_version": SCHEMA_VERSION, "npz_file": npz_path.name,
                "npz_sha256": _sha256(npz_temp), "sample_count": len(records),
                "samples": records,
            }
            json_temp.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
            os.replace(npz_temp, npz_path)
            npz_replaced = True
            os.replace(json_temp, manifest_path)
            manifest_replaced = True
        except Exception:
            npz_temp.unlink(missing_ok=True)
            json_temp.unlink(missing_ok=True)
            if npz_replaced:
                if npz_backup is not None:
                    os.replace(npz_backup, npz_path)
                else:
                    npz_path.unlink(missing_ok=True)
            if manifest_replaced:
                if json_backup is not None:
                    os.replace(json_backup, manifest_path)
                else:
                    manifest_path.unlink(missing_ok=True)
            raise
        finally:
            if npz_backup is not None:
                npz_backup.unlink(missing_ok=True)
            if json_backup is not None:
                json_backup.unlink(missing_ok=True)

    def load(self, manifest_path: Path, npz_path: Path) -> dict[str, tuple[CalibrationSample, ...]]:
        """Validate completely and return a new dataset; no active object is mutated."""
        self._require_enabled()
        try:
            root = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CalibrationDatasetError("invalid calibration manifest") from exc
        if not isinstance(root, dict) or root.get("schema_version") != SCHEMA_VERSION:
            raise CalibrationDatasetError("unsupported calibration manifest")
        if root.get("npz_file") != npz_path.name or root.get("npz_sha256") != _sha256(npz_path):
            raise CalibrationDatasetError("calibration archive integrity validation failed")
        records = root.get("samples")
        if not isinstance(records, list) or root.get("sample_count") != len(records):
            raise CalibrationDatasetError("invalid calibration sample list")
        if len(records) > self.limits.max_samples:
            raise CalibrationDatasetError("calibration sample limit exceeded")
        staged: dict[str, list[CalibrationSample]] = {}
        keys: set[str] = set()
        try:
            with np.load(npz_path, allow_pickle=False) as archive:
                for raw in records:
                    if not isinstance(raw, dict):
                        raise CalibrationDatasetError("invalid calibration sample metadata")
                    key = str(raw["array_key"])
                    if key in keys or key not in archive.files:
                        raise CalibrationDatasetError("invalid calibration array reference")
                    keys.add(key)
                    vector = _validated_vector(archive[key], self.limits.max_dimension)
                    if int(raw["dimension"]) != vector.size:
                        raise CalibrationDatasetError("calibration dimension mismatch")
                    identity = str(raw["temporary_identity_id"])
                    metadata = CalibrationSampleMetadata(
                        session_id=str(raw["session_id"]), temporary_identity_id=identity,
                        captured_at=datetime.fromisoformat(str(raw["captured_at"])),
                        source_identifier=str(raw["source_identifier"]),
                        resolution=(int(raw["resolution"][0]), int(raw["resolution"][1])),
                        alignment_quality=AlignmentQuality(str(raw["alignment_quality"])),
                        model=str(raw["model"]), version=str(raw["version"]),
                        weights_sha256=str(raw["weights_sha256"]),
                        face_quality_score=(None if raw.get("face_quality_score") is None
                                            else float(raw["face_quality_score"])),
                        face_quality_band=(None if raw.get("face_quality_band") is None
                                           else str(raw["face_quality_band"])),
                        quality_profile_name=(None if raw.get("quality_profile_name") is None
                                              else str(raw["quality_profile_name"])),
                        quality_profile_version=(
                            None if raw.get("quality_profile_version") is None
                            else str(raw["quality_profile_version"])
                        ),
                        sample_type=(None if raw.get("sample_type") is None else
                                     CalibrationSampleType(str(raw["sample_type"]))),
                        expected_identity=(None if raw.get("expected_identity") is None else
                                           str(raw["expected_identity"])),
                        calibration_session_id=(
                            None if raw.get("calibration_session_id") is None else
                            str(raw["calibration_session_id"])),
                        evaluation_sample_id=(
                            None if raw.get("evaluation_sample_id") is None else
                            str(raw["evaluation_sample_id"])),
                        condition_id=(None if raw.get("condition_id") is None else
                                      str(raw["condition_id"])),
                        illumination=(None if raw.get("illumination") is None else
                                      CalibrationIllumination(str(raw["illumination"]))),
                        distance=(None if raw.get("distance") is None else
                                  CalibrationDistance(str(raw["distance"]))),
                        pose=(None if raw.get("pose") is None else
                              CalibrationPose(str(raw["pose"]))),
                    )
                    staged.setdefault(identity, []).append(CalibrationSample(vector, metadata))
                if keys != set(archive.files):
                    raise CalibrationDatasetError("calibration archive has unexpected arrays")
        except CalibrationDatasetError:
            raise
        except Exception as exc:
            raise CalibrationDatasetError("calibration dataset validation failed") from exc
        if len(staged) > self.limits.max_identities:
            raise CalibrationDatasetError("calibration identity limit exceeded")
        return {key: tuple(values) for key, values in staged.items()}

    def delete_session(
        self, manifest_path: Path, npz_path: Path, images_directory: Path
    ) -> SessionDeletionResult:
        """Delete known artifacts. This does not claim physical secure erasure."""
        self._require_enabled()
        targets = [manifest_path, npz_path]
        if images_directory.exists() and images_directory.is_dir():
            targets.extend(sorted(path for path in images_directory.rglob("*") if path.is_file()))
        deleted: list[Path] = []
        missing: list[Path] = []
        for path in targets:
            if path.exists() and path.is_file():
                path.unlink()
                deleted.append(path)
            else:
                missing.append(path)
        if images_directory.exists() and images_directory.is_dir():
            for directory in sorted(
                (path for path in images_directory.rglob("*") if path.is_dir()), reverse=True
            ):
                directory.rmdir()
            images_directory.rmdir()
        return SessionDeletionResult(tuple(deleted), tuple(missing))

    def _require_enabled(self) -> None:
        if not self.enabled:
            raise CalibrationDatasetError("calibration persistence is disabled")


def require_capture_consent(*, save_data: bool, save_images: bool, consent_confirmed: bool) -> None:
    if (save_data or save_images) and not consent_confirmed:
        raise ConsentRequiredError("--consent-confirmed is required when saving calibration artifacts")


def _validated_vector(value: object, max_dimension: int) -> np.ndarray:
    vector = np.array(value, dtype=np.float32, order="C", copy=True)
    if vector.ndim != 1 or vector.size <= 0 or vector.size > max_dimension:
        raise CalibrationDatasetError("invalid calibration embedding dimension")
    if not np.isfinite(vector).all():
        raise CalibrationDatasetError("invalid calibration embedding values")
    vector.setflags(write=False)
    return vector


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as exc:
        raise CalibrationDatasetError("could not read calibration artifact") from exc
    return digest.hexdigest()


def _temporary(target: Path) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    os.close(descriptor)
    return Path(name)
