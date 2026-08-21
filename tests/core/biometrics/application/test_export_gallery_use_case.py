import unittest
from pathlib import Path

from src.core.biometrics.application import ExportGalleryUseCase
from tests.core.biometrics.fakes import (
    FakeGalleryPersistence,
    InMemoryBiometricGallery,
)


class ExportGalleryUseCaseTests(unittest.TestCase):
    def test_delegates_explicit_export_to_the_persistence_port(self) -> None:
        persistence = FakeGalleryPersistence()
        gallery = InMemoryBiometricGallery()
        manifest = Path("gallery.json")
        archive = Path("gallery.npz")

        ExportGalleryUseCase(persistence).execute(
            gallery, manifest, archive, overwrite=True
        )

        self.assertEqual(
            persistence.export_calls,
            [(gallery, manifest, archive, True)],
        )


if __name__ == "__main__":
    unittest.main()
