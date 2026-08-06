from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.camera.camera_types import CameraType
from src.core.config_manager import ConfigurationError, PROJECT_ROOT, load_config
from src.engine.config import QueuePolicy


class ConfigManagerTests(unittest.TestCase):
    def _config_file(self, data: object) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        directory = tempfile.TemporaryDirectory()
        path = Path(directory.name) / "config.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return directory, path

    def test_loads_usb_config(self) -> None:
        directory, path = self._config_file({"camera": {"type": "usb", "source": 2}})
        self.addCleanup(directory.cleanup)
        config = load_config(path)
        self.assertEqual(config.camera.camera_type, CameraType.USB)
        self.assertEqual(config.camera.source, 2)
        self.assertTrue(config.camera.is_live)

    def test_resolves_video_relative_to_project_root(self) -> None:
        directory, path = self._config_file(
            {"camera": {"type": "video_file", "source": "data/sample.mp4"}}
        )
        self.addCleanup(directory.cleanup)
        config = load_config(path)
        self.assertEqual(Path(str(config.camera.source)), (PROJECT_ROOT / "data/sample.mp4").resolve())
        self.assertFalse(config.camera.is_live)

    def test_rejects_invalid_rtsp_source(self) -> None:
        directory, path = self._config_file({"camera": {"type": "rtsp", "source": "camera"}})
        self.addCleanup(directory.cleanup)
        with self.assertRaises(ConfigurationError):
            load_config(path)

    def test_loads_pipeline_config(self) -> None:
        directory, path = self._config_file(
            {
                "camera": {"type": "usb", "source": 0},
                "pipeline": {
                    "queue": {"capacity": 8, "policy": "video_file"},
                    "simulated_detector": {"detection_count": 3, "confidence": 0.8},
                    "synthetic_frame_count": 12,
                },
            }
        )
        self.addCleanup(directory.cleanup)
        config = load_config(path)
        self.assertEqual(config.pipeline.queue.capacity, 8)
        self.assertEqual(config.pipeline.queue.policy, QueuePolicy.VIDEO_FILE)
        self.assertEqual(config.pipeline.detector.detection_count, 3)
        self.assertEqual(config.pipeline.synthetic_frame_count, 12)

    def test_old_config_receives_pipeline_defaults(self) -> None:
        directory, path = self._config_file({"camera": {"type": "usb", "source": 0}})
        self.addCleanup(directory.cleanup)
        config = load_config(path)
        self.assertEqual(config.pipeline.queue.capacity, 4)
        self.assertEqual(config.pipeline.queue.policy, QueuePolicy.REALTIME)

    def test_loads_plugin_configuration(self) -> None:
        directory, path = self._config_file(
            {
                "camera": {"type": "usb", "source": 0},
                "pipeline": {
                    "plugins": {
                        "directories": ["plugins"],
                        "continue_on_error": False,
                        "enabled": [
                            {
                                "id": "dummy",
                                "priority": 7,
                                "settings": {"detection_count": 2},
                            }
                        ],
                    }
                },
            }
        )
        self.addCleanup(directory.cleanup)
        config = load_config(path)
        self.assertFalse(config.pipeline.plugins.continue_on_error)
        self.assertEqual(config.pipeline.plugins.plugins[0].id, "dummy")
        self.assertEqual(config.pipeline.plugins.plugins[0].priority, 7)


if __name__ == "__main__":
    unittest.main()
