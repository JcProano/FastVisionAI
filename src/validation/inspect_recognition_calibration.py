"""Inspect the gallery and recognition safety state before RC17 capture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.engine.gallery import FaceGallery
from src.engine.gallery.persistence import GalleryPersistence


def inspect(manifest: Path, archive: Path, profile: Path) -> dict[str, object]:
    gallery = FaceGallery()
    GalleryPersistence(enabled=True).import_into(gallery, manifest, archive)
    templates = gallery.templates()
    config = json.loads(profile.read_text(encoding="utf-8"))
    recognition = config["recognition"]
    first = templates[0].template if templates else None
    return {
        "Model": None if first is None else first.model,
        "Version": None if first is None else first.model_version,
        "Weights SHA256": None if first is None else first.weights_sha256,
        "Reference identities": len(gallery.list_identities()),
        "Reference templates": len(templates),
        "Automatic recognition": (
            "ENABLED" if recognition["automatic_decision_enabled"] else "DISABLED"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect RC17 prerequisites")
    parser.add_argument("--gallery-manifest", type=Path, required=True)
    parser.add_argument("--gallery-archive", type=Path, required=True)
    parser.add_argument("--profile", type=Path,
                        default=Path("config/local_face_validation.pc.json"))
    args = parser.parse_args()
    print(json.dumps(inspect(args.gallery_manifest, args.gallery_archive, args.profile), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
