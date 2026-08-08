from __future__ import annotations

import tempfile
import unittest
from dataclasses import fields
from pathlib import Path

import numpy as np

from src.engine.alignment import AlignmentQuality
from src.engine.enrollment import EnrollmentPolicy, EnrollmentService
from src.engine.face_quality.contracts import FaceQualityScore, QualityBand
from src.engine.gallery import FaceGallery, FaceIdentity
from src.engine.gallery.persistence import GalleryPersistence
from src.ui.people.contracts import (
    PeopleListDTO, PeopleOperationResultDTO, PersonDetailsDTO, PersonSummaryDTO,
)
from src.ui.people.controller import (
    PeopleManagerController, record_template_quality_scores,
)
from tests.test_face_gallery import GalleryTestCase


class FailingReplaceGallery(FaceGallery):
    def replace_from(self, validated):
        raise RuntimeError("controlled reconstruction failure")


class PeopleManagerTests(GalleryTestCase):
    def score(self, value: float, index: int = 0) -> FaceQualityScore:
        return FaceQualityScore(
            value, 80, 80, 80, 80, 80, 80, 80, 80, 80,
            QualityBand.GOOD, "quality-dev", "1", (), "run", index,
        )

    def manager(self, gallery=None, root=None):
        gallery = gallery or FaceGallery()
        root = root or Path(tempfile.mkdtemp())
        return PeopleManagerController(
            gallery, EnrollmentService(gallery, EnrollmentPolicy(1, 5)),
            GalleryPersistence(enabled=True), root / "gallery.json", root / "gallery.npz",
        )

    def populated(self, gallery=None):
        gallery = gallery or FaceGallery()
        gallery.register_identity(FaceIdentity("p1", "Ada Lovelace", {
            "first_name": "Ada", "last_name": "Lovelace",
            "external_identifier": "EXT-1",
        }))
        gallery.add_template("p1", self.embedding([1, 0, 0]))
        return gallery

    def test_empty_listing_and_case_insensitive_search(self):
        self.assertEqual(self.manager().list_people().people, ())
        gallery = self.populated()
        gallery.register_identity(FaceIdentity("p2", "Grace Hopper", {
            "first_name": "Grace", "last_name": "Hopper",
            "external_identifier": "NAVY-2",
        }))
        gallery.add_template("p2", self.embedding([0, 1, 0], index=1))
        manager = self.manager(gallery)
        for query, expected in (("ADA", "p1"), ("love", "p1"),
                                ("navy", "p2"), ("grace hopper", "p2")):
            self.assertEqual(manager.list_people(query).people[0].person_id, expected)

    def test_edit_is_transactional_person_id_immutable_and_preserves_scores(self):
        gallery = self.populated()
        record_template_quality_scores(gallery, "p1", ((0, self.score(82)),))
        result = self.manager(gallery).update_person("p1", "Augusta", "King", "NEW")
        self.assertTrue(result.success)
        person = gallery.list_identities()[0]
        self.assertEqual(person.person_id, "p1")
        self.assertEqual(person.display_name, "Augusta King")
        summary = self.manager(gallery).details("p1").summary
        self.assertEqual(summary.average_quality, 82)
        self.assertEqual(summary.external_identifier, "NEW")

        failing = FailingReplaceGallery()
        failing.register_identity(person)
        failing.add_template("p1", gallery.templates()[0].template)
        before = (failing.list_identities(), failing.templates())
        failed = self.manager(failing).update_person("p1", "Other", "Name", None)
        self.assertFalse(failed.success)
        self.assertEqual((failing.list_identities(), failing.templates()), before)

    def test_quality_indices_and_unscored_templates_are_explicit(self):
        gallery = self.populated()
        gallery.add_template("p1", self.embedding([.8, .2, 0], index=1))
        gallery.add_template("p1", self.embedding([.7, 0, .3], index=2))
        record_template_quality_scores(gallery, "p1", (
            (0, self.score(80)), (2, self.score(90, 2)),
        ))
        summary = self.manager(gallery).details("p1").summary
        self.assertEqual(summary.scored_template_count, 2)
        self.assertEqual(summary.unscored_template_count, 1)
        self.assertEqual((summary.minimum_quality, summary.average_quality,
                          summary.maximum_quality), (80, 85, 90))
        items = gallery.list_identities()[0].metadata["face_quality_templates"]["items"]
        self.assertEqual([item["template_index"] for item in items], [0, 2])

    def test_delete_requires_confirmation_and_reindexes_remaining_quality(self):
        gallery = self.populated()
        gallery.register_identity(FaceIdentity("p2", "Grace Hopper", {
            "first_name": "Grace", "last_name": "Hopper",
        }))
        gallery.add_template("p2", self.embedding([0, 1, 0], index=1))
        record_template_quality_scores(gallery, "p2", ((1, self.score(75, 1)),))
        manager = self.manager(gallery)
        cancelled = manager.delete_person("p1", confirmed=False)
        self.assertFalse(cancelled.success); self.assertEqual(len(gallery), 2)
        removed = manager.delete_person("p1", confirmed=True)
        self.assertTrue(removed.success); self.assertEqual(removed.affected_templates, 1)
        self.assertEqual(manager.details("p2").summary.average_quality, 75)
        item = gallery.list_identities()[0].metadata["face_quality_templates"]["items"][0]
        self.assertEqual(item["template_index"], 0)

    def test_additional_enrollment_unknown_cancel_success_duplicate_and_incompatible(self):
        gallery = self.populated(); manager = self.manager(gallery)
        self.assertFalse(manager.begin_additional("missing").success)
        manager.begin_additional("p1"); manager.cancel_additional()
        self.assertEqual(len(gallery.templates()), 1)
        manager.begin_additional("p1")
        success = manager.complete_additional(
            "p1", ((self.embedding([.8, .2, 0], index=1), self.score(88, 1)),)
        )
        self.assertTrue(success.success); self.assertEqual(len(gallery.templates()), 2)
        before = gallery.templates()
        manager.begin_additional("p1")
        duplicate = manager.complete_additional("p1", ((self.embedding([1, 0, 0]), None),))
        self.assertFalse(duplicate.success); self.assertEqual(gallery.templates(), before)

        gallery2 = self.populated(); manager2 = self.manager(gallery2)
        manager2.begin_additional("p1")
        incompatible = manager2.complete_additional(
            "p1", ((self.embedding([0, 1, 0], model="other", index=2), None),)
        )
        self.assertFalse(incompatible.success); self.assertEqual(len(gallery2.templates()), 1)

    def test_public_dtos_have_no_biometric_fields_or_arrays(self):
        forbidden = {"embedding", "embeddings", "template", "templates", "image", "model"}
        for contract in (PersonSummaryDTO, PersonDetailsDTO, PeopleListDTO,
                         PeopleOperationResultDTO):
            names = {field.name for field in fields(contract)}
            self.assertTrue(names.isdisjoint(forbidden), (contract.__name__, names & forbidden))
        summary = self.manager(self.populated()).list_people().people[0]
        self.assertFalse(any(isinstance(value, np.ndarray) for value in summary.__dict__.values())
                         if hasattr(summary, "__dict__") else False)


if __name__ == "__main__":
    unittest.main()
