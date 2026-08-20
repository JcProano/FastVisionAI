from __future__ import annotations

import ipaddress
from typing import Callable
from urllib.parse import urlsplit

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except ModuleNotFoundError:  # pragma: no cover
    tk = None  # type: ignore[assignment]
    messagebox = None  # type: ignore[assignment]
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
                 on_delete: Callable[[CameraSourceDTO], bool] | None = None,
                 on_close: Callable[[], None] | None = None) -> None:
        if tk is None or ttk is None: raise RuntimeError("Tkinter no está disponible")
        self.controller = controller; self.on_use = on_use
        self.current_source_id = current_source_id; self.on_close = on_close or (lambda: None)
        self.on_delete = on_delete
        self.window = tk.Toplevel(parent); self.window.title("Seleccionar cámara")
        self.window.geometry("620x690"); self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.selected_source_id = tk.StringVar(value="")
        # Compatibility alias for existing tests/callers; the value is always a source_id.
        self.selected = self.selected_source_id
        self._selected_was_available = False
        self.preferred = tk.BooleanVar(value=False)
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
        ttk.Checkbutton(self.window, text="Recordar como cámara principal",
                        variable=self.preferred).pack(anchor="w", padx=12, pady=(5, 0))
        actions = ttk.Frame(self.window, padding=12); actions.pack(fill="x")
        ttk.Button(actions, text="Actualizar", command=self.refresh).pack(side="left", padx=3)
        ttk.Button(actions, text="Probar", command=self.test_selected).pack(side="left", padx=3)
        ttk.Button(actions, text="USAR ESTA CÁMARA", command=self.use_selected).pack(side="left", padx=3)
        ttk.Button(actions, text="Cancelar", command=self.close).pack(side="right", padx=3)
        self._update_network_guidance()
        self.refresh()

    def focus(self) -> None: self.window.lift(); self.window.focus_force()

    def refresh(self) -> None:
        previous_id = self.selected_source_id.get()
        previous_source = next(
            (item for item in self.controller.sources if item.source_id == previous_id),None)
        previous_was_available = bool(previous_source and previous_source.available)
        result = self.controller.refresh()
        for frame in (self.local_frame, self.network_frame):
            for child in frame.winfo_children(): child.destroy()
        local = tuple(item for item in result.sources if item.source_type is CameraSourceType.LOCAL_V4L2)
        network = tuple(item for item in result.sources if item.source_type is not CameraSourceType.LOCAL_V4L2)
        self._render_group(self.local_frame, local, "No se encontraron cámaras locales.")
        self._render_group(self.network_frame, network, "No hay cámaras IP guardadas.")
        existing = next((item for item in result.sources if item.source_id == previous_id),None)
        if existing is not None:
            self.selected_source_id.set(existing.source_id)
        elif result.selected is not None:
            self.selected_source_id.set(result.selected.source_id)
        else:
            self.selected_source_id.set("")
        selected = next(
            (item for item in result.sources
             if item.source_id == self.selected_source_id.get()),None)
        self._selected_was_available=bool(selected and selected.available)
        self.preferred.set(bool(selected and selected.preferred))
        if previous_id and existing is None and previous_was_available:
            self.status.configure(text="La fuente seleccionada ya no está disponible.")
        elif result.preferred_unavailable:
            self.status.configure(text="La cámara principal guardada no está disponible.")
        elif not result.sources:
            self.status.configure(text="Desconectada — conecte una cámara y pulse Actualizar.")
        elif selected is not None:
            self.status.configure(text="")

    def _render_group(self, frame, sources, empty: str) -> None:
        if not sources: ttk.Label(frame, text=empty).pack(anchor="w"); return
        for source in sources:
            row = ttk.Frame(frame); row.pack(fill="x", pady=3)
            label = source.display_name + (" — Cámara principal" if source.preferred else "")
            ttk.Radiobutton(row, text=label, variable=self.selected_source_id,
                            value=source.source_id, command=self._selection_changed).pack(anchor="w")
            kind = ("Cámara virtual" if source.details.get("virtual") else
                    str(source.details.get("transport", source.source_type.value)))
            endpoint = source.details.get("endpoint")
            resolution = source.details.get("resolution")
            resolution_text = (f" · {resolution[0]}×{resolution[1]}"
                               if isinstance(resolution, tuple) and len(resolution) == 2 else "")
            active = source.source_id == self.current_source_id()
            availability = "ACTIVA" if active else "DISPONIBLE" if source.available else "OFFLINE"
            ttk.Label(row, text=f"{availability} · {kind}{resolution_text}" +
                      (f" · {endpoint}" if endpoint else "")).pack(anchor="w", padx=22)
            row_actions=ttk.Frame(row);row_actions.pack(anchor="e")
            ttk.Button(row_actions,text="PROBAR",command=lambda item=source:self._probe(item)).pack(side="left",padx=2)
            if source.source_type is not CameraSourceType.LOCAL_V4L2:
                ttk.Button(row_actions,text="EDITAR",command=lambda item=source:self.edit_source(item)).pack(side="left",padx=2)
                ttk.Button(row_actions,text="ELIMINAR",command=lambda item=source:self.delete_source(item)).pack(side="left",padx=2)

    def _use(self, source: CameraSourceDTO) -> None:
        self.selected_source_id.set(source.source_id);self._selection_changed();self.use_selected()

    def _probe(self, source: CameraSourceDTO) -> None:
        self.selected_source_id.set(source.source_id);self._selection_changed();self.test_selected()

    def edit_source(self, source: CameraSourceDTO) -> None:
        configured=next((item for item in self.controller.discovery.config.network_sources
                         if item.source_id == source.source_id),None)
        if configured is None:return
        dialog=tk.Toplevel(self.window);dialog.title("Editar cámara")
        name=tk.StringVar(dialog,value=configured.name)
        kind=tk.StringVar(dialog,value=configured.source_type.value)
        url=tk.StringVar(dialog,value=configured.url)
        preferred=tk.BooleanVar(dialog,value=source.preferred)
        for row,(label,variable) in enumerate((("Nombre",name),("Tipo",kind),("URL / origen",url))):
            ttk.Label(dialog,text=label).grid(row=row,column=0,sticky="w",padx=8,pady=5)
            if label == "Tipo":
                ttk.Combobox(dialog,textvariable=variable,state="readonly",
                    values=("NETWORK_HTTP","NETWORK_RTSP","CUSTOM")).grid(row=row,column=1,sticky="ew",padx=8)
            else:ttk.Entry(dialog,textvariable=variable,width=52).grid(row=row,column=1,sticky="ew",padx=8)
        ttk.Label(dialog,text=("HTTP/MJPEG: http://192.168.1.12:4747/video\n"
                              "RTSP: rtsp://usuario:password@192.168.1.50:554/stream1"),
                  justify="left").grid(row=3,column=0,columnspan=2,sticky="w",padx=8,pady=5)
        ttk.Checkbutton(dialog,text="CÁMARA PRINCIPAL",variable=preferred).grid(row=4,column=0,columnspan=2,sticky="w",padx=8)
        def save() -> None:
            try:
                self.validate_camera_url(url.get())
                self.controller.update_network_source(
                    source.source_id,name.get(),CameraSourceType(kind.get()),url.get(),
                    preferred=preferred.get(),
                )
            except (ValueError,RuntimeError) as exc:self.status.configure(text=str(exc));return
            dialog.destroy();self.refresh();self.status.configure(text="Cámara actualizada.")
        ttk.Button(dialog,text="GUARDAR",command=save).grid(row=5,column=0,padx=8,pady=10)
        ttk.Button(dialog,text="CANCELAR",command=dialog.destroy).grid(row=5,column=1,padx=8,pady=10)

    def delete_source(self, source: CameraSourceDTO) -> None:
        if source.source_type is CameraSourceType.LOCAL_V4L2:return
        if not messagebox.askyesno("¿Eliminar esta cámara?",
            f"Nombre:\n{source.display_name}\n\nEsta acción eliminará la configuración guardada de la cámara.",
            parent=self.window):return
        try:
            if self.on_delete is not None:self.on_delete(source)
            else:self.controller.remove_network_source(source.source_id)
        except (ValueError,RuntimeError) as exc:self.status.configure(text=str(exc));return
        self.selected.set("");self.refresh();self.status.configure(text="Cámara eliminada.")

    def _selection_changed(self) -> None:
        source = next((item for item in self.controller.sources
                       if item.source_id == self.selected_source_id.get()),None)
        self.preferred.set(bool(source and source.preferred))
        self._selected_was_available=bool(source and source.available)
        if source is not None:self.status.configure(text="")

    def test_selected(self) -> None:
        source_id = self.selected_source_id.get()
        if not any(item.source_id == source_id for item in self.controller.sources):
            self.status.configure(text="Seleccione una cámara disponible."); return
        available=self.controller.probe(source_id)
        self.refresh()
        self.selected_source_id.set(source_id)
        self._selected_was_available=available
        self.status.configure(text="✓ Cámara disponible" if available
                              else "✗ Cámara offline; no se pudo conectar")

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
        if not raw.lower().startswith(("http://", "https://", "rtsp://", "rtsps://")):
            raise ValueError("Debe comenzar con http://, https://, rtsp:// o rtsps://")
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
        source_id=self.selected_source_id.get()
        source=next((item for item in self.controller.sources
                     if item.source_id == source_id),None)
        if source is None:
            self.status.configure(text="Seleccione una cámara disponible.")
            return
        if not source.available:
            if not self.controller.probe(source_id):
                self.status.configure(text="La cámara seleccionada está offline; no se pudo conectar.")
                return
            self.refresh()
            self.selected_source_id.set(source_id)
        try:
            source = self.controller.use(source_id)
        except (PermissionError, ValueError, RuntimeError) as exc: self.status.configure(text=str(exc)); return
        # Switch the single session-owned capture first. Persistence controls a
        # future startup and must not delay using the camera just chosen now.
        if not self.on_use(source):
            self.status.configure(text="No se puede cambiar de cámara durante un registro.")
            return
        try:
            # Persist both directions: clearing the checkbox must stop an old
            # DroidCam/network source from taking precedence on the next start.
            if self.preferred.get() or source.preferred:
                self.controller.set_preferred(source.source_id if self.preferred.get() else None)
        except RuntimeError as exc:
            self.status.configure(text=str(exc))
            return
        self.close()

    def close(self) -> None:
        if self.window.winfo_exists(): self.window.destroy()
        self.on_close()
