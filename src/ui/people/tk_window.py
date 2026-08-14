"""Tkinter-only registered-people window driven by safe DTOs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ModuleNotFoundError:  # pragma: no cover
    tk = filedialog = messagebox = ttk = None  # type: ignore[assignment]

from src.ui.people.controller import PeopleManagerController
from src.ui.people.contracts import PeopleManagerState, PersonSummaryDTO
from src.ui.people.contracts import PeopleSearchFiltersDTO
from src.core.person_database import PersonStatus
from src.ui.thumbnails import ThumbnailError, ThumbnailManager
from src.ui.thumbnails.presentation import thumbnail_to_ppm


class PeopleManagerWindow:
    def __init__(
        self, root: Any, controller: PeopleManagerController, *,
        on_additional: Callable[[str], bool], on_cancel_additional: Callable[[], bool],
        thumbnail_manager: ThumbnailManager | None = None,
        on_view_profile: Callable[[str], None] | None = None,
        advanced_controller: Any | None = None,
        on_capture_photo: Callable[[str], bool] | None = None,
        can_edit_photo: bool = True,
    ) -> None:
        if tk is None or ttk is None:
            raise RuntimeError("Tkinter no está disponible")
        self.controller = controller
        self._on_additional = on_additional
        self._on_cancel_additional = on_cancel_additional
        self._thumbnails = thumbnail_manager
        self._on_view_profile = on_view_profile
        self._advanced = advanced_controller
        self._on_capture_photo = on_capture_photo
        self._can_edit_photo = can_edit_photo
        self._search_after_id: Any | None = None
        self._page = 1
        self._thumbnail_photo: Any | None = None
        self.window = tk.Toplevel(root)
        self.window.title("Personas registradas")
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.query = tk.StringVar(master=self.window)
        self.status_filter = tk.StringVar(master=self.window, value="TODOS")
        self.created_from = tk.StringVar(master=self.window)
        self.created_to = tk.StringVar(master=self.window)
        default_size = (25 if advanced_controller is None else
                        advanced_controller.policy.default_page_size)
        self.page_size = tk.StringVar(master=self.window, value=str(default_size))
        ttk.Label(self.window, text="Personas registradas").grid(
            row=0, column=0, columnspan=8, sticky="w", padx=8, pady=8
        )
        ttk.Label(self.window, text="Buscar").grid(row=1, column=0, padx=8)
        search = ttk.Entry(self.window, textvariable=self.query, width=48)
        search.grid(row=1, column=1, columnspan=7, sticky="ew", padx=8)
        search.bind("<KeyRelease>", self._schedule_search)
        filters = ttk.Frame(self.window); filters.grid(
            row=2, column=0, columnspan=8, sticky="ew", padx=8,
        )
        ttk.Label(filters, text="Estado").pack(side="left")
        ttk.Combobox(filters, textvariable=self.status_filter, state="readonly", width=20,
                     values=("TODOS", "ACTIVE", "DISABLED", "PENDING_BIOMETRIC")).pack(side="left")
        ttk.Label(filters, text="Desde").pack(side="left", padx=(8, 0))
        ttk.Entry(filters, textvariable=self.created_from, width=12).pack(side="left")
        ttk.Label(filters, text="Hasta").pack(side="left", padx=(8, 0))
        ttk.Entry(filters, textvariable=self.created_to, width=12).pack(side="left")
        ttk.Label(filters, text="Resultados").pack(side="left", padx=(8, 0))
        sizes = (25, 50, 100) if advanced_controller is None else advanced_controller.policy.allowed_page_sizes
        ttk.Combobox(filters, textvariable=self.page_size, state="readonly", width=5,
                     values=sizes).pack(side="left")
        ttk.Button(filters, text="Buscar", command=self._filters_changed).pack(side="left", padx=4)
        ttk.Button(filters, text="Limpiar", command=self.clear_filters).pack(side="left")
        columns = (("photo", "name", "cedula", "phone", "email", "status", "templates",
                    "quality", "updated") if advanced_controller is not None else
                   ("first", "last", "external", "templates", "quality"))
        self.table = ttk.Treeview(self.window, columns=columns, show="headings", height=12)
        labels = (("Foto", "Nombre", "Cédula", "Teléfono", "Email", "Estado",
                   "Templates", "Calidad", "Actualizado") if advanced_controller is not None
                  else ("Nombre", "Apellido", "Identificador", "Templates", "Calidad"))
        for key, label in zip(columns, labels):
            self.table.heading(key, text=label)
        self.table.grid(row=3, column=0, columnspan=8, sticky="nsew", padx=8, pady=8)
        self.table.bind("<<TreeviewSelect>>", lambda _event: self._show_thumbnail())
        actions = (
            ("Ver ficha", self.view_profile), ("Editar", self.edit), ("Eliminar", self.delete),
            ("Agregar muestras", self.add_samples), ("Refrescar", self.refresh),
            ("Guardar cambios", self.save), ("Importar", self.import_gallery),
            ("Exportar", self.export_gallery),
        )
        self.buttons = []
        for column, (label, callback) in enumerate(actions):
            button = ttk.Button(self.window, text=label, command=callback)
            button.grid(row=4, column=column, padx=4, pady=8)
            self.buttons.append(button)
        self.cancel_additional_button = ttk.Button(
            self.window, text="Cancelar captura", command=self.cancel_additional,
            state="disabled",
        )
        self.cancel_additional_button.grid(row=5, column=6, padx=4, pady=4)
        self.status = ttk.Label(
            self.window,
            text="Mostrando 0 de 0" if advanced_controller is not None else "IDLE",
        )
        self.status.grid(row=5, column=0, columnspan=4, sticky="w", padx=8)
        self.previous_button = ttk.Button(self.window, text="Anterior", command=self.previous_page)
        self.previous_button.grid(row=5, column=4)
        self.next_button = ttk.Button(self.window, text="Siguiente", command=self.next_page)
        self.next_button.grid(row=5, column=5)
        self.toggle_status_button = ttk.Button(
            self.window, text="Deshabilitar/Habilitar", command=self.toggle_status,
        )
        self.toggle_status_button.grid(row=5, column=7)
        self.thumbnail = ttk.Label(self.window, text="Sin foto registrada", anchor="center")
        self.thumbnail.grid(row=6, column=0, columnspan=5, sticky="w", padx=8, pady=6)
        self.update_thumbnail_button = ttk.Button(
            self.window, text="Actualizar foto", command=self.update_thumbnail,
        )
        self.update_thumbnail_button.grid(row=6, column=5, padx=4)
        self.capture_thumbnail_button = ttk.Button(
            self.window, text="Capturar foto", command=self.capture_thumbnail,
            state="normal" if can_edit_photo else "disabled",
        )
        self.capture_thumbnail_button.grid(row=7, column=5, padx=4)
        self.delete_thumbnail_button = ttk.Button(
            self.window, text="Eliminar foto", command=self.delete_thumbnail,
        )
        self.delete_thumbnail_button.grid(row=6, column=6, padx=4)
        self.window.rowconfigure(3, weight=1)
        self.window.columnconfigure(1, weight=1)
        self.refresh()
        self.window.after(200, self._poll_state)

    def view_profile(self) -> None:
        person = self.selected()
        if person is not None and self._on_view_profile is not None:
            self._on_view_profile(person.person_id)

    def refresh(self) -> None:
        if self._advanced is not None:
            self._refresh_advanced(); return
        listing = self.controller.list_people(self.query.get())
        self.table.delete(*self.table.get_children())
        for person in listing.people:
            quality = ("sin score" if person.average_quality is None else
                       f"{person.average_quality:.1f} "
                       f"({person.minimum_quality:.1f}–{person.maximum_quality:.1f})")
            self.table.insert("", "end", iid=person.person_id, values=(
                person.first_name, person.last_name,
                person.external_identifier or "", person.template_count, quality,
            ))
        self.status.configure(text=listing.state.value.upper())

    def _refresh_advanced(self) -> None:
        try:
            filters = self._current_filters()
            page = self._advanced.paginate(filters, self._page)
        except Exception:
            self.status.configure(text="No se pudo consultar personas."); return
        self.table.delete(*self.table.get_children())
        for person in page.people:
            self.table.insert("", "end", iid=person.person_id, values=(
                "Sí" if person.thumbnail_available else "No", person.display_name,
                person.masked_cedula, person.phone or "", person.email or "", person.status,
                person.template_count, person.quality_summary or "sin score",
                person.updated_at.strftime("%Y-%m-%d %H:%M"),
            ))
        self.status.configure(text=page.message)
        self.previous_button.configure(state="normal" if page.has_previous else "disabled")
        self.next_button.configure(state="normal" if page.has_next else "disabled")

    def _current_filters(self) -> PeopleSearchFiltersDTO:
        from datetime import date
        parse = lambda value: None if not value.strip() else date.fromisoformat(value.strip())
        return PeopleSearchFiltersDTO(
            text=self.query.get(), administrative_status=self.status_filter.get(),
            created_from=parse(self.created_from.get()), created_to=parse(self.created_to.get()),
            limit=int(self.page_size.get()), offset=(self._page - 1) * int(self.page_size.get()),
        )

    def _schedule_search(self, _event=None) -> None:
        if self._advanced is None: self.refresh(); return
        if self._search_after_id is not None:
            self.window.after_cancel(self._search_after_id)
        self._page = 1
        self._search_after_id = self.window.after(
            self._advanced.policy.debounce_ms, self._run_debounced_search,
        )

    def _run_debounced_search(self) -> None:
        self._search_after_id = None
        if self.window.winfo_exists(): self.refresh()

    def _filters_changed(self) -> None:
        self._page = 1; self.refresh()

    def clear_filters(self) -> None:
        if self._search_after_id is not None:
            self.window.after_cancel(self._search_after_id); self._search_after_id = None
        self.query.set(""); self.status_filter.set("TODOS")
        self.created_from.set(""); self.created_to.set("")
        size = 25 if self._advanced is None else self._advanced.policy.default_page_size
        self.page_size.set(str(size)); self._page = 1; self.refresh()

    def previous_page(self) -> None:
        if self._page > 1: self._page -= 1; self.refresh()

    def next_page(self) -> None:
        self._page += 1; self.refresh()

    def toggle_status(self) -> None:
        if self._advanced is None: return
        person = self.selected()
        if person is None: return
        if person.civil_status == PersonStatus.ACTIVE.value:
            target = PersonStatus.DISABLED
        elif person.civil_status == PersonStatus.DISABLED.value:
            target = PersonStatus.ACTIVE
        else:
            self.status.configure(text="La transición administrativa no está permitida."); return
        confirmed = messagebox.askyesno(
            "Cambiar estado", "¿Confirmar el cambio de estado administrativo?",
            parent=self.window,
        )
        result = self._advanced.set_status(person.person_id, target, confirmed)
        self.status.configure(text=result.message)
        if result.success: self.refresh()

    def selected(self) -> PersonSummaryDTO | None:
        selection = self.table.selection()
        return self.controller.details(selection[0]).summary if selection else None

    def _show_thumbnail(self) -> None:
        person = self.selected()
        self._thumbnail_photo = None
        self.thumbnail.configure(image="", text="Sin foto registrada")
        if person is None or self._thumbnails is None:
            return
        try:
            dto = self._thumbnails.load(person.person_id)
            if not dto.available:
                self.capture_thumbnail_button.configure(text="Capturar foto")
                return
            self.capture_thumbnail_button.configure(text="Actualizar foto")
            self._thumbnail_photo = tk.PhotoImage(data=thumbnail_to_ppm(dto), format="PPM")
            self.thumbnail.configure(image=self._thumbnail_photo, text="")
        except Exception:
            self.status.configure(text="No se pudo cargar la foto visual.")

    def capture_thumbnail(self) -> None:
        person = self.selected()
        if (person is None or self._on_capture_photo is None
                or not self._can_edit_photo):
            return
        if self._on_capture_photo(person.person_id):
            self.status.configure(text="Captura de fotografía iniciada.")

    def update_thumbnail(self) -> None:
        person = self.selected()
        if person is None or self._thumbnails is None:
            return
        selected = filedialog.askopenfilename(
            parent=self.window,
            filetypes=[("Imágenes", "*.jpg *.jpeg *.png"), ("Todos", "*")],
        )
        if not selected:
            return
        replace = self._thumbnails.exists(person.person_id)
        if replace and not messagebox.askyesno(
            "Reemplazar foto", "¿Reemplazar la foto visual registrada?", parent=self.window,
        ):
            return
        try:
            payload = Path(selected).read_bytes()
            self._thumbnails.save(person.person_id, payload, replace=replace)
            self.status.configure(text="Foto visual actualizada.")
            self._show_thumbnail()
        except (OSError, ThumbnailError, ValueError):
            self.status.configure(text="La imagen seleccionada no es válida o no pudo guardarse.")

    def delete_thumbnail(self) -> None:
        person = self.selected()
        if person is None or self._thumbnails is None:
            return
        if not messagebox.askyesno(
            "Eliminar foto", "¿Eliminar únicamente la foto visual?", parent=self.window,
        ):
            return
        try:
            deleted = self._thumbnails.delete(person.person_id)
            self.status.configure(text="Foto eliminada." if deleted else "Sin foto registrada")
            self._show_thumbnail()
        except ThumbnailError:
            self.status.configure(text="No se pudo eliminar la foto visual.")

    def edit(self) -> None:
        person = self.selected()
        if person is None:
            return
        dialog = tk.Toplevel(self.window); dialog.title("Editar persona")
        raw_values = (
            person.first_name, person.last_name, person.cedula or person.external_identifier,
            person.address, person.phone, person.email, person.birth_date, person.sex,
            person.notes,
        )
        values = [tk.StringVar(dialog, value=value or "") for value in raw_values]
        labels = (
            "Nombre", "Apellido", "Cédula (inmutable)", "Dirección", "Teléfono",
            "Email", "Fecha nacimiento", "Sexo", "Observaciones",
        )
        for row, label in enumerate(labels):
            ttk.Label(dialog, text=label).grid(row=row, column=0, padx=6, pady=4)
            entry = ttk.Entry(dialog, textvariable=values[row])
            entry.grid(row=row, column=1, padx=6, pady=4)
            if row == 2:
                entry.configure(state="disabled")
        def apply() -> None:
            try:
                result = self.controller.update_person(
                    person.person_id, values[0].get(), values[1].get(), values[2].get(),
                    address=values[3].get(), phone=values[4].get(), email=values[5].get(),
                    birth_date=values[6].get(), sex=values[7].get(), notes=values[8].get(),
                )
            except TypeError:  # legacy controller without Person Database
                result = self.controller.update_person(
                    person.person_id, values[0].get(), values[1].get(), values[2].get()
                )
            self.status.configure(text=result.message); dialog.destroy(); self.refresh()
        ttk.Button(dialog, text="Guardar", command=apply).grid(row=len(labels), column=0)
        ttk.Button(dialog, text="Cancelar", command=dialog.destroy).grid(
            row=len(labels), column=1
        )

    def delete(self) -> None:
        person = self.selected()
        if person is None:
            return
        confirmed = messagebox.askyesno(
            "Eliminar identidad",
            f"Eliminar {person.display_name}\n{person.person_id}\n"
            f"Templates que se eliminarán: {person.template_count}", parent=self.window,
        )
        result = self.controller.delete_person(person.person_id, confirmed=confirmed)
        self.status.configure(text=result.message); self.refresh()

    def add_samples(self) -> None:
        person = self.selected()
        if person is not None and self._on_additional(person.person_id):
            self.status.configure(text="ENROLLING_MORE")

    def cancel_additional(self) -> None:
        if self.controller.state is not PeopleManagerState.ENROLLING_MORE:
            return
        if self._on_cancel_additional():
            self.status.configure(text="Cancelando captura adicional…")

    def save(self) -> None:
        overwrite = False
        if self.controller.manifest_path.exists() or self.controller.archive_path.exists():
            overwrite = messagebox.askyesno(
                "Sobrescribir", "Los archivos existen. ¿Sobrescribir tras confirmación?",
                parent=self.window,
            )
            if not overwrite:
                return
        result = self.controller.save_changes(overwrite_confirmed=overwrite)
        self.status.configure(text=result.message)

    def import_gallery(self) -> None:
        manifest = filedialog.askopenfilename(parent=self.window, filetypes=[("JSON", "*.json")])
        if not manifest:
            return
        archive = filedialog.askopenfilename(parent=self.window, filetypes=[("NPZ", "*.npz")])
        if not archive:
            return
        preview = self.controller.prepare_import(Path(manifest), Path(archive))
        if not preview.success:
            self.status.configure(text=preview.message); return
        confirmed = messagebox.askyesno(
            "Reemplazar galería",
            f"Se cargarán {preview.identity_count} identidades y "
            f"{preview.template_count} templates. ¿Reemplazar la galería activa?",
            parent=self.window,
        )
        result = self.controller.confirm_import(confirmed=confirmed)
        self.status.configure(text=result.message); self.refresh()

    def export_gallery(self) -> None:
        manifest = filedialog.asksaveasfilename(
            parent=self.window, defaultextension=".json", filetypes=[("JSON", "*.json")]
        )
        if not manifest:
            return
        archive = filedialog.asksaveasfilename(
            parent=self.window, defaultextension=".npz", filetypes=[("NPZ", "*.npz")]
        )
        if not archive:
            return
        paths = Path(manifest), Path(archive)
        overwrite = False
        if any(path.exists() for path in paths):
            overwrite = messagebox.askyesno("Sobrescribir", "¿Sobrescribir destinos existentes?",
                                            parent=self.window)
            if not overwrite:
                return
        result = self.controller.export_gallery(*paths, overwrite_confirmed=overwrite)
        self.status.configure(text=result.message)

    def _poll_state(self) -> None:
        if not self.window.winfo_exists():
            return
        busy = self.controller.state is PeopleManagerState.ENROLLING_MORE
        for button in self.buttons:
            button.configure(state="disabled" if busy else "normal")
        self.cancel_additional_button.configure(state="normal" if busy else "disabled")
        self.update_thumbnail_button.configure(state="disabled" if busy else "normal")
        self.capture_thumbnail_button.configure(
            state="disabled" if busy or not self._can_edit_photo else "normal"
        )
        self.delete_thumbnail_button.configure(state="disabled" if busy else "normal")
        self.window.after(200, self._poll_state)

    def close(self) -> None:
        if self._search_after_id is not None:
            try: self.window.after_cancel(self._search_after_id)
            except Exception: pass
            self._search_after_id = None
        if self.controller.state is PeopleManagerState.ENROLLING_MORE:
            self._on_cancel_additional()
        self.controller.close()
        self.window.destroy()
