"""Pure validation: it never constructs services or touches databases."""
from __future__ import annotations
import math,re
from pathlib import Path
from typing import Any
from .contracts import *
from src.camera.source_discovery import parse_discovery_config, redact_url

KNOWN_FIELDS={
"camera":{"source","auto_discovery","scan_indices","preferred_source","network_sources"},"queues":{"visual_size","event_size","command_size"},"worker":{"ui_poll_interval_ms","close_timeout_seconds","mock_frame_delay_seconds"},"dashboard":{"initial_width","initial_height","minimum_width","minimum_height","history_limit","event_debounce_seconds","metrics_refresh_ms"},"matcher":{"top_k","automatic_decision_enabled","threshold"},"recognition":{"policy_name","policy_version","automatic_decision_enabled","match_threshold","ambiguity_margin","top_k","minimum_quality_score","allow_low_quality"},"guided_capture":{"target_samples","policy_file","mirrored_source"},"quality":{"profile_file"},"enrollment":{"min_templates","max_templates","allow_low_quality","min_pairwise_similarity","max_pairwise_similarity","reject_exact_duplicates"},"persistence":{"enabled_by_default","load_on_startup","directory"},"thumbnails":{"enabled","directory","width","height","format","jpeg_quality","replace_existing"},"identification_popup":{"enabled","registered_cooldown_seconds","unknown_cooldown_seconds","unknown_popup_timeout_seconds","candidate_stability_frames"},"person_database":{"enabled","path","timeout_seconds"},"event_history":{"enabled","database_path","registered_cooldown_seconds","unregistered_cooldown_seconds","history_limit"},"attendance":{"enabled","database_path","timeout_seconds","automatic_attendance_enabled","automatic_mode","minimum_stable_observations","minimum_observation_seconds","duplicate_event_cooldown_seconds","minimum_time_between_check_in_out_seconds","allow_manual_events","policy_name","policy_version","work_schedule"},"stability":{"enabled","minimum_observations","minimum_duration_seconds","maximum_gap_seconds","minimum_similarity","reset_on_multiple_faces","reset_on_candidate_change","policy_name","policy_version"},"identification_policy":{"enabled","automatic_actions_enabled","require_candidate","require_active_person","require_stable_observation","minimum_quality_score","minimum_similarity","minimum_stability_observations","minimum_stability_duration_seconds","reject_incompatible","reject_ambiguous","policy_name","policy_version"},"decision_orchestrator":{"enabled","automatic_actions_enabled","allow_registered_popup_proposal","allow_unregistered_popup_proposal","allow_detection_event_proposal","allow_attendance_proposal","require_stable_for_registered_popup","require_policy_eligible_for_attendance","require_active_person_for_attendance","policy_name","policy_version"},"action_executor":{"enabled","automatic_execution_enabled","allow_registered_popup","allow_unregistered_popup","allow_detection_event_logging","allow_attendance_execution","require_orchestrator_actions_enabled","policy_name","policy_version"},"application_events":{"enabled","max_diagnostic_events"},"reports":{"enabled","default_range_days","dashboard_refresh_seconds","max_rows","presentation_timezone"},"people_search":{"enabled","default_page_size","allowed_page_sizes","debounce_ms","presentation_timezone"},"security":{"enabled","database_path","bootstrap_admin_enabled","minimum_password_length","maximum_password_length","max_failed_attempts","lockout_seconds","session_idle_timeout_seconds"},"backup":{"enabled","directory","include_configuration","allowed_configuration_files","maximum_archive_size_bytes","maximum_file_count","operation_history_limit","restore_timeout_seconds","sqlite_snapshot_timeout_seconds"},"system_health":{"enabled","dashboard_refresh_seconds","performance_window_seconds","stale_frame_seconds"},"configuration_manager":{"enabled","profile","backup_count","allow_import","allow_export"}}
KNOWN_FIELDS["identification_popup"].add("registered_pause_seconds")
KNOWN_FIELDS["identification_popup"].add("registered_popup_timeout_seconds")
KNOWN_FIELDS["camera"].update({"presentation", "presentation_crop"})
KNOWN_FIELDS["photo_capture"]={"mode","stability_frames","countdown_seconds","minimum_quality_score"}
KNOWN_FIELDS["guided_capture"].add("manual_capture")
KNOWN_FIELDS["guided_capture"].add("minimum_quality_score")
KNOWN_FIELDS["guided_capture"].add("stability_frames")
KNOWN_FIELDS["dashboard"].update({"refresh_seconds","statistics_refresh_seconds"})
KNOWN_FIELDS["security"].add("skip_login_for_local_validation")
KNOWN_FIELDS["security"].add("appliance_mode")
KNOWN_FIELDS["web_dashboard"]={"enabled","host","port","open_browser_on_start","allow_remote_lan","video_max_fps","video_jpeg_quality","max_stream_clients"}
KNOWN_FIELDS["ui"]={"tk_enabled","startup_mode"}
KNOWN_FIELDS["data_namespace"]={"root"}
KNOWN_FIELDS["audit"]={"enabled","database_path","sqlite_timeout_seconds","dashboard_refresh_seconds","default_query_limit","max_query_limit","metadata_max_items","metadata_value_max_length","message_max_length"}
ROOT_FIELDS={"config_schema_version","profile_name","profile_version",*KNOWN_FIELDS}
PATH_FIELDS={("guided_capture","policy_file"),("quality","profile_file"),("persistence","directory"),("thumbnails","directory"),("person_database","path"),("event_history","database_path"),("attendance","database_path"),("security","database_path"),("backup","directory")}
PATH_FIELDS.add(("audit","database_path"))
PATH_FIELDS.add(("data_namespace","root"))
SECRET=re.compile(r"password|secret|token|api_key|credential|private_key",re.I)

class ConfigurationValidator:
 def __init__(self,project_root:Path):self.root=project_root.resolve()
 def validate(self,candidate:object,profile:ConfigurationProfile)->ConfigurationValidationResult:
  issues=[]
  if not isinstance(candidate,dict):return ConfigurationValidationResult(False,(ConfigurationValidationIssue("root",ValidationSeverity.ERROR,"La configuración debe ser un objeto JSON."),))
  severity=ValidationSeverity.WARNING if profile is ConfigurationProfile.PRODUCTION else ValidationSeverity.ERROR
  for key in sorted(set(candidate)-ROOT_FIELDS):issues.append(ConfigurationValidationIssue(key,severity,"Sección desconocida; no será aplicada."))
  version=candidate.get("config_schema_version")
  if version is not None and (isinstance(version,bool) or not isinstance(version,int)):issues.append(ConfigurationValidationIssue("config_schema_version",ValidationSeverity.ERROR,"La versión debe ser un entero."))
  elif isinstance(version,int) and version>1:issues.append(ConfigurationValidationIssue("config_schema_version",ValidationSeverity.ERROR,"La versión futura no es compatible."))
  for section,allowed in KNOWN_FIELDS.items():
   if section not in candidate:continue
   value=candidate[section]
   if not isinstance(value,dict):issues.append(ConfigurationValidationIssue(section,ValidationSeverity.ERROR,"La sección debe ser un objeto."));continue
   for field in sorted(set(value)-allowed):issues.append(ConfigurationValidationIssue(f"{section}.{field}",severity,"Campo desconocido; no será aplicado."))
   for field,item in value.items():
    if field in allowed and _boolean_field(field) and type(item) is not bool:issues.append(ConfigurationValidationIssue(f"{section}.{field}",ValidationSeverity.ERROR,"El valor debe ser booleano."))
  for section,field in PATH_FIELDS:
   value=candidate.get(section,{})
   if isinstance(value,dict) and field in value:
    issue=self._path(value[field],f"{section}.{field}")
    if issue:issues.append(issue)
  backup=candidate.get("backup",{})
  if isinstance(backup,dict):
   for index,value in enumerate(backup.get("allowed_configuration_files",())):
    issue=self._path(value,f"backup.allowed_configuration_files[{index}]")
    if issue:issues.append(issue)
  self._positive_sections(candidate,issues)
  self._data_namespace(candidate,issues)
  if "camera" in candidate and isinstance(candidate.get("camera"),dict):
   try:parse_discovery_config(candidate["camera"])
   except ValueError as exc:issues.append(ConfigurationValidationIssue("camera",ValidationSeverity.ERROR,str(exc)))
  audit=candidate.get("audit",{})
  if isinstance(audit,dict):
   for field in ("sqlite_timeout_seconds","dashboard_refresh_seconds","default_query_limit","max_query_limit","metadata_max_items","metadata_value_max_length","message_max_length"):
    if field in audit and (isinstance(audit[field],bool) or not isinstance(audit[field],(int,float)) or not math.isfinite(float(audit[field])) or audit[field]<=0):issues.append(ConfigurationValidationIssue(f"audit.{field}",ValidationSeverity.ERROR,"El valor debe ser positivo y finito."))
   if isinstance(audit.get("default_query_limit"),int) and isinstance(audit.get("max_query_limit"),int) and audit["default_query_limit"]>audit["max_query_limit"]:issues.append(ConfigurationValidationIssue("audit.default_query_limit",ValidationSeverity.ERROR,"El límite predeterminado no puede superar el máximo."))
  guided=candidate.get("guided_capture",{})
  dashboard=candidate.get("dashboard",{})
  if isinstance(dashboard,dict):
   for field in ("refresh_seconds","statistics_refresh_seconds"):
    value=dashboard.get(field)
    if value is not None and (isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(float(value)) or value<=0):issues.append(ConfigurationValidationIssue(f"dashboard.{field}",ValidationSeverity.ERROR,"El intervalo debe ser positivo y finito."))
   operational=dashboard.get("refresh_seconds");statistics=dashboard.get("statistics_refresh_seconds")
   if isinstance(operational,(int,float)) and not isinstance(operational,bool) and isinstance(statistics,(int,float)) and not isinstance(statistics,bool) and statistics<operational:issues.append(ConfigurationValidationIssue("dashboard.statistics_refresh_seconds",ValidationSeverity.ERROR,"Las estadísticas no pueden refrescarse más rápido que el dashboard."))
  web=candidate.get("web_dashboard",{})
  if isinstance(web,dict):
   host=web.get("host")
   if host is not None:
    try:_validate_web_host(host)
    except ValueError as exc:issues.append(ConfigurationValidationIssue("web_dashboard.host",ValidationSeverity.ERROR,str(exc)))
   port=web.get("port")
   if port is not None and (isinstance(port,bool) or not isinstance(port,int) or not 1<=port<=65535):issues.append(ConfigurationValidationIssue("web_dashboard.port",ValidationSeverity.ERROR,"El puerto debe ser un entero entre 1 y 65535."))
   fps=web.get("video_max_fps")
   if fps is not None and (isinstance(fps,bool) or not isinstance(fps,(int,float)) or not math.isfinite(float(fps)) or not 0<float(fps)<=30):issues.append(ConfigurationValidationIssue("web_dashboard.video_max_fps",ValidationSeverity.ERROR,"La frecuencia MJPEG debe estar entre 0 y 30 FPS."))
   quality=web.get("video_jpeg_quality")
   if quality is not None and (isinstance(quality,bool) or not isinstance(quality,int) or not 1<=quality<=100):issues.append(ConfigurationValidationIssue("web_dashboard.video_jpeg_quality",ValidationSeverity.ERROR,"La calidad JPEG debe estar entre 1 y 100."))
   clients=web.get("max_stream_clients")
   if clients is not None and (isinstance(clients,bool) or not isinstance(clients,int) or not 1<=clients<=10):issues.append(ConfigurationValidationIssue("web_dashboard.max_stream_clients",ValidationSeverity.ERROR,"Los clientes MJPEG deben estar entre 1 y 10."))
   if web.get("enabled",False) and host not in (None,"localhost","127.0.0.1","::1") and not web.get("allow_remote_lan",False):issues.append(ConfigurationValidationIssue("web_dashboard.allow_remote_lan",ValidationSeverity.ERROR,"Un host de red requiere allow_remote_lan=true."))
  ui=candidate.get("ui",{})
  if isinstance(ui,dict) and "startup_mode" in ui and ui["startup_mode"] not in {"ASK","TK","WEB","BOTH"}:issues.append(ConfigurationValidationIssue("ui.startup_mode",ValidationSeverity.ERROR,"El modo debe ser ASK, TK, WEB o BOTH."))
  popup=candidate.get("identification_popup",{})
  if isinstance(popup,dict):
   timeout=popup.get("registered_popup_timeout_seconds")
   if timeout is not None and (isinstance(timeout,bool) or not isinstance(timeout,(int,float)) or not math.isfinite(float(timeout)) or timeout<=0):issues.append(ConfigurationValidationIssue("identification_popup.registered_popup_timeout_seconds",ValidationSeverity.ERROR,"El timeout debe ser positivo y finito."))
  if isinstance(ui,dict) and ui.get("tk_enabled") is False and not (isinstance(web,dict) and web.get("enabled") is True):issues.append(ConfigurationValidationIssue("ui.tk_enabled",ValidationSeverity.ERROR,"El modo experimental sin Tk requiere web_dashboard.enabled=true."))
  if isinstance(guided,dict) and "minimum_quality_score" in guided:
   minimum=guided["minimum_quality_score"]
   if isinstance(minimum,bool) or not isinstance(minimum,(int,float)) or not math.isfinite(float(minimum)) or not 0<=float(minimum)<=100:issues.append(ConfigurationValidationIssue("guided_capture.minimum_quality_score",ValidationSeverity.ERROR,"El umbral debe estar entre 0 y 100."))
  photo=candidate.get("photo_capture",{})
  if isinstance(photo,dict):
   minimum=photo.get("minimum_quality_score")
   if minimum is not None and (isinstance(minimum,bool) or not isinstance(minimum,(int,float)) or not math.isfinite(float(minimum)) or not 0<=float(minimum)<=100):issues.append(ConfigurationValidationIssue("photo_capture.minimum_quality_score",ValidationSeverity.ERROR,"El umbral debe estar entre 0 y 100."))
   stability=photo.get("stability_frames")
   if stability is not None and (isinstance(stability,bool) or not isinstance(stability,int) or stability<=0):issues.append(ConfigurationValidationIssue("photo_capture.stability_frames",ValidationSeverity.ERROR,"La estabilidad debe ser un entero positivo."))
  attendance=candidate.get("attendance",{})
  if isinstance(attendance,dict):
   schedule=attendance.get("work_schedule")
   automatic=attendance.get("automatic_attendance_enabled",False)
   if profile is ConfigurationProfile.PRODUCTION and automatic and not isinstance(schedule,dict):issues.append(ConfigurationValidationIssue("attendance.work_schedule",ValidationSeverity.ERROR,"Producción requiere un horario laboral explícito para asistencia automática."))
   if schedule is not None:
    required={"timezone","workday_start","workday_end","late_after","overtime_after"}
    if not isinstance(schedule,dict):issues.append(ConfigurationValidationIssue("attendance.work_schedule",ValidationSeverity.ERROR,"El horario laboral debe ser un objeto."))
    elif set(schedule)!=required:issues.append(ConfigurationValidationIssue("attendance.work_schedule",ValidationSeverity.ERROR,"El horario laboral debe declarar timezone y todos los horarios."))
    else:
     try:
      from src.core.attendance import AttendancePolicy
      AttendancePolicy(enabled=True,automatic_attendance_enabled=bool(automatic),automatic_mode=str(attendance.get("automatic_mode","TOGGLE_DAILY")),timezone=str(schedule["timezone"]),workday_start=str(schedule["workday_start"]),workday_end=str(schedule["workday_end"]),late_after=str(schedule["late_after"]),overtime_after=str(schedule["overtime_after"]))
     except Exception as exc:issues.append(ConfigurationValidationIssue("attendance.work_schedule",ValidationSeverity.ERROR,str(exc)))
  issues.sort(key=lambda i:(i.path,i.severity.value,i.message))
  return ConfigurationValidationResult(not any(i.severity is ValidationSeverity.ERROR for i in issues),tuple(issues))
 def _path(self,value,path):
  if not isinstance(value,str) or not value.strip():return ConfigurationValidationIssue(path,ValidationSeverity.ERROR,"La ruta relativa es inválida.")
  configured=Path(value)
  if configured.is_absolute() or ".." in configured.parts:return ConfigurationValidationIssue(path,ValidationSeverity.ERROR,"La ruta debe permanecer dentro del proyecto.")
  resolved=(self.root/configured).resolve(strict=False)
  if resolved!=self.root and self.root not in resolved.parents:return ConfigurationValidationIssue(path,ValidationSeverity.ERROR,"La ruta escapa del proyecto.")
  return None
 def _positive_sections(self,candidate,issues):
  checks={"queues":("visual_size","event_size","command_size"),"worker":("ui_poll_interval_ms","close_timeout_seconds"),"guided_capture":("target_samples","stability_frames"),"system_health":("dashboard_refresh_seconds","performance_window_seconds","stale_frame_seconds"),"configuration_manager":("backup_count",),"backup":("maximum_archive_size_bytes","maximum_file_count","operation_history_limit","restore_timeout_seconds","sqlite_snapshot_timeout_seconds")}
  for section,fields in checks.items():
   values=candidate.get(section,{})
   if not isinstance(values,dict):continue
   for field in fields:
    if field in values and (isinstance(values[field],bool) or not isinstance(values[field],(int,float)) or not math.isfinite(float(values[field])) or values[field]<=0):issues.append(ConfigurationValidationIssue(f"{section}.{field}",ValidationSeverity.ERROR,"El valor debe ser positivo y finito."))

 def _data_namespace(self,candidate,issues):
  message="La base de personas, la galería biométrica y los thumbnails deben pertenecer al mismo namespace de datos."
  values=(
   candidate.get("person_database",{}).get("path") if isinstance(candidate.get("person_database",{}),dict) else None,
   candidate.get("persistence",{}).get("directory") if isinstance(candidate.get("persistence",{}),dict) else None,
   candidate.get("thumbnails",{}).get("directory") if isinstance(candidate.get("thumbnails",{}),dict) else None,
  )
  if any(value is None for value in values):return
  inferred=[]
  for index,value in enumerate(values):
   if not isinstance(value,str):return
   path=Path(value);parts=path.parts
   if len(parts)>=2 and parts[0]=="data":inferred.append(Path(*parts[:2]))
   elif index==0:inferred.append(path.parent)
   elif path.name in {"gallery","thumbnails"}:inferred.append(path.parent)
   else:inferred.append(path)
  namespace=candidate.get("data_namespace",{})
  explicit=namespace.get("root") if isinstance(namespace,dict) else None
  if len(set(inferred))!=1 or (explicit is not None and Path(str(explicit))!=inferred[0]):
   issues.append(ConfigurationValidationIssue("data_namespace",ValidationSeverity.ERROR,message))

def redact(value:Any,key:str="")->Any:
 if SECRET.search(key):return "[REDACTED]"
 if isinstance(value,dict):return {str(k):redact(v,str(k)) for k,v in value.items()}
 if isinstance(value,(list,tuple)):return [redact(v,key) for v in value]
 if isinstance(value,str) and value.lower().startswith(("rtsp://","http://","https://")):return redact_url(value)
 return value

def known_only(value:dict[str,Any])->dict[str,Any]:
 result={}
 for key,item in value.items():
  if key not in ROOT_FIELDS:continue
  if key in KNOWN_FIELDS and isinstance(item,dict):result[key]={field:field_value for field,field_value in item.items() if field in KNOWN_FIELDS[key]}
  else:result[key]=item
 return result

def _boolean_field(field:str)->bool:
 return field in {"appliance_mode","open_browser_on_start"} or field=="enabled" or field.endswith("_enabled") or field.startswith(("allow_","require_","reject_","reset_","load_","include_","mirrored_","replace_","continue_","fail","skip_"))

def _validate_web_host(value:object)->None:
 import ipaddress
 if not isinstance(value,str) or not value or value.strip()!=value or len(value)>253 or any(ord(character)<33 for character in value):raise ValueError("El host web es inválido.")
 if value=="localhost":return
 try:ipaddress.ip_address(value);return
 except ValueError:pass
 if not re.fullmatch(r"(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))*",value):raise ValueError("El host web es inválido.")
