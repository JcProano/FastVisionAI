from __future__ import annotations

import inspect
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from src.camera.frame import Frame
from src.engine.alignment import AlignedFace, AlignmentQuality, AlignmentStatus
from src.engine.capture_quality import CapturePose, FaceCaptureQualityEvaluator
from src.engine.contracts.detection import BoundingBox, Detection
from src.engine.embedding.contracts import FaceEmbedding
from src.engine.enrollment import EnrollmentPolicy, EnrollmentService
from src.engine.gallery import FaceGallery
from src.engine.gallery.persistence import GalleryPersistence
from src.ui import tk_app
from src.ui.tk_app import ENROLLMENT_ASSET_DIR, ENROLLMENT_POSES
from src.validation.guided_face_capture import load_guided_profile


class RC2217GuidedEnrollmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = load_guided_profile(Path("config/guided_capture.dev.json")).policy

    def frame(self, sequence: int = 1) -> Frame:
        tile = np.indices((112, 112)).sum(axis=0) % 2
        image = np.repeat((tile * 180 + 40).astype(np.uint8)[..., None], 3, axis=2)
        return Frame(image, sequence, "rc22.17", datetime.now(timezone.utc),
                     float(sequence), 112, 112, 1)

    def face(self, *, confidence: float = .9, ratio: float = 0,
             sequence: int = 1) -> AlignedFace:
        frame = self.frame(sequence)
        nose_x = .5 + ratio * .3
        landmarks = ((.35, .4), (.65, .4), (nose_x, .52), (.4, .68), (.6, .68))
        return AlignedFace(
            frame, frame.image, BoundingBox(.2, .15, .8, .85, True), landmarks,
            np.eye(2, 3), np.eye(2, 3), 0, confidence, "run",
            AlignmentStatus.ALIGNED, AlignmentQuality.VALID, None, 1.0,
            .12, .2, 1.0,
        )

    def embedding(self, face: AlignedFace) -> FaceEmbedding:
        vector = np.asarray((1.0, face.frame.sequence_id / 100), dtype=np.float32)
        vector /= np.linalg.norm(vector)
        return FaceEmbedding(face.frame, "run", 0, vector, 2, 1.0,
                             AlignmentQuality.VALID, 1.0, "mock", "arc", "1", "sha")

    def evaluate(self, confidence: float, ratio: float, requested: CapturePose):
        face = self.face(confidence=confidence, ratio=ratio)
        detection = Detection(face.bounding_box, "face", confidence, 0)
        return FaceCaptureQualityEvaluator(self.policy).evaluate(
            (detection,), (face,), requested, "run", 1.0, self.embedding,
        )

    def test_enrollment_confidence_boundary(self):
        self.assertFalse(self.evaluate(.64, 0, CapturePose.FRONTAL).accepted)
        self.assertTrue(self.evaluate(.65, 0, CapturePose.FRONTAL).accepted)

    def test_operational_pose_ranges_have_no_dead_zone(self):
        cases = (
            (0, CapturePose.FRONTAL),
            (-.11, CapturePose.SLIGHT_LEFT),
            (-.36, CapturePose.SLIGHT_LEFT),
            (.11, CapturePose.SLIGHT_RIGHT),
            (.36, CapturePose.SLIGHT_RIGHT),
        )
        for ratio, pose in cases:
            with self.subTest(ratio=ratio, pose=pose):
                result = self.evaluate(.9, ratio, pose)
                self.assertEqual(result.estimated_pose, pose)
                self.assertTrue(result.accepted)
        self.assertEqual(
            self.evaluate(.9, .43, CapturePose.SLIGHT_RIGHT).estimated_pose,
            CapturePose.UNKNOWN,
        )

    def test_multiple_faces_are_rejected(self):
        face = self.face()
        detection = Detection(face.bounding_box, "face", .9, 0)
        result = FaceCaptureQualityEvaluator(self.policy).evaluate(
            (detection, detection), (), CapturePose.FRONTAL, "run", 1, self.embedding,
        )
        self.assertFalse(result.accepted)
        self.assertEqual(result.primary_state.value, "multiple_faces")

    def test_checklist_always_contains_five_statuses(self):
        checklist = tk_app._enrollment_checklist(2, 5)
        for text in ("1 Frontal", "2 Ligero giro izquierda",
                     "3 Ligero giro derecha", "4 Frontal estable", "5 Natural"):
            self.assertIn(text, checklist)
        self.assertEqual(checklist.count("COMPLETADO"), 2)
        self.assertEqual(checklist.count("ACTUAL"), 1)
        self.assertEqual(checklist.count("PENDIENTE"), 2)

    def test_five_fixed_pose_assets_exist(self):
        self.assertEqual(len(ENROLLMENT_POSES), 5)
        for _label, filename in ENROLLMENT_POSES:
            path = ENROLLMENT_ASSET_DIR / filename
            self.assertTrue(path.is_file())
            self.assertGreater(path.stat().st_size, 10_000)

    def test_canvas_is_responsive_and_reuses_shared_rgb_frame(self):
        capture = inspect.getsource(tk_app.LocalFaceTkApp._show_enrollment_capture)
        render = inspect.getsource(tk_app.LocalFaceTkApp._render_enrollment_frame)
        shared = inspect.getsource(tk_app.LocalFaceTkApp.show_rgb_frame)
        self.assertIn('sticky="nsew"', capture)
        self.assertIn('bind("<Configure>"', capture)
        self.assertIn("render_rgb(", render)
        self.assertIn("_latest_enrollment_frame", shared)
        combined = capture + render + shared
        self.assertNotIn("VideoCapture", combined)
        self.assertNotIn("CameraManager", combined)

    def test_persistence_keeps_existing_identity_and_all_ten_templates(self):
        gallery = FaceGallery()
        policy = EnrollmentPolicy(
            min_templates=5, max_templates=5,
            min_pairwise_similarity=None, max_pairwise_similarity=None,
        )
        service = EnrollmentService(gallery, policy)

        def samples(offset: int):
            values = (((1,.05),(1,.12),(1,.20),(1,.29),(1,.39)) if offset == 0 else
                      ((1,-.06),(1,-.14),(1,-.22),(1,-.31),(1,-.41)))
            result=[]
            for index,value in enumerate(values,offset+1):
                face=self.face(sequence=index)
                vector=np.asarray(value,dtype=np.float32);vector/=np.linalg.norm(vector)
                result.append(FaceEmbedding(
                    face.frame,"run",0,vector,2,1.0,AlignmentQuality.VALID,
                    1.0,"mock","arc","1","sha"))
            return tuple(result)

        service.enroll("person-a","Person A",samples(0))
        service.enroll("person-b","Person B",samples(10))
        self.assertEqual(len(gallery.list_identities()),2)
        self.assertEqual(len(gallery.templates()),10)
        with tempfile.TemporaryDirectory() as directory:
            manifest=Path(directory)/"gallery.json";archive=Path(directory)/"gallery.npz"
            persistence=GalleryPersistence(enabled=True)
            persistence.export(gallery,manifest,archive)
            loaded=FaceGallery();persistence.import_into(loaded,manifest,archive)
            self.assertEqual(len(loaded.list_identities()),2)
            self.assertEqual(len(loaded.templates("person-a")),5)
            self.assertEqual(len(loaded.templates("person-b")),5)


if __name__ == "__main__":
    unittest.main()
