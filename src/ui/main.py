"""Composition helpers for the local experimental UI.

The camera/biometric producer runs outside Tk's main thread and passes only safe
DTOs plus a transient RGB presentation frame to :class:`LocalFaceTkApp`. This
module intentionally does not choose a biometric threshold or persist by default.
"""

from __future__ import annotations

import argparse
import json
import threading
from pathlib import Path

from src.engine.enrollment import EnrollmentPolicy, EnrollmentService
from src.engine.gallery import FaceGallery, FaceMatcher, MatchPolicy
from src.engine.gallery.persistence import GalleryPersistence
from src.core.config_manager import PROJECT_ROOT
from src.ui.controller import LocalFaceUIController
from src.ui.enrollment_workflow import LocalEnrollmentWorkflow
from src.ui.live_session import LiveFaceSession
from src.ui.mock_runtime import MockUIRuntimeAdapter
from src.ui.recognition_session import ExperimentalRecognitionSession
from src.ui.runtime_adapter import RealUIRuntimeAdapter
from src.ui.tk_app import LocalFaceTkApp
from src.ui.form_validation import validate_registration_form
from src.validation.guided_face_capture import load_guided_profile


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


def build_controller(config_path: Path) -> LocalFaceUIController:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    enrollment_config = config["enrollment"]
    gallery = FaceGallery()
    matcher = FaceMatcher(
        top_k=int(config["matcher"]["top_k"]),
        policy=MatchPolicy(automatic_decision_enabled=False, threshold=None),
    )
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
    return LocalFaceUIController(ExperimentalRecognitionSession(gallery, matcher), workflow)


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
    args = parser.parse_args()
    if (args.mock_auto_enroll or args.mock_duration is not None) and not args.mock_camera:
        parser.error("mock automation options require --mock-camera")
    if args.mock_duration is not None and args.mock_duration <= 0:
        parser.error("--mock-duration must be positive")
    settings = json.loads(args.config.read_text(encoding="utf-8"))
    controller = build_controller(args.config)
    persistence, manifest_path, archive_path = build_persistence(settings)
    try:
        import tkinter as tk
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Tkinter no está disponible en este entorno; no se instalaron dependencias"
        ) from exc
    cancel_event = threading.Event()
    if args.mock_camera:
        adapter = MockUIRuntimeAdapter(delay=float(settings["worker"]["mock_frame_delay_seconds"]))
    else:
        policy_path = Path(settings["guided_capture"]["policy_file"])
        quality_path = Path(settings["quality"]["profile_file"])
        adapter = RealUIRuntimeAdapter(
            source=settings["camera"]["source"],
            policy=load_guided_profile(policy_path).policy,
            quality_profile_path=quality_path,
            cancel_event=cancel_event,
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
    )
    root = tk.Tk()
    def register(form):
        if not session.start_enrollment(form):
            app.status.configure(text="No se pudo encolar el registro")

    def close():
        session.close()

    app = LocalFaceTkApp(
        root,
        on_register=register,
        on_cancel=session.cancel_enrollment,
        on_close=close,
    )
    app.show_monitoring(controller.monitoring.empty())
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
