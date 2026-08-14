"""Pure validation: it never constructs services or touches databases."""
from __future__ import annotations
import math,re
from pathlib import Path
from typing import Any
from .contracts import *

KNOWN_FIELDS={
"camera":{"source"},"queues":{"visual_size","event_size","command_size"},"worker":{"ui_poll_interval_ms","close_timeout_seconds","mock_frame_delay_seconds"},"dashboard":{"initial_width","initial_height","minimum_width","minimum_height","history_limit","event_debounce_seconds","metrics_refresh_ms"},"matcher":{"top_k","automatic_decision_enabled","threshold"},"recognition":{"policy_name","policy_version","automatic_decision_enabled","match_threshold","ambiguity_margin","top_k","minimum_quality_score","allow_low_quality"},"guided_capture":{"target_samples","policy_file","mirrored_source"},"quality":{"profile_file"},"enrollment":{"min_templates","max_templates","allow_low_quality","min_pairwise_similarity","max_pairwise_similarity","reject_exact_duplicates"},"persistence":{"enabled_by_default","load_on_startup","directory"},"thumbnails":{"enabled","directory","width","height","format","jpeg_quality","replace_existing"},"identification_popup":{"enabled","registered_cooldown_seconds","unknown_cooldown_seconds","unknown_popup_timeout_seconds","candidate_stability_frames"},"person_database":{"enabled","path","timeout_seconds"},"event_history":{"enabled","database_path","registered_cooldown_seconds","unregistered_cooldown_seconds","history_limit"},"attendance":{"enabled","database_path","timeout_seconds","automatic_attendance_enabled","minimum_stable_observations","minimum_observation_seconds","duplicate_event_cooldown_seconds","minimum_time_between_check_in_out_seconds","allow_manual_events","policy_name","policy_version"},"stability":{"enabled","minimum_observations","minimum_duration_seconds","maximum_gap_seconds","minimum_similarity","reset_on_multiple_faces","reset_on_candidate_change","policy_name","policy_version"},"identification_policy":{"enabled","automatic_actions_enabled","require_candidate","require_active_person","require_stable_observation","minimum_quality_score","minimum_similarity","minimum_stability_observations","minimum_stability_duration_seconds","reject_incompatible","reject_ambiguous","policy_name","policy_version"},"decision_orchestrator":{"enabled","automatic_actions_enabled","allow_registered_popup_proposal","allow_unregistered_popup_proposal","allow_detection_event_proposal","allow_attendance_proposal","require_stable_for_registered_popup","require_policy_eligible_for_attendance","require_active_person_for_attendance","policy_name","policy_version"},"action_executor":{"enabled","automatic_execution_enabled","allow_registered_popup","allow_unregistered_popup","allow_detection_event_logging","allow_attendance_execution","require_orchestrator_actions_enabled","policy_name","policy_version"},"application_events":{"enabled","max_diagnostic_events"},"reports":{"enabled","default_range_days","dashboard_refresh_seconds","max_rows","presentation_timezone"},"people_search":{"enabled","default_page_size","allowed_page_sizes","debounce_ms","presentation_timezone"},"security":{"enabled","database_path","bootstrap_admin_enabled","minimum_password_length","maximum_password_length","max_failed_attempts","lockout_seconds","session_idle_timeout_seconds"},"backup":{"enabled","directory","include_configuration","allowed_configuration_files","maximum_archive_size_bytes","maximum_file_count","operation_history_limit","restore_timeout_seconds","sqlite_snapshot_timeout_seconds"},"system_health":{"enabled","dashboard_refresh_seconds","performance_window_seconds","stale_frame_seconds"},"configuration_manager":{"enabled","profile","backup_count","allow_import","allow_export"}}
KNOWN_FIELDS["identification_popup"].add("registered_pause_seconds")
KNOWN_FIELDS["security"].add("skip_login_for_local_validation")
KNOWN_FIELDS["audit"]={"enabled","database_path","sqlite_timeout_seconds","dashboard_refresh_seconds","default_query_limit","max_query_limit","metadata_max_items","metadata_value_max_length","message_max_length"}
ROOT_FIELDS={"config_schema_version","profile_name","profile_version",*KNOWN_FIELDS}
PATH_FIELDS={("guided_capture","policy_file"),("quality","profile_file"),("persistence","directory"),("thumbnails","directory"),("person_database","path"),("event_history","database_path"),("attendance","database_path"),("security","database_path"),("backup","directory")}
PATH_FIELDS.add(("audit","database_path"))
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
  audit=candidate.get("audit",{})
  if isinstance(audit,dict):
   for field in ("sqlite_timeout_seconds","dashboard_refresh_seconds","default_query_limit","max_query_limit","metadata_max_items","metadata_value_max_length","message_max_length"):
    if field in audit and (isinstance(audit[field],bool) or not isinstance(audit[field],(int,float)) or not math.isfinite(float(audit[field])) or audit[field]<=0):issues.append(ConfigurationValidationIssue(f"audit.{field}",ValidationSeverity.ERROR,"El valor debe ser positivo y finito."))
   if isinstance(audit.get("default_query_limit"),int) and isinstance(audit.get("max_query_limit"),int) and audit["default_query_limit"]>audit["max_query_limit"]:issues.append(ConfigurationValidationIssue("audit.default_query_limit",ValidationSeverity.ERROR,"El límite predeterminado no puede superar el máximo."))
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
  checks={"queues":("visual_size","event_size","command_size"),"worker":("ui_poll_interval_ms","close_timeout_seconds"),"system_health":("dashboard_refresh_seconds","performance_window_seconds","stale_frame_seconds"),"configuration_manager":("backup_count",),"backup":("maximum_archive_size_bytes","maximum_file_count","operation_history_limit","restore_timeout_seconds","sqlite_snapshot_timeout_seconds")}
  for section,fields in checks.items():
   values=candidate.get(section,{})
   if not isinstance(values,dict):continue
   for field in fields:
    if field in values and (isinstance(values[field],bool) or not isinstance(values[field],(int,float)) or not math.isfinite(float(values[field])) or values[field]<=0):issues.append(ConfigurationValidationIssue(f"{section}.{field}",ValidationSeverity.ERROR,"El valor debe ser positivo y finito."))

def redact(value:Any,key:str="")->Any:
 if SECRET.search(key):return "[REDACTED]"
 if isinstance(value,dict):return {str(k):redact(v,str(k)) for k,v in value.items()}
 if isinstance(value,(list,tuple)):return [redact(v,key) for v in value]
 return value

def known_only(value:dict[str,Any])->dict[str,Any]:
 result={}
 for key,item in value.items():
  if key not in ROOT_FIELDS:continue
  if key in KNOWN_FIELDS and isinstance(item,dict):result[key]={field:field_value for field,field_value in item.items() if field in KNOWN_FIELDS[key]}
  else:result[key]=item
 return result

def _boolean_field(field:str)->bool:
 return field=="enabled" or field.endswith("_enabled") or field.startswith(("allow_","require_","reject_","reset_","load_","include_","mirrored_","replace_","continue_","fail","skip_"))
