"""Command-line entry point for the FastVisionAI Camera Engine."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time

from src.camera.camera_manager import CameraManager
from src.camera.camera_types import ReadStatus
from src.core.config_manager import ConfigurationError, load_config
from src.core.logger import configure_logging

LOGGER = logging.getLogger(__name__)


def _non_negative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("debe ser mayor o igual a cero")
    return parsed


def _non_negative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("debe ser mayor o igual a cero")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FastVisionAI Camera Engine (sin GUI)")
    parser.add_argument("--max-frames", type=_non_negative_int, default=None)
    parser.add_argument("--max-duration", type=_non_negative_float, default=None, metavar="SECONDS")
    return parser


def run(max_frames: int | None = None, max_duration: float | None = None) -> int:
    try:
        config = load_config()
        configure_logging(config.log_level, config.log_file)
    except (ConfigurationError, ValueError) as exc:
        print(f"Error de configuración: {exc}")
        return 2

    cancelled = threading.Event()

    def request_stop(_signum: int, _frame: object) -> None:
        cancelled.set()

    previous_sigint = signal.signal(signal.SIGINT, request_stop)
    started_at = time.monotonic()
    frame_count = 0
    try:
        with CameraManager(config.camera, cancel_event=cancelled) as camera:
            while not cancelled.is_set():
                if max_frames is not None and frame_count >= max_frames:
                    break
                if max_duration is not None and time.monotonic() - started_at >= max_duration:
                    break

                result = camera.read()
                if result.status is ReadStatus.FRAME:
                    frame_count += 1
                    continue
                if result.status is ReadStatus.EOF:
                    LOGGER.info("Procesamiento completado al final del archivo")
                    break
                if result.status is ReadStatus.CANCELLED:
                    break
                LOGGER.error("Fuente no disponible; Camera Engine finalizado")
                return 1
    finally:
        signal.signal(signal.SIGINT, previous_sigint)

    LOGGER.info("Camera Engine finalizado limpiamente; frames=%d", frame_count)
    return 0


def main() -> int:
    # The supported demonstration entry point is the integrated UI. Keep the
    # historical bounded camera-engine commands available for validation.
    if not any(option in sys.argv[1:] for option in ("--max-frames", "--max-duration")):
        if "--config" not in sys.argv[1:]:
            sys.argv[1:1] = ["--config", "config/local_face_validation.jetson.json"]
        from src.ui.main import main as ui_main
        return ui_main()
    args = build_parser().parse_args()
    return run(max_frames=args.max_frames, max_duration=args.max_duration)


if __name__ == "__main__":
    raise SystemExit(main())
