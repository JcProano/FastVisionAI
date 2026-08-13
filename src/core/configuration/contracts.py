"""Immutable, redacted public configuration contracts."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any,Mapping

class ConfigurationError(RuntimeError):pass
class ConfigurationProfile(str,Enum):DEVELOPMENT="DEVELOPMENT";PRODUCTION="PRODUCTION";TESTING="TESTING"
class ConfigurationImpact(str,Enum):HOT_RELOADABLE="HOT_RELOADABLE";RESTART_REQUIRED="RESTART_REQUIRED";IMMUTABLE_AT_RUNTIME="IMMUTABLE_AT_RUNTIME"
class ValidationSeverity(str,Enum):ERROR="ERROR";WARNING="WARNING"
@dataclass(frozen=True,slots=True)
class ConfigurationValidationIssue:path:str;severity:ValidationSeverity;message:str
@dataclass(frozen=True,slots=True)
class ConfigurationValidationResult:
 valid:bool;issues:tuple[ConfigurationValidationIssue,...]
 @property
 def errors(self):return tuple(i for i in self.issues if i.severity is ValidationSeverity.ERROR)
 @property
 def warnings(self):return tuple(i for i in self.issues if i.severity is ValidationSeverity.WARNING)
@dataclass(frozen=True,slots=True)
class ConfigurationSectionDTO:name:str;values:Mapping[str,Any]
@dataclass(frozen=True,slots=True)
class ConfigurationSnapshot:
 profile:ConfigurationProfile;schema_version:int|None;legacy_configuration:bool
 sections:Mapping[str,Any];source_name:str;valid:bool=True
 def as_mapping(self)->dict[str,Any]:return thaw(self.sections)
@dataclass(frozen=True,slots=True)
class ConfigurationChangeDTO:section:str;field:str;old_value:Any;new_value:Any;impact:ConfigurationImpact
@dataclass(frozen=True,slots=True)
class ConfigurationDiffDTO:
 changes:tuple[ConfigurationChangeDTO,...]
 @property
 def hot_reloadable(self):return tuple(x for x in self.changes if x.impact is ConfigurationImpact.HOT_RELOADABLE)
 @property
 def restart_required(self):return tuple(x for x in self.changes if x.impact is ConfigurationImpact.RESTART_REQUIRED)
 @property
 def immutable(self):return tuple(x for x in self.changes if x.impact is ConfigurationImpact.IMMUTABLE_AT_RUNTIME)
@dataclass(frozen=True,slots=True)
class ConfigurationOperationResult:
 success:bool;message:str;validation:ConfigurationValidationResult|None=None
 diff:ConfigurationDiffDTO|None=None;warning:str|None=None

def freeze(value:Any)->Any:
 if isinstance(value,dict):return MappingProxyType({str(k):freeze(v) for k,v in value.items()})
 if isinstance(value,list):return tuple(freeze(v) for v in value)
 if isinstance(value,tuple):return tuple(freeze(v) for v in value)
 return value
def thaw(value:Any)->Any:
 if isinstance(value,Mapping):return {str(k):thaw(v) for k,v in value.items()}
 if isinstance(value,tuple):return [thaw(v) for v in value]
 return value
