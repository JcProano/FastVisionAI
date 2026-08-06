# FastVisionAI

FastVisionAI is a modular computer-vision platform. Phase 1 contains only the
headless Camera Engine and supports USB cameras, RTSP/IP streams and video
files through OpenCV.

## Configuration

The engine reads `config/config.json`. Set `camera.type` to `usb`, `rtsp` or
`video_file`. USB sources use a non-negative device index; network sources use
an RTSP/HTTP URL; video paths are resolved relative to the repository root.

## Run

Use the existing project environment without installing packages:

```bash
venv/bin/python app.py
venv/bin/python app.py --max-frames 100
venv/bin/python app.py --max-duration 30
```

Stop cleanly with `Ctrl+C`. The application does not open a window. Live
sources reconnect according to the configured limits; video files stop at EOF.

## Tests

```bash
venv/bin/python -m unittest discover -s tests -v
```

Tests mock video capture and do not access a physical camera. The capture layer
is isolated so a CSI/GStreamer backend can be added for Jetson Orin Nano later.

## Synthetic inference engine

The first Phase 2 delivery is headless and model-free. It connects a bounded
Frame Queue to a minimal preprocessor and deterministic simulated inference
backend. Run a limited demonstration without a camera:

```bash
venv/bin/python -m src.engine.runner --frames 20
```

The engine reports queue and pipeline metrics. No YOLO, GPU runtime, tracking,
recognition or biometric component is loaded.

Phase 2.5 adds lazy model lifecycle infrastructure, trusted plugin discovery,
ordered sequential scheduling and benchmark snapshots. The demonstration uses
only `DummyPlugin`; no model framework is imported. See [ARCHITECTURE.md](ARCHITECTURE.md)
for contracts, lifecycle states and extension boundaries.

## Live USB person detection validation

With a `/dev/videoX` device connected, run the isolated validation UI:

```bash
venv/bin/python -m src.validation.live_person_detection --source 0 --max-duration 30
```

Use `--no-display`, `--max-frames`, `--result-max-age`, resolution, confidence,
image-size and inference-interval options for bounded or headless validation.

## Static face detection validation

`FaceDetectorPlugin` uses OpenCV YuNet and is disabled by default. Once the
configured ONNX artifact is available locally, validate one image without
opening a camera:

```bash
venv/bin/python -m src.validation.static_face_detection --input bus.jpg --output outputs/face_validation/bus_faces.jpg
```

The plugin returns normalized face-only boxes and retains YuNet's five
normalized landmarks per face in `InferenceResult.attachments`. It does not
perform recognition, embeddings, identity comparison, iris or liveness work.

The separate live USB runner is available as
`python -m src.validation.live_face_detection`; do not run it until the model
artifact and a camera are available. It enables only the face plugin and leaves
the person detector untouched.
