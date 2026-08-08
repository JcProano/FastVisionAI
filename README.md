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

## Local biometric enrollment

`EnrollmentService` validates a complete sequence before transactionally
registering a temporary identity. Pairwise minimum consistency and maximum
near-duplicate limits are optional (`None` disables either check); no biometric
limits are assumed by default. The static validator uses explicit development
values and synthetic photometric variants only:

```bash
venv/bin/python -m src.validation.static_face_enrollment --input bus.jpg --templates-per-identity 3
```

## Face similarity calibration

Phase 10 performs offline analysis, not recognition. Capture is one consenting
participant and one temporary identifier per session. Nothing is saved unless
`--save-data` or `--save-images` is supplied; either requires
`--consent-confirmed`.

```bash
venv/bin/python -m src.validation.capture_face_calibration \
  --temporary-id temporary_calibration_001 --source 0 \
  --min-samples 5 --target-samples 10 --min-capture-interval 1.0 \
  --max-near-duplicate-similarity 0.995 --consent-confirmed --save-data
```

Analyze saved temporary identities with explicitly chosen development thresholds:

```bash
venv/bin/python -m src.validation.analyze_face_calibration \
  --input data/calibration/session_id --thresholds 0.2 0.3 0.4 0.5
```

Acceptance is `similarity >= threshold`; rejection is `similarity < threshold`.
FAR, FRR and approximate EER remain diagnostics and do not establish a production
threshold.

## Guided face capture

Guided capture evaluates face count, alignment, geometry, centering, illumination,
contrast, blur, requested pose, capture interval and sample diversity before a
sample is accepted. Its thresholds come from the explicit development profile
`config/guided_capture.dev.json`; they are not universal biometric limits.

```bash
venv/bin/python -m src.validation.guided_face_capture \
  --temporary-id temporary_guided_001 --source 0 --target-samples 9 \
  --consent-confirmed
```

Nothing is persisted by default. `--save-data` requires consent, and
`--save-images` additionally requires `--save-data`; only accepted aligned faces
may be stored. Neutral expression is an operator instruction, not an inferred
biometric attribute.

### Continuous face quality score

Guided capture also computes an informational `0..100` score using
`config/face_quality.dev.json`. It never changes acceptance and is not an identity
threshold. Detection, size, interocular distance, visibility, sharpness and
contrast use a clamped linear function:

```text
clamp((value - minimum) / (full_score - minimum), 0, 1)
```

Centering decreases linearly with Euclidean offset. Illumination scores `1` in
the configured ideal interval and falls linearly to `0` at its dark and bright
absolute limits. Pose scores are explicit constants. Normalized components are
multiplied by weights whose sum must equal `1`, then configured critical-state
penalties are applied. Structural failures produce `INVALID` and zero. Every
component and final result is clamped to its documented range.

### Guided profile diagnostics

Run a guided session with aggregate-only diagnostics using:

```bash
venv/bin/python -m src.validation.diagnose_guided_capture \
  --temporary-id temporary_diagnostic_001 --source 0 --target-samples 9
```

The report separates accepted, visually valid and rejected frames; summarizes
confidence, face size, interocular distance, visibility, centering, blur,
illumination and contrast; and includes requested-versus-estimated pose plus the
detected-face-count histogram. Diagnostic mode rejects `--save-data` and
`--save-images`. It does not retain images, landmarks, identities or embeddings.
# Interfaz facial local experimental

La capa `src/ui/` presenta candidatos de similitud y coordina un registro guiado
sin modificar el pipeline biométrico. Nunca confirma una identidad: muestra
únicamente **Candidato experimental**, la similitud y
`Decisión automática: deshabilitada / NOT_EVALUATED`. La galería es en memoria y
la persistencia local exige consentimiento y selección explícita; ocurre después
de que `EnrollmentService` complete la transacción. No se guardan imágenes por
defecto ni se exponen embeddings en DTOs, logs o pantalla.

La ventana base se inicia con:

```bash
venv/bin/python -m src.ui.main --config config/local_face_validation.dev.json
```

Sin dispositivo físico puede validarse la ventana, el worker, enrollment en
memoria y el regreso a monitorización sin persistir artefactos:

```bash
venv/bin/python -m src.ui.main --config config/local_face_validation.dev.json \
  --mock-camera --mock-auto-enroll --mock-duration 2
```

La captura y el procesamiento biométrico deben ejecutarse fuera del hilo de
Tkinter y entregar a la vista únicamente DTOs seguros y el frame RGB transitorio.

### Administrador local de personas

La acción **Personas registradas** administra exclusivamente la galería en
memoria compartida con la monitorización. Permite buscar, editar datos visibles,
eliminar identidades y agregar muestras mediante captura guiada. `person_id` es
inmutable; `display_name` siempre se deriva de nombre y apellido. Las mutaciones
se validan primero en una galería temporal y solo se publican con `replace_from()`.

Los cambios no se persisten automáticamente. Guardar, importar y exportar son
acciones explícitas JSON+NPZ; sobrescribir o reemplazar requiere confirmación.
La UI nunca presenta embeddings, huellas internas de templates ni imágenes
biométricas. Los templates antiguos sin puntuación se muestran como `sin score`.

### Recognition Service

`RecognitionService` transforma los rankings de `FaceMatcher` en resultados
seguros y estructurados sin acceder directamente a embeddings o templates. La
configuración local mantiene la decisión automática deshabilitada, sin threshold
ni margen biométrico. Por ello la UI continúa mostrando únicamente **Candidato
experimental** y `NOT_EVALUATED`. Los estados `MATCH`, `UNKNOWN` y `AMBIGUOUS`
solo pueden producirse con una política de prueba habilitada explícitamente.
