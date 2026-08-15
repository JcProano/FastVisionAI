import unittest

from src.ui.photo_capture import AutomaticPhotoPolicy, AutomaticPhotoSelector


class AutomaticPhotoCaptureTests(unittest.TestCase):
    def selector(self):
        clock = [10.0]
        value = AutomaticPhotoSelector(
            AutomaticPhotoPolicy(stability_frames=3, countdown_seconds=2),
            monotonic=lambda: clock[0],
        )
        return value, clock

    def test_no_face_multiple_faces_and_low_quality_reset_stability(self):
        selector, _ = self.selector()
        selector.observe(valid=True, image_bytes=b"candidate", quality_score=80,
                         rejection_message="")
        for message in ("Buscando rostro...", "Se detectaron varios rostros.",
                        "Calidad insuficiente."):
            state = selector.observe(valid=False, image_bytes=None, quality_score=None,
                                     rejection_message=message)
            self.assertEqual(state.observations, 0)
            self.assertEqual(state.message, message)
            self.assertIsNone(selector.best_bytes)

    def test_best_frame_replaces_worse_without_accumulating_frames(self):
        selector, _ = self.selector()
        selector.observe(valid=True, image_bytes=b"first", quality_score=70,
                         rejection_message="")
        selector.observe(valid=True, image_bytes=b"best", quality_score=94,
                         rejection_message="")
        selector.observe(valid=True, image_bytes=b"worse", quality_score=82,
                         rejection_message="")
        self.assertEqual(selector.best_bytes, b"best")
        self.assertEqual(selector.best_quality, 94)
        self.assertFalse(hasattr(selector, "frames"))

    def test_stability_countdown_and_automatic_capture(self):
        selector, clock = self.selector()
        first = selector.observe(valid=True, image_bytes=b"one", quality_score=80,
                                 rejection_message="")
        second = selector.observe(valid=True, image_bytes=b"two", quality_score=90,
                                  rejection_message="")
        countdown = selector.observe(valid=True, image_bytes=b"three", quality_score=85,
                                     rejection_message="")
        self.assertEqual((first.observations, second.observations), (1, 2))
        self.assertEqual(countdown.message, "Capturando automáticamente en 2...")
        clock[0] += 1
        self.assertEqual(selector.observe(
            valid=True, image_bytes=b"four", quality_score=88,
            rejection_message="",
        ).message, "Capturando automáticamente en 1...")
        clock[0] += 1
        captured = selector.observe(valid=True, image_bytes=b"five", quality_score=86,
                                    rejection_message="")
        self.assertEqual(captured.message, "Fotografía capturada.")
        self.assertEqual(captured.captured_bytes, b"two")
        self.assertEqual(captured.quality_score, 90)

    def test_reset_discards_only_temporary_candidate(self):
        selector, _ = self.selector()
        selector.observe(valid=True, image_bytes=b"temporary", quality_score=88,
                         rejection_message="")
        selector.reset()
        self.assertIsNone(selector.best_bytes)
        self.assertEqual(selector.observations, 0)


if __name__ == "__main__":
    unittest.main()
