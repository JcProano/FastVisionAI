"""Tkinter presentation layer; it never owns biometric arrays or model objects."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

try:  # Tk is an optional OS component and is not required by headless tests.
    import tkinter as tk
    from tkinter import messagebox, ttk
except ModuleNotFoundError:  # pragma: no cover - branch depends on Python build
    tk = None  # type: ignore[assignment]
    messagebox = None  # type: ignore[assignment]
    ttk = None  # type: ignore[assignment]

from src.ui.contracts import (
    EnrollmentProgressDTO, EnrollmentResultDTO, ErrorDTO, MonitoringDTO,
    RegistrationFormData, RuntimeStatusDTO,
)
from src.ui.form_validation import RegistrationFormError, validate_registration_form


@dataclass(frozen=True, slots=True)
class MonitoringText:
    headline: str
    candidate: str
    similarity: str
    decision: str
    quality: str


def monitoring_text(dto: MonitoringDTO) -> MonitoringText:
    candidate = dto.candidate_display_name or "Sin candidatos registrados"
    similarity = "—" if dto.similarity is None else f"{dto.similarity:.4f}"
    quality = "—" if dto.quality_score is None else f"{dto.quality_score:.1f}/100"
    return MonitoringText(
        dto.message, candidate, similarity,
        "Decisión automática: deshabilitada / NOT_EVALUATED", quality,
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
        self._form: tk.Toplevel | None = None
        self._photo: tk.PhotoImage | None = None
        root.title("FastVisionAI — validación facial experimental")
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.video = ttk.Label(root, text="Vista local sin frame")
        self.video.grid(row=0, column=0, columnspan=2, padx=12, pady=12)
        self.status = ttk.Label(root, text="Iniciando…")
        self.status.grid(row=1, column=0, columnspan=2, sticky="w", padx=12)
        self.candidate = ttk.Label(root, text="Sin candidatos registrados")
        self.candidate.grid(row=2, column=0, columnspan=2, sticky="w", padx=12)
        self.similarity = ttk.Label(root, text="Similitud: —")
        self.similarity.grid(row=3, column=0, sticky="w", padx=12)
        self.decision = ttk.Label(
            root, text="Decisión automática: deshabilitada / NOT_EVALUATED"
        )
        self.decision.grid(row=4, column=0, columnspan=2, sticky="w", padx=12)
        self.quality = ttk.Label(root, text="Calidad: —")
        self.quality.grid(row=5, column=0, sticky="w", padx=12)
        self.runtime_status = ttk.Label(root, text="Cámara: iniciando | Runtime: iniciando")
        self.runtime_status.grid(row=6, column=0, columnspan=2, sticky="w", padx=12)
        self.register_button = ttk.Button(root, text="Registrar rostro", command=self.open_form)
        self.register_button.grid(row=7, column=0, padx=12, pady=12, sticky="w")
        self.cancel_button = ttk.Button(root, text="Cancelar", command=self._cancel, state="disabled")
        self.cancel_button.grid(row=7, column=1, padx=12, pady=12, sticky="e")

    def show_monitoring(self, dto: MonitoringDTO) -> None:
        view = monitoring_text(dto)
        self.status.configure(text=view.headline)
        self.candidate.configure(text=view.candidate)
        self.similarity.configure(text=f"Similitud: {view.similarity}")
        self.decision.configure(text=view.decision)
        self.quality.configure(text=f"Score: {view.quality}")
        self.register_button.configure(state="normal" if dto.registration_enabled else "disabled")

    def show_progress(self, dto: EnrollmentProgressDTO) -> None:
        self.status.configure(
            text=f"{dto.instruction} — {dto.accepted_samples}/{dto.target_samples}"
        )
        self.register_button.configure(state="disabled")
        self.cancel_button.configure(state="normal" if dto.cancellation_enabled else "disabled")

    def show_result(self, dto: EnrollmentResultDTO) -> None:
        self.status.configure(text=dto.message)
        self.candidate.configure(text=dto.display_name)
        self.register_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")

    def show_error(self, dto: ErrorDTO) -> None:
        self.status.configure(text=dto.message)
        if not dto.recoverable:
            self.register_button.configure(state="disabled")

    def show_runtime_status(self, dto: RuntimeStatusDTO) -> None:
        self.runtime_status.configure(
            text=f"Cámara: {dto.camera_state} | Runtime: {dto.runtime_state} | "
                 f"YuNet: {dto.detector_model_state} | ArcFace: {dto.embedding_model_state}"
        )

    def poll_session(self, session: Any, interval_ms: int = 30) -> None:
        """Drain bounded worker queues from Tk's main thread only."""
        visual = session.take_latest_visual()
        if visual is not None:
            self.show_rgb_frame(visual.width, visual.height, visual.rgb_bytes)
            del visual
        for event in session.drain_events():
            if isinstance(event, MonitoringDTO):
                self.show_monitoring(event)
            elif isinstance(event, EnrollmentProgressDTO):
                self.show_progress(event)
            elif isinstance(event, EnrollmentResultDTO):
                self.show_result(event)
            elif isinstance(event, ErrorDTO):
                self.show_error(event)
            elif isinstance(event, RuntimeStatusDTO):
                self.show_runtime_status(event)
        if self.root.winfo_exists():
            self.root.after(interval_ms, self.poll_session, session, interval_ms)

    def show_rgb_frame(self, width: int, height: int, rgb_bytes: bytes) -> None:
        """Display one transient RGB frame; only Tk's current PhotoImage is retained."""
        header = f"P6 {width} {height} 255\n".encode("ascii")
        photo = tk.PhotoImage(data=header + rgb_bytes, format="PPM")
        self.video.configure(image=photo, text="")
        self._photo = photo

    def open_form(self) -> None:
        if self._form is not None and self._form.winfo_exists():
            self._form.lift()
            return
        form = tk.Toplevel(self.root)
        self._form = form
        form.title("Registrar rostro")
        values = {name: tk.StringVar() for name in ("first", "last", "external")}
        consent, persist = tk.BooleanVar(False), tk.BooleanVar(False)
        for row, (label, key) in enumerate((
            ("Nombre", "first"), ("Apellido", "last"),
            ("Identificador interno (opcional)", "external"),
        )):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", padx=8, pady=4)
            ttk.Entry(form, textvariable=values[key]).grid(row=row, column=1, padx=8, pady=4)
        ttk.Checkbutton(form, text="Confirmo consentimiento biométrico",
                        variable=consent).grid(row=3, column=0, columnspan=2, sticky="w", padx=8)
        ttk.Checkbutton(form, text="Persistir galería local después del registro",
                        variable=persist).grid(row=4, column=0, columnspan=2, sticky="w", padx=8)

        def submit() -> None:
            try:
                data = validate_registration_form(
                    values["first"].get(), values["last"].get(), values["external"].get(),
                    consent_confirmed=consent.get(), persist_locally=persist.get(),
                )
            except RegistrationFormError as exc:
                messagebox.showerror("Formulario inválido", str(exc), parent=form)
                return
            self._on_register(data)
            form.destroy()
            self._form = None

        ttk.Button(form, text="Iniciar captura guiada", command=submit).grid(
            row=5, column=0, padx=8, pady=8
        )
        ttk.Button(form, text="Cancelar", command=form.destroy).grid(
            row=5, column=1, padx=8, pady=8
        )

    def _cancel(self) -> None:
        self._on_cancel()
        self.register_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")

    def close(self) -> None:
        self._on_close()
        if self._form is not None and self._form.winfo_exists():
            self._form.destroy()
        self._photo = None
        self.root.destroy()
