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
        on_unknown_closed: Callable[[], None] | None = None,
        on_dismissed: Callable[[str, str], None] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if unknown_timeout_seconds <= 0:
            raise ValueError("unknown_timeout_seconds must be positive")
        self.root = root
        self.provider = provider
        self._on_view_person = on_view_person
        self._on_register = on_register
        self._unknown_timeout_seconds = unknown_timeout_seconds
        self._on_unknown_closed = on_unknown_closed
        self._on_dismissed = on_dismissed
        self._monotonic = monotonic
        self.window: Any | None = None
        self._photo: Any | None = None
        self._person_id: str | None = None
        self._popup_type: IdentificationPopupType | None = None
        self._timer_id: Any | None = None
        self._unknown_deadline: float | None = None

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
        self._render(dto)

    def _build(self) -> None:
        self.window = tk.Toplevel(self.root)
        self.window.title("FastVisionAI — Presentación experimental")
        self.window.protocol("WM_DELETE_WINDOW", self.dismiss)
        self.title = ttk.Label(self.window, font=("TkDefaultFont", 12, "bold"))
        self.title.pack(padx=16, pady=(14, 8))
        self.thumbnail = ttk.Label(self.window, text="Sin foto registrada", anchor="center")
        self.thumbnail.pack(padx=16, pady=6)
        self.details = ttk.Label(self.window, justify="left")
        self.details.pack(padx=16, pady=8, anchor="w")
        self.countdown = ttk.Label(self.window, justify="center")
        self.countdown.pack(padx=16, pady=4)
        self.actions = ttk.Frame(self.window); self.actions.pack(padx=12, pady=12)
        self.primary = ttk.Button(self.actions)
        self.primary.pack(side="left", padx=4)
        self.secondary = ttk.Button(self.actions, command=self.dismiss)
        self.secondary.pack(side="left", padx=4)

    def _render(self, dto: IdentificationPopupDTO) -> None:
        previous_type = self._popup_type
        self._cancel_timer(notify=False)
        if (previous_type is IdentificationPopupType.UNREGISTERED
                and dto.popup_type is not IdentificationPopupType.UNREGISTERED
                and self._on_unknown_closed is not None):
            self._on_unknown_closed()
        self._popup_type = dto.popup_type
        self._photo = None
        self.thumbnail.configure(image="", text="Sin foto registrada")
        if dto.popup_type is IdentificationPopupType.REGISTERED_CANDIDATE:
            self.countdown.configure(text="")
            self.title.configure(text="PERSONA REGISTRADA EN LA GALERÍA LOCAL")
            identifier = dto.external_identifier or "N/D"
            similarity = "N/D" if dto.similarity is None else f"{dto.similarity:.4f}"
            self.details.configure(text=(
                f"{dto.display_name}\nIdentificador: {identifier}\n"
                f"Dirección: {dto.address or 'N/D'}\nTeléfono: {dto.phone or 'N/D'}\n"
                f"Email: {dto.email or 'N/D'}\n"
                f"Similitud: {similarity}\nEstado: Candidato experimental registrado\n"
                "Decisión automática: NOT_EVALUATED"
            ))
            self._person_id = dto.person_id
            if dto.thumbnail_available and dto.person_id is not None:
                payload = thumbnail_to_ppm(self.provider.get_thumbnail(dto.person_id))
                if payload is not None:
                    self._photo = tk.PhotoImage(data=payload, format="PPM")
                    self.thumbnail.configure(image=self._photo, text="")
            self.primary.configure(text="Ver persona", command=self._view)
            self.secondary.configure(text="Cerrar")
        else:
            self.title.configure(text="PERSONA NO REGISTRADA EN LA GALERÍA LOCAL")
            self.details.configure(text=dto.message)
            self._person_id = None
            self.primary.configure(text="Registrar persona", command=self._register)
            self.secondary.configure(text="Ignorar", command=self.dismiss)
            self._unknown_deadline = self._monotonic() + self._unknown_timeout_seconds
            self._update_countdown()

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
        if notify and self._on_unknown_closed is not None:
            self._on_unknown_closed()

    def close(self) -> None:
        self.dismiss("application_close")
