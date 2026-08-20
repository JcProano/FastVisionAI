from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from src.camera.camera_types import CameraConfig, CameraType
from src.camera.source_discovery import (
    CameraDiscoveryConfig, CameraSelectionController, CameraSourceDiscovery,
    CameraSourceDTO, CameraSourceType, camera_config_for_source,
    classify_camera_source, parse_discovery_config, redact_url, CameraConfigurationPersistence,
)
from src.ui.runtime_adapter import RealUIRuntimeAdapter
from src.core.configuration.validators import redact


class FakeCapture:
    def __init__(self, *, opens=True, reads=True, raises=False):
        self.opens = opens; self.reads = reads; self.raises = raises
        self.released = False; self.source = None

    def set(self, _property, _value): return True
    def open(self, source):
        self.source = source
        if self.raises: raise RuntimeError("probe")
        return self.opens
    def isOpened(self): return self.opens
    def read(self): return self.reads, np.zeros((2, 2, 3), np.uint8) if self.reads else None
    def release(self): self.released = True


class Factory:
    def __init__(self, captures): self.captures = iter(captures); self.created = []
    def __call__(self):
        item = next(self.captures); self.created.append(item); return item


def config(**overrides):
    value = {"source": "auto", "auto_discovery": True, "scan_indices": 10,
             "preferred_source": None, "network_sources": []}
    value.update(overrides)
    return parse_discovery_config(value)


class CameraSourceDiscoveryTests(unittest.TestCase):
    def discovery(self, cfg, captures, existing, names=None):
        factory = Factory(captures)
        service = CameraSourceDiscovery(
            cfg, capture_factory=factory,
            path_exists=lambda path: int(path.name.removeprefix("video")) in existing,
            name_reader=lambda path: (names or {}).get(
                int(path.parent.name.removeprefix("video")), ""
            ),
        )
        return service, factory

    def test_legacy_source_zero_is_unchanged_and_not_scanned(self):
        cfg = parse_discovery_config({"source": 0})
        service, factory = self.discovery(cfg, [], {0})
        self.assertEqual(cfg.source, 0)
        self.assertEqual(service.discover(), ())
        self.assertEqual(factory.created, [])

    def test_auto_with_no_one_and_multiple_cameras(self):
        none, _ = self.discovery(config(scan_indices=3), [], set())
        self.assertEqual(CameraSelectionController(none).refresh().sources, ())
        one, _ = self.discovery(config(scan_indices=3), [FakeCapture()], {2})
        result = CameraSelectionController(one).refresh()
        self.assertEqual(result.selected.source_id, "v4l2:2")
        many, _ = self.discovery(config(scan_indices=3), [FakeCapture(), FakeCapture()], {0, 2})
        result = CameraSelectionController(many).refresh()
        self.assertIsNone(result.selected); self.assertTrue(result.requires_selection)

    def test_missing_zero_valid_two_and_safe_fallback_name(self):
        service, factory = self.discovery(config(scan_indices=4), [FakeCapture()], {2})
        sources = service.discover()
        self.assertEqual(sources[0].details["index"], 2)
        self.assertEqual(sources[0].display_name, "Cámara de video #2")
        self.assertTrue(factory.created[0].released)

    def test_virtual_droidcam_and_obs_names_are_supported_as_v4l2(self):
        service, _ = self.discovery(
            config(scan_indices=2), [FakeCapture(), FakeCapture()], {0, 1},
            {0: "DroidCam", 1: "OBS Virtual Camera"},
        )
        sources = service.discover()
        self.assertEqual([item.display_name for item in sources], ["DroidCam", "OBS Virtual Camera"])
        self.assertTrue(all(item.details["virtual"] for item in sources))

    def test_preferred_source_and_refresh(self):
        service, factory = self.discovery(
            config(scan_indices=3, preferred_source="v4l2:2"),
            [FakeCapture(), FakeCapture(), FakeCapture(), FakeCapture()], {0, 2},
        )
        controller = CameraSelectionController(service)
        first = controller.refresh(); second = controller.refresh()
        self.assertEqual(first.selected.source_id, "v4l2:2")
        self.assertEqual(second.selected.source_id, "v4l2:2")
        self.assertEqual(len(factory.created), 4)

    def test_missing_preferred_allows_session_only_fallback(self):
        service, _ = self.discovery(
            config(scan_indices=3, preferred_source="v4l2:2"), [FakeCapture()], {0},
        )
        result = CameraSelectionController(service).refresh()
        self.assertEqual(result.selected.source_id, "v4l2:0")
        self.assertFalse(result.requires_selection)
        self.assertTrue(result.preferred_unavailable)

    def test_only_the_saved_network_camera_is_probed_at_startup(self):
        cfg = config(auto_discovery=False, preferred_source="primary", network_sources=[
            {"id": "primary", "type": "NETWORK_HTTP", "name": "Principal", "url": "http://cam/main"},
            {"id": "old-droidcam", "type": "NETWORK_HTTP", "name": "DroidCam", "url": "http://cam/old"},
        ])
        primary = FakeCapture(opens=False)
        service, factory = self.discovery(cfg, [primary], set())
        service._probe_network_sources = True
        service._network_source_ids_to_probe = frozenset(("primary",))
        result = CameraSelectionController(service).refresh()
        self.assertIsNone(result.selected)
        self.assertTrue(result.preferred_unavailable)
        self.assertEqual([item.source for item in factory.created], ["http://cam/main"])

    def test_every_probe_releases_on_failure_and_success(self):
        captures = [FakeCapture(raises=True), FakeCapture(opens=False), FakeCapture()]
        service, factory = self.discovery(config(scan_indices=3), captures, {0, 1, 2})
        self.assertEqual(len(service.discover()), 1)
        self.assertTrue(all(item.released for item in factory.created))

    def test_refresh_does_not_open_a_second_capture_for_source_in_use(self):
        factory = Factory([])
        service = CameraSourceDiscovery(
            config(scan_indices=1), capture_factory=factory,
            path_exists=lambda _path: True, name_reader=lambda _path: "Integrated Camera",
            occupied_source_id=lambda: "v4l2:0",
        )
        sources = service.refresh()
        self.assertEqual(sources[0].source_id, "v4l2:0")
        self.assertTrue(sources[0].details["in_use"])
        self.assertEqual(factory.created, [])

    def test_rtsp_http_are_manual_and_credentials_are_absent_from_dtos(self):
        cfg = config(auto_discovery=False, network_sources=[
            {"id": "rtsp-main", "type": "NETWORK_RTSP", "name": "Entrada", "url": "rtsp://user:pass@cam/live"},
            {"id": "mjpeg", "type": "NETWORK_HTTP", "name": "Patio", "url": "http://alice:secret@cam/mjpeg"},
        ])
        service, _ = self.discovery(cfg, [], set())
        sources = service.discover()
        rendered = repr(sources)
        self.assertNotIn("user", rendered); self.assertNotIn("pass", rendered)
        self.assertEqual(camera_config_for_source(sources[0], cfg).camera_type, CameraType.RTSP)
        self.assertEqual(camera_config_for_source(sources[1], cfg).camera_type,
                         CameraType.NETWORK_HTTP)

    def test_network_probe_opens_reads_and_releases(self):
        cfg = config(auto_discovery=False, network_sources=[
            {"id": "ip", "type": "NETWORK_RTSP", "name": "Entrada",
             "url": "rtsp://user:pass@cam/live"},
        ])
        capture = FakeCapture(); service, factory = self.discovery(cfg, [capture], set())
        self.assertTrue(service.probe("ip")); self.assertTrue(capture.released)
        self.assertEqual(capture.source, "rtsp://user:pass@cam/live")
        self.assertNotIn("pass", repr(service.discover()))

    def test_add_network_and_preferred_are_persisted(self):
        service, _ = self.discovery(config(auto_discovery=False), [], set())
        persisted = []
        controller = CameraSelectionController(service, persist_config=lambda value: persisted.append(value) or True)
        source = controller.add_network_source(
            "Entrada", CameraSourceType.NETWORK_HTTP, "http://user:pass@cam/mjpeg",
        )
        controller.set_preferred(source.source_id)
        self.assertEqual(len(persisted), 2)
        self.assertEqual(persisted[-1].source, "auto")
        self.assertTrue(persisted[-1].auto_discovery)
        self.assertEqual(persisted[-1].preferred_source, source.source_id)

    def test_clearing_preference_removes_old_network_primary(self):
        service, _ = self.discovery(config(auto_discovery=False, preferred_source="old-droidcam",
            network_sources=[{"id": "old-droidcam", "type": "NETWORK_HTTP", "name": "DroidCam",
                              "url": "http://cam/old"}]), [], set())
        persisted = []
        controller = CameraSelectionController(service, persist_config=lambda value: persisted.append(value) or True)
        controller.refresh()
        controller.set_preferred(None)
        self.assertIsNone(persisted[-1].preferred_source)
        self.assertEqual(persisted[-1].source, "auto")

    def test_custom_opencv_source_can_be_configured_manually(self):
        cfg = config(auto_discovery=False, network_sources=[
            {"id": "custom", "type": "CUSTOM", "name": "Pipeline personalizado",
             "url": "gst-pipeline-safe-name"},
        ])
        service, _ = self.discovery(cfg, [], set())
        source = service.discover()[0]
        self.assertEqual(source.source_type, CameraSourceType.CUSTOM)
        self.assertEqual(source.details["transport"], "Personalizada")

    def test_configuration_manager_persists_network_source(self):
        class Snapshot:
            def as_mapping(self): return {"config_schema_version": 1, "camera": {"source": 0}}
        class Service:
            def __init__(self): self.candidate = None
            def current(self): return Snapshot()
            def save(self, candidate):
                self.candidate = candidate
                return type("Result", (), {"success": True})()
        service = Service(); persistence = CameraConfigurationPersistence(service)
        cfg = config(network_sources=[
            {"id": "ip", "type": "NETWORK_RTSP", "name": "Entrada",
             "url": "rtsp://user:pass@cam/live"},
        ], preferred_source="ip")
        self.assertTrue(persistence.save(cfg))
        self.assertEqual(service.candidate["camera"]["preferred_source"], "ip")
        self.assertEqual(service.candidate["camera"]["network_sources"][0]["url"],
                         "rtsp://user:pass@cam/live")

    def test_url_redaction_and_classification(self):
        safe = redact_url("rtsp://user:password@example.test:8554/live?token=secret")
        self.assertEqual(safe, "rtsp://***:***@example.test:8554/live")
        self.assertNotIn("password", safe); self.assertNotIn("token", safe)
        self.assertEqual(classify_camera_source(0), CameraType.USB)
        self.assertEqual(classify_camera_source("rtsp://cam/live"), CameraType.RTSP)
        self.assertEqual(classify_camera_source("http://cam/mjpeg"), CameraType.NETWORK_HTTP)
        projected = redact({"camera": {"network_sources": [{"url":
            "http://alice:secret@cam/mjpeg?token=hidden"}]}})
        rendered = repr(projected)
        self.assertNotIn("alice", rendered); self.assertNotIn("secret", rendered)

    def test_selection_controller_rejects_sensitive_state(self):
        dto = CameraSourceDTO("v4l2:0", CameraSourceType.LOCAL_V4L2, "Camera", True,
                              details={"index": 0})
        controller = CameraSelectionController(object(), switch_allowed=lambda: False)  # type: ignore[arg-type]
        controller.sources = (dto,)
        with self.assertRaises(PermissionError): controller.use(dto.source_id)

    def test_switch_releases_old_camera_before_constructing_new_one(self):
        events = []
        old = type("Old", (), {"release": lambda self: events.append("release")})()
        new = type("New", (), {"open": lambda self: events.append("open") or True})()
        adapter = RealUIRuntimeAdapter.__new__(RealUIRuntimeAdapter)
        adapter._camera = old; adapter._cancel_event = object()
        with patch("src.ui.runtime_adapter.CameraManager",
                   side_effect=lambda *_args, **_kwargs: events.append("construct") or new):
            self.assertTrue(adapter.switch_camera(CameraConfig("safe", CameraType.USB, 2)))
        self.assertEqual(events, ["release", "construct", "open"])


if __name__ == "__main__":
    unittest.main()
