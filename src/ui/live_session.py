"""Bounded worker coordinating the runtime adapter and safe UI controller."""

from __future__ import annotations

import logging
import math
import queue
import threading
import time
import uuid
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path

from src.engine.capture_quality import (
    CapturePlanStep, CapturePose, GuidedCapturePlan, GuidedCaptureState,
)
from src.engine.action_executor import (
    ActionExecutionInput, ActionExecutionResult, ActionExecutionState, ActionExecutor,
    DetectionEventActionData, PopupActionData,
)
from src.engine.decision_orchestrator import (
    DecisionOrchestrator, DecisionOrchestratorInput, DecisionOrchestratorResult,
    DecisionState, ProposedAction,
)
from src.engine.identification_policy import (
    IdentificationPolicyEngine, IdentificationPolicyInput,
    IdentificationPolicyResult, IdentificationPolicyState,
)
from src.engine.stability import StabilityObservation, StabilityTracker
from src.engine.gallery import FaceGallery
from src.engine.gallery.persistence import GalleryPersistence
from src.ui.contracts import (
    ActionExecutorDTO, DecisionOrchestratorDTO, EnrollmentProgressDTO,
    EnrollmentResultDTO, EnrollmentConflictDTO, ErrorDTO, PersonPhotoCaptureDTO,
    IdentificationPolicyDTO,
    MonitoringDTO,
    RegistrationFormData, RuntimeStatusDTO, StabilityDTO, UIErrorCode, UIState,
    VisualFrameDTO,
)
from src.ui.controller import LocalFaceUIController
from src.ui.enrollment_workflow import PersistenceCallback
from src.ui.runtime_adapter import (
    CameraAdapterError, InferenceAdapterError, UIRuntimeAdapter,
)
from src.ui.people.contracts import PeopleOperationResultDTO
from src.ui.people.controller import PeopleManagerController
from src.ui.identification import IdentificationPresentationController
from src.ui.person_enrollment import (
    ExistingActivePersonError, ExistingDisabledPersonError, ExistingPendingPersonError,
)
from src.ui.photo_capture import (
    AutomaticPhotoPolicy, AutomaticPhotoSelector, PersonPhotoController,
)
from src.ui.thumbnails import ThumbnailManager, select_thumbnail
from src.ui.thumbnails.contracts import ThumbnailSample
from src.ui.dashboard.contracts import (
    DashboardMetricState, DashboardMetricsDTO, DashboardQualityDTO,
    DashboardQualityMetricDTO,
)
from src.core.detection_events import (
    DetectionEventInput, DetectionEventService, DetectionEventType,
)
from src.core.application_events import (
    ActionExecutionUpdatedEvent, ApplicationEventBus, DecisionUpdatedEvent,
    EnrollmentCancelledEvent, EnrollmentFinishedEvent, EnrollmentStartedEvent,
    IdentificationPolicyUpdatedEvent, MonitoringUpdatedEvent, StabilityUpdatedEvent,
)
from datetime import datetime, timezone
from collections.abc import Callable
from src.camera.camera_types import CameraConfig, CameraType
from src.camera.source_discovery import redact_url

LOGGER = logging.getLogger(__name__)
UIEvent = (MonitoringDTO | EnrollmentProgressDTO | EnrollmentResultDTO | ErrorDTO |
           RuntimeStatusDTO | PeopleOperationResultDTO | StabilityDTO |
           EnrollmentConflictDTO | IdentificationPolicyDTO | DecisionOrchestratorDTO |
           ActionExecutorDTO | PersonPhotoCaptureDTO)


def _verify_enrollment_commit(
    result: EnrollmentResultDTO, gallery: FaceGallery,
    manifest_path: Path | None, archive_path: Path | None,
    target_samples: int,
) -> None:
    """Require the in-memory and persisted galleries to contain the full enrollment."""
    if result.enrollment_status.casefold() != "enrolled":
        raise RuntimeError("enrollment service rejected the biometric samples")
    identities = {item.person_id for item in gallery.list_identities()}
    if result.person_id not in identities:
        raise RuntimeError("committed gallery identity is missing")
    if len(gallery.templates(result.person_id)) < target_samples:
        raise RuntimeError("committed gallery has fewer templates than requested")
    if not result.persistence_requested:
        return
    if result.persistence_succeeded is not True:
        raise RuntimeError("gallery persistence did not succeed")
    if manifest_path is None or archive_path is None:
        raise RuntimeError("gallery persistence paths are unavailable")
    persisted = FaceGallery()
    GalleryPersistence(enabled=True).import_into(
        persisted, manifest_path, archive_path,
    )
    persisted_ids = {item.person_id for item in persisted.list_identities()}
    if result.person_id not in persisted_ids:
        raise RuntimeError("persisted gallery identity is missing")
    if len(persisted.templates(result.person_id)) < target_samples:
        raise RuntimeError("persisted gallery has fewer templates than requested")


def _safe_camera_reference(display_name: str | None, source_id: str | None) -> str | None:
    value = (display_name if display_name and display_name != "N/D" else source_id)
    if not value: return None
    cleaned = " ".join(str(value).split())[:160]
    return redact_url(cleaned) if "://" in cleaned else cleaned


class SessionCommandType(str, Enum):
    START_ENROLLMENT = "start_enrollment"
    CANCEL_ENROLLMENT = "cancel_enrollment"
    STOP = "stop"
    START_ADDITIONAL_ENROLLMENT = "start_additional_enrollment"
    START_FACE_REPLACEMENT = "start_face_replacement"
    START_EXISTING_PERSON_ENROLLMENT = "start_existing_person_enrollment"
    CAPTURE_ENROLLMENT_SAMPLE = "capture_enrollment_sample"
    START_PERSON_PHOTO = "start_person_photo"
    CAPTURE_PERSON_PHOTO = "capture_person_photo"
    CONFIRM_PERSON_PHOTO = "confirm_person_photo"
    RETAKE_PERSON_PHOTO = "retake_person_photo"
    CANCEL_PERSON_PHOTO = "cancel_person_photo"
    SWITCH_CAMERA = "switch_camera"
    RETRY_CAMERA = "retry_camera"


@dataclass(frozen=True, slots=True)
class SessionCommand:
    kind: SessionCommandType
    form: RegistrationFormData | None = None
    person_id: str | None = None
    camera_config: CameraConfig | None = None


@dataclass(slots=True)
class _EnrollmentStability:
    observations: int = 0
    best_guided: object | None = None
    best_image: bytes | None = None
    best_score: float = -1.0

    def reset(self) -> None:
        self.observations = 0; self.best_guided = None
        self.best_image = None; self.best_score = -1.0


class LiveFaceSession:
    def __init__(
        self, adapter: UIRuntimeAdapter, controller: LocalFaceUIController, *,
        event_queue_size: int = 16, command_queue_size: int = 8,
        close_timeout_seconds: float = 5.0,
        mirrored_source: bool = False,
        persistence: PersistenceCallback | None = None,
        manifest_path: Path | None = None, archive_path: Path | None = None,
        people_controller: PeopleManagerController | None = None,
        thumbnail_manager: ThumbnailManager | None = None,
        detection_event_service: DetectionEventService | None = None,
        camera_id: str | None = None,
        administrative_status_resolver: Callable[[str], str | None] | None = None,
        stability_tracker: StabilityTracker | None = None,
        identification_policy_engine: IdentificationPolicyEngine | None = None,
        decision_orchestrator: DecisionOrchestrator | None = None,
        action_executor: ActionExecutor | None = None,
        detection_event_logging_via_executor: bool = False,
        application_event_bus: ApplicationEventBus | None = None,
        identification_presentation: IdentificationPresentationController | None = None,
        manual_enrollment_capture: bool = False,
        enrollment_minimum_quality_score: float = 75.0,
        enrollment_stability_frames: int = 1,
        profile_photo_after_enrollment: bool = False,
        photo_controller: PersonPhotoController | None = None,
        photo_capture_policy: AutomaticPhotoPolicy | None = None,
        stay_alive_disconnected: bool = False,
        camera_display_name: str = "N/D", camera_source_type: str = "N/D",
        presentation_frame_sink: Callable[[VisualFrameDTO], object] | None = None,
    ) -> None:
        if min(event_queue_size, command_queue_size) <= 0 or close_timeout_seconds <= 0:
            raise ValueError("queue sizes and close timeout must be positive")
        self.adapter = adapter
        self.controller = controller
        self.visual_queue: queue.Queue[VisualFrameDTO] = queue.Queue(maxsize=1)
        self.event_queue: queue.Queue[UIEvent] = queue.Queue(maxsize=event_queue_size)
        self.command_queue: queue.Queue[SessionCommand] = queue.Queue(maxsize=command_queue_size)
        self.close_timeout_seconds = close_timeout_seconds
        self.mirrored_source = mirrored_source
        self._persistence = persistence
        self._manifest_path = manifest_path
        self._archive_path = archive_path
        self._people = people_controller
        self._thumbnails = thumbnail_manager
        self._detection_events = detection_event_service
        self._camera_id = camera_id
        self._administrative_status_resolver = administrative_status_resolver
        self._stability = stability_tracker
        self._identification_policy = identification_policy_engine
        self._decision_orchestrator = decision_orchestrator
        self._action_executor = action_executor
        if detection_event_logging_via_executor and (
            action_executor is None or not action_executor.has_detection_event_adapter
        ):
            raise ValueError("action-executor event mode requires a configured adapter")
        self._detection_event_logging_via_executor = detection_event_logging_via_executor
        self._application_events = application_event_bus
        self._identification_presentation = identification_presentation
        self._identification_pause_active = False
        self.manual_enrollment_capture = manual_enrollment_capture
        if not 0 <= enrollment_minimum_quality_score <= 100:
            raise ValueError("enrollment minimum quality score must be within 0..100")
        self.enrollment_minimum_quality_score = float(enrollment_minimum_quality_score)
        if enrollment_stability_frames <= 0:
            raise ValueError("enrollment stability frames must be positive")
        self.enrollment_stability_frames = int(enrollment_stability_frames)
        self._enrollment_stability = _EnrollmentStability()
        self.profile_photo_after_enrollment = bool(profile_photo_after_enrollment)
        self._capture_requested = False
        self._photo_controller = photo_controller
        self._photo_policy = photo_capture_policy or AutomaticPhotoPolicy()
        self._photo_selector = AutomaticPhotoSelector(self._photo_policy)
        self._stay_alive_disconnected = stay_alive_disconnected
        self._camera_display_name = camera_display_name
        self._camera_source_type = camera_source_type
        self._presentation_frame_sink = presentation_frame_sink
        self._photo_person_id: str | None = None
        self._photo_replace = False
        self._photo_capture_requested = False
        self._pending_photo_bytes: bytes | None = None
        self._pending_photo_quality: float | None = None
        self._photo_grace_until = 0.0
        self._event_history_suspended = threading.Event()
        self._session_id = str(uuid.uuid4())
        self._thumbnail_samples: list[ThumbnailSample] = []
        self._thumbnail_consent = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._plan: GuidedCapturePlan | None = None
        self._last_single_valid = False
        self._additional_person_id: str | None = None
        self._additional_samples: list[tuple[object, object]] = []
        # Session telemetry is reset for every LiveFaceSession instance.
        self._metrics_lock = threading.Lock()
        self._started_at = time.monotonic()
        self._frames_received = 0
        self._frames_processed = 0
        self._visual_frames_dropped = 0
        self._faces_detected_total = 0
        self._faces_detected_current = 0
        self._embeddings_generated = 0
        self._dashboard_quality = DashboardQualityDTO()

    @property
    def alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def session_id(self) -> str:
        """Safe correlation identifier for application-level UI events."""
        return self._session_id

    def start(self) -> None:
        if self.alive:
            raise RuntimeError("live session is already running")
        self._thread = threading.Thread(target=self._run, name="face-ui-worker", daemon=True)
        self._thread.start()

    def start_enrollment(self, form: RegistrationFormData) -> bool:
        accepted = self._command(SessionCommand(SessionCommandType.START_ENROLLMENT, form))
        if accepted: self.set_event_history_suspended(True)
        return accepted

    def cancel_enrollment(self) -> bool:
        return self._command(SessionCommand(SessionCommandType.CANCEL_ENROLLMENT))

    def capture_enrollment_sample(self) -> bool:
        if not self.manual_enrollment_capture:
            return False
        return self._command(SessionCommand(SessionCommandType.CAPTURE_ENROLLMENT_SAMPLE))

    def start_additional_enrollment(self, person_id: str) -> bool:
        accepted = self._command(SessionCommand(
            SessionCommandType.START_ADDITIONAL_ENROLLMENT, person_id=person_id
        ))
        if accepted: self.set_event_history_suspended(True)
        return accepted

    def start_face_replacement(self, person_id: str) -> bool:
        LOGGER.info(
            "people_face_session_method_invoked person_ref=%s workflow_state=%s",
            uuid.uuid5(uuid.NAMESPACE_OID, person_id).hex[:12], self.controller.state.value,
        )
        accepted=self._command(SessionCommand(
            SessionCommandType.START_FACE_REPLACEMENT,person_id=person_id,
        ))
        if accepted:self.set_event_history_suspended(True)
        return accepted

    def start_existing_person_enrollment(self, person_id: str) -> bool:
        LOGGER.info(
            "people_face_session_method_invoked person_ref=%s workflow_state=%s",
            uuid.uuid5(uuid.NAMESPACE_OID, person_id).hex[:12], self.controller.state.value,
        )
        accepted = self._command(SessionCommand(
            SessionCommandType.START_EXISTING_PERSON_ENROLLMENT, person_id=person_id,
        ))
        if accepted:
            self.set_event_history_suspended(True)
        return accepted

    def active_camera_ready(self) -> bool:
        """Report only the active runtime's health, never discovery probe results."""
        with self._metrics_lock:
            return self.alive and self._frames_received > 0

    def start_person_photo(self, person_id: str) -> bool:
        accepted = self._command(SessionCommand(
            SessionCommandType.START_PERSON_PHOTO, person_id=person_id,
        ))
        if accepted:
            self.set_event_history_suspended(True)
        return accepted

    def capture_person_photo(self) -> bool:
        return self._command(SessionCommand(SessionCommandType.CAPTURE_PERSON_PHOTO))

    def confirm_person_photo(self) -> bool:
        return self._command(SessionCommand(SessionCommandType.CONFIRM_PERSON_PHOTO))

    def retake_person_photo(self) -> bool:
        return self._command(SessionCommand(SessionCommandType.RETAKE_PERSON_PHOTO))

    def cancel_person_photo(self) -> bool:
        return self._command(SessionCommand(SessionCommandType.CANCEL_PERSON_PHOTO))

    def set_event_history_suspended(self, suspended: bool) -> None:
        if suspended:
            self._event_history_suspended.set()
            self._reset_stability(emit=True)
        else:
            self._event_history_suspended.clear()

    @property
    def camera_switch_allowed(self) -> bool:
        return not (
            self._event_history_suspended.is_set() or self._plan is not None
            or self._photo_person_id is not None or self.controller.enrollment.active
        )

    def switch_camera(self, config: CameraConfig) -> bool:
        if not self.camera_switch_allowed:
            return False
        return self._command(SessionCommand(
            SessionCommandType.SWITCH_CAMERA, camera_config=config,
        ))

    def retry_camera(self) -> bool:
        if not self.camera_switch_allowed:
            return False
        return self._command(SessionCommand(SessionCommandType.RETRY_CAMERA))

    def request_stop(self) -> None:
        self._stop.set()
        self._command(SessionCommand(SessionCommandType.STOP))

    def close(self, timeout: float | None = None) -> bool:
        self.request_stop()
        thread = self._thread
        if thread is not None:
            thread.join(self.close_timeout_seconds if timeout is None else max(0, timeout))
        # Idempotent release also protects a timed-out worker.
        self.adapter.close()
        if self.controller.enrollment.active:
            self.controller.cancel_enrollment()
        self._clear_thumbnail_samples()
        self._pending_photo_bytes = None
        self._photo_person_id = None
        return not self.alive

    def drain_events(self) -> tuple[UIEvent, ...]:
        return _drain(self.event_queue)

    def take_latest_visual(self) -> VisualFrameDTO | None:
        items = _drain(self.visual_queue)
        return items[-1] if items else None

    def dashboard_telemetry(self) -> tuple[DashboardMetricsDTO, DashboardQualityDTO]:
        """Return a scalar-only snapshot; unavailable inference latency remains None."""
        with self._metrics_lock:
            uptime = max(0.0, time.monotonic() - self._started_at)
            capture_fps = self._frames_received / uptime if uptime > 0 else None
            processing_fps = self._frames_processed / uptime if uptime > 0 else None
            return DashboardMetricsDTO(
                self._frames_received, self._frames_processed, self._visual_frames_dropped,
                self._faces_detected_total, self._faces_detected_current,
                self._embeddings_generated, capture_fps, processing_fps, uptime, None,
            ), self._dashboard_quality

    def _command(self, command: SessionCommand) -> bool:
        try:
            self.command_queue.put_nowait(command)
            return True
        except queue.Full:
            if command.kind is SessionCommandType.STOP:
                _put_recent(self.command_queue, command)
                return True
            return False

    def _run(self) -> None:
        try:
            try:
                opened = self.adapter.open()
            except CameraAdapterError:
                self._error(UIErrorCode.CAMERA_ERROR, "No se pudo abrir la cámara", False)
                return
            except Exception:
                self._error(UIErrorCode.INFERENCE_ERROR,
                            "No se pudo preparar el motor biométrico.", False)
                return
            if not opened:
                self._error(UIErrorCode.CAMERA_ERROR,
                            "Cámara desconectada. Use Buscar cámaras para seleccionar otra.", True)
                if not self._stay_alive_disconnected:
                    return
            self._event(self._safe_status())
            while not self._stop.is_set():
                self._commands()
                if self._stop.is_set():
                    break
                requested = (
                    requested_capture_pose(self._plan.current, self.mirrored_source)
                    if self._plan else CapturePose.FRONTAL
                )
                try:
                    step = self.adapter.process(requested)
                except CameraAdapterError:
                    self._event(self._safe_status())
                    self._error(UIErrorCode.CAMERA_ERROR,
                                "La cámara no está disponible; se aplicó su política de reconexión.",
                                True)
                    continue
                except InferenceAdapterError:
                    self._error(UIErrorCode.INFERENCE_ERROR,
                                "La inferencia falló; la sesión continúa.", True)
                    continue
                except Exception:
                    self._error(UIErrorCode.INFERENCE_ERROR,
                                "Error interno de inferencia; la sesión continúa.", True)
                    continue
                dropped = _put_recent(self.visual_queue, step.visual)
                if self._presentation_frame_sink is not None:
                    try:self._presentation_frame_sink(step.visual)
                    except Exception:pass
                with self._metrics_lock:
                    self._frames_received += 1
                    self._frames_processed += 1
                    self._visual_frames_dropped += int(dropped)
                    self._faces_detected_total += step.face_count
                    self._faces_detected_current = step.face_count
                    self._embeddings_generated += int(step.monitoring_embedding is not None)
                    self._dashboard_quality = _dashboard_quality(step.guided)
                self._last_single_valid = (
                    step.face_count == 1 and step.guided.visual_quality_passed
                )
                if self._photo_person_id is not None:
                    self._photo_step(step)
                elif self._plan is not None:
                    if not self.manual_enrollment_capture or self._capture_requested:
                        self._capture_requested = False
                        self._enrollment_step(step.guided, step.aligned_face_bytes)
                    else:
                        score = step.guided.face_quality_score
                        self._event(EnrollmentProgressDTO(
                            UIState.ENROLLMENT_CAPTURE,
                            operator_instruction(self._plan.current, self.mirrored_source),
                            self._plan.accepted_count, self._plan.target_samples,
                            tuple(reason.value for reason in step.guided.reasons),
                            None if score is None else score.total_score,
                            None if score is None else score.quality_band.value, True,
                        ))
                else:
                    self._monitoring_step(
                        step.face_count, step.guided, step.monitoring_embedding
                    )
        finally:
            self.adapter.close()
            if self.controller.enrollment.active:
                self.controller.cancel_enrollment()
            self._reset_stability(emit=False)
            if self._people is not None and self._additional_person_id is not None:
                self._people.cancel_additional()
                self._additional_person_id = None
                self._additional_samples.clear()
            self._clear_thumbnail_samples()
            self._pending_photo_bytes = None
            self._photo_person_id = None
            self._event(self._safe_status())

    def _commands(self) -> None:
        for command in _drain(self.command_queue):
            if command.kind is SessionCommandType.STOP:
                self._stop.set()
            elif command.kind is SessionCommandType.CANCEL_ENROLLMENT:
                cancelled_person_id = self._additional_person_id
                was_active = bool(
                    self.controller.enrollment.active or self._plan is not None
                    or self._additional_person_id is not None
                )
                if self.controller.enrollment.active:
                    self.controller.cancel_enrollment()
                self._plan = None
                self._capture_requested = False
                if self._people is not None and self._additional_person_id is not None:
                    self._event(self._people.cancel_additional())
                self._additional_person_id = None
                self._additional_samples.clear()
                self._clear_thumbnail_samples()
                self._enrollment_stability.reset()
                self.adapter.set_thumbnail_capture(False)
                self.adapter.new_evaluator()
                self._reset_stability(emit=True)
                self._event_history_suspended.clear()
                self._event(MonitoringDTO(
                    UIState.MONITORING, "Registro cancelado", None, None,
                    "deshabilitada / NOT_EVALUATED", True,
                ))
                if was_active:
                    self._publish_application(EnrollmentCancelledEvent(
                        source="live_face_session", session_id=self._session_id,
                        run_id=self._session_id, person_id=cancelled_person_id,
                        state="CANCELLED", message="enrollment_cancelled",
                    ))
            elif command.kind is SessionCommandType.START_ENROLLMENT and command.form is not None:
                if self._plan is not None or self.controller.enrollment.active:
                    self._error(UIErrorCode.ENROLLMENT_ERROR,
                                "Ya existe un registro guiado activo.", True)
                    continue
                try:
                    self._reset_stability(emit=True)
                    plan = GuidedCapturePlan(self.controller.enrollment.target_samples)
                    progress = self.controller.begin_enrollment(command.form)
                    self.adapter.new_evaluator()
                    self._thumbnail_consent = command.form.consent_confirmed
                    self._thumbnail_samples.clear()
                    self._enrollment_stability.reset()
                    self.adapter.set_thumbnail_capture(True)
                    self._plan = plan
                    self._event(progress)
                    self._publish_application(EnrollmentStartedEvent(
                        source="live_face_session", session_id=self._session_id,
                        run_id=self._session_id, person_id=command.form.person_id,
                        state="ENROLLING", message="primary_enrollment_started",
                    ))
                except (ExistingActivePersonError, ExistingDisabledPersonError,
                        ExistingPendingPersonError) as exc:
                    self._plan = None
                    self._capture_requested = False
                    self._clear_thumbnail_samples()
                    self.adapter.set_thumbnail_capture(False)
                    active = isinstance(exc, ExistingActivePersonError)
                    disabled = isinstance(exc, ExistingDisabledPersonError)
                    display_name = None
                    template_count = 0
                    if self._people is not None:
                        try:
                            details = self._people.details(exc.person_id)
                            display_name = details.summary.display_name
                            template_count = details.summary.template_count
                        except Exception:
                            pass
                    thumbnail_available = bool(
                        self._thumbnails is not None
                        and self._thumbnails.exists(exc.person_id)
                    )
                    self._event(EnrollmentConflictDTO(
                        UIState.ERROR, exc.person_id,
                        "ACTIVE" if active else "DISABLED" if disabled else "PENDING_BIOMETRIC",
                        str(exc),
                        True, active and template_count == 0, False, display_name,
                        thumbnail_available, template_count, disabled,
                    ))
                except Exception as exc:
                    safe_person = uuid.uuid5(
                        uuid.NAMESPACE_OID, command.form.person_id,
                    ).hex[:12]
                    coordinator = getattr(self.controller, "person_coordinator", None)
                    workflow_state = getattr(getattr(coordinator, "state", None), "value", None)
                    LOGGER.error(
                        "Enrollment start failed; stage=begin_enrollment person_ref=%s "
                        "error_type=%s workflow_state=%s biometric_payload=omitted",
                        safe_person, type(exc).__name__, workflow_state or self.controller.state.value,
                    )
                    if self.controller.enrollment.active:
                        self.controller.cancel_enrollment()
                    self._plan = None
                    self._capture_requested = False
                    self._clear_thumbnail_samples()
                    self.adapter.set_thumbnail_capture(False)
                    self._event_history_suspended.clear()
                    self._error(UIErrorCode.ENROLLMENT_ERROR,
                                "No se pudo iniciar el registro guiado "
                                f"({type(exc).__name__}; estado "
                                f"{workflow_state or self.controller.state.value}).", False)
            elif (command.kind in {SessionCommandType.START_ADDITIONAL_ENROLLMENT,
                                   SessionCommandType.START_FACE_REPLACEMENT,
                                   SessionCommandType.START_EXISTING_PERSON_ENROLLMENT} and
                  command.person_id is not None):
                if self._plan is not None or self.controller.enrollment.active or (
                    self._additional_person_id is not None
                ):
                    self._error(UIErrorCode.ENROLLMENT_ERROR,
                                "Ya existe un registro guiado activo.", True)
                    continue
                if self._people is None:
                    self._error(UIErrorCode.ENROLLMENT_ERROR,
                                "El administrador de personas no está disponible.", False)
                    continue
                safe_person = uuid.uuid5(uuid.NAMESPACE_OID, command.person_id).hex[:12]
                civil_status = "UNKNOWN"
                identity_present = False
                template_count = 0
                try:
                    summary = self._people.details(command.person_id).summary
                    civil_status = summary.civil_status or "UNKNOWN"
                    template_count = summary.template_count
                    gallery = getattr(self._people, "biometrics", self._people).gallery
                    identity_present = any(
                        item.person_id == command.person_id
                        for item in gallery.list_identities()
                    )
                except Exception:
                    pass
                LOGGER.info(
                    "face_enrollment_action_requested person_ref=%s civil_status=%s "
                    "gallery_identity_present=%s template_count=%d biometric_payload=omitted",
                    safe_person, civil_status, identity_present, template_count,
                )
                try:
                    self._reset_stability(emit=True)
                    LOGGER.info(
                        "face_enrollment_begin_called person_ref=%s workflow_state=%s",
                        safe_person, self.controller.state.value,
                    )
                    if command.kind is SessionCommandType.START_FACE_REPLACEMENT:
                        started = self._people.begin_replacement(command.person_id)
                    elif command.kind is SessionCommandType.START_EXISTING_PERSON_ENROLLMENT:
                        begin_existing = getattr(
                            self._people, "begin_existing_person_enrollment", None,
                        )
                        if begin_existing is None:
                            raise RuntimeError("existing-person enrollment is unavailable")
                        started = begin_existing(command.person_id)
                    else:
                        started = self._people.begin_additional(command.person_id)
                    if not started.success:
                        LOGGER.error(
                            "face_enrollment_started=false stage=begin_replacement "
                            "person_ref=%s error_type=WorkflowRejected workflow_state=%s "
                            "biometric_payload=omitted",
                            safe_person, started.state.value,
                        )
                        self._event(started)
                        self._error(UIErrorCode.ENROLLMENT_ERROR,
                                    "No se pudo iniciar el registro facial.", False)
                        continue
                    self._plan = GuidedCapturePlan(self.controller.enrollment.target_samples)
                    self._additional_person_id = command.person_id
                    self._additional_samples.clear()
                    self.adapter.set_thumbnail_capture(False)
                    self.adapter.new_evaluator()
                    self._event(started)
                    self._event(EnrollmentProgressDTO(
                        UIState.ENROLLING, "Mire al frente", 0, self._plan.target_samples,
                        (), None, None, True,
                    ))
                    LOGGER.info(
                        "face_enrollment_progress_received person_ref=%s workflow_state=%s "
                        "accepted_samples=0 target_samples=%d",
                        safe_person, started.state.value, self._plan.target_samples,
                    )
                    LOGGER.info(
                        "face_enrollment_started=true person_ref=%s workflow_state=%s "
                        "biometric_payload=omitted",
                        safe_person, started.state.value,
                    )
                    self._publish_application(EnrollmentStartedEvent(
                        source="live_face_session", session_id=self._session_id,
                        run_id=self._session_id, person_id=command.person_id,
                        state="ENROLLING", message="additional_enrollment_started",
                    ))
                except Exception as exc:
                    workflow_state = self.controller.state.value
                    LOGGER.exception(
                        "face_enrollment_started=false stage=begin_replacement person_ref=%s "
                        "error_type=%s workflow_state=%s biometric_payload=omitted",
                        safe_person, type(exc).__name__, workflow_state,
                    )
                    self._plan = None
                    self._additional_person_id = None
                    self._additional_samples.clear()
                    self._event_history_suspended.clear()
                    self._error(UIErrorCode.ENROLLMENT_ERROR,
                                "No se pudo iniciar el registro facial.", False)
            elif command.kind is SessionCommandType.CAPTURE_ENROLLMENT_SAMPLE:
                if self._plan is None:
                    self._error(UIErrorCode.ENROLLMENT_ERROR,
                                "No existe una captura de enrollment activa.", True)
                else:
                    self._capture_requested = True
            elif command.kind is SessionCommandType.START_PERSON_PHOTO:
                self._start_person_photo(command.person_id)
            elif command.kind is SessionCommandType.CAPTURE_PERSON_PHOTO:
                if self._photo_person_id is not None:
                    self._photo_capture_requested = True
            elif command.kind is SessionCommandType.RETAKE_PERSON_PHOTO:
                if self._photo_person_id is not None:
                    self._pending_photo_bytes = None
                    self._pending_photo_quality = None
                    self._photo_capture_requested = False
                    self._photo_selector.reset()
            elif command.kind is SessionCommandType.CONFIRM_PERSON_PHOTO:
                self._confirm_person_photo()
            elif command.kind is SessionCommandType.CANCEL_PERSON_PHOTO:
                self._finish_person_photo("Captura de fotografía cancelada.", saved=False)
            elif command.kind is SessionCommandType.SWITCH_CAMERA and command.camera_config is not None:
                if not self.camera_switch_allowed:
                    self._error(UIErrorCode.CAMERA_ERROR,
                                "No se puede cambiar la cámara durante una operación sensible.", True)
                    continue
                try:
                    opened = self.adapter.switch_camera(command.camera_config)
                    self._camera_id = command.camera_config.name
                    self._camera_display_name = command.camera_config.name
                    self._camera_source_type = (
                        "DroidCam-OBS" if command.camera_config.camera_type is CameraType.USB
                        and any(marker in command.camera_config.name.casefold()
                                for marker in ("droidcam", "obs", "virtual", "loopback")) else
                        "V4L2" if command.camera_config.camera_type is CameraType.USB else
                        "HTTP/MJPEG" if str(command.camera_config.source).lower().startswith(("http://", "https://"))
                        else "RTSP"
                    )
                    self._event(self._safe_status())
                    if not opened:
                        self._error(UIErrorCode.CAMERA_ERROR,
                                    "La cámara seleccionada no está disponible.", True)
                except Exception:
                    LOGGER.exception("Camera switch failed; source details omitted")
                    self._error(UIErrorCode.CAMERA_ERROR,
                                "No se pudo cambiar la cámara.", True)
            elif command.kind is SessionCommandType.RETRY_CAMERA:
                if not self.camera_switch_allowed:
                    self._error(UIErrorCode.CAMERA_ERROR,
                                "No se puede cambiar de cámara durante un registro.", True)
                    continue
                try:
                    self._event(replace(self._safe_status(), camera_state="reconnecting"))
                    self.adapter.retry_camera()
                    self._event(self._safe_status())
                except Exception:
                    LOGGER.exception("Camera retry failed; source details omitted")
                    self._error(UIErrorCode.CAMERA_ERROR, "No se pudo reconectar la cámara.", True)

    def _safe_status(self) -> RuntimeStatusDTO:
        return replace(
            self.adapter.status(), camera_switch_allowed=self.camera_switch_allowed,
            camera_source_name=self._camera_display_name,
            camera_source_type=self._camera_source_type,
        )

    def _monitoring_step(self, face_count: int, guided, monitoring_embedding) -> None:
        if face_count == 0:
            self._emit_monitoring(MonitoringDTO(
                UIState.NO_FACE, "No se detectó un rostro", None, None,
                "deshabilitada / NOT_EVALUATED", True,
            ))
            return
        if face_count > 1:
            self._emit_monitoring(MonitoringDTO(
                UIState.MULTIPLE_FACES, "MULTIPLE_FACES", None, None,
                "deshabilitada / NOT_EVALUATED", True,
            ))
            return
        score = guided.face_quality_score
        if monitoring_embedding is None:
            state = (GuidedCaptureState.ALIGNMENT_FAILED.value
                     if guided.primary_state is GuidedCaptureState.ALIGNMENT_FAILED
                     else GuidedCaptureState.EMBEDDING_FAILED.value)
            self._emit_monitoring(MonitoringDTO(
                UIState.MONITORING, state, None, None,
                "deshabilitada / NOT_EVALUATED", True,
                None if score is None else score.total_score,
                None if score is None else score.quality_band.value,
            ))
            return
        LOGGER.info("Recognition pipeline started")
        dto, error = self.controller.monitor(monitoring_embedding, score)
        LOGGER.info(
            "Recognition candidate: %s",
            dto.candidate_display_name or dto.candidate_person_id or "none",
        )
        LOGGER.info(
            "Similarity: %s",
            "N/D" if dto.similarity is None else f"{dto.similarity:.6f}",
        )
        LOGGER.info("Recognition state: %s", dto.recognition_state)
        if (dto.recognition_state == "NOT_EVALUATED"
                and dto.candidate_person_id is not None):
            dto = replace(
                dto, message="CANDIDATO BIOMÉTRICO — NO EVALUADO — SISTEMA PENDIENTE DE CALIBRACIÓN"
            )
        self._emit_monitoring(dto)
        if error is not None:
            self._event(error)

    def _start_person_photo(self, person_id: str | None) -> None:
        if (self._plan is not None or self._photo_person_id is not None
                or person_id is None or self._photo_controller is None):
            self._event_history_suspended.clear()
            self._error(UIErrorCode.THUMBNAIL_ERROR,
                        "No se pudo iniciar la captura de fotografía.", True)
            return
        try:
            self._photo_replace = self._photo_controller.begin(person_id)
            self._photo_person_id = person_id
            self._pending_photo_bytes = None
            self._pending_photo_quality = None
            self._photo_capture_requested = False
            self._photo_selector.reset()
            self.adapter.set_thumbnail_capture(True)
            self.adapter.new_evaluator()
            self._reset_stability(emit=True)
            self._event(PersonPhotoCaptureDTO(
                UIState.CAPTURE_PERSON_PHOTO, person_id,
                "Centre su rostro. Buscando la mejor imagen...", None,
                False, False, self._photo_replace,
            ))
        except Exception:
            LOGGER.exception("Person photo capture start failed; visual payload omitted")
            self._event_history_suspended.clear()
            self._error(UIErrorCode.THUMBNAIL_ERROR,
                        "No se pudo iniciar la captura de fotografía.", True)

    def _photo_step(self, step) -> None:
        person_id = self._photo_person_id
        if person_id is None:
            return
        score = step.guided.face_quality_score
        quality = None if score is None else score.total_score
        ready = bool(step.face_count == 1 and step.guided.visual_quality_passed
                     and step.aligned_face_bytes and quality is not None
                     and quality >= self._photo_policy.minimum_quality_score)
        if self._pending_photo_bytes is not None:
            self._event(PersonPhotoCaptureDTO(
                UIState.CAPTURE_PERSON_PHOTO, person_id, "Fotografía capturada.",
                self._pending_photo_quality, True, True,
                self._photo_replace, self._pending_photo_bytes,
                self._photo_policy.stability_frames, self._photo_policy.stability_frames,
            ))
            return
        if self._photo_capture_requested:
            self._photo_capture_requested = False
            if ready:
                self._pending_photo_bytes = step.aligned_face_bytes
                self._pending_photo_quality = quality
                self._event(PersonPhotoCaptureDTO(
                    UIState.CAPTURE_PERSON_PHOTO, person_id,
                    "Revise la fotografía capturada.", quality, True, True,
                    self._photo_replace, self._pending_photo_bytes,
                ))
                return
        reasons = set(step.guided.reasons)
        message = (
            "Buscando rostro..." if step.face_count == 0 else
            "Se detectaron varios rostros." if step.face_count > 1 else
            "Acérquese un poco." if GuidedCaptureState.FACE_TOO_SMALL in reasons else
            "Centre su rostro." if (GuidedCaptureState.FACE_OFF_CENTER in reasons
                                     or GuidedCaptureState.PARTIALLY_VISIBLE in reasons) else
            "Calidad insuficiente." if (not step.guided.visual_quality_passed
                                         or quality is None or quality <
                                         self._photo_policy.minimum_quality_score) else
            "Fotografía lista para capturar."
        )
        if self._photo_policy.mode == "automatic":
            automatic = self._photo_selector.observe(
                valid=ready, image_bytes=step.aligned_face_bytes,
                quality_score=quality, rejection_message=message,
            )
            if automatic.captured_bytes is not None:
                self._pending_photo_bytes = automatic.captured_bytes
                self._pending_photo_quality = automatic.quality_score
                self._event(PersonPhotoCaptureDTO(
                    UIState.CAPTURE_PERSON_PHOTO, person_id, automatic.message,
                    automatic.quality_score, True, True, self._photo_replace,
                    self._pending_photo_bytes, automatic.observations,
                    automatic.required_observations,
                ))
                return
            self._event(PersonPhotoCaptureDTO(
                UIState.CAPTURE_PERSON_PHOTO, person_id, automatic.message,
                automatic.quality_score, ready, False, self._photo_replace, None,
                automatic.observations, automatic.required_observations,
            ))
            return
        self._event(PersonPhotoCaptureDTO(
            UIState.CAPTURE_PERSON_PHOTO, person_id, message, quality,
            ready, False, self._photo_replace,
        ))

    def _confirm_person_photo(self) -> None:
        if (self._photo_person_id is None or self._pending_photo_bytes is None
                or self._photo_controller is None):
            return
        try:
            self._photo_controller.save(
                self._photo_person_id, self._pending_photo_bytes,
                replace=self._photo_replace,
            )
            self._finish_person_photo("Fotografía guardada correctamente.", saved=True)
        except Exception:
            LOGGER.exception("Person photo save failed; visual payload omitted")
            self._error(UIErrorCode.THUMBNAIL_ERROR,
                        "No se pudo guardar la fotografía.", True)

    def _finish_person_photo(self, message: str, *, saved: bool) -> None:
        person_id = self._photo_person_id
        if person_id is None:
            return
        replace_existing = self._photo_replace
        self._pending_photo_bytes = None
        self._pending_photo_quality = None
        self._photo_capture_requested = False
        self._photo_selector.reset()
        self._photo_person_id = None
        self.adapter.set_thumbnail_capture(False)
        self.adapter.new_evaluator()
        self._reset_stability(emit=True)
        self._photo_grace_until = time.monotonic() + 2.5
        self._event_history_suspended.clear()
        self._event(PersonPhotoCaptureDTO(
            UIState.MONITORING, person_id, message, None, saved, False,
            replace_existing,
        ))

    def _emit_monitoring(self, dto: MonitoringDTO) -> None:
        monitoring = getattr(getattr(self, "controller", None), "monitoring", None)
        gallery = getattr(monitoring, "gallery", None)
        gallery_size = 0 if gallery is None else len(gallery.list_identities())
        LOGGER.debug(
            "Recognition diagnostic face_detected=%s embedding_generated=%s gallery_size=%d "
            "candidate_present=%s candidate_similarity=%s recognition_state=%s evaluated=%s",
            dto.state is UIState.MONITORING, dto.state is UIState.MONITORING,
            gallery_size,
            dto.candidate_person_id is not None,
            "N/D" if dto.similarity is None else f"{dto.similarity:.6f}",
            dto.recognition_state, dto.evaluated,
        )
        presentation = getattr(self, "_identification_presentation", None)
        pause_remaining = (
            0.0 if presentation is None
            else presentation.registered_pause_remaining_seconds()
        )
        if pause_remaining > 0:
            if not self._identification_pause_active:
                self._identification_pause_active = True
                self._reset_stability(emit=False)
            self._event(self._policy_not_evaluated_dto())
            self._event(self._orchestration_not_evaluated_dto())
            self._event(self._action_not_evaluated_dto())
            self._event(dto)
            return
        if getattr(self, "_identification_pause_active", False):
            self._identification_pause_active = False
            self._reset_stability(emit=True)
        stability = getattr(self, "_stability", None)
        stability_result = None
        face_count = (0 if dto.state is UIState.NO_FACE else
                      2 if dto.state is UIState.MULTIPLE_FACES else 1)
        if stability is not None:
            stability_result = stability.observe(StabilityObservation(
                None, dto.candidate_person_id, dto.recognition_state, dto.similarity,
                face_count, dto.quality_score, self._session_id,
            ))
            self._event(_stability_dto(stability_result, stability))
        identification = self._evaluate_identification_policy(
            dto, stability_result, face_count,
        )
        self._event(identification)
        orchestration = self._evaluate_decision_orchestrator(
            dto, stability_result, identification, face_count,
        )
        self._event(orchestration)
        action = self._evaluate_action_executor(orchestration, dto, face_count)
        self._event(action)
        LOGGER.debug(
            "Recognition diagnostic recognition_state=%s candidate_present=%s "
            "similarity=%s stability_state=%s policy_state=%s decision_state=%s "
            "popup_action=%s",
            dto.recognition_state, dto.candidate_person_id is not None,
            "N/D" if dto.similarity is None else f"{dto.similarity:.6f}",
            "NO_OBSERVATION" if stability_result is None else stability_result.state.value,
            identification.state, orchestration.state,
            next((item for item in action.requested_actions
                  if item in {ProposedAction.SHOW_REGISTERED_POPUP.value,
                              ProposedAction.SHOW_UNREGISTERED_POPUP.value}), "NONE"),
        )
        if (not getattr(self, "_detection_event_logging_via_executor", False)
                and self._detection_events is not None
                and not self._event_history_suspended.is_set()):
            event_type = None
            if dto.state is UIState.MULTIPLE_FACES:
                event_type = DetectionEventType.MULTIPLE_FACES
            elif dto.recognition_state == "INCOMPATIBLE":
                event_type = DetectionEventType.INCOMPATIBLE
            elif (dto.candidate_person_id is not None and (
                  stability is None or (
                      stability_result is not None
                      and stability_result.state.value == "STABLE"
                      and identification.eligible
                      and identification.administrative_status == "ACTIVE"))):
                event_type = DetectionEventType.REGISTERED_CANDIDATE
            elif dto.state is not UIState.NO_FACE and dto.recognition_state in {
                "NO_GALLERY", "NOT_EVALUATED",
            }:
                event_type = DetectionEventType.UNREGISTERED
            if event_type is not None:
                status = None
                if (dto.candidate_person_id is not None
                        and self._administrative_status_resolver is not None):
                    try: status = self._administrative_status_resolver(dto.candidate_person_id)
                    except Exception: status = None
                self._detection_events.observe(DetectionEventInput(
                    event_type, (dto.candidate_person_id if event_type is
                                 DetectionEventType.REGISTERED_CANDIDATE else None),
                    datetime.now(timezone.utc),
                    _safe_camera_reference(getattr(self, "_camera_display_name", None),
                                           self._camera_id),
                    dto.candidate_display_name, dto.similarity,
                    dto.quality_score, "NOT_EVALUATED" if event_type is
                    DetectionEventType.REGISTERED_CANDIDATE else dto.recognition_state,
                    status, self._session_id,
                ))
        self._event(dto)

    def _reset_stability(self, *, emit: bool) -> None:
        stability = getattr(self, "_stability", None)
        result = None if stability is None else stability.reset()
        if emit:
            self._event(self._orchestration_not_evaluated_dto())
            self._event(self._action_not_evaluated_dto())
            self._event(self._policy_not_evaluated_dto())
        if emit and result is not None:
            self._event(_stability_dto(result, stability))

    def _evaluate_identification_policy(
        self, dto: MonitoringDTO, stability_result, face_count: int,
    ) -> IdentificationPolicyDTO:
        engine = getattr(self, "_identification_policy", None)
        if engine is None:
            return self._policy_not_evaluated_dto()
        administrative_status = None
        if dto.candidate_person_id is not None:
            resolver = getattr(self, "_administrative_status_resolver", None)
            if resolver is not None:
                try:
                    administrative_status = resolver(dto.candidate_person_id)
                except Exception:
                    LOGGER.warning(
                        "Administrative status resolution failed during policy evaluation; "
                        "person details omitted"
                    )
                    administrative_status = None
        result = engine.evaluate(IdentificationPolicyInput(
            dto.candidate_person_id, dto.recognition_state, dto.similarity,
            "NO_OBSERVATION" if stability_result is None else stability_result.state.value,
            0 if stability_result is None else stability_result.observations_count,
            0.0 if stability_result is None else stability_result.stable_duration_seconds,
            dto.quality_score, administrative_status, face_count, self._session_id,
            datetime.now(timezone.utc),
        ))
        return _identification_policy_dto(result, engine)

    def _policy_not_evaluated_dto(self) -> IdentificationPolicyDTO:
        engine = getattr(self, "_identification_policy", None)
        return IdentificationPolicyDTO(
            IdentificationPolicyState.POLICY_NOT_EVALUATED.value, False, False,
            None, ("policy_not_evaluated",), None, None, "NO_OBSERVATION", None,
            "N/D" if engine is None else engine.policy.policy_name,
            "N/D" if engine is None else engine.policy.policy_version,
            False if engine is None else engine.policy.automatic_actions_enabled,
        )

    def _evaluate_decision_orchestrator(
        self, dto: MonitoringDTO, stability_result,
        identification: IdentificationPolicyDTO, face_count: int,
    ) -> DecisionOrchestratorDTO:
        orchestrator = getattr(self, "_decision_orchestrator", None)
        if orchestrator is None:
            return self._orchestration_not_evaluated_dto()
        result = orchestrator.evaluate(DecisionOrchestratorInput(
            face_count, dto.candidate_person_id, dto.recognition_state, dto.similarity,
            "NO_OBSERVATION" if stability_result is None else stability_result.state.value,
            identification.state, identification.eligible,
            identification.administrative_status, dto.quality_score,
            self._session_id, self._session_id, datetime.now(timezone.utc),
        ))
        return _decision_orchestrator_dto(result)

    def _orchestration_not_evaluated_dto(self) -> DecisionOrchestratorDTO:
        orchestrator = getattr(self, "_decision_orchestrator", None)
        return DecisionOrchestratorDTO(
            DecisionState.NOT_EVALUATED.value, False, None,
            (ProposedAction.NONE.value,), (), ("orchestrator_not_evaluated",),
            False if orchestrator is None else
                orchestrator.policy.automatic_actions_enabled,
            "N/D" if orchestrator is None else orchestrator.policy.policy_name,
            "N/D" if orchestrator is None else orchestrator.policy.policy_version,
        )

    def _evaluate_action_executor(
        self, orchestration: DecisionOrchestratorDTO,
        monitoring: MonitoringDTO | None = None, face_count: int = 0,
    ) -> ActionExecutorDTO:
        executor = getattr(self, "_action_executor", None)
        suspension = getattr(self, "_event_history_suspended", None)
        if executor is None or (suspension is not None and suspension.is_set()):
            return self._action_not_evaluated_dto()
        administrative_status = None
        resolver = getattr(self, "_administrative_status_resolver", None)
        if monitoring is not None and monitoring.candidate_person_id and resolver is not None:
            try: administrative_status = resolver(monitoring.candidate_person_id)
            except Exception: administrative_status = None
        event_data = None if monitoring is None else DetectionEventActionData(
            monitoring.recognition_state, monitoring.candidate_display_name,
            monitoring.similarity, monitoring.quality_score,
            _safe_camera_reference(getattr(self, "_camera_display_name", None),
                                   self._camera_id), face_count, administrative_status,
        )
        popup_data = None if monitoring is None else PopupActionData(
            monitoring.recognition_state, monitoring.similarity, monitoring.message,
            monitoring.evaluated,
        )
        result = executor.execute(ActionExecutionInput(
            orchestration.proposed_actions, orchestration.blocked_actions,
            orchestration.state, orchestration.automatic_actions_enabled,
            orchestration.person_id, self._session_id, self._session_id,
            datetime.now(timezone.utc), event_data, popup_data,
        ))
        return _action_executor_dto(result)

    def _action_not_evaluated_dto(self) -> ActionExecutorDTO:
        executor = getattr(self, "_action_executor", None)
        return ActionExecutorDTO(
            ActionExecutionState.NOT_EVALUATED.value, False, (), (), (), (),
            ("executor_not_evaluated",),
            False if executor is None else executor.policy.automatic_execution_enabled,
            "N/D" if executor is None else executor.policy.policy_name,
            "N/D" if executor is None else executor.policy.policy_version,
        )

    def _enrollment_step(self, guided, aligned_face_bytes: bytes | None = None) -> None:
        plan = self._plan
        if plan is None:
            return
        score = guided.face_quality_score
        if guided.accepted and guided.embedding is not None and (
            score is None or score.total_score < self.enrollment_minimum_quality_score
        ):
            reject = getattr(self.adapter, "reject_enrollment_candidate", None)
            if reject is not None:
                reject(guided)
            self._enrollment_stability.reset()
            self._event(EnrollmentProgressDTO(
                UIState.ENROLLING,
                "Calidad insuficiente. No se mueva y mejore la iluminación.",
                plan.accepted_count, plan.target_samples,
                ("quality_below_enrollment_minimum",),
                None if score is None else score.total_score,
                None if score is None else score.quality_band.value, True,
            ))
            return
        if guided.accepted and guided.embedding is not None and score is not None \
                and self.enrollment_stability_frames > 1:
            reject = getattr(self.adapter, "reject_enrollment_candidate", None)
            if reject is not None and not reject(guided):
                self._enrollment_stability.reset()
                return
            stable = self._enrollment_stability
            stable.observations += 1
            if score.total_score > stable.best_score:
                stable.best_guided = guided
                stable.best_image = aligned_face_bytes
                stable.best_score = score.total_score
            if stable.observations < self.enrollment_stability_frames:
                self._event(EnrollmentProgressDTO(
                    UIState.ENROLLMENT_CAPTURE, "Mantenga la posición...",
                    plan.accepted_count, plan.target_samples, (), score.total_score,
                    score.quality_band.value, True,
                ))
                return
            guided = stable.best_guided
            aligned_face_bytes = stable.best_image
            restore = getattr(self.adapter, "restore_enrollment_candidate", None)
            if guided is None or restore is None or not restore(guided):
                stable.reset(); return
            score = guided.face_quality_score
            stable.reset()
        elif not guided.accepted:
            self._enrollment_stability.reset()
        if guided.accepted and guided.embedding is not None:
            sample_index = plan.accepted_count
            requested_pose = plan.current.requested_pose
            if (
                self._additional_person_id is None
                and self._thumbnails is not None and self._thumbnails.enabled
                and aligned_face_bytes is not None
            ):
                self._thumbnail_samples.append(ThumbnailSample(
                    sample_index, requested_pose.value,
                    0.0 if score is None else score.total_score,
                    bytes(aligned_face_bytes),
                ))
            plan.accept()
            if self._additional_person_id is not None:
                self._additional_samples.append((guided.embedding, score))
                progress = EnrollmentProgressDTO(
                    UIState.ENROLLING,
                    "Registro completo" if plan.completed else
                    operator_instruction(plan.current, self.mirrored_source),
                    plan.accepted_count, plan.target_samples, (),
                    None if score is None else score.total_score,
                    None if score is None else score.quality_band.value, True,
                )
            else:
                progress = self.controller.add_enrollment_sample(
                    guided.embedding, score,
                    "Registro completo" if plan.completed else
                    operator_instruction(plan.current, self.mirrored_source),
                )
            self._event(progress)
        else:
            self._event(EnrollmentProgressDTO(
                UIState.ENROLLING,
                operator_instruction(plan.current, self.mirrored_source),
                plan.accepted_count,
                plan.target_samples, tuple(reason.value for reason in guided.reasons),
                None if score is None else score.total_score,
                None if score is None else score.quality_band.value, True,
            ))
        if not plan.completed:
            return
        if self._additional_person_id is not None:
            person_id = self._additional_person_id
            try:
                assert self._people is not None
                result = self._people.complete_additional(
                    person_id, tuple(self._additional_samples)  # type: ignore[arg-type]
                )
                self._event(result)
                if result.success:
                    details = self._people.details(person_id).summary
                    biometric_manager = getattr(self._people, "biometrics", self._people)
                    template_count = len(biometric_manager.gallery.templates(person_id))
                    completed = EnrollmentResultDTO(
                        UIState.ENROLLMENT_COMPLETE, person_id,
                        details.first_name, details.last_name, details.display_name,
                        template_count, 0,
                        details.average_quality or 0.0,
                        details.minimum_quality or 0.0,
                        details.maximum_quality or 0.0,
                        "enrolled", True, True,
                        "Registro biométrico existente actualizado y verificado.",
                    )
                    self._event(completed)
                self._publish_application(EnrollmentFinishedEvent(
                    source="live_face_session", session_id=self._session_id,
                    run_id=self._session_id, person_id=person_id,
                    state="COMPLETED" if result.success else "REJECTED",
                    message=result.message,
                ))
                if not result.success:
                    self._error(UIErrorCode.ENROLLMENT_ERROR, result.message, True)
            finally:
                self._additional_person_id = None
                self._additional_samples.clear()
                self._plan = None
                self._event_history_suspended.clear()
                self.adapter.new_evaluator()
            return
        try:
            result = self.controller.finish_enrollment(
                persistence=self._persistence, manifest_path=self._manifest_path,
                archive_path=self._archive_path,
            )
            if (
                result.enrollment_status.casefold() == "enrolled"
                and not self.profile_photo_after_enrollment
                and self._thumbnail_consent
                and self._thumbnails is not None and self._thumbnails.enabled
            ):
                selected = select_thumbnail(self._thumbnail_samples)
                if selected is not None:
                    try:
                        self._thumbnails.save(result.person_id, selected.image_bytes)
                    except Exception as exc:
                        LOGGER.error(
                            "Thumbnail save failed after successful enrollment; "
                            "visual and biometric payloads omitted; exception_type=%s",type(exc).__name__
                        )
                        self._error(
                            UIErrorCode.THUMBNAIL_ERROR,
                            "Registro en memoria correcto; la miniatura visual no pudo guardarse.",
                            True,
                        )
            if result.persistence_requested and result.persistence_succeeded is None:
                succeeded = False
                try:
                    if (self._persistence is None or self._manifest_path is None
                            or self._archive_path is None):
                        raise RuntimeError("gallery persistence is not configured")
                    self._persistence(
                        self.controller.enrollment.gallery,
                        self._manifest_path, self._archive_path,
                    )
                    succeeded = True
                except Exception as exc:
                    LOGGER.error(
                        "Gallery persistence failed after ACTIVE; biometric payload omitted; exception_type=%s",type(exc).__name__
                    )
                result = replace(result, persistence_succeeded=succeeded)
            _verify_enrollment_commit(
                result, self.controller.enrollment.gallery,
                self._manifest_path, self._archive_path,
                self.controller.enrollment.target_samples,
            )
            self._event(result)
            gallery = self.controller.enrollment.gallery
            administrative_status = (
                None if self._administrative_status_resolver is None else
                self._administrative_status_resolver(result.person_id)
            )
            LOGGER.info(
                "Post-enrollment diagnostic person_present=%s template_count=%d "
                "gallery_identity_present=%s administrative_status=%s "
                "recognition_state=NOT_EVALUATED similarity=None shared_gallery=%s",
                administrative_status is not None,
                len(gallery.templates(result.person_id)),
                any(item.person_id == result.person_id for item in gallery.list_identities()),
                administrative_status,
                self.controller.monitoring.gallery is gallery,
            )
            self._publish_application(EnrollmentFinishedEvent(
                source="live_face_session", session_id=self._session_id,
                run_id=self._session_id, person_id=result.person_id,
                state=result.enrollment_status, message=result.message,
            ))
        except Exception as exc:
            LOGGER.error(
                "Enrollment finalization verification failed; stage=post_commit "
                "error_type=%s workflow_state=%s biometric_payload=omitted",
                type(exc).__name__, self.controller.state.value,
            )
            self._error(UIErrorCode.ENROLLMENT_ERROR,
                        "El registro biométrico no pudo verificarse ni persistirse. "
                        "No se marcó como completado.", False)
        finally:
            self._plan = None
            self._enrollment_stability.reset()
            self._capture_requested = False
            if not self.profile_photo_after_enrollment:
                self._event_history_suspended.clear()
            self._clear_thumbnail_samples()
            self.adapter.set_thumbnail_capture(False)
            self.adapter.new_evaluator()

    def _clear_thumbnail_samples(self) -> None:
        self._thumbnail_samples.clear()
        self._thumbnail_consent = False

    def _event(self, event: UIEvent) -> None:
        _put_recent(self.event_queue, event)
        self._publish_dto_event(event)

    def _publish_dto_event(self, value: UIEvent) -> None:
        if getattr(self, "_application_events", None) is None:
            return
        common = {
            "source": "live_face_session", "session_id": self._session_id,
            "run_id": self._session_id,
        }
        event = (
            MonitoringUpdatedEvent(monitoring=value, **common)
            if isinstance(value, MonitoringDTO) else
            StabilityUpdatedEvent(stability=value, **common)
            if isinstance(value, StabilityDTO) else
            IdentificationPolicyUpdatedEvent(policy=value, **common)
            if isinstance(value, IdentificationPolicyDTO) else
            DecisionUpdatedEvent(decision=value, **common)
            if isinstance(value, DecisionOrchestratorDTO) else
            ActionExecutionUpdatedEvent(execution=value, **common)
            if isinstance(value, ActionExecutorDTO) else None
        )
        if event is not None:
            self._publish_application(event)

    def _publish_application(self, event) -> None:
        bus = getattr(self, "_application_events", None)
        if bus is None:
            return
        try:
            bus.publish(event)
        except Exception as exc:
            LOGGER.error(
                "Application event publication failed safely; event_type=%s "
                "exception_type=%s", getattr(event, "event_type", "unknown"),
                type(exc).__name__,
            )

    def _error(self, code: UIErrorCode, message: str, recoverable: bool) -> None:
        LOGGER.warning("Safe UI error: %s", code.value)
        self._event(ErrorDTO(UIState.ERROR, code, message, recoverable))


def _put_recent(target: queue.Queue, item: object) -> bool:
    dropped = False
    try:
        target.put_nowait(item)
    except queue.Full:
        dropped = True
        try:
            target.get_nowait()
        except queue.Empty:
            pass
        try:
            target.put_nowait(item)
        except queue.Full:
            pass
    return dropped


def _drain(target: queue.Queue) -> tuple:
    items = []
    while True:
        try:
            items.append(target.get_nowait())
        except queue.Empty:
            return tuple(items)


def operator_instruction(step: CapturePlanStep, mirrored_source: bool) -> str:
    """Return stable operator-facing guidance; image mirroring is mapped separately."""
    return step.instruction


def requested_capture_pose(step: CapturePlanStep, mirrored_source: bool) -> CapturePose:
    """Map operator-facing left/right guidance to mirrored image coordinates."""
    if not mirrored_source:
        return step.requested_pose
    if step.requested_pose is CapturePose.SLIGHT_LEFT:
        return CapturePose.SLIGHT_RIGHT
    if step.requested_pose is CapturePose.SLIGHT_RIGHT:
        return CapturePose.SLIGHT_LEFT
    return step.requested_pose


def _dashboard_quality(guided: object) -> DashboardQualityDTO:
    metrics = getattr(guided, "quality_metrics", None)
    score = getattr(guided, "face_quality_score", None)
    if metrics is None:
        return DashboardQualityDTO()
    reasons = {getattr(item, "value", str(item)) for item in getattr(guided, "reasons", ())}
    values: tuple[tuple[str, float | str | None, set[str]], ...] = (
        ("detección", metrics.detection_confidence, {"low_detection_confidence"}),
        ("tamaño", metrics.relative_face_size, {"face_too_small"}),
        ("interocular", metrics.normalized_interocular_distance,
         {"low_interocular_distance"}),
        ("visibilidad", metrics.visible_box_ratio, {"partially_visible"}),
        ("centrado", _offset(metrics.center_offset_x, metrics.center_offset_y),
         {"face_off_center"}),
        ("iluminación", metrics.mean_illumination, {"too_dark", "too_bright"}),
        ("contraste", metrics.contrast, {"low_contrast"}),
        ("nitidez", metrics.blur_variance, {"blurry"}),
        ("pose", getattr(getattr(guided, "estimated_pose", None), "value", None),
         {"pose_not_requested"}),
    )
    projected = tuple(
        DashboardQualityMetricDTO(
            name, value,
            DashboardMetricState.NOT_AVAILABLE if value is None else
            DashboardMetricState.REJECTED if rejected & reasons else
            DashboardMetricState.OK,
        ) for name, value, rejected in values
    )
    return DashboardQualityDTO(
        None if score is None else score.total_score,
        None if score is None else score.quality_band.value,
        projected,
    )


def _offset(x: float | None, y: float | None) -> float | None:
    return None if x is None or y is None else math.hypot(x, y)


def _stability_dto(result, tracker: StabilityTracker) -> StabilityDTO:
    return StabilityDTO(
        result.state.value, result.person_id, result.observations_count,
        tracker.policy.minimum_observations, result.stable_duration_seconds,
        tracker.policy.minimum_duration_seconds, result.current_similarity,
        result.average_similarity, result.reason,
    )


def _identification_policy_dto(
    result: IdentificationPolicyResult, engine: IdentificationPolicyEngine,
) -> IdentificationPolicyDTO:
    return IdentificationPolicyDTO(
        result.state.value, result.evaluated, result.eligible, result.person_id,
        result.reasons, result.similarity, result.quality_score,
        result.stability_state, result.administrative_status, result.policy_name,
        result.policy_version, engine.policy.automatic_actions_enabled,
    )


def _decision_orchestrator_dto(
    result: DecisionOrchestratorResult,
) -> DecisionOrchestratorDTO:
    return DecisionOrchestratorDTO(
        result.state.value, result.evaluated, result.person_id,
        tuple(item.value for item in result.proposed_actions),
        tuple(item.value for item in result.blocked_actions), result.reasons,
        result.automatic_actions_enabled, result.policy_name, result.policy_version,
    )


def _action_executor_dto(result: ActionExecutionResult) -> ActionExecutorDTO:
    return ActionExecutorDTO(
        result.state.value, result.evaluated, result.requested_actions,
        result.executed_actions, result.skipped_actions, result.failed_actions,
        result.reasons, result.automatic_execution_enabled, result.policy_name,
        result.policy_version,
    )
