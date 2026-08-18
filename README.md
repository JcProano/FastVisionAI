# FastVisionAI

## Dashboard appliance en red local

El perfil `config/local_face_validation.jetson.json` habilita una sesión ADMIN
temporal en memoria y el dashboard web para el despliegue posterior en Jetson.

> Este dashboard sin autenticación web está diseñado exclusivamente para
> localhost o una LAN privada confiable. No exponer directamente a Internet.

El servidor no configura UPnP, el router, HTTPS ni acceso desde Internet. En
Jetson debe conservarse el OpenCV suministrado por JetPack.

**Versión candidata:** `1.0.0-rc1`. Consulte [release notes](docs/RELEASE_NOTES_v1.0.0-rc1.md), [despliegue Ubuntu](docs/DEPLOYMENT_UBUNTU.md), [Jetson Orin Nano](docs/JETSON_ORIN_NANO.md) y [checklist](docs/RELEASE_CHECKLIST.md).

## Auditoría administrativa local

El registro administrativo es append-only, usa un SQLite separado y cubre fronteras humanas como seguridad, usuarios, personas, asistencia manual, reportes, configuración, backup/restore y apertura de diagnóstico. Es best-effort: una indisponibilidad no revierte una operación principal confirmada. ADMIN y AUDITOR pueden consultar y exportar; OPERATOR y VIEWER no tienen acceso. El CSV UTF-8 no sobrescribe por defecto, protege contra fórmulas y omite metadata interna.

## Person Database (Fase 20, infraestructura)

`src/core/person_database/` aporta un repositorio SQLite local para información
administrativa. `person_id` continúa siendo un UUID interno estable y la cédula
es un identificador civil separado y único. La validación de cédula comprueba
solo formato y checksum: no demuestra existencia ni titularidad.

La integración futura seguirá una saga explícita: crear el registro
`PENDING_BIOMETRIC`, realizar captura y enrollment, confirmar FaceGallery y pasar
a `ACTIVE`. Una cancelación o fallo anterior al commit de FaceGallery eliminará
la reserva pendiente. Este flujo todavía no está conectado a la UI.

La presentación visual experimental puede abrir un único popup tras observar un
candidato estable o un rostro sin candidato local. El popup aplica estabilidad y
cooldown, se suspende durante enrollment y conserva `NOT_EVALUATED`: no confirma
identidad ni toma decisiones automáticas.

Las miniaturas opcionales de la UI son archivos visuales sensibles separados de
la galería biométrica. No se usan para comparar rostros ni tomar decisiones y no
se incluyen al importar o exportar JSON+NPZ.

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

### Coordinación civil y biométrica

Con `person_database.enabled=true`, la UI reserva primero una persona civil como
`PENDING_BIOMETRIC`. `PersonEnrollmentCoordinator` confirma el enrollment
biométrico y después cambia el registro a `ACTIVE`. Una cancelación o rechazo
elimina únicamente la reserva pendiente actual. Si la activación falla, la
compensación verifica ambos almacenes; si no puede garantizar el estado anterior
informa `INCONSISTENT` para reconciliación administrativa.

Los datos civiles permanecen en SQLite y no se copian a metadata de templates.
Miniatura y exportación son efectos opcionales posteriores a `ACTIVE`; su fallo
no revierte un alta válida. Las identidades antiguas se presentan como registros
biométricos heredados sin datos civiles.

### Ficha completa de persona

La ficha local compone información civil SQLite, estadísticas biométricas
escalares y una miniatura visual opcional. Puede resolverse por `person_id` o por
cédula, pero esta última nunca se usa como identificador biométrico. Distingue
`ACTIVE`, `DISABLED`, `PENDING_BIOMETRIC`, registros heredados y ausencias sin
inventar datos. Solo `ACTIVE` habilita muestras adicionales.

### Historial de eventos de detección

`DetectionEventService` registra observaciones relevantes —candidato experimental,
persona no registrada, incompatibilidad y múltiples rostros— en una base SQLite
independiente. No registra `NO_FACE`, decisiones de identidad, imágenes ni
embeddings. El cooldown es monotónico y agregado por cámara para eventos sin
`person_id`; sin tracking no se intenta distinguir desconocidos diferentes.
RecognitionService continúa en `NOT_EVALUATED`.

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

La UI consulta este servicio mediante `ExperimentalRecognitionSession` y recibe
solo DTO seguros. En el perfil actual, `NO_GALLERY`, `INCOMPATIBLE` y
`NOT_EVALUATED` mantienen disponible el registro; no se muestran decisiones de
identidad. Durante enrollment principal o adicional no se ejecutan consultas de
reconocimiento, y la misma galería compartida vuelve a estar disponible al
regresar a monitorización.

### Dashboard local

La ventana principal organiza video, sistema, candidato experimental, calidad,
galería, métricas, historial temporal y acciones administrativas en un dashboard
`ttk` adaptable. El historial está limitado, vive solo en memoria y aplica
debounce. “Pipeline FPS” representa el throughput efectivo completo, no FPS puro
del modelo; la latencia de inferencia se muestra como `N/D` mientras no exista una
medición segura. Configuración es solo lectura y RecognitionService permanece sin
threshold, margen ni decisión automática.

```bash
venv/bin/python -m src.ui.main \
  --config config/local_face_validation.dev.json --mock-camera
```
### Attendance Service (Fase 23)

La asistencia administrativa usa una base SQLite independiente como fuente de verdad.
La configuración de desarrollo permite marcaciones manuales para personas `ACTIVE`,
pero mantiene `automatic_attendance_enabled=false`; una detección nunca genera una
marcación en esta fase. `MANUAL_CHECK_IN`/`MANUAL_CHECK_OUT` permanecen diferenciados
de los futuros eventos automáticos. El cooldown de duplicados se aplica a acciones
manuales; el intervalo mínimo entre entrada/salida está reservado para la política
automática explícita. Los CSV omiten cédula completa, datos civiles y biometría.
### Stability Tracker (Fase 24)

El tracker mantiene una secuencia temporal efímera por sesión y expone al dashboard
si un candidato permanece continuo durante el número de observaciones y duración
configurados. `STABLE` describe exclusivamente continuidad temporal: no confirma
identidad, no autoriza acceso, no crea asistencia y no filtra eventos. La similitud
opcional es solo un filtro de estabilidad y permanece deshabilitada por defecto.
### Identification Policy Engine (Fase 25)

El motor combina únicamente señales escalares seguras de monitorización, estabilidad,
calidad y estado administrativo. Su evaluación es pura e informativa. `ELIGIBLE`
significa que la observación cumple la política configurada; no confirma identidad,
no autoriza acceso y no crea eventos o asistencia. No existen umbrales predeterminados
de calidad o similitud y las acciones automáticas permanecen deshabilitadas.
### Decision Orchestrator (Fase 26)

El orquestador convierte señales escalares ya calculadas en propuestas ordenadas.
No ejecuta acciones: no abre popups, no escribe eventos, no registra asistencia y no
modifica la galería. `PROPOSE_ATTENDANCE` es únicamente una propuesta informativa y
permanece deshabilitada en la configuración de desarrollo. No existe un campo de
acciones ejecutadas y las acciones automáticas están deshabilitadas por defecto.

### Action Executor (Fase 27)

`ActionExecutor` recibe exclusivamente propuestas del orquestador y aplica una
política explícita antes de atravesar adaptadores de efectos. Deduplica y ordena las
acciones de forma determinista; los fallos de un adapter se aíslan y no detienen las
acciones posteriores ni la sesión. No consulta reconocimiento, galería, estabilidad,
modelos o datos civiles.

Con `automatic_execution_enabled=false` no se invoca ningún adapter. Asistencia,
control de acceso y apertura de puertas siguen bloqueados y no ejecutables.

### Logging controlado mediante Action Executor (Fase 28)

El perfil local habilita exclusivamente `LOG_DETECTION_EVENT`: las propuestas y
ejecución de popups están deshabilitadas, y no existe adapter de asistencia. La ruta
se decide una vez al construir la sesión. Si todas las barreras están habilitadas,
el evento pasa por `DetectionEventServiceActionAdapter`; ante una configuración
incompleta se conserva la ruta heredada. Nunca se usan ambas rutas en una evaluación.

`DetectionEventService` continúa siendo responsable de cooldown, caché y escritura.
Un cooldown procesado correctamente aparece como acción `EXECUTED` aunque no genere
otra fila. Formulario, enrollment y rollback suspenden completamente el historial.

### Popups controlados mediante Action Executor (Fase 29)

Los popups registrado y no registrado pueden seguir una ruta independiente del modo
de logging. La configuración local habilita ambos mediante `PopupActionAdapter`; una
configuración parcial conserva el camino heredado y nunca usa los dos en el mismo
frame. `candidate_stability_frames`, cooldowns, singleton y el timeout desconocido de
60 segundos continúan perteneciendo a la capa de presentación.

El worker no llama Tkinter. El adapter entrega DTO seguros a una cola limitada y Tk
los consume en el hilo principal. Nombres, datos civiles y disponibilidad de thumbnail
se resuelven posteriormente mediante `IdentityInfoProvider`; `PopupActionData` no
transporta PII. Formulario, enrollment, rollback y cierre limpian solicitudes
pendientes. Attendance y control de acceso permanecen desconectados.
### Application Event Bus interno (Fase 30)

`src/core/application_events/` ofrece un bus síncrono, en memoria y thread-safe
para publicar proyecciones seguras de cambios de la aplicación. Se crea una sola
instancia por ejecución cuando `application_events.enabled=true`. La integración
es paralela: las colas limitadas, callbacks, polling del dashboard y el EventBus
del Runtime continúan siendo los mecanismos vigentes; esta fase no migra
consumidores ni convierte el bus en fuente de verdad.

Los eventos contienen correlación, timestamps UTC y DTO seguros. Nunca incluyen
embeddings, imágenes, templates, modelos, repositorios ni formularios civiles.
El almacén de diagnóstico conserva solamente tipo, timestamp y origen, con un
límite configurable y sin persistencia.
### Reportes y estadísticas locales (Fase 31)

`ReportService` consolida en modo estrictamente read-only personas, eventos de
detección y asistencia desde sus repositorios SQLite. Los filtros se interpretan
en `America/Guayaquil`, se convierten a UTC para consultar y vuelven a hora local
para presentación. Toda consulta está paginada y limitada; los DTO indican
explícitamente `truncated` y `rows_considered`.

CSV está disponible con UTF-8, protección contra fórmulas y sin sobrescritura por
defecto. Excel queda no disponible si `openpyxl` no está instalado y PDF permanece
deshabilitado hasta adoptar una infraestructura adecuada. Ninguna exportación
incluye embeddings, imágenes, thumbnails o PII civil detallada; la cédula solo se
presenta enmascarada.
### Búsqueda avanzada de personas (Fase 32)

La administración civil dispone de búsqueda SQLite paginada por texto, cédula,
nombre, apellido, teléfono, email, estado y fecha de creación. Cada término libre
debe aparecer en al menos un campo y los términos se combinan con `AND`. Los
valores SQL siempre se parametrizan; orden y dirección se restringen a listas
internas.

La UI usa páginas de 25, 50 o 100 filas, debounce cancelable y fechas presentadas
en `America/Guayaquil`. La cédula se muestra enmascarada y cada fila consulta solo
sus estadísticas biométricas y un indicador de foto. No se añadieron índices ni
migraciones sin métricas reales que los justifiquen.
# Seguridad administrativa local (Fase 35)

FastVisionAI separa estrictamente los operadores administrativos de las personas
civiles y biométricas. Las cuentas viven en `users.db`; nunca en `people.db` ni en
`FaceGallery`. El primer arranque solicita crear un ADMIN sin credenciales por
defecto. Las contraseñas se derivan exclusivamente con `hashlib.scrypt`, salt
aleatorio y comparación constante. La autorización RBAC es obligatoria salvo que
`security.enabled=false` se configure explícitamente para desarrollo.
# Copias de seguridad seguras (Fase 36)

El subsistema genera archivos `.fvbackup` ZIP con un `manifest.json` versionado,
SHA-256 y snapshots consistentes de SQLite mediante `sqlite3.Connection.backup()`.
La restauración valida todo el paquete antes de reemplazar destinos, exige permiso
`RESTORE`, quiescencia completa y un nuevo arranque/login al finalizar.

> El backup contiene información sensible y no está cifrado. `encryption=NONE`.
> Debe almacenarse en un medio protegido; SHA-256 aporta integridad, no
> confidencialidad ni autenticidad.
# System Health & Performance Monitor (Fase 37)

El monitor técnico es exclusivamente observacional: reutiliza estados seguros ya
expuestos, realiza `SELECT 1` read-only y calcula FPS móvil con timestamps
monotónicos. No abre cámara, ejecuta inferencia, reinicia servicios ni escribe en
bases. Las latencias de procesamiento e inferencia permanecen `N/D` hasta disponer
de una medición fiable.
# Configuration Manager (Fase 38)

`ConfigurationService` centraliza carga, validación, diff, recarga y guardado
atómico sin reconstruir servicios. El formato legacy sin
`config_schema_version` sigue siendo legible y se marca explícitamente; la versión
actual es `1`. Development y Testing rechazan campos desconocidos, mientras
Production los reporta como warning y nunca los aplica silenciosamente.

Los cambios se clasifican como `HOT_RELOADABLE`, `RESTART_REQUIRED` o
`IMMUTABLE_AT_RUNTIME`. Recargar solo cambia el snapshot: no reinicia cámara,
Runtime ni bases. Las claves sensibles se redactan recursivamente.
