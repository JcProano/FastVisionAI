"""Consistent backup creation and complete package verification."""
from __future__ import annotations
import json,shutil,tempfile,uuid
from datetime import datetime,timezone
from pathlib import Path
from .archive import BackupArchive,sha256_file
from .catalog import BackupSourceCatalog
from .contracts import *
from .maintenance import ApplicationMaintenanceCoordinator
from .sqlite_snapshot import SQLiteSnapshotProvider
from src.engine.gallery import FaceGallery
from src.engine.gallery.persistence import GalleryPersistence
from src.version import __version__

class BackupService:
 def __init__(self,catalog:BackupSourceCatalog,archive:BackupArchive,snapshots:SQLiteSnapshotProvider,maintenance:ApplicationMaintenanceCoordinator|None=None,*,application_version:str=__version__,audit_callback=None):self.catalog=catalog;self.archive=archive;self.snapshots=snapshots;self.maintenance=maintenance;self.application_version=application_version;self.audit=audit_callback
 def create(self,request:BackupRequest)->BackupResult:
  self._audit("BACKUP_STARTED");backup_id=str(uuid.uuid4());maintenance=self.maintenance
  if maintenance:maintenance.begin_backup()
  try:
   estimated=sum(source.source_path.stat().st_size for source in self.catalog.sources() if source.source_path.is_file())
   thumbnail_directory=self.catalog.thumbnail_directory()
   if thumbnail_directory.is_dir():estimated+=sum(path.stat().st_size for path in thumbnail_directory.iterdir() if path.is_file() and not path.is_symlink())
   if self.archive.disk_usage(Path(tempfile.gettempdir())).free<estimated+1_048_576:raise BackupSpaceError("insufficient temporary space to create backup")
   with tempfile.TemporaryDirectory(prefix="fastvision-backup-") as name:
    staging=Path(name);files={};entries=[];missing=[]
    sources=self.catalog.sources();gallery=[s for s in sources if s.component_type in {BackupComponentType.GALLERY_MANIFEST,BackupComponentType.GALLERY_ARCHIVE}]
    if sum(s.source_path.exists() for s in gallery)==1:raise BackupValidationError("gallery persistence pair is incomplete")
    if gallery and all(s.source_path.is_file() for s in gallery):
     by_type={s.component_type:s.source_path for s in gallery}
     GalleryPersistence(enabled=True).import_into(
      FaceGallery(), by_type[BackupComponentType.GALLERY_MANIFEST],
      by_type[BackupComponentType.GALLERY_ARCHIVE],
     )
    for source in sources:
     if not source.source_path.is_file():missing.append(source.component_type.value);continue
     if source.source_path.is_symlink():raise BackupValidationError("backup source symlink is forbidden")
     target=staging/source.archive_path;target.parent.mkdir(parents=True,exist_ok=True);schema=None;snapshot_at=None
     if source.is_sqlite:schema,snapshot_at=self.snapshots.create(source.source_path,target)
     else:
      if source.component_type is BackupComponentType.CONFIGURATION:json.loads(source.source_path.read_text(encoding="utf-8"))
      shutil.copyfile(source.source_path,target)
     entry=BackupFileEntry(source.logical_path,source.archive_path,source.component_type,target.stat().st_size,sha256_file(target),schema,snapshot_at);entries.append(entry);files[source.archive_path]=target
    directory=self.catalog.thumbnail_directory()
    if directory.exists():
     if directory.is_symlink():raise BackupValidationError("thumbnail directory symlink is forbidden")
     for path in sorted(directory.iterdir(),key=lambda p:p.name):
      if path.is_symlink():raise BackupValidationError("thumbnail symlink is forbidden")
      if not path.is_file() or path.suffix.casefold() not in {".jpg",".jpeg",".png"} or path.name.startswith("."):continue
      if not path.stem or not all(c.isalnum() or c in "_-" for c in path.stem):raise BackupValidationError("thumbnail filename is invalid")
      import cv2,numpy as np
      if cv2.imdecode(np.frombuffer(path.read_bytes(),np.uint8),cv2.IMREAD_COLOR) is None:raise BackupValidationError("thumbnail image is invalid")
      archive_path=f"components/thumbnails/{path.name}";target=staging/archive_path;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
      logical=str(path.relative_to(self.catalog.root));entries.append(BackupFileEntry(logical,archive_path,BackupComponentType.THUMBNAIL,target.stat().st_size,sha256_file(target)));files[archive_path]=target
    staged_gallery={entry.component_type:files[entry.archive_path] for entry in entries if entry.component_type in {BackupComponentType.GALLERY_MANIFEST,BackupComponentType.GALLERY_ARCHIVE}}
    if len(staged_gallery)==2:
     GalleryPersistence(enabled=True).import_into(FaceGallery(),staged_gallery[BackupComponentType.GALLERY_MANIFEST],staged_gallery[BackupComponentType.GALLERY_ARCHIVE])
    manifest=BackupManifest(BACKUP_FORMAT_VERSION,datetime.now(timezone.utc),"FastVisionAI",self.application_version,backup_id,"NONE",tuple(sorted(entries,key=lambda i:i.archive_path)),tuple(sorted(set(missing))))
    self.archive.create(request.destination,manifest,files,overwrite=request.overwrite)
    result=BackupResult(True,backup_id,request.destination.name,len(entries),request.destination.stat().st_size,manifest.missing_components,"Backup creado. El backup contiene información sensible y no está cifrado.")
    self._audit("BACKUP_SUCCESS");return result
  except Exception:self._audit("BACKUP_FAILED");raise
  finally:
   if maintenance:maintenance.end_backup()
 def verify(self,path:Path)->BackupVerificationResult:
  try:
   manifest,_=self.archive.verify(path);self._validate_compatibility(manifest);self._audit("VERIFY_SUCCESS");return BackupVerificationResult(True,manifest.backup_id,len(manifest.files),path.stat().st_size,"Backup válido. El backup contiene información sensible y no está cifrado.")
  except Exception:self._audit("VERIFY_FAILED");raise
 def _validate_compatibility(self,manifest):
  for item in manifest.files:
   if item.component_type.value.endswith("DATABASE") and (item.schema_version is None or item.schema_version>1):raise BackupValidationError("SQLite schema is unsupported")
 def _audit(self,event):
  if self.audit:
   try:self.audit(event,{})
   except Exception:pass
