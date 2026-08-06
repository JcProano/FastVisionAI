"""Manual OpenCV/DroidCam compatibility probe.

This script is intentionally independent from FastVisionAI's Camera Service.
It opens each candidate source sequentially and never displays a GUI window.
"""

from __future__ import annotations

import time
import socket
from dataclasses import dataclass
from typing import Final

import cv2

BASE_URL: Final = "http://192.168.1.17:4747/video"
FPS_SAMPLE_SECONDS: Final = 5.0
HOST: Final = "192.168.1.17"
PORT: Final = 4747


@dataclass(frozen=True, slots=True)
class Probe:
    name: str
    url: str
    backend: int | None = None


def run_probe(probe: Probe) -> None:
    """Open one source, inspect its first frame, and measure delivered FPS."""

    print(f"\n=== {probe.name} ===")
    print(f"URL: {probe.url}")
    capture: cv2.VideoCapture | None = None

    try:
        started_open = time.monotonic()
        capture = (
            cv2.VideoCapture(probe.url)
            if probe.backend is None
            else cv2.VideoCapture(probe.url, probe.backend)
        )
        open_seconds = time.monotonic() - started_open
        opened = capture.isOpened()
        print(f"isOpened(): {opened}")
        print(f"Tiempo de apertura: {open_seconds:.3f} s")

        if not opened:
            print("Backend utilizado: ninguno")
            print("Primer frame recibido: False")
            print("Resolución: no detectada")
            print("FPS: 0.000")
            return

        try:
            backend_name = capture.getBackendName()
        except cv2.error:
            backend_name = "no disponible"
        print(f"Backend utilizado: {backend_name}")

        ok, first_frame = capture.read()
        print(f"Primer frame recibido: {ok}")
        if not ok or first_frame is None:
            print("Resolución: no detectada")
            print("FPS: 0.000")
            return

        height, width = first_frame.shape[:2]
        print(f"Resolución: {width}x{height}")

        frame_count = 1
        sample_started = time.monotonic()
        while time.monotonic() - sample_started < FPS_SAMPLE_SECONDS:
            ok, frame = capture.read()
            if not ok or frame is None:
                print("La lectura se interrumpió durante la medición")
                break
            frame_count += 1

        sample_elapsed = time.monotonic() - sample_started
        measured_fps = frame_count / sample_elapsed if sample_elapsed > 0 else 0.0
        reported_fps = capture.get(cv2.CAP_PROP_FPS)
        print(f"FPS efectivo: {measured_fps:.3f}")
        print(f"FPS reportado por OpenCV: {reported_fps:.3f}")
        print(f"Frames medidos: {frame_count}")
    except (cv2.error, OSError, RuntimeError) as exc:
        print(f"Error: {type(exc).__name__}: {exc}")
    finally:
        if capture is not None:
            capture.release()
        print("Captura liberada")
        time.sleep(1.0)


def tcp_available(timeout_seconds: float = 1.0) -> bool:
    """Check DroidCam's TCP listener without consuming the video stream."""

    try:
        with socket.create_connection((HOST, PORT), timeout=timeout_seconds):
            return True
    except OSError as exc:
        print(f"Comprobación TCP fallida: {exc}")
        return False


def main() -> int:
    probes = [
        Probe("VideoCapture URL base", BASE_URL),
        Probe("VideoCapture URL con resolución", f"{BASE_URL}?640x480"),
    ]
    if hasattr(cv2, "CAP_FFMPEG"):
        probes.append(Probe("VideoCapture con CAP_FFMPEG", BASE_URL, cv2.CAP_FFMPEG))
    else:
        print("CAP_FFMPEG no está disponible en esta compilación de OpenCV")

    print(f"OpenCV: {cv2.__version__}")
    for probe in probes:
        print(f"\nComprobación TCP previa: {HOST}:{PORT}")
        if not tcp_available():
            print("PRUEBA DETENIDA: el servidor DroidCam dejó de responder; no es un fallo de OpenCV")
            return 2
        print("Comprobación TCP previa: OK")
        run_probe(probe)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
