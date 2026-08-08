"""Singleton Tk popup consuming only safe identification DTOs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

try:
    import tkinter as tk
    from tkinter import ttk
except ModuleNotFoundError:  # pragma: no cover
    tk = ttk = None  # type: ignore[assignment]

from src.ui.thumbnails.presentation import thumbnail_to_ppm

from .contracts import IdentificationPopupDTO, IdentificationPopupType, IdentityInfoProvider


class IdentificationPopupWindow:
    def __init__(
        self, root: Any, provider: IdentityInfoProvider, *,
        on_view_person: Callable[[str], None], on_register: Callable[[], None],
    ) -> None:
        self.root = root
        self.provider = provider
        self._on_view_person = on_view_person
        self._on_register = on_register
        self.window: Any | None = None
        self._photo: Any | None = None
        self._person_id: str | None = None

    @property
    def active(self) -> bool:
        return self.window is not None and bool(self.window.winfo_exists())

    def show(self, dto: IdentificationPopupDTO) -> None:
        if dto.popup_type is IdentificationPopupType.SUPPRESSED:
            return
        if tk is None or ttk is None:
            raise RuntimeError("Tkinter no está disponible")
        if not self.active:
            self._build()
        else:
            self.window.lift()
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
        self.actions = ttk.Frame(self.window); self.actions.pack(padx=12, pady=12)
        self.primary = ttk.Button(self.actions)
        self.primary.pack(side="left", padx=4)
        self.secondary = ttk.Button(self.actions, command=self.dismiss)
        self.secondary.pack(side="left", padx=4)

    def _render(self, dto: IdentificationPopupDTO) -> None:
        self._photo = None
        self.thumbnail.configure(image="", text="Sin foto registrada")
        if dto.popup_type is IdentificationPopupType.REGISTERED_CANDIDATE:
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
            self.secondary.configure(text="Ignorar")

    def _view(self) -> None:
        if self._person_id is not None:
            self._on_view_person(self._person_id)

    def _register(self) -> None:
        self.dismiss()
        self._on_register()

    def dismiss(self) -> None:
        self._photo = None
        self._person_id = None
        if self.active:
            self.window.destroy()
        self.window = None

    def close(self) -> None:
        self.dismiss()
