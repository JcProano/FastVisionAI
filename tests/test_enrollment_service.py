from __future__ import annotations

import unittest

import numpy as np

from src.engine.alignment import AlignmentQuality
from src.engine.enrollment import EnrollmentCause, EnrollmentPolicy, EnrollmentService, EnrollmentStatus
from src.engine.gallery import FaceGallery, FaceIdentity
from tests.test_face_gallery import GalleryTestCase


class FailingGallery(FaceGallery):
    def __init__(self, rollback_fails=False):
        super().__init__(); self.calls = 0; self.rollback_fails = rollback_fails

    def add_template(self, person_id, embedding, source_reference=None):
        self.calls += 1
        if self.calls == 2:
            raise RuntimeError("controlled write failure")
        return super().add_template(person_id, embedding, source_reference)

    def remove_identity(self, person_id):
        if self.rollback_fails:
            return False
        return super().remove_identity(person_id)


class EnrollmentServiceTests(GalleryTestCase):
    def vectors(self, quality=AlignmentQuality.VALID):
        values = ([1, .1, 0], [1, .2, .05], [1, .3, -.05], [1, .4, .1])
        output = []
        for index, value in enumerate(values):
            item = self.embedding(value, index=index)
            if quality is not AlignmentQuality.VALID:
                from dataclasses import replace
                item = replace(item, alignment_quality=quality)
            output.append(item)
        return tuple(output)

    def test_successful_registration_with_multiple_templates(self):
        gallery = FaceGallery()
        result = EnrollmentService(gallery, EnrollmentPolicy(min_templates=3)).enroll(
            "temporary", "Temporary", self.vectors()[:3]
        )
        self.assertEqual(result.status, EnrollmentStatus.ENROLLED)
        self.assertEqual(len(result.accepted_templates), 3)
        self.assertEqual(len(gallery.templates("temporary")), 3)

    def test_pairwise_validations_are_disabled_with_none(self):
        policy = EnrollmentPolicy(2, 3, min_pairwise_similarity=None,
                                  max_pairwise_similarity=None)
        result = EnrollmentService(FaceGallery(), policy).enroll(
            "temporary", "Temporary", (self.embedding([1, 0]), self.embedding([0, 1], index=1))
        )
        self.assertEqual(result.status, EnrollmentStatus.ENROLLED)
        self.assertEqual(result.metrics.pairwise_comparisons, 1)

    def test_low_quality_rejected_by_default_and_allowed_explicitly(self):
        rejected = EnrollmentService(FaceGallery(), EnrollmentPolicy(1, 2)).enroll(
            "a", "A", self.vectors(AlignmentQuality.LOW_QUALITY)[:1]
        )
        self.assertEqual(rejected.status, EnrollmentStatus.REJECTED)
        self.assertIn(EnrollmentCause.LOW_QUALITY, rejected.rejected_templates[0].causes)
        allowed = EnrollmentService(
            FaceGallery(), EnrollmentPolicy(1, 2, allow_low_quality=True)
        ).enroll("b", "B", self.vectors(AlignmentQuality.LOW_QUALITY)[:1])
        self.assertEqual(allowed.status, EnrollmentStatus.ENROLLED)

    def test_exact_duplicate_and_pairwise_bounds(self):
        duplicate = self.embedding([1, 0])
        result = EnrollmentService(FaceGallery(), EnrollmentPolicy(2, 4)).enroll(
            "a", "A", (duplicate, duplicate)
        )
        self.assertIn(EnrollmentCause.EXACT_DUPLICATE, result.rejected_templates[0].causes)
        too_close = EnrollmentService(
            FaceGallery(), EnrollmentPolicy(2, 3, max_pairwise_similarity=0.8)
        ).enroll("b", "B", self.vectors()[:2])
        self.assertIn(EnrollmentCause.INSUFFICIENT_DIVERSITY,
                      too_close.rejected_templates[0].causes)
        too_far = EnrollmentService(
            FaceGallery(), EnrollmentPolicy(2, 3, min_pairwise_similarity=0.9)
        ).enroll("c", "C", (self.embedding([1, 0]), self.embedding([0, 1], index=1)))
        self.assertIn(EnrollmentCause.INSUFFICIENT_SIMILARITY,
                      too_far.rejected_templates[0].causes)

    def test_incompatible_model_version_sha_and_dimension(self):
        baseline = self.embedding([1, 0, 0])
        variants = (
            self.embedding([0, 1], index=1),
            self.embedding([0, 1, 0], model="other", index=1),
            self.embedding([0, 1, 0], version="v2", index=1),
            self.embedding([0, 1, 0], sha="other", index=1),
        )
        expected = (
            EnrollmentCause.INCOMPATIBLE_DIMENSION, EnrollmentCause.INCOMPATIBLE_MODEL,
            EnrollmentCause.INCOMPATIBLE_VERSION, EnrollmentCause.INCOMPATIBLE_WEIGHTS,
        )
        for variant, cause in zip(variants, expected):
            result = EnrollmentService(FaceGallery(), EnrollmentPolicy(2, 3)).enroll(
                "a", "A", (baseline, variant)
            )
            self.assertIn(cause, result.rejected_templates[0].causes)

    def test_selection_over_max_is_deterministic_and_preserves_input_indices(self):
        policy = EnrollmentPolicy(2, 2)
        first = EnrollmentService(FaceGallery(), policy).enroll("a", "A", self.vectors())
        second = EnrollmentService(FaceGallery(), policy).enroll("a", "A", self.vectors())
        self.assertEqual([item.input_index for item in first.accepted_templates], [0, 1])
        self.assertEqual([item.input_index for item in second.accepted_templates], [0, 1])
        self.assertTrue(all(
            item.causes == (EnrollmentCause.MAX_TEMPLATES_EXCEEDED,)
            for item in first.rejected_templates
        ))

    def test_rejection_leaves_gallery_exactly_unchanged(self):
        gallery = FaceGallery(); gallery.register_identity(FaceIdentity("keep", "Keep"))
        before = (gallery.list_identities(), gallery.templates())
        result = EnrollmentService(gallery, EnrollmentPolicy(3, 4)).enroll(
            "new", "New", self.vectors()[:2]
        )
        self.assertEqual(result.status, EnrollmentStatus.REJECTED)
        self.assertEqual((gallery.list_identities(), gallery.templates()), before)

    def test_successful_and_failed_rollback(self):
        successful = FailingGallery()
        result = EnrollmentService(successful, EnrollmentPolicy(2, 3)).enroll(
            "new", "New", self.vectors()[:2]
        )
        self.assertIn(EnrollmentCause.TRANSACTION_FAILED, result.causes)
        self.assertNotIn(EnrollmentCause.ROLLBACK_FAILED, result.causes)
        self.assertEqual(len(successful), 0)

        failed = FailingGallery(rollback_fails=True)
        result = EnrollmentService(failed, EnrollmentPolicy(2, 3)).enroll(
            "new", "New", self.vectors()[:2]
        )
        self.assertIn(EnrollmentCause.ROLLBACK_FAILED, result.causes)
        self.assertNotEqual(len(failed), 0)

    def test_metadata_is_deep_copied(self):
        metadata = {"nested": {"temporary": True}}
        result = EnrollmentService(FaceGallery(), EnrollmentPolicy(1, 2)).enroll(
            "a", "A", self.vectors()[:1], metadata
        )
        metadata["nested"]["temporary"] = False
        self.assertTrue(result.identity.metadata["nested"]["temporary"])

    def test_accepted_template_quality_score_fields_are_optional(self):
        result = EnrollmentService(FaceGallery(), EnrollmentPolicy(1, 2)).enroll(
            "quality-optional", "Temporary", self.vectors()[:1]
        )
        accepted = result.accepted_templates[0]
        self.assertIsNone(accepted.face_quality_score)
        self.assertIsNone(accepted.quality_profile_name)


if __name__ == "__main__": unittest.main()
