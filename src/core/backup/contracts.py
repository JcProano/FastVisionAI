"""Immutable and payload-safe contracts for backup and restore."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

BACKUP_FORMAT_VERSION = 1

class BackupError(RuntimeError): pass
class BackupValidationError(BackupError): pass
class BackupIntegrityError(BackupError): pass
class BackupSpaceError(BackupError): pass
class RestoreError(BackupError): pass
class RestoreRollbackError(RestoreError): pass

class BackupComponentType(str,Enum):
 PEOPLE_DATABASE="PEOPLE_DATABASE"; DETECTION_EVENTS_DATABASE="DETECTION_EVENTS_DATABASE"
 ATTENDANCE_DATABASE="ATTENDANCE_DATABASE"; USERS_DATABASE="USERS_DATABASE"
 AUDIT_DATABASE="AUDIT_DATABASE"
 GALLERY_MANIFEST="GALLERY_MANIFEST"; GALLERY_ARCHIVE="GALLERY_ARCHIVE"
 THUMBNAIL="THUMBNAIL"; CONFIGURATION="CONFIGURATION"

class MaintenanceState(str,Enum):
 RUNNING="RUNNING"; BACKUP_IN_PROGRESS="BACKUP_IN_PROGRESS"; QUIESCING="QUIESCING"
 QUIESCENT="QUIESCENT"; RESTORING="RESTORING"; FAILED="FAILED"

@dataclass(frozen=True,slots=True)
class BackupFileEntry:
 logical_path:str; archive_path:str; component_type:BackupComponentType; size:int; sha256:str
 schema_version:int|None=None; snapshot_at:datetime|None=None

@dataclass(frozen=True,slots=True)
class BackupManifest:
 format_version:int; created_at:datetime; application:str; application_version:str
 backup_id:str; encryption:str; files:tuple[BackupFileEntry,...]; missing_components:tuple[str,...]

@dataclass(frozen=True,slots=True)
class BackupRequest:
 destination:Path; overwrite:bool=False

@dataclass(frozen=True,slots=True)
class BackupResult:
 success:bool; backup_id:str|None; filename:str|None; files_count:int; total_size:int
 missing_components:tuple[str,...]; message:str; encryption:str="NONE"

@dataclass(frozen=True,slots=True)
class BackupVerificationResult:
 valid:bool; backup_id:str|None; files_count:int; total_size:int; message:str
 encryption:str="NONE"

@dataclass(frozen=True,slots=True)
class RestorePlan:
 backup_id:str; archive_path:Path; staging_directory:Path
 files:tuple[BackupFileEntry,...]; total_size:int; requires_restart:bool=True

@dataclass(frozen=True,slots=True)
class RestoreResult:
 success:bool; backup_id:str|None; files_restored:int; rollback_performed:bool
 restart_required:bool; message:str

@dataclass(frozen=True,slots=True)
class BackupOperationRecord:
 operation:str; success:bool; timestamp:datetime; message:str
