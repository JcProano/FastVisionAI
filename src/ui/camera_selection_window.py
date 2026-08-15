from __future__ import annotations

import ipaddress
from typing import Callable
from urllib.parse import urlsplit

try:
    import tkinter as tk
    from tkinter import ttk
except ModuleNotFoundError:  # pragma: no cover
    tk = None  # type: ignore[assignment]
    ttk = None  # type: ignore[assignment]

from src.camera.source_discovery import CameraSelectionController, CameraSourceDTO, CameraSourceType


class CameraSelectionWindow:
    """Safe camera chooser. Raw network credentials exist only in the URL entry."""

    TYPE_EXAMPLES = {
        "HTTP/MJPEG": "http://192.168.1.3:4747/video",
        "RTSP": "rtsp://usuario:clave@192.168.1.100:554/stream1",
        "Personalizada": "http://host:puerto/ruta",
        "DroidCam WiFi": "http://192.168.1.3:4747/video",
    }
    TYPE_HELP = {
        "HTTP/MJPEG": "DroidCam WiFi normalmente usa:\nhttp://IP_DEL_TELEFONO:4747/video",
        "RTSP": "Incluye usuario y clave en la URL solo si la cámara los requiere.",
        "Personalizada": "Indica la URL completa proporcionada por la cámara.",
        "DroidCam WiFi": "DroidCam WiFi normalmente usa:\nhttp://IP_DEL_TELEFONO:4747/video",
    }

    def __init__(self, parent, controller: CameraSelectionController,
                 on_use: Callable[[CameraSourceDTO], bool], *,
                 current_source_id: Callable[[], str | None],
                 on_close: Callable[[], None] | None = None) -> None:
        if tk is None or ttk is None: raise RuntimeError("Tkinter no está disponible")
        self.controller = controller; self.on_use = on_use
        self.current_source_id = current_source_id; self.on_close = on_close or (lambda: None)
        self.window = tk.Toplevel(parent); self.window.title("Seleccionar cámara")
        self.window.geometry("620x690"); self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.selected = tk.StringVar(value=""); self.preferred = tk.BooleanVar(value=False)
        local_card = ttk.LabelFrame(self.window, text="Cámaras locales detectadas", padding=10)
        local_card.pack(fill="both", expand=True, padx=12, pady=(12, 6))
        self.local_frame = ttk.Frame(local_card); self.local_frame.pack(fill="both", expand=True)
        network_card = ttk.LabelFrame(self.window, text="Cámaras de red", padding=10)
        network_card.pack(fill="both", expand=True, padx=12, pady=6)
        self.network_frame = ttk.Frame(network_card); self.network_frame.pack(fill="both", expand=True)
        ttk.Button(network_card, text="+ Agregar cámara IP", command=self.show_network_form).pack(anchor="w", pady=(8, 0))
        self.network_form = ttk.LabelFrame(self.window, text="Agregar cámara IP", padding=10)
        self.network_name = tk.StringVar(); self.network_type = tk.StringVar(value="RTSP"); self.network_url = tk.StringVar()
        self.droidcam_ip = tk.StringVar(); self.droidcam_port = tk.StringVar(value="4747")
        self.network_example = tk.StringVar(); self.network_help = tk.StringVar()
        self.droidcam_preview = tk.StringVar()
        ttk.Label(self.network_form, text="Nombre").grid(row=0, column=0, sticky="w")
        ttk.Entry(self.network_form, textvariable=self.network_name, width=42).grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Label(self.network_form, text="Tipo").grid(row=1, column=0, sticky="w")
        self.network_type_combo = ttk.Combobox(
            self.network_form, textvariable=self.network_type,
            values=("RTSP", "HTTP/MJPEG", "Personalizada", "DroidCam WiFi"),
            state="readonly", width=18,
        )
        self.network_type_combo.grid(row=1, column=1, sticky="w", padx=5)
        self.network_type_combo.bind("<<ComboboxSelected>>", self._network_type_changed)
        ttk.Label(self.network_form, text="URL").grid(row=2, column=0, sticky="w")
        self.network_url_entry = ttk.Entry(self.network_form, textvariable=self.network_url, width=42)
        self.network_url_entry.grid(row=2, column=1, sticky="ew", padx=5)
        ttk.Label(self.network_form, textvariable=self.network_example, foreground="#666666").grid(
            row=3, column=1, sticky="w", padx=5,
        )
        ttk.Label(self.network_form, textvariable=self.network_help, foreground="#555555",
                  justify="left").grid(row=4, column=1, sticky="w", padx=5, pady=(3, 5))
        self.droidcam_fields = ttk.Frame(self.network_form)
        ttk.Label(self.droidcam_fields, text="IP del teléfono").grid(row=0, column=0, sticky="w")
        ttk.Entry(self.droidcam_fields, textvariable=self.droidcam_ip, width=22).grid(row=0, column=1, sticky="w", padx=5)
        ttk.Label(self.droidcam_fields, text="Puerto").grid(row=1, column=0, sticky="w")
        ttk.Entry(self.droidcam_fields, textvariable=self.droidcam_port, width=8).grid(row=1, column=1, sticky="w", padx=5)
        ttk.Label(self.droidcam_fields, textvariable=self.droidcam_preview,
                  justify="left").grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        self.droidcam_ip.trace_add("write", self._droidcam_fields_changed)
        self.droidcam_port.trace_add("write", self._droidcam_fields_changed)
        self.network_form.columnconfigure(1, weight=1)
        network_actions = ttk.Frame(self.network_form); network_actions.grid(row=6, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(network_actions, text="Probar", command=self.test_network_form).pack(side="left", padx=3)
        ttk.Button(network_actions, text="Guardar", command=self.save_network).pack(side="left", padx=3)
        ttk.Button(network_actions, text="Cancelar", command=self.hide_network_form).pack(side="right", padx=3)
        self.status = ttk.Label(self.window, text=""); self.status.pack(fill="x", padx=12)
        ttk.Checkbutton(self.window, text="Usar esta cámara automáticamente al iniciar",
                        variable=self.preferred).pack(anchor="w", padx=12, pady=(5, 0))
        actions = ttk.Frame(self.window, padding=12); actions.pack(fill="x")
        ttk.Button(actions, text="Actualizar", command=self.refresh).pack(side="left", padx=3)
        ttk.Button(actions, text="Probar", command=self.test_selected).pack(side="left", padx=3)
        ttk.Button(actions, text="Conectar", command=self.use_selected).pack(side="left", padx=3)
        ttk.Button(actions, text="Cancelar", command=self.close).pack(side="right", padx=3)
        self._update_network_guidance()
        self.refresh()

    def focus(self) -> None: self.window.lift(); self.window.focus_force()

    def refresh(self) -> None:
        result = self.controller.refresh()
        for frame in (self.local_frame, self.network_frame):
            for child in frame.winfo_children(): child.destroy()
        local = tuple(item for item in result.sources if item.source_type is CameraSourceType.LOCAL_V4L2)
        network = tuple(item for item in result.sources if item.source_type is not CameraSourceType.LOCAL_V4L2)
        self._render_group(self.local_frame, local, "No se encontraron cámaras locales.")
        self._render_group(self.network_frame, network, "No hay cámaras IP guardadas.")
        if result.selected is not None: self.selected.set(result.selected.source_id)
        selected = next((item for item in result.sources if item.source_id == self.selected.get()), None)
        self.preferred.set(bool(selected and selected.preferred))
        if not result.sources: self.status.configure(text="Desconectada — conecte una cámara y pulse Actualizar.")

    def _render_group(self, frame, sources, empty: str) -> None:
        if not sources: ttk.Label(frame, text=empty).pack(anchor="w"); return
        for source in sources:
            row = ttk.Frame(frame); row.pack(fill="x", pady=3)
            ttk.Radiobutton(row, text=source.display_name, variable=self.selected,
                            value=source.source_id, command=self._selection_changed).pack(anchor="w")
            kind = ("Cámara virtual" if source.details.get("virtual") else
                    str(source.details.get("transport", source.source_type.value)))
            endpoint = source.details.get("endpoint")
            ttk.Label(row, text=f"Disponible · {kind}" + (f" · {endpoint}" if endpoint else "")).pack(anchor="w", padx=22)

    def _selection_changed(self) -> None:
        source = next((item for item in self.controller.sources if item.source_id == self.selected.get()), None)
        self.preferred.set(bool(source and source.preferred))

    def test_selected(self) -> None:
        source_id = self.selected.get()
        if not any(item.source_id == source_id for item in self.controller.sources):
            self.status.configure(text="Seleccione una cámara disponible."); return
        self.status.configure(text="✓ Cámara disponible" if self.controller.probe(source_id)
                              else "✗ No se pudo conectar")

    def show_network_form(self) -> None: self.network_form.pack(fill="x", padx=12, pady=6)
    def hide_network_form(self) -> None: self.network_url.set(""); self.network_form.pack_forget()

    def test_network_form(self) -> None:
        source_type = self._network_source_type()
        try:
            self._validate_network_form()
            available = self.controller.probe_network_source(
                self.network_name.get(), source_type, self.network_url.get(),
            )
        except (ValueError, RuntimeError) as exc: self.status.configure(text=str(exc)); return
        self.status.configure(text="✓ Cámara disponible" if available else "✗ No se pudo conectar")

    def save_network(self) -> None:
        try: source = self._add_network()
        except (ValueError, RuntimeError) as exc: self.status.configure(text=str(exc)); return
        self.selected.set(source.source_id); self.network_url.set(""); self.network_name.set("")
        self.hide_network_form(); self.refresh()
        self.status.configure(text="Cámara IP guardada; las credenciales permanecen ocultas.")

    def _add_network(self) -> CameraSourceDTO:
        source_type = self._network_source_type()
        self._validate_network_form()
        return self.controller.add_network_source(
            self.network_name.get(), source_type, self.network_url.get(),
        )

    def _network_source_type(self) -> CameraSourceType:
        return (CameraSourceType.NETWORK_RTSP if self.network_type.get() == "RTSP" else
                CameraSourceType.NETWORK_HTTP if self.network_type.get() in ("HTTP/MJPEG", "DroidCam WiFi") else
                CameraSourceType.CUSTOM)

    def _network_type_changed(self, _event=None) -> None:
        """Update guidance without replacing an URL the user already entered."""
        self._update_network_guidance()

    def _update_network_guidance(self) -> None:
        selected = self.network_type.get()
        self.network_example.set(f"Ejemplo: {self.TYPE_EXAMPLES[selected]}")
        self.network_help.set(self.TYPE_HELP[selected])
        if selected == "DroidCam WiFi":
            self.droidcam_fields.grid(row=5, column=0, columnspan=2, sticky="ew", padx=5)
            self._update_droidcam_preview()
        else:
            self.droidcam_fields.grid_remove()

    def _droidcam_fields_changed(self, *_args) -> None:
        if self.network_type.get() != "DroidCam WiFi": return
        generated = self.build_droidcam_url(self.droidcam_ip.get(), self.droidcam_port.get())
        self.droidcam_preview.set(f"URL generada:\n{generated}")
        if self.droidcam_ip.get().strip(): self.network_url.set(generated)

    def _update_droidcam_preview(self) -> None:
        generated = self.build_droidcam_url(
            self.droidcam_ip.get().strip() or "192.168.1.3",
            self.droidcam_port.get(),
        )
        self.droidcam_preview.set(f"URL generada:\n{generated}")

    @staticmethod
    def build_droidcam_url(phone_ip: str, port: str = "4747") -> str:
        return f"http://{phone_ip.strip()}:{port.strip() or '4747'}/video"

    @staticmethod
    def validate_camera_url(url: str) -> None:
        raw = url.strip()
        if not raw.lower().startswith(("http://", "https://", "rtsp://")):
            raise ValueError("Debe comenzar con http://, https:// o rtsp://")
        try: parsed = urlsplit(raw)
        except ValueError as exc: raise ValueError("Dirección de cámara inválida.") from exc
        if not parsed.hostname:
            raise ValueError("Dirección de cámara inválida.")

    def _validate_network_form(self) -> None:
        if self.network_type.get() == "DroidCam WiFi":
            try: ipaddress.ip_address(self.droidcam_ip.get().strip())
            except ValueError as exc:
                raise ValueError("Introduce una IP válida, por ejemplo 192.168.1.3") from exc
        self.validate_camera_url(self.network_url.get())

    def use_selected(self) -> None:
        try:
            source = self.controller.use(self.selected.get())
            if self.preferred.get(): self.controller.set_preferred(source.source_id)
        except (PermissionError, ValueError, RuntimeError) as exc: self.status.configure(text=str(exc)); return
        if self.on_use(source): self.close()
        else: self.status.configure(text="No se puede cambiar de cámara durante un registro.")

    def close(self) -> None:
        if self.window.winfo_exists(): self.window.destroy()
        self.on_close()
