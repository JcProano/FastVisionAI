"""Analyze an explicitly persisted calibration dataset without identity decisions."""

from __future__ import annotations

import argparse
import json
import logging
import uuid
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

import numpy as np

from src.core.config_manager import PROJECT_ROOT
from src.engine.calibration.contracts import CalibrationPolicy, CalibrationSample
from src.engine.calibration.dataset import CalibrationDatasetError, CalibrationDatasetStore
from src.engine.calibration.service import CalibrationService

LOGGER = logging.getLogger(__name__)
MANIFEST_NAME = "manifest.json"
ARCHIVE_NAME = "embeddings.npz"


def load_calibration_input(
    input_path: Path,
    store: CalibrationDatasetStore | None = None,
) -> dict[str, tuple[CalibrationSample, ...]]:
    """Load one session or merge immediate session directories deterministically.

    Repeated temporary identities are intentionally combined across sessions. Each
    sample keeps its original ``session_id`` metadata. A child with neither expected
    artifact is ignored with a warning; a child with only one artifact is corrupt.
    """

    dataset_store = store or CalibrationDatasetStore(enabled=True)
    if not input_path.is_dir():
        raise CalibrationDatasetError("calibration input must be an existing directory")
    direct_manifest = input_path / MANIFEST_NAME
    direct_archive = input_path / ARCHIVE_NAME
    if direct_manifest.exists() or direct_archive.exists():
        if not direct_manifest.is_file() or not direct_archive.is_file():
            raise CalibrationDatasetError(
                f"incomplete calibration session: {input_path.name}"
            )
        sessions = (input_path,)
    else:
        discovered: list[Path] = []
        for child in sorted(input_path.iterdir(), key=lambda item: item.name):
            if not child.is_dir():
                LOGGER.warning("Ignoring non-session entry: %s", child.name)
                continue
            manifest = child / MANIFEST_NAME
            archive = child / ARCHIVE_NAME
            if manifest.is_file() and archive.is_file():
                discovered.append(child)
            elif manifest.exists() or archive.exists():
                raise CalibrationDatasetError(
                    f"incomplete calibration session: {child.name}"
                )
            else:
                LOGGER.warning("Ignoring non-session directory: %s", child.name)
        if not discovered:
            raise CalibrationDatasetError("no calibration sessions were found")
        sessions = tuple(discovered)

    merged: defaultdict[str, list[CalibrationSample]] = defaultdict(list)
    expected_provenance: tuple[int, str, str, str] | None = None
    for session in sessions:
        try:
            groups = dataset_store.load(session / MANIFEST_NAME, session / ARCHIVE_NAME)
        except CalibrationDatasetError as exc:
            raise CalibrationDatasetError(
                f"corrupt calibration session '{session.name}': {exc}"
            ) from exc
        for identity in sorted(groups):
            for sample in groups[identity]:
                provenance = _sample_provenance(sample)
                if expected_provenance is None:
                    expected_provenance = provenance
                elif provenance != expected_provenance:
                    raise CalibrationDatasetError(
                        f"incompatible model provenance in calibration session '{session.name}'"
                    )
                merged[identity].append(sample)
    return {identity: tuple(merged[identity]) for identity in sorted(merged)}


def _sample_provenance(sample: CalibrationSample) -> tuple[int, str, str, str]:
    vector = np.asarray(sample.embedding)
    return (
        int(vector.size), sample.metadata.model, sample.metadata.version,
        sample.metadata.weights_sha256,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze face calibration similarities")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--thresholds", type=float, nargs="+", required=True)
    parser.add_argument("--max-impostor-pairs", type=int)
    parser.add_argument("--impostor-sampling-seed", type=int, default=0)
    args = parser.parse_args()
    root = args.input if args.input.is_absolute() else PROJECT_ROOT / args.input
    groups = load_calibration_input(root)
    policy = CalibrationPolicy(
        max_impostor_pairs=args.max_impostor_pairs,
        impostor_sampling_seed=args.impostor_sampling_seed,
    )
    report = CalibrationService(policy).calibrate(
        groups, args.thresholds, f"calibration-analysis-{uuid.uuid4()}",
        synthetic_validation=False,
    )
    # asdict(report) contains statistics and provenance only, never vectors.
    print(json.dumps(asdict(report), indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
