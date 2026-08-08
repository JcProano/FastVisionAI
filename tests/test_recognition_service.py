from __future__ import annotations

import dataclasses
import unittest

import numpy as np

from src.engine.alignment import AlignmentQuality
from src.engine.face_quality import FaceQualityScore, QualityBand
from src.engine.gallery import FaceGallery, FaceIdentity, FaceMatcher, MatchPolicy
from src.engine.recognition import RecognitionPolicy, RecognitionService, RecognitionState
from tests.test_face_gallery import GalleryTestCase


class RecognitionServiceTests(GalleryTestCase):
    def gallery(self, entries):
        gallery = FaceGallery()
        for person_id, name, vector in entries:
            gallery.register_identity(FaceIdentity(person_id, name))
            gallery.add_template(person_id, self.embedding(vector, index=len(gallery.templates())))
        return gallery

    def service(self, gallery, policy=None, *, top_k=5):
        return RecognitionService(
            gallery, FaceMatcher(top_k=top_k, policy=MatchPolicy(False, None)),
            policy or RecognitionPolicy(top_k=top_k),
        )

    def test_gallery_without_templates_is_no_gallery(self):
        gallery = FaceGallery()
        gallery.register_identity(FaceIdentity("a", "Temporary A"))
        result = self.service(gallery).recognize(self.embedding([1, 0]))
        self.assertEqual(result.state, RecognitionState.NO_GALLERY)
        self.assertFalse(result.evaluated)

    def test_existing_but_incompatible_templates_are_incompatible(self):
        gallery = self.gallery((("a", "Temporary A", [1, 0]),))
        result = self.service(gallery).recognize(self.embedding([1, 0], model="other"))
        self.assertEqual(result.state, RecognitionState.INCOMPATIBLE)
        self.assertEqual(result.candidates, ())

    def test_disabled_policy_returns_informative_candidate_and_top_k(self):
        gallery = self.gallery((
            ("a", "Temporary A", [1, 0, 0]),
            ("b", "Temporary B", [.8, .2, 0]),
            ("c", "Temporary C", [0, 1, 0]),
        ))
        policy = RecognitionPolicy(top_k=2, minimum_quality_score=100.0)
        result = self.service(gallery, policy, top_k=3).recognize(self.embedding([1, 0, 0]))
        self.assertEqual(result.state, RecognitionState.NOT_EVALUATED)
        self.assertFalse(result.evaluated)
        self.assertEqual(len(result.candidates), 2)
        self.assertEqual(result.person_id, "a")

    def test_automatic_policy_requires_explicit_threshold_and_passive_matcher(self):
        with self.assertRaises(ValueError):
            RecognitionPolicy(automatic_decision_enabled=True)
        with self.assertRaises(ValueError):
            RecognitionService(
                FaceGallery(), FaceMatcher(policy=MatchPolicy(True, .5)),
                RecognitionPolicy(top_k=1),
            )

    def test_same_identity_second_template_does_not_create_ambiguity(self):
        gallery = FaceGallery()
        gallery.register_identity(FaceIdentity("a", "Temporary A"))
        gallery.add_template("a", self.embedding([1, 0, 0]))
        gallery.add_template("a", self.embedding([.99, .01, 0], index=1))
        policy = RecognitionPolicy(True, .5, .5, 2, allow_low_quality=True)
        result = self.service(gallery, policy, top_k=2).recognize(self.embedding([1, 0, 0]))
        self.assertEqual(result.state, RecognitionState.MATCH)
        self.assertIsNone(result.second_best_similarity)
        self.assertIsNone(result.margin)

    def test_exact_threshold_is_match(self):
        gallery = self.gallery((("a", "Temporary A", [0.8, 0.6]),))
        query = self.embedding([1, 0])
        threshold = float(np.dot(query.embedding, gallery.templates()[0].template.embedding))
        policy = RecognitionPolicy(True, threshold, None, 1, allow_low_quality=True)
        result = self.service(gallery, policy, top_k=1).recognize(query)
        self.assertEqual(result.state, RecognitionState.MATCH)

    def test_unknown_precedes_ambiguity(self):
        gallery = self.gallery((
            ("a", "Temporary A", [.7, .7, 0]),
            ("b", "Temporary B", [.69, .71, 0]),
        ))
        policy = RecognitionPolicy(True, .99, 1.0, 2, allow_low_quality=True)
        result = self.service(gallery, policy, top_k=2).recognize(self.embedding([1, 0, 0]))
        self.assertEqual(result.state, RecognitionState.UNKNOWN)

    def test_ambiguous_only_between_distinct_identities(self):
        gallery = self.gallery((
            ("a", "Temporary A", [1, 0, 0]),
            ("b", "Temporary B", [.999, .001, 0]),
        ))
        policy = RecognitionPolicy(True, .8, .01, 2, allow_low_quality=True)
        result = self.service(gallery, policy, top_k=2).recognize(self.embedding([1, 0, 0]))
        self.assertEqual(result.state, RecognitionState.AMBIGUOUS)
        self.assertEqual(result.person_id, "a")
        self.assertIsNotNone(result.second_best_similarity)

    def test_insufficient_quality_only_gates_automatic_decision(self):
        gallery = self.gallery((("a", "Temporary A", [1, 0]),))
        low = dataclasses.replace(
            self.embedding([1, 0]), alignment_quality=AlignmentQuality.LOW_QUALITY
        )
        automatic = RecognitionPolicy(True, .5, None, 1, allow_low_quality=False)
        passive = RecognitionPolicy(False, None, None, 1, allow_low_quality=False)
        self.assertEqual(
            self.service(gallery, automatic, top_k=1).recognize(low).state,
            RecognitionState.NOT_EVALUATED,
        )
        passive_result = self.service(gallery, passive, top_k=1).recognize(low)
        self.assertEqual(passive_result.state, RecognitionState.NOT_EVALUATED)
        self.assertIsNotNone(passive_result.primary_candidate)

    def test_minimum_quality_score_is_an_automatic_only_gate(self):
        gallery = self.gallery((("a", "Temporary A", [1, 0]),))
        query = self.embedding([1, 0])
        score = FaceQualityScore(
            69.0, 69.0, 69.0, 69.0, 69.0, 69.0, 69.0, 69.0, 69.0, 69.0,
            QualityBand.ACCEPTABLE, "quality-test", "1.0", (), "run", 0,
        )
        automatic = RecognitionPolicy(True, .5, None, 1, 70.0, True)
        passive = RecognitionPolicy(False, None, None, 1, 70.0, True)
        automatic_result = self.service(gallery, automatic, top_k=1).recognize(query, score)
        passive_result = self.service(gallery, passive, top_k=1).recognize(query, score)
        self.assertEqual(automatic_result.state, RecognitionState.NOT_EVALUATED)
        self.assertFalse(automatic_result.evaluated)
        self.assertEqual(passive_result.state, RecognitionState.NOT_EVALUATED)
        self.assertIsNotNone(passive_result.primary_candidate)

    def test_public_contracts_contain_no_biometric_payloads(self):
        gallery = self.gallery((("a", "Temporary A", [1, 0]),))
        result = self.service(gallery, RecognitionPolicy(top_k=1), top_k=1).recognize(
            self.embedding([1, 0])
        )
        forbidden = {"embedding", "template", "sha", "model", "image", "path"}
        for value in (result, result.primary_candidate, result.quality, *result.candidates):
            names = {field.name.lower() for field in dataclasses.fields(value)}
            self.assertTrue(names.isdisjoint(forbidden))
            self.assertFalse(any(isinstance(item, np.ndarray) for item in dataclasses.astuple(value)))


if __name__ == "__main__":
    unittest.main()
