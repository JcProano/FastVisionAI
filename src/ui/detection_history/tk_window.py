"""Local Tk history window; explicit refresh and CSV export only."""
from __future__ import annotations
from typing import Any
from datetime import datetime, timezone
try:
    import tkinter as tk
    from tkinter import filedialog, ttk
except ModuleNotFoundError:  # pragma: no cover
    tk = filedialog = ttk = None  # type: ignore[assignment]
from src.core.detection_events import DetectionEventType
from .controller import DetectionHistoryController


class DetectionHistoryWindow:
    def __init__(self, root: Any, controller: DetectionHistoryController,
                 *, on_close=None) -> None:
        if tk is None or ttk is None: raise RuntimeError("Tkinter no está disponible")
        self.controller = controller; self._on_close = on_close
        self.window = tk.Toplevel(root); self.window.title("Historial de detecciones")
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.person_id = tk.StringVar(self.window); self.name = tk.StringVar(self.window)
        self.event_type = tk.StringVar(self.window)
        self.date_from = tk.StringVar(self.window); self.date_to = tk.StringVar(self.window)
        self.limit = tk.StringVar(self.window, value="100")
        ttk.Label(self.window, text="Desde YYYY-MM-DD").grid(row=0, column=0)
        ttk.Entry(self.window, textvariable=self.date_from).grid(row=0, column=1)
        ttk.Label(self.window, text="Hasta YYYY-MM-DD").grid(row=0, column=2)
        ttk.Entry(self.window, textvariable=self.date_to).grid(row=0, column=3)
        ttk.Label(self.window, text="Person ID").grid(row=1, column=0)
        ttk.Entry(self.window, textvariable=self.person_id).grid(row=1, column=1)
        ttk.Label(self.window, text="Nombre").grid(row=1, column=2)
        ttk.Entry(self.window, textvariable=self.name).grid(row=1, column=3)
        ttk.Label(self.window, text="Tipo").grid(row=2, column=0)
        ttk.Combobox(self.window, textvariable=self.event_type,
                     values=("",) + tuple(item.value for item in DetectionEventType)).grid(row=2, column=1)
        ttk.Label(self.window, text="Límite").grid(row=2, column=2)
        ttk.Entry(self.window, textvariable=self.limit, width=6).grid(row=2, column=3)
        columns = ("time", "person", "type", "similarity", "quality", "state")
        self.table = ttk.Treeview(self.window, columns=columns, show="headings")
        for key, label in zip(columns, ("Hora", "Persona", "Tipo", "Similitud", "Calidad", "Estado")):
            self.table.heading(key, text=label)
        self.table.grid(row=3, column=0, columnspan=6, sticky="nsew")
        ttk.Button(self.window, text="Refrescar", command=self.refresh).grid(row=4, column=0)
        ttk.Button(self.window, text="Exportar CSV", command=self.export).grid(row=4, column=1)
        ttk.Button(self.window, text="Cerrar", command=self.close).grid(row=4, column=5)
        self.status = ttk.Label(self.window); self.status.grid(row=5, column=0, columnspan=6)
        self.refresh()

    def focus(self): self.window.lift(); self.window.focus_force()
    def refresh(self):
        try:
            selected = self.event_type.get()
            result = self.controller.list(
                date_from=self._date(self.date_from.get(), end=False),
                date_to=self._date(self.date_to.get(), end=True),
                person_id=self.person_id.get() or None,
                name=self.name.get() or None,
                event_type=DetectionEventType(selected) if selected else None,
                limit=max(1, min(500, int(self.limit.get() or "100"))),
            )
        except Exception:
            self.status.configure(text="No se pudo consultar el historial con esos filtros")
            return
        self.table.delete(*self.table.get_children())
        for item in result.events:
            self.table.insert("", "end", values=(
                item.timestamp.isoformat(timespec="seconds"), item.display_name or "No registrada",
                item.event_type, "N/D" if item.similarity is None else f"{item.similarity:.4f}",
                "N/D" if item.quality_score is None else f"{item.quality_score:.1f}",
                item.recognition_state,
            ))
        self.status.configure(text=result.message)
    @staticmethod
    def _date(value: str, *, end: bool):
        if not value.strip(): return None
        parsed = datetime.strptime(value.strip(), "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return parsed.replace(hour=23, minute=59, second=59) if end else parsed
    def export(self):
        selected = filedialog.asksaveasfilename(parent=self.window, defaultextension=".csv")
        if selected:
            from pathlib import Path
            self.status.configure(text=self.controller.export_csv(Path(selected)).message)
    def close(self):
        if self.window.winfo_exists(): self.window.destroy()
        if self._on_close: self._on_close()
