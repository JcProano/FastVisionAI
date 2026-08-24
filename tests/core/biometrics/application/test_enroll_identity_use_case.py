import unittest

from src.core.biometrics.application import EnrollIdentityUseCase
from src.core.biometrics.domain import (
    EnrollmentCause,
    EnrollmentPolicy,
    EnrollmentStatus,
)
from tests.core.biometrics.fakes import (
    FakeEmbedding,
    FakeEmbeddingMath,
    FakeIdentityFactory,
    InMemoryBiometricGallery,
)


class EnrollIdentityUseCaseTests(unittest.TestCase):
    def make(self, gallery=None):
        gallery = gallery or InMemoryBiometricGallery()
        return gallery, EnrollIdentityUseCase(
            gallery,
            FakeIdentityFactory(),
            FakeEmbeddingMath(),
            EnrollmentPolicy(min_templates=2, max_templates=3),
            monotonic=lambda: 1.0,
        )

    def test_enrolls_valid_batch_transactionally(self) -> None:
        gallery, use_case = self.make()

        result = use_case.execute(
            "person-1",
            "Ada Lovelace",
            (FakeEmbedding(key="one"), FakeEmbedding(face_index=1, key="two")),
        )

        self.assertIs(result.status, EnrollmentStatus.ENROLLED)
        self.assertEqual(len(gallery.templates("person-1")), 2)
        self.assertEqual(
            tuple(item.gallery_template_index for item in result.accepted_templates),
            (0, 1),
        )

    def test_rejects_low_quality_without_writing(self) -> None:
        gallery, use_case = self.make()

        result = use_case.execute(
            "person-1",
            "Ada Lovelace",
            (
                FakeEmbedding(key="one"),
                FakeEmbedding(
                    face_index=1, key="two", alignment_quality="low_quality"
                ),
            ),
        )

        self.assertIs(result.status, EnrollmentStatus.REJECTED)
        self.assertIn(
            EnrollmentCause.INSUFFICIENT_ACCEPTED_TEMPLATES, result.causes
        )
        self.assertEqual(gallery.list_identities(), ())

    def test_compensates_a_failed_template_write(self) -> None:
        gallery = InMemoryBiometricGallery()
        gallery.fail_add = True
        gallery, use_case = self.make(gallery)

        result = use_case.execute(
            "person-1",
            "Ada Lovelace",
            (FakeEmbedding(key="one"), FakeEmbedding(face_index=1, key="two")),
        )

        self.assertIs(result.status, EnrollmentStatus.REJECTED)
        self.assertIn(EnrollmentCause.TRANSACTION_FAILED, result.causes)
        self.assertNotIn(EnrollmentCause.ROLLBACK_FAILED, result.causes)
        self.assertEqual(gallery.list_identities(), ())


if __name__ == "__main__":
    unittest.main()
