"""Read-only effective configuration window for the local dashboard."""

from __future__ import annotations

from typing import Any

try:
    import tkinter as tk
    from tkinter import ttk
except ModuleNotFoundError:  # pragma: no cover
    tk = ttk = None  # type: ignore[assignment]

from .contracts import DashboardConfigurationDTO


class DashboardConfigurationWindow:
    def __init__(self, root: Any, configuration: DashboardConfigurationDTO) -> None:
        if tk is None or ttk is None:
            raise RuntimeError("Tkinter no está disponible")
        self.window = tk.Toplevel(root)
        self.window.title("Configuración efectiva — solo lectura")
        rows = (
            ("Source", configuration.source),
            ("Resolución", configuration.resolution),
            ("Fuente espejada", _yes(configuration.mirrored_source)),
            ("Perfil Guided Capture", configuration.guided_profile),
            ("Perfil Face Quality", configuration.quality_profile),
            ("Muestras objetivo", str(configuration.target_samples)),
            ("Persistencia predeterminada", _yes(configuration.persistence_enabled_by_default)),
            ("Carga al inicio", _yes(configuration.load_on_startup)),
            ("Recognition policy", configuration.recognition_policy),
            ("Policy version", configuration.recognition_policy_version),
            ("Decisión automática", "deshabilitada"),
            ("Match threshold", configuration.match_threshold),
            ("Ambiguity margin", configuration.ambiguity_margin),
        )
        for row, (label, value) in enumerate(rows):
            ttk.Label(self.window, text=label).grid(row=row, column=0, sticky="w", padx=10, pady=4)
            ttk.Label(self.window, text=value).grid(row=row, column=1, sticky="w", padx=10, pady=4)
        ttk.Button(self.window, text="Cerrar", command=self.close).grid(
            row=len(rows), column=0, columnspan=2, pady=10
        )
        self.window.columnconfigure(1, weight=1)

    def focus(self) -> None:
        self.window.lift()
        self.window.focus_force()

    def close(self) -> None:
        if self.window.winfo_exists():
            self.window.destroy()


def _yes(value: bool) -> str:
    return "sí" if value else "no"
