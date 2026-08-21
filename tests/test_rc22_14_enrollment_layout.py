from __future__ import annotations

import inspect
import unittest

from src.ui.tk_app import (
    ENROLLMENT_ASSET_DIR,
    ENROLLMENT_POSES,
    LocalFaceTkApp,
    _enrollment_step_states,
    _enrollment_window_dimensions,
)


class RC2214EnrollmentLayoutTests(unittest.TestCase):
    def test_five_packaged_pose_assets_exist(self):
        self.assertEqual(len(ENROLLMENT_POSES),5)
        for _label,filename in ENROLLMENT_POSES:
            path=ENROLLMENT_ASSET_DIR/filename
            self.assertTrue(path.is_file(),path)
            self.assertEqual(path.suffix,".png")

    def test_visual_states_follow_accepted_samples_only(self):
        self.assertEqual(
            _enrollment_step_states(2,5),
            ("completed","completed","current","pending","pending"),
        )
        self.assertEqual(_enrollment_step_states(5,5),("completed",)*5)

    def test_window_stays_inside_supported_screens(self):
        for screen in ((1280,720),(1366,768),(1920,1080)):
            width,height=_enrollment_window_dimensions(*screen)
            self.assertLessEqual(width,screen[0])
            self.assertLessEqual(height,screen[1])
            self.assertGreaterEqual(width,1200)
            self.assertGreaterEqual(height,650)

    def test_modal_grid_prioritizes_expandable_video(self):
        source=inspect.getsource(LocalFaceTkApp._show_enrollment_capture)
        self.assertIn("shell.columnconfigure(0,weight=3,minsize=700)",source)
        self.assertIn("shell.columnconfigure(1,weight=1,minsize=300)",source)
        self.assertIn("left.rowconfigure(1,weight=1)",source)
        self.assertIn('self._enrollment_video.grid(row=1,column=0,sticky="nsew")',source)
        self.assertIn("for index,(pose_name,asset_name) in enumerate(ENROLLMENT_POSES)",source)

    def test_enrollment_uses_shared_frame_and_no_new_pipeline(self):
        frame_source=inspect.getsource(LocalFaceTkApp.show_rgb_frame)
        modal_source=inspect.getsource(LocalFaceTkApp._show_enrollment_capture)
        self.assertIn("source_rgb_bytes = rgb_bytes",frame_source)
        self.assertIn("enrollment_bytes = render_rgb",frame_source)
        for forbidden in ("VideoCapture","CameraManager(","Runtime(","FaceDetectorPlugin("):
            self.assertNotIn(forbidden,modal_source)
            self.assertNotIn(forbidden,frame_source)


if __name__ == "__main__":
    unittest.main()
