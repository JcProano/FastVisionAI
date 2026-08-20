from __future__ import annotations

import unittest
from types import SimpleNamespace

from src.camera.source_discovery import CameraSourceType, parse_discovery_config, redact_url
from src.core.person_database import PersonStatus
from src.engine.gallery import FaceGallery, FaceIdentity
from src.ui.dashboard.professional_controller import _recognition_state
from src.ui.main import storage_synchronization_diagnostic
from src.ui.main import _camera_network_type, _camera_url
from src.ui.web_dashboard.controller import WebDashboardController


class Rc20IpCameraHelpTests(unittest.TestCase):
    def test_camera_page_guides_rtsp_http_and_custom_urls(self):
        page = WebDashboardController(lambda: None).render("/camera").decode("utf-8")
        for text in (
            "AGREGAR CÁMARA IP / CCTV", "NETWORK_RTSP", "HTTP/MJPEG", "URL personalizada",
            "¿Cómo encuentro la URL de mi cámara?", "Hikvision:", "Dahua:", "Reolink:",
            "Axis:", "DroidCam:", "Probar conexión", "ONVIF → RTSP",
        ):
            self.assertIn(text, page)
        self.assertLess(page.index('value="NETWORK_RTSP"'), page.index('value="NETWORK_HTTP"'))

    def test_custom_and_secure_rtsp_urls_are_valid_network_sources(self):
        config = parse_discovery_config({
            "source": "auto", "network_sources": [
                {"id": "secure", "type": "NETWORK_RTSP", "name": "Entrada",
                 "url": "rtsps://admin:secret@192.168.1.50/live"},
                {"id": "custom", "type": "CUSTOM", "name": "Personalizada",
                 "url": "https://camera.example/video"},
            ],
        })
        self.assertEqual(config.network_sources[1].source_type, CameraSourceType.CUSTOM)

    def test_web_validation_requires_allowed_scheme_and_host(self):
        self.assertEqual(_camera_url({"url": "rtsps://camera.local/live"}), "rtsps://camera.local/live")
        with self.assertRaises(ValueError):
            _camera_url({"url": "rtsp://"})
        self.assertEqual(_camera_network_type({"type": "CUSTOM"}), CameraSourceType.CUSTOM)

    def test_credentials_are_redacted_for_presentation(self):
        self.assertEqual(
            redact_url("rtsp://admin:123456@192.168.1.50:554/stream1"),
            "rtsp://***:***@192.168.1.50:554/stream1",
        )

    def test_active_person_without_face_is_valid_and_orphans_are_not(self):
        jean, miguel = "jean", "miguel"
        repository = SimpleNamespace(list=lambda **_kwargs: (
            SimpleNamespace(person_id=jean, status=PersonStatus.ACTIVE),
            SimpleNamespace(person_id=miguel, status=PersonStatus.ACTIVE),
        ))
        gallery = FaceGallery(); gallery.register_identity(FaceIdentity(jean, "Jean"))
        diagnostic = storage_synchronization_diagnostic(repository, gallery, gallery_loaded=True)
        self.assertEqual(diagnostic.active_person_count, 2)
        self.assertEqual(diagnostic.biometric_person_count, 1)
        self.assertEqual(diagnostic.persons_without_face, (miguel,))
        self.assertEqual(diagnostic.orphan_gallery_identity_count, 0)
        self.assertTrue(diagnostic.synchronization_ok)
        gallery.register_identity(FaceIdentity("orphan", "Unknown"))
        self.assertFalse(storage_synchronization_diagnostic(repository, gallery, gallery_loaded=True).synchronization_ok)

    def test_non_decisional_candidate_pipeline_is_operational(self):
        self.assertEqual(
            _recognition_state("INITIALIZED", "NOT_EVALUATED"),
            "OPERATIVO — SIN CALIBRAR",
        )


if __name__ == "__main__":
    unittest.main()
