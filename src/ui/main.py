"""Composition helpers for the local experimental UI.

The camera/biometric producer runs outside Tk's main thread and passes only safe
DTOs plus a transient RGB presentation frame to :class:`LocalFaceTkApp`. This
module intentionally does not choose a biometric threshold or persist by default.
"""

from __future__ import annotations

import argparse
import json
import logging
import threading
import uuid
from urllib.parse import urlsplit
from enum import Enum
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from src.engine.enrollment import EnrollmentPolicy, EnrollmentService
from src.engine.action_executor import ActionExecutor, ActionExecutorPolicy
from src.engine.decision_orchestrator import (
    DecisionOrchestrator, DecisionOrchestratorPolicy,
)
from src.engine.gallery import FaceGallery, FaceMatcher, MatchPolicy
from src.engine.gallery.persistence import GalleryPersistence
from src.engine.recognition import RecognitionPolicy, RecognitionService
from src.engine.identification_policy import (
    IdentificationPolicy, IdentificationPolicyEngine,
)
from src.engine.stability import StabilityPolicy, StabilityTracker
from src.core.config_manager import PROJECT_ROOT
from src.core.application_events import (
    ApplicationEvent, ApplicationEventBus, ApplicationEventDiagnosticsStore,
    AttendanceRecordedEvent, DetectionEventStoredEvent, PopupDismissedEvent,
)
from src.ui.controller import LocalFaceUIController
from src.ui.enrollment_workflow import LocalEnrollmentWorkflow
from src.ui.live_session import LiveFaceSession
from src.ui.mock_runtime import MockUIRuntimeAdapter
from src.ui.recognition_session import ExperimentalRecognitionSession
from src.ui.runtime_adapter import RealUIRuntimeAdapter
from src.ui.camera_selection_window import CameraSelectionWindow
from src.camera.source_discovery import (
    CameraSelectionController, CameraSourceDiscovery, camera_config_for_source,
    parse_discovery_config, CameraConfigurationPersistence,
    redact_url, CameraSourceType,
)
from src.camera.camera_types import CameraConfig, CameraType, ReconnectConfig
from src.ui.tk_app import LocalFaceTkApp
from src.ui.form_validation import validate_registration_form
from src.ui.contracts import ErrorDTO, UIErrorCode, UIState
from src.ui.people.controller import PeopleManagerController
from src.ui.people.tk_window import PeopleManagerWindow
from src.ui.people.database_controller import DatabasePeopleManagerController
from src.ui.dashboard.config_window import DashboardConfigurationWindow
from src.ui.dashboard.contracts import DashboardConfigurationDTO, DashboardGalleryDTO
from src.ui.dashboard import (
    DashboardRefreshCoordinator, ProfessionalDashboardController,
)
from src.ui.thumbnails import ThumbnailManager
from src.ui.photo_capture import PersonPhotoController
from src.ui.photo_capture import AutomaticPhotoPolicy
from src.ui.video_presentation import VideoPresentation
from src.ui.web_dashboard import (
    LatestPresentationFrameStore, WebDashboardController, WebDashboardServer, detect_lan_ip,
)
from src.ui.web_dashboard.contracts import WebDashboardPolicy
from src.ui.operational_semantics import operational_presentation_state


def _video_presentation_settings(settings: dict[str, object]) -> dict[str, object]:
    camera = settings.get("camera", {})
    if not isinstance(camera, dict): return {}
    presentation = camera.get("presentation", {})
    crop = camera.get("presentation_crop", {})
    presentation = presentation if isinstance(presentation, dict) else {}
    crop = crop if isinstance(crop, dict) else {}
    return {
        "rotation": int(presentation.get("rotation", 0)),
        "mirror_horizontal": bool(presentation.get("mirror_horizontal", False)),
        "crop_enabled": bool(crop.get("enabled", False)),
        "crop_top_percent": float(crop.get("top_percent", 0)),
        "crop_bottom_percent": float(crop.get("bottom_percent", 0)),
        "crop_left_percent": float(crop.get("left_percent", 0)),
        "crop_right_percent": float(crop.get("right_percent", 0)),
    }
from src.ui.identification import (
    IdentificationPopupPolicy, IdentificationPresentationController,
    PeopleThumbnailIdentityInfoProvider,
)
from src.ui.identification.tk_popup import IdentificationPopupWindow
from src.ui.identification import SQLiteThumbnailIdentityInfoProvider
from src.core.person_database import (
    PersonRepository, SQLiteIdentityDataProvider, PersonStatus,
)
from src.ui.person_enrollment import PersonEnrollmentCoordinator
from src.ui.person_profile import PersonProfileController
from src.ui.person_profile.tk_window import PersonProfileWindow
from src.core.detection_events import DetectionEventRepository, DetectionEventService
from src.ui.detection_history import DetectionHistoryController
from src.ui.detection_history.tk_window import DetectionHistoryWindow
from src.core.attendance import AttendancePolicy, AttendanceRepository, AttendanceService
from src.ui.attendance import AttendanceUIController
from src.ui.attendance.tk_window import AttendanceHistoryWindow
from src.ui.action_adapters import (
    AutomaticAttendanceEventAdapter, DetectionEventServiceActionAdapter,
    IdentificationPopupActionAdapter,
)
from src.validation.guided_face_capture import load_guided_profile
from src.core.reports import ReportPolicy, ReportService
from src.ui.reports import ReportController, ReportWindow
from src.ui.people.search_controller import (
    AdvancedPeopleSearchController, PeopleSearchPolicy,
)
from src.core.security import (
    AuthenticationPolicy, AuthenticationService, AuthenticatedSessionManager,
    AuthorizationEngine, AuthorizationPermission, PasswordHasher, PasswordPolicy, UserRepository,
    AuthenticatedSessionDTO, UserDTO, UserRole, UserStatus,
)
from src.ui.security import AuthorizationController, LoginWindow, SecurityController
from src.core.backup import (
    ApplicationMaintenanceCoordinator, BackupArchive, BackupService,
    BackupSourceCatalog, RestoreService, SQLiteSnapshotProvider,
)
from src.ui.backup import BackupController, BackupWindow
from src.core.system_health import (
    ApplicationEventBusHealthProvider, BackupHealthProvider, CameraHealthProvider,
    RollingPerformanceMetrics, RuntimeHealthProvider, SecurityHealthProvider,
    SQLiteDatabaseHealthProvider, SystemHealthService, WorkerHealthProvider,
)
from src.ui.system_health import SystemHealthController, SystemHealthWindow
from src.core.configuration import (
    ConfigurationLoader, ConfigurationProfile, ConfigurationService,
    ConfigurationValidator,
)
from src.ui.configuration import ConfigurationController, ConfigurationWindow
from src.core.time_provider import Clock
from src.core.audit import AuditCallbackAdapter, AuditRepository, AuditService
from src.ui.audit import AuditController, AuditLogWindow

LOGGER = logging.getLogger(__name__)

class StartupMode(str, Enum):
    ASK = "ASK"
    TK = "TK"
    WEB = "WEB"
    BOTH = "BOTH"

def _web_value(payload: object, name: str, *, limit: int = 120) -> str:
    if not isinstance(payload, dict) or not isinstance(payload.get(name), str):
        raise ValueError(f"{name} es obligatorio.")
    value = payload[name].strip()
    if not value or len(value) > limit:
        raise ValueError(f"{name} es inválido.")
    return value

def _web_registration_form(payload: object):
    if not isinstance(payload,dict):raise ValueError("Datos de persona inválidos.")
    optional=lambda key,limit=200: (str(payload[key]).strip()[:limit] or None) if payload.get(key) is not None else None
    return validate_registration_form(
        _web_value(payload,"first_name"),_web_value(payload,"last_name"),None,
        consent_confirmed=payload.get("consent_confirmed") is True,persist_locally=True,
        cedula=_web_value(payload,"cedula"),address=optional("address"),
        phone=optional("phone",40),email=optional("email",254),
    )

def _camera_id(payload: object) -> str:
    if isinstance(payload, dict) and isinstance(payload.get("source_id"), str):
        return _web_value(payload, "source_id")
    return _web_value(payload, "id")

def _camera_name(payload: object) -> str:
    return _web_value(payload, "name")

def _camera_url(payload: object) -> str:
    value = _web_value(payload, "url", limit=2_000)
    if not value.lower().startswith(("http://", "https://", "rtsp://", "rtsps://")):
        raise ValueError("URL de cámara inválida. Use rtsp://, rtsps://, http:// o https://.")
    try:
        if not urlsplit(value).hostname:
            raise ValueError
    except ValueError as exc:
        raise ValueError("URL de cámara inválida.") from exc
    return value

def _camera_network_type(payload: object) -> CameraSourceType:
    value = _web_value(payload, "type")
    try:
        result = CameraSourceType(value)
    except ValueError as exc:
        raise ValueError("Tipo de cámara inválido.") from exc
    if result not in {CameraSourceType.NETWORK_HTTP, CameraSourceType.NETWORK_RTSP, CameraSourceType.CUSTOM}:
        raise ValueError("Tipo de cámara inválido.")
    return result

def configured_startup_mode(settings: dict[str, object]) -> StartupMode:
    """Read the additive UI mode while preserving legacy tk_enabled behavior."""
    ui = settings.get("ui", {})
    if not isinstance(ui, dict): raise ValueError("ui configuration must be an object")
    value = ui.get("startup_mode")
    if value is None:
        web = settings.get("web_dashboard", {})
        web_enabled = isinstance(web, dict) and web.get("enabled") is True
        return StartupMode.BOTH if ui.get("tk_enabled", True) and web_enabled else (
            StartupMode.WEB if ui.get("tk_enabled", True) is False else StartupMode.TK)
    try: return StartupMode(str(value).upper())
    except ValueError as exc: raise ValueError("ui.startup_mode must be ASK, TK, WEB or BOTH") from exc

def apply_startup_mode(settings: dict[str, object], mode: StartupMode) -> dict[str, object]:
    """Compose presentation flags without changing runtime/camera ownership."""
    if mode is StartupMode.ASK: raise ValueError("ASK must be resolved before service composition")
    result = dict(settings)
    ui = dict(settings.get("ui", {})); web = dict(settings.get("web_dashboard", {}))
    ui["tk_enabled"] = mode in {StartupMode.TK, StartupMode.BOTH}
    web["enabled"] = mode in {StartupMode.WEB, StartupMode.BOTH}
    # RC20.2: the web endpoint is advertised, but startup never launches a browser.
    web["open_browser_on_start"] = False
    result["ui"] = ui; result["web_dashboard"] = web
    return result

def ask_startup_mode(root: object) -> StartupMode | None:
    """Modal appliance selector; closing it requests a clean shutdown."""
    import tkinter as tk
    from tkinter import ttk
    selected: list[StartupMode] = []
    window = tk.Toplevel(root); window.title("FASTVISION AI")
    window.resizable(False, False); window.transient(root); window.grab_set()
    ttk.Label(window, text="FASTVISION AI", font=("TkDefaultFont", 17, "bold")).pack(padx=42, pady=(28, 10))
    ttk.Label(window, text="¿Cómo desea iniciar?").pack(pady=(0, 14))
    def choose(mode: StartupMode) -> None: selected.append(mode); window.destroy()
    for label, mode in (("Dashboard local", StartupMode.TK), ("Dashboard Web", StartupMode.WEB), ("Ambos", StartupMode.BOTH)):
        ttk.Button(window, text=label, width=28, command=lambda item=mode: choose(item)).pack(padx=28, pady=5)
    window.protocol("WM_DELETE_WINDOW", window.destroy)
    window.bind("<Escape>", lambda _event: window.destroy())
    window.wait_window()
    return selected[0] if selected else None

GALLERY_SYNC_WARNING = (
    "La información civil y la galería biométrica activa no están sincronizadas."
)
GALLERY_SYNC_ERROR = (
    "La sincronización entre personas ACTIVE y la galería biométrica es incompatible; "
    "revise el perfil de datos. No se realizó ninguna reparación automática."
)

@dataclass(frozen=True, slots=True)
class StorageSynchronizationDiagnostic:
    gallery_loaded: bool
    identity_count: int
    template_count: int
    active_person_count: int
    matched_person_ids: tuple[str, ...]
    synchronization_ok: bool
    persons_without_face: tuple[str, ...] = ()
    orphan_gallery_identity_ids: tuple[str, ...] = ()

    @property
    def gallery_identity_count(self) -> int:
        return self.identity_count

    @property
    def biometric_person_count(self) -> int:
        return self.identity_count

    @property
    def persons_without_face_count(self) -> int:
        return len(self.persons_without_face)

    @property
    def orphan_gallery_identity_count(self) -> int:
        return len(self.orphan_gallery_identity_ids)

def storage_synchronization_diagnostic(
    repository: PersonRepository | None, gallery: FaceGallery, *, gallery_loaded: bool,
) -> StorageSynchronizationDiagnostic:
    active_ids: set[str] = set()
    if repository is not None:
        offset = 0
        while True:
            page = repository.list(limit=100, offset=offset)
            active_ids.update(item.person_id for item in page if item.status is PersonStatus.ACTIVE)
            if len(page) < 100: break
            offset += len(page)
    gallery_ids = {item.person_id for item in gallery.list_identities()}
    # An ACTIVE civil record without templates is a valid pending-biometric state.
    # Only a gallery identity with no active civil owner is operationally incompatible.
    without_face = tuple(sorted(active_ids - gallery_ids))
    orphaned = tuple(sorted(gallery_ids - active_ids))
    return StorageSynchronizationDiagnostic(
        gallery_loaded, len(gallery_ids), len(gallery.templates()), len(active_ids),
        tuple(sorted(active_ids & gallery_ids)), not orphaned, without_face, orphaned,
    )


def civil_gallery_sync_warning(repository: PersonRepository | None,
                               gallery: FaceGallery) -> str | None:
    if repository is None: return None
    diagnostic = storage_synchronization_diagnostic(
        repository, gallery, gallery_loaded=bool(gallery.list_identities()))
    has_data = diagnostic.orphan_gallery_identity_count
    return GALLERY_SYNC_WARNING if not diagnostic.synchronization_ok and has_data else None


def local_validation_login_bypass_enabled(settings: dict[str, object]) -> bool:
    """Return only the explicit local-validation switch; never infer a bypass."""
    configuration = settings.get("security", {})
    if not isinstance(configuration, dict):
        raise ValueError("security configuration must be an object")
    enabled = configuration.get("skip_login_for_local_validation", False)
    if type(enabled) is not bool:
        raise ValueError("security.skip_login_for_local_validation must be boolean")
    if enabled and not bool(configuration.get("enabled", True)):
        raise ValueError("local validation login bypass requires security.enabled=true")
    return enabled


def appliance_mode_enabled(settings: dict[str, object]) -> bool:
    configuration=settings.get("security",{})
    if not isinstance(configuration,dict):raise ValueError("security configuration must be an object")
    enabled=configuration.get("appliance_mode",False)
    if type(enabled) is not bool:raise ValueError("security.appliance_mode must be boolean")
    if enabled and not bool(configuration.get("enabled",True)):raise ValueError("appliance mode requires security.enabled=true")
    return enabled


def start_local_validation_admin_session(
    security: SecurityController,
) -> AuthenticatedSessionDTO:
    """Start an ephemeral ADMIN session without creating a repository user."""
    if not security.enabled:
        raise ValueError("local validation session requires enabled security")
    now = datetime.now(timezone.utc)
    temporary_user = UserDTO(
        str(uuid.uuid4()), "local-validation-admin", "Validación local",
        UserRole.ADMIN, UserStatus.ACTIVE, 0, None, None, None, now, now,
    )
    return security.sessions.start(temporary_user)


def start_appliance_admin_session(security: SecurityController) -> AuthenticatedSessionDTO:
    """Create an ADMIN principal only in memory; it is never a credential account."""
    if not security.enabled:raise ValueError("appliance session requires enabled security")
    now=datetime.now(timezone.utc)
    principal=UserDTO(str(uuid.uuid4()),"appliance","Appliance Jetson",UserRole.ADMIN,
                      UserStatus.ACTIVE,0,None,None,None,now,now)
    return security.sessions.start(principal)


def authenticate_startup(
    root: object, security: SecurityController, *, skip_login: bool,
    login_factory=LoginWindow, reveal_root: bool = True,
) -> bool:
    """Authenticate before Runtime/Camera construction, optionally via explicit bypass."""
    root.withdraw()
    if skip_login:
        start_local_validation_admin_session(security)
        LOGGER.warning("Security login bypass enabled for local validation")
        authenticated = True
    else:
        authenticated = bool(login_factory(root, security).run())
    if authenticated and reveal_root:
        root.deiconify()
    return authenticated


def build_security(
    settings: dict[str, object], project_root: Path = PROJECT_ROOT,
) -> SecurityController:
    """Build fail-closed operator security with a project-relative users.db."""
    configuration = settings.get("security", {})
    if not isinstance(configuration, dict):
        raise ValueError("security configuration must be an object")
    enabled = bool(configuration.get("enabled", True))
    sessions = AuthenticatedSessionManager(
        float(configuration.get("session_idle_timeout_seconds", 1800))
    )
    engine = AuthorizationEngine(enabled=enabled)
    authorization = AuthorizationController(engine, sessions, enabled=enabled)
    if not enabled:
        # This is the sole explicit authorization bypass. No database is touched.
        repository = UserRepository(project_root / ".security-disabled-unused.db")
        hasher = PasswordHasher(PasswordPolicy())
        authentication = AuthenticationService(repository, hasher)
        return SecurityController(authentication, sessions, authorization, enabled=False)
    configured = Path(str(configuration.get("database_path", "data/fastvision/users.db")))
    if configured.is_absolute() or ".." in configured.parts:
        raise ValueError("security database path must be project-relative and safe")
    root = project_root.resolve(); database = (root / configured).resolve()
    if root not in database.parents:
        raise ValueError("security database path escapes project root")
    repository = UserRepository(database)
    appliance=configuration.get("appliance_mode",False)
    if type(appliance) is not bool:raise ValueError("security.appliance_mode must be boolean")
    if not appliance:
        repository.initialize()  # normal login/bootstrap remains fail-closed
    password_policy = PasswordPolicy(
        int(configuration.get("minimum_password_length", 10)),
        int(configuration.get("maximum_password_length", 128)),
    )
    hasher = PasswordHasher(password_policy)
    authentication = AuthenticationService(repository, hasher, AuthenticationPolicy(
        int(configuration.get("max_failed_attempts", 5)),
        int(configuration.get("lockout_seconds", 300)),
    ))
    return SecurityController(
        authentication, sessions, authorization, enabled=True,
        bootstrap_enabled=bool(configuration.get("bootstrap_admin_enabled", True)),
    )


def build_audit(settings: dict[str, object], project_root: Path = PROJECT_ROOT) -> AuditService:
    configuration=settings.get("audit",{})
    if not isinstance(configuration,dict):raise ValueError("audit configuration must be an object")
    enabled=bool(configuration.get("enabled",False))
    configured=Path(str(configuration.get("database_path","data/fastvision/audit.db")))
    if configured.is_absolute() or ".." in configured.parts:raise ValueError("audit database path must be project-relative and safe")
    root=project_root.resolve();database=(root/configured).resolve()
    if root not in database.parents:raise ValueError("audit database path escapes project root")
    repository=AuditRepository(database,timeout=float(configuration.get("sqlite_timeout_seconds",5.0)))
    service=AuditService(repository,enabled=enabled,metadata_max_items=int(configuration.get("metadata_max_items",20)),metadata_value_max_length=int(configuration.get("metadata_value_max_length",256)),message_max_length=int(configuration.get("message_max_length",500)))
    if enabled:
        try:repository.initialize()
        except Exception:
            LOGGER.warning("Administrative audit initialization failed; audit remains unavailable")
            service.enabled=False
    return service


@dataclass(frozen=True, slots=True)
class GalleryStartupResult:
    gallery: FaceGallery
    message: str
    error: ErrorDTO | None = None


def load_startup_gallery(
    settings: dict[str, object], *, force_load: bool = False,
    project_root: Path = PROJECT_ROOT,
) -> GalleryStartupResult:
    """Optionally import a validated gallery before matcher construction."""
    persistence_settings = settings["persistence"]
    if not isinstance(persistence_settings, dict):
        raise ValueError("persistence configuration must be an object")
    enabled = force_load or bool(persistence_settings.get("load_on_startup", False))
    gallery = FaceGallery()
    if not enabled:
        return GalleryStartupResult(gallery, "Galería vacía")
    _, manifest, archive = build_persistence(settings, project_root)
    manifest_exists = manifest.is_file()
    archive_exists = archive.is_file()
    if not manifest_exists and not archive_exists:
        return GalleryStartupResult(gallery, "Galería vacía")
    if manifest_exists != archive_exists:
        return GalleryStartupResult(
            gallery, "Galería vacía",
            ErrorDTO(
                UIState.ERROR, UIErrorCode.PERSISTENCE_ERROR,
                "La galería persistida está incompleta; se inició una galería vacía.", True,
            ),
        )
    try:
        GalleryPersistence(enabled=True).import_into(gallery, manifest, archive)
    except Exception:
        # Do not expose exception text, hashes, templates or biometric vectors.
        return GalleryStartupResult(
            FaceGallery(), "Galería vacía",
            ErrorDTO(
                UIState.ERROR, UIErrorCode.PERSISTENCE_ERROR,
                "La galería persistida no superó la validación; se inició una galería vacía.",
                True,
            ),
        )
    return GalleryStartupResult(
        gallery,
        f"Galería cargada: {len(gallery.list_identities())} identidades, "
        f"{len(gallery.templates())} templates",
    )


def build_persistence(
    settings: dict[str, object], project_root: Path = PROJECT_ROOT,
):
    """Build an explicit post-enrollment export without touching its destination."""
    persistence_settings = settings["persistence"]
    if not isinstance(persistence_settings, dict):
        raise ValueError("persistence configuration must be an object")
    configured = Path(str(persistence_settings["directory"]))
    if configured.is_absolute():
        raise ValueError("persistence directory must be relative to the project root")
    root = project_root.resolve()
    destination = (root / configured).resolve()
    if destination != root and root not in destination.parents:
        raise ValueError("persistence directory escapes the project root")
    persistence = GalleryPersistence(enabled=True)

    def persist_enrollment_gallery(gallery, manifest_path, archive_path):
        # Enrollment is the authoritative update of the configured active
        # gallery. Existing startup artifacts (including an empty gallery)
        # must be atomically replaced after a successful biometric commit.
        persistence.export(
            gallery, manifest_path, archive_path, overwrite=True,
        )

    return (
        persist_enrollment_gallery,
        destination / "gallery.json",
        destination / "gallery.npz",
    )


def build_thumbnail_manager(
    settings: dict[str, object], project_root: Path = PROJECT_ROOT,
) -> ThumbnailManager:
    thumbnail = settings.get("thumbnails", {})
    if not isinstance(thumbnail, dict):
        raise ValueError("thumbnail configuration must be an object")
    return ThumbnailManager(
        project_root, Path(str(thumbnail.get("directory", "data/ui_validation/thumbnails"))),
        enabled=bool(thumbnail.get("enabled", False)),
        width=int(thumbnail.get("width", 224)),
        height=int(thumbnail.get("height", 224)),
        image_format=str(thumbnail.get("format", "jpeg")),
        jpeg_quality=int(thumbnail.get("jpeg_quality", 90)),
        replace_existing=bool(thumbnail.get("replace_existing", False)),
    )


def build_controller(
    config_path: Path, gallery: FaceGallery | None = None,
    person_repository: PersonRepository | None = None,
) -> LocalFaceUIController:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    enrollment_config = config["enrollment"]
    recognition_config = config["recognition"]
    if not isinstance(recognition_config, dict):
        raise ValueError("recognition configuration must be an object")
    gallery = gallery if gallery is not None else FaceGallery()
    automatic_recognition = bool(recognition_config.get("automatic_decision_enabled"))
    if not automatic_recognition and (
        recognition_config.get("match_threshold") is not None
        or recognition_config.get("ambiguity_margin") is not None
    ):
        raise ValueError("disabled recognition requires null threshold and ambiguity_margin")
    calibration_invalid = False
    if automatic_recognition:
        from src.engine.calibration import validate_approved_calibration
        calibration_file = config.get("recognition_calibration_file")
        try:
            if not isinstance(calibration_file, str) or not calibration_file.strip():
                raise ValueError("missing calibration file")
            calibration_path = Path(calibration_file)
            if not calibration_path.is_absolute():
                calibration_path = PROJECT_ROOT / calibration_path
            validate_approved_calibration(calibration_path, gallery, recognition_config)
        except Exception:
            LOGGER.error("RECONOCIMIENTO DESACTIVADO — CALIBRACIÓN INVÁLIDA")
            automatic_recognition = False
            calibration_invalid = True
    matcher = FaceMatcher(
        top_k=int(config["matcher"]["top_k"]),
        policy=MatchPolicy(automatic_decision_enabled=False, threshold=None),
    )
    recognition_policy = RecognitionPolicy(
        automatic_decision_enabled=automatic_recognition,
        match_threshold=(recognition_config.get("match_threshold")
                         if automatic_recognition else None),
        ambiguity_margin=(recognition_config.get("ambiguity_margin")
                          if automatic_recognition else None),
        top_k=int(recognition_config["top_k"]),
        minimum_quality_score=recognition_config["minimum_quality_score"],
        allow_low_quality=bool(recognition_config["allow_low_quality"]),
        policy_name=str(recognition_config["policy_name"]),
        policy_version=str(recognition_config["policy_version"]),
    )
    recognition_service = RecognitionService(gallery, matcher, recognition_policy)
    policy = EnrollmentPolicy(
        min_templates=int(enrollment_config["min_templates"]),
        max_templates=int(enrollment_config["max_templates"]),
        allow_low_quality=bool(enrollment_config["allow_low_quality"]),
        min_pairwise_similarity=enrollment_config["min_pairwise_similarity"],
        max_pairwise_similarity=enrollment_config["max_pairwise_similarity"],
        reject_exact_duplicates=bool(enrollment_config["reject_exact_duplicates"]),
    )
    service = EnrollmentService(gallery, policy)
    workflow = LocalEnrollmentWorkflow(
        gallery, service, target_samples=int(config["guided_capture"]["target_samples"])
    )
    coordinator = (None if person_repository is None else
                   PersonEnrollmentCoordinator(person_repository, gallery, workflow))
    return LocalFaceUIController(
        ExperimentalRecognitionSession(
            recognition_service, calibration_invalid=calibration_invalid), workflow, coordinator,
    )


def build_person_repository(
    settings: dict[str, object], project_root: Path = PROJECT_ROOT,
) -> PersonRepository | None:
    database = settings.get("person_database", {})
    if not isinstance(database, dict):
        raise ValueError("person_database configuration must be an object")
    if not bool(database.get("enabled", False)):
        return None
    configured = Path(str(database.get("path", "data/fastvision/people.db")))
    if configured.is_absolute():
        raise ValueError("person database path must be relative")
    root = project_root.resolve()
    resolved = (root / configured).resolve()
    if root not in resolved.parents:
        raise ValueError("person database path escapes project root")
    repository = PersonRepository(
        resolved, timeout=float(database.get("timeout_seconds", 5.0))
    )
    repository.initialize()
    return repository


def build_detection_event_service(
    settings: dict[str, object], project_root: Path = PROJECT_ROOT,
) -> DetectionEventService | None:
    configuration = settings.get("event_history", {})
    if not isinstance(configuration, dict):
        raise ValueError("event_history configuration must be an object")
    if not bool(configuration.get("enabled", False)):
        return None
    configured = Path(str(configuration.get("database_path", "data/fastvision/events.db")))
    if configured.is_absolute():
        raise ValueError("event history database path must be relative")
    root = project_root.resolve(); resolved = (root / configured).resolve()
    if root not in resolved.parents:
        raise ValueError("event history database path escapes project root")
    repository = DetectionEventRepository(resolved)
    try:
        repository.initialize()
    except Exception:
        LOGGER.warning("Event history initialization failed; history remains disabled")
        return None
    return DetectionEventService(
        repository,
        registered_cooldown_seconds=float(configuration.get("registered_cooldown_seconds", 60)),
        unregistered_cooldown_seconds=float(configuration.get("unregistered_cooldown_seconds", 60)),
        cache_limit=int(configuration.get("history_limit", 500)),
    )

def build_attendance(
    settings: dict[str, object], people: PersonRepository | None,
    project_root: Path = PROJECT_ROOT, authorization=None,
) -> AttendanceUIController | None:
    configuration = settings.get("attendance", {})
    if not isinstance(configuration, dict):
        raise ValueError("attendance configuration must be an object")
    # Return before even resolving a path: disabled mode must not access the database.
    if not bool(configuration.get("enabled", False)) or people is None:
        return None
    if (settings.get("profile_name") == "local_face_validation_prod"
            and bool(configuration.get("automatic_attendance_enabled", False))
            and not isinstance(configuration.get("work_schedule"), dict)):
        raise ValueError("production automatic attendance requires explicit work_schedule")
    configured = Path(str(
        configuration.get("database_path", "data/fastvision/attendance.db")
    ))
    if configured.is_absolute():
        raise ValueError("attendance database path must be relative")
    root = project_root.resolve()
    resolved = (root / configured).resolve()
    if root not in resolved.parents:
        raise ValueError("attendance database path escapes project root")
    repository = AttendanceRepository(
        resolved, timeout=float(configuration.get("timeout_seconds", 5.0)),
    )
    try:
        repository.initialize()
    except Exception:
        LOGGER.warning("Attendance initialization failed; attendance remains disabled")
        return None
    policy = AttendancePolicy(
        enabled=True,
        automatic_attendance_enabled=bool(
            configuration.get("automatic_attendance_enabled", False)
        ),
        minimum_stable_observations=int(
            configuration.get("minimum_stable_observations", 3)
        ),
        minimum_observation_seconds=float(
            configuration.get("minimum_observation_seconds", 2)
        ),
        duplicate_event_cooldown_seconds=float(
            configuration.get("duplicate_event_cooldown_seconds", 60)
        ),
        minimum_time_between_check_in_out_seconds=float(
            configuration.get("minimum_time_between_check_in_out_seconds", 60)
        ),
        allow_manual_events=bool(configuration.get("allow_manual_events", True)),
        policy_name=str(configuration.get("policy_name", "attendance_manual_validation")),
        policy_version=str(configuration.get("policy_version", "1.0")),
        automatic_mode=str(configuration.get("automatic_mode", "TOGGLE_DAILY")),
        timezone=str((configuration.get("work_schedule") or {}).get(
            "timezone", "America/Guayaquil")),
        workday_start=str((configuration.get("work_schedule") or {}).get(
            "workday_start", "08:00")),
        workday_end=str((configuration.get("work_schedule") or {}).get(
            "workday_end", "17:00")),
        late_after=str((configuration.get("work_schedule") or {}).get(
            "late_after", "08:10")),
        overtime_after=str((configuration.get("work_schedule") or {}).get(
            "overtime_after", "17:00")),
    )
    service = AttendanceService(repository, people, policy)
    return AttendanceUIController(service, repository, people, authorization)


def build_stability_tracker(settings: dict[str, object]) -> StabilityTracker | None:
    configuration = settings.get("stability", {})
    if not isinstance(configuration, dict):
        raise ValueError("stability configuration must be an object")
    if not bool(configuration.get("enabled", False)):
        return None
    policy = StabilityPolicy(
        enabled=True,
        minimum_observations=int(configuration.get("minimum_observations", 5)),
        minimum_duration_seconds=float(
            configuration.get("minimum_duration_seconds", 1.5)
        ),
        maximum_gap_seconds=float(configuration.get("maximum_gap_seconds", 0.75)),
        minimum_similarity=(
            None if configuration.get("minimum_similarity") is None
            else float(configuration["minimum_similarity"])
        ),
        reset_on_multiple_faces=bool(
            configuration.get("reset_on_multiple_faces", True)
        ),
        reset_on_candidate_change=bool(
            configuration.get("reset_on_candidate_change", True)
        ),
        policy_name=str(configuration.get("policy_name", "stability_development")),
        policy_version=str(configuration.get("policy_version", "1.0")),
    )
    return StabilityTracker(policy)


def build_identification_policy_engine(
    settings: dict[str, object],
) -> IdentificationPolicyEngine | None:
    configuration = settings.get("identification_policy", {})
    if not isinstance(configuration, dict):
        raise ValueError("identification_policy configuration must be an object")
    if not bool(configuration.get("enabled", False)):
        return None
    policy = IdentificationPolicy(
        enabled=True,
        automatic_actions_enabled=bool(
            configuration.get("automatic_actions_enabled", False)
        ),
        require_candidate=bool(configuration.get("require_candidate", True)),
        require_active_person=bool(configuration.get("require_active_person", True)),
        require_stable_observation=bool(
            configuration.get("require_stable_observation", True)
        ),
        minimum_quality_score=_optional_float(configuration, "minimum_quality_score"),
        minimum_similarity=_optional_float(configuration, "minimum_similarity"),
        minimum_stability_observations=_optional_int(
            configuration, "minimum_stability_observations"
        ),
        minimum_stability_duration_seconds=_optional_float(
            configuration, "minimum_stability_duration_seconds"
        ),
        reject_incompatible=bool(configuration.get("reject_incompatible", True)),
        reject_ambiguous=bool(configuration.get("reject_ambiguous", True)),
        policy_name=str(configuration.get(
            "policy_name", "identification_policy_development"
        )),
        policy_version=str(configuration.get("policy_version", "1.0")),
    )
    return IdentificationPolicyEngine(policy)


def build_decision_orchestrator(
    settings: dict[str, object],
) -> DecisionOrchestrator | None:
    configuration = settings.get("decision_orchestrator", {})
    if not isinstance(configuration, dict):
        raise ValueError("decision_orchestrator configuration must be an object")
    if not bool(configuration.get("enabled", False)):
        return None
    return DecisionOrchestrator(DecisionOrchestratorPolicy(
        enabled=True,
        automatic_actions_enabled=bool(
            configuration.get("automatic_actions_enabled", False)
        ),
        allow_registered_popup_proposal=bool(
            configuration.get("allow_registered_popup_proposal", True)
        ),
        allow_unregistered_popup_proposal=bool(
            configuration.get("allow_unregistered_popup_proposal", True)
        ),
        allow_detection_event_proposal=bool(
            configuration.get("allow_detection_event_proposal", True)
        ),
        allow_attendance_proposal=bool(
            configuration.get("allow_attendance_proposal", False)
        ),
        require_stable_for_registered_popup=bool(
            configuration.get("require_stable_for_registered_popup", True)
        ),
        require_policy_eligible_for_attendance=bool(
            configuration.get("require_policy_eligible_for_attendance", True)
        ),
        require_active_person_for_attendance=bool(
            configuration.get("require_active_person_for_attendance", True)
        ),
        policy_name=str(configuration.get(
            "policy_name", "decision_orchestrator_development"
        )),
        policy_version=str(configuration.get("policy_version", "1.0")),
    ))


def build_action_executor(
    settings: dict[str, object],
    detection_events: DetectionEventService | None = None,
    popup_adapter: IdentificationPopupActionAdapter | None = None,
    application_event_bus: ApplicationEventBus | None = None,
) -> ActionExecutor | None:
    """Build the executor; only the low-risk event adapter may be wired."""
    configuration = settings.get("action_executor", {})
    if not isinstance(configuration, dict):
        raise ValueError("action_executor configuration must be an object")
    if not bool(configuration.get("enabled", False)):
        return None
    policy = ActionExecutorPolicy(
        enabled=True,
        automatic_execution_enabled=bool(
            configuration.get("automatic_execution_enabled", False)
        ),
        allow_registered_popup=bool(
            configuration.get("allow_registered_popup", True)
        ),
        allow_unregistered_popup=bool(
            configuration.get("allow_unregistered_popup", True)
        ),
        allow_detection_event_logging=bool(
            configuration.get("allow_detection_event_logging", True)
        ),
        allow_attendance_execution=bool(
            configuration.get("allow_attendance_execution", False)
        ),
        require_orchestrator_actions_enabled=bool(
            configuration.get("require_orchestrator_actions_enabled", True)
        ),
        policy_name=str(configuration.get(
            "policy_name", "action_executor_development"
        )),
        policy_version=str(configuration.get("policy_version", "1.0")),
    )
    adapter = None
    if detection_events is not None and policy.allow_detection_event_logging:
        adapter = DetectionEventServiceActionAdapter(
            detection_events, application_event_bus,
        )
    configured_popup = popup_adapter if _popup_configuration_complete(settings) else None
    return ActionExecutor(
        policy, popup_adapter=configured_popup, detection_event_adapter=adapter,
    )


def build_application_events(
    settings: dict[str, object],
) -> tuple[ApplicationEventBus | None, ApplicationEventDiagnosticsStore | None]:
    """Create one optional application bus and its scalar-only diagnostics store."""
    configuration = settings.get("application_events", {})
    if not isinstance(configuration, dict):
        raise ValueError("application_events configuration must be an object")
    if not bool(configuration.get("enabled", False)):
        return None, None
    limit = int(configuration.get("max_diagnostic_events", 100))
    diagnostics = ApplicationEventDiagnosticsStore(limit=limit)
    bus = ApplicationEventBus()
    bus.subscribe(ApplicationEvent, diagnostics.record)
    return bus, diagnostics


def build_reports(settings, people, detections, attendance, authorization=None,
                  attendance_policy=None):
    configuration = settings.get("reports", {})
    if not isinstance(configuration, dict):
        raise ValueError("reports configuration must be an object")
    if not bool(configuration.get("enabled", False)):
        return None
    if people is None or detections is None or attendance is None:
        return None
    policy = ReportPolicy(
        default_range_days=int(configuration.get("default_range_days", 7)),
        max_rows=int(configuration.get("max_rows", 5_000)),
        presentation_timezone=str(
            configuration.get("presentation_timezone", "America/Guayaquil")
        ),
    )
    return ReportController(ReportService(people, detections, attendance, policy,
                                          attendance_policy), authorization=authorization)


def build_people_search(settings, controller, thumbnail_manager):
    configuration = settings.get("people_search", {})
    if not isinstance(configuration, dict):
        raise ValueError("people_search configuration must be an object")
    if not bool(configuration.get("enabled", False)):
        return None
    if not isinstance(controller, DatabasePeopleManagerController):
        return None
    policy = PeopleSearchPolicy(
        default_page_size=int(configuration.get("default_page_size", 25)),
        allowed_page_sizes=tuple(int(value) for value in
                                 configuration.get("allowed_page_sizes", (25, 50, 100))),
        debounce_ms=int(configuration.get("debounce_ms", 400)),
        presentation_timezone=str(
            configuration.get("presentation_timezone", "America/Guayaquil")
        ),
    )
    return AdvancedPeopleSearchController(controller, thumbnail_manager, policy)


def _popup_configuration_complete(settings: dict[str, object]) -> bool:
    action = settings.get("action_executor", {})
    decision = settings.get("decision_orchestrator", {})
    if not isinstance(action, dict) or not isinstance(decision, dict):
        return False
    return bool(
        action.get("enabled", False)
        and action.get("automatic_execution_enabled", False)
        and action.get("allow_registered_popup", False)
        and action.get("allow_unregistered_popup", False)
        and decision.get("enabled", False)
        and decision.get("automatic_actions_enabled", False)
        and decision.get("allow_registered_popup_proposal", False)
        and decision.get("allow_unregistered_popup_proposal", False)
    )


def uses_action_executor_detection_logging(
    executor: ActionExecutor | None,
    orchestrator: DecisionOrchestrator | None,
    detection_events: DetectionEventService | None,
) -> bool:
    """Resolve one stable logging route at composition time, never per frame."""
    return bool(
        detection_events is not None
        and executor is not None
        and executor.policy.enabled
        and executor.has_detection_event_adapter
        and executor.policy.automatic_execution_enabled
        and executor.policy.allow_detection_event_logging
        and orchestrator is not None
        and orchestrator.policy.enabled
        and orchestrator.policy.automatic_actions_enabled
        and orchestrator.policy.allow_detection_event_proposal
    )


def uses_action_executor_popups(
    executor: ActionExecutor | None,
    orchestrator: DecisionOrchestrator | None,
    controller: IdentificationPresentationController | None,
) -> bool:
    """Resolve the popup route independently from detection logging."""
    return bool(
        executor is not None and executor.policy.enabled
        and executor.policy.automatic_execution_enabled
        and executor.has_popup_adapter
        and executor.policy.allow_registered_popup
        and executor.policy.allow_unregistered_popup
        and orchestrator is not None and orchestrator.policy.enabled
        and orchestrator.policy.automatic_actions_enabled
        and orchestrator.policy.allow_registered_popup_proposal
        and orchestrator.policy.allow_unregistered_popup_proposal
        and controller is not None and controller.policy.enabled
    )


def _optional_float(configuration: dict[str, object], key: str) -> float | None:
    value = configuration.get(key)
    return None if value is None else float(value)


def _optional_int(configuration: dict[str, object], key: str) -> int | None:
    value = configuration.get(key)
    return None if value is None else int(value)


def build_dashboard_configuration(settings: dict[str, object]) -> DashboardConfigurationDTO:
    camera = settings["camera"]; guided = settings["guided_capture"]
    quality = settings["quality"]; persistence = settings["persistence"]
    recognition = settings["recognition"]
    if not all(isinstance(item, dict) for item in (
        camera, guided, quality, persistence, recognition,
    )):
        raise ValueError("dashboard configuration sections must be objects")
    raw_camera_source = camera.get("source", "N/D")
    safe_camera_source = (
        redact_url(raw_camera_source) if isinstance(raw_camera_source, str)
        and raw_camera_source.lower().startswith(("rtsp://", "rtsps://", "http://", "https://"))
        else str(raw_camera_source)
    )
    return DashboardConfigurationDTO(
        safe_camera_source, str(camera.get("resolution", "N/D")),
        bool(guided.get("mirrored_source", False)), str(guided.get("policy_file", "N/D")),
        str(quality.get("profile_file", "N/D")), int(guided["target_samples"]),
        bool(persistence.get("enabled_by_default", False)),
        bool(persistence.get("load_on_startup", False)),
        str(recognition["policy_name"]), str(recognition["policy_version"]),
        bool(recognition["automatic_decision_enabled"]),
        "N/D" if recognition.get("match_threshold") is None else str(recognition["match_threshold"]),
        "N/D" if recognition.get("ambiguity_margin") is None else str(recognition["ambiguity_margin"]),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="UI facial local experimental")
    parser.add_argument("--config", type=Path,
                        default=Path("config/local_face_validation.dev.json"))
    parser.add_argument("--mock-camera", action="store_true",
                        help="use deterministic synthetic frames without /dev/videoX")
    parser.add_argument("--mock-auto-enroll", action="store_true",
                        help="run a consented, non-persistent mock enrollment smoke test")
    parser.add_argument("--mock-duration", type=float,
                        help="close a mock UI automatically after this many seconds")
    parser.add_argument("--load-gallery", action="store_true",
                        help="load the configured local gallery for this execution")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--desktop-only", action="store_true",
                            help="start only the Tk desktop dashboard")
    mode_group.add_argument("--web-only", action="store_true",
                            help="start only the web dashboard")
    args = parser.parse_args()
    if (args.mock_auto_enroll or args.mock_duration is not None) and not args.mock_camera:
        parser.error("mock automation options require --mock-camera")
    if args.mock_duration is not None and args.mock_duration <= 0:
        parser.error("--mock-duration must be positive")
    raw_settings = json.loads(args.config.read_text(encoding="utf-8"))
    manager_settings = raw_settings.get("configuration_manager", {})
    if not isinstance(manager_settings, dict):
        raise ValueError("configuration_manager configuration must be an object")
    configuration_service = configuration_controller = None
    if bool(manager_settings.get("enabled", False)):
        try:
            profile = ConfigurationProfile(str(manager_settings.get("profile", "DEVELOPMENT")))
        except ValueError as exc:
            raise ValueError("configuration profile is unavailable") from exc
        if profile not in {ConfigurationProfile.DEVELOPMENT,ConfigurationProfile.PRODUCTION}:
            raise ValueError("configuration profile is unavailable")
        loader = ConfigurationLoader(ConfigurationValidator(PROJECT_ROOT))
        configuration_service = ConfigurationService(
            loader, args.config, profile,
            backup_count=int(manager_settings.get("backup_count", 10)),
        )
        settings = configuration_service.current().as_mapping()
    else:
        settings = raw_settings
    requested_startup_mode = (StartupMode.TK if args.desktop_only else
                              StartupMode.WEB if args.web_only else StartupMode.BOTH)
    ui_settings=settings.get("ui",{})
    if not isinstance(ui_settings,dict):raise ValueError("ui configuration must be an object")
    tk_enabled=ui_settings.get("tk_enabled",True)
    if type(tk_enabled) is not bool:raise ValueError("ui.tk_enabled must be boolean")
    if not tk_enabled:
        LOGGER.info("WEB-only enabled; Tk remains hidden only as the internal event-loop host")
    if settings.get("profile_name") == "local_face_validation_prod" and args.mock_camera:
        parser.error("production profile does not allow mock camera")
    security = build_security(settings)
    appliance_mode=appliance_mode_enabled(settings)
    if appliance_mode:
        start_appliance_admin_session(security)
        LOGGER.warning("MODO APPLIANCE JETSON enabled; credentials database is not used")
    local_validation_bypass = local_validation_login_bypass_enabled(settings)
    if appliance_mode and local_validation_bypass:
        raise ValueError("appliance_mode and local validation login bypass are mutually exclusive")
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Tkinter no está disponible en este entorno; no se instalaron dependencias"
        ) from exc
    root = tk.Tk(); root.withdraw()
    if requested_startup_mode is StartupMode.ASK:
        selected_mode = ask_startup_mode(root)
        if selected_mode is None:
            security.logout(); root.destroy(); return 0
        settings = apply_startup_mode(settings, selected_mode)
    else:
        settings = apply_startup_mode(settings, requested_startup_mode)
    tk_enabled = bool(settings["ui"]["tk_enabled"])
    if security.enabled and not appliance_mode:
        if not authenticate_startup(root, security, skip_login=local_validation_bypass,
                                    reveal_root=tk_enabled):
            root.destroy(); return 0
    elif tk_enabled:
        root.deiconify()
    audit_service=build_audit(settings)
    def audit(source):return AuditCallbackAdapter(audit_service,security.sessions.context,source)
    security.audit_callback=audit("security")
    if configuration_service is not None:configuration_service.audit=audit("configuration")
    application_events, application_event_diagnostics = build_application_events(settings)
    startup = load_startup_gallery(settings, force_load=args.load_gallery)
    person_repository = build_person_repository(settings)
    synchronization = storage_synchronization_diagnostic(
        person_repository, startup.gallery,
        gallery_loaded=startup.error is None and startup.message.startswith("Galería cargada:"),
    )
    LOGGER.info(
        "Storage synchronization diagnostic gallery_loaded=%s gallery_identity_count=%d "
        "template_count=%d active_person_count=%d biometric_person_count=%d "
        "persons_without_face_count=%d orphan_gallery_identity_count=%d synchronization_ok=%s",
        synchronization.gallery_loaded, synchronization.identity_count,
        synchronization.template_count, synchronization.active_person_count,
        synchronization.biometric_person_count, synchronization.persons_without_face_count,
        synchronization.orphan_gallery_identity_count, synchronization.synchronization_ok,
    )
    integral_profile = settings.get("profile_name") in {
        "local_face_validation_pc", "local_face_validation_prod",
        "local_face_validation_jetson",
    }
    synchronization_error = integral_profile and not synchronization.synchronization_ok
    if synchronization_error:
        LOGGER.error("Civil/gallery synchronization is incompatible; automatic repair disabled")
    detection_event_service = build_detection_event_service(settings)
    attendance_controller = build_attendance(
        settings, person_repository, authorization=security.authorization,
    )
    automatic_attendance_adapter = None
    if attendance_controller is not None:
        automatic_attendance_adapter = AutomaticAttendanceEventAdapter(
            attendance_controller.service, application_events,
        )
        application_events.subscribe(DetectionEventStoredEvent,
                                     automatic_attendance_adapter)
    report_controller = build_reports(
        settings, person_repository,
        None if detection_event_service is None else detection_event_service.repository,
        None if attendance_controller is None else attendance_controller.repository,
        security.authorization,
        None if attendance_controller is None else attendance_controller.service.policy,
    )
    stability_tracker = build_stability_tracker(settings)
    identification_policy_engine = build_identification_policy_engine(settings)
    decision_orchestrator = build_decision_orchestrator(settings)
    controller = build_controller(args.config, startup.gallery, person_repository)
    if controller.person_coordinator is not None:controller.person_coordinator.audit_callback=audit("person_enrollment")
    if attendance_controller is not None:attendance_controller.audit_callback=audit("attendance")
    if report_controller is not None:report_controller.audit_callback=audit("reports")
    persistence, manifest_path, archive_path = build_persistence(settings)
    thumbnail_manager = build_thumbnail_manager(settings)
    photo_controller = (
        None if person_repository is None else PersonPhotoController(
            person_repository, thumbnail_manager, security.authorization,
        )
    )
    people_controller = PeopleManagerController(
        startup.gallery, controller.enrollment.enrollment,
        GalleryPersistence(enabled=True), manifest_path, archive_path,
    )
    if person_repository is not None:
        people_controller = DatabasePeopleManagerController(  # type: ignore[assignment]
            person_repository, people_controller, security.authorization,audit("people"),
            thumbnail_manager,
        )
    people_search_controller = build_people_search(
        settings, people_controller, thumbnail_manager,
    )
    popup_settings = settings.get("identification_popup", {})
    if not isinstance(popup_settings, dict):
        raise ValueError("identification_popup configuration must be an object")
    identity_provider = (
        PeopleThumbnailIdentityInfoProvider(people_controller, thumbnail_manager)
        if person_repository is None else SQLiteThumbnailIdentityInfoProvider(
            SQLiteIdentityDataProvider(person_repository), thumbnail_manager, startup.gallery,
        )
    )
    if attendance_controller is not None:
        attendance_controller.identity_provider = identity_provider
    identification_controller = IdentificationPresentationController(
        IdentificationPopupPolicy(
            enabled=bool(popup_settings.get("enabled", True)),
            registered_cooldown_seconds=float(
                popup_settings.get("registered_cooldown_seconds", 10.0)
            ),
            unknown_cooldown_seconds=float(
                popup_settings.get("unknown_cooldown_seconds", 10.0)
            ),
            candidate_stability_frames=int(
                popup_settings.get("candidate_stability_frames", 3)
            ),
            unknown_popup_timeout_seconds=float(
                popup_settings.get("unknown_popup_timeout_seconds", 60.0)
            ),
            registered_popup_timeout_seconds=float(
                popup_settings.get("registered_popup_timeout_seconds", 60.0)
            ),
            registered_pause_seconds=float(
                popup_settings.get("registered_pause_seconds", 60.0)
            ),
        ),
        identity_provider,
    )
    popup_action_adapter = IdentificationPopupActionAdapter(
        identification_controller,
        queue_size=int(settings["queues"].get("event_size", 16)),
        application_event_bus=application_events,
    )
    action_executor = build_action_executor(
        settings, detection_event_service, popup_action_adapter, application_events,
    )
    detection_logging_via_executor = uses_action_executor_detection_logging(
        action_executor, decision_orchestrator, detection_event_service,
    )
    popups_via_executor = uses_action_executor_popups(
        action_executor, decision_orchestrator, identification_controller,
    )
    # Real Runtime/Camera ownership is deliberately constructed only after login.
    cancel_event = threading.Event()
    presentation_frame_store=LatestPresentationFrameStore()
    camera_discovery_config = parse_discovery_config(settings["camera"])
    preferred_source_id = camera_discovery_config.preferred_source
    camera_discovery = CameraSourceDiscovery(
        camera_discovery_config,
        # Saved network endpoints are probed after UI construction so their
        # bounded timeouts never freeze Tk startup.
        probe_network_sources=False,
    )
    initial_selection = None
    initial_selection_result = None
    if (camera_discovery_config.preferred_source is not None
            or camera_discovery_config.source == "auto"):
        initial_selection_result = CameraSelectionController(camera_discovery).refresh()
        initial_selection = initial_selection_result.selected
    initial_source = camera_discovery_config.source
    if initial_selection is not None:
        initial_source = camera_config_for_source(initial_selection, camera_discovery_config).source
    elif initial_source == "auto" or preferred_source_id is not None:
        # Deliberately invalid local index: the app remains DISCONNECTED until selection.
        initial_source = camera_discovery_config.scan_indices + 10_000
    explicit_legacy_source = (
        preferred_source_id is None and camera_discovery_config.source != "auto"
    )
    current_camera_source = {"id": (
        initial_selection.source_id if initial_selection is not None else
        f"v4l2:{initial_source}" if isinstance(initial_source, int)
        and explicit_legacy_source else None
    )}
    initial_camera_name = (
        initial_selection.display_name if initial_selection is not None else
        f"Cámara de video #{initial_source}" if isinstance(initial_source, int)
        and explicit_legacy_source else
        "Cámara RTSP" if isinstance(initial_source, str) and initial_source.lower().startswith("rtsp://") else
        "Cámara HTTP/MJPEG" if isinstance(initial_source, str) and initial_source.lower().startswith(("http://", "https://")) else
        "Sin cámara seleccionada"
    )
    initial_camera_type = (
        "DroidCam-OBS" if initial_selection is not None and initial_selection.details.get("virtual") else
        "V4L2" if isinstance(initial_source, int) and explicit_legacy_source else
        "HTTP/MJPEG" if isinstance(initial_source, str) and initial_source.lower().startswith(("http://", "https://")) else
        "RTSP" if isinstance(initial_source, str) and initial_source.lower().startswith("rtsp://") else "N/D"
    )
    if args.mock_camera:
        adapter = MockUIRuntimeAdapter(
            delay=float(settings["worker"]["mock_frame_delay_seconds"]),
            thumbnail_capture_enabled=thumbnail_manager.enabled,
        )
    else:
        policy_path = Path(settings["guided_capture"]["policy_file"])
        quality_path = Path(settings["quality"]["profile_file"])
        adapter = RealUIRuntimeAdapter(
            source=initial_source,
            policy=load_guided_profile(policy_path).policy,
            quality_profile_path=quality_path,
            cancel_event=cancel_event,
            thumbnail_capture_enabled=thumbnail_manager.enabled,
        )
    session = LiveFaceSession(
        adapter, controller,
        event_queue_size=int(settings["queues"]["event_size"]),
        command_queue_size=int(settings["queues"]["command_size"]),
        close_timeout_seconds=float(settings["worker"]["close_timeout_seconds"]),
        mirrored_source=bool(settings["guided_capture"].get("mirrored_source", False)),
        persistence=persistence,
        manifest_path=manifest_path,
        archive_path=archive_path,
        people_controller=people_controller,
        thumbnail_manager=thumbnail_manager,
        detection_event_service=detection_event_service,
        camera_id=(current_camera_source["id"] or "camera"),
        administrative_status_resolver=(None if person_repository is None else
            lambda person_id: (
                record.status.value if (record := person_repository.get_by_person_id(person_id))
                is not None else None
            )),
        stability_tracker=stability_tracker,
        identification_policy_engine=identification_policy_engine,
        decision_orchestrator=decision_orchestrator,
        action_executor=action_executor,
        detection_event_logging_via_executor=detection_logging_via_executor,
        application_event_bus=application_events,
        identification_presentation=identification_controller,
        manual_enrollment_capture=bool(
            settings["guided_capture"].get("manual_capture", True)
        ),
        enrollment_minimum_quality_score=float(
            settings["guided_capture"].get("minimum_quality_score", 75.0)
        ),
        enrollment_stability_frames=int(
            settings["guided_capture"].get("stability_frames", 3)
        ),
        profile_photo_after_enrollment=True,
        photo_controller=photo_controller,
        photo_capture_policy=AutomaticPhotoPolicy(**settings.get("photo_capture", {})),
        stay_alive_disconnected=True,
        camera_display_name=initial_camera_name,
        camera_source_type=initial_camera_type,
        presentation_frame_sink=presentation_frame_store.publish,
    )
    people_window: dict[str, PeopleManagerWindow] = {}
    configuration_window: dict[str, object] = {}
    camera_window: dict[str, CameraSelectionWindow] = {}
    selector_discovery = CameraSourceDiscovery(
        replace(camera_discovery_config, auto_discovery=True),
        occupied_source_id=lambda: current_camera_source["id"],
        # Network availability is tested only when the user explicitly asks;
        # refreshing a browser/Tk list must never serially timeout every URL.
        probe_network_sources=False,
    )
    camera_persistence = (None if configuration_service is None else
                          CameraConfigurationPersistence(configuration_service))
    camera_selection = CameraSelectionController(
        selector_discovery, switch_allowed=lambda: session.camera_switch_allowed,
        persist_config=None if camera_persistence is None else camera_persistence.save,
    )
    if initial_selection_result is not None:
        camera_selection.sources = initial_selection_result.sources
    profile_windows: dict[str, PersonProfileWindow] = {}
    history_window: dict[str, DetectionHistoryWindow] = {}
    attendance_window: dict[str, AttendanceHistoryWindow] = {}
    report_window: dict[str, ReportWindow] = {}
    backup_window: dict[str, BackupWindow] = {}
    system_health_window: dict[str, SystemHealthWindow] = {}
    audit_window: dict[str, AuditLogWindow] = {}
    closing = False
    def register(form):
        if not session.start_enrollment(form):
            app.status.configure(text="No se pudo encolar el registro")
            return False
        return True

    def web_update_person(person_id: str, payload: object):
        if not isinstance(payload,dict):raise ValueError("Datos civiles inválidos.")
        result=people_controller.update_person(
            person_id,str(payload.get("first_name",""))[:120],
            str(payload.get("last_name",""))[:120],
            str(payload.get("cedula","")).strip()[:20] or None,
            phone=str(payload.get("phone",""))[:40],
            email=str(payload.get("email",""))[:254],
        )
        requested=str(payload.get("status","")).upper()
        if requested == "INACTIVE":requested="DISABLED"
        if result.success and requested in {"ACTIVE","DISABLED"}:
            current=people_controller.details(person_id).summary.civil_status
            if current != requested:
                result=people_controller.set_administrative_status(
                    person_id,PersonStatus(requested),confirmed=True,
                )
        return result

    def web_person_photo(person_id: str, payload: object) -> bool:
        if not isinstance(payload,dict) or payload.get("confirmed") is not True:
            raise ValueError("Se requiere confirmación.")
        return session.start_person_photo(person_id)

    def web_person_face(person_id: str, payload: object) -> bool:
        if not isinstance(payload,dict) or payload.get("confirmed") is not True:
            raise ValueError("Se requiere confirmación.")
        return session.start_face_replacement(person_id)

    def reactivate_person(person_id: str) -> bool:
        result = people_controller.set_administrative_status(
            person_id, PersonStatus.ACTIVE, confirmed=True,
        )
        return bool(result.success)

    def register_existing_person_face(person_id: str) -> bool:
        logging.getLogger(__name__).info(
            "people_face_callback_invoked person_ref=%s workflow_state=%s",
            uuid.uuid5(uuid.NAMESPACE_OID, person_id).hex[:12],
            people_controller.state.value,
        )
        return session.start_existing_person_enrollment(person_id)

    def close():
        nonlocal closing
        if closing:return
        closing=True
        popup_action_adapter.close()
        window = people_window.pop("window", None)
        if window is not None and window.window.winfo_exists():
            window.close()
        config_window = configuration_window.pop("window", None)
        if config_window is not None and config_window.window.winfo_exists():
            config_window.close()
        source_window = camera_window.pop("window", None)
        if source_window is not None and source_window.window.winfo_exists():
            source_window.close()
        for profile in tuple(profile_windows.values()):
            if profile.window.winfo_exists():
                profile.close()
        profile_windows.clear()
        event_window = history_window.pop("window", None)
        if event_window is not None and event_window.window.winfo_exists():
            event_window.close()
        attendance_view=attendance_window.pop("window",None)
        if attendance_view is not None and attendance_view.window.winfo_exists():attendance_view.close()
        reports_view = report_window.pop("window", None)
        if reports_view is not None and reports_view.window.winfo_exists(): reports_view.close()
        backup_view = backup_window.pop("window", None)
        if backup_view is not None and backup_view.window.winfo_exists(): backup_view.close()
        health_view = system_health_window.pop("window", None)
        if health_view is not None and health_view.window.winfo_exists(): health_view.close()
        audit_view=audit_window.pop("window",None)
        if audit_view is not None and audit_view.window.winfo_exists():audit_view.close()
        session.close(float(settings["worker"]["close_timeout_seconds"]))
        security.logout()

    profile_controller = None if person_repository is None else PersonProfileController(
        person_repository, people_controller, people_controller.biometrics, thumbnail_manager,
        attendance_controller,
    )
    history_controller = (None if detection_event_service is None else
        DetectionHistoryController(
            detection_event_service.repository, person_repository, detection_event_service,
            identity_provider, security.authorization,
        ))

    def open_detection_history() -> None:
        if history_controller is None: return
        current = history_window.get("window")
        if current is not None and current.window.winfo_exists():
            current.focus(); return
        history_window["window"] = DetectionHistoryWindow(
            root, history_controller, on_close=lambda: history_window.pop("window", None),
            on_view_person=lambda person_id: open_profile(person_id),
        )

    def open_attendance_history():
        if attendance_controller is None:return
        current=attendance_window.get("window")
        if current is not None and current.window.winfo_exists():current.focus();return
        attendance_window["window"]=AttendanceHistoryWindow(root,attendance_controller,on_close=lambda:attendance_window.pop("window",None),on_view_person=lambda person_id:open_profile(person_id))

    def open_reports():
        if report_controller is None: return
        current = report_window.get("window")
        if current is not None and current.window.winfo_exists(): current.focus(); return
        report_window["window"] = ReportWindow(
            root, report_controller, on_close=lambda: report_window.pop("window", None),
        )

    def close_profile(person_id: str) -> None:
        profile_windows.pop(person_id, None)

    def open_profile(person_id: str) -> None:
        current = profile_windows.get(person_id)
        if current is not None and current.window.winfo_exists():
            current.focus()
            return
        if profile_controller is None:
            open_people(person_id)
            return
        profile_windows[person_id] = PersonProfileWindow(
            root, profile_controller, person_id,
            on_additional=session.start_additional_enrollment,
            thumbnail_manager=thumbnail_manager, on_close=close_profile,
            on_capture_photo=session.start_person_photo,
            can_edit_photo=security.authorization.can(AuthorizationPermission.EDIT_PERSON),
        )

    def open_people(_person_id: str | None = None):
        current = people_window.get("window")
        if current is not None and current.window.winfo_exists():
            current.window.lift()
            current.window.focus_force()
            return
        people_window["window"] = PeopleManagerWindow(
            root, people_controller,
            on_additional=session.start_additional_enrollment,
            on_cancel_additional=session.cancel_enrollment,
            thumbnail_manager=thumbnail_manager,
            on_view_profile=open_profile,
            advanced_controller=people_search_controller,
            on_capture_photo=session.start_person_photo,
            on_replace_face=session.start_face_replacement,
            on_register_face=register_existing_person_face,
            on_reactivate_person=reactivate_person,
            camera_available=session.active_camera_ready,
            can_edit_photo=security.authorization.can(AuthorizationPermission.EDIT_PERSON),
        )

    def open_configuration():
        current = configuration_window.get("window")
        if current is not None and current.window.winfo_exists():
            current.focus()
            return
        if configuration_controller is None:
            configuration_window["window"] = DashboardConfigurationWindow(
                root, build_dashboard_configuration(settings)
            )
        else:
            configuration_window["window"] = ConfigurationWindow(
                root, configuration_controller,
                on_close=lambda: configuration_window.pop("window", None),
            )

    def use_camera(source) -> bool:
        config = camera_config_for_source(source, selector_discovery.config)
        accepted = session.switch_camera(config)
        if accepted:
            current_camera_source["id"] = source.source_id
        return accepted

    def web_camera_probe(payload: object) -> dict[str, object]:
        """Probe a saved source asynchronously, or a form URL before it is saved."""
        if isinstance(payload, dict) and "url" in payload:
            connected, resolution = camera_selection.probe_network_source_details(
                _camera_name(payload), _camera_network_type(payload), _camera_url(payload),
            )
            return {"connected": connected, "resolution": resolution}
        source_id = _camera_id(payload)
        threading.Thread(target=lambda: camera_selection.probe(source_id),
                         name="web-camera-probe", daemon=True).start()
        return {"queued": True}

    def delete_camera(source) -> bool:
        """Remove saved configuration and disconnect only when it is active."""
        source_id=source if isinstance(source,str) else source.source_id
        was_active=current_camera_source["id"] == source_id
        camera_selection.remove_network_source(source_id)
        if was_active:
            disconnected=CameraConfig(
                "Sin cámara seleccionada",CameraType.USB,
                camera_discovery_config.scan_indices+10_000,
                reconnect=ReconnectConfig(enabled=False),
            )
            session.switch_camera(disconnected)
            current_camera_source["id"]=None
        return True

    def open_camera_selection() -> None:
        current = camera_window.get("window")
        if current is not None and current.window.winfo_exists():
            current.focus(); return
        camera_window["window"] = CameraSelectionWindow(
            root, camera_selection, use_camera,
            current_source_id=lambda: current_camera_source["id"],
            on_delete=delete_camera,
            on_close=lambda: camera_window.pop("window", None),
        )

    def finish_startup_camera_discovery() -> None:
        """Apply startup choice after bounded network probes complete."""
        result = camera_selection.refresh()
        available = tuple(source for source in result.sources if source.available)
        if not available:
            return
        if len(available) == 1:
            source = available[0]
            if current_camera_source["id"] != source.source_id:
                use_camera(source)
            return
        if tk_enabled:
            open_camera_selection()

    def start_network_camera_discovery() -> None:
        """Probe saved network sources concurrently without blocking the UI."""
        source_ids = tuple(
            source.source_id for source in selector_discovery.config.network_sources
        )
        if not source_ids:
            root.after(0, finish_startup_camera_discovery)
            return

        def probe_saved_sources() -> None:
            workers = tuple(
                threading.Thread(
                    target=camera_selection.probe, args=(source_id,),
                    name=f"camera-startup-probe-{index}", daemon=True,
                )
                for index, source_id in enumerate(source_ids)
            )
            for worker in workers: worker.start()
            for worker in workers: worker.join()
            root.after(0, finish_startup_camera_discovery)

        threading.Thread(
            target=probe_saved_sources, name="camera-startup-discovery", daemon=True,
        ).start()

    def gallery_summary() -> DashboardGalleryDTO:
        gallery = people_controller.biometrics.gallery
        return DashboardGalleryDTO(
            len(gallery.list_identities()), len(gallery.templates()), people_controller.state.value
        )

    def save_gallery():
        targets_exist = manifest_path.exists() or archive_path.exists()
        overwrite = False
        if targets_exist:
            overwrite = messagebox.askyesno(
                "Sobrescribir galería",
                "La galería local ya existe. ¿Desea sobrescribirla?",
                parent=root,
            )
            if not overwrite:
                return None
        return people_controller.save_changes(overwrite_confirmed=overwrite)

    backup_settings = settings.get("backup", {})
    if not isinstance(backup_settings, dict):
        raise ValueError("backup configuration must be an object")
    for key in ("maximum_archive_size_bytes", "maximum_file_count",
                "operation_history_limit"):
        if int(backup_settings.get(key, 0)) <= 0:
            raise ValueError(f"backup {key} must be positive")
    for key in ("restore_timeout_seconds", "sqlite_snapshot_timeout_seconds"):
        if float(backup_settings.get(key, 0)) <= 0:
            raise ValueError(f"backup {key} must be positive")
    maintenance = ApplicationMaintenanceCoordinator()
    catalog = BackupSourceCatalog(PROJECT_ROOT, settings)
    backup_archive = BackupArchive(
        maximum_archive_size_bytes=int(backup_settings["maximum_archive_size_bytes"]),
        maximum_file_count=int(backup_settings["maximum_file_count"]),
    )
    snapshots = SQLiteSnapshotProvider(
        float(backup_settings["sqlite_snapshot_timeout_seconds"])
    )
    backup_service = BackupService(catalog, backup_archive, snapshots, maintenance,audit_callback=audit("backup"))
    restore_service = RestoreService(catalog, backup_archive, snapshots, maintenance,audit_callback=audit("restore"))

    def quiesce_for_restore() -> None:
        completed = threading.Event(); failure: list[BaseException] = []
        def on_tk_thread() -> None:
            try:
                for mapping in (people_window, configuration_window, profile_windows,
                                history_window, attendance_window, report_window):
                    for item in tuple(mapping.values()):
                        if item.window.winfo_exists(): item.close()
                    mapping.clear()
                maintenance.quiesce(
                    cancel_enrollment=session.cancel_enrollment,
                    close_session=lambda: session.close(
                        float(backup_settings["restore_timeout_seconds"])
                    ),
                    close_windows=lambda: None,
                    cancel_callbacks=lambda: None,
                    timeout_seconds=float(backup_settings["restore_timeout_seconds"]),
                )
            except BaseException as exc:
                failure.append(exc)
            finally:
                completed.set()
        root.after(0, on_tk_thread)
        if not completed.wait(float(backup_settings["restore_timeout_seconds"]) + 1):
            raise RuntimeError("restore quiescence timeout")
        if failure:
            raise failure[0]

    backup_controller = BackupController(
        backup_service, restore_service, security.authorization,
        history_limit=int(backup_settings["operation_history_limit"]),
        prepare_for_restore=quiesce_for_restore,
    )
    if configuration_service is not None:
        configuration_controller = ConfigurationController(
            configuration_service, security.authorization,
            security_disabled=not security.enabled,
            allow_import=bool(manager_settings.get("allow_import", True)),
            allow_export=bool(manager_settings.get("allow_export", True)),
        )

    health_settings = settings.get("system_health", {})
    if not isinstance(health_settings, dict):raise ValueError("system_health configuration must be an object")
    health_enabled = bool(health_settings.get("enabled", False))
    system_health_service = system_health_controller = None
    if health_enabled:
        import math
        for key,upper in (("dashboard_refresh_seconds",3600),("performance_window_seconds",3600),("stale_frame_seconds",300)):
            value=float(health_settings.get(key,0))
            if not math.isfinite(value) or value<=0 or value>upper:raise ValueError(f"system_health {key} is invalid")
        rolling = RollingPerformanceMetrics(float(health_settings["performance_window_seconds"]))
        def queue_depth():return session.visual_queue.qsize()+session.event_queue.qsize()+session.command_queue.qsize()
        sources={item.component_type.value:item.source_path for item in catalog.sources()}
        providers=[
            CameraHealthProvider(enabled=lambda:True,worker_alive=lambda:session.alive,camera_state=lambda:app._dashboard.system.camera_state,last_frame_monotonic=lambda:rolling.last_frame_monotonic,stale_frame_seconds=float(health_settings["stale_frame_seconds"])),
            WorkerHealthProvider(lambda:session.alive,lambda:controller.state.value,lambda:controller.enrollment.active,queue_depth),
            RuntimeHealthProvider(lambda:app._dashboard.system.runtime_state),
            SQLiteDatabaseHealthProvider("people_database",sources["PEOPLE_DATABASE"],enabled=bool(settings.get("person_database",{}).get("enabled",False))),
            SQLiteDatabaseHealthProvider("events_database",sources["DETECTION_EVENTS_DATABASE"],enabled=bool(settings.get("event_history",{}).get("enabled",False))),
            SQLiteDatabaseHealthProvider("attendance_database",sources["ATTENDANCE_DATABASE"],enabled=bool(settings.get("attendance",{}).get("enabled",False))),
            SQLiteDatabaseHealthProvider("users_database",sources["USERS_DATABASE"],enabled=bool(settings.get("security",{}).get("enabled",True))),
            SQLiteDatabaseHealthProvider("audit_database",sources["AUDIT_DATABASE"],enabled=bool(settings.get("audit",{}).get("enabled",False))),
            ApplicationEventBusHealthProvider(application_events,application_event_diagnostics),
            SecurityHealthProvider(security.enabled,security.sessions),
            BackupHealthProvider(bool(backup_settings.get("enabled",False)),maintenance,backup_controller.history),
        ]
        system_health_service=SystemHealthService(providers,rolling)
        system_health_controller=SystemHealthController(system_health_service,security.authorization,security_disabled=not security.enabled,audit_callback=audit("system_health"))

    def open_system_health():
        if system_health_controller is None:return
        current=system_health_window.get("window")
        if current is not None and current.window.winfo_exists():current.focus();return
        system_health_controller.record_viewed()
        system_health_window["window"]=SystemHealthWindow(root,system_health_controller,on_close=lambda:system_health_window.pop("window",None))

    audit_settings=settings.get("audit",{})
    audit_controller=AuditController(audit_service.repository,security.authorization,default_limit=int(audit_settings.get("default_query_limit",200)),maximum_limit=int(audit_settings.get("max_query_limit",1000))) if audit_service.enabled else None
    def open_audit():
        if audit_controller is None:return
        current=audit_window.get("window")
        if current is not None and current.window.winfo_exists():current.focus();return
        audit_window["window"]=AuditLogWindow(root,audit_controller,on_close=lambda:audit_window.pop("window",None))

    def open_backup() -> None:
        current = backup_window.get("window")
        if current is not None and current.window.winfo_exists():
            current.focus(); return
        backup_window["window"] = BackupWindow(
            root, backup_controller,
            on_close=lambda: backup_window.pop("window", None),
            on_restore_success=lambda _result: root.after(0, app.close),
        )

    identification_popup = IdentificationPopupWindow(
        root, identity_provider,
        on_view_person=open_profile,
        on_register=lambda: app.open_form(),
        unknown_timeout_seconds=identification_controller.policy.unknown_popup_timeout_seconds,
        registered_timeout_seconds=float(settings.get("identification_popup", {}).get(
            "registered_popup_timeout_seconds", 60.0)),
        on_unknown_closed=identification_controller.unknown_dismissed,
        on_dismissed=(None if application_events is None else lambda popup_type, reason:
            application_events.publish(PopupDismissedEvent(
                source="identification_popup", session_id=session.session_id,
                run_id=session.session_id, popup_type=popup_type, reason=reason,
            ))),
    )
    if not tk_enabled:
        # Web-only keeps the Tk event-loop host hidden, never a visible modal.
        identification_popup.close()
        identification_popup = None
    if attendance_controller is not None and tk_enabled:
        def show_attendance_popup(event: AttendanceRecordedEvent, attempts: int = 0) -> None:
            if identification_popup.active:
                if attempts < 20:
                    root.after(250, lambda: show_attendance_popup(event, attempts + 1))
                return
            person = identity_provider.get_person(event.person_id)
            name = "Persona registrada" if person is None else person.display_name
            local = event.timestamp.astimezone(ZoneInfo("America/Guayaquil"))
            if event.attendance_event_type == "CHECK_IN":
                title = "✓ ENTRADA REGISTRADA"
                body = f"{name}\nHora: {local:%H:%M:%S}"
            else:
                title = "✓ SALIDA REGISTRADA"
                detail = attendance_controller.detail(event.person_id, local.date())
                worked = 0 if detail is None else detail.day.worked_seconds
                body = f"{name}\nHora salida: {local:%H:%M:%S}\nHoras trabajadas: {worked // 3600:02d}:{worked % 3600 // 60:02d}"
            messagebox.showinfo(title, body, parent=root)
        application_events.subscribe(AttendanceRecordedEvent,
            lambda event: root.after(0, lambda: show_attendance_popup(event)))

    configured_web=WebDashboardPolicy.from_mapping(settings.get("web_dashboard",{}))
    web_local_url=(f"http://127.0.0.1:{configured_web.port}"
                   if configured_web.enabled else None)
    lan_ip=detect_lan_ip() if configured_web.enabled else None
    web_lan_url=(f"http://{lan_ip}:{configured_web.port}" if lan_ip else None)
    app = LocalFaceTkApp(
        root,
        on_register=register,
        on_cancel=session.cancel_enrollment,
        on_capture_enrollment=session.capture_enrollment_sample,
        on_view_person=open_profile,
        on_additional_enrollment=session.start_additional_enrollment,
        on_replace_face=session.start_face_replacement,
        on_reactivate_person=reactivate_person,
        on_start_photo=session.start_person_photo,
        on_capture_photo=session.capture_person_photo,
        on_confirm_photo=session.confirm_person_photo,
        on_retake_photo=session.retake_person_photo,
        on_cancel_photo=session.cancel_person_photo,
        enrollment_target_samples=int(settings["guided_capture"]["target_samples"]),
        manual_enrollment_capture=bool(
            settings["guided_capture"].get("manual_capture", True)
        ),
        profile_photo_after_enrollment=True,
        on_close=close,
        on_people=open_people,
        on_configuration=open_configuration,
        on_camera=open_camera_selection,
        on_retry_camera=session.retry_camera,
        on_save_gallery=save_gallery,
        get_gallery=gallery_summary,
        dashboard_settings=settings.get("dashboard", {}),
        video_presentation=VideoPresentation(**_video_presentation_settings(settings)),
        photo_capture_mode=str(settings.get("photo_capture", {}).get("mode", "automatic")),
        get_thumbnail=thumbnail_manager.load,
        identification_controller=identification_controller,
        identification_popup=identification_popup if tk_enabled else None,
        popup_mode="action_executor" if popups_via_executor else "legacy",
        get_popup_requests=popup_action_adapter.drain,
        clear_popup_requests=popup_action_adapter.clear,
        on_registration_form_state=session.set_event_history_suspended,
        get_detection_events=(None if history_controller is None else
                              lambda: history_controller.recent_identifications(5)),
        on_detection_history=open_detection_history,
        get_attendance_summary=(None if attendance_controller is None else
                                attendance_controller.attendance_today),
        on_attendance_history=open_attendance_history,
        on_reports=open_reports,
        get_daily_report=(None if report_controller is None else
                          lambda: report_controller.service.daily_report(
                              Clock().local_today(report_controller.service.policy.presentation_timezone)
                          )),
        report_refresh_seconds=float(
            settings.get("reports", {}).get("dashboard_refresh_seconds", 30)
        ),
        can=lambda permission: security.authorization.can(AuthorizationPermission(permission)),
        on_backup=open_backup,
        system_health_controller=system_health_controller,
        system_health_service=system_health_service,
        on_system_health=open_system_health,
        system_health_refresh_seconds=float(health_settings.get("dashboard_refresh_seconds",10)),
        on_audit=open_audit if audit_controller is not None else None,
        audit_controller=audit_controller,
        audit_refresh_seconds=float(audit_settings.get("dashboard_refresh_seconds",30.0)),
        local_validation_login_bypass=local_validation_bypass,
        appliance_mode=appliance_mode,
        web_dashboard_local_url=web_local_url,
        web_dashboard_lan_url=web_lan_url,
    )
    app.web_only=not tk_enabled
    dashboard_coordinator = None
    if history_controller is not None and attendance_controller is not None and report_controller is not None:
        professional_dashboard = ProfessionalDashboardController(
            history_controller,attendance_controller,report_controller,identity_provider,
            security.authorization,system_health_service,
        )
        dashboard_settings=settings.get("dashboard",{})
        dashboard_coordinator=DashboardRefreshCoordinator(
            root,professional_dashboard,app.professional_live_state,
            app.show_professional_dashboard,
            dashboard_seconds=float(dashboard_settings.get("refresh_seconds",5.0)),
            statistics_seconds=float(dashboard_settings.get("statistics_refresh_seconds",10.0)),
        )
        application_events.subscribe(DetectionEventStoredEvent,dashboard_coordinator.invalidate)
        application_events.subscribe(AttendanceRecordedEvent,dashboard_coordinator.invalidate)
        app.set_dashboard_refresh_coordinator(dashboard_coordinator)
    web_server=None
    web_policy=configured_web
    if web_policy.enabled:
        web_controller=WebDashboardController(
            lambda:None if dashboard_coordinator is None else dashboard_coordinator.last_snapshot,
            people=people_search_controller,history=history_controller,
            attendance=attendance_controller,reports=report_controller,
            system_health=system_health_controller,identity_provider=identity_provider,
            camera_provider=lambda:{
                "state":app._dashboard.system.camera_state,
                "name":app._camera_source_name,
                "type":app._camera_source_type,
                "source":current_camera_source.get("id") or "N/D",
            },
            presentation_provider=lambda:getattr(app,"latest_monitoring",None),
            operational_state_provider=lambda dto: operational_presentation_state(
                camera_state=app._dashboard.system.camera_state,
                frame_available=(lambda status: bool(
                    status["available"] and not status["stale"]
                ))(presentation_frame_store.status()),
                monitoring=dto,
                gallery_identity_count=app._dashboard.gallery.identities,
            ),
            actions={
                "cameras": lambda: camera_selection.refresh().sources,
                "camera_select": lambda payload: use_camera(camera_selection.use(_camera_id(payload))),
                "camera_preferred": lambda payload: camera_selection.set_preferred(_camera_id(payload)),
                "camera_network": lambda payload: camera_selection.add_network_source(
                    _camera_name(payload), _camera_network_type(payload), _camera_url(payload)),
                "camera_network_delete": delete_camera,
                "camera_network_update": lambda payload: camera_selection.update_network_source(
                    _camera_id(payload),_camera_name(payload),_camera_network_type(payload),
                    _camera_url(payload),preferred=bool(payload.get("preferred",False))),
                "camera_probe": web_camera_probe,
                "enrollment_person": lambda payload: register(_web_registration_form(payload)),
                "enrollment_capture_start": lambda _payload: session.capture_enrollment_sample(),
                "enrollment_cancel": lambda _payload: session.cancel_enrollment(),
                "enrollment_status": lambda:getattr(app,"latest_enrollment_event",None),
                "enrollment_photo_start": lambda _payload: session.start_person_photo(
                    getattr(getattr(app,"latest_enrollment_event",None),"person_id","")),
                "enrollment_photo_capture": lambda _payload: session.capture_person_photo(),
                "enrollment_photo_confirm": lambda _payload: session.confirm_person_photo(),
                "person_update": web_update_person,
                "person_delete": lambda person_id,confirmed:
                    people_controller.delete_person(person_id,confirmed=confirmed),
                "person_photo": web_person_photo,
                "person_face": web_person_face,
                "shutdown": lambda _payload: root.after(0, app.close) or True,
            },
            audit=audit_controller, backups=backup_controller,
            configuration=configuration_controller,
        )
        web_server=WebDashboardServer(
            web_policy,web_controller,presentation_frame_store,printer=lambda _message: None,
        )
        if not web_server.start():
            LOGGER.warning("Web dashboard did not start; Tk and Runtime continue")
        else:
            print("\nFASTVISION AI INICIADO\n\n"
                  f"Dashboard de escritorio: {'ACTIVO' if tk_enabled else 'INACTIVO'}\n\n"
                  "Dashboard web disponible en:\n\n"
                  f"{web_server.local_url}\n\n"
                  "Para acceder desde otro equipo:\n\n"
                  f"http://IP_DEL_JETSON:{web_policy.port}\n")
    app.set_appliance_shutdown(
        None if web_server is None else web_server.close,
        presentation_frame_store.close,
    )
    if not tk_enabled:root.withdraw()
    app.show_monitoring(controller.monitoring.empty())
    app.status.configure(text=startup.message)
    if startup.error is not None:
        app.show_error(startup.error)
    elif synchronization_error:
        app.show_error(ErrorDTO(
            UIState.ERROR, UIErrorCode.PERSISTENCE_ERROR, GALLERY_SYNC_ERROR, True,
        ))
    session.start()
    start_network_camera_discovery()
    app.poll_session(session, int(settings["worker"]["ui_poll_interval_ms"]))
    if args.mock_auto_enroll:
        mock_form = validate_registration_form(
            "Temporary", "Mock", None, consent_confirmed=True, persist_locally=False,
            cedula="1710034065",
        )
        root.after(250, register, mock_form)
    if args.mock_duration is not None:
        root.after(int(args.mock_duration * 1_000), app.close)
    root.mainloop()
    if args.mock_camera:
        gallery = controller.monitoring.gallery
        print(json.dumps({
            "mock_camera": True,
            "identities_in_memory": len(gallery.list_identities()),
            "templates_in_memory": len(gallery.templates()),
            "controller_state": controller.state.value,
            "worker_alive": session.alive,
            "adapter_closed": adapter.closed,
            "automatic_decision_enabled": False,
            "persistence_requested": False,
        }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
