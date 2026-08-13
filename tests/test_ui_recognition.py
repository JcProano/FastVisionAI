from __future__ import annotations

import dataclasses
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.engine.gallery import FaceGallery, FaceIdentity, FaceMatcher, MatchPolicy
from src.engine.recognition import (
    RecognitionPolicy, RecognitionService, RecognitionState,
)
from src.ui.contracts import UIErrorCode
from src.ui.main import build_controller
from src.ui.recognition_session import ExperimentalRecognitionSession
from tests.test_face_gallery import GalleryTestCase


class FailingMatcher(FaceMatcher):
    def match(self, query, gallery):
        raise RuntimeError("controlled matcher failure")


class StubRecognitionService:
    def __init__(self, source: RecognitionService, state: RecognitionState) -> None:
        self.gallery = source.gallery
        self.policy = source.policy
        self.source = source
        self.state = state

    def recognize(self, embedding, score=None):
        return dataclasses.replace(
            self.source.recognize(embedding, score), state=self.state, evaluated=True
        )


class UIRecognitionTests(GalleryTestCase):
    def service(self, gallery, matcher=None, policy=None):
        policy = policy or RecognitionPolicy(top_k=1)
        matcher = matcher or FaceMatcher(top_k=policy.top_k, policy=MatchPolicy(False, None))
        return RecognitionService(gallery, matcher, policy)

    def session(self, gallery, matcher=None):
        return ExperimentalRecognitionSession(self.service(gallery, matcher))

    def test_no_gallery_keeps_registration_enabled(self):
        dto, error = self.session(FaceGallery()).query(self.embedding([1, 0]))
        self.assertEqual(dto.message, "Sin candidatos registrados")
        self.assertEqual(dto.recognition_state, "NO_GALLERY")
        self.assertTrue(dto.registration_enabled)
        self.assertIsNone(error)

    def test_incompatible_keeps_registration_enabled(self):
        gallery = FaceGallery()
        gallery.register_identity(FaceIdentity("temporary", "Temporary 1"))
        gallery.add_template("temporary", self.embedding([1, 0]))
        dto, error = self.session(gallery).query(self.embedding([1, 0], model="other"))
        self.assertEqual(dto.message, "Sin candidatos compatibles")
        self.assertEqual(dto.recognition_state, "INCOMPATIBLE")
        self.assertTrue(dto.registration_enabled)
        self.assertIsNone(error)

    def test_candidate_is_experimental_and_decision_not_evaluated(self):
        gallery = FaceGallery()
        gallery.register_identity(FaceIdentity("temporary", "Temporary 1"))
        gallery.add_template("temporary", self.embedding([1, 0]))
        dto, error = self.session(gallery).query(self.embedding([1, 0]))
        self.assertEqual(dto.message, "Candidato experimental")
        self.assertEqual(dto.automatic_decision, "NOT_EVALUATED")
        self.assertEqual(dto.recognition_state, "NOT_EVALUATED")
        self.assertAlmostEqual(dto.similarity, 1.0)
        self.assertIsNone(error)

    def test_service_failure_is_recoverable_and_registration_remains_available(self):
        gallery = FaceGallery()
        gallery.register_identity(FaceIdentity("temporary", "Temporary"))
        gallery.add_template("temporary", self.embedding([1, 0]))
        matcher = FailingMatcher(top_k=1, policy=MatchPolicy(False, None))
        dto, error = self.session(gallery, matcher).query(self.embedding([1, 0]))
        self.assertTrue(dto.registration_enabled)
        self.assertEqual(dto.message, "Sin candidatos compatibles")
        self.assertEqual(dto.recognition_state, "NOT_EVALUATED")
        self.assertIsNotNone(error)
        self.assertEqual(error.operation, UIErrorCode.MATCHER_ERROR)
        self.assertTrue(error.recoverable)

    def test_future_decision_states_are_blocked_by_experimental_ui(self):
        gallery = FaceGallery()
        gallery.register_identity(FaceIdentity("temporary", "Temporary"))
        gallery.add_template("temporary", self.embedding([1, 0]))
        base = self.service(gallery)
        for state in (RecognitionState.MATCH, RecognitionState.UNKNOWN,
                      RecognitionState.AMBIGUOUS):
            session = ExperimentalRecognitionSession(StubRecognitionService(base, state))
            dto, error = session.query(self.embedding([1, 0]))
            self.assertEqual(dto.message, "Sin candidatos compatibles")
            self.assertEqual(dto.recognition_state, "NOT_EVALUATED")
            self.assertTrue(dto.registration_enabled)
            self.assertIsNotNone(error)
            self.assertNotIn("reconoc", dto.message.casefold())
            self.assertNotIn("desconoc", dto.message.casefold())

    def test_automatic_or_threshold_configuration_is_prohibited(self):
        gallery = FaceGallery()
        policies = (
            RecognitionPolicy(True, .5, None, 1),
            RecognitionPolicy(False, .5, None, 1),
            RecognitionPolicy(False, None, .1, 1),
        )
        for policy in policies:
            service = self.service(gallery, policy=policy)
            with self.assertRaises(ValueError):
                ExperimentalRecognitionSession(service)

    def test_composition_root_rejects_automatic_threshold_or_margin(self):
        base = json.loads(Path("config/local_face_validation.dev.json").read_text(
            encoding="utf-8"
        ))
        invalid_values = (
            ("automatic_decision_enabled", True),
            ("match_threshold", .5),
            ("ambiguity_margin", .1),
        )
        for key, value in invalid_values:
            config = json.loads(json.dumps(base))
            config["recognition"][key] = value
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "config.json"
                path.write_text(json.dumps(config), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, key):
                    build_controller(path)

    def test_gallery_property_is_read_only_and_public_dto_is_safe(self):
        gallery = FaceGallery()
        session = self.session(gallery)
        self.assertIs(session.gallery, gallery)
        with self.assertRaises(AttributeError):
            session.gallery = FaceGallery()
        dto, _ = session.query(self.embedding([1, 0]))
        forbidden = {"embedding", "template", "model", "image", "frame"}
        self.assertTrue({field.name for field in dataclasses.fields(dto)}.isdisjoint(forbidden))
        self.assertFalse(any(isinstance(value, np.ndarray) for value in dataclasses.astuple(dto)))

    def test_shared_gallery_update_with_five_templates_is_immediately_visible(self):
        gallery = FaceGallery()
        session = self.session(gallery)
        gallery.register_identity(FaceIdentity("temporary", "Temporary 1"))
        for index in range(5):
            gallery.add_template(
                "temporary", self.embedding([1.0, 0.01 * index + 0.001]),
            )
        self.assertIs(session.gallery, gallery)
        self.assertEqual(len(gallery.templates()), 5)
        dto, error = session.query(self.embedding([1.0, 0.001]))
        self.assertEqual(dto.candidate_person_id, "temporary")
        self.assertEqual(dto.recognition_state, "NOT_EVALUATED")
        self.assertIsNone(error)


if __name__ == "__main__":
    unittest.main()
