"""Singleton-capable local attendance history window."""

from __future__ import annotations

from datetime import datetime, time, timezone
from pathlib import Path
from typing import Any

try:
    import tkinter as tk
    from tkinter import filedialog, ttk
except ModuleNotFoundError:  # pragma: no cover
    tk = filedialog = ttk = None

from src.core.attendance import AttendanceEventType


class AttendanceHistoryWindow:
    def __init__(self, root: Any, controller: Any, *, on_close=None) -> None:
        if tk is None or ttk is None:
            raise RuntimeError("Tkinter no está disponible")
        self.controller = controller
        self._on_close = on_close
        self.window = tk.Toplevel(root)
        self.window.title("Historial de asistencia")
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.date_from = tk.StringVar(self.window)
        self.date_to = tk.StringVar(self.window)
        self.person = tk.StringVar(self.window)
        self.name = tk.StringVar(self.window)
        self.kind = tk.StringVar(self.window)
        self.limit = tk.StringVar(self.window, value="100")
        fields = (
            ("Desde YYYY-MM-DD", self.date_from), ("Hasta YYYY-MM-DD", self.date_to),
            ("Person ID", self.person), ("Persona", self.name),
            ("Tipo", self.kind), ("Límite", self.limit),
        )
        for index, (label, variable) in enumerate(fields):
            ttk.Label(self.window, text=label).grid(row=0, column=index * 2)
            ttk.Entry(self.window, textvariable=variable, width=13).grid(
                row=0, column=index * 2 + 1,
            )
        columns = ("date", "time", "person", "cedula", "type", "camera")
        self.table = ttk.Treeview(self.window, columns=columns, show="headings")
        for key, label in zip(
            columns, ("Fecha", "Hora", "Persona", "Cédula", "Tipo", "Cámara"),
        ):
            self.table.heading(key, text=label)
        self.table.grid(row=1, column=0, columnspan=12)
        ttk.Button(self.window, text="Refrescar", command=self.refresh).grid(row=2, column=0)
        ttk.Button(self.window, text="Exportar CSV", command=self.export).grid(row=2, column=1)
        ttk.Button(self.window, text="Cerrar", command=self.close).grid(row=2, column=11)
        self.status = ttk.Label(self.window)
        self.status.grid(row=3, column=0, columnspan=12)
        self.refresh()

    def focus(self) -> None:
        self.window.lift()
        self.window.focus_force()

    def refresh(self) -> None:
        try:
            event_type = AttendanceEventType(self.kind.get()) if self.kind.get() else None
            result = self.controller.list(
                date_from=_parse_date(self.date_from.get(), end=False),
                date_to=_parse_date(self.date_to.get(), end=True),
                person_id=self.person.get() or None,
                name=self.name.get() or None,
                event_type=event_type,
                limit=max(1, min(500, int(self.limit.get()))),
            )
            self.table.delete(*self.table.get_children())
            for event in result.events:
                self.table.insert("", "end", values=(
                    event.timestamp.date(), event.timestamp.time().replace(microsecond=0),
                    event.display_name or event.person_id, event.masked_cedula or "N/D",
                    event.event_type, event.camera_id or "N/D",
                ))
            self.status.configure(text=result.message)
        except Exception:
            self.status.configure(text="Filtros inválidos")

    def export(self) -> None:
        selected = filedialog.asksaveasfilename(
            parent=self.window, defaultextension=".csv",
        )
        if selected:
            self.status.configure(text=self.controller.export_csv(Path(selected)).message)

    def close(self) -> None:
        if self.window.winfo_exists():
            self.window.destroy()
        if self._on_close:
            self._on_close()


def _parse_date(value: str, *, end: bool) -> datetime | None:
    if not value.strip():
        return None
    day = datetime.strptime(value.strip(), "%Y-%m-%d").date()
    return datetime.combine(day, time.max if end else time.min, tzinfo=timezone.utc)
