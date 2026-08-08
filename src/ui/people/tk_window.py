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


class PeopleManagerWindow:
    def __init__(
        self, root: Any, controller: PeopleManagerController, *,
        on_additional: Callable[[str], bool], on_cancel_additional: Callable[[], bool],
    ) -> None:
        if tk is None or ttk is None:
            raise RuntimeError("Tkinter no está disponible")
        self.controller = controller
        self._on_additional = on_additional
        self._on_cancel_additional = on_cancel_additional
        self.window = tk.Toplevel(root)
        self.window.title("Personas registradas")
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.query = tk.StringVar(master=self.window)
        ttk.Label(self.window, text="Personas registradas").grid(
            row=0, column=0, columnspan=7, sticky="w", padx=8, pady=8
        )
        ttk.Label(self.window, text="Buscar").grid(row=1, column=0, padx=8)
        search = ttk.Entry(self.window, textvariable=self.query, width=48)
        search.grid(row=1, column=1, columnspan=6, sticky="ew", padx=8)
        search.bind("<KeyRelease>", lambda _event: self.refresh())
        columns = ("first", "last", "external", "templates", "quality")
        self.table = ttk.Treeview(self.window, columns=columns, show="headings", height=12)
        for key, label in zip(columns, (
            "Nombre", "Apellido", "Identificador", "Templates", "Calidad",
        )):
            self.table.heading(key, text=label)
        self.table.grid(row=2, column=0, columnspan=7, sticky="nsew", padx=8, pady=8)
        actions = (
            ("Editar", self.edit), ("Eliminar", self.delete),
            ("Agregar muestras", self.add_samples), ("Refrescar", self.refresh),
            ("Guardar cambios", self.save), ("Importar", self.import_gallery),
            ("Exportar", self.export_gallery),
        )
        self.buttons = []
        for column, (label, callback) in enumerate(actions):
            button = ttk.Button(self.window, text=label, command=callback)
            button.grid(row=3, column=column, padx=4, pady=8)
            self.buttons.append(button)
        self.cancel_additional_button = ttk.Button(
            self.window, text="Cancelar captura", command=self.cancel_additional,
            state="disabled",
        )
        self.cancel_additional_button.grid(row=4, column=6, padx=4, pady=4)
        self.status = ttk.Label(self.window, text="IDLE")
        self.status.grid(row=4, column=0, columnspan=6, sticky="w", padx=8)
        self.window.rowconfigure(2, weight=1)
        self.window.columnconfigure(1, weight=1)
        self.refresh()
        self.window.after(200, self._poll_state)

    def refresh(self) -> None:
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

    def selected(self) -> PersonSummaryDTO | None:
        selection = self.table.selection()
        return self.controller.details(selection[0]).summary if selection else None

    def edit(self) -> None:
        person = self.selected()
        if person is None:
            return
        dialog = tk.Toplevel(self.window); dialog.title("Editar persona")
        values = [tk.StringVar(dialog, value=value or "") for value in (
            person.first_name, person.last_name, person.external_identifier,
        )]
        for row, label in enumerate(("Nombre", "Apellido", "Identificador externo")):
            ttk.Label(dialog, text=label).grid(row=row, column=0, padx=6, pady=4)
            ttk.Entry(dialog, textvariable=values[row]).grid(row=row, column=1, padx=6, pady=4)
        def apply() -> None:
            result = self.controller.update_person(
                person.person_id, values[0].get(), values[1].get(), values[2].get()
            )
            self.status.configure(text=result.message); dialog.destroy(); self.refresh()
        ttk.Button(dialog, text="Guardar en memoria", command=apply).grid(row=3, column=0)
        ttk.Button(dialog, text="Cancelar", command=dialog.destroy).grid(row=3, column=1)

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
        self.window.after(200, self._poll_state)

    def close(self) -> None:
        if self.controller.state is PeopleManagerState.ENROLLING_MORE:
            self._on_cancel_additional()
        self.controller.close()
        self.window.destroy()
