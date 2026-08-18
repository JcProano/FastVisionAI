"""Singleton Tk popup consuming only safe identification DTOs."""

from __future__ import annotations

from collections.abc import Callable
import math
import time
import logging
from typing import Any

try:
    import tkinter as tk
    from tkinter import ttk
except ModuleNotFoundError:  # pragma: no cover
    tk = ttk = None  # type: ignore[assignment]

from src.ui.thumbnails.presentation import thumbnail_to_ppm

from .contracts import IdentificationPopupDTO, IdentificationPopupType, IdentityInfoProvider

LOGGER = logging.getLogger(__name__)


class IdentificationPopupWindow:
    def __init__(
        self, root: Any, provider: IdentityInfoProvider, *,
        on_view_person: Callable[[str], None], on_register: Callable[[], None],
        unknown_timeout_seconds: float = 60.0,
        registered_timeout_seconds: float = 60.0,
        on_unknown_closed: Callable[[], None] | None = None,
        on_dismissed: Callable[[str, str], None] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if unknown_timeout_seconds <= 0:
            raise ValueError("unknown_timeout_seconds must be positive")
        if registered_timeout_seconds <= 0:
            raise ValueError("registered_timeout_seconds must be positive")
        self.root = root
        self.provider = provider
        self._on_view_person = on_view_person
        self._on_register = on_register
        self._unknown_timeout_seconds = unknown_timeout_seconds
        self._registered_timeout_seconds = registered_timeout_seconds
        self._on_unknown_closed = on_unknown_closed
        self._on_dismissed = on_dismissed
        self._monotonic = monotonic
        self.window: Any | None = None
        self._photo: Any | None = None
        self._person_id: str | None = None
        self._popup_type: IdentificationPopupType | None = None
        self._timer_id: Any | None = None
        self._unknown_deadline: float | None = None
        self._registered_deadline: float | None = None

    @property
    def active(self) -> bool:
        return self.window is not None and bool(self.window.winfo_exists())

    @property
    def popup_type(self) -> IdentificationPopupType | None:
        return self._popup_type

    def show(self, dto: IdentificationPopupDTO) -> None:
        if dto.popup_type is IdentificationPopupType.SUPPRESSED:
            return
        if tk is None or ttk is None:
            raise RuntimeError("Tkinter no está disponible")
        if not self.active:
            self._build()
        else:
            self.window.lift()
            if (dto.popup_type is IdentificationPopupType.UNREGISTERED
                    and self._popup_type is IdentificationPopupType.UNREGISTERED):
                return
            if (dto.popup_type is IdentificationPopupType.REGISTERED_CANDIDATE
                    and self._popup_type is IdentificationPopupType.REGISTERED_CANDIDATE
                    and dto.person_id == self._person_id):
                return
        self._render(dto)

    def _build(self) -> None:
        self.window = tk.Toplevel(self.root)
        self.window.title("FastVisionAI — Identificación")
        self.window.configure(background="#10151d")
        self.window.protocol("WM_DELETE_WINDOW", self.dismiss)
        self.window.transient(self.root)
        self.window.minsize(760, 500)
        style = ttk.Style(self.window)
        style.configure("Identification.TFrame", background="#10151d")
        style.configure(
            "Identification.Title.TLabel", background="#10151d",
            foreground="#54d38a", font=("TkDefaultFont", 18, "bold"),
        )
        style.configure(
            "Identification.Heading.TLabel", background="#10151d",
            foreground="#f2f5f8", font=("TkDefaultFont", 13, "bold"),
        )
        style.configure(
            "Identification.Body.TLabel", background="#10151d",
            foreground="#d4d9df", font=("TkDefaultFont", 11),
        )
        container = ttk.Frame(self.window, style="Identification.TFrame", padding=24)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1, minsize=320)
        container.columnconfigure(1, weight=2, minsize=380)
        container.rowconfigure(1, weight=1)
        self.title = ttk.Label(
            container, style="Identification.Title.TLabel", anchor="center",
        )
        self.title.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 18))
        photo_panel = ttk.Frame(container, style="Identification.TFrame", width=320,
                                height=410)
        photo_panel.grid(row=1, column=0, sticky="nsew", padx=(0, 22))
        photo_panel.grid_propagate(False)
        photo_panel.columnconfigure(0, weight=1); photo_panel.rowconfigure(0, weight=1)
        self.thumbnail = ttk.Label(
            photo_panel, text="◯\n\nSin fotografía registrada", anchor="center",
            justify="center", style="Identification.Body.TLabel",
        )
        self.thumbnail.grid(row=0, column=0, sticky="nsew")
        details_panel = ttk.Frame(container, style="Identification.TFrame")
        details_panel.grid(row=1, column=1, sticky="nsew")
        self.right_title = ttk.Label(
            details_panel, style="Identification.Heading.TLabel", anchor="w",
        )
        self.right_title.pack(fill="x", pady=(2, 12))
        self.details = ttk.Label(
            details_panel, justify="left", style="Identification.Body.TLabel",
        )
        self.details.pack(fill="both", expand=True, anchor="w")
        self.countdown = ttk.Label(
            details_panel, justify="center", style="Identification.Body.TLabel",
        )
        self.countdown.pack(fill="x", pady=(8, 0))
        self.actions = ttk.Frame(container, style="Identification.TFrame")
        self.actions.grid(row=2, column=0, columnspan=2, pady=(18, 0))
        self.primary = ttk.Button(self.actions)
        self.primary.pack(side="left", padx=4)
        self.secondary = ttk.Button(self.actions, command=self.dismiss)
        self.secondary.pack(side="left", padx=4)
        self.window.bind("<Return>", lambda _event: self.dismiss("enter"))
        self.window.bind("<Escape>", lambda _event: self.dismiss("escape"))
        self.window.update_idletasks()
        width = max(880, self.window.winfo_reqwidth())
        height = max(560, self.window.winfo_reqheight())
        x = max(0, (self.window.winfo_screenwidth() - width) // 2)
        y = max(0, (self.window.winfo_screenheight() - height) // 2)
        self.window.geometry(f"{width}x{height}+{x}+{y}")
        self.window.grab_set()
        self.window.deiconify(); self.window.lift(); self.window.focus_force()

    def _render(self, dto: IdentificationPopupDTO) -> None:
        previous_type = self._popup_type
        self._cancel_timer(notify=False)
        if (previous_type is IdentificationPopupType.UNREGISTERED
                and dto.popup_type is not IdentificationPopupType.UNREGISTERED
                and self._on_unknown_closed is not None):
            self._on_unknown_closed()
        self._popup_type = dto.popup_type
        self._photo = None
        self.thumbnail.configure(image="", text="◯\n\nSin fotografía registrada")
        if dto.popup_type is IdentificationPopupType.REGISTERED_CANDIDATE:
            self.title.configure(text="✔ PERSONA IDENTIFICADA")
            self.right_title.configure(text="PERSONA IDENTIFICADA")
            identifier = dto.external_identifier or "No disponible"
            similarity = ("No disponible" if dto.similarity is None
                          else f"{dto.similarity * 100:.1f} %")
            registered = _format_datetime(dto.registered_at)
            last_access = _format_datetime(dto.last_access_at)
            identified_at = _format_datetime(dto.timestamp)
            self.details.configure(text=(
                f"Nombre completo\n{dto.display_name or 'No disponible'}\n\n"
                f"Cédula\n{identifier}\n\n"
                f"Cargo: {dto.position or 'No disponible'}\n"
                f"Departamento: {dto.department or 'No disponible'}\n"
                f"Empresa: {dto.company or 'No disponible'}\n"
                f"Teléfono: {dto.phone or 'No disponible'}\n"
                f"Correo: {dto.email or 'No disponible'}\n"
                f"Fecha de registro: {registered}\n"
                f"Último acceso: {last_access}\n"
                "────────────────────────\n"
                "RESULTADO\n\n"
                f"Score de reconocimiento: {similarity}\n"
                "Estado: IDENTIFICADO\n"
                f"Hora de identificación: {identified_at}"
            ))
            self._person_id = dto.person_id
            if dto.thumbnail_available and dto.person_id is not None:
                try:
                    payload = thumbnail_to_ppm(
                        self.provider.get_thumbnail(dto.person_id), max_width=300,
                        max_height=400, allow_upscale=True,
                    )
                    if payload is not None:
                        self._photo = tk.PhotoImage(data=payload, format="PPM")
                        self.thumbnail.configure(image=self._photo, text="")
                except Exception as exc:
                    LOGGER.warning(
                        "Registered thumbnail unavailable safely; exception_type=%s",
                        type(exc).__name__,
                    )
            self.primary.configure(text="Ver detalles", command=self._view)
            self.secondary.configure(text="Cerrar")
            self._registered_deadline = self._monotonic() + getattr(
                self, "_registered_timeout_seconds", 60.0)
            self._update_registered_countdown()
        else:
            self.title.configure(text="PERSONA NO REGISTRADA")
            self.right_title.configure(text="REGISTRO LOCAL")
            self.details.configure(text=_friendly_unknown_message(dto.message))
            self._person_id = None
            self.primary.configure(text="Registrar persona", command=self._register)
            self.secondary.configure(text="Ignorar", command=self.dismiss)
            self._unknown_deadline = self._monotonic() + self._unknown_timeout_seconds
            self._update_countdown()

    def _update_registered_countdown(self) -> None:
        if (not self.active
                or self._popup_type is not IdentificationPopupType.REGISTERED_CANDIDATE
                or self._registered_deadline is None):
            return
        remaining = max(0, math.ceil(self._registered_deadline - self._monotonic()))
        self.secondary.configure(text=f"Cerrar ({remaining})")
        if remaining == 0:
            self.dismiss("timeout")
            return
        self._timer_id = self.root.after(1000, self._update_registered_countdown)

    def _update_countdown(self) -> None:
        if (not self.active or self._popup_type is not IdentificationPopupType.UNREGISTERED
                or self._unknown_deadline is None):
            return
        remaining = max(0, math.ceil(self._unknown_deadline - self._monotonic()))
        minutes, seconds = divmod(remaining, 60)
        self.countdown.configure(
            text=f"Tiempo restante para decidir: {minutes:02d}:{seconds:02d}"
        )
        if remaining == 0:
            self.dismiss("timeout")
            return
        self._timer_id = self.root.after(1000, self._update_countdown)

    def _view(self) -> None:
        if self._person_id is not None:
            self._on_view_person(self._person_id)

    def _register(self) -> None:
        self.dismiss()
        self._on_register()

    def dismiss(self, reason: str = "user") -> None:
        was_unknown = self._popup_type is IdentificationPopupType.UNREGISTERED
        previous_type = self._popup_type
        self._cancel_timer(notify=False)
        self._photo = None
        self._person_id = None
        if self.active:
            try:
                self.window.grab_release()
            except Exception:
                pass
            self.window.destroy()
        self.window = None
        self._popup_type = None
        if was_unknown and self._on_unknown_closed is not None:
            self._on_unknown_closed()
        on_dismissed = getattr(self, "_on_dismissed", None)
        if previous_type is not None and on_dismissed is not None:
            try:
                on_dismissed(previous_type.value, reason)
            except Exception as exc:
                LOGGER.error("Popup dismiss notification failed safely; exception_type=%s",
                             type(exc).__name__)

    def dismiss_with_reason(self, reason: str) -> None:
        """Reason-aware close hook; separate method preserves legacy popup test doubles."""
        self.dismiss(reason)

    def _cancel_timer(self, *, notify: bool) -> None:
        if self._timer_id is not None:
            try:
                self.root.after_cancel(self._timer_id)
            except Exception:
                pass
            self._timer_id = None
        self._unknown_deadline = None
        self._registered_deadline = None
        if notify and self._on_unknown_closed is not None:
            self._on_unknown_closed()

    def close(self) -> None:
        self.dismiss("application_close")


def _friendly_unknown_message(message: str) -> str:
    lowered = message.casefold()
    quality_markers = (
        "pose_not_requested", "low_interocular_distance", "low_quality",
        "alignment_failed", "blurry", "too_dark", "too_bright",
    )
    if any(marker in lowered for marker in quality_markers):
        return "Mejore la iluminación, centre el rostro y manténgase estable."
    return "No existe una identidad registrada para este rostro."


def _format_datetime(value) -> str:
    if value is None:
        return "No disponible"
    try:
        return value.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except (AttributeError, ValueError, OSError):
        return "No disponible"
