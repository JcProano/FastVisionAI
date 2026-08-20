from __future__ import annotations

import inspect
import unittest

from src.ui.contracts import MonitoringDTO, UIState
from src.ui.identification import IdentificationPresentationController
from src.ui.main import main
from src.ui.camera_selection_window import CameraSelectionWindow
from src.ui.operational_semantics import (
    OperationalPresentationState, operational_presentation_state,
)
from src.ui.web_dashboard.controller import WebDashboardController, _modal_html


def empty_gallery_face() -> MonitoringDTO:
    return MonitoringDTO(
        UIState.MONITORING, "Sin galería", None, None, "NOT_EVALUATED", True,
        recognition_state="NO_GALLERY", candidate_person_id=None, evaluated=False,
    )


class RC212CameraAndEmptyGalleryTests(unittest.TestCase):
    def test_startup_discovery_is_async_and_never_opens_ip_form(self):
        source=inspect.getsource(main)
        self.assertIn("start_network_camera_discovery",source)
        self.assertIn('name="camera-startup-discovery"',source)
        self.assertIn("if len(available) == 1",source)
        self.assertIn("if tk_enabled",source)
        self.assertNotIn("show_network_form()",source)

    def test_session_selection_does_not_persist_implicitly(self):
        source=inspect.getsource(main)
        use_block=source[source.index("def use_camera"):source.index("def web_camera_probe")]
        self.assertIn("session.switch_camera",use_block)
        self.assertNotIn("set_preferred",use_block)
        chooser=inspect.getsource(CameraSelectionWindow.use_selected)
        self.assertIn("self.preferred.get()",chooser)
        self.assertIn("set_preferred",chooser)

    def test_empty_gallery_with_valid_face_is_unregisterered(self):
        state=operational_presentation_state(
            camera_state="CONNECTED",frame_available=True,
            monitoring=empty_gallery_face(),gallery_identity_count=0,
        )
        self.assertIs(state,OperationalPresentationState.GALLERY_UNREGISTERED)

    def test_empty_gallery_web_offers_register_and_ignore(self):
        dto=empty_gallery_face()
        controller=WebDashboardController(
            lambda:None,presentation_provider=lambda:dto,
            operational_state_provider=lambda _dto:
                OperationalPresentationState.GALLERY_UNREGISTERED,
        )
        value=controller.api("/api/presentation")
        self.assertEqual(value["title"],"PERSONA NO REGISTRADA")
        self.assertNotIn("CANDIDATO BIOMÉTRICO",str(value))
        modal=_modal_html(value)
        self.assertIn("REGISTRAR PERSONA",modal);self.assertIn("IGNORAR",modal)
        controller.action("/api/presentation/ignore",{})
        self.assertFalse(controller.api("/api/presentation")["active"])

    def test_empty_gallery_uses_existing_tk_popup_cooldown_controller(self):
        source=inspect.getsource(IdentificationPresentationController.observe_empty_gallery)
        self.assertIn("_observe_locked",source)
        self.assertIn("NO_GALLERY",source)

    def test_gallery_with_identities_not_evaluated_remains_candidate(self):
        dto=MonitoringDTO(
            UIState.MONITORING,"candidate","Jean",.2,"NOT_EVALUATED",False,
            recognition_state="NOT_EVALUATED",candidate_person_id="jean",evaluated=False,
        )
        state=operational_presentation_state(
            camera_state="CONNECTED",frame_available=True,monitoring=dto,
            gallery_identity_count=1,
        )
        self.assertIs(state,OperationalPresentationState.RECOGNITION_RESULT)

    def test_after_enrollment_count_one_no_longer_uses_empty_gallery_flow(self):
        dto=empty_gallery_face()
        before=operational_presentation_state(
            camera_state="CONNECTED",frame_available=True,monitoring=dto,
            gallery_identity_count=0,
        )
        after=operational_presentation_state(
            camera_state="CONNECTED",frame_available=True,monitoring=dto,
            gallery_identity_count=1,
        )
        self.assertIs(before,OperationalPresentationState.GALLERY_UNREGISTERED)
        self.assertIs(after,OperationalPresentationState.RECOGNITION_UNAVAILABLE)


if __name__ == "__main__":
    unittest.main()
