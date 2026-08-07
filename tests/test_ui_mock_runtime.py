from __future__ import annotations

import unittest

from src.engine.capture_quality import CapturePose, GuidedCaptureState
from src.ui.mock_runtime import MockUIRuntimeAdapter
from src.ui.runtime_adapter import CameraAdapterError, InferenceAdapterError


class MockUIRuntimeTests(unittest.TestCase):
    def test_mock_produces_transient_visual_and_single_face_embedding(self):
        adapter = MockUIRuntimeAdapter(delay=0)
        self.assertTrue(adapter.open())
        step = adapter.process(CapturePose.FRONTAL)
        self.assertEqual(step.face_count, 1)
        self.assertTrue(step.guided.accepted)
        self.assertIsNotNone(step.guided.embedding)
        self.assertEqual(len(step.visual.rgb_bytes), step.visual.width * step.visual.height * 3)
        adapter.close()
        self.assertTrue(adapter.closed)

    def test_mock_faults_and_multiple_faces_are_deterministic(self):
        adapter = MockUIRuntimeAdapter(
            fail_camera_at={1}, fail_inference_at={2}, multiple_at={3}, delay=0
        )
        adapter.open()
        with self.assertRaises(CameraAdapterError):
            adapter.process(CapturePose.FRONTAL)
        with self.assertRaises(InferenceAdapterError):
            adapter.process(CapturePose.FRONTAL)
        multiple = adapter.process(CapturePose.FRONTAL)
        self.assertEqual(multiple.face_count, 2)
        self.assertEqual(multiple.guided.primary_state, GuidedCaptureState.MULTIPLE_FACES)
        self.assertIsNone(multiple.guided.embedding)


if __name__ == "__main__":
    unittest.main()
