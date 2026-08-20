"""Load and validate FastVisionAI configuration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from dataclasses import dataclass

from src.camera.camera_types import CameraConfig, CameraType, ReconnectConfig
from src.engine.config import (
    PipelineConfig,
    PluginConfig,
    PluginManagerConfig,
    QueueConfig,
    QueuePolicy,
    RuntimeConfig,
    SimulatedDetectorConfig,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "config.json"


class ConfigurationError(ValueError):
    """Raised when config/config.json is missing or invalid."""


@dataclass(frozen=True, slots=True)
class AppConfig:
    camera: CameraConfig
    pipeline: PipelineConfig
    log_level: str = "INFO"
    log_file: Path | None = None


def _mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ConfigurationError(f"'{field_name}' debe ser un objeto JSON")
    return value


def _non_negative_int(value: object, field_name: str, default: int) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConfigurationError(f"'{field_name}' debe ser un entero no negativo")
    return value


def _non_negative_number(value: object, field_name: str, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ConfigurationError(f"'{field_name}' debe ser un número no negativo")
    return float(value)


def _resolve_project_path(value: object, field_name: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"'{field_name}' debe ser una ruta no vacía")
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def load_config(config_path: Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    """Read the single phase-1 configuration file and return typed settings."""

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigurationError(f"No existe el archivo de configuración: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"JSON inválido en {config_path}: {exc}") from exc
    except OSError as exc:
        raise ConfigurationError(f"No se pudo leer {config_path}: {exc}") from exc

    root = _mapping(raw, "root")
    camera_raw = _mapping(root.get("camera"), "camera")
    reconnect_raw = _mapping(camera_raw.get("reconnect", {}), "camera.reconnect")

    try:
        camera_type = CameraType(camera_raw.get("type"))
    except (ValueError, TypeError) as exc:
        supported = ", ".join(item.value for item in CameraType)
        raise ConfigurationError(f"'camera.type' debe ser uno de: {supported}") from exc

    source: int | str | Path
    raw_source = camera_raw.get("source")
    if camera_type is CameraType.USB:
        if isinstance(raw_source, bool) or not isinstance(raw_source, int) or raw_source < 0:
            raise ConfigurationError("'camera.source' debe ser un índice USB no negativo")
        source = raw_source
    elif camera_type is CameraType.RTSP:
        if not isinstance(raw_source, str) or not raw_source.lower().startswith(("rtsp://", "rtsps://", "http://", "https://")):
            raise ConfigurationError("'camera.source' debe ser una URL RTSP/HTTP válida")
        source = raw_source
    else:
        source = _resolve_project_path(raw_source, "camera.source")

    reconnect = ReconnectConfig(
        enabled=bool(reconnect_raw.get("enabled", True)),
        max_attempts=_non_negative_int(reconnect_raw.get("max_attempts"), "camera.reconnect.max_attempts", 3),
        interval_seconds=_non_negative_number(
            reconnect_raw.get("interval_seconds"), "camera.reconnect.interval_seconds", 1.0
        ),
    )
    camera = CameraConfig(
        name=str(camera_raw.get("name", "default")),
        camera_type=camera_type,
        source=str(source) if isinstance(source, Path) else source,
        open_timeout_ms=_non_negative_int(
            camera_raw.get("open_timeout_ms"), "camera.open_timeout_ms", 5_000
        ),
        read_timeout_ms=_non_negative_int(
            camera_raw.get("read_timeout_ms"), "camera.read_timeout_ms", 5_000
        ),
        reconnect=reconnect,
    )

    logging_raw = _mapping(root.get("logging", {}), "logging")
    log_file_raw = logging_raw.get("file")
    log_file = None if log_file_raw in (None, "") else _resolve_project_path(log_file_raw, "logging.file")
    pipeline_raw = _mapping(root.get("pipeline", {}), "pipeline")
    queue_raw = _mapping(pipeline_raw.get("queue", {}), "pipeline.queue")
    detector_raw = _mapping(pipeline_raw.get("simulated_detector", {}), "pipeline.simulated_detector")
    plugins_raw = _mapping(pipeline_raw.get("plugins", {}), "pipeline.plugins")
    runtime_raw = _mapping(pipeline_raw.get("runtime", {}), "pipeline.runtime")
    try:
        queue_policy = QueuePolicy(queue_raw.get("policy", "realtime"))
    except ValueError as exc:
        raise ConfigurationError("'pipeline.queue.policy' debe ser realtime o video_file") from exc
    capacity = _non_negative_int(queue_raw.get("capacity"), "pipeline.queue.capacity", 4)
    if capacity == 0:
        raise ConfigurationError("'pipeline.queue.capacity' debe ser mayor que cero")
    detection_count = _non_negative_int(
        detector_raw.get("detection_count"), "pipeline.simulated_detector.detection_count", 1
    )
    confidence = _non_negative_number(
        detector_raw.get("confidence"), "pipeline.simulated_detector.confidence", 0.9
    )
    if confidence > 1:
        raise ConfigurationError("'pipeline.simulated_detector.confidence' no puede superar 1")
    raw_directories = plugins_raw.get("directories", ["plugins"])
    if not isinstance(raw_directories, list) or not all(isinstance(item, str) for item in raw_directories):
        raise ConfigurationError("'pipeline.plugins.directories' debe ser una lista de rutas")
    raw_enabled = plugins_raw.get("enabled", [])
    if not isinstance(raw_enabled, list):
        raise ConfigurationError("'pipeline.plugins.enabled' debe ser una lista")
    plugin_configs: list[PluginConfig] = []
    for index, item in enumerate(raw_enabled):
        plugin_raw = _mapping(item, f"pipeline.plugins.enabled[{index}]")
        plugin_id = plugin_raw.get("id")
        if not isinstance(plugin_id, str) or not plugin_id:
            raise ConfigurationError(f"'pipeline.plugins.enabled[{index}].id' es obligatorio")
        settings = _mapping(plugin_raw.get("settings", {}), f"pipeline.plugins.enabled[{index}].settings")
        priority = plugin_raw.get("priority", 100)
        if isinstance(priority, bool) or not isinstance(priority, int):
            raise ConfigurationError(f"'pipeline.plugins.enabled[{index}].priority' debe ser entero")
        plugin_configs.append(
            PluginConfig(
                id=plugin_id,
                enabled=bool(plugin_raw.get("enabled", True)),
                priority=priority,
                settings=dict(settings),
            )
        )
    pipeline = PipelineConfig(
        queue=QueueConfig(
            capacity=capacity,
            policy=queue_policy,
            wait_timeout_seconds=_non_negative_number(
                queue_raw.get("wait_timeout_seconds"), "pipeline.queue.wait_timeout_seconds", 0.5
            ),
        ),
        detector=SimulatedDetectorConfig(
            detection_count=detection_count,
            class_name=str(detector_raw.get("class_name", "person")),
            confidence=confidence,
            latency_ms=_non_negative_number(
                detector_raw.get("latency_ms"), "pipeline.simulated_detector.latency_ms", 0.0
            ),
            fail=bool(detector_raw.get("fail", False)),
        ),
        plugins=PluginManagerConfig(
            directories=tuple(raw_directories),
            continue_on_error=bool(plugins_raw.get("continue_on_error", True)),
            plugins=tuple(plugin_configs),
        ),
        runtime=RuntimeConfig(
            name=str(runtime_raw.get("name", "scheduler")),
            settings=dict(_mapping(runtime_raw.get("settings", {}), "pipeline.runtime.settings")),
        ),
        synthetic_frame_count=_non_negative_int(
            pipeline_raw.get("synthetic_frame_count"), "pipeline.synthetic_frame_count", 20
        ),
    )
    return AppConfig(
        camera=camera,
        pipeline=pipeline,
        log_level=str(logging_raw.get("level", "INFO")),
        log_file=log_file,
    )
