"""MJPEG encoding and streaming isolated from the HTTP framework."""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator


def encode_jpeg(frame, quality: int) -> bytes:
    import cv2
    import numpy as np

    rgb = np.frombuffer(frame.rgb_bytes, dtype=np.uint8).reshape(
        (frame.height, frame.width, 3)
    )
    ok, encoded = cv2.imencode(
        ".jpg",
        cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR),
        [cv2.IMWRITE_JPEG_QUALITY, quality],
    )
    if not ok:
        raise RuntimeError("presentation JPEG encoding failed")
    return encoded.tobytes()


def iter_mjpeg(
    frame_store,
    closing: threading.Event,
    *,
    maximum_fps: float,
    jpeg_quality: int,
) -> Iterator[bytes]:
    sequence = None
    period = 1.0 / maximum_fps
    deadline = 0.0
    while not closing.is_set() and not frame_store.closed:
        frame = frame_store.wait_for_new(sequence, 1.0)
        if frame is None:
            continue
        delay = deadline - time.monotonic()
        if delay > 0 and closing.wait(delay):
            break
        jpeg = encode_jpeg(frame, jpeg_quality)
        sequence = frame.sequence_id
        deadline = time.monotonic() + period
        yield (
            b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "
            + str(len(jpeg)).encode()
            + b"\r\n\r\n"
            + jpeg
            + b"\r\n"
        )
