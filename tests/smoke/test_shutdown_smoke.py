from __future__ import annotations
import time,unittest
from src.engine.enrollment import EnrollmentPolicy,EnrollmentService
from src.engine.gallery import FaceGallery,FaceMatcher,MatchPolicy
from src.engine.recognition import RecognitionPolicy,RecognitionService
from src.ui.controller import LocalFaceUIController
from src.ui.enrollment_workflow import LocalEnrollmentWorkflow
from src.ui.live_session import LiveFaceSession
from src.ui.mock_runtime import MockUIRuntimeAdapter
from src.ui.recognition_session import ExperimentalRecognitionSession

class ShutdownSmokeTests(unittest.TestCase):
 def test_headless_mock_shutdown_is_idempotent_and_thread_stops(self):
  gallery=FaceGallery();workflow=LocalEnrollmentWorkflow(gallery,EnrollmentService(gallery,EnrollmentPolicy(1,1)),1);recognition=RecognitionService(gallery,FaceMatcher(policy=MatchPolicy(False,None)),RecognitionPolicy());controller=LocalFaceUIController(ExperimentalRecognitionSession(recognition),workflow);adapter=MockUIRuntimeAdapter(delay=.001);session=LiveFaceSession(adapter,controller);session.start();time.sleep(.02);self.assertTrue(session.close(1));self.assertTrue(session.close(1));self.assertFalse(session.alive);self.assertTrue(adapter.closed)

