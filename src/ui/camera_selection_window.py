from __future__ import annotations

from typing import Callable
from urllib.parse import quote, urlsplit

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except ModuleNotFoundError:  # pragma: no cover
    tk = None  # type: ignore[assignment]
    messagebox = None  # type: ignore[assignment]
    ttk = None  # type: ignore[assignment]

from src.camera.source_discovery import (
    CameraSelectionController, CameraSourceDTO, CameraSourceType, redact_url,
)


class NetworkCameraDialog:
    """Shared add/edit modal; probing never mutates saved or active camera state."""

    CONNECTION_TYPES = ("HTTP/MJPEG", "HTTPS", "RTSP", "RTSPS", "URL personalizada")

    def __init__(self, parent, controller: CameraSelectionController, *,
                 on_saved: Callable[[CameraSourceDTO], None],
                 source: CameraSourceDTO | None = None) -> None:
        if tk is None or ttk is None: raise RuntimeError("Tkinter no está disponible")
        self.parent = parent; self.controller = controller; self.on_saved = on_saved
        self.source = source
        self.window = tk.Toplevel(parent)
        self.window.title("EDITAR CÁMARA IP" if source else "AGREGAR CÁMARA IP")
        self.window.geometry("600x500"); self.window.resizable(False, False)
        self.window.transient(parent); self.window.grab_set()
        self.window.protocol("WM_DELETE_WINDOW", self.cancel)
        self.window.configure(background="#07111D")
        self.name=tk.StringVar(self.window);self.profile=tk.StringVar(self.window)
        self.connection_type=tk.StringVar(self.window,value="RTSP")
        self.host=tk.StringVar(self.window);self.port=tk.StringVar(self.window)
        self.path=tk.StringVar(self.window);self.username=tk.StringVar(self.window)
        self.password=tk.StringVar(self.window);self.full_url=tk.StringVar(self.window)
        self.preview=tk.StringVar(self.window);self.result=tk.StringVar(self.window)
        shell=ttk.Frame(self.window,style="Card.TFrame",padding=14)
        shell.pack(fill="both",expand=True,padx=12,pady=12)
        fields=(("Nombre de cámara *",self.name),("Fabricante / Perfil",self.profile),
                ("Tipo de conexión *",self.connection_type),("Host / IP *",self.host),
                ("Puerto",self.port),("Ruta / Stream",self.path),
                ("Usuario",self.username),("Contraseña",self.password),
                ("URL completa (modo simple)",self.full_url))
        for row,(label,variable) in enumerate(fields):
            ttk.Label(shell,text=label,style="CardText.TLabel").grid(
                row=row,column=0,sticky="w",padx=(0,12),pady=5)
            if variable is self.connection_type:
                widget=ttk.Combobox(shell,textvariable=variable,
                    values=self.CONNECTION_TYPES,state="readonly",width=39)
            else:
                widget=ttk.Entry(shell,textvariable=variable,width=44,
                                 show="*" if variable is self.password else "")
            widget.grid(row=row,column=1,sticky="ew",pady=5)
        ttk.Label(shell,text="URL final / Vista previa",style="CardText.TLabel").grid(
            row=9,column=0,sticky="nw",padx=(0,12),pady=5)
        ttk.Label(shell,textvariable=self.preview,style="CardText.TLabel",
                  wraplength=390).grid(row=9,column=1,sticky="w",pady=5)
        ttk.Label(shell,textvariable=self.result,style="Institution.TLabel",
                  wraplength=540).grid(row=10,column=0,columnspan=2,sticky="w",pady=(7,3))
        actions=ttk.Frame(shell,style="CardBody.TFrame")
        actions.grid(row=11,column=0,columnspan=2,sticky="ew",pady=(10,0))
        ttk.Button(actions,text="PROBAR CONEXIÓN",command=self.test_connection,
                   style="Secondary.TButton").pack(side="left")
        ttk.Button(actions,text="CANCELAR",command=self.cancel,
                   style="Secondary.TButton").pack(side="right",padx=(8,0))
        ttk.Button(actions,text="GUARDAR CAMBIOS" if source else "GUARDAR CÁMARA",
                   command=self.save,style="Primary.TButton").pack(side="right")
        shell.columnconfigure(1,weight=1)
        for variable in (self.connection_type,self.host,self.port,self.path,
                         self.username,self.password,self.full_url):
            variable.trace_add("write",self._update_preview)
        if source is not None:self._load(source)
        self._update_preview();self._center()

    def _load(self, source: CameraSourceDTO) -> None:
        configured=next(item for item in self.controller.discovery.config.network_sources
                        if item.source_id == source.source_id)
        parsed=urlsplit(configured.url);self.name.set(configured.name)
        self.connection_type.set(_connection_label(configured.source_type,parsed.scheme))
        self.host.set(parsed.hostname or "")
        self.port.set("" if parsed.port is None else str(parsed.port))
        self.path.set(parsed.path.lstrip("/"));self.username.set(parsed.username or "")
        self.password.set(parsed.password or "")
        if parsed.username is None:self.full_url.set(configured.url)

    def _source(self) -> tuple[CameraSourceType,str]:
        name=self.name.get().strip()
        if not name:raise ValueError("Nombre de cámara es obligatorio.")
        label=self.connection_type.get();kind=_source_type(label)
        complete=self.full_url.get().strip()
        if complete:
            CameraSelectionWindow.validate_camera_url(complete)
            return kind,complete
        if label == "URL personalizada":
            raise ValueError("Ingrese una URL completa para el tipo personalizado.")
        host=self.host.get().strip()
        if not host:raise ValueError("Host / IP es obligatorio.")
        port=self.port.get().strip()
        if port and (not port.isdigit() or not 1 <= int(port) <= 65535):
            raise ValueError("Puerto inválido.")
        credentials=""
        if self.username.get().strip():
            credentials=quote(self.username.get().strip(),safe="")
            if self.password.get():credentials += ":"+quote(self.password.get(),safe="")
            credentials += "@"
        scheme={"HTTP/MJPEG":"http","HTTPS":"https","RTSP":"rtsp","RTSPS":"rtsps"}[label]
        url=f"{scheme}://{credentials}{host}{(':'+port) if port else ''}"
        path=self.path.get().strip().lstrip("/")
        if path:url += "/"+path
        CameraSelectionWindow.validate_camera_url(url)
        return kind,url

    def _update_preview(self,*_args) -> None:
        try:self.preview.set(redact_url(self._source()[1]))
        except ValueError:self.preview.set("Complete una URL o los campos de conexión.")

    def test_connection(self) -> None:
        try:
            kind,url=self._source()
            connected,resolution=self.controller.probe_network_source_details(
                self.name.get(),kind,url)
        except (ValueError,RuntimeError) as exc:self.result.set(str(exc));return
        detail="N/D" if resolution is None else f"{resolution[0]}×{resolution[1]}"
        self.result.set(("CONECTADA" if connected else "NO CONECTADA")+
                        f" · {self.connection_type.get()} · Resolución {detail}")

    def save(self) -> None:
        try:
            kind,url=self._source()
            saved=(self.controller.add_network_source(self.name.get(),kind,url)
                   if self.source is None else
                   self.controller.update_network_source(
                       self.source.source_id,self.name.get(),kind,url,
                       preferred=self.source.preferred))
        except (ValueError,RuntimeError) as exc:self.result.set(str(exc));return
        self.on_saved(saved);self.cancel()

    def cancel(self) -> None:
        try:self.window.grab_release()
        except Exception:pass
        if self.window.winfo_exists():self.window.destroy()

    def _center(self) -> None:
        self.window.update_idletasks()
        x=self.parent.winfo_rootx()+max(0,(self.parent.winfo_width()-600)//2)
        y=self.parent.winfo_rooty()+max(0,(self.parent.winfo_height()-500)//2)
        self.window.geometry(f"600x500+{x}+{y}")


def _source_type(label: str) -> CameraSourceType:
    return (CameraSourceType.NETWORK_RTSP if label in {"RTSP","RTSPS"} else
            CameraSourceType.NETWORK_HTTP if label in {"HTTP/MJPEG","HTTPS"} else
            CameraSourceType.CUSTOM)


def _connection_label(kind: CameraSourceType, scheme: str) -> str:
    if kind is CameraSourceType.CUSTOM:return "URL personalizada"
    if kind is CameraSourceType.NETWORK_RTSP:return "RTSPS" if scheme == "rtsps" else "RTSP"
    return "HTTPS" if scheme == "https" else "HTTP/MJPEG"


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
        ttk.Button(network_card, text="+ AGREGAR CÁMARA IP",
                   command=self.show_network_form).pack(anchor="w", pady=(8, 0))
        self.network_dialog: NetworkCameraDialog | None = None
        self.status = ttk.Label(self.window, text=""); self.status.pack(fill="x", padx=12)
        ttk.Checkbutton(self.window, text="CÁMARA PRINCIPAL (recordar)",
                        variable=self.preferred).pack(anchor="w", padx=12, pady=(5, 0))
        actions = ttk.Frame(self.window, padding=12); actions.pack(fill="x")
        ttk.Button(actions, text="Actualizar", command=self.refresh).pack(side="left", padx=3)
        ttk.Button(actions, text="Probar", command=self.test_selected).pack(side="left", padx=3)
        ttk.Button(actions, text="USAR ESTA CÁMARA", command=self.use_selected).pack(side="left", padx=3)
        ttk.Button(actions, text="Cancelar", command=self.close).pack(side="right", padx=3)
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
        self._open_network_dialog(source)

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

    def show_network_form(self) -> None:
        self._open_network_dialog(None)

    def _open_network_dialog(self, source: CameraSourceDTO | None) -> None:
        current=getattr(self,"network_dialog",None)
        if current is not None and current.window.winfo_exists():
            current.window.lift();current.window.focus_force();return
        self.network_dialog=NetworkCameraDialog(
            self.window,self.controller,on_saved=self._network_saved,source=source,
        )

    def _network_saved(self, source: CameraSourceDTO) -> None:
        self.refresh()
        self.selected_source_id.set(source.source_id)
        self._selection_changed()
        self.status.configure(
            text="Cámara guardada y seleccionada. Pulse USAR ESTA CÁMARA para conectarla."
        )

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
