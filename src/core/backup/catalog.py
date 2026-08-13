"""Allowlisted mapping between configuration and backup components."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from .contracts import BackupComponentType,BackupValidationError

@dataclass(frozen=True,slots=True)
class BackupSource:
 logical_path:str; source_path:Path; archive_path:str; component_type:BackupComponentType
 is_sqlite:bool=False

class BackupSourceCatalog:
 def __init__(self,project_root:Path,settings:dict[str,object]):
  self.root=project_root.resolve();self.settings=settings
 def resolve_relative(self,value:object)->Path:
  configured=Path(str(value))
  if configured.is_absolute() or ".." in configured.parts:raise BackupValidationError("configured path is unsafe")
  result=(self.root/configured).resolve(strict=False)
  if result!=self.root and self.root not in result.parents:raise BackupValidationError("configured path escapes project root")
  return result
 def sources(self)->tuple[BackupSource,...]:
  result=[]
  mapping=(("person_database","path","data/fastvision/people.db",BackupComponentType.PEOPLE_DATABASE,"people.db"),("event_history","database_path","data/fastvision/events.db",BackupComponentType.DETECTION_EVENTS_DATABASE,"events.db"),("attendance","database_path","data/fastvision/attendance.db",BackupComponentType.ATTENDANCE_DATABASE,"attendance.db"),("security","database_path","data/fastvision/users.db",BackupComponentType.USERS_DATABASE,"users.db"),("audit","database_path","data/fastvision/audit.db",BackupComponentType.AUDIT_DATABASE,"audit.db"))
  for section,key,default,kind,name in mapping:
   config=self.settings.get(section,{})
   if not isinstance(config,dict):raise BackupValidationError(f"{section} configuration is invalid")
   path=self.resolve_relative(config.get(key,default));result.append(BackupSource(str(path.relative_to(self.root)),path,f"components/databases/{name}",kind,True))
  persistence=self.settings.get("persistence",{})
  if not isinstance(persistence,dict):raise BackupValidationError("persistence configuration is invalid")
  directory=self.resolve_relative(persistence.get("directory","data/ui_validation"))
  result.extend((BackupSource(str((directory/"gallery.json").relative_to(self.root)),directory/"gallery.json","components/gallery/gallery.json",BackupComponentType.GALLERY_MANIFEST),BackupSource(str((directory/"gallery.npz").relative_to(self.root)),directory/"gallery.npz","components/gallery/gallery.npz",BackupComponentType.GALLERY_ARCHIVE)))
  backup=self.settings.get("backup",{})
  if not isinstance(backup,dict):raise BackupValidationError("backup configuration is invalid")
  if bool(backup.get("include_configuration",True)):
   for item in backup.get("allowed_configuration_files",("config/local_face_validation.dev.json",)):
    path=self.resolve_relative(item);result.append(BackupSource(str(path.relative_to(self.root)),path,f"components/config/{path.name}",BackupComponentType.CONFIGURATION))
  return tuple(result)
 def thumbnail_directory(self)->Path:
  config=self.settings.get("thumbnails",{})
  if not isinstance(config,dict):raise BackupValidationError("thumbnail configuration is invalid")
  return self.resolve_relative(config.get("directory","data/ui_validation/thumbnails"))
 def destination_for(self,entry)->Path:
  allowed={(source.logical_path,source.component_type) for source in self.sources()}
  if entry.component_type is BackupComponentType.THUMBNAIL:
   destination=self.resolve_relative(entry.logical_path);directory=self.thumbnail_directory()
   if destination.parent!=directory or destination.suffix.casefold() not in {".jpg",".jpeg",".png"}:raise BackupValidationError("thumbnail restore destination is not allowlisted")
   return destination
  if (entry.logical_path,entry.component_type) not in allowed:raise BackupValidationError("restore destination is not allowlisted")
  return self.resolve_relative(entry.logical_path)
