import unittest
from pathlib import Path

from src.core.biometrics.application import ImportGalleryUseCase
from tests.core.biometrics.fakes import (
    FakeGalleryPersistence,
    InMemoryBiometricGallery,
)


class ImportGalleryUseCaseTests(unittest.TestCase):
    def test_delegates_transactional_import_to_the_persistence_port(self) -> None:
        persistence = FakeGalleryPersistence()
        gallery = InMemoryBiometricGallery()
        manifest = Path("gallery.json")
        archive = Path("gallery.npz")

        ImportGalleryUseCase(persistence).execute(gallery, manifest, archive)

        self.assertEqual(
            persistence.import_calls,
            [(gallery, manifest, archive)],
        )


if __name__ == "__main__":
    unittest.main()
