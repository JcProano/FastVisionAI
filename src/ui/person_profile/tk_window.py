"""Tkinter person profile consuming only safe presentation DTOs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ModuleNotFoundError:  # pragma: no cover
    tk = filedialog = messagebox = ttk = None  # type: ignore[assignment]

from src.ui.thumbnails import ThumbnailManager
from src.ui.thumbnails.presentation import thumbnail_to_ppm

from .contracts import PersonProfileStatus
from .controller import PersonProfileController


class PersonProfileWindow:
    def __init__(
        self, root: Any, controller: PersonProfileController, person_id: str, *,
        on_additional: Callable[[str], bool], thumbnail_manager: ThumbnailManager,
        on_close: Callable[[str], None] | None = None,
    ) -> None:
        if tk is None or ttk is None:
            raise RuntimeError("Tkinter no está disponible")
        self.controller = controller
        self.person_id = person_id
        self._on_additional = on_additional
        self._thumbnails = thumbnail_manager
        self._on_close = on_close
        self._photo: Any | None = None
        self.window = tk.Toplevel(root)
        self.window.title("Ficha completa de persona")
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.title = ttk.Label(self.window, text="PERSONA REGISTRADA", font=("TkDefaultFont", 13, "bold"))
        self.title.grid(row=0, column=0, columnspan=2, padx=12, pady=10, sticky="w")
        self.thumbnail = ttk.Label(self.window, text="Sin foto registrada", anchor="center")
        self.thumbnail.grid(row=1, column=0, padx=12, pady=8, sticky="n")
        self.details = ttk.Label(self.window, justify="left")
        self.details.grid(row=1, column=1, padx=12, pady=8, sticky="nw")
        self.summary = ttk.Label(self.window, justify="left")
        self.summary.grid(row=2, column=0, columnspan=2, padx=12, pady=8, sticky="w")
        self.attendance = ttk.Label(self.window, justify="left")
        self.attendance.grid(row=3, column=0, columnspan=2, padx=12, pady=8, sticky="w")
        actions = ttk.Frame(self.window); actions.grid(row=4, column=0, columnspan=2, pady=10)
        self.edit_button = ttk.Button(actions, text="Editar datos", command=self.edit)
        self.edit_button.pack(side="left", padx=4)
        self.additional_button = ttk.Button(actions, text="Agregar muestras", command=self.add_samples)
        self.additional_button.pack(side="left", padx=4)
        self.photo_button = ttk.Button(actions, text="Actualizar foto", command=self.update_photo)
        self.photo_button.pack(side="left", padx=4)
        self.check_in_button = ttk.Button(actions, text="Registrar entrada manual",
                                          command=lambda: self.manual_attendance(True))
        self.check_in_button.pack(side="left", padx=4)
        self.check_out_button = ttk.Button(actions, text="Registrar salida manual",
                                           command=lambda: self.manual_attendance(False))
        self.check_out_button.pack(side="left", padx=4)
        ttk.Button(actions, text="Cerrar", command=self.close).pack(side="left", padx=4)
        self.status = ttk.Label(self.window)
        self.status.grid(row=5, column=0, columnspan=2, padx=12, pady=6, sticky="w")
        self.refresh()

    def focus(self) -> None:
        self.window.lift(); self.window.focus_force()

    def refresh(self) -> None:
        profile = self.controller.get_by_person_id(self.person_id)
        self._profile = profile
        self.title.configure(text=("REGISTRO BIOMÉTRICO HEREDADO" if profile.legacy_biometric_record
                                   else "FICHA COMPLETA DE PERSONA"))
        value = lambda item: "N/D" if item in (None, "") else str(item)
        self.details.configure(text=(
            f"Nombre: {value(profile.first_name)}\nApellido: {value(profile.last_name)}\n"
            f"Cédula: {value(profile.cedula)}\nDirección: {value(profile.address)}\n"
            f"Teléfono: {value(profile.phone)}\nEmail: {value(profile.email)}\n"
            f"Fecha nacimiento: {value(profile.birth_date)}\nSexo: {value(profile.sex)}\n"
            f"Observaciones: {value(profile.notes)}\nEstado: {profile.administrative_status.value}"
        ))
        quality = lambda item: "N/D" if item is None else f"{item:.1f}"
        self.summary.configure(text=(
            "RESUMEN BIOMÉTRICO\n"
            f"Templates: {profile.template_count}\nCon score: {profile.scored_template_count}\n"
            f"Calidad promedio: {quality(profile.average_quality_score)}\n"
            f"Calidad mínima: {quality(profile.minimum_quality_score)}\n"
            f"Calidad máxima: {quality(profile.maximum_quality_score)}\n"
            f"Primer template: {value(profile.first_template_at)}\n"
            f"Último template: {value(profile.last_template_at)}"
        ))
        self.attendance.configure(text=(
            "ASISTENCIA RECIENTE\n"
            f"Última entrada: {value(profile.last_check_in)}\n"
            f"Última salida: {value(profile.last_check_out)}\n"
            f"Eventos de hoy: {profile.attendance_events_today}"
        ))
        self.status.configure(text=profile.profile_message)
        editable = profile.administrative_status in {
            PersonProfileStatus.ACTIVE, PersonProfileStatus.DISABLED,
            PersonProfileStatus.PENDING_BIOMETRIC,
        }
        active = profile.administrative_status is PersonProfileStatus.ACTIVE
        self.edit_button.configure(state="normal" if editable else "disabled")
        self.additional_button.configure(state="normal" if active else "disabled")
        self.check_in_button.configure(state="normal" if active else "disabled")
        self.check_out_button.configure(state="normal" if active else "disabled")
        self._photo = None
        self.thumbnail.configure(image="", text="Sin foto registrada")
        if profile.thumbnail_available and profile.thumbnail_bytes:
            dto = self._thumbnails.load(self.person_id)
            payload = thumbnail_to_ppm(dto)
            if payload is not None:
                self._photo = tk.PhotoImage(data=payload, format="PPM")
                self.thumbnail.configure(image=self._photo, text="")

    def edit(self) -> None:
        profile = self._profile
        if profile.administrative_status in {
            PersonProfileStatus.LEGACY_BIOMETRIC_ONLY, PersonProfileStatus.NOT_FOUND,
        }:
            return
        dialog = tk.Toplevel(self.window); dialog.title("Editar datos civiles")
        fields = ("first_name", "last_name", "address", "phone", "email", "birth_date", "sex", "notes")
        labels = ("Nombre", "Apellido", "Dirección", "Teléfono", "Email", "Fecha nacimiento", "Sexo", "Observaciones")
        values = {name: tk.StringVar(dialog, value=getattr(profile, name) or "") for name in fields}
        for row, (name, label) in enumerate(zip(fields, labels)):
            ttk.Label(dialog, text=label).grid(row=row, column=0, padx=5, pady=3)
            ttk.Entry(dialog, textvariable=values[name]).grid(row=row, column=1, padx=5, pady=3)
        def save() -> None:
            result = self.controller.update_person(
                self.person_id, **{name: variable.get() for name, variable in values.items()}
            )
            self.status.configure(text=result.message)
            if result.success:
                dialog.destroy(); self.refresh()
        ttk.Button(dialog, text="Guardar", command=save).grid(row=len(fields), column=0)
        ttk.Button(dialog, text="Cancelar", command=dialog.destroy).grid(row=len(fields), column=1)

    def add_samples(self) -> None:
        result = self.controller.begin_additional(self.person_id)
        self.status.configure(text=result.message)
        if result.success and not self._on_additional(self.person_id):
            self.status.configure(text="No se pudo iniciar la captura adicional.")

    def manual_attendance(self, check_in: bool) -> None:
        label = "entrada" if check_in else "salida"
        if not messagebox.askyesno(
            "Confirmar marcación",
            f"Registrar {label} manual para {self._profile.display_name}?\nHora aproximada: ahora",
            parent=self.window,
        ):
            return
        result = self.controller.manual_attendance(self.person_id, check_in=check_in)
        self.status.configure(text=("Asistencia no disponible" if result is None else result.message))
        if result is not None and result.success: self.refresh()

    def update_photo(self) -> None:
        selected = filedialog.askopenfilename(parent=self.window, filetypes=[("Imágenes", "*.jpg *.jpeg *.png")])
        if not selected:
            return
        replace = self._thumbnails.exists(self.person_id)
        if replace and not messagebox.askyesno("Reemplazar foto", "¿Reemplazar la foto registrada?", parent=self.window):
            return
        try:
            from pathlib import Path
            self._thumbnails.save(self.person_id, Path(selected).read_bytes(), replace=replace)
            self.refresh()
        except Exception:
            self.status.configure(text="No se pudo actualizar la foto visual.")

    def close(self) -> None:
        if self.window.winfo_exists():
            self.window.destroy()
        if self._on_close is not None:
            self._on_close(self.person_id)
