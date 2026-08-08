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

from src.engine.capture_quality import CapturePlanStep, CapturePose, GuidedCapturePlan
from src.engine.stability import StabilityObservation, StabilityTracker
from src.ui.contracts import (
    EnrollmentProgressDTO, EnrollmentResultDTO, ErrorDTO, MonitoringDTO,
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
from src.ui.thumbnails import ThumbnailManager, select_thumbnail
from src.ui.thumbnails.contracts import ThumbnailSample
from src.ui.dashboard.contracts import (
    DashboardMetricState, DashboardMetricsDTO, DashboardQualityDTO,
    DashboardQualityMetricDTO,
)
from src.core.detection_events import (
    DetectionEventInput, DetectionEventService, DetectionEventType,
)
from datetime import datetime, timezone
from collections.abc import Callable

LOGGER = logging.getLogger(__name__)
UIEvent = (MonitoringDTO | EnrollmentProgressDTO | EnrollmentResultDTO | ErrorDTO |
           RuntimeStatusDTO | PeopleOperationResultDTO | StabilityDTO)


class SessionCommandType(str, Enum):
    START_ENROLLMENT = "start_enrollment"
    CANCEL_ENROLLMENT = "cancel_enrollment"
    STOP = "stop"
    START_ADDITIONAL_ENROLLMENT = "start_additional_enrollment"


@dataclass(frozen=True, slots=True)
class SessionCommand:
    kind: SessionCommandType
    form: RegistrationFormData | None = None
    person_id: str | None = None


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

    def start_additional_enrollment(self, person_id: str) -> bool:
        accepted = self._command(SessionCommand(
            SessionCommandType.START_ADDITIONAL_ENROLLMENT, person_id=person_id
        ))
        if accepted: self.set_event_history_suspended(True)
        return accepted

    def set_event_history_suspended(self, suspended: bool) -> None:
        if suspended:
            self._event_history_suspended.set()
            self._reset_stability(emit=True)
        else:
            self._event_history_suspended.clear()

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
                self._error(UIErrorCode.CAMERA_ERROR, "No se pudo abrir la cámara", False)
                return
            self._event(self.adapter.status())
            while not self._stop.is_set():
                self._commands()
                if self._stop.is_set():
                    break
                requested = self._plan.current.requested_pose if self._plan else CapturePose.FRONTAL
                try:
                    step = self.adapter.process(requested)
                except CameraAdapterError:
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
                with self._metrics_lock:
                    self._frames_received += 1
                    self._frames_processed += 1
                    self._visual_frames_dropped += int(dropped)
                    self._faces_detected_total += step.face_count
                    self._faces_detected_current = step.face_count
                    self._embeddings_generated += int(step.guided.embedding is not None)
                    self._dashboard_quality = _dashboard_quality(step.guided)
                self._last_single_valid = (
                    step.face_count == 1 and step.guided.visual_quality_passed
                )
                if self._plan is not None:
                    self._enrollment_step(step.guided, step.aligned_face_bytes)
                else:
                    self._monitoring_step(step.face_count, step.guided)
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
            self._event(self.adapter.status())

    def _commands(self) -> None:
        for command in _drain(self.command_queue):
            if command.kind is SessionCommandType.STOP:
                self._stop.set()
            elif command.kind is SessionCommandType.CANCEL_ENROLLMENT:
                if self.controller.enrollment.active:
                    self.controller.cancel_enrollment()
                self._plan = None
                if self._people is not None and self._additional_person_id is not None:
                    self._event(self._people.cancel_additional())
                self._additional_person_id = None
                self._additional_samples.clear()
                self._clear_thumbnail_samples()
                self.adapter.set_thumbnail_capture(False)
                self.adapter.new_evaluator()
                self._reset_stability(emit=True)
                self._event(MonitoringDTO(
                    UIState.MONITORING, "Registro cancelado", None, None,
                    "deshabilitada / NOT_EVALUATED", True,
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
                    self.adapter.set_thumbnail_capture(True)
                    self._plan = plan
                    self._event(progress)
                except Exception:
                    LOGGER.exception(
                        "Enrollment start failed before biometric sample collection; "
                        "target_samples=%d consent_confirmed=%s",
                        self.controller.enrollment.target_samples,
                        command.form.consent_confirmed,
                    )
                    if self.controller.enrollment.active:
                        self.controller.cancel_enrollment()
                    self._plan = None
                    self._clear_thumbnail_samples()
                    self.adapter.set_thumbnail_capture(False)
                    self._error(UIErrorCode.ENROLLMENT_ERROR,
                                "No se pudo iniciar el registro guiado.", False)
            elif (command.kind is SessionCommandType.START_ADDITIONAL_ENROLLMENT and
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
                try:
                    self._reset_stability(emit=True)
                    started = self._people.begin_additional(command.person_id)
                    if not started.success:
                        self._event(started)
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
                except Exception:
                    LOGGER.exception("Additional enrollment start failed; biometric data omitted")
                    self._plan = None
                    self._additional_person_id = None
                    self._additional_samples.clear()
                    self._error(UIErrorCode.ENROLLMENT_ERROR,
                                "No se pudo iniciar la captura adicional.", False)

    def _monitoring_step(self, face_count: int, guided) -> None:
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
        if guided.embedding is None:
            self._emit_monitoring(MonitoringDTO(
                UIState.MONITORING, guided.primary_state.value, None, None,
                "deshabilitada / NOT_EVALUATED", True,
                None if score is None else score.total_score,
                None if score is None else score.quality_band.value,
            ))
            return
        dto, error = self.controller.monitor(guided.embedding, score)
        self._emit_monitoring(dto)
        if error is not None:
            self._event(error)

    def _emit_monitoring(self, dto: MonitoringDTO) -> None:
        stability = getattr(self, "_stability", None)
        if stability is not None:
            face_count = (0 if dto.state is UIState.NO_FACE else
                          2 if dto.state is UIState.MULTIPLE_FACES else 1)
            result = stability.observe(StabilityObservation(
                None, dto.candidate_person_id, dto.recognition_state, dto.similarity,
                face_count, dto.quality_score, self._session_id,
            ))
            self._event(_stability_dto(result, stability))
        if self._detection_events is not None and not self._event_history_suspended.is_set():
            event_type = None
            if dto.state is UIState.MULTIPLE_FACES:
                event_type = DetectionEventType.MULTIPLE_FACES
            elif dto.recognition_state == "INCOMPATIBLE":
                event_type = DetectionEventType.INCOMPATIBLE
            elif dto.candidate_person_id is not None:
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
                    event_type, dto.candidate_person_id, datetime.now(timezone.utc),
                    self._camera_id, dto.candidate_display_name, dto.similarity,
                    dto.quality_score, "NOT_EVALUATED" if event_type is
                    DetectionEventType.REGISTERED_CANDIDATE else dto.recognition_state,
                    status, self._session_id,
                ))
        self._event(dto)

    def _reset_stability(self, *, emit: bool) -> None:
        stability = getattr(self, "_stability", None)
        if stability is None:
            return
        result = stability.reset()
        if emit:
            self._event(_stability_dto(result, stability))

    def _enrollment_step(self, guided, aligned_face_bytes: bytes | None = None) -> None:
        plan = self._plan
        if plan is None:
            return
        score = guided.face_quality_score
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
                if not result.success:
                    self._error(UIErrorCode.ENROLLMENT_ERROR, result.message, True)
            finally:
                self._additional_person_id = None
                self._additional_samples.clear()
                self._plan = None
                self.adapter.new_evaluator()
            return
        try:
            result = self.controller.finish_enrollment(
                persistence=self._persistence, manifest_path=self._manifest_path,
                archive_path=self._archive_path,
            )
            if (
                result.enrollment_status.casefold() == "enrolled"
                and self._thumbnail_consent
                and self._thumbnails is not None and self._thumbnails.enabled
            ):
                selected = select_thumbnail(self._thumbnail_samples)
                if selected is not None:
                    try:
                        self._thumbnails.save(result.person_id, selected.image_bytes)
                    except Exception:
                        LOGGER.exception(
                            "Thumbnail save failed after successful enrollment; "
                            "visual and biometric payloads omitted"
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
                except Exception:
                    LOGGER.exception(
                        "Gallery persistence failed after ACTIVE; biometric payload omitted"
                    )
                result = replace(result, persistence_succeeded=succeeded)
            if result.persistence_requested and result.persistence_succeeded is False:
                self._error(UIErrorCode.PERSISTENCE_ERROR,
                            "Registro en memoria correcto; la persistencia local falló.", True)
            self._event(result)
        except Exception:
            LOGGER.exception(
                "Enrollment finalization failed; temporary biometric payload omitted from log"
            )
            self._error(UIErrorCode.ENROLLMENT_ERROR,
                        "El registro no pudo completarse.", False)
        finally:
            self._plan = None
            self._clear_thumbnail_samples()
            self.adapter.set_thumbnail_capture(False)
            self.adapter.new_evaluator()

    def _clear_thumbnail_samples(self) -> None:
        self._thumbnail_samples.clear()
        self._thumbnail_consent = False

    def _event(self, event: UIEvent) -> None:
        _put_recent(self.event_queue, event)

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
    """Translate an image-coordinate pose into the operator's mirrored perspective.

    CapturePose remains expressed in image coordinates. Only the human-facing
    instruction is exchanged for LEFT/RIGHT when the preview source is mirrored.
    FRONTAL, UNKNOWN and the logical order of GuidedCapturePlan are unchanged.
    """
    if not mirrored_source:
        return step.instruction
    if step.requested_pose is CapturePose.SLIGHT_LEFT:
        return "Gire ligeramente a la derecha"
    if step.requested_pose is CapturePose.SLIGHT_RIGHT:
        return "Gire ligeramente a la izquierda"
    return step.instruction


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
