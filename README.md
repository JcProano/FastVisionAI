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

## Static face alignment

Run detection and deterministic five-point alignment without a camera:

```bash
venv/bin/python -m src.validation.static_face_alignment --input bus.jpg --output-dir outputs/face_alignment
```

The fixed `fva-5pt-112-v1` template expects, in order: left eye, right eye,
nose, left mouth corner and right mouth corner. Outputs are 112 x 112 pixels.
Low-quality but geometrically valid faces remain aligned and are labelled
`low_quality`; this phase creates no embeddings or identity data.

## Face embedding postprocessor

`FaceEmbeddingPlugin` is a biometric postprocessor over `AlignedFace`; despite
its functional name, it is not an `InferenceBackend` and is not registered in
the PreparedFrame Scheduler. It produces normalized, read-only float32 vectors
and never compares, identifies or stores them.

Once the explicitly configured model exists locally, validate the complete
static flow with:

```bash
venv/bin/python -m src.validation.static_face_embedding --input bus.jpg
```

### LICENSE / MODEL NOTICE

FastVisionAI source code does not inherit the license of a model artifact.
Official pretrained InsightFace weights are restricted to non-commercial
research use. Before commercializing FastVisionAI, replace those weights with
a commercially licensed model or obtain the corresponding license from the
model owner. Model files are not downloaded automatically or committed to Git.

## In-memory face gallery

The Phase 8 gallery stores temporary identities and read-only templates in
memory. Matching returns template-level cosine scores and ranked candidates;
automatic decisions are disabled by default and no universal threshold is
defined. Run the non-identifying static validation with:

```bash
venv/bin/python -m src.validation.static_face_gallery --input bus.jpg --top-k 2
```

Optional JSON+NPZ persistence is explicit, disabled by default and intended
only for controlled development. See [docs/BIOMETRIC_DATA.md](docs/BIOMETRIC_DATA.md).
