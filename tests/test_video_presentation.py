import unittest

import numpy as np

from src.ui.video_presentation import VideoPresentation, contain_size, render_rgb


class VideoPresentationTests(unittest.TestCase):
    def test_small_and_maximized_areas_preserve_aspect_ratio(self):
        self.assertEqual(contain_size(1920, 1080, 400, 300), (400, 225))
        self.assertEqual(contain_size(1920, 1080, 1600, 900), (1600, 900))

    def test_letterbox_and_dynamic_resize_never_deform(self):
        small = contain_size(640, 480, 500, 500)
        wide = contain_size(640, 480, 1000, 400)
        self.assertEqual(small, (500, 375))
        self.assertEqual(wide, (533, 400))
        self.assertAlmostEqual(small[0] / small[1], 4 / 3, places=2)
        self.assertLess(small[1], 500)  # neutral space remains above and below

    def test_rotations_have_expected_dimensions(self):
        image = np.arange(2 * 3 * 3, dtype=np.uint8).reshape((2, 3, 3))
        for rotation, expected in ((0, (3, 2)), (90, (2, 3)),
                                   (180, (3, 2)), (270, (2, 3))):
            with self.subTest(rotation=rotation):
                width, height, payload = render_rgb(
                    image.tobytes(), 3, 2, expected[0], expected[1],
                    VideoPresentation(rotation=rotation),
                )
                self.assertEqual((width, height), expected)
                self.assertEqual(len(payload), width * height * 3)

    def test_crop_is_opt_in_and_presentation_only(self):
        image = np.zeros((100, 200, 3), np.uint8)
        original = image.tobytes()
        width, height, _ = render_rgb(
            original, 200, 100, 1000, 1000,
            VideoPresentation(crop_enabled=True, crop_left_percent=25,
                              crop_right_percent=25),
        )
        self.assertEqual((width, height), (1000, 1000))
        self.assertEqual(image.tobytes(), original)


if __name__ == "__main__":
    unittest.main()
