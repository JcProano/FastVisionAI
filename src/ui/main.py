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
from dataclasses import dataclass
from datetime import date
from pathlib import Path

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
    PopupDismissedEvent,
)
from src.ui.controller import LocalFaceUIController
from src.ui.enrollment_workflow import LocalEnrollmentWorkflow
from src.ui.live_session import LiveFaceSession
from src.ui.mock_runtime import MockUIRuntimeAdapter
from src.ui.recognition_session import ExperimentalRecognitionSession
from src.ui.runtime_adapter import RealUIRuntimeAdapter
from src.ui.tk_app import LocalFaceTkApp
from src.ui.form_validation import validate_registration_form
from src.ui.contracts import ErrorDTO, UIErrorCode, UIState
from src.ui.people.controller import PeopleManagerController
from src.ui.people.tk_window import PeopleManagerWindow
from src.ui.people.database_controller import DatabasePeopleManagerController
from src.ui.dashboard.config_window import DashboardConfigurationWindow
from src.ui.dashboard.contracts import DashboardConfigurationDTO, DashboardGalleryDTO
from src.ui.thumbnails import ThumbnailManager
from src.ui.identification import (
    IdentificationPopupPolicy, IdentificationPresentationController,
    PeopleThumbnailIdentityInfoProvider,
)
from src.ui.identification.tk_popup import IdentificationPopupWindow
from src.ui.identification import SQLiteThumbnailIdentityInfoProvider
from src.core.person_database import (
    PersonRepository, SQLiteIdentityDataProvider,
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
    DetectionEventServiceActionAdapter, IdentificationPopupActionAdapter,
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
    repository.initialize()  # failure deliberately aborts administrative startup
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
    return (
        persistence.export,
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
    if recognition_config.get("automatic_decision_enabled") is not False:
        raise ValueError("experimental UI requires automatic_decision_enabled=false")
    if recognition_config.get("match_threshold") is not None:
        raise ValueError("experimental UI requires match_threshold=null")
    if recognition_config.get("ambiguity_margin") is not None:
        raise ValueError("experimental UI requires ambiguity_margin=null")
    gallery = gallery if gallery is not None else FaceGallery()
    matcher = FaceMatcher(
        top_k=int(config["matcher"]["top_k"]),
        policy=MatchPolicy(automatic_decision_enabled=False, threshold=None),
    )
    recognition_policy = RecognitionPolicy(
        automatic_decision_enabled=False,
        match_threshold=None,
        ambiguity_margin=None,
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
        ExperimentalRecognitionSession(recognition_service), workflow, coordinator,
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


def build_reports(settings, people, detections, attendance, authorization=None):
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
    return ReportController(ReportService(people, detections, attendance, policy), authorization=authorization)


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
    return DashboardConfigurationDTO(
        str(camera.get("source", "N/D")), str(camera.get("resolution", "N/D")),
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
    if settings.get("profile_name") == "local_face_validation_prod" and args.mock_camera:
        parser.error("production profile does not allow mock camera")
    security = build_security(settings)
    audit_service=build_audit(settings)
    def audit(source):return AuditCallbackAdapter(audit_service,security.sessions.context,source)
    security.audit_callback=audit("security")
    if configuration_service is not None:configuration_service.audit=audit("configuration")
    application_events, application_event_diagnostics = build_application_events(settings)
    startup = load_startup_gallery(settings, force_load=args.load_gallery)
    person_repository = build_person_repository(settings)
    detection_event_service = build_detection_event_service(settings)
    attendance_controller = build_attendance(
        settings, person_repository, authorization=security.authorization,
    )
    report_controller = build_reports(
        settings, person_repository,
        None if detection_event_service is None else detection_event_service.repository,
        None if attendance_controller is None else attendance_controller.repository,
        security.authorization,
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
    people_controller = PeopleManagerController(
        startup.gallery, controller.enrollment.enrollment,
        GalleryPersistence(enabled=True), manifest_path, archive_path,
    )
    if person_repository is not None:
        people_controller = DatabasePeopleManagerController(  # type: ignore[assignment]
            person_repository, people_controller, security.authorization,audit("people"),
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
        identification_presentation=identification_controller,
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
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Tkinter no está disponible en este entorno; no se instalaron dependencias"
        ) from exc
    root = tk.Tk()
    if security.enabled:
        root.withdraw()
        if not LoginWindow(root, security).run():
            root.destroy()
            return 0
        root.deiconify()
    # Real Runtime/Camera ownership is deliberately constructed only after login.
    cancel_event = threading.Event()
    if args.mock_camera:
        adapter = MockUIRuntimeAdapter(
            delay=float(settings["worker"]["mock_frame_delay_seconds"]),
            thumbnail_capture_enabled=thumbnail_manager.enabled,
        )
    else:
        policy_path = Path(settings["guided_capture"]["policy_file"])
        quality_path = Path(settings["quality"]["profile_file"])
        adapter = RealUIRuntimeAdapter(
            source=settings["camera"]["source"],
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
        camera_id=str(settings["camera"].get("source", "camera")),
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
    )
    people_window: dict[str, PeopleManagerWindow] = {}
    configuration_window: dict[str, object] = {}
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
        ))

    def open_detection_history() -> None:
        if history_controller is None: return
        current = history_window.get("window")
        if current is not None and current.window.winfo_exists():
            current.focus(); return
        history_window["window"] = DetectionHistoryWindow(
            root, history_controller, on_close=lambda: history_window.pop("window", None),
        )

    def open_attendance_history():
        if attendance_controller is None:return
        current=attendance_window.get("window")
        if current is not None and current.window.winfo_exists():current.focus();return
        attendance_window["window"]=AttendanceHistoryWindow(root,attendance_controller,on_close=lambda:attendance_window.pop("window",None))

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

    def gallery_summary() -> DashboardGalleryDTO:
        listing = people_controller.list_people()
        return DashboardGalleryDTO(
            listing.total_identities, listing.total_templates, listing.state.value
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
        on_unknown_closed=identification_controller.unknown_dismissed,
        on_dismissed=(None if application_events is None else lambda popup_type, reason:
            application_events.publish(PopupDismissedEvent(
                source="identification_popup", session_id=session.session_id,
                run_id=session.session_id, popup_type=popup_type, reason=reason,
            ))),
    )

    app = LocalFaceTkApp(
        root,
        on_register=register,
        on_cancel=session.cancel_enrollment,
        on_close=close,
        on_people=open_people,
        on_configuration=open_configuration,
        on_save_gallery=save_gallery,
        get_gallery=gallery_summary,
        dashboard_settings=settings.get("dashboard", {}),
        get_thumbnail=thumbnail_manager.load,
        identification_controller=identification_controller,
        identification_popup=identification_popup,
        popup_mode="action_executor" if popups_via_executor else "legacy",
        get_popup_requests=popup_action_adapter.drain,
        clear_popup_requests=popup_action_adapter.clear,
        on_registration_form_state=session.set_event_history_suspended,
        get_detection_events=(None if history_controller is None else
                              lambda: history_controller.recent(10)),
        on_detection_history=open_detection_history,
        get_attendance_summary=(None if attendance_controller is None else
                                attendance_controller.daily_summary),
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
    )
    app.show_monitoring(controller.monitoring.empty())
    app.status.configure(text=startup.message)
    if startup.error is not None:
        app.show_error(startup.error)
    session.start()
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
