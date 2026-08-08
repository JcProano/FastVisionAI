"""Composition helpers for the local experimental UI.

The camera/biometric producer runs outside Tk's main thread and passes only safe
DTOs plus a transient RGB presentation frame to :class:`LocalFaceTkApp`. This
module intentionally does not choose a biometric threshold or persist by default.
"""

from __future__ import annotations

import argparse
import json
import threading
from dataclasses import dataclass
from pathlib import Path

from src.engine.enrollment import EnrollmentPolicy, EnrollmentService
from src.engine.gallery import FaceGallery, FaceMatcher, MatchPolicy
from src.engine.gallery.persistence import GalleryPersistence
from src.engine.recognition import RecognitionPolicy, RecognitionService
from src.core.config_manager import PROJECT_ROOT
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
from src.ui.dashboard.config_window import DashboardConfigurationWindow
from src.ui.dashboard.contracts import DashboardConfigurationDTO, DashboardGalleryDTO
from src.ui.thumbnails import ThumbnailManager
from src.ui.identification import (
    IdentificationPopupPolicy, IdentificationPresentationController,
    PeopleThumbnailIdentityInfoProvider,
)
from src.ui.identification.tk_popup import IdentificationPopupWindow
from src.validation.guided_face_capture import load_guided_profile


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
    return LocalFaceUIController(ExperimentalRecognitionSession(recognition_service), workflow)


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
    settings = json.loads(args.config.read_text(encoding="utf-8"))
    startup = load_startup_gallery(settings, force_load=args.load_gallery)
    controller = build_controller(args.config, startup.gallery)
    persistence, manifest_path, archive_path = build_persistence(settings)
    thumbnail_manager = build_thumbnail_manager(settings)
    people_controller = PeopleManagerController(
        startup.gallery, controller.enrollment.enrollment,
        GalleryPersistence(enabled=True), manifest_path, archive_path,
    )
    popup_settings = settings.get("identification_popup", {})
    if not isinstance(popup_settings, dict):
        raise ValueError("identification_popup configuration must be an object")
    identity_provider = PeopleThumbnailIdentityInfoProvider(
        people_controller, thumbnail_manager,
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
        ),
        identity_provider,
    )
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Tkinter no está disponible en este entorno; no se instalaron dependencias"
        ) from exc
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
    )
    root = tk.Tk()
    people_window: dict[str, PeopleManagerWindow] = {}
    configuration_window: dict[str, DashboardConfigurationWindow] = {}
    def register(form):
        if not session.start_enrollment(form):
            app.status.configure(text="No se pudo encolar el registro")

    def close():
        window = people_window.pop("window", None)
        if window is not None and window.window.winfo_exists():
            window.close()
        config_window = configuration_window.pop("window", None)
        if config_window is not None and config_window.window.winfo_exists():
            config_window.close()
        session.close()

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
        )

    def open_configuration():
        current = configuration_window.get("window")
        if current is not None and current.window.winfo_exists():
            current.focus()
            return
        configuration_window["window"] = DashboardConfigurationWindow(
            root, build_dashboard_configuration(settings)
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

    identification_popup = IdentificationPopupWindow(
        root, identity_provider,
        on_view_person=open_people,
        on_register=lambda: app.open_form(),
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
            id_factory=lambda: "person_mock_ui_smoke",
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
