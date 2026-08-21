"""Tkinter presentation layer; it never owns biometric arrays or model objects."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
import math
import logging
import time
import webbrowser
from datetime import datetime
from pathlib import Path
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
from src.ui.operational_semantics import (
    OperationalPresentationState, operational_presentation_state, operational_title,
)

LOGGER = logging.getLogger(__name__)
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


class RegistrationFlowState(str, Enum):
    """Authoritative lifecycle for the single registration flow."""

    IDLE = "idle"
    CIVIL_FORM = "civil_form"
    STARTING_ENROLLMENT = "starting_enrollment"
    ENROLLMENT = "enrollment"
    PROFILE_PHOTO = "profile_photo"


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


class _ControlState:
    """Non-visual state holder for enrollment controls owned by modal workflows."""

    def __init__(self, state: str) -> None:
        self.state = state

    def configure(self, **values: object) -> None:
        if "state" in values:
            self.state = str(values["state"])


class LocalFaceTkApp:
    # RC22 replaces the former "Candidato experimental", "Métricas de sesión"
    # and "Historial temporal" cards with the integrated registration and the
    # three operational panels.  Keep these names documented for compatibility
    # with older dashboard audits; they are not rendered as duplicate widgets.
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
        on_replace_face: Callable[[str], bool] | None = None,
        on_reactivate_person: Callable[[str], bool] | None = None,
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
        web_dashboard_local_url: str | None = None,
        web_dashboard_lan_url: str | None = None,
        browser_open: Callable[[str], object] = webbrowser.open,
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
        self._on_replace_face = on_replace_face
        self._on_reactivate_person = on_reactivate_person
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
        self._registration_flow_state = RegistrationFlowState.IDLE
        self._enrollment_active = False
        self._registration_form_open = False
        self._pending_enrollment_person_id: str | None = None
        self._registration_submit_button: Any | None = None
        self._awaiting_profile_choice = False
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
        self._web_dashboard_local_url = web_dashboard_local_url
        self._web_dashboard_lan_url = web_dashboard_lan_url
        self._browser_open = browser_open
        self._web_shutdown = None
        self._presentation_frame_close = None
        self._audit_after_id = None
        self._dashboard_refresh_coordinator = None
        self._fullscreen = False
        self._professional_photos: list[Any] = []
        self._camera_source_name = "N/D"
        self._camera_source_type = "N/D"
        self._database_state = "N/D"
        self._video_resolution = "N/D"

        self._form: tk.Toplevel | None = None
        self._enrollment_video: Any | None = None
        self._enrollment_video_item: Any | None = None
        self._enrollment_guide_text: Any | None = None
        self._enrollment_heading: Any | None = None
        self._enrollment_progress: Any | None = None
        self._enrollment_quality: Any | None = None
        self._enrollment_reasons: Any | None = None
        self._capture_button: Any | None = None
        self._photo_capture_window: Any | None = None
        self._photo_capture_preview: Any | None = None
        self._photo_capture_status: Any | None = None
        self._photo_capture_quality: Any | None = None
        self._photo_capture_image: Any | None = None
        self._photo_replace_confirmed_person_id: str | None = None
        self._photo_replace_declined_person_id: str | None = None
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
        root.configure(background="#07111D")
        style=ttk.Style(root)
        # The clam engine honors background/border mappings consistently on
        # Linux; the platform theme otherwise turns navigation buttons gray.
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame",background="#07111D")
        style.configure("TLabel",background="#07111D",foreground="#F3F6F9")
        style.configure("TLabelframe",background="#10263A",foreground="#F3F6F9",bordercolor="#23445E")
        style.configure("TLabelframe.Label",background="#07111D",foreground="#22D3D3",font=("TkDefaultFont",10,"bold"))
        style.configure("Title.TLabel",font=("TkDefaultFont",18,"bold"),foreground="#FFFFFF")
        style.configure("Institution.TLabel",font=("TkDefaultFont",12,"bold"),foreground="#4FD1C5")
        style.configure("Subtitle.TLabel",font=("TkDefaultFont",10),foreground="#AFC1D2")
        style.configure("HeaderStatus.TLabel",font=("TkDefaultFont",9),foreground="#D7E2EC")
        style.configure("Clock.TLabel",font=("TkDefaultFont",10,"bold"),foreground="#FFFFFF")
        style.configure("Sidebar.TFrame",background="#081625")
        style.configure("SidebarText.TLabel",background="#081625",foreground="#9CB0C3")
        style.configure("Sidebar.TButton",padding=(12,7),anchor="w",relief="flat",
                        background="#081625",foreground="#D7E2EC",borderwidth=0)
        style.configure("Active.Sidebar.TButton",padding=(12,7),anchor="w",relief="flat",
                        background="#185ABD",foreground="#FFFFFF",borderwidth=0)
        style.map("Sidebar.TButton",background=[("active","#12345A"),("disabled","#081625")],
                  foreground=[("active","#FFFFFF"),("disabled","#71869A")])
        style.map("Active.Sidebar.TButton",background=[("active","#2474DA")])
        for name,color in (("Primary","#2583FF"),("Success","#20D67A"),
                           ("Warning","#FF9800"),("Danger","#EF4444"),
                           ("Secondary","#19344A")):
            style.configure(f"{name}.TButton",background=color,foreground="#F3F6F9",
                            padding=(12,7),relief="flat",borderwidth=0)
            style.map(f"{name}.TButton",background=[("active","#286CA8"),
                                                     ("disabled","#24384A")])
        style.configure("Card.TFrame",background="#10263A",relief="solid",borderwidth=1,
                        bordercolor="#23445E",lightcolor="#23445E",darkcolor="#23445E")
        style.configure("CardTitle.TLabel",background="#10263A",foreground="#F3F6F9",
                        font=("TkDefaultFont",10,"bold"))
        style.configure("CardText.TLabel",background="#10263A",foreground="#F3F6F9")
        style.configure("CardBody.TFrame",background="#10263A")
        style.configure("Treeview",background="#0D2033",fieldbackground="#0D2033",foreground="#F3F6F9",rowheight=40,borderwidth=0)
        style.configure("Treeview.Heading",background="#10263A",foreground="#F3F6F9",relief="flat")
        for name,color in (("Cyan","#22D3D3"),("Blue","#2583FF"),("Green","#20D67A"),
                           ("Orange","#FF9800"),("Red","#EF4444"),("Purple","#9854FF")):
            style.configure(f"{name}.Kpi.TFrame",background="#10263A",relief="solid",
                            borderwidth=1,bordercolor=color,lightcolor=color,darkcolor=color)
            style.configure(f"{name}.KpiTitle.TLabel",background="#10263A",foreground=color,
                            font=("TkDefaultFont",8,"bold"))
            style.configure(f"{name}.KpiValue.TLabel",background="#10263A",foreground="#FFFFFF",
                            font=("TkDefaultFont",18,"bold"))
            style.configure(f"{name}.KpiSubtitle.TLabel",background="#10263A",foreground="#9CB0C3",
                            font=("TkDefaultFont",8))
        root.geometry(
            f"{max(1280, int(settings.get('initial_width', 1280)))}x"
            f"{int(settings.get('initial_height', 720))}"
        )
        root.minsize(
            int(settings.get("minimum_width", 820)),
            int(settings.get("minimum_height", 600)),
        )
        root.protocol("WM_DELETE_WINDOW", self.close)
        sidebar_width=200 if root.winfo_screenwidth()>=1600 else 190
        root.columnconfigure(0, weight=0, minsize=sidebar_width)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(2, weight=1)
        sidebar=ttk.Frame(root,style="Sidebar.TFrame",padding=(10,12),width=sidebar_width)
        sidebar.grid(row=0,column=0,rowspan=4,sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar_items=(
            ("▦","Dashboard",lambda:None,True),("◉","Cámara",on_camera,True),
            ("♙","Personas",on_people,self._can("VIEW_PEOPLE")),
            ("✓","Asistencia",on_attendance_history,self._can("VIEW_ATTENDANCE")),
            ("◷","Historial",on_detection_history,self._can("VIEW_DETECTION_HISTORY")),
            ("▤","Reportes",on_reports,self._can("VIEW_REPORTS")),
            ("▣","Backups",on_backup,self._can("BACKUP") or self._can("RESTORE")),
            ("◌","Auditoría",on_audit,self._can("VIEW_AUDIT")),
            ("⌁","Diagnóstico",on_system_health,self._can("VIEW_SYSTEM_HEALTH")),
            ("⚙","Configuración",on_configuration,self._can("VIEW_SETTINGS")),
        )
        self.sidebar_buttons={}
        for index,(icon,label,command,allowed) in enumerate(sidebar_items):
            navigate=(lambda key=label,callback=command:
                      self._activate_sidebar(key,callback))
            button=ttk.Button(sidebar,text=f"{icon}  {label}",command=navigate,
                style="Active.Sidebar.TButton" if index==0 else "Sidebar.TButton",
                state="normal" if command is not None and allowed else "disabled")
            button.pack(fill="x",pady=2);self.sidebar_buttons[label]=button
        self.camera_button=self.sidebar_buttons["Cámara"]
        self.people_button=self.sidebar_buttons["Personas"]
        self.backup_button=self.sidebar_buttons["Backups"]
        self.audit_button=self.sidebar_buttons["Auditoría"]
        self.health_button=self.sidebar_buttons["Diagnóstico"]
        sidebar_institution=ttk.Frame(sidebar,style="Sidebar.TFrame")
        sidebar_institution.pack(side="bottom",fill="x",pady=(10,0))
        self.sidebar_logo_label=ttk.Label(
            sidebar_institution,text="Instituto Superior\nTecnológico Simón Bolívar",
            style="SidebarText.TLabel",justify="left")
        self.sidebar_logo_label.pack(anchor="w")
        header = ttk.Frame(root, padding=(14, 6)); header.grid(row=0, column=1, sticky="ew")
        header.columnconfigure(1, weight=1)
        header.columnconfigure(2, weight=1)
        self._institutional_logo=None
        logo_path=Path(__file__).resolve().parent/"assets"/"LOGO-MODIFICADO-SUPERIOR-izq-1.png"
        logo_label=ttk.Label(header,text="ISTSB",style="Institution.TLabel")
        if logo_path.is_file():
            try:
                logo=tk.PhotoImage(file=str(logo_path));factor=max(1,math.ceil(logo.height()/54))
                self._institutional_logo=logo.subsample(factor,factor)
                logo_label.configure(image=self._institutional_logo,text="")
                self.sidebar_logo_label.configure(image=self._institutional_logo,text="")
            except Exception:
                pass
        logo_label.grid(row=0,column=0,rowspan=2,sticky="w",padx=(0,12))
        ttk.Label(header, text="FASTVISION AI", style="Title.TLabel").grid(row=0, column=1, sticky="w")
        ttk.Label(header,text="Sistema Inteligente de Reconocimiento y Asistencia",style="Subtitle.TLabel").grid(row=1,column=1,sticky="w")
        self.header_camera=ttk.Label(
            header,text="●  Cámara activa\nN/D",justify="left",anchor="w",
            style="HeaderStatus.TLabel")
        self.header_camera.grid(row=0,column=2,rowspan=2,sticky="e",padx=(10,14))
        self.header_state=self.header_camera
        self.header_recognition=ttk.Label(
            header,text="●  Reconocimiento\nN/D",justify="left",anchor="w",
            style="HeaderStatus.TLabel")
        self.header_recognition.grid(row=0,column=3,rowspan=2,sticky="e",padx=(0,14))
        self.header_clock=ttk.Label(header,text="",style="Clock.TLabel",justify="right")
        self.header_clock.grid(row=0,column=4,rowspan=2,sticky="e")
        self._update_header_clock()
        statistics = ttk.Frame(root,padding=(10,4));statistics.grid(row=1,column=1,sticky="ew")
        for column in range(6):statistics.columnconfigure(column,weight=1,uniform="stats")
        self.stat_values={}
        stat_items=(("present","◉  PERSONAS PRESENTES","Blue","En tiempo real"),
                    ("registered","♙  PERSONAS REGISTRADAS","Green","Base civil"),
                    ("biometrics","◇  IDENTIDADES BIOMÉTRICAS","Purple","Galería activa"),
                    ("entries","↳  ENTRADAS HOY","Blue","Asistencia"),
                    ("late","!  RETRASOS HOY","Orange","Jornada actual"),
                    ("without_face","○  PERSONAS SIN ROSTRO","Red","Pendientes"))
        for column,(key,label,color,subtitle) in enumerate(stat_items):
            card=ttk.Frame(statistics,padding=(8,6),style=f"{color}.Kpi.TFrame")
            card.grid(row=0,column=column,sticky="nsew",padx=3,pady=2)
            ttk.Label(card,text=label,style=f"{color}.KpiTitle.TLabel",anchor="center").pack(fill="x")
            value=ttk.Label(card,text="N/D",style=f"{color}.KpiValue.TLabel",anchor="center")
            value.pack(fill="x")
            ttk.Label(card,text=subtitle,style=f"{color}.KpiSubtitle.TLabel",anchor="center").pack(fill="x")
            self.stat_values[key]=value

        body = ttk.Frame(root, padding=(10, 4)); body.grid(row=2, column=1, sticky="nsew")
        body.columnconfigure(0, weight=65); body.columnconfigure(1, weight=35)
        body.rowconfigure(0, weight=3);body.rowconfigure(1,weight=2)
        # Keep the existing live-video Canvas (formerly captioned "VIDEO EN VIVO").
        video_card = ttk.Frame(body, style="Card.TFrame", padding=8)
        video_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8),pady=(0,6))
        video_card.columnconfigure(0, weight=1); video_card.rowconfigure(1, weight=1)
        ttk.Label(video_card,text="▦  VIDEO EN TIEMPO REAL",style="CardTitle.TLabel").grid(
            row=0,column=0,sticky="w",pady=(0,7))
        self.video = tk.Canvas(video_card, background="#07111D", highlightthickness=0)
        self.video.grid(row=1, column=0, sticky="nsew")
        self._video_item = self.video.create_image(0, 0, anchor="center")
        self._video_status_item=self.video.create_text(
            20,20,anchor="nw",text="CÁMARA DESCONECTADA\nSeleccione una cámara desde el menú Cámara.",
            fill="#A9BACB",font=("TkDefaultFont",12,"bold"),
        )
        self._video_meta_item=self.video.create_text(
            20,280,anchor="sw",text="FPS: N/D · Resolución: N/D",fill="#1FD6D0",
            font=("TkDefaultFont",9,"bold"),
        )
        video_metrics=ttk.Frame(video_card,style="CardBody.TFrame")
        video_metrics.grid(row=2,column=0,sticky="ew",pady=(7,0))
        for column in range(5):video_metrics.columnconfigure(column,weight=1,uniform="video_metrics")
        self.video_resolution=ttk.Label(video_metrics,text="RESOLUCIÓN\nN/D",style="CardText.TLabel")
        self.video_quality=ttk.Label(video_metrics,text="CALIDAD DE CAPTURA\nN/D",style="CardText.TLabel")
        self.video_state=ttk.Label(video_metrics,text="ESTADO\nN/D",style="CardText.TLabel")
        self.video_samples=ttk.Label(video_metrics,text="MUESTRAS\n—",style="CardText.TLabel")
        self.video_recognition=ttk.Label(video_metrics,text="RECONOCIMIENTO\nN/D",style="CardText.TLabel")
        for column,widget in enumerate((self.video_resolution,self.video_quality,self.video_state,
                                        self.video_samples,self.video_recognition)):
            widget.grid(row=0,column=column,sticky="nsew",padx=3)

        right_column=ttk.Frame(body)
        right_column.grid(row=0,column=1,sticky="nsew",pady=(0,6))
        right_column.columnconfigure(0,weight=1);right_column.rowconfigure(0,weight=1)
        right_column.rowconfigure(1,weight=1)
        main_health=ttk.Frame(right_column,style="Card.TFrame",padding=12)
        main_health.grid(row=0,column=0,sticky="nsew",pady=(0,8))
        ttk.Label(main_health,text="⌁  ESTADO DEL SISTEMA",style="CardTitle.TLabel").pack(
            fill="x",pady=(0,8))
        self.main_system_status=ttk.Label(
            main_health,
            text=("Cámara                  ● N/D\n"
                  "Reconocimiento     ● N/D\n"
                  "Base de datos       ● N/D\n"
                  "Almacenamiento      N/D\n"
                  "Dashboard Web       ● N/D"),
            style="CardText.TLabel",justify="left",
        )
        self.main_system_status.pack(fill="both",expand=True)
        camera_card_main=ttk.Frame(right_column,style="Card.TFrame",padding=12)
        camera_card_main.grid(row=1,column=0,sticky="nsew")
        ttk.Label(camera_card_main,text="▣  ESTADO DE LA CÁMARA",
                  style="CardTitle.TLabel").pack(fill="x",pady=(0,8))
        self.main_camera_status=ttk.Label(
            camera_card_main,
            text="Estado        N/D\nNombre       N/D\nResolución   N/D\nFPS              N/D",
            style="CardText.TLabel",justify="left")
        self.main_camera_status.pack(fill="both",expand=True)
        self.main_camera_button=ttk.Button(
            camera_card_main,text="▣  CAMBIAR CÁMARA",command=on_camera or (lambda:None),
            style="Primary.TButton",state="normal" if on_camera is not None else "disabled")
        self.main_camera_button.pack(fill="x",pady=(8,0))

        side = ttk.Frame(body); side.grid(row=1,column=0,columnspan=2,sticky="nsew")
        for column in range(3):side.columnconfigure(column,weight=1,uniform="lower")
        side.rowconfigure(0,weight=1)
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

        recognition_card=ttk.Frame(side,style="Card.TFrame",padding=8)
        recognition_card.grid(row=0,column=0,sticky="nsew",padx=(0,4))
        ttk.Label(recognition_card,text="◷  RECONOCIMIENTOS RECIENTES",
                  style="CardTitle.TLabel").pack(fill="x",pady=(0,6))
        self.recent_recognition_table=ttk.Treeview(recognition_card,
            columns=("name","time","similarity","state"),show=("tree","headings"),height=4)
        self.recent_recognition_table.heading("#0",text="Foto")
        self.recent_recognition_table.column("#0",width=48,stretch=False,anchor="center")
        for key,label in (("name","Nombre"),("time","Hora"),("similarity","Similitud"),("state","Estado")):
            self.recent_recognition_table.heading(key,text=label)
        self.recent_recognition_table.tag_configure("IDENTIFICADO",foreground="#20D67A")
        self.recent_recognition_table.tag_configure("NO EVALUADO",foreground="#FF9800")
        self.recent_recognition_table.tag_configure("NO REGISTRADA",foreground="#EF4444")
        self.recent_recognition_table.pack(fill="both",expand=True)
        ttk.Button(recognition_card,text="Ver todos",command=on_detection_history or (lambda:None)).pack(anchor="e",pady=(3,0))

        today_card=ttk.Frame(side,style="Card.TFrame",padding=8)
        today_card.grid(row=0,column=1,sticky="nsew",padx=4)
        ttk.Label(today_card,text="▣  ASISTENCIA DE HOY",style="CardTitle.TLabel").pack(
            fill="x",pady=(0,6))
        self.recent_attendance_table=ttk.Treeview(today_card,
            columns=("name","in","out","state"),show="headings",height=4)
        for key,label in (("name","Nombre"),("in","Entrada"),("out","Salida"),("state","Estado")):
            self.recent_attendance_table.heading(key,text=label)
        self.recent_attendance_table.pack(fill="both",expand=True)
        ttk.Button(today_card,text="Ver asistencia completa",command=on_attendance_history or (lambda:None)).pack(anchor="e",pady=(3,0))

        performance=ttk.Frame(side,style="Card.TFrame",padding=9)
        performance.grid(row=0,column=2,sticky="nsew",padx=(4,0))
        ttk.Label(performance,text="⌁  RENDIMIENTO DEL SISTEMA",style="CardTitle.TLabel").pack(
            fill="x",pady=(0,7))
        self.metrics=ttk.Label(performance,text="FPS: N/D\nLatencia: N/D",style="CardText.TLabel")
        self.metrics.pack(anchor="w")
        self.system_health=ttk.Label(performance,text=(
            "CPU: N/D\nMemoria: N/D\nCámara: N/D\nIA: N/D\nVersión: N/D"),style="CardText.TLabel")
        self.system_health.pack(anchor="w",pady=4)
        self.audit_summary=ttk.Label(performance,text="Auditoría: N/D",style="CardText.TLabel")
        self.audit_summary.pack(anchor="w")

        # Compatibility target for existing controller updates. Operational
        # details are rendered in the main system card, not duplicated here.
        operational=ttk.Frame(root)
        self.operational_status=ttk.Label(operational,text=(
            "Cámara: N/D\nBase de datos: N/D\nGalería: 0 · Reconocimiento: Detenido\nAsistencia: Desactivada"),
            wraplength=sidebar_width-34,justify="left")
        self.operational_status.pack(fill="x",anchor="w")

        web_card=ttk.Frame(sidebar,style="Card.TFrame",padding=8)
        web_card.pack(side="bottom",fill="x",pady=(8,0))
        ttk.Label(web_card,text="◎  ACCESO WEB",style="CardTitle.TLabel").pack(anchor="w")
        shown_urls=[item for item in (web_dashboard_local_url,web_dashboard_lan_url) if item]
        ttk.Label(web_card,text="\n".join(shown_urls) if shown_urls else "No disponible",
                  style="CardText.TLabel",justify="left",wraplength=165).pack(anchor="w",pady=(5,0))
        web_actions=ttk.Frame(web_card,style="CardBody.TFrame");web_actions.pack(fill="x",pady=(6,0))
        self.copy_web_url_button=ttk.Button(web_actions,text="COPIAR",command=self.copy_web_dashboard_url,
            state="normal" if shown_urls else "disabled")
        self.copy_web_url_button.pack(side="right")
        self.open_web_url_button=ttk.Button(web_actions,text="ABRIR",command=self.open_web_dashboard,
            state="normal" if web_dashboard_local_url else "disabled")
        self.open_web_url_button.pack(side="left")

        self.diagnostic_card = ttk.LabelFrame(technical, text="Diagnóstico de calidad", padding=6)
        self.diagnostic_values = ttk.Label(self.diagnostic_card, text="N/D")
        self.diagnostic_values.pack(anchor="w")
        self.diagnostic_card.pack(fill="x",padx=10,pady=4)

        footer=ttk.Frame(root,padding=(14,5));footer.grid(row=3,column=1,sticky="ew")
        footer.columnconfigure(1,weight=1)
        ttk.Label(footer,text="FastVisionAI v2.0",
                  style="Subtitle.TLabel").grid(row=0,column=0,sticky="w")
        ttk.Label(footer,text="Instituto Superior Tecnológico Simón Bolívar",
                  style="Subtitle.TLabel").grid(row=0,column=2,sticky="e")

        # Enrollment state remains part of the controller, without adding a second
        # visible navigation/action bar to the professional dashboard.
        self._open_registration_form = self.open_form
        self.register_button = _ControlState(
            "normal" if self._can("ENROLL_PERSON") else "disabled"
        )
        self.cancel_button = _ControlState("disabled")
        # Legacy condition retained conceptually: if self._system_health_controller is not None,
        # RC13 reads it through the single professional dashboard coordinator.
        if self._audit_controller is not None:
            self._audit_after_id=self.root.after(0,self._schedule_audit_summary)
        root.bind("<F11>",self.toggle_fullscreen)
        root.bind("<Escape>",self.exit_fullscreen)

    def _activate_sidebar(self, label: str, callback: Callable[[], None] | None) -> None:
        """Select one sidebar destination and invoke its existing controller."""
        for key, button in self.sidebar_buttons.items():
            button.configure(
                style="Active.Sidebar.TButton" if key == label else "Sidebar.TButton"
            )
        if callback is not None:
            callback()

    def _render_main_system_status(self) -> None:
        dashboard=getattr(self,"_dashboard",None)
        camera_state="N/D" if dashboard is None else dashboard.system.camera_state
        recognition="N/D" if dashboard is None else dashboard.system.recognition_state
        metrics=None if dashboard is None else dashboard.metrics
        fps="N/D" if metrics is None else _number(metrics.effective_capture_fps)
        web_state="En línea" if getattr(self,"_web_dashboard_local_url",None) else "N/D"
        database_state=getattr(self,"_database_state","N/D")
        if hasattr(self,"main_system_status"):
            self.main_system_status.configure(text=(
                f"Cámara                  ● {camera_state}\n"
                f"Reconocimiento     ● {recognition}\n"
                f"Base de datos       ● {database_state}\n"
                "Almacenamiento      N/D\n"
                f"Dashboard Web       ● {web_state}"))
        if hasattr(self,"main_camera_status"):
            self.main_camera_status.configure(text=(
                f"Estado        {camera_state}\n"
                f"Nombre       {getattr(self,'_camera_source_name','N/D')}\n"
                f"Resolución   {getattr(self,'_video_resolution','N/D')}\n"
                f"FPS              {fps}"))

    def show_monitoring(self, dto: MonitoringDTO) -> None:
        self.latest_monitoring = dto
        view = monitoring_text(dto)
        dashboard = getattr(self, "_dashboard", None)
        operational = None
        if dashboard is None:
            headline = view.headline
        else:
            operational = operational_presentation_state(
                camera_state=dashboard.system.camera_state,
                frame_available=(dashboard.metrics.frames_received > 0),
                monitoring=dto,
                gallery_identity_count=dashboard.gallery.identities,
            )
            headline = operational_title(operational) or view.headline

        self.status.configure(text=headline)
        self.candidate.configure(text=view.candidate)
        self.similarity.configure(
            text=f"Similitud: {view.similarity}"
        )
        self.decision.configure(text=view.decision)
        self.quality.configure(
            text=f"Score: {view.quality}"
        )
        if hasattr(self,"video_quality"):
            self.video_quality.configure(text=f"CALIDAD DE CAPTURA\n{view.quality}")
            self.video_state.configure(text=f"ESTADO\n{headline}")
            recognition_state=("N/D" if dashboard is None else
                               dashboard.system.recognition_state)
            self.video_recognition.configure(text=f"RECONOCIMIENTO\n{recognition_state}")

        self.register_button.configure(
            state="normal"
            if dto.registration_enabled
            else "disabled"
        )
        if self._registration_form_open:
            self.register_button.configure(state="disabled")
            return
        if self._enrollment_active:
            if getattr(self, "_awaiting_profile_choice", False):
                self.register_button.configure(state="disabled")
                return
            if dto.state is not UIState.MONITORING:
                self.register_button.configure(state="disabled")
                return
            self._enrollment_active = False
            self._registration_flow_state = RegistrationFlowState.IDLE
            self._pending_enrollment_person_id = None
            self._close_enrollment_form()
            self._on_registration_form_state(False)
            if self._identification is not None:
                self._identification.resume()
        if (operational is OperationalPresentationState.GALLERY_UNREGISTERED
                and self._identification is not None
                and self._identification_popup is not None):
            popup = self._identification.observe_empty_gallery(dto)
            self._identification_popup.show(popup)
            return
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
        self.latest_enrollment_event = dto
        if hasattr(self, "_form") and self._form is None:
            self._form = tk.Toplevel(self.root)
            self._form.protocol("WM_DELETE_WINDOW", self._cancel)
            self._show_enrollment_capture(self._form)
            LOGGER.info(
                "face_enrollment_window_opened workflow_state=ENROLLMENT "
                "accepted_samples=%d target_samples=%d",
                dto.accepted_samples, dto.target_samples,
            )
        if (getattr(self, "_registration_flow_state", None)
                is RegistrationFlowState.STARTING_ENROLLMENT
                and self._form is not None
                and getattr(self, "_enrollment_video", None) is None):
            self._show_enrollment_capture(self._form)
        self._registration_flow_state = RegistrationFlowState.ENROLLMENT
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
                text=(f"Muestras: {dto.accepted_samples} / {dto.target_samples} · "
                      f"Paso actual: {min(dto.accepted_samples+1,dto.target_samples)} de {dto.target_samples}\n"
                      f"{_enrollment_progress_bar(dto.accepted_samples, dto.target_samples)}")
            )
        if hasattr(self,"video_samples"):
            self.video_samples.configure(
                text=f"MUESTRAS\n{dto.accepted_samples} / {dto.target_samples}")
        if getattr(self,"_enrollment_heading",None) is not None:
            self._enrollment_heading.configure(text=(
                f"Paso {min(dto.accepted_samples+1,dto.target_samples)}/{dto.target_samples} — "
                f"{dto.instruction}"))
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
        self.latest_enrollment_event = dto
        self._registration_flow_state = RegistrationFlowState.ENROLLMENT
        self._pending_enrollment_person_id = dto.person_id
        self._enrollment_active = True
        self._registration_form_open = False
        self.status.configure(text=dto.message)
        self.candidate.configure(text=dto.display_name)

        if getattr(self, "_profile_photo_after_enrollment", False) and self._form is not None:
            self._awaiting_profile_choice = True
            form = self._form
            for child in form.winfo_children(): child.destroy()
            form.title("REGISTRO FACIAL COMPLETADO")
            form.configure(background="#07111D")
            completed=ttk.Frame(form,style="Card.TFrame",padding=24)
            completed.pack(fill="both",expand=True,padx=24,pady=24)
            ttk.Label(completed,text="✓ REGISTRO FACIAL COMPLETADO",
                      style="Title.TLabel").pack(pady=(35,12))
            ttk.Label(completed,text=(f"{dto.templates_registered}/5 muestras\n\n"
                      "Se guardaron las muestras biométricas correctamente.\n\n"
                      "Ahora puede tomar una fotografía para el perfil de la persona."),
                      style="CardText.TLabel",justify="center").pack(pady=12)
            actions = ttk.Frame(completed,style="CardBody.TFrame");actions.pack(pady=18)
            ttk.Button(actions,text="CONTINUAR A FOTO DE PERFIL",style="Primary.TButton",
                       command=lambda:self._continue_profile_photo(dto.person_id)).pack(
                           side="left",padx=6)
            ttk.Button(actions,text="OMITIR",style="Secondary.TButton",
                       command=self._skip_profile_photo).pack(side="left",padx=6)
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
        self._awaiting_profile_choice = False
        self._close_enrollment_form()
        if self._on_start_photo is None or not self._on_start_photo(person_id):
            self.status.configure(text="No se pudo iniciar la fotografía de perfil.")
            return
        self._registration_flow_state = RegistrationFlowState.PROFILE_PHOTO

    def _skip_profile_photo(self) -> None:
        self._awaiting_profile_choice = False
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
        without_face = dto.template_count == 0 and dto.person_status == "ACTIVE"
        disabled = dto.person_status == "DISABLED"
        form.title("Persona sin rostro" if without_face else "Persona deshabilitada"
                   if disabled else "Conflicto de registro")
        photo = "Disponible" if dto.thumbnail_available else "No disponible"
        samples = (str(dto.template_count) if dto.template_count else "No disponibles")
        ttk.Label(
            form,
            text=(("PERSONA SIN ROSTRO REGISTRADO" if without_face else
                   "PERSONA DESHABILITADA" if disabled else "PERSONA YA REGISTRADA")+"\n\n"
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
        if dto.can_add_samples and self._on_replace_face is not None:
            ttk.Button(actions, text="REGISTRAR / ACTUALIZAR ROSTRO",
                       command=lambda: self._start_conflict_replacement(dto.person_id)).pack(
                           side="left", padx=5)
        if dto.can_reactivate and self._on_reactivate_person is not None:
            ttk.Button(actions, text="REACTIVAR PERSONA",
                       command=lambda: self._reactivate_conflict_person(dto)).pack(
                           side="left", padx=5)
        ttk.Button(actions, text="Cancelar",
                   command=lambda: self._close_conflict_form()).pack(side="left", padx=5)

    def _finish_enrollment_grace(self) -> None:
        self._enrollment_resume_after_id = None
        if self._closing:
            return
        self._enrollment_active = False
        self._registration_flow_state = RegistrationFlowState.IDLE
        self._pending_enrollment_person_id = None
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

    def _start_conflict_replacement(self, person_id: str) -> None:
        if self._on_replace_face is None:
            return
        if self._on_replace_face(person_id):
            self._registration_form_open = False
            self._enrollment_active = True

    def _reactivate_conflict_person(self, dto: EnrollmentConflictDTO) -> None:
        if self._on_reactivate_person is None or not self._on_reactivate_person(dto.person_id):
            self.status.configure(text="No se pudo reactivar la persona.")
            return
        self.show_enrollment_conflict(EnrollmentConflictDTO(
            UIState.ERROR, dto.person_id, "ACTIVE",
            "Persona reactivada. Ahora puede registrar o actualizar su rostro.",
            True, dto.template_count == 0, False, dto.display_name,
            dto.thumbnail_available, dto.template_count, False,
        ))

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

        if (dto.operation is UIErrorCode.ENROLLMENT_ERROR
                and getattr(self, "_registration_flow_state", None)
                is RegistrationFlowState.STARTING_ENROLLMENT):
            # Command-queue acceptance is not enrollment acceptance. Keep the
            # civil form intact until the worker confirms begin_enrollment.
            self._registration_flow_state = RegistrationFlowState.CIVIL_FORM
            self._enrollment_active = False
            self._registration_form_open = True
            self._pending_enrollment_person_id = None
            if self._registration_submit_button is not None:
                self._registration_submit_button.configure(state="normal")
            if messagebox is not None and self._form is not None:
                messagebox.showerror(
                    "No se pudo iniciar la captura", dto.message, parent=self._form,
                )
        elif dto.operation is UIErrorCode.ENROLLMENT_ERROR and not dto.recoverable:
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
        dashboard=getattr(self,"_dashboard",None)
        recognition=("N/D" if dashboard is None else dashboard.system.recognition_state)
        self.header_state.configure(
            text=(f"●  Cámara activa\n{dto.camera_source_name} · {dto.camera_state.title()}")
        )
        if hasattr(self,"header_recognition"):
            self.header_recognition.configure(
                text=f"●  Reconocimiento\n{recognition}")
        self._render_main_system_status()
        if hasattr(self,"_video_status_item"):
            disconnected=dto.camera_state == "disconnected"
            self.video.itemconfigure(
                self._video_status_item,
                text=("CÁMARA DESCONECTADA\nSeleccione una cámara desde el menú Cámara."
                      if disconnected else ""),
            )
        if hasattr(self, "camera_button"):
            self.camera_button.configure(
                state="normal" if dto.camera_switch_allowed else "disabled",
            )
        if hasattr(self,"main_camera_button"):
            self.main_camera_button.configure(
                state="normal" if dto.camera_switch_allowed else "disabled")
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
            if self._closing or self._registration_flow_active():
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
            f"Captura FPS: {_number(metrics.effective_capture_fps)}\n"
            f"Pipeline FPS: {_number(metrics.effective_processing_fps)}\n"
            f"Latencia: {_number(metrics.inference_latency_ms, ' ms')}"
        ))
        self._render_main_system_status()
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

    def selected_web_dashboard_url(self) -> str | None:
        return self._web_dashboard_lan_url or self._web_dashboard_local_url

    def copy_web_dashboard_url(self) -> bool:
        value=self.selected_web_dashboard_url()
        if value is None:return False
        try:
            self.root.clipboard_clear();self.root.clipboard_append(value)
            self.root.update_idletasks();return True
        except Exception:return False

    def open_web_dashboard(self) -> bool:
        if self._web_dashboard_local_url is None:return False
        return self._open_web_url(self._web_dashboard_local_url)

    def _open_web_url(self, value: str | None) -> bool:
        if value is None:return False
        try:return bool(self._browser_open(value))
        except Exception:return False

    def _update_header_clock(self) -> None:
        if self._closing:return
        self.header_clock.configure(
            text=datetime.now().astimezone().strftime("%H:%M:%S\n%d/%m/%Y"))
        self.root.after(1000,self._update_header_clock)

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
        for key,number in (("present",value.people_present),
                           ("entries",value.check_ins_today),("late",value.late_today)):
            self.stat_values[key].configure(text="N/D" if number is None else str(number))
        self.stat_values["biometrics"].configure(text=str(value.gallery_identities))
        self._database_state=value.database_state
        self._render_main_system_status()
        self._professional_photos.clear()
        self.recent_recognition_table.delete(*self.recent_recognition_table.get_children())
        for row in value.recent_recognitions:
            photo=self._dashboard_photo(row.photo);text="Sin fotografía" if photo is None else ""
            state=("IDENTIFICADO" if row.recognition_state == "MATCH" and row.evaluated else
                   "NO REGISTRADA" if row.recognition_state == "UNKNOWN" and row.evaluated else
                   "NO EVALUADO")
            self.recent_recognition_table.insert("","end",text=text,image=photo or "",values=(
                row.display_name,row.local_time,
                "N/D" if row.similarity is None else f"{row.similarity*100:.1f}%",state),
                tags=(state,))
        if not value.recent_recognitions:
            self.recent_recognition_table.insert(
                "","end",values=("No hay reconocimientos recientes.","—","—","—"))
        self.recent_attendance_table.delete(*self.recent_attendance_table.get_children())
        for row in value.recent_attendance:
            photo=self._dashboard_photo(row.photo);text="Sin fotografía" if photo is None else ""
            self.recent_attendance_table.insert("","end",text=text,image=photo or "",values=(
                row.display_name,row.check_in_local or "—",row.check_out_local or "—",row.status))
        if not value.recent_attendance:
            self.recent_attendance_table.insert("","end",values=(
                "No hay registros de asistencia hoy.","—","—","—"))
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

        source_width,source_height=width,height
        self._video_resolution=f"{source_width}×{source_height}"
        if hasattr(self,"video_resolution"):
            self.video_resolution.configure(text=f"RESOLUCIÓN\n{self._video_resolution}")
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
        if hasattr(self,"_video_status_item"):
            self.video.itemconfigure(self._video_status_item,text="")
        if hasattr(self,"_video_meta_item"):
            self.video.coords(self._video_meta_item,12,max(20,available_height-10))
            self.video.itemconfigure(
                self._video_meta_item,text=f"● EN VIVO · Resolución: {source_width}×{source_height}")
        self._render_main_system_status()

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
        self.latest_photo_event = dto
        if getattr(self, "web_only", False):
            return
        if dto.state is UIState.MONITORING:
            self.status.configure(text=dto.message)
            self._close_photo_capture()
            self._photo_replace_confirmed_person_id = None
            self._photo_replace_declined_person_id = None
            self._enrollment_active = False
            self._registration_flow_state = RegistrationFlowState.IDLE
            self._pending_enrollment_person_id = None
            self._set_camera_switch_allowed(True)
            self._on_registration_form_state(False)
            if self._identification is not None:
                self._identification.resume()
            return
        self._registration_flow_state = RegistrationFlowState.PROFILE_PHOTO
        self._enrollment_active = True
        self._set_camera_switch_allowed(False)
        self._clear_pending_popups()
        if self._identification is not None:
            self._identification.suspend()
        if self._identification_popup is not None:
            self._dismiss_identification_popup("photo_capture")
        if self._photo_replace_declined_person_id == dto.person_id:
            return
        if (dto.replace_existing
                and self._photo_replace_confirmed_person_id != dto.person_id):
            confirmed=(messagebox is None or messagebox.askyesno(
                "Reemplazar foto de perfil",
                "Esta persona ya tiene una foto de perfil.\n¿Desea reemplazarla?",
                parent=self.root,
            ))
            if not confirmed:
                self._photo_replace_confirmed_person_id = None
                self._photo_replace_declined_person_id = dto.person_id
                if self._on_cancel_photo is not None:self._on_cancel_photo()
                return
            self._photo_replace_confirmed_person_id = dto.person_id
        if self._photo_capture_window is None:
            window = tk.Toplevel(self.root)
            self._photo_capture_window = window
            window.title("FOTO DE PERFIL")
            window.geometry("760x720")
            window.configure(background="#07111D")
            window.protocol("WM_DELETE_WINDOW", self._cancel_person_photo)
            shell=ttk.Frame(window,style="Card.TFrame",padding=16)
            shell.pack(fill="both",expand=True,padx=14,pady=14)
            self._photo_capture_heading = ttk.Label(
                shell,text="FOTO DE PERFIL",style="Title.TLabel",
            )
            self._photo_capture_heading.pack(pady=(2,5))
            ttk.Label(
                shell,
                text="Ahora puede tomar una fotografía para el perfil de la persona.",
                style="CardText.TLabel",
            ).pack(pady=(0,8))
            self._photo_capture_preview = ttk.Label(
                shell,text="Esperando video",anchor="center",style="CardText.TLabel",
            )
            self._photo_capture_preview.pack(fill="both",expand=True,padx=4,pady=8)
            photo_info=ttk.Frame(shell,style="CardBody.TFrame");photo_info.pack(fill="x")
            self._photo_capture_quality=ttk.Label(
                photo_info,text="Calidad de foto: N/D\nEstado: NO EVALUADA",
                style="CardText.TLabel")
            self._photo_capture_quality.pack(side="left")
            self._photo_capture_stability=ttk.Label(
                photo_info,text="Estabilidad: 0/5",style="CardText.TLabel")
            self._photo_capture_stability.pack(side="right")
            self._photo_capture_status=ttk.Label(
                shell,wraplength=680,style="CardText.TLabel")
            self._photo_capture_status.pack(pady=7)
            photo_actions=ttk.Frame(shell,style="CardBody.TFrame");photo_actions.pack(pady=8)
            self._photo_capture_take = ttk.Button(
                photo_actions,text="TOMAR FOTO",style="Primary.TButton",
                command=lambda: self._on_capture_photo and self._on_capture_photo(),
            )
            self._photo_capture_take.pack(side="left",padx=4)
            self._photo_capture_use = ttk.Button(
                photo_actions,text="USAR ESTA FOTO",style="Success.TButton",
                command=lambda: self._on_confirm_photo and self._on_confirm_photo(),
            )
            self._photo_capture_repeat = ttk.Button(
                photo_actions,text="REPETIR",style="Secondary.TButton",
                command=self._retake_person_photo,
            )
            self._photo_capture_repeat.pack(side="left", padx=4)
            self._photo_capture_use.pack(side="left", padx=4)
            ttk.Button(photo_actions,text="OMITIR",style="Secondary.TButton",
                       command=self._cancel_person_photo).pack(side="left",padx=4)
        self._photo_capture_status.configure(text=dto.message)
        self._photo_capture_heading.configure(
            text="FOTO CAPTURADA" if dto.review else "FOTO DE PERFIL",
        )
        quality = "N/D" if dto.quality_score is None else f"{dto.quality_score:.1f}/100"
        self._photo_capture_quality.configure(
            text=f"Calidad de foto: {quality}\nEstado: {_photo_quality_state(dto.quality_score)}"
        )
        required = dto.stability_required or 5
        self._photo_capture_stability.configure(
            text=f"Estabilidad: {dto.stability_observations}/{required}",
        )
        self._photo_capture_take.configure(
            state="normal" if dto.ready and not dto.review else "disabled",
        )
        self._photo_capture_use.configure(state="normal" if dto.review else "disabled")
        self._photo_capture_repeat.configure(state="normal" if dto.review else "disabled")
        if dto.review and dto.image_bytes:
            visual = ThumbnailDTO(dto.person_id, True, 112, 112, "png", dto.image_bytes)
            payload=thumbnail_to_ppm(
                visual,max_width=600,max_height=430,allow_upscale=True)
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

        form.title("Registro facial")
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
            value=True,
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
                "Persistir galería local después del registro (obligatorio)"
            ),
            variable=persist,
            state="disabled",
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
            if accepted is False:
                if messagebox is not None:
                    messagebox.showerror(
                        "No se pudo iniciar la captura",
                        "El registro facial no pudo encolarse. Inténtelo nuevamente.",
                        parent=form,
                    )
                return
            self._pending_enrollment_person_id = data.person_id
            self._registration_flow_state = RegistrationFlowState.STARTING_ENROLLMENT
            self._registration_submit_button.configure(state="disabled")

        self._registration_submit_button = ttk.Button(
            form,
            text="Iniciar captura guiada",
            command=submit,
        )
        self._registration_submit_button.grid(
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
        """Transform the separate civil form into the shared-camera enrollment UI."""
        for child in form.winfo_children():
            child.destroy()
        self._registration_form_open = False
        self._enrollment_active = True
        self._registration_flow_state = RegistrationFlowState.ENROLLMENT
        form.title("REGISTRO FACIAL")
        form.geometry("820x760")
        form.configure(background="#07111D")
        shell=ttk.Frame(form,style="Card.TFrame",padding=16)
        shell.pack(fill="both",expand=True,padx=14,pady=14)
        ttk.Label(shell,text="REGISTRO FACIAL",style="Title.TLabel").pack(anchor="w")
        ttk.Label(shell,text="① ─ ② ─ ③ ─ ④ ─ ⑤",style="Institution.TLabel").pack(
            anchor="e",pady=(0,4))
        self._enrollment_heading=ttk.Label(
            shell,text="Paso 1/5 — Frontal",style="Institution.TLabel")
        self._enrollment_heading.pack(anchor="w",pady=(0,8))
        self._enrollment_video=tk.Canvas(
            shell,background="#07111D",highlightthickness=1,
            highlightbackground="#23445E",height=430)
        self._enrollment_video.pack(fill="both",expand=True)
        self._enrollment_video_item=self._enrollment_video.create_image(0,0,anchor="center")
        self._enrollment_guide_text=self._enrollment_video.create_text(
            16,16,anchor="nw",text="Centre el rostro y siga la pose indicada",
            fill="#22D3D3",font=("TkDefaultFont",11,"bold"))
        enrollment_metrics=ttk.Frame(shell,style="CardBody.TFrame")
        enrollment_metrics.pack(fill="x",pady=(8,0))
        self._enrollment_quality=ttk.Label(
            enrollment_metrics,text="Calidad: N/D\nEstado: ESPERANDO",style="CardText.TLabel")
        self._enrollment_quality.pack(side="left")
        self._enrollment_progress=ttk.Label(
            enrollment_metrics,
            text=f"Muestras: 0 / {self._enrollment_target_samples}\nProgreso: 0 %",
            style="CardText.TLabel",justify="right")
        self._enrollment_progress.pack(side="right")
        self._enrollment_reasons=ttk.Label(
            shell,text=("INSTRUCCIONES\nMantenga una expresión neutral, buena iluminación "
                        "y siga cada pose: frontal, izquierda, derecha, frontal estable y natural."),
            style="CardText.TLabel",wraplength=740,justify="left")
        self._enrollment_reasons.pack(fill="x",pady=9)
        controls=ttk.Frame(shell,style="CardBody.TFrame");controls.pack(fill="x")
        self._capture_button=ttk.Button(
            controls,text="CAPTURAR MUESTRA",command=self._request_enrollment_capture,
            style="Primary.TButton",
            state="normal" if self._manual_enrollment_capture else "disabled")
        if self._manual_enrollment_capture:
            self._capture_button.pack(side="right",padx=(6,0))
        ttk.Button(controls,text="CANCELAR",command=self._cancel,
                   style="Secondary.TButton").pack(side="right")
        form.protocol("WM_DELETE_WINDOW",self._cancel)

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
        self._enrollment_heading = None
        self._enrollment_progress = None
        self._enrollment_quality = None
        self._enrollment_reasons = None
        self._capture_button = None
        self._registration_submit_button = None
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
        self._registration_flow_state = RegistrationFlowState.CIVIL_FORM
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
            self._registration_flow_state = RegistrationFlowState.IDLE
            self._pending_enrollment_person_id = None
            self._set_camera_switch_allowed(True)
        if resume:
            self._on_registration_form_state(False)
        if resume:
            self._enrollment_active = False
            if self._identification is not None:
                self._identification.resume()
            self.register_button.configure(state="normal")

    def _registration_flow_active(self) -> bool:
        state = getattr(self, "_registration_flow_state", RegistrationFlowState.IDLE)
        return (state is not RegistrationFlowState.IDLE
                or self._registration_form_open or self._enrollment_active)

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


def _photo_quality_state(score: float | None) -> str:
    if score is None:return "NO EVALUADA"
    if score >= 75:return "BUENA"
    if score >= 50:return "MEJORABLE"
    return "BAJA"


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
