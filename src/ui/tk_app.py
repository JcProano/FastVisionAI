"""Tkinter presentation layer; it never owns biometric arrays or model objects."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import time
from typing import Any

try:  # Tk is an optional OS component and is not required by headless tests.
    import tkinter as tk
    from tkinter import messagebox, ttk
except ModuleNotFoundError:  # pragma: no cover - branch depends on Python build
    tk = None  # type: ignore[assignment]
    messagebox = None  # type: ignore[assignment]
    ttk = None  # type: ignore[assignment]

from src.ui.contracts import (
    EnrollmentProgressDTO,
    EnrollmentResultDTO,
    ErrorDTO,
    MonitoringDTO,
    RegistrationFormData,
    RuntimeStatusDTO,
)
from src.ui.form_validation import (
    RegistrationFormError,
    validate_registration_form,
)
from src.ui.people.contracts import PeopleOperationResultDTO
from src.ui.dashboard.contracts import DashboardGalleryDTO
from src.ui.dashboard.state import DashboardStateStore
from src.ui.thumbnails import ThumbnailDTO
from src.ui.thumbnails.presentation import thumbnail_to_ppm


@dataclass(frozen=True, slots=True)
class MonitoringText:
    headline: str
    candidate: str
    similarity: str
    decision: str
    quality: str


def monitoring_text(dto: MonitoringDTO) -> MonitoringText:
    candidate = dto.candidate_display_name or (
        dto.message if dto.message in {
            "Sin candidatos registrados", "Sin candidatos compatibles",
        } else "Sin candidatos registrados"
    )
    similarity = "—" if dto.similarity is None else f"{dto.similarity:.4f}"
    quality = "—" if dto.quality_score is None else f"{dto.quality_score:.1f}/100"

    return MonitoringText(
        dto.message,
        candidate,
        similarity,
        "Decisión automática: deshabilitada / NOT_EVALUATED",
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
        on_close: Callable[[], None],
        on_people: Callable[[], None] | None = None,
        on_configuration: Callable[[], None] | None = None,
        on_save_gallery: Callable[[], object] | None = None,
        get_gallery: Callable[[], DashboardGalleryDTO] | None = None,
        dashboard_settings: dict[str, object] | None = None,
        get_thumbnail: Callable[[str], ThumbnailDTO] | None = None,
    ) -> None:
        if tk is None or ttk is None:
            raise RuntimeError(
                "Tkinter no está disponible en este Python; use mocks/headless o "
                "un intérprete del sistema con soporte Tk"
            )

        self.root = root
        self._on_register = on_register
        self._on_cancel = on_cancel
        self._on_close = on_close
        self._on_people = on_people
        self._on_configuration = on_configuration
        self._on_save_gallery = on_save_gallery
        self._get_gallery = get_gallery
        self._get_thumbnail = get_thumbnail
        self._thumbnail_person_id: str | None = None
        self._thumbnail_photo: tk.PhotoImage | None = None

        self._form: tk.Toplevel | None = None
        self._photo: tk.PhotoImage | None = None
        settings = dashboard_settings or {}
        self._dashboard = DashboardStateStore(
            int(settings.get("history_limit", 100)),
            float(settings.get("event_debounce_seconds", 2.0)),
        )
        self._history_rendered: tuple[object, ...] = ()
        self._diagnostic_visible = False
        self._metrics_refresh_seconds = float(settings.get("metrics_refresh_ms", 250)) / 1000.0
        self._last_dashboard_refresh = float("-inf")

        root.title("FastVisionAI — Dashboard local experimental")
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
        root.rowconfigure(1, weight=1)
        header = ttk.Frame(root, padding=(12, 8)); header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="FASTVISION AI", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        self.header_state = ttk.Label(header, text="Cámara ●  Runtime ●")
        self.header_state.grid(row=0, column=1, sticky="e")

        body = ttk.Frame(root, padding=(10, 4)); body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=3); body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)
        video_card = ttk.LabelFrame(body, text="VIDEO EN VIVO", padding=6)
        video_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        video_card.columnconfigure(0, weight=1); video_card.rowconfigure(0, weight=1)
        self.video = ttk.Label(video_card, text="Vista local sin frame", anchor="center")
        self.video.grid(row=0, column=0, sticky="nsew")

        side = ttk.Frame(body); side.grid(row=0, column=1, sticky="nsew")
        system_card = ttk.LabelFrame(side, text="Estado del sistema", padding=8)
        system_card.pack(fill="x", pady=(0, 6))
        self.runtime_status = ttk.Label(system_card, text="Cámara: N/D\nRuntime: N/D\nYuNet: N/D\nArcFace: N/D")
        self.runtime_status.pack(anchor="w")
        self.gallery_status = ttk.Label(system_card, text="Personas: 0\nTemplates: 0")
        self.gallery_status.pack(anchor="w", pady=(6, 0))

        candidate_card = ttk.LabelFrame(side, text="Candidato experimental", padding=8)
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

        history_card = ttk.LabelFrame(side, text="Historial temporal", padding=6)
        history_card.pack(fill="both", expand=True, pady=6)
        self.history = tk.Listbox(history_card, height=6, activestyle="none")
        self.history.pack(fill="both", expand=True)

        self.diagnostic_card = ttk.LabelFrame(root, text="Diagnóstico de calidad", padding=6)
        self.diagnostic_values = ttk.Label(self.diagnostic_card, text="N/D")
        self.diagnostic_values.pack(anchor="w")

        metrics_card = ttk.LabelFrame(root, text="Métricas de sesión", padding=6)
        metrics_card.grid(row=3, column=0, sticky="ew", padx=10, pady=4)
        self.metrics = ttk.Label(metrics_card, text="Captura FPS: N/D | Pipeline FPS: N/D | Latencia inferencia: N/D")
        self.metrics.pack(anchor="w")

        actions = ttk.Frame(root, padding=(10, 6)); actions.grid(row=4, column=0, sticky="ew")
        self.register_button = ttk.Button(actions, text="Registrar rostro", command=self.open_form)
        self.register_button.pack(side="left", padx=3)
        self.people_button = ttk.Button(actions, text="Personas registradas", command=on_people or (lambda: None))
        self.people_button.pack(side="left", padx=3)
        ttk.Button(actions, text="Diagnóstico", command=self.toggle_diagnostic).pack(side="left", padx=3)
        ttk.Button(actions, text="Configuración", command=on_configuration or (lambda: None)).pack(side="left", padx=3)
        ttk.Button(actions, text="Guardar galería", command=self._save_gallery).pack(side="left", padx=3)
        self.cancel_button = ttk.Button(actions, text="Cancelar", command=self._cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=3)
        ttk.Button(actions, text="Salir", command=self.close).pack(side="right", padx=3)

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

    def show_progress(
        self,
        dto: EnrollmentProgressDTO,
    ) -> None:
        self.status.configure(
            text=(
                f"{dto.instruction} — "
                f"{dto.accepted_samples}/{dto.target_samples}"
            )
        )

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
        self.status.configure(text=dto.message)
        self.candidate.configure(text=dto.display_name)

        self.register_button.configure(
            state="normal"
        )

        self.cancel_button.configure(
            state="disabled"
        )

    def show_error(
        self,
        dto: ErrorDTO,
    ) -> None:
        self.status.configure(text=dto.message)

        if not dto.recoverable:
            self.register_button.configure(
                state="disabled"
            )

    def show_runtime_status(
        self,
        dto: RuntimeStatusDTO,
    ) -> None:
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

    def poll_session(
        self,
        session: Any,
        interval_ms: int = 30,
    ) -> None:
        """Drain bounded worker queues from Tk's main thread only."""

        visual = session.take_latest_visual()

        if visual is not None:
            self.show_rgb_frame(
                visual.width,
                visual.height,
                visual.rgb_bytes,
            )
            del visual

        metrics, quality = session.dashboard_telemetry()
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

            elif isinstance(event, ErrorDTO):
                self.show_error(event)

            elif isinstance(
                event,
                RuntimeStatusDTO,
            ):
                self.show_runtime_status(event)

            elif isinstance(event, PeopleOperationResultDTO):
                self.status.configure(text=event.message)

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

    def _refresh_dashboard(self) -> None:
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
            self.diagnostic_card.grid_remove()
        else:
            self.diagnostic_card.grid(row=2, column=0, sticky="ew", padx=10, pady=4)
        self._diagnostic_visible = not self._diagnostic_visible

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

        header = (
            f"P6 {width} {height} 255\n"
        ).encode("ascii")

        photo = tk.PhotoImage(
            data=header + rgb_bytes,
            format="PPM",
        )

        self.video.configure(
            image=photo,
            text="",
        )

        self._photo = photo

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

        form = tk.Toplevel(self.root)
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
                "first",
                "last",
                "external",
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
            ("Nombre", "first"),
            ("Apellido", "last"),
            (
                "Identificador interno (opcional)",
                "external",
            ),
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

        ttk.Checkbutton(
            form,
            text=(
                "Confirmo consentimiento biométrico"
            ),
            variable=consent,
        ).grid(
            row=3,
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
            row=4,
            column=0,
            columnspan=2,
            sticky="w",
            padx=8,
            pady=4,
        )

        def close_form() -> None:
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

        def submit() -> None:
            """
            Validate form and start guided enrollment.
            """

            try:
                data = validate_registration_form(
                    values["first"].get(),
                    values["last"].get(),
                    values["external"].get(),
                    consent_confirmed=consent.get(),
                    persist_locally=persist.get(),
                )

            except RegistrationFormError as exc:

                if messagebox is not None:
                    messagebox.showerror(
                        "Formulario inválido",
                        str(exc),
                        parent=form,
                    )

                return

            self._on_register(data)

            close_form()

        ttk.Button(
            form,
            text="Iniciar captura guiada",
            command=submit,
        ).grid(
            row=5,
            column=0,
            padx=8,
            pady=10,
        )

        ttk.Button(
            form,
            text="Cancelar",
            command=close_form,
        ).grid(
            row=5,
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

    def _cancel(self) -> None:
        """
        Cancel an active enrollment workflow.
        """

        self._on_cancel()

        self.register_button.configure(
            state="normal"
        )

        self.cancel_button.configure(
            state="disabled"
        )

    def close(self) -> None:
        """
        Close UI and request resource cleanup.
        """

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


def _number(value: float | None, suffix: str = "") -> str:
    return "N/D" if value is None else f"{value:.1f}{suffix}"


def _value(value: float | str | None) -> str:
    if value is None:
        return "N/D"
    return f"{value:.3f}" if isinstance(value, float) else str(value)
