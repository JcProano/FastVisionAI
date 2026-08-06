from __future__ import annotations

import unittest

import numpy as np

from src.engine.gallery import FaceGallery, FaceIdentity, FaceMatcher, MatchDecision, MatchPolicy
from tests.test_face_gallery import GalleryTestCase


class FaceMatcherTests(GalleryTestCase):
    def gallery(self):
        gallery = FaceGallery()
        gallery.register_identity(FaceIdentity("a", "Temporary A"))
        gallery.register_identity(FaceIdentity("b", "Temporary B"))
        return gallery

    def test_empty_gallery(self):
        result = FaceMatcher().match(self.embedding([1, 0]), FaceGallery())
        self.assertEqual(result.candidates, ())
        self.assertIsNone(result.best_candidate)
        self.assertEqual(result.decision, MatchDecision.NOT_EVALUATED)

    def test_self_match_top_k_order_and_score_clamping(self):
        gallery = self.gallery()
        query = self.embedding([1, 0, 0])
        gallery.add_template("a", query)
        gallery.add_template("b", self.embedding([0, 1, 0]))
        result = FaceMatcher(top_k=1).match(query, gallery)
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.best_candidate.identity.person_id, "a")
        self.assertEqual(result.best_candidate.rank, 1)
        self.assertGreaterEqual(result.best_candidate.similarity, -1.0)
        self.assertLessEqual(result.best_candidate.similarity, 1.0)
        self.assertAlmostEqual(result.best_candidate.similarity, 1.0, places=6)
        self.assertEqual(result.decision, MatchDecision.NOT_EVALUATED)

    def test_multiple_templates_remain_template_level_candidates(self):
        gallery = self.gallery()
        gallery.add_template("a", self.embedding([1, 0, 0]))
        gallery.add_template("a", self.embedding([0.9, 0.1, 0]))
        gallery.add_template("b", self.embedding([0, 1, 0]))
        result = FaceMatcher(top_k=3).match(self.embedding([1, 0, 0]), gallery)
        self.assertEqual([item.identity.person_id for item in result.candidates[:2]], ["a", "a"])
        self.assertNotEqual(result.candidates[0].template_index, result.candidates[1].template_index)

    def test_deterministic_tie_break_uses_template_index(self):
        gallery = self.gallery()
        gallery.add_template("b", self.embedding([0, 1, 0]))
        gallery.add_template("a", self.embedding([0, -1, 0]))
        result = FaceMatcher(top_k=2).match(self.embedding([1, 0, 0]), gallery)
        self.assertEqual([item.template_index for item in result.candidates], [0, 1])

    def test_invalid_policy_and_explicit_decisions(self):
        with self.assertRaises(ValueError):
            MatchPolicy(automatic_decision_enabled=True)
        with self.assertRaises(ValueError):
            MatchPolicy(threshold=1.1)
        gallery = self.gallery(); query = self.embedding([1, 0])
        gallery.add_template("a", query)
        match = FaceMatcher(policy=MatchPolicy(True, 0.8)).match(query, gallery)
        no_match = FaceMatcher(policy=MatchPolicy(True, 0.8)).match(
            self.embedding([0, 1]), gallery
        )
        self.assertEqual(match.decision, MatchDecision.MATCH)
        self.assertEqual(no_match.decision, MatchDecision.NO_MATCH)


if __name__ == "__main__": unittest.main()
