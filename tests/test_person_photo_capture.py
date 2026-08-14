import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from src.core.person_database import PersonCreateRequest, PersonRepository
from src.engine.gallery import FaceGallery
from src.engine.capture_quality import GuidedCaptureState
from src.ui.live_session import LiveFaceSession
from src.ui.mock_runtime import MockUIRuntimeAdapter
from src.ui.photo_capture import PersonPhotoController
from src.ui.thumbnails import ThumbnailManager
from tests.test_ui_live_session import RejectedGuidedAdapter, controller, wait_until


class Authorization:
    def __init__(self, allowed=True): self.allowed = allowed
    def can(self, _permission): return self.allowed


class PersonPhotoCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repository = PersonRepository(self.root / "people.db"); self.repository.initialize()
        self.person_id = "64308b40-2636-4737-8523-e070ade05331"
        self.repository.create(PersonCreateRequest(
            self.person_id, "1710034065", "Temporary", "Person",
        ))
        self.thumbnails = ThumbnailManager(self.root, Path("thumbs"))

    @staticmethod
    def image_bytes(value=90):
        ok, payload = cv2.imencode(".png", np.full((112, 112, 3), value, np.uint8))
        assert ok
        return payload.tobytes()

    def test_controller_saves_replaces_and_preserves_civil_identity(self):
        service = PersonPhotoController(
            self.repository, self.thumbnails, Authorization(True),
        )
        self.assertFalse(service.begin(self.person_id))
        service.save(self.person_id, self.image_bytes(), replace=False)
        self.assertTrue(service.begin(self.person_id))
        service.save(self.person_id, self.image_bytes(120), replace=True)
        record = self.repository.get_by_person_id(self.person_id)
        self.assertEqual(record.person_id, self.person_id)
        self.assertEqual(record.cedula, "1710034065")

    def test_rbac_denied_and_cancel_does_not_replace_existing_photo(self):
        allowed = PersonPhotoController(self.repository, self.thumbnails, Authorization(True))
        original = allowed.save(self.person_id, self.image_bytes(), replace=False).image_bytes
        denied = PersonPhotoController(self.repository, self.thumbnails, Authorization(False))
        with self.assertRaises(PermissionError): denied.begin(self.person_id)
        with self.assertRaises(PermissionError):
            denied.save(self.person_id, self.image_bytes(150), replace=True)
        self.assertEqual(self.thumbnails.load(self.person_id).image_bytes, original)

    def test_live_capture_uses_one_worker_and_does_not_change_gallery_templates(self):
        gallery, ui = controller(FaceGallery(), target=2)
        photo = PersonPhotoController(self.repository, self.thumbnails, Authorization(True))
        adapter = MockUIRuntimeAdapter(delay=.003, thumbnail_capture_enabled=True)
        session = LiveFaceSession(
            adapter, ui, event_queue_size=64, photo_controller=photo,
        )
        session.start()
        self.assertTrue(session.start_person_photo(self.person_id))
        self.assertTrue(wait_until(lambda: session._photo_person_id == self.person_id))
        frames_before = session.dashboard_telemetry()[0].frames_processed
        self.assertTrue(session.capture_person_photo())
        self.assertTrue(wait_until(lambda: session._pending_photo_bytes is not None))
        self.assertGreater(session.dashboard_telemetry()[0].frames_processed, frames_before)
        self.assertTrue(session.confirm_person_photo())
        self.assertTrue(wait_until(lambda: session._photo_person_id is None))
        session.close()
        self.assertTrue(self.thumbnails.exists(self.person_id))
        self.assertEqual(len(gallery.list_identities()), 0)
        self.assertEqual(len(gallery.templates()), 0)

    def test_cancel_clears_temporary_photo_without_writing(self):
        _, ui = controller(target=2)
        photo = PersonPhotoController(self.repository, self.thumbnails, Authorization(True))
        session = LiveFaceSession(
            MockUIRuntimeAdapter(delay=.003, thumbnail_capture_enabled=True), ui,
            event_queue_size=64, photo_controller=photo,
        )
        session.start(); session.start_person_photo(self.person_id)
        self.assertTrue(wait_until(lambda: session._photo_person_id is not None))
        session.capture_person_photo()
        self.assertTrue(wait_until(lambda: session._pending_photo_bytes is not None))
        session.cancel_person_photo()
        self.assertTrue(wait_until(lambda: session._photo_person_id is None))
        session.close()
        self.assertFalse(self.thumbnails.exists(self.person_id))

    def test_no_face_multiple_faces_and_low_quality_are_not_captured(self):
        adapters = (
            RejectedGuidedAdapter(GuidedCaptureState.NO_FACE, face_count=0),
            MockUIRuntimeAdapter(delay=.003, multiple_at=set(range(1, 1000)),
                                 thumbnail_capture_enabled=True),
            RejectedGuidedAdapter(GuidedCaptureState.BLURRY, face_count=1),
        )
        for adapter in adapters:
            with self.subTest(adapter=type(adapter).__name__):
                adapter.thumbnail_capture_enabled = True
                _, ui = controller(target=2)
                photo = PersonPhotoController(
                    self.repository, self.thumbnails, Authorization(True),
                )
                session = LiveFaceSession(
                    adapter, ui, event_queue_size=64, photo_controller=photo,
                )
                session.start(); session.start_person_photo(self.person_id)
                self.assertTrue(wait_until(lambda: session._photo_person_id is not None))
                session.capture_person_photo()
                self.assertFalse(wait_until(
                    lambda: session._pending_photo_bytes is not None, .08,
                ))
                session.cancel_person_photo(); session.close()


if __name__ == "__main__":
    unittest.main()
