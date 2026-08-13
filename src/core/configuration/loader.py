from __future__ import annotations
import json
from pathlib import Path
from .contracts import *
from .validators import ConfigurationValidator,known_only
class ConfigurationLoader:
 def __init__(self,validator:ConfigurationValidator):self.validator=validator
 def load(self,path:Path,profile:ConfigurationProfile)->ConfigurationSnapshot:
  try:value=json.loads(path.read_text(encoding="utf-8"))
  except (OSError,json.JSONDecodeError) as exc:raise ConfigurationError("La configuración no pudo cargarse.") from exc
  validation=self.validator.validate(value,profile)
  if not validation.valid:raise ConfigurationError("La configuración no superó la validación.")
  version=value.get("config_schema_version")
  return ConfigurationSnapshot(profile,version,version is None,freeze(known_only(value)),path.name,True)
 def from_candidate(self,candidate:dict,profile:ConfigurationProfile,source_name="candidate.json"):
  validation=self.validator.validate(candidate,profile)
  if not validation.valid:raise ConfigurationError("La configuración candidata no es válida.")
  version=candidate.get("config_schema_version");return ConfigurationSnapshot(profile,version,version is None,freeze(known_only(candidate)),source_name,True)
