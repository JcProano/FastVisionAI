"""Singleton-friendly Tk presentation for safe report DTOs."""
from __future__ import annotations
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Callable

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ModuleNotFoundError:  # pragma: no cover
    tk = filedialog = messagebox = ttk = None


class ReportWindow:
    def __init__(self, root: Any, controller, *, on_close: Callable[[], None] | None = None):
        if tk is None or ttk is None: raise RuntimeError("Tkinter is unavailable")
        self.controller = controller; self._on_close = on_close
        self.window = tk.Toplevel(root); self.window.title("Reportes")
        self.window.geometry("900x600"); self.window.minsize(700, 480)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        start, end = controller.default_dates()
        self.from_value = tk.StringVar(master=self.window, value=start)
        self.to_value = tk.StringVar(master=self.window, value=end)
        self.person_value = tk.StringVar(master=self.window)
        self.type_value = tk.StringVar(master=self.window, value=controller.REPORT_TYPES[0])
        controls = ttk.Frame(self.window, padding=8); controls.pack(fill="x")
        for column, (label, variable) in enumerate((
            ("Desde", self.from_value), ("Hasta", self.to_value),
            ("Persona", self.person_value), ("Tipo", self.type_value),
        )):
            ttk.Label(controls, text=label).grid(row=0, column=column, sticky="w")
            if label == "Tipo":
                ttk.Combobox(controls, textvariable=variable,
                             values=controller.REPORT_TYPES, state="readonly").grid(row=1, column=column)
            else: ttk.Entry(controls, textvariable=variable).grid(row=1, column=column)
        self.table = ttk.Treeview(self.window, show="headings"); self.table.pack(fill="both", expand=True, padx=8)
        self.status = ttk.Label(self.window, text="Listo"); self.status.pack(anchor="w", padx=8)
        actions = ttk.Frame(self.window, padding=8); actions.pack(fill="x")
        ttk.Button(actions, text="Generar", command=self.generate).pack(side="left")
        ttk.Button(actions, text="Exportar CSV", command=self.export_csv).pack(side="left", padx=4)
        ttk.Button(actions, text="Exportar Excel", state=("normal" if controller.excel_available else "disabled")).pack(side="left")
        ttk.Button(actions, text="Exportar PDF", state="disabled").pack(side="left", padx=4)
        ttk.Button(actions, text="Cerrar", command=self.close).pack(side="right")

    def focus(self) -> None: self.window.lift(); self.window.focus_force()

    def generate(self) -> None:
        try:
            report = self.controller.generate(
                self.type_value.get(), self.from_value.get(), self.to_value.get(),
                self.person_value.get() or None,
            )
            self._render(report); self.status.configure(text="Reporte generado")
        except Exception:
            self.status.configure(text="No se pudo generar el reporte")

    def _render(self, report) -> None:
        values = getattr(report, "days", getattr(report, "people", (report,)))
        if not values or not is_dataclass(values[0]): return
        records = [asdict(item) for item in values]
        columns = tuple(records[0]); self.table.configure(columns=columns)
        for column in columns:
            self.table.heading(column, text=column); self.table.column(column, width=120)
        for item in self.table.get_children(): self.table.delete(item)
        for record in records:
            self.table.insert("", "end", values=tuple(_display(record[key]) for key in columns))

    def export_csv(self) -> None:
        if filedialog is None: return
        destination = filedialog.asksaveasfilename(parent=self.window, defaultextension=".csv")
        if not destination: return
        try:
            result = self.controller.export_csv(Path(destination))
            self.status.configure(text=result.message)
        except Exception: self.status.configure(text="No se pudo exportar CSV")

    def close(self) -> None:
        if self.window.winfo_exists(): self.window.destroy()
        if self._on_close is not None: self._on_close()


def _display(value) -> str:
    if value is None: return "N/D"
    if isinstance(value, (tuple, list)): return str(len(value))
    return str(value)
