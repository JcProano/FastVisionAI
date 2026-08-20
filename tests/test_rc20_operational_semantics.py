import unittest
from types import SimpleNamespace

from src.ui.contracts import MonitoringDTO, UIState
from src.ui.operational_semantics import (
    OperationalPresentationState, operational_presentation_state, operational_title,
)
from src.ui.web_dashboard.controller import WebDashboardController


def monitoring(state="NO_GALLERY", ui_state=UIState.MONITORING):
    return MonitoringDTO(ui_state, "GALERÍA VACÍA", None, None, "NOT_EVALUATED", True,
                         recognition_state=state, evaluated=False)


class RC20OperationalSemanticsTests(unittest.TestCase):
    def classify(self, camera="CONNECTED", frame=True, gallery=1, dto=None):
        return operational_presentation_state(
            camera_state=camera, frame_available=frame,
            monitoring=dto or monitoring(), gallery_identity_count=gallery,
        )

    def test_disconnected_camera_with_identity_never_reports_empty_gallery(self):
        state=self.classify(camera="DISCONNECTED",gallery=1)
        self.assertIs(state,OperationalPresentationState.CAMERA_DISCONNECTED)
        self.assertEqual(operational_title(state),"CÁMARA DESCONECTADA")
        self.assertNotEqual(operational_title(state),"GALERÍA VACÍA")

    def test_connected_without_frame_and_valid_frame_without_face_are_distinct(self):
        self.assertIs(self.classify(frame=False),OperationalPresentationState.VIDEO_NO_SIGNAL)
        self.assertIs(self.classify(dto=monitoring("NOT_EVALUATED",UIState.NO_FACE)),
                      OperationalPresentationState.NO_FACE)

    def test_gallery_empty_requires_connected_frame_and_real_zero_count(self):
        self.assertIs(self.classify(gallery=0),
                      OperationalPresentationState.GALLERY_UNREGISTERED)
        self.assertIs(self.classify(gallery=0,dto=monitoring(ui_state=UIState.NO_FACE)),
                      OperationalPresentationState.NO_FACE)
        self.assertIs(self.classify(gallery=1),
                      OperationalPresentationState.RECOGNITION_UNAVAILABLE)

    def test_web_consumes_the_same_shared_operational_result_as_tk(self):
        dto=monitoring();shared=self.classify(camera="DISCONNECTED",gallery=1,dto=dto)
        controller=WebDashboardController(
            lambda:None,presentation_provider=lambda:dto,
            operational_state_provider=lambda _dto:shared,
        )
        payload=controller.api("/api/presentation")
        self.assertEqual(payload["title"],operational_title(shared))
        self.assertNotEqual(payload["title"],"GALERÍA VACÍA")


if __name__ == "__main__":unittest.main()
