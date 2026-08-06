from __future__ import annotations

import unittest

from src.engine.enrollment import EnrollmentPolicy, EnrollmentService
from src.engine.gallery import FaceGallery
from src.validation.static_face_enrollment import SYNTHETIC_NOTICE, build_validation_report
from tests.test_face_gallery import GalleryTestCase


class StaticEnrollmentReportTests(GalleryTestCase):
    def test_report_is_explicitly_synthetic(self):
        gallery = FaceGallery()
        policy = EnrollmentPolicy(1, 2)
        result = EnrollmentService(gallery, policy).enroll(
            "temporary", "Temporary", (self.embedding([1, 0]),),
            {"synthetic_validation": True},
        )
        report = build_validation_report([result], gallery, policy)
        self.assertTrue(report["synthetic_validation"])
        self.assertEqual(report["notice"], SYNTHETIC_NOTICE)
        self.assertNotIn("embedding", str(report).lower())


if __name__ == "__main__": unittest.main()
