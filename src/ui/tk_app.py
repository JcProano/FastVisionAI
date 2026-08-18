"""Tkinter presentation layer; it never owns biometric arrays or model objects."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import math
import time
from typing import Any
from zoneinfo import ZoneInfo

try:  # Tk is an optional OS component and is not required by headless tests.
    import tkinter as tk
    from tkinter import messagebox, ttk
except ModuleNotFoundError:  # pragma: no cover - branch depends on Python build
    tk = None  # type: ignore[assignment]
    messagebox = None  # type: ignore[assignment]
    ttk = None  # type: ignore[assignment]

from src.ui.contracts import (
    ActionExecutorDTO,
    EnrollmentProgressDTO,
    EnrollmentResultDTO,
    EnrollmentConflictDTO,
    PersonPhotoCaptureDTO,
    ErrorDTO,
    MonitoringDTO,
    RegistrationFormData,
    DecisionOrchestratorDTO, IdentificationPolicyDTO, RuntimeStatusDTO, StabilityDTO,
    UIErrorCode,
    UIState,
)
from src.ui.form_validation import (
    RegistrationFormError,
    validate_registration_form,
)
from src.ui.people.contracts import PeopleOperationResultDTO
from src.ui.dashboard.contracts import DashboardGalleryDTO
from src.ui.dashboard.state import DashboardStateStore
from src.ui.dashboard.professional_contracts import (
    DashboardLiveStateDTO, DashboardSnapshotDTO,
)
from src.ui.thumbnails import ThumbnailDTO
from src.ui.thumbnails.presentation import thumbnail_to_ppm
from src.ui.video_presentation import VideoPresentation, render_rgb
from src.ui.identification import (
    IdentificationPopupDTO, IdentificationPopupType,
    IdentificationPresentationController,
)
from src.ui.identification.tk_popup import IdentificationPopupWindow
from src.core.detection_events import DetectionEventDTO


def local_validation_banner(enabled: bool) -> str:
    return "MODO VALIDACIÓN LOCAL — LOGIN OMITIDO" if enabled else ""


@dataclass(frozen=True, slots=True)
class MonitoringText:
    headline: str
    candidate: str
    similarity: str
    decision: str
    quality: str


@dataclass(frozen=True, slots=True)
class StabilityText:
    state: str
    observations: str
    duration: str
    average_similarity: str


@dataclass(frozen=True, slots=True)
class IdentificationPolicyText:
    state: str
    evaluated: str
    automatic_actions: str
    primary_reason: str


@dataclass(frozen=True, slots=True)
class DecisionOrchestratorText:
    state: str
    proposals: str
    automatic_actions: str
    primary_reason: str


@dataclass(frozen=True, slots=True)
class ActionExecutorText:
    state: str
    requested: str
    executed: str
    automation: str
    primary_reason: str


def action_executor_text(dto: ActionExecutorDTO | None) -> ActionExecutorText:
    if dto is None:
        return ActionExecutorText(
            "NOT_EVALUATED", "N/D", "—", "Deshabilitada", "N/D",
        )
    return ActionExecutorText(
        dto.state,
        ", ".join(dto.requested_actions) if dto.requested_actions else "—",
        ", ".join(dto.executed_actions) if dto.executed_actions else "—",
        "Habilitada" if dto.automatic_execution_enabled else "Deshabilitada",
        dto.reasons[0] if dto.reasons else "N/D",
    )


def decision_orchestrator_text(
    dto: DecisionOrchestratorDTO | None,
) -> DecisionOrchestratorText:
    if dto is None:
        return DecisionOrchestratorText(
            "NOT_EVALUATED", "N/D", "Deshabilitadas", "N/D",
        )
    proposals = ", ".join(dto.proposed_actions) if dto.proposed_actions else "NONE"
    return DecisionOrchestratorText(
        dto.state, proposals,
        "Habilitadas" if dto.automatic_actions_enabled else "Deshabilitadas",
        dto.reasons[0] if dto.reasons else "N/D",
    )


def identification_policy_text(
    dto: IdentificationPolicyDTO | None,
) -> IdentificationPolicyText:
    if dto is None:
        return IdentificationPolicyText(
            "POLICY_NOT_EVALUATED", "No", "Deshabilitadas", "N/D",
        )
    return IdentificationPolicyText(
        dto.state, "Sí" if dto.evaluated else "No",
        "Habilitadas" if dto.automatic_actions_enabled else "Deshabilitadas",
        dto.reasons[0] if dto.reasons else "N/D",
    )


def stability_text(dto: StabilityDTO | None) -> StabilityText:
    if dto is None:
        return StabilityText("N/D", "N/D", "N/D", "N/D")
    average = "N/D" if dto.average_similarity is None else f"{dto.average_similarity:.4f}"
    return StabilityText(
        dto.state,
        f"{dto.observations_count}/{dto.required_observations}",
        f"{dto.stable_duration_seconds:.1f} / {dto.required_duration_seconds:.1f} s",
        average,
    )


def monitoring_text(dto: MonitoringDTO) -> MonitoringText:
    candidate = dto.candidate_display_name or (
        dto.message if dto.candidate_display_name is None else dto.candidate_display_name
    )
    similarity = "—" if dto.similarity is None else f"{dto.similarity:.4f}"
    quality = "—" if dto.quality_score is None else f"{dto.quality_score:.1f}/100"

    return MonitoringText(
        dto.message,
        candidate,
        similarity,
        (f"Threshold: {'N/D' if dto.match_threshold is None else format(dto.match_threshold, '.4f')}"
         f" | Estado: {dto.recognition_state}"),
        quality,
    )


class LocalFaceTkApp:
    """Small local view driven only by safe DTOs and short-lived RGB frames."""

    def __init__(
        self,
        root: Any,
        *,
        on_register: Callable[[RegistrationFormData], None],
        on_cancel: Callable[[], None],
        on_capture_enrollment: Callable[[], bool] | None = None,
        on_view_person: Callable[[str], None] | None = None,
        on_additional_enrollment: Callable[[str], bool] | None = None,
        on_start_photo: Callable[[str], bool] | None = None,
        on_capture_photo: Callable[[], bool] | None = None,
        on_confirm_photo: Callable[[], bool] | None = None,
        on_retake_photo: Callable[[], bool] | None = None,
        on_cancel_photo: Callable[[], bool] | None = None,
        enrollment_target_samples: int = 5,
        manual_enrollment_capture: bool = True,
        profile_photo_after_enrollment: bool = False,
        on_close: Callable[[], None],
        on_people: Callable[[], None] | None = None,
        on_configuration: Callable[[], None] | None = None,
        on_camera: Callable[[], None] | None = None,
        on_retry_camera: Callable[[], bool] | None = None,
        on_save_gallery: Callable[[], object] | None = None,
        get_gallery: Callable[[], DashboardGalleryDTO] | None = None,
        dashboard_settings: dict[str, object] | None = None,
        video_presentation: VideoPresentation | None = None,
        photo_capture_mode: str = "automatic",
        get_thumbnail: Callable[[str], ThumbnailDTO] | None = None,
        identification_controller: IdentificationPresentationController | None = None,
        identification_popup: IdentificationPopupWindow | None = None,
        popup_mode: str = "legacy",
        get_popup_requests: Callable[[], tuple[IdentificationPopupDTO, ...]] | None = None,
        clear_popup_requests: Callable[[], None] | None = None,
        on_registration_form_state: Callable[[bool], None] | None = None,
        get_detection_events: Callable[[], tuple[DetectionEventDTO, ...]] | None = None,
        on_detection_history: Callable[[], None] | None = None,
        get_attendance_summary: Callable[[], object] | None = None,
        on_attendance_history: Callable[[], None] | None = None,
        on_reports: Callable[[], None] | None = None,
        get_daily_report: Callable[[], object] | None = None,
        report_refresh_seconds: float = 30.0,
        can: Callable[[str], bool] | None = None,
        on_backup: Callable[[], None] | None = None,
        system_health_controller: object | None = None,
        system_health_service: object | None = None,
        on_system_health: Callable[[], None] | None = None,
        system_health_refresh_seconds: float = 10.0,
        on_audit: Callable[[], None] | None = None,
        audit_controller: object | None = None,
        audit_refresh_seconds: float = 30.0,
        local_validation_login_bypass: bool = False,
        appliance_mode: bool = False,
    ) -> None:
        if tk is None or ttk is None:
            raise RuntimeError(
                "Tkinter no está disponible en este Python; use mocks/headless o "
                "un intérprete del sistema con soporte Tk"
            )
        if popup_mode not in {"legacy", "action_executor"}:
            raise ValueError("popup_mode must be legacy or action_executor")

        self.root = root
        self._on_register = on_register
        self._on_cancel = on_cancel
        self._on_capture_enrollment = on_capture_enrollment
        self._on_view_person = on_view_person
        self._on_additional_enrollment = on_additional_enrollment
        self._on_start_photo = on_start_photo
        self._on_capture_photo = on_capture_photo
        self._on_confirm_photo = on_confirm_photo
        self._on_retake_photo = on_retake_photo
        self._on_cancel_photo = on_cancel_photo
        self._enrollment_target_samples = enrollment_target_samples
        self._manual_enrollment_capture = manual_enrollment_capture
        self._profile_photo_after_enrollment = profile_photo_after_enrollment
        self._on_close = on_close
        self._on_people = on_people
        self._on_configuration = on_configuration
        self._on_camera = on_camera
        self._on_retry_camera = on_retry_camera
        self._on_save_gallery = on_save_gallery
        self._get_gallery = get_gallery
        self._get_thumbnail = get_thumbnail
        self._thumbnail_person_id: str | None = None
        self._thumbnail_photo: tk.PhotoImage | None = None
        self._identification = identification_controller
        self._identification_popup = identification_popup
        self._popup_mode = popup_mode
        self._get_popup_requests = get_popup_requests
        self._clear_popup_requests = clear_popup_requests or (lambda: None)
        self._on_registration_form_state = on_registration_form_state or (lambda _value: None)
        self._get_detection_events = get_detection_events
        self._on_detection_history = on_detection_history
        self._get_attendance_summary=get_attendance_summary
        self._get_daily_report = get_daily_report
        self._report_refresh_seconds = report_refresh_seconds
        self._report_after_id = None
        self._detection_events_rendered: tuple[DetectionEventDTO, ...] = ()
        self._enrollment_active = False
        self._registration_form_open = False
        self._closing = False
        self._stability: StabilityDTO | None = None
        self._identification_policy: IdentificationPolicyDTO | None = None
        self._decision_orchestrator: DecisionOrchestratorDTO | None = None
        self._action_executor: ActionExecutorDTO | None = None
        self._can = can or (lambda _permission: True)
        self._system_health_controller = system_health_controller
        self._system_health_service = system_health_service
        self._system_health_refresh_seconds = system_health_refresh_seconds
        self._system_health_after_id = None
        self._audit_controller = audit_controller
        self._audit_refresh_seconds = audit_refresh_seconds
        self._local_validation_login_bypass = local_validation_login_bypass
        self._appliance_mode = appliance_mode
        self._web_shutdown = None
        self._presentation_frame_close = None
        self._audit_after_id = None
        self._dashboard_refresh_coordinator = None
        self._fullscreen = False
        self._professional_photos: list[Any] = []
        self._camera_source_name = "N/D"
        self._camera_source_type = "N/D"

        self._form: tk.Toplevel | None = None
        self._enrollment_video: Any | None = None
        self._enrollment_video_item: Any | None = None
        self._enrollment_guide_text: Any | None = None
        self._enrollment_progress: Any | None = None
        self._enrollment_quality: Any | None = None
        self._enrollment_reasons: Any | None = None
        self._capture_button: Any | None = None
        self._photo_capture_window: Any | None = None
        self._photo_capture_preview: Any | None = None
        self._photo_capture_status: Any | None = None
        self._photo_capture_quality: Any | None = None
        self._photo_capture_image: Any | None = None
        self._enrollment_resume_after_id: Any | None = None
        self._photo: tk.PhotoImage | None = None
        self._video_presentation = video_presentation or VideoPresentation()
        self._photo_capture_mode = photo_capture_mode
        settings = dashboard_settings or {}
        self._dashboard = DashboardStateStore(
            int(settings.get("history_limit", 100)),
            float(settings.get("event_debounce_seconds", 2.0)),
        )
        self._history_rendered: tuple[object, ...] = ()
        self._diagnostic_visible = False
        self._metrics_refresh_seconds = float(settings.get("metrics_refresh_ms", 250)) / 1000.0
        self._last_dashboard_refresh = float("-inf")

        root.title("FastVisionAI — Dashboard profesional")
        root.configure(background="#111827")
        style=ttk.Style(root)
        style.configure("TFrame",background="#111827")
        style.configure("TLabel",background="#111827",foreground="#e5e7eb")
        style.configure("TLabelframe",background="#111827",foreground="#e5e7eb")
        style.configure("TLabelframe.Label",background="#111827",foreground="#93c5fd")
        style.configure("Title.TLabel",font=("TkDefaultFont",16,"bold"),foreground="#f9fafb")
        style.configure("Treeview",background="#1f2937",fieldbackground="#1f2937",foreground="#f3f4f6",rowheight=52)
        style.configure("Treeview.Heading",background="#374151",foreground="#f9fafb")
        root.geometry(
            f"{int(settings.get('initial_width', 1100))}x"
            f"{int(settings.get('initial_height', 720))}"
        )
        root.minsize(
            int(settings.get("minimum_width", 820)),
            int(settings.get("minimum_height", 600)),
        )
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)
        header = ttk.Frame(root, padding=(12, 8)); header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="FASTVISION AI", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.header_state = ttk.Label(header, text="Cámara ●  Runtime ●")
        self.header_state.grid(row=0, column=1, sticky="e")
        self.validation_mode_banner = ttk.Label(
            header,
            text=("MODO APPLIANCE — RED LOCAL" if appliance_mode else
                  local_validation_banner(local_validation_login_bypass)),
        )
        self.validation_mode_banner.grid(row=1, column=0, columnspan=2, sticky="w")

        navigation = ttk.Frame(header); navigation.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6,0))
        for column in range(6):navigation.columnconfigure(column,weight=1)
        nav_items = (
            ("Cámara", on_camera, True),
            ("Personas", on_people, self._can("VIEW_PEOPLE")),
            ("Asistencia", on_attendance_history, self._can("VIEW_ATTENDANCE")),
            ("Historial", on_detection_history, self._can("VIEW_DETECTION_HISTORY")),
            ("Reportes", on_reports, self._can("VIEW_REPORTS")),
            ("Configuración", on_configuration, self._can("VIEW_SETTINGS")),
        )
        self.navigation_buttons = {}
        for column,(label,command,allowed) in enumerate(nav_items):
            button=ttk.Button(navigation,text=label,command=command or (lambda:None),
                              state="normal" if command is not None and allowed else "disabled")
            button.grid(row=0,column=column,sticky="ew",padx=2);self.navigation_buttons[label]=button

        statistics = ttk.Frame(root,padding=(10,4));statistics.grid(row=1,column=0,sticky="ew")
        for column in range(4):statistics.columnconfigure(column,weight=1,uniform="stats")
        self.stat_values={}
        for column,(key,label) in enumerate((("present","PERSONAS PRESENTES"),("recognitions","RECONOCIMIENTOS"),("entries","ENTRADAS HOY"),("late","RETRASOS"))):
            card=ttk.LabelFrame(statistics,text=label,padding=8);card.grid(row=0,column=column,sticky="nsew",padx=3)
            value=ttk.Label(card,text="N/D",style="Title.TLabel",anchor="center");value.pack(fill="x")
            self.stat_values[key]=value

        body = ttk.Frame(root, padding=(10, 4)); body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(0, weight=3); body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        # Keep the existing live-video Canvas (formerly captioned "VIDEO EN VIVO").
        video_card = ttk.LabelFrame(body, text="VIDEO EN TIEMPO REAL", padding=6)
        video_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        video_card.columnconfigure(0, weight=1); video_card.rowconfigure(0, weight=1)
        self.video = tk.Canvas(video_card, background="#202124", highlightthickness=0)
        self.video.grid(row=0, column=0, sticky="nsew")
        self._video_item = self.video.create_image(0, 0, anchor="center")

        side = ttk.Frame(body); side.grid(row=0, column=1, sticky="nsew")
        technical = ttk.Frame(root); self.technical_panel=technical
        system_card = ttk.LabelFrame(technical, text="Estado del sistema técnico", padding=8)
        system_card.pack(fill="x", pady=(0, 6))
        self.runtime_status = ttk.Label(system_card, text="Cámara: N/D\nRuntime: N/D\nYuNet: N/D\nArcFace: N/D")
        self.runtime_status.pack(anchor="w")
        self.gallery_status = ttk.Label(system_card, text="Personas: 0\nTemplates: 0")
        self.gallery_status.pack(anchor="w", pady=(6, 0))

        camera_card = ttk.LabelFrame(technical, text="CÁMARA", padding=8)
        camera_card.pack(fill="x", pady=6)
        self.camera_status = ttk.Label(
            camera_card, text="Estado: Desconectada\nFuente: N/D\nTipo: N/D", justify="left",
        )
        self.camera_status.pack(anchor="w")
        camera_actions = ttk.Frame(camera_card); camera_actions.pack(fill="x", pady=(6, 0))
        self.camera_search_button = ttk.Button(
            camera_actions, text="Buscar cámaras", command=on_camera or (lambda: None),
            state="normal" if on_camera is not None else "disabled",
        )
        self.camera_search_button.pack(side="left", padx=2)
        self.camera_change_button = ttk.Button(
            camera_actions, text="Cambiar cámara", command=on_camera or (lambda: None),
            state="normal" if on_camera is not None else "disabled",
        )
        self.camera_change_button.pack(side="left", padx=2)
        self.camera_retry_button = ttk.Button(
            camera_actions, text="Reintentar", command=on_retry_camera or (lambda: None),
            state="disabled",
        )
        self.camera_retry_button.pack(side="left", padx=2)

        candidate_card = ttk.LabelFrame(technical, text="Candidato experimental", padding=8)
        candidate_card.pack(fill="x", pady=6)
        self.candidate_thumbnail = ttk.Label(
            candidate_card, text="Sin foto registrada", anchor="center",
        )
        self.candidate_thumbnail.pack(anchor="center", pady=(0, 5))
        self.status = ttk.Label(candidate_card, text="Iniciando…"); self.status.pack(anchor="w")
        self.candidate = ttk.Label(candidate_card, text="Sin candidatos registrados"); self.candidate.pack(anchor="w")
        self.similarity = ttk.Label(candidate_card, text="Similitud: —"); self.similarity.pack(anchor="w")
        self.decision = ttk.Label(candidate_card, text="Decisión automática: deshabilitada / NOT_EVALUATED")
        self.decision.pack(anchor="w")
        self.quality = ttk.Label(candidate_card, text="Score: —"); self.quality.pack(anchor="w")
        self.recognition_pause = ttk.Label(candidate_card, text="")
        self.recognition_pause.pack(anchor="w")

        stability_card = ttk.LabelFrame(technical, text="Estabilidad", padding=6)
        stability_card.pack(fill="x", pady=6)
        self.stability_status = ttk.Label(
            stability_card,
            text="Estado: N/D\nObservaciones: N/D\nDuración: N/D\nSimilitud media: N/D",
            justify="left",
        )
        self.stability_status.pack(anchor="w")

        policy_card = ttk.LabelFrame(technical, text="Política de identificación", padding=6)
        policy_card.pack(fill="x", pady=6)
        self.identification_policy_status = ttk.Label(
            policy_card,
            text=("Estado: POLICY_NOT_EVALUATED\nEvaluado: No\n"
                  "Acciones automáticas: Deshabilitadas\nRazón principal: N/D"),
            justify="left",
        )
        self.identification_policy_status.pack(anchor="w")

        orchestrator_card = ttk.LabelFrame(technical, text="Orquestación", padding=6)
        orchestrator_card.pack(fill="x", pady=6)
        self.decision_orchestrator_status = ttk.Label(
            orchestrator_card,
            text=("Estado: NOT_EVALUATED\nPropuestas: N/D\n"
                  "Acciones automáticas: Deshabilitadas\nRazón: N/D"),
            justify="left",
        )
        self.decision_orchestrator_status.pack(anchor="w")

        executor_card = ttk.LabelFrame(technical, text="Ejecución controlada", padding=6)
        executor_card.pack(fill="x", pady=6)
        self.action_executor_status = ttk.Label(
            executor_card,
            text=("Estado: NOT_EVALUATED\nSolicitadas: N/D\nEjecutadas: —\n"
                  "Automatización: Deshabilitada\nRazón: N/D"),
            justify="left",
        )
        self.action_executor_status.pack(anchor="w")

        history_card = ttk.LabelFrame(technical, text="Historial temporal", padding=6)
        history_card.pack(fill="both", expand=True, pady=6)
        self.history = tk.Listbox(history_card, height=6, activestyle="none")
        self.history.pack(fill="both", expand=True)

        # The former "Últimos eventos" card now contains only registered recognitions.
        events_card = ttk.LabelFrame(technical, text="Últimas identificaciones", padding=6)
        events_card.pack(fill="both", expand=True, pady=6)
        self.detection_events = tk.Listbox(events_card, height=5, activestyle="none")
        self.detection_events.pack(fill="both", expand=True)
        ttk.Button(events_card, text="Historial", command=on_detection_history or
                   (lambda: None), state="normal" if self._can("VIEW_DETECTION_HISTORY") else "disabled").pack(anchor="e", pady=(4, 0))
        attendance_card=ttk.LabelFrame(technical,text="ASISTENCIA HOY",padding=6);attendance_card.pack(fill="x",pady=6)
        self.attendance_summary=ttk.Label(attendance_card,text="Presentes: N/D\nCon salida: N/D\nPendientes: N/D\nRetrasos: N/D");self.attendance_summary.pack(anchor="w")
        ttk.Button(attendance_card,text="Abrir asistencia",command=on_attendance_history or (lambda:None),state="normal" if self._can("VIEW_ATTENDANCE") else "disabled").pack(anchor="e")
        reports_card = ttk.LabelFrame(technical, text="Hoy", padding=6); reports_card.pack(fill="x", pady=6)
        self.report_summary = ttk.Label(
            reports_card,
            text="Personas activas: N/D\nDetecciones: N/D\nEntradas: N/D\nSalidas: N/D\nPersonas únicas: N/D",
        )
        self.report_summary.pack(anchor="w")
        self.reports_button = ttk.Button(
            reports_card, text="Ver reportes", command=on_reports or (lambda: None),
            state="normal" if get_daily_report is not None and self._can("VIEW_REPORTS") else "disabled",
        )
        self.reports_button.pack(anchor="e")

        recognition_card=ttk.LabelFrame(side,text="RECONOCIMIENTOS RECIENTES",padding=6)
        recognition_card.pack(fill="both",expand=True,pady=(0,5))
        self.recent_recognition_table=ttk.Treeview(recognition_card,
            columns=("name","time","similarity"),show="tree headings",height=5)
        self.recent_recognition_table.heading("#0",text="Foto")
        for key,label in (("name","Nombre"),("time","Hora"),("similarity","Similitud")):
            self.recent_recognition_table.heading(key,text=label)
        self.recent_recognition_table.pack(fill="both",expand=True)

        today_card=ttk.LabelFrame(side,text="ASISTENCIA DE HOY",padding=6)
        today_card.pack(fill="both",expand=True,pady=5)
        self.recent_attendance_table=ttk.Treeview(today_card,
            columns=("name","in","out","state"),show="tree headings",height=5)
        self.recent_attendance_table.heading("#0",text="Foto")
        for key,label in (("name","Nombre"),("in","Entrada"),("out","Salida"),("state","Estado")):
            self.recent_attendance_table.heading(key,text=label)
        self.recent_attendance_table.pack(fill="both",expand=True)

        operational=ttk.LabelFrame(side,text="ESTADO DEL SISTEMA",padding=6)
        operational.pack(fill="x",pady=(5,0))
        self.operational_status=ttk.Label(operational,text=(
            "Cámara: N/D | Base de datos: N/D\nGalería: 0 | Reconocimiento: Detenido | Asistencia: Desactivada"))
        self.operational_status.pack(anchor="w")

        self.diagnostic_card = ttk.LabelFrame(technical, text="Diagnóstico de calidad", padding=6)
        self.diagnostic_values = ttk.Label(self.diagnostic_card, text="N/D")
        self.diagnostic_values.pack(anchor="w")
        self.diagnostic_card.pack(fill="x",padx=10,pady=4)

        metrics_card = ttk.LabelFrame(technical, text="Métricas de sesión", padding=6)
        metrics_card.pack(fill="x",padx=10,pady=4)
        self.metrics = ttk.Label(metrics_card, text="Captura FPS: N/D | Pipeline FPS: N/D | Latencia inferencia: N/D")
        self.metrics.pack(anchor="w")
        self.system_health = ttk.Label(metrics_card, text="Estado del sistema: N/D | FPS móvil: N/D | Memoria: N/D | Uptime: N/D")
        self.system_health.pack(anchor="w")
        self.audit_summary = ttk.Label(metrics_card,text="Auditoría: N/D")
        self.audit_summary.pack(anchor="w")

        actions = ttk.Frame(root, padding=(10, 6)); actions.grid(row=3, column=0, sticky="ew")
        self.register_button = ttk.Button(actions, text="Registrar rostro", command=self.open_form,state="normal" if self._can("ENROLL_PERSON") else "disabled")
        self.register_button.pack(side="left", padx=3)
        self.people_button = ttk.Button(actions, text="Personas registradas", command=on_people or (lambda: None),state="normal" if self._can("VIEW_PEOPLE") else "disabled")
        self.people_button.pack(side="left", padx=3)
        self.backup_button = ttk.Button(actions, text="Copias de seguridad", command=on_backup or (lambda: None),state="normal" if self._can("BACKUP") or self._can("RESTORE") else "disabled")
        self.backup_button.pack(side="left", padx=3)
        self.health_button = ttk.Button(actions,text="Ver diagnóstico",command=on_system_health or (lambda:None),state="normal" if system_health_controller is not None and self._can("VIEW_SYSTEM_HEALTH") else "disabled")
        self.health_button.pack(side="left",padx=3)
        self.audit_button = ttk.Button(actions,text="Auditoría",command=on_audit or (lambda:None),state="normal" if on_audit is not None and self._can("VIEW_AUDIT") else "disabled")
        self.audit_button.pack(side="left",padx=3)
        ttk.Button(actions, text="Diagnóstico", command=self.toggle_diagnostic).pack(side="left", padx=3)
        ttk.Button(actions, text="Configuración", command=on_configuration or (lambda: None)).pack(side="left", padx=3)
        self.camera_button = ttk.Button(actions, text="Cámara", command=on_camera or (lambda: None),
                                        state="normal" if on_camera is not None else "disabled")
        self.camera_button.pack(side="left", padx=3)
        ttk.Button(actions, text="Guardar galería", command=self._save_gallery).pack(side="left", padx=3)
        self.cancel_button = ttk.Button(actions, text="Cancelar", command=self._cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=3)
        ttk.Button(actions, text="Salir", command=self.close).pack(side="right", padx=3)
        # Legacy condition retained conceptually: if self._system_health_controller is not None,
        # RC13 reads it through the single professional dashboard coordinator.
        if self._audit_controller is not None:
            self._audit_after_id=self.root.after(0,self._schedule_audit_summary)
        root.bind("<F11>",self.toggle_fullscreen)
        root.bind("<Escape>",self.exit_fullscreen)

    def show_monitoring(self, dto: MonitoringDTO) -> None:
        view = monitoring_text(dto)

        self.status.configure(text=view.headline)
        self.candidate.configure(text=view.candidate)
        self.similarity.configure(
            text=f"Similitud: {view.similarity}"
        )
        self.decision.configure(text=view.decision)
        self.quality.configure(
            text=f"Score: {view.quality}"
        )

        self.register_button.configure(
            state="normal"
            if dto.registration_enabled
            else "disabled"
        )
        if self._registration_form_open:
            self.register_button.configure(state="disabled")
            return
        if self._enrollment_active:
            if dto.state is not UIState.MONITORING:
                self.register_button.configure(state="disabled")
                return
            self._enrollment_active = False
            self._close_enrollment_form()
            self._on_registration_form_state(False)
            if self._identification is not None:
                self._identification.resume()
        if getattr(self, "_popup_mode", "legacy") == "action_executor":
            if (
                dto.state in {UIState.NO_FACE, UIState.MULTIPLE_FACES}
                and self._identification_popup is not None
                and self._identification_popup.popup_type
                    is IdentificationPopupType.REGISTERED_CANDIDATE
            ):
                self._dismiss_identification_popup("programmatic")
            return
        if self._identification is not None and self._identification_popup is not None:
            orchestration = getattr(self, "_decision_orchestrator", None)
            if orchestration is not None:
                required_action = (
                    "SHOW_REGISTERED_POPUP" if dto.candidate_person_id is not None
                    else "SHOW_UNREGISTERED_POPUP"
                )
                if required_action not in orchestration.proposed_actions:
                    return
            popup = self._identification.observe(dto)
            if (
                popup.popup_type is IdentificationPopupType.SUPPRESSED
                and dto.state in {UIState.NO_FACE, UIState.MULTIPLE_FACES}
                and self._identification_popup.popup_type
                    is IdentificationPopupType.REGISTERED_CANDIDATE
            ):
                self._dismiss_identification_popup("programmatic")
            self._identification_popup.show(popup)

    def show_progress(
        self,
        dto: EnrollmentProgressDTO,
    ) -> None:
        self._enrollment_active = True
        self._set_camera_switch_allowed(False)
        self._clear_pending_popups()
        if self._identification is not None:
            self._identification.suspend()
        if self._identification_popup is not None:
            self._dismiss_identification_popup("enrollment")
        self.status.configure(
            text=(
                f"Paso {min(dto.accepted_samples + 1, dto.target_samples)} de "
                f"{dto.target_samples} — {dto.instruction} — "
                f"{dto.accepted_samples}/{dto.target_samples}"
            )
        )
        if getattr(self, "_enrollment_progress", None) is not None:
            self._enrollment_progress.configure(
                text=(f"Muestras: {dto.accepted_samples} / {dto.target_samples}\n"
                      f"{_enrollment_progress_bar(dto.accepted_samples, dto.target_samples)}")
            )
        if (getattr(self, "_enrollment_video", None) is not None
                and self._enrollment_guide_text is not None):
            self._enrollment_video.itemconfigure(
                self._enrollment_guide_text,
                text=(f"Paso {min(dto.accepted_samples + 1, dto.target_samples)}/"
                      f"{dto.target_samples} · {dto.instruction}"),
            )
        if getattr(self, "_enrollment_quality", None) is not None:
            quality = "No disponible" if dto.quality_score is None else f"{dto.quality_score:.1f}/100"
            self._enrollment_quality.configure(text=f"Calidad de captura: {quality}\nEstado: {_capture_quality_state(dto.quality_score)}")
        if getattr(self, "_enrollment_reasons", None) is not None:
            reasons = (f"✓ Muestra guardada {dto.accepted_samples}/{dto.target_samples}"
                       if not dto.current_reasons and dto.accepted_samples else
                       "Buena imagen detectada") if not dto.current_reasons else \
                "No capturada: " + ", ".join(
                    _enrollment_reason(reason) for reason in dto.current_reasons
                )
            checklist = _enrollment_checklist(dto.accepted_samples, dto.target_samples)
            self._enrollment_reasons.configure(
                text=(f"Paso {min(dto.accepted_samples + 1, dto.target_samples)} de "
                      f"{dto.target_samples}\n{dto.instruction}\n{reasons}\n\n{checklist}")
            )
        if getattr(self, "_capture_button", None) is not None:
            self._capture_button.configure(state="normal")

        self.register_button.configure(
            state="disabled"
        )

        self.cancel_button.configure(
            state=(
                "normal"
                if dto.cancellation_enabled
                else "disabled"
            )
        )

    def show_result(
        self,
        dto: EnrollmentResultDTO,
    ) -> None:
        self._enrollment_active = True
        self._registration_form_open = False
        self.status.configure(text=dto.message)
        self.candidate.configure(text=dto.display_name)

        if getattr(self, "_profile_photo_after_enrollment", False) and self._form is not None:
            form = self._form
            for child in form.winfo_children(): child.destroy()
            form.title("REGISTRO FACIAL COMPLETADO")
            ttk.Label(form, text="✓ REGISTRO FACIAL COMPLETADO",
                      font=("TkDefaultFont", 16, "bold")).pack(pady=(40, 12))
            ttk.Label(form, text=f"{dto.templates_registered}/5 muestras\n\n"
                      "Se guardaron 5 muestras biométricas correctamente.\n\n"
                      "¿Desea tomar una fotografía de perfil?",
                      justify="center").pack(pady=12)
            actions = ttk.Frame(form); actions.pack(pady=16)
            ttk.Button(actions, text="Tomar fotografía",
                       command=lambda: self._continue_profile_photo(dto.person_id)).pack(side="left", padx=6)
            ttk.Button(actions, text="Omitir por ahora",
                       command=self._skip_profile_photo).pack(side="left", padx=6)
            return

        self._close_enrollment_form()

        self.register_button.configure(state="disabled")

        self.cancel_button.configure(
            state="disabled"
        )
        previous = getattr(self, "_enrollment_resume_after_id", None)
        if previous is not None:
            try: self.root.after_cancel(previous)
            except Exception: pass
        root = getattr(self, "root", None)
        if root is None or not hasattr(root, "after"):
            self._finish_enrollment_grace()
        else:
            self._enrollment_resume_after_id = root.after(
                2500, self._finish_enrollment_grace,
            )

    def _continue_profile_photo(self, person_id: str) -> None:
        self._close_enrollment_form()
        if self._on_start_photo is None or not self._on_start_photo(person_id):
            self.status.configure(text="No se pudo iniciar la fotografía de perfil.")

    def _skip_profile_photo(self) -> None:
        self._close_enrollment_form()
        self.status.configure(text="Registro facial completado. Fotografía omitida por ahora.")
        self._finish_enrollment_grace()

    def show_enrollment_conflict(self, dto: EnrollmentConflictDTO) -> None:
        self._enrollment_active = False
        self._registration_form_open = True
        form = self._form
        if form is None or not form.winfo_exists():
            self._leave_registration_form_state(resume=True)
            self.status.configure(text=dto.message)
            return
        for child in form.winfo_children():
            child.destroy()
        form.title("Conflicto de registro")
        photo = "Disponible" if dto.thumbnail_available else "No disponible"
        samples = (str(dto.template_count) if dto.template_count else "No disponibles")
        ttk.Label(
            form,
            text=("PERSONA YA REGISTRADA\n\n"
                  f"Nombre: {dto.display_name or 'No disponible'}\n"
                  f"Estado: {dto.person_status}\nFotografía: {photo}\n"
                  f"Muestras biométricas: {samples}\n\n{dto.message}"),
            wraplength=440, justify="left",
        ).pack(padx=20, pady=20)
        actions = ttk.Frame(form); actions.pack(pady=(0, 20))
        if (dto.person_status == "ACTIVE" and not dto.thumbnail_available
                and self._on_start_photo is not None):
            ttk.Button(
                actions, text="Capturar foto",
                command=lambda: self._start_conflict_photo(dto.person_id),
            ).pack(side="left", padx=5)
        if dto.can_view_person and self._on_view_person is not None:
            ttk.Button(actions, text="Ver persona",
                       command=lambda: self._view_conflict_person(dto.person_id)).pack(
                           side="left", padx=5)
        if dto.can_add_samples and self._on_additional_enrollment is not None:
            ttk.Button(actions, text="Agregar muestras",
                       command=lambda: self._start_conflict_additional(dto.person_id)).pack(
                           side="left", padx=5)
        ttk.Button(actions, text="Cancelar",
                   command=lambda: self._close_conflict_form()).pack(side="left", padx=5)

    def _finish_enrollment_grace(self) -> None:
        self._enrollment_resume_after_id = None
        if self._closing:
            return
        self._enrollment_active = False
        self._on_registration_form_state(False)
        if self._identification is not None:
            self._identification.resume()
        self.register_button.configure(state="normal")

    def _start_conflict_additional(self, person_id: str) -> None:
        if self._on_additional_enrollment is None:
            return
        if self._on_additional_enrollment(person_id):
            self._registration_form_open = False
            self._enrollment_active = True
            self._close_enrollment_form()

    def _start_conflict_photo(self, person_id: str) -> None:
        if self._on_start_photo is None:
            return
        if self._on_start_photo(person_id):
            self._close_enrollment_form()
            self._registration_form_open = False
            self._enrollment_active = True

    def _view_conflict_person(self, person_id: str) -> None:
        """Release the modal conflict form before opening the existing profile UI."""
        callback = self._on_view_person
        if callback is None:
            return
        self._close_enrollment_form()
        self._leave_registration_form_state(resume=True)
        callback(person_id)

    def _close_conflict_form(self) -> None:
        self._close_enrollment_form()
        self._leave_registration_form_state(resume=True)

    def show_error(
        self,
        dto: ErrorDTO,
    ) -> None:
        self.status.configure(text=dto.message)

        if dto.operation is UIErrorCode.ENROLLMENT_ERROR and not dto.recoverable:
            self._enrollment_active = False
            self._registration_form_open = False
            self._close_enrollment_form()
            self._on_registration_form_state(False)
            if self._identification is not None and not self._closing:
                self._identification.resume()

        if not dto.recoverable:
            self.register_button.configure(
                state="disabled"
            )

    def show_runtime_status(
        self,
        dto: RuntimeStatusDTO,
    ) -> None:
        self._camera_source_name=dto.camera_source_name
        self._camera_source_type=dto.camera_source_type
        self.runtime_status.configure(
            text=(
                f"Cámara: {dto.camera_state}\n"
                f"Runtime: {dto.runtime_state}\n"
                f"YuNet: {dto.detector_model_state}\n"
                f"ArcFace: {dto.embedding_model_state}"
            )
        )
        self.header_state.configure(
            text=f"Cámara ● {dto.camera_state}   Runtime ● {dto.runtime_state}"
        )
        if hasattr(self, "camera_button"):
            self.camera_button.configure(
                text="Buscar cámaras" if dto.camera_state == "disconnected" else "Cámara",
                state="normal" if dto.camera_switch_allowed else "disabled",
            )
        state_text = {
            "connected": "Conectada", "disconnected": "Desconectada",
            "reconnecting": "Reconectando", "error": "Error",
        }.get(dto.camera_state, dto.camera_state.title())
        if hasattr(self, "camera_status"):
            self.camera_status.configure(
                text=f"Estado: {state_text}\nFuente: {dto.camera_source_name}\nTipo: {dto.camera_source_type}"
            )
            allowed = "normal" if dto.camera_switch_allowed else "disabled"
            self.camera_search_button.configure(state=allowed)
            self.camera_change_button.configure(state=allowed)
            self.camera_retry_button.configure(
                state=allowed if dto.camera_state == "disconnected" else "disabled"
            )

    def poll_session(
        self,
        session: Any,
        interval_ms: int = 30,
    ) -> None:
        """Drain bounded worker queues from Tk's main thread only."""

        self._drain_action_popups()
        visual = session.take_latest_visual()

        if visual is not None:
            self.show_rgb_frame(
                visual.width,
                visual.height,
                visual.rgb_bytes,
            )
            del visual
            if self._system_health_service is not None:
                self._system_health_service.observe_frame()

        metrics, quality = session.dashboard_telemetry()
        if self._system_health_service is not None:
            try:
                depth = session.visual_queue.qsize()+session.event_queue.qsize()+session.command_queue.qsize()
            except Exception:
                depth = None
            self._system_health_service.observe_counters(queue_depth=depth,dropped_frames=metrics.visual_frames_dropped)
        self._dashboard.update_metrics(metrics)
        self._dashboard.update_quality(quality)
        if self._get_gallery is not None:
            try:
                self._dashboard.update_gallery(self._get_gallery())
            except Exception:
                pass

        for event in session.drain_events():
            self._dashboard.consume(event)

            if isinstance(event, MonitoringDTO):
                self.show_monitoring(event)

            elif isinstance(
                event,
                EnrollmentProgressDTO,
            ):
                self.show_progress(event)

            elif isinstance(
                event,
                EnrollmentResultDTO,
            ):
                self.show_result(event)

            elif isinstance(event, EnrollmentConflictDTO):
                self.show_enrollment_conflict(event)

            elif isinstance(event, PersonPhotoCaptureDTO):
                self.show_person_photo_capture(event)

            elif isinstance(event, ErrorDTO):
                self.show_error(event)

            elif isinstance(
                event,
                RuntimeStatusDTO,
            ):
                self.show_runtime_status(event)

            elif isinstance(event, PeopleOperationResultDTO):
                self.status.configure(text=event.message)

            elif isinstance(event, StabilityDTO):
                self._stability = event
                self._refresh_stability()

            elif isinstance(event, IdentificationPolicyDTO):
                self._identification_policy = event
                self._refresh_identification_policy()

            elif isinstance(event, DecisionOrchestratorDTO):
                self._decision_orchestrator = event
                self._refresh_decision_orchestrator()

            elif isinstance(event, ActionExecutorDTO):
                self._action_executor = event
                self._refresh_action_executor()

        now = time.monotonic()
        if now - self._last_dashboard_refresh >= self._metrics_refresh_seconds:
            self._refresh_dashboard()
            self._last_dashboard_refresh = now

        if self.root.winfo_exists():
            self.root.after(
                interval_ms,
                self.poll_session,
                session,
                interval_ms,
            )

    def _drain_action_popups(self) -> None:
        if (getattr(self, "_popup_mode", "legacy") != "action_executor"
                or getattr(self, "_get_popup_requests", None) is None):
            return
        for dto in self._get_popup_requests():
            if self._closing or self._registration_form_open or self._enrollment_active:
                continue
            if self._identification_popup is not None:
                self._identification_popup.show(dto)

    def _clear_pending_popups(self) -> None:
        callback = getattr(self, "_clear_popup_requests", None)
        if callback is not None:
            callback()

    def _refresh_dashboard(self) -> None:
        remaining = (
            0.0 if self._identification is None
            else self._identification.registered_pause_remaining_seconds()
        )
        if remaining > 0:
            seconds = max(1, math.ceil(remaining))
            self.recognition_pause.configure(
                text=f"Reconocimiento pausado: {seconds // 60:02d}:{seconds % 60:02d}"
            )
        else:
            self.recognition_pause.configure(text="")
        metrics = self._dashboard.metrics
        self.metrics.configure(text=(
            f"Captura efectiva FPS: {_number(metrics.effective_capture_fps)} | "
            f"Pipeline FPS: {_number(metrics.effective_processing_fps)} | "
            f"Latencia inferencia: {_number(metrics.inference_latency_ms, ' ms')} | "
            f"Frames: {metrics.frames_received}/{metrics.frames_processed} | "
            f"Descartados: {metrics.visual_frames_dropped} | "
            f"Rostros: {metrics.faces_detected_current} ({metrics.faces_detected_total}) | "
            f"Embeddings: {metrics.embeddings_generated} | Uptime: {metrics.uptime_seconds:.1f}s"
        ))
        gallery = self._dashboard.gallery
        self.gallery_status.configure(
            text=f"Personas: {gallery.identities}\nTemplates: {gallery.templates}"
        )
        self._refresh_candidate_thumbnail(self._dashboard.recognition.person_id)
        quality = self._dashboard.quality
        self.diagnostic_values.configure(text="\n".join(
            f"{item.name}: {_value(item.value)} — {item.state.value}"
            for item in quality.metrics
        ) or "N/D")
        current_history = self._dashboard.history
        if current_history != self._history_rendered:
            self.history.delete(0, "end")
            for item in current_history:
                suffix = f" — {item.display_name}" if item.display_name else ""
                self.history.insert("end", f"{item.timestamp:%H:%M:%S} {item.message}{suffix}")
            self._history_rendered = current_history
        if self._dashboard_refresh_coordinator is None and self._get_detection_events is not None:
            try: recent_events = self._get_detection_events()
            except Exception: recent_events = ()
            if recent_events != self._detection_events_rendered:
                self.detection_events.delete(0, "end")
                for item in recent_events:
                    person = item.display_name or "No registrada"
                    similarity = ("N/D" if item.similarity is None
                                  else f"{item.similarity * 100:.0f}%")
                    self.detection_events.insert(
                        "end", f"{person} — {item.timestamp.astimezone(ZoneInfo('America/Guayaquil')):%H:%M} — {similarity}"
                    )
                self._detection_events_rendered = recent_events
        if self._dashboard_refresh_coordinator is None and self._get_attendance_summary is not None:
            try:
                item=self._get_attendance_summary()
                latest="\n".join(f"{name} — {'Entrada' if kind.endswith('CHECK_IN') else 'Salida'} {when.astimezone(ZoneInfo('America/Guayaquil')):%H:%M}" for name,kind,when in item.latest)
                self.attendance_summary.configure(text=f"Presentes: {item.present}\nCon salida: {item.completed}\nPendientes: {item.pending}\nRetrasos: {item.late}"+(f"\nÚltimos:\n{latest}" if latest else ""))
            except Exception:self.attendance_summary.configure(text="Asistencia no disponible")

    def _refresh_stability(self) -> None:
        value = stability_text(self._stability)
        self.stability_status.configure(text=(
            f"Estado: {value.state}\n"
            f"Observaciones: {value.observations}\n"
            f"Duración: {value.duration}\n"
            f"Similitud media: {value.average_similarity}"
        ))

    def _refresh_identification_policy(self) -> None:
        value = identification_policy_text(self._identification_policy)
        self.identification_policy_status.configure(text=(
            f"Estado: {value.state}\n"
            f"Evaluado: {value.evaluated}\n"
            f"Acciones automáticas: {value.automatic_actions}\n"
            f"Razón principal: {value.primary_reason}"
        ))

    def _refresh_decision_orchestrator(self) -> None:
        value = decision_orchestrator_text(self._decision_orchestrator)
        self.decision_orchestrator_status.configure(text=(
            f"Estado: {value.state}\n"
            f"Propuestas: {value.proposals}\n"
            f"Acciones automáticas: {value.automatic_actions}\n"
            f"Razón: {value.primary_reason}"
        ))

    def _refresh_action_executor(self) -> None:
        value = action_executor_text(self._action_executor)
        self.action_executor_status.configure(text=(
            f"Estado: {value.state}\n"
            f"Solicitadas: {value.requested}\n"
            f"Ejecutadas: {value.executed}\n"
            f"Automatización: {value.automation}\n"
            f"Razón: {value.primary_reason}"
        ))

    def _refresh_candidate_thumbnail(self, person_id: str | None) -> None:
        """Load only when candidate identity changes, never once per video frame."""
        if person_id != self._thumbnail_person_id:
            self._thumbnail_person_id = person_id
            self._thumbnail_photo = None
            self.candidate_thumbnail.configure(image="", text="Sin foto registrada")
            if person_id is not None and self._get_thumbnail is not None:
                try:
                    payload = thumbnail_to_ppm(self._get_thumbnail(person_id))
                    if payload is not None:
                        photo = tk.PhotoImage(data=payload, format="PPM")
                        self.candidate_thumbnail.configure(image=photo, text="")
                        self._thumbnail_photo = photo
                except Exception:
                    self.candidate_thumbnail.configure(image="", text="Sin foto registrada")

    def toggle_diagnostic(self) -> None:
        if self._diagnostic_visible:
            self.technical_panel.grid_remove()
        else:
            self.technical_panel.grid(row=4,column=0,sticky="ew",padx=10,pady=4)
        self._diagnostic_visible = not self._diagnostic_visible

    def set_dashboard_refresh_coordinator(self, coordinator) -> None:
        self._dashboard_refresh_coordinator=coordinator
        coordinator.start()

    def set_appliance_shutdown(self, web_shutdown=None, frame_store_close=None) -> None:
        self._web_shutdown=web_shutdown;self._presentation_frame_close=frame_store_close

    def professional_live_state(self) -> DashboardLiveStateDTO:
        recognition_state=self._dashboard.system.recognition_state
        if (self._identification is not None and
                self._identification.registered_pause_remaining_seconds()>0):
            recognition_state="PAUSED"
        return DashboardLiveStateDTO(
            self._dashboard.system.camera_state,self._dashboard.system.runtime_state,
            recognition_state,self._dashboard.gallery.identities,
        )

    def show_professional_dashboard(self, value: DashboardSnapshotDTO) -> None:
        if self._closing:return
        for key,number in (("present",value.people_present),("recognitions",value.recognitions_today),
                           ("entries",value.check_ins_today),("late",value.late_today)):
            self.stat_values[key].configure(text="N/D" if number is None else str(number))
        self._professional_photos.clear()
        self.recent_recognition_table.delete(*self.recent_recognition_table.get_children())
        for row in value.recent_recognitions:
            photo=self._dashboard_photo(row.photo);text="Sin fotografía" if photo is None else ""
            self.recent_recognition_table.insert("","end",text=text,image=photo or "",values=(
                row.display_name,row.local_time,"N/D" if row.similarity is None else f"{row.similarity*100:.1f}%"))
        self.recent_attendance_table.delete(*self.recent_attendance_table.get_children())
        for row in value.recent_attendance:
            photo=self._dashboard_photo(row.photo);text="Sin fotografía" if photo is None else ""
            self.recent_attendance_table.insert("","end",text=text,image=photo or "",values=(
                row.display_name,row.check_in_local or "—",row.check_out_local or "—",row.status))
        self.operational_status.configure(text=(
            f"Cámara: {value.camera_state} | Base de datos: {value.database_state}\n"
            f"Galería: {value.gallery_identities} | Reconocimiento: {value.recognition_state} | "
            f"Asistencia: {value.attendance_state}"))

    def _dashboard_photo(self,value):
        try:payload=thumbnail_to_ppm(value,max_width=48,max_height=48)
        except Exception:payload=None
        if payload is None:return None
        photo=tk.PhotoImage(data=payload,format="PPM");self._professional_photos.append(photo);return photo

    def toggle_fullscreen(self,_event=None):
        self._fullscreen=not self._fullscreen
        self.root.attributes("-fullscreen",self._fullscreen)
        return "break"

    def exit_fullscreen(self,_event=None):
        self._fullscreen=False;self.root.attributes("-fullscreen",False);return "break"

    def _schedule_report_refresh(self, *, initial: bool = False) -> None:
        if self._closing or self._get_daily_report is None: return
        if not initial:
            try:
                report = self._get_daily_report()
                self.report_summary.configure(text=(
                    f"Personas activas: {report.active_people}\n"
                    f"Detecciones: {report.detection_events}\n"
                    f"Entradas: {report.attendance_check_ins}\n"
                    f"Salidas: {report.attendance_check_outs}\n"
                    f"Personas únicas: {report.unique_attendance_people}"
                ))
            except Exception:
                self.report_summary.configure(text=(
                    "Personas activas: N/D\nDetecciones: N/D\nEntradas: N/D\n"
                    "Salidas: N/D\nPersonas únicas: N/D"
                ))
        self._report_after_id = self.root.after(
            max(1, int(self._report_refresh_seconds * 1_000)),
            self._schedule_report_refresh,
        )

    def _save_gallery(self) -> None:
        if self._on_save_gallery is None:
            return
        result = self._on_save_gallery()
        message = getattr(result, "message", None)
        if message:
            self.status.configure(text=message)

    def show_rgb_frame(
        self,
        width: int,
        height: int,
        rgb_bytes: bytes,
    ) -> None:
        """
        Display one transient RGB frame.

        Only Tk's current PhotoImage is retained.
        """

        available_width = max(1, self.video.winfo_width())
        available_height = max(1, self.video.winfo_height())
        width, height, rgb_bytes = render_rgb(
            rgb_bytes, width, height, available_width, available_height,
            self._video_presentation,
        )
        header = f"P6 {width} {height} 255\n".encode("ascii")

        photo = tk.PhotoImage(
            data=header + rgb_bytes,
            format="PPM",
        )

        self.video.coords(self._video_item, available_width // 2, available_height // 2)
        self.video.itemconfigure(self._video_item, image=photo)

        self._photo = photo
        enrollment_video = getattr(self, "_enrollment_video", None)
        if enrollment_video is not None:
            try:
                if enrollment_video.winfo_exists():
                    if self._enrollment_video_item is not None:
                        area_width = max(1, enrollment_video.winfo_width())
                        area_height = max(1, enrollment_video.winfo_height())
                        enrollment_video.coords(
                            self._enrollment_video_item, area_width // 2, area_height // 2,
                        )
                        enrollment_video.itemconfigure(self._enrollment_video_item, image=photo)
            except Exception:
                self._enrollment_video = None
        photo_preview = getattr(self, "_photo_capture_preview", None)
        if photo_preview is not None and self._photo_capture_image is None:
            try:
                if photo_preview.winfo_exists():
                    photo_preview.configure(image=photo, text="")
            except Exception:
                self._photo_capture_preview = None

    def show_person_photo_capture(self, dto: PersonPhotoCaptureDTO) -> None:
        if dto.state is UIState.MONITORING:
            self.status.configure(text=dto.message)
            self._close_photo_capture()
            self._enrollment_active = False
            self._set_camera_switch_allowed(True)
            self._on_registration_form_state(False)
            if self._identification is not None:
                self._identification.resume()
            return
        self._enrollment_active = True
        self._set_camera_switch_allowed(False)
        self._clear_pending_popups()
        if self._identification is not None:
            self._identification.suspend()
        if self._identification_popup is not None:
            self._dismiss_identification_popup("photo_capture")
        if self._photo_capture_window is None:
            window = tk.Toplevel(self.root)
            self._photo_capture_window = window
            window.title("CAPTURA DE FOTO DE PERFIL")
            window.geometry("650x650")
            window.protocol("WM_DELETE_WINDOW", self._cancel_person_photo)
            self._photo_capture_heading = ttk.Label(
                window, text="CAPTURA DE FOTO DE PERFIL",
                font=("TkDefaultFont", 15, "bold"),
            )
            self._photo_capture_heading.pack(pady=10)
            self._photo_capture_preview = ttk.Label(
                window, text="Esperando video", anchor="center",
            )
            self._photo_capture_preview.pack(fill="both", expand=True, padx=15, pady=8)
            self._photo_capture_quality = ttk.Label(window, text="Calidad actual: N/D")
            self._photo_capture_quality.pack()
            self._photo_capture_stability = ttk.Label(window, text="Estabilidad: 0/5")
            self._photo_capture_stability.pack()
            self._photo_capture_status = ttk.Label(window, wraplength=580)
            self._photo_capture_status.pack(pady=6)
            actions = ttk.Frame(window); actions.pack(pady=10)
            self._photo_capture_take = ttk.Button(
                actions, text="Capturar fotografía",
                command=lambda: self._on_capture_photo and self._on_capture_photo(),
            )
            if self._photo_capture_mode == "manual":
                self._photo_capture_take.pack(side="left", padx=4)
            self._photo_capture_use = ttk.Button(
                actions, text="Usar esta foto",
                command=lambda: self._on_confirm_photo and self._on_confirm_photo(),
            )
            self._photo_capture_use.pack(side="left", padx=4)
            self._photo_capture_repeat = ttk.Button(
                actions, text="Repetir", command=self._retake_person_photo,
            )
            self._photo_capture_repeat.pack(side="left", padx=4)
            ttk.Button(actions, text="Cancelar", command=self._cancel_person_photo).pack(
                side="left", padx=4,
            )
        self._photo_capture_status.configure(text=dto.message)
        self._photo_capture_heading.configure(
            text="FOTO CAPTURADA" if dto.review else "CAPTURA DE FOTO DE PERFIL",
        )
        quality = "N/D" if dto.quality_score is None else f"{dto.quality_score:.1f}/100"
        self._photo_capture_quality.configure(
            text=f"Calidad actual: {quality}\nEstado: {_capture_quality_state(dto.quality_score)}"
        )
        required = dto.stability_required or 5
        self._photo_capture_stability.configure(
            text=f"Estabilidad: {dto.stability_observations}/{required}",
        )
        self._photo_capture_take.configure(
            state="normal" if self._photo_capture_mode == "manual"
            and dto.ready and not dto.review else "disabled",
        )
        self._photo_capture_use.configure(state="normal" if dto.review else "disabled")
        self._photo_capture_repeat.configure(state="normal" if dto.review else "disabled")
        if dto.review and dto.image_bytes:
            visual = ThumbnailDTO(dto.person_id, True, 112, 112, "png", dto.image_bytes)
            payload = thumbnail_to_ppm(visual)
            if payload is not None:
                self._photo_capture_image = tk.PhotoImage(data=payload, format="PPM")
                self._photo_capture_preview.configure(image=self._photo_capture_image, text="")
        elif not dto.review:
            self._photo_capture_image = None

    def _retake_person_photo(self) -> None:
        self._photo_capture_image = None
        if self._on_retake_photo is not None:
            self._on_retake_photo()

    def _cancel_person_photo(self) -> None:
        if self._on_cancel_photo is not None:
            self._on_cancel_photo()

    def _close_photo_capture(self) -> None:
        window = self._photo_capture_window
        self._photo_capture_window = None
        self._photo_capture_preview = None
        self._photo_capture_image = None
        if window is not None:
            try:
                if window.winfo_exists():
                    window.destroy()
            except Exception:
                pass

    def open_form(self) -> None:
        """
        Open the local registration form.

        The form only collects safe textual metadata
        and explicit consent.
        """

        if (
            self._form is not None
            and self._form.winfo_exists()
        ):
            self._form.lift()
            self._form.focus_force()
            return

        self._enter_registration_form_state()

        try:
            form = tk.Toplevel(self.root)
        except Exception:
            self._leave_registration_form_state(resume=True)
            raise
        self._form = form

        form.title("Registrar rostro")
        form.transient(self.root)
        form.grab_set()

        # -------------------------------------------------
        # IMPORTANTE:
        # Todas las variables Tkinter reciben como master
        # la ventana del formulario.
        # -------------------------------------------------

        values = {
            name: tk.StringVar(master=form)
            for name in (
                "cedula", "first", "last", "address", "phone", "email",
                "birth_date", "sex", "notes",
            )
        }

        consent = tk.BooleanVar(
            master=form,
            value=False,
        )

        persist = tk.BooleanVar(
            master=form,
            value=False,
        )

        fields = (
            ("Cédula", "cedula"),
            ("Nombre", "first"),
            ("Apellido", "last"),
            ("Dirección (opcional)", "address"),
            ("Teléfono (opcional)", "phone"),
            ("Email (opcional)", "email"),
            ("Fecha nacimiento YYYY-MM-DD (opcional)", "birth_date"),
            ("Sexo (opcional)", "sex"),
            ("Observaciones (opcional)", "notes"),
        )

        for row, (label, key) in enumerate(fields):

            ttk.Label(
                form,
                text=label,
            ).grid(
                row=row,
                column=0,
                sticky="w",
                padx=8,
                pady=4,
            )

            entry = ttk.Entry(
                form,
                textvariable=values[key],
                width=32,
            )

            entry.grid(
                row=row,
                column=1,
                padx=8,
                pady=4,
                sticky="ew",
            )

            if row == 0:
                entry.focus_set()

        consent_row = len(fields)
        ttk.Checkbutton(
            form,
            text=(
                "Confirmo consentimiento biométrico"
            ),
            variable=consent,
        ).grid(
            row=consent_row,
            column=0,
            columnspan=2,
            sticky="w",
            padx=8,
            pady=(8, 4),
        )

        ttk.Checkbutton(
            form,
            text=(
                "Persistir galería local "
                "después del registro"
            ),
            variable=persist,
        ).grid(
            row=consent_row + 1,
            column=0,
            columnspan=2,
            sticky="w",
            padx=8,
            pady=4,
        )

        def close_form(*, enrollment_started: bool = False) -> None:
            """
            Close the form and clear its reference.
            """

            if self._form is form:
                self._form = None

            try:
                form.grab_release()
            except tk.TclError:
                pass

            if form.winfo_exists():
                form.destroy()
            if enrollment_started:
                self._registration_form_open = False
                self._enrollment_active = True
            else:
                self._leave_registration_form_state(resume=not self._closing)

        def submit() -> None:
            """
            Validate form and start guided enrollment.
            """

            try:
                data = validate_registration_form(
                    values["first"].get(),
                    values["last"].get(),
                    None,
                    consent_confirmed=consent.get(),
                    persist_locally=persist.get(),
                    cedula=values["cedula"].get(),
                    address=values["address"].get(),
                    phone=values["phone"].get(),
                    email=values["email"].get(),
                    birth_date=values["birth_date"].get(),
                    sex=values["sex"].get(),
                    notes=values["notes"].get(),
                )

            except RegistrationFormError as exc:

                if messagebox is not None:
                    messagebox.showerror(
                        "Formulario inválido",
                        str(exc),
                        parent=form,
                    )

                return

            accepted = self._on_register(data)
            if accepted is not False:
                self._show_enrollment_capture(form)

        ttk.Button(
            form,
            text="Iniciar captura guiada",
            command=submit,
        ).grid(
            row=consent_row + 2,
            column=0,
            padx=8,
            pady=10,
        )

        ttk.Button(
            form,
            text="Cancelar",
            command=close_form,
        ).grid(
            row=consent_row + 2,
            column=1,
            padx=8,
            pady=10,
        )

        # Si el usuario cierra con la X,
        # limpiamos también self._form.
        form.protocol(
            "WM_DELETE_WINDOW",
            close_form,
        )

        form.columnconfigure(
            1,
            weight=1,
        )

    def _show_enrollment_capture(self, form: Any) -> None:
        """Transform the existing civil form into a safe enrollment presentation."""
        for child in form.winfo_children():
            child.destroy()
        self._registration_form_open = False
        self._enrollment_active = True
        form.title("REGISTRO FACIAL")
        form.geometry("760x720")
        ttk.Label(form, text="REGISTRO FACIAL", font=("TkDefaultFont", 16, "bold")).pack(
            pady=(16, 8)
        )
        self._enrollment_video = tk.Canvas(
            form, background="#202124", highlightthickness=0,
        )
        self._enrollment_video.pack(fill="both", expand=True, padx=18, pady=8)
        self._enrollment_video_item = self._enrollment_video.create_image(
            0, 0, anchor="center",
        )
        self._enrollment_video.create_oval(
            230, 45, 530, 420, outline="#54d38a", width=3,
        )
        self._enrollment_guide_text = self._enrollment_video.create_text(
            380, 24, text="Centre su rostro", fill="white",
            font=("TkDefaultFont", 13, "bold"),
        )
        self._enrollment_quality = ttk.Label(form, text="Calidad: No disponible")
        self._enrollment_quality.pack(pady=3)
        self._enrollment_progress = ttk.Label(
            form, text=f"Muestras: 0 / {self._enrollment_target_samples}",
        )
        self._enrollment_progress.pack(pady=3)
        self._enrollment_reasons = ttk.Label(
            form,
            text=("Mantenga el rostro frente a cámara\n\n" +
                  _enrollment_checklist(0, self._enrollment_target_samples)),
            justify="left", wraplength=680,
        )
        self._enrollment_reasons.pack(padx=18, pady=8)
        actions = ttk.Frame(form); actions.pack(pady=(6, 16))
        self._capture_button = ttk.Button(
            actions, text="Capturar", command=self._request_enrollment_capture,
        )
        if self._manual_enrollment_capture:
            self._capture_button.pack(side="left", padx=6)
        ttk.Button(actions, text="Cancelar", command=self._cancel).pack(
            side="left", padx=6
        )
        form.protocol("WM_DELETE_WINDOW", self._cancel)

    def _request_enrollment_capture(self) -> None:
        callback = self._on_capture_enrollment
        if callback is None:
            return
        if callback() and self._capture_button is not None:
            self._capture_button.configure(state="disabled")

    def _close_enrollment_form(self) -> None:
        form = getattr(self, "_form", None)
        self._form = None
        self._enrollment_video = None
        self._enrollment_video_item = None
        self._enrollment_guide_text = None
        self._enrollment_progress = None
        self._enrollment_quality = None
        self._enrollment_reasons = None
        self._capture_button = None
        if form is not None:
            try:
                form.grab_release()
            except Exception:
                pass
            try:
                if form.winfo_exists():
                    form.destroy()
            except Exception:
                pass

    def _enter_registration_form_state(self) -> None:
        self._registration_form_open = True
        self._set_camera_switch_allowed(False)
        self._clear_pending_popups()
        self._on_registration_form_state(True)
        if self._identification is not None:
            self._identification.suspend()
        if self._identification_popup is not None:
            self._dismiss_identification_popup("form_open")
        self.register_button.configure(state="disabled")

    def _leave_registration_form_state(self, *, resume: bool) -> None:
        self._clear_pending_popups()
        self._registration_form_open = False
        if resume:
            self._set_camera_switch_allowed(True)
        if resume:
            self._on_registration_form_state(False)
        if resume:
            self._enrollment_active = False
            if self._identification is not None:
                self._identification.resume()
            self.register_button.configure(state="normal")

    def _set_camera_switch_allowed(self, allowed: bool) -> None:
        for name in ("camera_button", "camera_search_button", "camera_change_button"):
            button = getattr(self, name, None)
            if button is not None: button.configure(state="normal" if allowed else "disabled")
        retry = getattr(self, "camera_retry_button", None)
        if retry is not None and not allowed: retry.configure(state="disabled")

    def _dismiss_identification_popup(self, reason: str) -> None:
        if self._identification_popup is None:
            return
        reasoned = getattr(self._identification_popup, "dismiss_with_reason", None)
        if reasoned is not None:
            reasoned(reason)
        else:
            self._identification_popup.dismiss()

    def _cancel(self) -> None:
        """
        Cancel an active enrollment workflow.
        """

        self._on_cancel()
        self._clear_pending_popups()
        self._enrollment_active = True
        if self._identification is not None:
            self._identification.suspend()

        self.register_button.configure(state="disabled")

        self.cancel_button.configure(
            state="disabled"
        )

    def close(self) -> None:
        """
        Close UI and request resource cleanup.
        """
        if self._closing:return
        self._closing = True
        web_shutdown=getattr(self,"_web_shutdown",None)
        if web_shutdown is not None:
            try:web_shutdown()
            except Exception:pass
        coordinator=getattr(self,"_dashboard_refresh_coordinator",None)
        if coordinator is not None:coordinator.close()
        frame_close=getattr(self,"_presentation_frame_close",None)
        if frame_close is not None:
            try:frame_close()
            except Exception:pass
        self._close_photo_capture()
        enrollment_after_id = getattr(self, "_enrollment_resume_after_id", None)
        if enrollment_after_id is not None:
            try: self.root.after_cancel(enrollment_after_id)
            except Exception: pass
            self._enrollment_resume_after_id = None
        health_after_id = getattr(self,"_system_health_after_id",None)
        if health_after_id is not None:
            try:self.root.after_cancel(health_after_id)
            except Exception:pass
            self._system_health_after_id=None
        audit_after_id=getattr(self,"_audit_after_id",None)
        if audit_after_id is not None:
            try:self.root.after_cancel(audit_after_id)
            except Exception:pass
            self._audit_after_id=None
        report_after_id = getattr(self, "_report_after_id", None)
        if report_after_id is not None:
            try: self.root.after_cancel(report_after_id)
            except Exception: pass
            self._report_after_id = None
        self._clear_pending_popups()
        if self._identification_popup is not None:
            self._identification_popup.close()

        self._on_close()

        if (
            self._form is not None
            and self._form.winfo_exists()
        ):
            try:
                self._form.grab_release()
            except tk.TclError:
                pass

            self._form.destroy()

        self._form = None
        self._photo = None

        if self.root.winfo_exists():
            self.root.destroy()

    def _schedule_system_health(self) -> None:
        if self._closing or self._system_health_controller is None:return
        try:
            dto=self._system_health_controller.snapshot()
            self.system_health.configure(text=f"Estado del sistema: {dto.overall} | FPS móvil: {dto.fps} | Memoria: {dto.memory} | Uptime: {dto.uptime} | Procesamiento: {dto.processing_latency} | Inferencia: {dto.inference_latency}")
        except Exception:self.system_health.configure(text="Estado del sistema: no disponible")
        self._system_health_after_id=self.root.after(int(self._system_health_refresh_seconds*1000),self._schedule_system_health)

    def _schedule_audit_summary(self) -> None:
        if self._closing or self._audit_controller is None:return
        try:
            dto=self._audit_controller.summary()
            self.audit_summary.configure(text=f"Auditoría: {dto.total} eventos | OK: {dto.successes} | Fallos: {dto.failures}")
        except Exception:self.audit_summary.configure(text="Auditoría: N/D")
        self._audit_after_id=self.root.after(int(self._audit_refresh_seconds*1000),self._schedule_audit_summary)


def _number(value: float | None, suffix: str = "") -> str:
    return "N/D" if value is None else f"{value:.1f}{suffix}"


def _value(value: float | str | None) -> str:
    if value is None:
        return "N/D"
    return f"{value:.3f}" if isinstance(value, float) else str(value)


def _enrollment_checklist(accepted: int, target: int) -> str:
    labels = (
        "Frontal", "Ligero giro izquierda", "Ligero giro derecha",
        "Frontal estable", "Natural",
    )
    return "\n".join(
        f"{'✓' if index < accepted else '○'} "
        f"{labels[index] if index < len(labels) else f'Muestra {index + 1}'}"
        for index in range(target)
    )


def _enrollment_progress_bar(accepted: int, target: int) -> str:
    filled = 0 if target <= 0 else round(10 * accepted / target)
    return f"[{'█' * filled}{'-' * (10 - filled)}] {accepted}/{target}"


def _capture_quality_state(score: float | None) -> str:
    if score is None: return "NO EVALUADA"
    if score >= 75: return "APROBADA"
    if score >= 50: return "MEJORABLE"
    return "INSUFICIENTE"


def _enrollment_reason(reason: str) -> str:
    return {
        "no_face": "Centre su rostro",
        "multiple_faces": "Se detectaron varios rostros",
        "face_too_small": "Rostro demasiado lejos; acérquese a la cámara",
        "low_interocular_distance": "Acérquese a la cámara",
        "partially_visible": "Rostro parcialmente fuera del cuadro",
        "face_off_center": "Centre su rostro",
        "too_dark": "Iluminación insuficiente",
        "too_bright": "Iluminación excesiva",
        "low_contrast": "Contraste insuficiente",
        "blurry": "Rostro borroso; no se mueva",
        "pose_not_requested": "Siga la pose indicada",
        "too_soon": "No se mueva; espere un momento",
        "near_duplicate": "Cambie ligeramente la pose",
        "low_quality": "Mejore la iluminación y mantenga el rostro estable",
        "alignment_failed": "Centre el rostro frente a la cámara",
        "quality_below_enrollment_minimum": "Calidad insuficiente",
    }.get(reason, reason.replace("_", " ").capitalize())
