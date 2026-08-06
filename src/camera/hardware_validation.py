"""Headless hardware validation for the configured Camera Engine source."""

from __future__ import annotations

import argparse
import json
import logging
import signal
import statistics
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from src.camera.camera_manager import CameraManager
from src.camera.camera_types import ReadStatus
from src.core.config_manager import PROJECT_ROOT, ConfigurationError, load_config
from src.core.logger import configure_logging

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ValidationReport:
    source_opened: bool
    frames_captured: int
    average_fps: float
    resolution: str
    average_frame_interval_ms: float
    reconnections: int
    last_recovery_seconds: float | None
    estimated_frames_lost: int
    final_camera_state: str
    elapsed_seconds: float


class ValidationMetrics:
    def __init__(self) -> None:
        self.timestamps: list[float] = []
        self.resolution = "unknown"

    def add(self, timestamp: float, width: int, height: int) -> None:
        self.timestamps.append(timestamp)
        if width > 0 and height > 0:
            self.resolution = f"{width}x{height}"

    @property
    def intervals(self) -> list[float]:
        return [later - earlier for earlier, later in zip(self.timestamps, self.timestamps[1:])]

    @property
    def average_interval(self) -> float:
        return statistics.fmean(self.intervals) if self.intervals else 0.0

    @property
    def fps(self) -> float:
        interval = self.average_interval
        return 1.0 / interval if interval > 0 else 0.0


def validate(max_duration: float | None = None, report_path: Path | None = None) -> int:
    try:
        config = load_config()
        configure_logging(config.log_level, config.log_file)
    except (ConfigurationError, ValueError) as exc:
        print(f"Error de configuración: {exc}")
        return 2

    cancelled = threading.Event()
    previous_sigint = signal.signal(signal.SIGINT, lambda _signum, _frame: cancelled.set())
    metrics = ValidationMetrics()
    started = time.monotonic()
    source_opened = False
    final_state = "not_started"
    manager = CameraManager(config.camera, cancel_event=cancelled)

    LOGGER.info("HARDWARE VALIDATION iniciada para %s", config.camera.source)
    try:
        source_opened = manager.open()
        final_state = "connected" if source_opened else "opening_or_reconnecting"
        while not cancelled.is_set():
            if max_duration is not None and time.monotonic() - started >= max_duration:
                break
            result = manager.read()
            if result.status is ReadStatus.FRAME and result.frame is not None:
                frame = result.frame
                metrics.add(frame.monotonic_timestamp, frame.width, frame.height)
                final_state = "connected"
            elif result.status is ReadStatus.EOF:
                final_state = "eof"
                break
            elif result.status is ReadStatus.CANCELLED:
                final_state = "cancelled"
                break
            else:
                final_state = "disconnected"
                break
    finally:
        manager.release()
        signal.signal(signal.SIGINT, previous_sigint)

    elapsed = time.monotonic() - started
    recovery = manager.last_recovery_seconds
    estimated_lost = round((recovery or 0.0) * metrics.fps)
    if cancelled.is_set():
        final_state = "closed_cleanly"
    report = ValidationReport(
        source_opened=source_opened,
        frames_captured=len(metrics.timestamps),
        average_fps=round(metrics.fps, 3),
        resolution=metrics.resolution,
        average_frame_interval_ms=round(metrics.average_interval * 1_000, 3),
        reconnections=manager.reconnection_count,
        last_recovery_seconds=None if recovery is None else round(recovery, 3),
        estimated_frames_lost=estimated_lost,
        final_camera_state=final_state,
        elapsed_seconds=round(elapsed, 3),
    )
    payload = json.dumps(asdict(report), indent=2, ensure_ascii=False)
    LOGGER.info("HARDWARE VALIDATION finalizada\n%s", payload)
    print(payload)
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(payload + "\n", encoding="utf-8")
    return 0 if source_opened and bool(metrics.timestamps) and final_state != "disconnected" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Validación headless de Camera Service")
    parser.add_argument("--max-duration", type=float, default=None, metavar="SECONDS")
    parser.add_argument(
        "--report",
        type=Path,
        default=PROJECT_ROOT / "logs" / "hardware_validation.json",
    )
    args = parser.parse_args()
    if args.max_duration is not None and args.max_duration < 0:
        parser.error("--max-duration debe ser no negativo")
    return validate(args.max_duration, args.report)


if __name__ == "__main__":
    raise SystemExit(main())
