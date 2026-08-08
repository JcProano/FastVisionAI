from __future__ import annotations

import unittest

from src.engine.gallery import FaceGallery, FaceIdentity, FaceMatcher, MatchPolicy
from src.ui.recognition_session import ExperimentalRecognitionSession
from tests.test_face_gallery import GalleryTestCase


class FailingMatcher(FaceMatcher):
    def match(self, query, gallery):
        raise RuntimeError("controlled matcher failure")


class UIRecognitionTests(GalleryTestCase):
    def session(self, gallery, matcher=None):
        return ExperimentalRecognitionSession(
            gallery, matcher or FaceMatcher(policy=MatchPolicy(False, None))
        )

    def test_empty_gallery_keeps_registration_enabled(self):
        dto, error = self.session(FaceGallery()).query(self.embedding([1, 0]))
        self.assertEqual(dto.message, "Sin candidatos registrados")
        self.assertTrue(dto.registration_enabled)
        self.assertIsNone(error)

    def test_candidate_is_experimental_and_decision_not_evaluated(self):
        gallery = FaceGallery()
        gallery.register_identity(FaceIdentity("temporary", "Temporary 1"))
        gallery.add_template("temporary", self.embedding([1, 0]))
        dto, error = self.session(gallery).query(self.embedding([1, 0]))
        self.assertEqual(dto.message, "Candidato experimental")
        self.assertEqual(dto.automatic_decision, "NOT_EVALUATED")
        self.assertAlmostEqual(dto.similarity, 1.0)
        self.assertIsNone(error)

    def test_matcher_failure_is_recoverable_and_registration_remains_available(self):
        gallery = FaceGallery()
        gallery.register_identity(FaceIdentity("temporary", "Temporary"))
        gallery.add_template("temporary", self.embedding([1, 0]))
        matcher = FailingMatcher(policy=MatchPolicy(False, None))
        dto, error = self.session(gallery, matcher).query(self.embedding([1, 0]))
        self.assertTrue(dto.registration_enabled)
        self.assertEqual(dto.message, "Sin candidatos registrados")
        self.assertIsNotNone(error)
        self.assertTrue(error.recoverable)

    def test_automatic_match_policy_is_prohibited(self):
        with self.assertRaises(ValueError):
            ExperimentalRecognitionSession(
                FaceGallery(), FaceMatcher(policy=MatchPolicy(True, .5))
            )


if __name__ == "__main__":
    unittest.main()
