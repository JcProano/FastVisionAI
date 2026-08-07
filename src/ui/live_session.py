"""Bounded worker coordinating the runtime adapter and safe UI controller."""

from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from src.engine.capture_quality import CapturePlanStep, CapturePose, GuidedCapturePlan
from src.ui.contracts import (
    EnrollmentProgressDTO, EnrollmentResultDTO, ErrorDTO, MonitoringDTO,
    RegistrationFormData, RuntimeStatusDTO, UIErrorCode, UIState, VisualFrameDTO,
)
from src.ui.controller import LocalFaceUIController
from src.ui.enrollment_workflow import PersistenceCallback
from src.ui.runtime_adapter import (
    CameraAdapterError, InferenceAdapterError, UIRuntimeAdapter,
)

LOGGER = logging.getLogger(__name__)
UIEvent = MonitoringDTO | EnrollmentProgressDTO | EnrollmentResultDTO | ErrorDTO | RuntimeStatusDTO


class SessionCommandType(str, Enum):
    START_ENROLLMENT = "start_enrollment"
    CANCEL_ENROLLMENT = "cancel_enrollment"
    STOP = "stop"


@dataclass(frozen=True, slots=True)
class SessionCommand:
    kind: SessionCommandType
    form: RegistrationFormData | None = None


class LiveFaceSession:
    def __init__(
        self, adapter: UIRuntimeAdapter, controller: LocalFaceUIController, *,
        event_queue_size: int = 16, command_queue_size: int = 8,
        close_timeout_seconds: float = 5.0,
        mirrored_source: bool = False,
        persistence: PersistenceCallback | None = None,
        manifest_path: Path | None = None, archive_path: Path | None = None,
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
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._plan: GuidedCapturePlan | None = None
        self._last_single_valid = False

    @property
    def alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.alive:
            raise RuntimeError("live session is already running")
        self._thread = threading.Thread(target=self._run, name="face-ui-worker", daemon=True)
        self._thread.start()

    def start_enrollment(self, form: RegistrationFormData) -> bool:
        return self._command(SessionCommand(SessionCommandType.START_ENROLLMENT, form))

    def cancel_enrollment(self) -> bool:
        return self._command(SessionCommand(SessionCommandType.CANCEL_ENROLLMENT))

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
        return not self.alive

    def drain_events(self) -> tuple[UIEvent, ...]:
        return _drain(self.event_queue)

    def take_latest_visual(self) -> VisualFrameDTO | None:
        items = _drain(self.visual_queue)
        return items[-1] if items else None

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
                _put_recent(self.visual_queue, step.visual)
                self._last_single_valid = (
                    step.face_count == 1 and step.guided.visual_quality_passed
                )
                if self._plan is not None:
                    self._enrollment_step(step.guided)
                else:
                    self._monitoring_step(step.face_count, step.guided)
        finally:
            self.adapter.close()
            if self.controller.enrollment.active:
                self.controller.cancel_enrollment()
            self._event(self.adapter.status())

    def _commands(self) -> None:
        for command in _drain(self.command_queue):
            if command.kind is SessionCommandType.STOP:
                self._stop.set()
            elif command.kind is SessionCommandType.CANCEL_ENROLLMENT:
                if self.controller.enrollment.active:
                    self.controller.cancel_enrollment()
                self._plan = None
                self.adapter.new_evaluator()
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
                    plan = GuidedCapturePlan(self.controller.enrollment.target_samples)
                    progress = self.controller.begin_enrollment(command.form)
                    self.adapter.new_evaluator()
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
                    self._error(UIErrorCode.ENROLLMENT_ERROR,
                                "No se pudo iniciar el registro guiado.", False)

    def _monitoring_step(self, face_count: int, guided) -> None:
        if face_count == 0:
            self._event(MonitoringDTO(
                UIState.NO_FACE, "No se detectó un rostro", None, None,
                "deshabilitada / NOT_EVALUATED", True,
            ))
            return
        if face_count > 1:
            self._event(MonitoringDTO(
                UIState.MULTIPLE_FACES, "MULTIPLE_FACES", None, None,
                "deshabilitada / NOT_EVALUATED", True,
            ))
            return
        score = guided.face_quality_score
        if guided.embedding is None:
            self._event(MonitoringDTO(
                UIState.MONITORING, guided.primary_state.value, None, None,
                "deshabilitada / NOT_EVALUATED", True,
                None if score is None else score.total_score,
                None if score is None else score.quality_band.value,
            ))
            return
        dto, error = self.controller.monitor(guided.embedding, score)
        self._event(dto)
        if error is not None:
            self._event(error)

    def _enrollment_step(self, guided) -> None:
        plan = self._plan
        if plan is None:
            return
        score = guided.face_quality_score
        if guided.accepted and guided.embedding is not None:
            plan.accept()
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
        try:
            result = self.controller.finish_enrollment(
                persistence=self._persistence, manifest_path=self._manifest_path,
                archive_path=self._archive_path,
            )
            self._event(result)
            if result.persistence_requested and result.persistence_succeeded is False:
                self._error(UIErrorCode.PERSISTENCE_ERROR,
                            "Registro en memoria correcto; la persistencia local falló.", True)
        except Exception:
            LOGGER.exception(
                "Enrollment finalization failed; temporary biometric payload omitted from log"
            )
            self._error(UIErrorCode.ENROLLMENT_ERROR,
                        "El registro no pudo completarse.", False)
        finally:
            self._plan = None
            self.adapter.new_evaluator()

    def _event(self, event: UIEvent) -> None:
        _put_recent(self.event_queue, event)

    def _error(self, code: UIErrorCode, message: str, recoverable: bool) -> None:
        LOGGER.warning("Safe UI error: %s", code.value)
        self._event(ErrorDTO(UIState.ERROR, code, message, recoverable))


def _put_recent(target: queue.Queue, item: object) -> None:
    try:
        target.put_nowait(item)
    except queue.Full:
        try:
            target.get_nowait()
        except queue.Empty:
            pass
        try:
            target.put_nowait(item)
        except queue.Full:
            pass


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
