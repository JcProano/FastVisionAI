import json
from pathlib import Path
from src.core.security import AuthorizationPermission
class ConfigurationController:
 def __init__(self,service,authorization=None,*,security_disabled=False,allow_import=True,allow_export=True):self.service=service;self.authorization=authorization;self.security_disabled=security_disabled;self.allow_import=allow_import;self.allow_export=allow_export
 def _require(self,permission):
  if self.security_disabled:return
  if self.authorization is None or not self.authorization.require(permission).allowed:raise PermissionError("operation is not authorized")
 def current(self):self._require(AuthorizationPermission.VIEW_SETTINGS);return self.service.current()
 def validate_text(self,text):self._require(AuthorizationPermission.VIEW_SETTINGS);return self.service.validate_candidate(json.loads(text))
 def diff_text(self,text):self._require(AuthorizationPermission.VIEW_SETTINGS);return self.service.diff(json.loads(text))
 def reload(self):self._require(AuthorizationPermission.VIEW_SETTINGS);return self.service.reload()
 def save_text(self,text):self._require(AuthorizationPermission.EDIT_SETTINGS);return self.service.save(json.loads(text))
 def import_file(self,path:Path):
  self._require(AuthorizationPermission.EDIT_SETTINGS)
  if not self.allow_import:raise PermissionError("configuration import is disabled")
  return self.service.import_candidate(path)
 def export_file(self,path:Path,overwrite=False):
  self._require(AuthorizationPermission.VIEW_SETTINGS)
  if not self.allow_export:raise PermissionError("configuration export is disabled")
  return self.service.export(path,overwrite=overwrite)
 def can_edit(self):
  try:self._require(AuthorizationPermission.EDIT_SETTINGS);return True
  except PermissionError:return False
