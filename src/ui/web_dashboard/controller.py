"""Safe read-only web projection over existing UI controllers and snapshots."""
from __future__ import annotations
import hashlib
import json
import secrets
import threading
import dataclasses
import time
from datetime import datetime
from urllib.parse import parse_qs
from src.ui.identification_semantics import (
    IdentificationVisualState, identification_visual_state,
)
from src.ui.operational_semantics import OperationalPresentationState, operational_title

from src.camera.source_discovery import redact_url
from src.ui.people.contracts import PeopleSearchFiltersDTO
from . import html


class WebDashboardController:
    def __init__(self, snapshot_provider, *, people=None, history=None, attendance=None,
                 reports=None, system_health=None, identity_provider=None,
                 camera_provider=None, actions=None, diagnostics_provider=None,
                 audit=None, backups=None, configuration=None,
                 presentation_provider=None, monotonic=time.monotonic,
                 modal_timeout_seconds: float = 60.0,
                 operational_state_provider=None) -> None:
        self.snapshot_provider=snapshot_provider;self.people=people;self.history=history
        self.attendance=attendance;self.reports=reports;self.system_health=system_health
        self.identity_provider=identity_provider;self.camera_provider=camera_provider or (lambda:{})
        self.actions=actions or {};self.diagnostics_provider=diagnostics_provider
        self.audit=audit;self.backups=backups;self.configuration=configuration
        self.presentation_provider=presentation_provider;self._monotonic=monotonic
        self.operational_state_provider=operational_state_provider
        self._modal_timeout=float(modal_timeout_seconds);self._modal_key=None
        self._modal_started=float("-inf");self._dismissed_key=None
        self._enrollment_stage="IDLE";self._enrollment_summary={}
        self._enrollment_result=None
        self._salt=secrets.token_bytes(32);self._tokens={};self._photos={};self._lock=threading.Lock()

    def dashboard_payload(self) -> dict[str, object]:
        value=self.snapshot_provider()
        people_summary=self._people_summary()
        if value is None:
            camera=self._safe_camera()
            return {"available":False,"camera":camera.get("state","DESCONECTADA"),"recognition":"N/D","database":"N/D","attendance":"N/D","gallery":0,"people_summary":people_summary,"statistics":{"people_present":None,"recognitions_today":None,"check_ins_today":None,"late_today":None},"recent_recognitions":[],"recent_attendance":[],"presentation":self._presentation_payload()}
        recognitions=[]
        for item in value.recent_recognitions:
            state=getattr(item,"recognition_state","NOT_EVALUATED").upper()
            evaluated=getattr(item,"evaluated",state == "MATCH") is True
            recognitions.append({"photo":self._photo_url(item.photo),"name":item.display_name,"time":item.local_time,"similarity":item.similarity,"state":_visual_state(state,evaluated)})
        attendance=[]
        for item in value.recent_attendance:
            attendance.append({"photo":self._photo_url(item.photo),"name":item.display_name,"check_in":item.check_in_local,"check_out":item.check_out_local,"status":item.status})
        camera=self._safe_camera()
        people_summary["biometric_identities"]=value.gallery_identities
        people_summary["without_face"]=max(0, people_summary["registered_people"]-value.gallery_identities)
        return {"available":True,"camera":value.camera_state,"camera_name":camera.get("name","N/D"),"camera_type":camera.get("type","N/D"),"camera_source":camera.get("source","N/D"),"recognition":value.recognition_state,"database":value.database_state,"attendance":value.attendance_state,"gallery":value.gallery_identities,"people_summary":people_summary,"statistics":{"people_present":value.people_present,"recognitions_today":value.recognitions_today,"check_ins_today":value.check_ins_today,"late_today":value.late_today},"recent_recognitions":recognitions,"recent_attendance":attendance,"presentation":self._presentation_payload(),"generated_at":value.generated_at.isoformat()}

    def _people_summary(self) -> dict[str, int]:
        if self.people is None:return {"registered_people":0,"biometric_identities":0,"without_face":0}
        try:
            result=self.people.search(PeopleSearchFiltersDTO(limit=self.people.policy.default_page_size))
            return {"registered_people":result.total,"biometric_identities":0,"without_face":result.total}
        except Exception:return {"registered_people":0,"biometric_identities":0,"without_face":0}

    def json_bytes(self) -> bytes:
        return json.dumps(self.dashboard_payload(),ensure_ascii=False,separators=(",",":")).encode("utf-8")

    def api(self, path: str, query: str = "") -> dict[str, object]:
        """Read-only API projections.  They intentionally expose DTO fields only."""
        if path == "/api/dashboard": return self.dashboard_payload()
        if path == "/api/presentation": return self._presentation_payload()
        if path == "/api/enrollment/status": return self._enrollment_payload()
        if path == "/api/cameras":
            sources = self._action("cameras", default=())
            return {"cameras": tuple(self._camera_dto(item) for item in sources)}
        if path == "/api/people": return self._people_payload(parse_qs(query, keep_blank_values=False))
        if path == "/api/attendance": return self._attendance_payload()
        if path == "/api/history": return self._history_payload()
        if path == "/api/reports": return self._reports_payload()
        if path in {"/api/system", "/api/diagnostics"}: return self._system_payload()
        if path == "/api/audit": return self._audit_payload()
        if path == "/api/backups": return self._backups_payload()
        if path == "/api/settings": return self._settings_payload()
        raise KeyError(path)

    def action(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        """Explicitly allowlisted commands wired by composition in main.py."""
        routes = {
            "/api/camera/select": "camera_select", "/api/camera/connect": "camera_select", "/api/camera/preferred": "camera_preferred",
            "/api/camera/network": "camera_network", "/api/camera/network/edit": "camera_network_update", "/api/camera/probe": "camera_probe",
            "/api/camera/network/delete": "camera_network_delete",
            "/api/person/update": "person_update", "/api/person/delete": "person_delete",
            "/api/person/photo": "person_photo", "/api/person/face": "person_face",
            "/api/enrollment/start": "enrollment_start", "/api/enrollment/person": "enrollment_person",
            "/api/enrollment/capture/start": "enrollment_capture_start",
            "/api/enrollment/cancel": "enrollment_cancel", "/api/enrollment/photo": "enrollment_photo",
            "/api/enrollment/confirm": "enrollment_confirm",
            "/api/presentation/ignore": "presentation_ignore",
            "/api/attendance/manual": "attendance_manual", "/api/backups": "backup_create",
            "/api/shutdown": "shutdown",
        }
        key = routes.get(path)
        if key is None: raise KeyError(path)
        if key == "camera_network_delete":
            if payload.get("confirmed") is not True:raise ValueError("Se requiere confirmación.")
            source_id=str(payload.get("source_id",""))
            if not source_id or "/" in source_id:raise ValueError("Identificador inválido.")
            value=self._action(key,source_id)
        elif key.startswith("person_"):
            token=str(payload.get("token",""));person_id=self._resolve_person_token(token)
            if key == "person_delete":
                if payload.get("confirmed") is not True or payload.get("confirmation") != "ELIMINAR":
                    raise ValueError("Se requiere confirmación reforzada.")
                value=self._action(key,person_id,True)
            else:value=self._action(key,person_id,payload)
        elif key == "presentation_ignore":
            self._dismissed_key=self._modal_key;self._modal_started=float("-inf");value=True
        elif key == "enrollment_start":
            current=self._presentation_payload()
            if current.get("kind") not in {"UNKNOWN","GALLERY_UNREGISTERED"}:
                raise ValueError("El registro requiere una persona no registrada.")
            self._enrollment_stage="PERSON";self._enrollment_summary={};self._enrollment_result=None;value=True
        elif key == "enrollment_person":
            if self._enrollment_stage != "PERSON":raise ValueError("Etapa de datos no activa.")
            value=self._action(key,payload)
            if value is False:raise RuntimeError("No se pudo iniciar enrollment.")
            self._enrollment_summary={k:str(payload.get(k,""))[:200] for k in ("first_name","last_name","cedula","position","department","company")}
            self._enrollment_stage="PREPARATION"
        elif key == "enrollment_capture_start":
            if self._enrollment_stage not in {"PREPARATION","CAPTURE"}:raise ValueError("Captura no disponible.")
            value=self._action(key,payload);self._enrollment_stage="CAPTURE"
        elif key == "enrollment_photo":
            if self._enrollment_stage != "PHOTO":raise ValueError("Fotografía no disponible.")
            choice=str(payload.get("action","")).upper()
            if choice == "TAKE":value=self._action("enrollment_photo_start",payload)
            elif choice == "SKIP":value=True;self._enrollment_stage="CONFIRMATION"
            elif choice == "CAPTURE":value=self._action("enrollment_photo_capture",payload)
            elif choice == "CONFIRM":value=self._action("enrollment_photo_confirm",payload);self._enrollment_stage="CONFIRMATION"
            else:raise ValueError("Acción de fotografía inválida.")
        elif key == "enrollment_confirm":
            if self._enrollment_stage != "CONFIRMATION":raise ValueError("Confirmación no disponible.")
            value=True;self._enrollment_stage="COMPLETE"
        elif key == "enrollment_cancel":
            value=self._action(key,payload);self._enrollment_stage="IDLE";self._enrollment_summary={};self._enrollment_result=None
        else:value = self._action(key, payload)
        return {"ok": True, "result": self._plain_dto(value)}

    def _enrollment_payload(self):
        raw=self._action("enrollment_status",default=None)
        progress=getattr(raw,"progress",raw)
        result=getattr(raw,"result",None)
        if result is None and raw is not None and hasattr(raw,"templates_registered"):result=raw
        if result is not None:self._enrollment_result=result
        elif self._enrollment_result is not None:result=self._enrollment_result
        if progress is not None and hasattr(progress,"accepted_samples"):
            accepted=int(progress.accepted_samples);target=int(progress.target_samples)
            if accepted >= target:self._enrollment_stage="VALIDATION"
            return {"active":True,"stage":self._enrollment_stage,"accepted_samples":accepted,
                    "target_samples":target,"instruction":str(progress.instruction),
                    "quality_score":progress.quality_score,"quality_band":progress.quality_band,
                    "can_continue":accepted >= target,"summary":dict(self._enrollment_summary)}
        if result is not None:
            if str(result.enrollment_status).casefold() == "enrolled" and self._enrollment_stage not in {"PHOTO","CONFIRMATION","COMPLETE"}:self._enrollment_stage="PHOTO"
            return {"active":self._enrollment_stage != "IDLE","stage":self._enrollment_stage,
                    "accepted_samples":int(result.templates_registered),"target_samples":5,
                    "instruction":"CAPTURA FACIAL COMPLETADA","quality_score":result.average_quality,
                    "quality_band":None,"can_continue":True,"summary":dict(self._enrollment_summary),
                    "success":self._enrollment_stage == "COMPLETE"}
        return {"active":self._enrollment_stage != "IDLE","stage":self._enrollment_stage,
                "accepted_samples":0,"target_samples":5,"instruction":None,
                "quality_score":None,"quality_band":None,"can_continue":self._enrollment_stage in {"PREPARATION","CONFIRMATION"},"summary":dict(self._enrollment_summary)}

    def delete(self, path: str) -> dict[str, object]:
        raise ValueError("La eliminación requiere confirmación JSON explícita.")

    def render(self, path: str, query: str = "") -> bytes:
        if path=="/":return self._dashboard_page()
        if path=="/people":return self._people_page(parse_qs(query,keep_blank_values=False))
        if path=="/history":return self._history_page()
        if path=="/attendance":return self._attendance_page()
        if path=="/reports":return self._reports_page()
        if path in {"/system", "/diagnostics"}:return self._system_page()
        if path=="/camera":return self._camera_page()
        if path=="/backups":return self._simple_page("Copias de seguridad", self._backups_payload())
        if path=="/audit":return self._simple_page("Auditoría", self._audit_payload())
        if path=="/settings":return self._simple_page("Configuración", self._settings_payload())
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

    def _resolve_person_token(self, token: str) -> str:
        if len(token)!=64 or any(character not in "0123456789abcdef" for character in token):
            raise ValueError("Identificador inválido.")
        with self._lock:person_id=self._tokens.get(token)
        if person_id is None:raise ValueError("La persona ya no está disponible.")
        return person_id

    def _safe_camera(self) -> dict[str,str]:
        try:value=dict(self.camera_provider())
        except Exception:return {"state":"DESCONECTADA","name":"N/D","type":"N/D","source":"N/D"}
        source=str(value.get("source","N/D"))
        if source.lower().startswith(("http://","https://","rtsp://","rtsps://")):source=redact_url(source)
        return {"state":str(value.get("state","DESCONECTADA")),"name":str(value.get("name","N/D")),"type":str(value.get("type","N/D")),"source":source}

    def _dashboard_page(self)->bytes:
        data=self.dashboard_payload();stats=data["statistics"]
        cards="".join(f'<div class="card"><div>{label}</div><div class="value">{stats[key] if stats[key] is not None else "N/D"}</div></div>' for key,label in (("people_present","Personas presentes"),("recognitions_today","Reconocimientos hoy"),("check_ins_today","Entradas hoy"),("late_today","Retrasos")))
        summary=data["people_summary"]
        cards += "".join(f'<div class="card"><div>{label}</div><div class="value">{summary[key]}</div></div>' for key,label in (("registered_people","Personas registradas"),("biometric_identities","Identidades biométricas"),("without_face","Personas sin rostro")))
        states=html.table(("Cámara","Reconocimiento","Base de datos","Asistencia","Galería"),((data["camera"],data["recognition"],data["database"],data["attendance"],data["gallery"]),))
        recognition_rows=tuple((item["photo"],item["name"],item["time"],_similarity(item["similarity"]),item["state"]) for item in data["recent_recognitions"])
        attendance_rows=tuple((item["photo"],item["name"],item["check_in"],item["check_out"],item["status"]) for item in data["recent_attendance"])
        camera_detail=f'<p>Fuente: {html.escape(str(data.get("camera_source","N/D")))} · Nombre: {html.escape(str(data.get("camera_name","N/D")))} · Tipo: {html.escape(str(data.get("camera_type","N/D")))}</p>'
        modal=_modal_html(data.get("presentation",{}))
        content=f'''<section>{states}{camera_detail}</section><div class="grid">{cards}</div><div class="columns"><section><h3>Video en vivo <span id="video-state" class="badge">CONECTANDO</span></h3><img id="live-video" class="video" src="/api/video.mjpeg" alt="Cámara desconectada"><p id="video-meta">Cámara activa: {html.escape(str(data.get("camera_name","N/D")))}</p></section><div><section><h3>Actividad de reconocimiento reciente</h3>{html.photo_table(("Foto","Candidato / Nombre","Hora","Similitud","Estado"),recognition_rows)}</section><section><h3>Asistencia de hoy</h3>{html.photo_table(("Foto","Nombre","Entrada","Salida","Estado"),attendance_rows)}</section></div></div>{_modal_shell(modal)}<script>{_enrollment_script()}let last;async function webIgnore(){{await command('/api/presentation/ignore');location.reload()}}async function webEnroll(){{await command('/api/enrollment/start');await enrollmentStatus()}}async function vs(){{try{{const s=await (await fetch('/api/video/status',{{cache:'no-store'}})).json();document.getElementById('video-state').textContent=s.stale?'VIDEO SIN SEÑAL':'ACTIVA';document.getElementById('video-meta').textContent=s.available?'Último frame: hace '+s.age_seconds.toFixed(1)+' s · '+s.width+'×'+s.height:'Cámara desconectada';if(s.available&&s.sequence_id!==last){{last=s.sequence_id;document.getElementById('live-video').src='/api/video.mjpeg?ts='+Date.now()}}await enrollmentStatus()}}catch(_)}}setInterval(vs,2000);vs();</script>'''
        return html.page("Dashboard",content,refresh=5)

    def _presentation_payload(self):
        try:dto=None if self.presentation_provider is None else self.presentation_provider()
        except Exception:dto=None
        if dto is None:return {"active":False}
        operational = (None if self.operational_state_provider is None else
                       self.operational_state_provider(dto))
        if operational is OperationalPresentationState.GALLERY_UNREGISTERED:
            key=("GALLERY_UNREGISTERED",None);now=self._monotonic()
            if key != self._modal_key:
                self._modal_key=key;self._modal_started=now
                if key != self._dismissed_key:self._dismissed_key=None
            remaining=self._modal_timeout-(now-self._modal_started)
            if remaining <= 0 or key == self._dismissed_key:return {"active":False}
            return {"active":True,"kind":"GALLERY_UNREGISTERED",
                    "title":"PERSONA NO REGISTRADA","name":None,"photo":None,
                    "similarity":None,"status":"GALERÍA SIN IDENTIDADES",
                    "warning":"No existen rostros registrados en la galería.",
                    "details":[],"remaining_seconds":max(0,remaining)}
        if (operational is not None and
                operational is not OperationalPresentationState.RECOGNITION_RESULT):
            title=operational_title(operational)
            return {"active":True,"kind":operational.value,"title":title,
                    "name":None,"photo":None,"similarity":None,"status":title,
                    "warning":None,"details":[],
                    "remaining_seconds":self._modal_timeout}
        state=str(getattr(dto,"recognition_state","")).upper()
        evaluated=getattr(dto,"evaluated",None);person_id=getattr(dto,"candidate_person_id",None)
        visual_state=identification_visual_state(state,evaluated,person_id)
        valid=(visual_state is not IdentificationVisualState.NOT_PRESENTABLE or
               state in {"NO_GALLERY","INCOMPATIBLE"})
        if not valid:return {"active":False}
        key=(state,person_id);now=self._monotonic()
        if key != self._modal_key:
            self._modal_key=key;self._modal_started=now
            if key != self._dismissed_key:self._dismissed_key=None
        remaining=self._modal_timeout-(now-self._modal_started)
        if remaining <= 0 or key == self._dismissed_key:return {"active":False}
        name=getattr(dto,"candidate_display_name",None);photo=None;details=[]
        if person_id and self.identity_provider is not None:
            photo=f"/api/thumbnails/{self._person_token(person_id)}"
        if visual_state is IdentificationVisualState.IDENTIFIED:
            person=self.identity_provider.get_person(person_id) if self.identity_provider else None
            if person:
                name=person.display_name
                details=[{"label":label,"value":value or "N/D"} for label,value in (("Cédula",person.external_identifier),("Cargo",person.position),("Departamento",person.department),("Empresa",person.company),("Teléfono",person.phone),("Correo",person.email))]
            title,status,warning="PERSONA IDENTIFICADA","IDENTIFICADO",None
        elif visual_state is IdentificationVisualState.UNREGISTERED:
            title,status,warning="PERSONA NO REGISTRADA","NO REGISTRADA","No existe una identidad registrada para este rostro."
            name=None;photo=None
        elif visual_state is IdentificationVisualState.BIOMETRIC_CANDIDATE:
            title,status,warning="CANDIDATO BIOMÉTRICO","NO EVALUADO — SISTEMA PENDIENTE DE CALIBRACIÓN","El candidato más cercano no constituye una identificación."
        elif state == "NO_GALLERY":title,status,warning="GALERÍA VACÍA","NO EVALUADO",None
        else:title,status,warning="MODELO BIOMÉTRICO INCOMPATIBLE","NO EVALUADO",None
        return {"active":True,"kind":state,"title":title,"name":name,"photo":photo,
                "similarity":getattr(dto,"similarity",None),"status":status,"warning":warning,
                "details":details,"remaining_seconds":max(0,remaining)}

    def _camera_page(self) -> bytes:
        content='''<section><h3>Cámaras</h3><p id="camera-message" role="status"></p><div id="camera-list">Cargando cámaras…</div></section>
<section><h3>AGREGAR CÁMARA IP / CCTV</h3>
<label>Nombre <input id="camera-name" maxlength="120" required></label>
<label>Tipo <select id="camera-type" onchange="updateGuidance()"><option value="NETWORK_RTSP">RTSP</option><option value="NETWORK_HTTP">HTTP/MJPEG</option><option value="CUSTOM">URL personalizada</option></select></label>
<label>URL <input id="camera-url" maxlength="2000" required></label>
<p id="camera-example">Ejemplo: <code></code></p>
<div class="card"><strong>Ejemplos</strong><br>RTSP: <code>rtsp://usuario:contraseña@192.168.1.50:554/stream1</code><br>HTTP/MJPEG: <code>http://192.168.1.50:8080/video</code><br>DroidCam: <code>http://192.168.1.3:4747/video</code><p>La ruta exacta depende del fabricante y modelo de la cámara.</p></div>
<details><summary>¿Cómo encuentro la URL de mi cámara?</summary><ul><li>Busque en la configuración del equipo opciones como: RTSP, ONVIF, Streaming, Network Video o Integración.</li><li>La Jetson y la cámara deben estar en la misma red o tener conectividad entre sí.</li><li>Algunas cámaras requieren habilitar RTSP u ONVIF manualmente.</li></ul></details>
<details><summary>Ejemplos orientativos por fabricante</summary><p>Hikvision: <code>rtsp://usuario:contraseña@IP:554/Streaming/Channels/101</code><br>Dahua: <code>rtsp://usuario:contraseña@IP:554/cam/realmonitor?channel=1&amp;subtype=0</code><br>Reolink: <code>rtsp://usuario:contraseña@IP:554/h264Preview_01_main</code><br>Axis: <code>rtsp://usuario:contraseña@IP/axis-media/media.amp</code><br>DroidCam: <code>http://IP:4747/video</code></p><p>Estas rutas son ejemplos comunes. Pueden variar según modelo y firmware.</p></details>
<p>Compatible con USB/V4L2, RTSP, HTTP/MJPEG y fuentes personalizadas compatibles con OpenCV. ONVIF → RTSP estará disponible cuando se implemente; no todos los modelos propietarios son compatibles.</p>
<button id="probe-button" onclick="probeNewCamera()">Probar conexión</button> <button onclick="addNetwork()">Guardar cámara</button></section>
<script>
let csrf=''; const message=t=>document.getElementById('camera-message').textContent=t;
async function api(path,method='GET',body){const o={method,credentials:'same-origin',headers:{}};if(body){o.headers['Content-Type']='application/json';o.headers['X-CSRF-Token']=csrf;o.body=JSON.stringify(body)}const r=await fetch(path,o);const d=await r.json();if(!r.ok)throw Error(d.error||'Operación no disponible');return d}
function esc(v){const s=document.createElement('span');s.textContent=v??'';return s.innerHTML}
let listedCameras={};async function load(){try{const d=await api('/api/cameras');listedCameras=Object.fromEntries(d.cameras.map(c=>[c.id,c]));document.getElementById('camera-list').innerHTML='<div class="scroll"><table><thead><tr><th>Nombre</th><th>Tipo</th><th>Estado</th><th>Principal</th><th>Acciones</th></tr></thead><tbody>'+d.cameras.map(c=>`<tr><td>${esc(c.name)}${c.active?' <strong>ACTIVA AHORA</strong>':''}</td><td>${esc(c.type)}</td><td>${esc(c.status)}</td><td>${c.preferred?'★ CÁMARA PRINCIPAL':'—'}</td><td><button onclick="connectCamera('${esc(c.id)}')">USAR</button> <button onclick="probeCamera('${esc(c.id)}')">PROBAR</button> <button onclick="preferCamera('${esc(c.id)}')">☆ Principal</button> ${c.network?`<button onclick="editCamera('${esc(c.id)}')">EDITAR</button> <button onclick="deleteCamera('${esc(c.id)}')">ELIMINAR</button>`:''}</td></tr>`).join('')+'</tbody></table></div>'}catch(e){message(e.message)}}
async function mutate(path,body,method='POST'){try{await api(path,method,body);message('Solicitud enviada.');load()}catch(e){message(e.message)}}
function connectCamera(source_id){mutate('/api/camera/connect',{source_id})}function preferCamera(source_id){mutate('/api/camera/preferred',{source_id})}function probeCamera(source_id){mutate('/api/camera/probe',{source_id})}function editCamera(source_id){const camera=listedCameras[source_id];if(!camera)return;const nextName=prompt('Nombre',camera.name);if(nextName===null)return;const nextType=prompt('Tipo: NETWORK_HTTP, NETWORK_RTSP o CUSTOM',camera.type);if(nextType===null)return;const url=prompt('URL / origen\nHTTP: http://192.168.1.12:4747/video\nRTSP: rtsp://usuario:password@192.168.1.50:554/stream1');if(!url)return;mutate('/api/camera/network/edit',{source_id,name:nextName,type:nextType,url,preferred:camera.preferred})}function deleteCamera(source_id){const camera=listedCameras[source_id];if(camera&&confirm('¿Eliminar esta cámara?\n\nNombre: '+camera.name+'\n\nEsta acción eliminará la configuración guardada de la cámara.'))mutate('/api/camera/network/delete',{source_id,confirmed:true})}
const guidance={NETWORK_RTSP:'rtsp://usuario:contraseña@192.168.1.50:554/stream1',NETWORK_HTTP:'http://192.168.1.50:8080/video',CUSTOM:'rtsp://192.168.1.50:554/cam/realmonitor?channel=1&subtype=0'};
function formCamera(){return {name:document.getElementById('camera-name').value,type:document.getElementById('camera-type').value,url:document.getElementById('camera-url').value}}
function updateGuidance(){const example=guidance[document.getElementById('camera-type').value];const url=document.getElementById('camera-url');url.placeholder=example;document.querySelector('#camera-example code').textContent=example}
async function probeNewCamera(){const button=document.getElementById('probe-button');button.disabled=true;message('COMPROBANDO...');try{const d=await api('/api/camera/probe','POST',formCamera());const type=document.getElementById('camera-type').selectedOptions[0].textContent;const resolution=d.result.resolution;message(d.result.connected?'CONEXIÓN CORRECTA · Resolución: '+(resolution?resolution[0]+'×'+resolution[1]:'N/D')+' · Tipo: '+type:'OFFLINE · SIN VIDEO');}catch(e){message(e.message)}finally{button.disabled=false}}
function addNetwork(){mutate('/api/camera/network',formCamera())}
(async()=>{try{csrf=(await api('/api/session')).csrf_token;updateGuidance();load()}catch(e){message(e.message)}})();
</script>'''
        return html.page("Cámara", content)

    def _simple_page(self, title, payload) -> bytes:
        return html.page(title, "<pre>"+html.escape(json.dumps(payload, ensure_ascii=False, indent=2))+"</pre>")

    def _action(self, name, *args, default=None):
        callback=self.actions.get(name)
        if callback is None:return default
        return callback(*args)

    def _camera_dto(self, item):
        active = item.source_id == self._safe_camera().get("source")
        network = item.source_type.value != "LOCAL_V4L2"
        status = ("ACTIVA" if active else "OFFLINE" if not item.available else
                  "NO COMPROBADA" if network else "DISPONIBLE")
        return {"id":item.source_id,"name":item.display_name,"type":item.source_type.value,
                "available":item.available,"preferred":item.preferred,"active":active,
                "network":network,"status":status,"details":dict(item.details)}

    def _people_payload(self, query):
        if self.people is None:return {"people":(),"total":0}
        text=str(query.get("q",[""])[0])[:100]
        value=self.people.search(PeopleSearchFiltersDTO(text=text,limit=self.people.policy.default_page_size))
        return {"people":[{"token":self._person_token(item.person_id),"name":item.display_name,
                             "first_name":item.first_name,"last_name":item.last_name,
                             "cedula":item.masked_cedula,"phone":item.phone,"email":item.email,
                             "status":item.status,"biometrics":("SIN ROSTRO REGISTRADO" if item.template_count == 0 else f"{item.template_count} TEMPLATES"),"thumbnail":f"/api/thumbnails/{self._person_token(item.person_id)}" if item.thumbnail_available else None}
                            for item in value.people],"total":value.total}

    def _attendance_payload(self):
        values=() if self.attendance is None else self.attendance.day_list().days
        return {"attendance":[{"name":item.display_name,"date":item.local_date.isoformat(),"status":item.status,
                                "check_in":_time(item.check_in),"check_out":_time(item.check_out)} for item in values]}

    def _history_payload(self):
        values=() if self.history is None else self.history.list(limit=100).events
        return {"events":[{"name":item.display_name,"time":item.timestamp.isoformat(),"type":item.event_type,
                            "similarity":item.similarity,"camera":redact_url(item.camera_id) if isinstance(item.camera_id,str) else item.camera_id} for item in values]}

    def _reports_payload(self):
        if self.reports is None:return {"available":False}
        start,end=self.reports.default_dates();value=self.reports.generate("Resumen diario",end,end)
        return {"available":True,"date":str(end),"report":self._plain_dto(value)}

    def _system_payload(self):
        if self.diagnostics_provider is not None:
            try:return self._plain_dto(self.diagnostics_provider())
            except Exception:return {"available":False}
        if self.system_health is None:return {"available":False}
        value=self.system_health.snapshot();return {"available":True,"overall":value.overall_level,
            "components":[{"name":part[0],"level":part[1],"message":part[2],"checked":str(part[3])} for part in value.components]}

    def _audit_payload(self):
        if self.audit is None:return {"available":False}
        value=self.audit.query();return {"available":True,"events":[self._plain_dto(item) for item in value.records]}

    def _backups_payload(self):
        if self.backups is None:return {"available":False}
        return {"available":True,"operations":[self._plain_dto(item) for item in self.backups.history()]}

    def _settings_payload(self):
        if self.configuration is None:return {"available":False}
        value=self.configuration.current().as_mapping()
        return {"available":True,"settings":_redacted_settings(value)}

    @staticmethod
    def _plain_dto(value):
        if dataclasses.is_dataclass(value): return {field.name:WebDashboardController._plain_dto(getattr(value,field.name)) for field in dataclasses.fields(value) if _safe_key(field.name)}
        if isinstance(value,dict): return {str(key):WebDashboardController._plain_dto(item) for key,item in value.items() if _safe_key(str(key))}
        if isinstance(value,(tuple,list)): return [WebDashboardController._plain_dto(item) for item in value]
        return _plain(value)

    def _people_page(self,query)->bytes:
        if self.people is None:return html.page("Personas","<p>Servicio no disponible.</p>")
        text=str(query.get("q",[""])[0])[:100]
        page=self.people.search(PeopleSearchFiltersDTO(text=text,limit=self.people.policy.default_page_size))
        rows=[]
        for item in page.people:
            token=self._person_token(item.person_id)
            biometrics = "SIN ROSTRO REGISTRADO" if item.template_count == 0 else f"{item.template_count} TEMPLATES"
            photo=(f'<img src="/api/thumbnails/{token}" width="44" height="44" alt="Foto">'
                   if item.thumbnail_available else "Sin foto")
            rows.append(f'<tr><td>{photo}</td><td>{html.escape(item.display_name)}</td>'
                        f'<td>{html.escape(item.masked_cedula)}</td><td>{html.escape(str(item.phone or ""))}</td>'
                        f'<td>{html.escape(str(item.email or ""))}</td><td>{html.escape(item.status)}</td>'
                        f'<td>{html.escape(biometrics)}</td><td><button onclick="viewPerson(\'{token}\')">VER</button>'
                        f'<button onclick="editPerson(\'{token}\')">EDITAR</button>'
                        f'<button onclick="updatePhoto(\'{token}\')">ACTUALIZAR FOTO</button>'
                        f'<button onclick="replaceFace(\'{token}\')">ACTUALIZAR ROSTRO</button>'
                        f'<button onclick="deletePerson(\'{token}\')">ELIMINAR</button></td></tr>')
        form=f'<form method="get"><input name="q" maxlength="100" value="{html.escape(text)}"><button>Buscar</button></form>'
        table='<div class="scroll"><table><thead><tr><th>Foto</th><th>Nombre</th><th>Cédula</th><th>Teléfono</th><th>Correo</th><th>Estado</th><th>Biometría</th><th>Acciones</th></tr></thead><tbody>'+''.join(rows)+'</tbody></table></div>'
        script='''<p id="person-message" role="status"></p><script>
let people={},csrf='';async function personApi(path,body){if(!csrf)csrf=(await (await fetch('/api/session')).json()).csrf_token;const r=await fetch(path,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(d.error||'Operación no disponible');return d}async function loadPeople(){const d=await (await fetch('/api/people')).json();people=Object.fromEntries(d.people.map(p=>[p.token,p]))}function viewPerson(token){const p=people[token];if(p)alert(p.name+'\n'+p.cedula+'\n'+p.status+'\n'+p.biometrics)}async function editPerson(token){const p=people[token];if(!p)return;const first_name=prompt('Nombre',p.first_name);if(first_name===null)return;const last_name=prompt('Apellido',p.last_name);if(last_name===null)return;const cedula=prompt('Nueva cédula (dejar vacío para conservar)','');if(cedula===null)return;const phone=prompt('Teléfono',p.phone||'');if(phone===null)return;const email=prompt('Correo',p.email||'');if(email===null)return;const status=prompt('Estado: ACTIVE o INACTIVE',p.status==='DISABLED'?'INACTIVE':p.status);if(status===null)return;await personApi('/api/person/update',{token,first_name,last_name,cedula,phone,email,status});location.reload()}async function updatePhoto(token){await personApi('/api/person/photo',{token,confirmed:true});document.getElementById('person-message').textContent='Captura de fotografía iniciada.'}async function replaceFace(token){if(confirm('¿Reemplazar todos los templates faciales mediante el enrollment existente?'))await personApi('/api/person/face',{token,confirmed:true})}async function deletePerson(token){const p=people[token];if(!p||!confirm('ELIMINAR PERSONA\n\nNombre: '+p.name+'\n\nSe eliminarán fotografía, templates e identidad biométrica. El historial se conservará.'))return;const word=prompt('Escriba ELIMINAR para confirmar');if(word==='ELIMINAR'){await personApi('/api/person/delete',{token,confirmed:true,confirmation:word});location.reload()}}loadPeople();
</script>'''
        return html.page("Personas",form+table+script)

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
def _visual_state(state,evaluated):
    return "IDENTIFICADO" if state == "MATCH" and evaluated else "NO REGISTRADA" if state == "UNKNOWN" and evaluated else "NO EVALUADO"
def _modal_html(value):
    if not value.get("active"):return ""
    photo=(f'<img class="portrait" src="{html.escape(value["photo"])}" alt="Foto">' if value.get("photo") else "")
    details="".join(f'<p><strong>{html.escape(str(item["label"]))}:</strong> {html.escape(str(item["value"]))}</p>' for item in value.get("details",()))
    similarity="" if value.get("similarity") is None else f'<p>Similitud: {float(value["similarity"])*100:.1f} %</p>'
    warning="" if not value.get("warning") else f'<p class="modal-warning">{html.escape(value["warning"])}</p>'
    actions='<button onclick="webEnroll()">REGISTRAR PERSONA</button><button onclick="webIgnore()">IGNORAR</button>' if value.get("kind") in {"UNKNOWN","GALLERY_UNREGISTERED"} else ""
    return (f'<header class="modal-header"><h2>{html.escape(value["title"])}</h2></header>'
            f'<div class="modal-photo">{photo}</div><div class="modal-content">'
            f'<h3>{html.escape(str(value.get("name") or ""))}</h3>{details}{similarity}'
            f'<p class="badge">{html.escape(value["status"])}</p>{warning}'
            f'<small>Se cerrará en 00:{int(value["remaining_seconds"]):02d}</small></div>'
            f'<footer class="modal-actions">{actions}</footer>')
def _modal_shell(presentation):
    hidden="" if presentation else " hidden"
    style='<style>.modal-overlay{position:fixed;inset:0;z-index:1000;background:#020711d9;display:flex;align-items:center;justify-content:center;padding:20px;isolation:isolate}.modal-overlay[hidden]{display:none}.modal-card{position:relative;z-index:1;display:flex;flex-direction:column;width:min(520px,100%);max-height:90vh;overflow:auto;text-align:center;border-color:var(--accent)}.modal-header,.modal-photo,.modal-content,.modal-actions{position:static;flex:0 0 auto}.modal-actions{display:flex;justify-content:center;gap:8px;padding-top:12px}.portrait{width:150px;height:150px;object-fit:cover;border-radius:14px;border:2px solid var(--line)}.modal-warning{color:var(--warn);font-weight:700}</style>'
    return style+f'<div id="modal-overlay" class="modal-overlay"{hidden}><section id="modal" class="modal-card"><div id="presentation-body">{presentation}</div><div id="enrollment-body" hidden></div><p id="enrollment-error" class="modal-warning"></p></section></div>'
def _enrollment_script():
    return r'''let csrf;async function command(path,body={}){if(!csrf)csrf=(await (await fetch('/api/session')).json()).csrf_token;const r=await fetch(path,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify(body)});const d=await r.json();if(!r.ok)throw Error(d.error||'Operación no disponible');return d}
function field(id,label,type='text'){return '<label>'+label+'<input id="'+id+'" type="'+type+'" maxlength="200"></label>'}
async function submitPerson(){try{const ids=['first_name','last_name','cedula','position','department','company','phone','email','address'];const p={consent_confirmed:document.getElementById('consent').checked};ids.forEach(x=>p[x]=document.getElementById(x).value);await command('/api/enrollment/person',p);await enrollmentStatus()}catch(e){document.getElementById('enrollment-error').textContent=e.message}}
async function captureSample(){try{await command('/api/enrollment/capture/start');await enrollmentStatus()}catch(e){document.getElementById('enrollment-error').textContent=e.message}}
async function photo(action){try{await command('/api/enrollment/photo',{action});await enrollmentStatus()}catch(e){document.getElementById('enrollment-error').textContent=e.message}}
async function confirmEnrollment(){await command('/api/enrollment/confirm');await enrollmentStatus()}
async function cancelEnrollment(){await command('/api/enrollment/cancel');const b=document.getElementById('enrollment-body'),p=document.getElementById('presentation-body'),box=document.getElementById('modal-overlay');b.hidden=true;p.hidden=false;box.hidden=!p.innerHTML.trim()}
function renderEnrollment(s){const box=document.getElementById('modal-overlay'),b=document.getElementById('enrollment-body'),p=document.getElementById('presentation-body');if(!s.active){b.hidden=true;if(!p.innerHTML.trim())box.hidden=true;return}box.hidden=false;p.hidden=true;b.hidden=false;const cancel='<button onclick="cancelEnrollment()">CANCELAR</button>',head='<header class="modal-header"><h2>REGISTRO DE PERSONA</h2></header>';let content='',actions=cancel;if(s.stage==='PERSON'){content='<h3>1. DATOS DE PERSONA</h3>'+field('first_name','Nombre')+field('last_name','Apellido')+field('cedula','Cédula')+field('position','Cargo')+field('department','Departamento')+field('company','Empresa')+field('phone','Teléfono')+field('email','Correo','email')+field('address','Dirección')+'<label><input id="consent" type="checkbox"> Consentimiento biométrico confirmado</label>';actions='<button onclick="submitPerson()">SIGUIENTE</button>'+cancel}else if(s.stage==='PREPARATION'){content='<h3>2. PREPARACIÓN</h3><ul><li>Mire al frente</li><li>Buena iluminación</li><li>Mantenga el rostro visible</li><li>Evite cubrir ojos/nariz</li><li>Manténgase a distancia adecuada</li></ul><p>Muestras objetivo: 5</p>';actions='<button onclick="captureSample()">INICIAR CAPTURA</button>'+cancel}else if(s.stage==='CAPTURE'||s.stage==='VALIDATION'){content='<h3>3. CAPTURA FACIAL</h3><img class="video" src="/api/video.mjpeg" alt="Video en vivo"><p class="value">'+s.accepted_samples+' / '+s.target_samples+'</p><p>'+String(s.instruction||'MIRE AL FRENTE')+'</p><p>Score facial: '+(s.quality_score==null?'N/D':Number(s.quality_score).toFixed(1))+' · '+String(s.quality_band||'N/D')+'</p>'+(s.can_continue?'<h3>4. VALIDACIÓN BIOMÉTRICA</h3><p>CAPTURA FACIAL COMPLETADA</p>':'');actions=(s.can_continue?'':'<button onclick="captureSample()">CAPTURAR MUESTRA</button>')+cancel}else if(s.stage==='PHOTO'){content='<h3>5. FOTOGRAFÍA</h3><p>¿Desea guardar una fotografía de perfil?</p>';actions='<button onclick="photo(\'TAKE\')">TOMAR FOTO</button><button onclick="photo(\'SKIP\')">OMITIR</button>'+cancel}else if(s.stage==='CONFIRMATION'){content='<h3>6. CONFIRMACIÓN</h3><pre>'+JSON.stringify(s.summary,null,2)+'</pre><p>Biometría: '+s.accepted_samples+' TEMPLATES</p>';actions='<button onclick="confirmEnrollment()">CONFIRMAR REGISTRO</button>'+cancel}else if(s.stage==='COMPLETE'){content='<h3>PERSONA REGISTRADA CORRECTAMENTE</h3>';actions='<button onclick="location.reload()">FINALIZAR</button>'}b.innerHTML=head+'<div class="modal-photo"></div><div class="modal-content">'+content+'</div><footer class="modal-actions">'+actions+'</footer>'}
async function enrollmentStatus(){try{renderEnrollment(await (await fetch('/api/enrollment/status',{cache:'no-store'})).json())}catch(_){}}
'''
def _time(value):return None if value is None else value.isoformat()
def _safe_key(key):return not any(word in key.lower() for word in ("person_id","embedding","template","password","hash","salt","path"))
def _plain(value):
    if isinstance(value,(str,int,float,bool)) or value is None:return value
    if isinstance(value,datetime):return value.isoformat()
    return len(value) if isinstance(value,(tuple,list)) else str(value)

def _redacted_settings(value):
    """Configuration projection: never send camera credentials or biometric internals."""
    if isinstance(value,dict):
        result={}
        for key,item in value.items():
            lowered=str(key).lower()
            if any(part in lowered for part in ("embedding","template","hash","password","secret","salt")):
                continue
            result[key]=redact_url(str(item)) if key == "url" else _redacted_settings(item)
        return result
    if isinstance(value,list):return [_redacted_settings(item) for item in value]
    return value
