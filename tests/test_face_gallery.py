from __future__ import annotations

import unittest

import numpy as np

from src.camera.frame import Frame
from src.engine.alignment import AlignmentQuality
from src.engine.embedding.contracts import FaceEmbedding
from src.engine.gallery import (
    DuplicateIdentityError, DuplicateTemplateError, FaceGallery, FaceIdentity,
    GalleryCompatibilityError,
)


class GalleryTestCase(unittest.TestCase):
    def setUp(self):
        image = np.zeros((10, 10, 3), dtype=np.uint8)
        self.frame = Frame.create(
            image, sequence_id=1, source_name="test", monotonic_timestamp=0, connection_id=1
        )

    def embedding(self, values, *, model="model", version="v1", sha="sha", index=0):
        vector = np.asarray(values, dtype=np.float32)
        vector /= np.linalg.norm(vector)
        return FaceEmbedding(
            self.frame, "run", index, vector, vector.size, 1.0,
            AlignmentQuality.VALID, 1.0, "test", model, version, sha,
        )


class FaceGalleryTests(GalleryTestCase):
    def test_registration_duplicate_and_listing(self):
        gallery = FaceGallery()
        gallery.register_identity(FaceIdentity("b", "Temporary B"))
        gallery.register_identity(FaceIdentity("a", "Temporary A"))
        with self.assertRaises(DuplicateIdentityError):
            gallery.register_identity(FaceIdentity("a", "Other"))
        self.assertEqual([item.person_id for item in gallery.list_identities()], ["a", "b"])

    def test_existing_identity_accepts_distinct_additional_template(self):
        gallery = FaceGallery(); gallery.register_identity(FaceIdentity("a", "Temporary"))
        first = gallery.add_template("a", self.embedding([1, 0, 0]))
        second = gallery.add_template("a", self.embedding([0.9, 0.1, 0]))
        self.assertEqual((first, second), (0, 1))
        self.assertEqual(len(gallery.templates("a")), 2)

    def test_exact_duplicate_template_is_rejected(self):
        gallery = FaceGallery(); gallery.register_identity(FaceIdentity("a", "Temporary"))
        embedding = self.embedding([1, 2, 3])
        gallery.add_template("a", embedding)
        with self.assertRaises(DuplicateTemplateError):
            gallery.add_template("a", embedding)

    def test_removing_identity_removes_templates(self):
        gallery = FaceGallery(); gallery.register_identity(FaceIdentity("a", "Temporary"))
        gallery.add_template("a", self.embedding([1, 0]))
        self.assertTrue(gallery.remove_identity("a"))
        self.assertFalse(gallery.remove_identity("a"))
        self.assertEqual(gallery.templates(), ())

    def test_dimension_model_version_and_sha_must_match(self):
        variants = (
            self.embedding([1, 0, 0]),
            self.embedding([0, 1], model="model"),
            self.embedding([0, 1, 0], model="other"),
            self.embedding([0, 1, 0], version="v2"),
            self.embedding([0, 1, 0], sha="other"),
        )
        for incompatible in variants[1:]:
            gallery = FaceGallery(); gallery.register_identity(FaceIdentity("a", "Temporary"))
            gallery.add_template("a", variants[0])
            with self.assertRaises(GalleryCompatibilityError):
                gallery.add_template("a", incompatible)

    def test_template_is_copied_c_contiguous_and_read_only(self):
        gallery = FaceGallery(); gallery.register_identity(FaceIdentity("a", "Temporary"))
        source = self.embedding([1, 2, 3])
        gallery.add_template("a", source)
        vector = gallery.templates()[0].template.embedding
        self.assertTrue(vector.flags.c_contiguous)
        self.assertFalse(vector.flags.writeable)
        self.assertIsNot(vector, source.embedding)

    def test_invalid_embedding_is_rejected_without_exposing_values(self):
        identity = FaceIdentity("a", "Temporary")
        from src.engine.gallery.contracts import FaceTemplate
        for vector in (np.array([np.nan], np.float32), np.array([2.0], np.float32)):
            with self.assertRaises(ValueError) as context:
                FaceTemplate(identity, vector, 1, "m", "v", "sha")
            self.assertNotIn(str(vector), str(context.exception))


if __name__ == "__main__": unittest.main()
