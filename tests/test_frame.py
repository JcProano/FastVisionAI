from __future__ import annotations

import unittest

import numpy as np

from src.camera.frame import Frame


class FrameTests(unittest.TestCase):
    def test_encapsulates_image_and_metadata(self) -> None:
        image = np.zeros((720, 1280, 3), dtype=np.uint8)
        frame = Frame.create(
            image,
            sequence_id=7,
            source_name="camera",
            monotonic_timestamp=12.5,
            connection_id=2,
        )
        self.assertIs(frame.image, image)
        self.assertEqual((frame.width, frame.height), (1280, 720))
        self.assertEqual(frame.sequence_id, 7)
        self.assertEqual(frame.connection_id, 2)
        self.assertIsNotNone(frame.captured_at.tzinfo)


if __name__ == "__main__":
    unittest.main()
