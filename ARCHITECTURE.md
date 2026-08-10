# FastVisionAI Architecture

## Person Database boundary

Person Database separa PII administrativa de la biometría. SQLite usa conexiones
por operación, transacciones cortas, consultas parametrizadas y migraciones
explícitas. FaceGallery conserva únicamente su `person_id` UUID y templates; la
cédula nunca sustituye esa clave interna.

La integración futura será una saga local: `INSERT PENDING_BIOMETRIC` → captura →
EnrollmentService/FaceGallery → `ACTIVE`. Cancelaciones o fallos previos a
FaceGallery eliminarán la reserva. Thumbnail y Gallery JSON+NPZ ocurrirán después
y sus fallos no cambiarán silenciosamente el estado biométrico o administrativo.

## Experimental identification presentation

`IdentificationPresentationController` transforma exclusivamente `MonitoringDTO`
en DTOs seguros para un popup Tk singleton. `IdentityInfoProvider` separa los
datos visibles de People Manager y Thumbnail Manager de la presentación; el
popup nunca conoce galería, matcher, RecognitionService ni payloads biométricos.
La estabilidad, cooldown y suspensión durante enrollment son controles UI y no
constituyen una decisión de identidad.

## Face Thumbnail Manager

`src/ui/thumbnails/` es una dependencia exclusiva de presentación. Recibe de la
capa UI candidatos temporales de rostros alineados ya aceptados, elige de forma
determinista la mejor pose frontal y escribe únicamente después de `ENROLLED` y
consentimiento. `person_id` es la única asociación; ninguna ruta ni imagen entra
en contratos biométricos, `RecognitionResult`, Gallery JSON o Gallery NPZ.

## Design principles

FastVisionAI separates capture, inference orchestration and domain features.
Components depend on typed contracts rather than concrete ML frameworks. Camera
capture must remain usable when inference is disabled or fails.

Core principles are bounded memory, explicit cancellation, lazy resources,
observable execution, relative paths and backend independence. External Python
plugins are trusted code and must be installed deliberately by an administrator.

## Data flow

```text
Camera Service -> Frame -> FrameQueue -> MinimalPreprocessor -> PreparedFrame
                                                        |
                                                        v
                                               InferenceScheduler
                                                |      |      |
                                             Plugin Plugin Plugin
                                                        |
                                                        v
                                                 InferenceResult
```

`Frame` is the immutable link to the original image and capture metadata.
`PreparedFrame` keeps that reference while describing the data presented to an
inference backend. `InferenceResult` groups detections, metrics, latency,
backend identity and extensible attachments.

## Execution contracts

`InferenceBackend` is the only execution contract. Built-in modules, external
plugins and the scheduler all implement it. No separate plugin execution
interface exists.

`InferenceContext.run_id` correlates inference, metrics and logs. The context is
reserved for future runtime resources without coupling plugins to ONNX Runtime,
TensorRT or DeepStream today.

The sequential `InferenceScheduler` orders plugins by ascending priority and
then stable plugin ID. It aggregates detections and namespaces attachments by
plugin. Configurable error isolation allows later plugins to run after a failure.

## Model lifecycle

`ModelManager` registers versioned `ModelSpec` objects and resolves artifacts
relative to the project. A model moves through `UNREGISTERED`, `REGISTERED`,
`LOADED`, `UNLOADING` and `FAILED`. Loading is lazy and cached. Concrete
`ModelLoader` adapters will be supplied later for PyTorch, ONNX Runtime and
TensorRT; none are dependencies of the current infrastructure.

## Plugin lifecycle

`PluginManager` discovers built-in and external modules, validates a complete
`PluginDescriptor`, applies configuration, dynamically instantiates only enabled
plugins and caches loaded instances. Descriptors include identity, version,
author, backend, capabilities, priority and enabled state.

## Observability

`BenchmarkManager` produces immutable snapshots containing effective FPS,
pipeline latency, queue wait, total execution time, dropped frames and per-plugin
timings/errors. It has no database or API dependency.

## Current boundaries

The current engine uses synthetic images and `DummyPlugin`. It contains no real
model, YOLO, tracking, recognition, biometrics, GPU scheduling, API or GUI.
Future Jetson support will be implemented through backend and model-loader
adapters without changing Camera Service or inference contracts.

The first real-model adapter is `PersonDetectorPlugin`. It uses a logical model
alias, normalized boxes and a lazy `ModelLoader`; weights are never downloaded
automatically. Device `auto` is resolved by `ModelRuntime`.

`FaceDetectorPlugin` is an independent OpenCV YuNet backend. Its ONNX artifact
is resolved through `ModelManager`, loaded lazily and hashed with SHA-256. It
emits normalized face-only boxes for multiple faces and preserves five
normalized landmarks per detection in namespaced result attachments. The
landmarks are metadata only; no recognition or biometric processing is part of
the plugin.

Face alignment is a downstream, model-free component and does not alter
inference contracts. `FaceAligner` consumes the detector result and its five
landmark groups in the fixed order left eye, right eye, nose, left mouth corner
and right mouth corner. Versioned template `fva-5pt-112-v1` deterministically
produces 112 x 112 crops, forward/inverse transforms and quality measurements.
Detection-to-landmark cardinality is validated before alignment. Low-quality
geometry may still yield an aligned crop; malformed or degenerate geometry is
represented as a typed rejected result.

Face embedding is a post-alignment biometric transformation. The functional
`FaceEmbeddingPlugin` consumes `AlignedFace` values directly and therefore is
not an `InferenceBackend`, is not discovered by `PluginManager`, and does not
run in the PreparedFrame Scheduler. It uses a dedicated `ModelManager` in the
end-to-end validator, explicit color/normalization/layout preprocessing and a
lazy OpenCV-DNN ONNX loader. Its only output is a typed, finite, L2-normalized,
read-only vector with provenance; comparison and identity policy remain out of
scope.

`FaceGallery` is the initial thread-safe, in-memory store for identities and
template-level biometric vectors. It fixes compatible model provenance from
the first template and rejects exact canonical duplicates. `FaceMatcher`
calculates bounded cosine scores and deterministic rankings; `MatchPolicy`
keeps optional decisions separate and disabled by default. No template fusion
or identity-level aggregation is performed. Optional JSON+NPZ development
persistence is explicit, integrity-checked and transactionally imported, but
is neither encrypted nor production-ready.

`EnrollmentService` is a transactional layer above `FaceGallery`. It validates
quality, provenance, exact duplicates and optional pairwise bounds before any
write. `min_pairwise_similarity` expresses minimum within-identity consistency;
`max_pairwise_similarity` limits near-identical samples that add no diversity.
Both default to `None`. Inputs beyond the configured maximum are selected by
stable input order, and rollback is verified against a logical gallery snapshot.

`CalibrationService` is a pure analysis layer downstream of face embeddings. It
groups samples by temporary identity, generates every genuine pair and either all
or a deterministic seeded sample of impostor pairs. It reports descriptive
distributions, explicit-threshold FAR/FRR and an estimated EER without recognizing
anyone or selecting a production threshold. Samples retain session, UTC capture,
source, resolution, quality and model provenance. Optional JSON+NPZ persistence
is disabled by default, integrity checked and loaded without pickle. Operator
capture remains isolated under `src/validation` and does not alter Camera Service.

`FaceCaptureQualityEvaluator` is an independent, stateful gate between alignment
and embedding during guided validation. Its fixed order is face count, alignment,
confidence, geometry, centering, image quality, requested pose, time, embedding
and diversity. It calls embedding only after visual and temporal gates pass and
never retains rejected images or rejected embeddings. Pose combines eye, nose and
mouth geometry and returns `UNKNOWN` for disagreement. `GuidedCapturePlan` advances
only after acceptance; expression prompts remain operator guidance rather than
automatic analysis.

`FaceQualityScorer` is a deterministic, stateless informational layer over
`GuidedQualityMetrics`. It does not participate in `GuidedCapturePolicy` and
cannot alter acceptance. All component normalization, weights, band boundaries,
critical penalties and structural invalid states are loaded from a versioned
profile. Higher-is-better metrics use clamped linear interpolation; centering
uses inverse clamped Euclidean offset; illumination uses a piecewise-linear ideal
band; pose uses explicit constants. The weighted sum is multiplied by penalties
and clamped to `0..100`. Structural failures yield `QualityBand.INVALID`.

`GuidedProfileDiagnosticCollector` is an optional validation observer. It copies
only scalar quality measurements, categorical poses, rejection states and face
counts from each result, then produces cohort distributions and current-profile
comparisons. It never retains the frame, aligned image, landmarks, embedding or
the `GuidedCaptureResult` object. Diagnostic mode cannot enable persistence.

`PeopleManagerController` is the transactional application boundary for the
local registered-people UI. It exposes safe scalar DTOs, reconstructs candidate
galleries for edits, deletion and additional-template batches, and publishes a
change only through `FaceGallery.replace_from()`. Additional capture suspends
matching and retains accepted samples only until the whole batch validates.
Persistence remains an explicit post-change operation through the existing
`GalleryPersistence`; import fully validates a temporary gallery before operator
confirmation and never merges galleries implicitly.

`RecognitionService` is a policy boundary above `FaceMatcher`. The matcher remains
score-only and non-deciding; the service converts its ranked template candidates
into a safe structured result. With automatic decisions disabled it always keeps
candidates informational and returns `NOT_EVALUATED`. `NO_GALLERY` and
`INCOMPATIBLE` are structural outcomes. Explicit test policies may produce
`MATCH`, `UNKNOWN` or `AMBIGUOUS`, but the project config contains no biometric
threshold and does not enable automatic recognition. Ambiguity compares only the
best candidate belonging to a different identity.

The experimental UI composes `ExperimentalRecognitionSession` with
`RecognitionService` only; presentation code no longer calls `FaceMatcher`.
`RecognitionResult` is reduced to `MonitoringDTO`, including a safe textual
recognition state. The UI composition root rejects automatic decisions and any
configured match threshold or ambiguity margin. Enrollment routes frames away
from the service until monitoring resumes.

`PersonEnrollmentCoordinator` owns the cross-store enrollment state machine:
`IDLE -> RESERVING_PERSON -> ENROLLING -> ACTIVATING_PERSON -> ACTIVE`. SQLite is
reserved as `PENDING_BIOMETRIC` before capture; only a committed FaceGallery
enrollment may transition it to `ACTIVE`. Cancellation and rejection remove the
current pending reservation. Activation failure enters `ROLLING_BACK`, removes
and verifies only the current gallery identity, then removes and verifies its
pending civil row. Any unverifiable compensation becomes `INCONSISTENT`; no
global cleanup is attempted. Persistence and thumbnails are post-activation
best-effort effects.

`PersonProfileController` is a read-oriented UI composition over PersonRepository,
the existing people controllers and ThumbnailManager. Every refresh rebuilds a
safe `PersonProfileDTO`; it is not a source of truth. Template vectors and model
provenance remain internal, while only counts, optional quality aggregates and
template date bounds cross the presentation boundary. Cedula lookup resolves to
the immutable internal `person_id` before profile composition.

The detection-event database is an independent observation log downstream of
safe monitoring DTOs. `DetectionEventService` owns in-memory monotonic cooldowns
and a bounded thread-safe presentation cache; SQLite remains authoritative.
LiveFaceSession performs writes from its worker and suppresses them from form
opening through enrollment and rollback. Unknown and multiple-face observations
are aggregate per camera because this phase deliberately has no tracking.

The Phase 17 dashboard remains a presentation projection over safe UI DTOs.
`DashboardStateStore` is bounded, ephemeral and never authoritative for gallery,
recognition, enrollment, runtime or configuration. `LiveFaceSession` exposes a
scalar telemetry snapshot reset per session; effective capture and pipeline FPS
are explicitly distinguished from pure model FPS, and inference latency remains
unavailable until a safe measurement exists. Tk widgets consume only DTOs and a
single transient visual buffer, while history stays memory-only and debounced.

## Runtime and events

`RuntimeRegistry` registers factories while `ModelRuntime` owns initialization,
preparation, inference and release. Typed `InternalEventBus` and
`ExternalEventBus` boundaries currently share a synchronous `EventBus`.
Architectural decisions are recorded under `docs/adr/`; plugin authors should
follow `PLUGIN_API.md`.

## Controlled Action Executor

`ActionExecutor` is the adapter-only boundary after `DecisionOrchestrator`. It does
not derive biometric decisions or inspect galleries, templates, images, recognition,
stability or civil data. Its immutable input contains only proposed/blocked action
names, orchestration state, safe correlation identifiers and an aware timestamp.

Execution is deterministic: proposals are deduplicated and processed as registered
popup, unregistered popup, then detection-event logging. Side effects can occur only
through injected `PopupActionAdapter` or `DetectionEventActionAdapter` instances.
With `automatic_execution_enabled=false`, the executor is strictly side-effect free,
reports `EXECUTION_DISABLED`, and invokes no adapter. Attendance and access actions
remain non-executable.

Phase 28 enables one low-risk adapter in the local development profile:
`LOG_DETECTION_EVENT`. Composition resolves a stable route once per session. When all
orchestrator, executor, service and adapter gates are enabled, event observations flow
exclusively through `DetectionEventServiceActionAdapter`; otherwise the legacy direct
session route remains active. They are mutually exclusive for every evaluation.
Cooldown, cache and persistence remain owned by `DetectionEventService`. Popup and
attendance adapters are not connected. Form, enrollment and rollback suspend both
routes and clear the dashboard projection to `NOT_EVALUATED`.

Phase 29 independently migrates popup presentation through a second adapter. A
session fixes `popup_mode` and `detection_logging_mode` separately at composition
time. Complete popup policy gates select the executor route; any missing gate selects
the legacy `MonitoringDTO` route. The two routes are never used for the same
evaluation.

`PopupActionData` contains only recognition state, optional similarity and a safe
message. The worker-side adapter asks the thread-safe
`IdentificationPresentationController` to apply presentation stability, cooldown and
provider resolution, then places only `IdentificationPopupDTO` values in a bounded
recent-state queue. Tk drains that queue on its main thread. Civil information remains
behind `IdentityInfoProvider`; ActionExecutor never receives it. The 60-second unknown
timer, singleton window and thumbnail rendering remain in the existing Tk boundary.
Pending popup DTOs are cleared or discarded across form, enrollment, rollback and
shutdown transitions.
# Capa UI local experimental

`src/ui/` es una frontera de presentación independiente. `ExperimentalRecognitionSession`
consulta `FaceMatcher` con `MatchPolicy(False, None)`; un error del matcher se
convierte en `ErrorDTO` recuperable y no detiene captura ni registro.
`LocalEnrollmentWorkflow` mantiene las muestras temporales privadas hasta la
confirmación, bloquea workflows simultáneos y usa `EnrollmentService` como único
punto de commit. La persistencia opcional se ejecuta solamente después de un
resultado `ENROLLED`; un fallo de persistencia no revierte silenciosamente la
galería en memoria.

La frontera pública usa `MonitoringDTO`, `EnrollmentProgressDTO`,
`EnrollmentResultDTO` y `ErrorDTO`. Estos contratos excluyen frames, rostros
alineados, arrays de embeddings y objetos de modelo. La imagen mostrada por
Tkinter vive únicamente durante el ciclo de presentación actual.

`LiveFaceSession` mantiene Tkinter en el hilo principal y ejecuta captura e
inferencia en un worker. Usa una cola visual de tamaño uno y colas limitadas de
eventos y comandos; cuando se llenan descarta el elemento más antiguo para
conservar estado reciente. `RealUIRuntimeAdapter` es la única frontera que conoce
CameraManager, Runtime, plugins, alineación, calidad y embedding. Los errores se
reducen a códigos seguros y el cierre solicita STOP, espera un timeout configurable
y ejecuta liberación idempotente.
## Attendance Service (Fase 23)

`AttendanceRepository` y su `attendance.db` independiente constituyen la fuente de
verdad. `AttendanceService` valida política y estado civil `ACTIVE` antes de escribir.
Dashboard, ficha de persona y ventana de historial son proyecciones de lectura y se
degradan de forma segura si SQLite no está disponible. No existe conexión desde
`DetectionEventService` ni `LiveFaceSession`: `evaluate_observation()` es inocuo cuando
la decisión automática está deshabilitada. Las conexiones SQLite son por operación,
con SQL parametrizado, transacciones explícitas y migración versionada.
## Stability Tracker (Fase 24)

`StabilityTracker` recibe observaciones escalares ya seguras desde `LiveFaceSession`
y produce una salida paralela `StabilityResult`. Cada instancia representa una sola
sesión/cámara y protege su estado con `RLock`. El estado se reinicia durante formulario
y enrollment, no se persiste y no entra en `RecognitionResult`, Gallery, events.db ni
attendance.db. El dashboard consume exclusivamente `StabilityDTO`; el popup conserva
su mecanismo anterior de estabilidad por frames.
## Identification Policy Engine (Fase 25)

`IdentificationPolicyEngine` es stateless, thread-safe por diseño y no conoce Gallery,
Matcher, RecognitionService, repositorios ni modelos. `LiveFaceSession` construye una
entrada segura desde `MonitoringDTO`, el resultado paralelo de estabilidad y el estado
administrativo resuelto. La salida `IdentificationPolicyDTO` se limita al dashboard;
no controla popups, eventos, attendance ni acciones externas. Durante formulario y
enrollment la proyección se limpia a `POLICY_NOT_EVALUATED`.
## Decision Orchestrator (Fase 26)

`DecisionOrchestrator` es stateless, thread-safe por diseño y side-effect free. Recibe
únicamente la proyección segura de monitorización, estabilidad, política identificatoria
y estado administrativo. Produce propuestas y bloqueos escalares para el dashboard,
sin depender de RecognitionService, repositorios, Gallery, DetectionEventService o
AttendanceService. Durante formulario y enrollment se limpia a `NOT_EVALUATED`.
## Fase 30 — Application Event Bus

El bus de aplicación vive en `src/core/application_events` y es deliberadamente
distinto de `src/engine/events/EventBus`, cuyo alcance sigue siendo el Runtime.
`ApplicationEventBus` toma un snapshot de suscripciones bajo `RLock`, libera el
lock antes de invocar handlers y mantiene el orden global de suscripción. Los
fallos de subscribers quedan aislados y una protección por hilo limita la
recursión de publicaciones anidadas.

`LiveFaceSession` conserva primero el DTO en su cola y publica después una
proyección tipada. Enrollment se publica únicamente en transiciones explícitas.
Los adaptadores de historial y popup publican después de procesar correctamente
sus solicitudes, y el cierre del popup emite una notificación sin impedir su
limpieza. `ApplicationEventDiagnosticsStore` es una proyección temporal limitada
que guarda solo `event_type`, `timestamp` y `source`. Ninguno de estos elementos
es fuente de verdad ni sustituye callbacks, colas o polling existentes.
## Fase 31 — Reportes locales

`src/core/reports` es una proyección read-only sobre `PersonRepository`,
`DetectionEventRepository` y `AttendanceRepository`. No usa ApplicationEventBus
como fuente de verdad ni ejecuta operaciones de escritura. Los rangos locales se
transforman a intervalos UTC `[inicio, fin)` y las consultas se paginan en bloques
de hasta 500, con un máximo configurable.

La UI de reportes depende de DTO seguros mediante `ReportController`. Su tarjeta
diaria usa un temporizador independiente del ciclo de frames y los fallos quedan
aislados como `N/D`. CSV es el único formato habilitado obligatoriamente; Excel es
opcional por importación diferida y PDF permanece indisponible.
## Fase 32 — Búsqueda civil avanzada

`AdvancedPeopleSearchController` se ubica entre `DatabasePeopleManagerController`
y `PeopleManagerWindow`. La fuente de búsqueda es exclusivamente SQLite; Gallery
solo aporta estadísticas para las personas de la página actual. Los filtros
locales se convierten a UTC y usan un intervalo superior exclusivo.

`PersonRepository.advanced_search()` y `count_advanced()` comparten el mismo
constructor de filtros parametrizados. El orden usa una whitelist y `person_id`
como desempate estable. Las transiciones administrativas continúan pasando por
`DatabasePeopleManagerController` y se limitan a ACTIVE/ DISABLED. El modo legacy
de la ventana permanece disponible cuando no se inyecta el controlador avanzado.
# Fase 35 — autenticación local y RBAC

`users.db → UserRepository → AuthenticationService → AuthenticatedSessionManager
→ AuthorizationEngine → AuthorizationController → UI administrativa`.

`users.db` es un dominio independiente: no contiene embeddings, templates,
imágenes ni datos civiles. El repositorio usa una conexión SQLite por operación y
protege al último ADMIN activo dentro de la misma transacción que cambia rol o
estado. La UI aplica permisos y los controladores vuelven a validarlos. Un timeout
durante enrollment queda pendiente hasta que el flujo termine o complete rollback.
Los eventos de seguridad admiten un callback seguro opcional; no se crea otra base
de auditoría ni se modifica ApplicationEventBus.
