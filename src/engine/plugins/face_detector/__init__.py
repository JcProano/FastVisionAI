"""YuNet face detection plugin."""

from src.engine.plugins.face_detector.plugin import (
    PLUGIN_DESCRIPTOR,
    FaceDetectorPlugin,
    create_plugin,
)

__all__ = ["PLUGIN_DESCRIPTOR", "FaceDetectorPlugin", "create_plugin"]
