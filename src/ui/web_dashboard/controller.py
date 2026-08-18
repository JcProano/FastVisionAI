"""Safe read-only web projection over existing UI controllers and snapshots."""
from __future__ import annotations
import hashlib
import json
import secrets
import threading
import dataclasses
from datetime import datetime
from urllib.parse import parse_qs

from src.camera.source_discovery import redact_url
from src.ui.people.contracts import PeopleSearchFiltersDTO
from . import html


class WebDashboardController:
    def __init__(self, snapshot_provider, *, people=None, history=None, attendance=None,
                 reports=None, system_health=None, identity_provider=None,
                 camera_provider=None) -> None:
        self.snapshot_provider=snapshot_provider;self.people=people;self.history=history
        self.attendance=attendance;self.reports=reports;self.system_health=system_health
        self.identity_provider=identity_provider;self.camera_provider=camera_provider or (lambda:{})
        self._salt=secrets.token_bytes(32);self._tokens={};self._photos={};self._lock=threading.Lock()

    def dashboard_payload(self) -> dict[str, object]:
        value=self.snapshot_provider()
        if value is None:
            camera=self._safe_camera()
            return {"available":False,"camera":camera.get("state","DESCONECTADA"),"recognition":"N/D","database":"N/D","attendance":"N/D","gallery":0,"statistics":{"people_present":None,"recognitions_today":None,"check_ins_today":None,"late_today":None},"recent_recognitions":[],"recent_attendance":[]}
        recognitions=[]
        for item in value.recent_recognitions:
            recognitions.append({"photo":self._photo_url(item.photo),"name":item.display_name,"time":item.local_time,"similarity":item.similarity})
        attendance=[]
        for item in value.recent_attendance:
            attendance.append({"photo":self._photo_url(item.photo),"name":item.display_name,"check_in":item.check_in_local,"check_out":item.check_out_local,"status":item.status})
        camera=self._safe_camera()
        return {"available":True,"camera":value.camera_state,"camera_name":camera.get("name","N/D"),"camera_type":camera.get("type","N/D"),"camera_source":camera.get("source","N/D"),"recognition":value.recognition_state,"database":value.database_state,"attendance":value.attendance_state,"gallery":value.gallery_identities,"statistics":{"people_present":value.people_present,"recognitions_today":value.recognitions_today,"check_ins_today":value.check_ins_today,"late_today":value.late_today},"recent_recognitions":recognitions,"recent_attendance":attendance,"generated_at":value.generated_at.isoformat()}

    def json_bytes(self) -> bytes:
        return json.dumps(self.dashboard_payload(),ensure_ascii=False,separators=(",",":")).encode("utf-8")

    def render(self, path: str, query: str = "") -> bytes:
        if path=="/":return self._dashboard_page()
        if path=="/people":return self._people_page(parse_qs(query,keep_blank_values=False))
        if path=="/history":return self._history_page()
        if path=="/attendance":return self._attendance_page()
        if path=="/reports":return self._reports_page()
        if path=="/system":return self._system_page()
        raise KeyError(path)

    def thumbnail(self, token: str) -> tuple[str,bytes] | None:
        if len(token)!=64 or any(character not in "0123456789abcdef" for character in token):return None
        with self._lock:
            photo=self._photos.get(token);person_id=self._tokens.get(token)
        if photo is not None:return photo
        if person_id is None or self.identity_provider is None:return None
        value=self.identity_provider.get_thumbnail(person_id)
        if not value.available or not value.image_bytes:return None
        return _mime(value.format),bytes(value.image_bytes)

    def _photo_url(self, photo) -> str | None:
        if not photo.available or not photo.image_bytes:return None
        payload=bytes(photo.image_bytes);token=hashlib.sha256(self._salt+payload).hexdigest()
        with self._lock:self._photos[token]=(_mime(photo.format),payload)
        return f"/api/thumbnails/{token}"

    def _person_token(self, person_id: str) -> str:
        token=hashlib.sha256(self._salt+person_id.encode("utf-8")).hexdigest()
        with self._lock:self._tokens[token]=person_id
        return token

    def _safe_camera(self) -> dict[str,str]:
        try:value=dict(self.camera_provider())
        except Exception:return {"state":"DESCONECTADA","name":"N/D","type":"N/D","source":"N/D"}
        source=str(value.get("source","N/D"))
        if source.lower().startswith(("http://","https://","rtsp://")):source=redact_url(source)
        return {"state":str(value.get("state","DESCONECTADA")),"name":str(value.get("name","N/D")),"type":str(value.get("type","N/D")),"source":source}

    def _dashboard_page(self)->bytes:
        data=self.dashboard_payload();stats=data["statistics"]
        cards="".join(f'<div class="card"><div>{label}</div><div class="value">{stats[key] if stats[key] is not None else "N/D"}</div></div>' for key,label in (("people_present","Personas presentes"),("recognitions_today","Reconocimientos hoy"),("check_ins_today","Entradas hoy"),("late_today","Retrasos")))
        states=html.table(("Cámara","Reconocimiento","Base de datos","Asistencia","Galería"),((data["camera"],data["recognition"],data["database"],data["attendance"],data["gallery"]),))
        recognition_rows=tuple((item["photo"],item["name"],item["time"],_similarity(item["similarity"])) for item in data["recent_recognitions"])
        attendance_rows=tuple((item["photo"],item["name"],item["check_in"],item["check_out"],item["status"]) for item in data["recent_attendance"])
        camera_detail=f'<p>Fuente: {html.escape(str(data.get("camera_source","N/D")))} · Nombre: {html.escape(str(data.get("camera_name","N/D")))} · Tipo: {html.escape(str(data.get("camera_type","N/D")))}</p>'
        content=f'<section>{states}{camera_detail}</section><div class="grid">{cards}</div><div class="columns"><section><h3>Video en vivo</h3><img class="video" src="/api/video.mjpeg" alt="Video no disponible"></section><div><section><h3>Reconocimientos recientes</h3>{html.photo_table(("Foto","Nombre","Hora","Similitud"),recognition_rows)}</section><section><h3>Asistencia de hoy</h3>{html.photo_table(("Foto","Nombre","Entrada","Salida","Estado"),attendance_rows)}</section></div></div>'
        return html.page("Dashboard",content,refresh=5)

    def _people_page(self,query)->bytes:
        if self.people is None:return html.page("Personas","<p>Servicio no disponible.</p>")
        text=str(query.get("q",[""])[0])[:100]
        page=self.people.search(PeopleSearchFiltersDTO(text=text,limit=self.people.policy.default_page_size))
        rows=[]
        for item in page.people:
            token=self._person_token(item.person_id)
            rows.append((f"/api/thumbnails/{token}" if item.thumbnail_available else "",item.display_name,item.masked_cedula,item.phone,item.email,item.status))
        form=f'<form method="get"><input name="q" maxlength="100" value="{html.escape(text)}"><button>Buscar</button></form>'
        return html.page("Personas",form+html.photo_table(("Foto","Nombre","Cédula","Teléfono","Email","Estado"),tuple(rows)))

    def _history_page(self)->bytes:
        values=() if self.history is None else self.history.list(limit=50).events
        rows=tuple((item.display_name,item.timestamp.isoformat(),item.event_type,_similarity(item.similarity),redact_url(item.camera_id) if isinstance(item.camera_id,str) else item.camera_id) for item in values)
        return html.page("Historial",html.table(("Nombre","Fecha","Tipo","Similitud","Cámara"),rows))

    def _attendance_page(self)->bytes:
        values=() if self.attendance is None else self.attendance.day_list().days
        rows=tuple((item.display_name,item.masked_cedula,_time(item.check_in),_time(item.check_out),item.status) for item in values)
        return html.page("Asistencia",html.table(("Nombre","Cédula","Entrada","Salida","Estado"),rows))

    def _reports_page(self)->bytes:
        if self.reports is None:return html.page("Reportes","<p>Servicio no disponible.</p>")
        start,end=self.reports.default_dates();value=self.reports.generate("Resumen diario",end,end)
        source=((field.name,getattr(value,field.name)) for field in dataclasses.fields(value)) if dataclasses.is_dataclass(value) else vars(value).items()
        rows=tuple((key.replace("_"," ").title(),_plain(item)) for key,item in source if _safe_key(key))
        return html.page("Reportes",f"<p>Fecha: {end}</p>"+html.table(("Métrica","Valor"),rows))

    def _system_page(self)->bytes:
        if self.system_health is None:return html.page("Estado del sistema","<p>Servicio no disponible.</p>")
        value=self.system_health.snapshot();rows=tuple((component,level,message,checked) for component,level,message,checked in value.components)
        return html.page("Estado del sistema",f"<p>Estado general: {html.escape(value.overall_level)}</p>"+html.table(("Componente","Estado","Mensaje","Comprobado"),rows))


def _mime(value:str)->str:return "image/jpeg" if value.upper() in {"JPG","JPEG"} else "image/png"
def _similarity(value):return "N/D" if value is None else f"{float(value)*100:.1f}%"
def _time(value):return None if value is None else value.isoformat()
def _safe_key(key):return not any(word in key.lower() for word in ("person_id","embedding","template","password","hash","salt","path"))
def _plain(value):
    if isinstance(value,(str,int,float,bool)) or value is None:return value
    if isinstance(value,datetime):return value.isoformat()
    return len(value) if isinstance(value,(tuple,list)) else str(value)
