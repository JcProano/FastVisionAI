"""Fully validated, staged and compensable restore workflow."""
from __future__ import annotations
import json,os,shutil,tempfile
from pathlib import Path
from src.engine.gallery import FaceGallery
from src.engine.gallery.persistence import GalleryPersistence
from .archive import BackupArchive,sha256_file
from .catalog import BackupSourceCatalog
from .contracts import *
from .maintenance import ApplicationMaintenanceCoordinator
from .sqlite_snapshot import SQLiteSnapshotProvider

class RestoreService:
 def __init__(self,catalog:BackupSourceCatalog,archive:BackupArchive,snapshots:SQLiteSnapshotProvider,maintenance:ApplicationMaintenanceCoordinator,*,disk_usage=shutil.disk_usage,audit_callback=None):self.catalog=catalog;self.archive=archive;self.snapshots=snapshots;self.maintenance=maintenance;self.disk_usage=disk_usage;self.audit=audit_callback
 def prepare(self,archive_path:Path)->RestorePlan:
  staging=Path(tempfile.mkdtemp(prefix="fastvision-restore-"))
  try:
   if self.disk_usage(staging).free<archive_path.stat().st_size*2+1_048_576:raise BackupSpaceError("insufficient space to prepare restore")
   manifest,extracted=self.archive.verify(archive_path,staging)
   for entry in manifest.files:
    self.catalog.destination_for(entry)
    path=extracted[entry.archive_path]
    if entry.component_type.value.endswith("DATABASE"):
     if entry.schema_version is None:raise BackupValidationError("SQLite schema metadata is missing")
     if entry.schema_version>1:raise BackupValidationError("future SQLite schema is unsupported")
     if self.snapshots.validate(path,1)!=entry.schema_version:raise BackupValidationError("SQLite schema metadata mismatch")
    elif entry.component_type is BackupComponentType.CONFIGURATION:
     root=json.loads(path.read_text(encoding="utf-8"))
     if not isinstance(root,dict):raise BackupValidationError("restored configuration is invalid")
   galleries={e.component_type:e for e in manifest.files if e.component_type in {BackupComponentType.GALLERY_MANIFEST,BackupComponentType.GALLERY_ARCHIVE}}
   if len(galleries)==1:raise BackupValidationError("restored gallery pair is incomplete")
   if len(galleries)==2:
    GalleryPersistence(enabled=True).import_into(FaceGallery(),extracted[galleries[BackupComponentType.GALLERY_MANIFEST].archive_path],extracted[galleries[BackupComponentType.GALLERY_ARCHIVE].archive_path])
   return RestorePlan(manifest.backup_id,archive_path,staging,manifest.files,sum(e.size for e in manifest.files),True)
  except Exception:shutil.rmtree(staging,ignore_errors=True);raise
 def restore(self,plan:RestorePlan,*,confirmed:bool)->RestoreResult:
  if not confirmed:return RestoreResult(False,plan.backup_id,0,False,False,"Restauración cancelada.")
  self._audit("RESTORE_STARTED")
  rollback=Path(tempfile.mkdtemp(prefix="fastvision-rollback-",dir=self.catalog.root));moved=[];installed=[]
  try:
   if self.maintenance.state is not MaintenanceState.QUIESCENT:raise RestoreError("restore requires application quiescence")
   if self.disk_usage(self.catalog.root).free<plan.total_size*2+1_048_576:raise BackupSpaceError("insufficient space to commit restore")
   self.maintenance.begin_restore()
   for entry in plan.files:
    source=plan.staging_directory/entry.archive_path;destination=self.catalog.destination_for(entry);destination.parent.mkdir(parents=True,exist_ok=True)
    previous=rollback/entry.logical_path;previous.parent.mkdir(parents=True,exist_ok=True)
    if destination.exists():os.replace(destination,previous);moved.append((previous,destination,sha256_file(previous)))
    os.replace(source,destination);installed.append(destination)
   self.maintenance.complete_restore();shutil.rmtree(rollback,ignore_errors=True);shutil.rmtree(plan.staging_directory,ignore_errors=True);self._audit("RESTORE_SUCCESS")
   return RestoreResult(True,plan.backup_id,len(installed),False,True,"Restauración completada; reinicio y nuevo login obligatorios.")
  except Exception as original:
   rollback_ok=True
   for destination in reversed(installed):
    try:destination.unlink(missing_ok=True)
    except Exception:rollback_ok=False
   for previous,destination,digest in reversed(moved):
    try:
     destination.parent.mkdir(parents=True,exist_ok=True);os.replace(previous,destination)
     if sha256_file(destination)!=digest:rollback_ok=False
    except Exception:rollback_ok=False
   shutil.rmtree(plan.staging_directory,ignore_errors=True);self._audit("RESTORE_FAILED")
   if not rollback_ok:
    self.maintenance.fail();raise RestoreRollbackError("restore rollback could not be verified; manual recovery is required") from original
   shutil.rmtree(rollback,ignore_errors=True)
   self.maintenance.fail();raise RestoreError("restore failed and original files were restored") from original
 def _audit(self,event):
  if self.audit:
   try:self.audit(event,{})
   except Exception:pass
