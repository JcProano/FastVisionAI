"""Recognition history and civil-detail presentation."""
from __future__ import annotations
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo
try:
    import tkinter as tk
    from tkinter import filedialog, ttk
except ModuleNotFoundError:  # pragma: no cover
    tk = filedialog = ttk = None  # type: ignore[assignment]

from src.core.detection_events import DetectionEventType
from src.core.time_provider import Clock
from src.ui.thumbnails.presentation import thumbnail_to_ppm
from .controller import DetectionHistoryController

PRESENTATION_TIMEZONE = "America/Guayaquil"


def local_event_parts(value: datetime, timezone_name: str = PRESENTATION_TIMEZONE) -> tuple[str, str]:
    local = value.astimezone(ZoneInfo(timezone_name))
    return local.strftime("%Y-%m-%d"), local.strftime("%H:%M:%S")


class DetectionHistoryWindow:
    # Replaces the former "Historial de detecciones" filters (Person ID, Tipo) with
    # civil filters; internal identifiers are deliberately absent from the UI.
    def __init__(self, root: Any, controller: DetectionHistoryController,
                 *, on_close=None, on_view_person=None) -> None:
        if tk is None or ttk is None: raise RuntimeError("Tkinter no está disponible")
        self.controller = controller; self._on_close = on_close
        self._on_view_person = on_view_person; self._photos: dict[str, Any] = {}
        self.window = tk.Toplevel(root); self.window.title("HISTORIAL DE RECONOCIMIENTOS")
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.name = tk.StringVar(self.window); self.cedula = tk.StringVar(self.window)
        self.camera = tk.StringVar(self.window); self.status_filter = tk.StringVar(self.window)
        self.result_filter = tk.StringVar(self.window)
        self.date_from = tk.StringVar(self.window); self.date_to = tk.StringVar(self.window)
        self.limit = tk.StringVar(self.window, value="100")
        labels = (("Nombre", self.name), ("Cédula", self.cedula),
                  ("Desde YYYY-MM-DD", self.date_from), ("Hasta YYYY-MM-DD", self.date_to),
                  ("Cámara", self.camera))
        for index, (label, variable) in enumerate(labels):
            row, column = divmod(index, 3)
            ttk.Label(self.window, text=label).grid(row=row, column=column * 2, sticky="w")
            ttk.Entry(self.window, textvariable=variable).grid(row=row, column=column * 2 + 1, sticky="ew")
        ttk.Label(self.window, text="Estado").grid(row=2, column=0, sticky="w")
        ttk.Combobox(self.window, textvariable=self.status_filter,
                     values=("", "ACTIVE", "DISABLED", "PENDING_BIOMETRIC"),
                     state="readonly").grid(row=2, column=1, sticky="ew")
        ttk.Label(self.window, text="Resultado").grid(row=2, column=2, sticky="w")
        ttk.Combobox(self.window, textvariable=self.result_filter,
                     values=("", "IDENTIFICADO", "NO REGISTRADO"),
                     state="readonly").grid(row=2, column=3, sticky="ew")
        ttk.Label(self.window, text="Límite").grid(row=2, column=4, sticky="w")
        ttk.Entry(self.window, textvariable=self.limit, width=6).grid(row=2, column=5, sticky="w")
        columns = ("name", "cedula", "date", "time", "similarity", "camera", "status")
        self.table = ttk.Treeview(self.window, columns=columns, show="tree headings")
        self.table.heading("#0", text="Foto"); self.table.column("#0", width=90, anchor="center")
        for key, label in zip(columns, ("Nombre", "Cédula", "Fecha", "Hora", "Similitud", "Cámara", "Estado")):
            self.table.heading(key, text=label)
        self.table.grid(row=3, column=0, columnspan=6, sticky="nsew")
        self.table.bind("<Double-1>", lambda _event: self.show_detail())
        ttk.Button(self.window, text="Refrescar", command=self.refresh).grid(row=4, column=0)
        ttk.Button(self.window, text="Ver detalle", command=self.show_detail).grid(row=4, column=1)
        ttk.Button(self.window, text="Exportar CSV", command=self.export).grid(row=4, column=2)
        ttk.Button(self.window, text="Cerrar", command=self.close).grid(row=4, column=5)
        self.status = ttk.Label(self.window); self.status.grid(row=5, column=0, columnspan=6)
        self.window.rowconfigure(3, weight=1)
        for column in range(6): self.window.columnconfigure(column, weight=1)
        self.refresh()

    def focus(self): self.window.lift(); self.window.focus_force()

    def refresh(self):
        try:
            selected = self.result_filter.get()
            event_type = (DetectionEventType.REGISTERED_CANDIDATE if selected == "IDENTIFICADO"
                          else DetectionEventType.UNREGISTERED if selected == "NO REGISTRADO" else None)
            result = self.controller.list(
                date_from=self._date(self.date_from.get(), end=False),
                date_to=self._date(self.date_to.get(), end=True), name=self.name.get() or None,
                cedula=self.cedula.get() or None, camera_id=self.camera.get() or None,
                administrative_status=self.status_filter.get() or None,
                event_type=event_type, limit=max(1, min(500, int(self.limit.get() or "100"))),
            )
        except Exception as exc:
            self.status.configure(text=str(exc) if isinstance(exc, PermissionError)
                                  else "No se pudo consultar el historial con esos filtros")
            return
        self.table.delete(*self.table.get_children()); self._photos.clear()
        for item in result.events:
            date_text, time_text = local_event_parts(item.timestamp)
            photo = None; photo_text = "Sin fotografía"
            if item.person_id and self.controller.identity_provider is not None:
                payload = thumbnail_to_ppm(self.controller.identity_provider.get_thumbnail(item.person_id))
                if payload:
                    photo = tk.PhotoImage(data=payload, format="PPM")
                    self._photos[item.event_id] = photo; photo_text = ""
            self.table.insert("", "end", iid=item.event_id, text=photo_text, image=photo or "", values=(
                item.display_name or "No registrada", item.masked_cedula or "N/D", date_text, time_text,
                "N/D" if item.similarity is None else f"{item.similarity * 100:.1f}%",
                item.camera_id or "N/D", item.administrative_status or item.recognition_state,
            ))
        self.status.configure(text=result.message)

    @staticmethod
    def _date(value: str, *, end: bool):
        if not value.strip(): return None
        day = datetime.strptime(value.strip(), "%Y-%m-%d").date()
        start, following = Clock().utc_range_for_local_day(day, PRESENTATION_TIMEZONE)
        return following - timedelta(microseconds=1) if end else start

    def show_detail(self):
        selected = self.table.selection()
        if not selected: self.status.configure(text="Seleccione un reconocimiento"); return
        detail = self.controller.detail(selected[0])
        if detail is None: self.status.configure(text="El evento ya no está disponible"); return
        dialog = tk.Toplevel(self.window); dialog.title("Detalle del reconocimiento")
        photo = None
        if detail.thumbnail is not None:
            payload = thumbnail_to_ppm(detail.thumbnail)
            if payload: photo = tk.PhotoImage(data=payload, format="PPM")
        image_label = ttk.Label(dialog, text="Sin fotografía" if photo is None else "", image=photo or "")
        image_label.image = photo; image_label.grid(row=0, column=0, rowspan=10, padx=12, pady=12)
        person = detail.person; event = detail.event
        date_text, time_text = local_event_parts(event.timestamp)
        fields = (("Nombre completo", None if person is None else person.display_name),
                  ("Cédula", None if person is None else person.external_identifier),
                  ("Cargo", None if person is None else person.position),
                  ("Departamento", None if person is None else person.department),
                  ("Empresa", None if person is None else person.company),
                  ("Teléfono", None if person is None else person.phone),
                  ("Correo", None if person is None else person.email), ("Fecha", date_text),
                  ("Hora", time_text), ("Similitud", "N/D" if event.similarity is None else f"{event.similarity * 100:.1f}%"),
                  ("Cámara", event.camera_id),
                  ("Estado", event.administrative_status or event.recognition_state))
        for row, (label, value) in enumerate(fields):
            ttk.Label(dialog, text=f"{label}:").grid(row=row, column=1, sticky="e")
            ttk.Label(dialog, text=value or "N/D").grid(row=row, column=2, sticky="w")
        if event.person_id and self._on_view_person:
            ttk.Button(dialog, text="Ver persona", command=lambda: self._on_view_person(event.person_id)).grid(row=len(fields), column=2)
        ttk.Button(dialog, text="Cerrar", command=dialog.destroy).grid(row=len(fields) + 1, column=2)

    def export(self):
        selected = filedialog.asksaveasfilename(parent=self.window, defaultextension=".csv")
        if selected: self.status.configure(text=self.controller.export_csv(Path(selected)).message)

    def close(self):
        if self.window.winfo_exists(): self.window.destroy()
        if self._on_close: self._on_close()
