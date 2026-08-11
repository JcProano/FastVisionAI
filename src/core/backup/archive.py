"""Safe ZIP construction and verification; never uses extractall()."""
from __future__ import annotations
import hashlib,json,os,shutil,tempfile,uuid,zipfile
from dataclasses import asdict
from datetime import datetime,timezone
from pathlib import Path,PurePosixPath
from .contracts import *

MANIFEST_NAME="manifest.json"
def sha256_file(path:Path)->str:
 digest=hashlib.sha256()
 with path.open("rb") as stream:
  for block in iter(lambda:stream.read(1024*1024),b""):digest.update(block)
 return digest.hexdigest()
def _entry_dict(item:BackupFileEntry):
 value=asdict(item);value["component_type"]=item.component_type.value
 value["snapshot_at"]=item.snapshot_at.isoformat() if item.snapshot_at else None;return value
def manifest_bytes(manifest:BackupManifest)->bytes:
 root={"format_version":manifest.format_version,"created_at":manifest.created_at.isoformat(),"application":manifest.application,"application_version":manifest.application_version,"backup_id":manifest.backup_id,"encryption":manifest.encryption,"files":[_entry_dict(i) for i in manifest.files],"missing_components":list(manifest.missing_components)}
 return json.dumps(root,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()
def parse_manifest(payload:bytes)->BackupManifest:
 try:root=json.loads(payload.decode("utf-8"))
 except Exception as exc:raise BackupValidationError("backup manifest is invalid") from exc
 if not isinstance(root,dict) or root.get("format_version")!=BACKUP_FORMAT_VERSION:raise BackupValidationError("backup format version is unsupported")
 if root.get("encryption")!="NONE":raise BackupValidationError("backup encryption mode is unsupported")
 try:
  files=tuple(BackupFileEntry(str(i["logical_path"]),str(i["archive_path"]),BackupComponentType(i["component_type"]),int(i["size"]),str(i["sha256"]),None if i.get("schema_version") is None else int(i["schema_version"]),None if i.get("snapshot_at") is None else datetime.fromisoformat(i["snapshot_at"])) for i in root["files"])
  result=BackupManifest(int(root["format_version"]),datetime.fromisoformat(root["created_at"]),str(root["application"]),str(root["application_version"]),str(root["backup_id"]),str(root["encryption"]),files,tuple(str(x) for x in root.get("missing_components",())))
 except Exception as exc:raise BackupValidationError("backup manifest fields are invalid") from exc
 paths=[i.archive_path for i in files]
 if len(paths)!=len(set(paths)):raise BackupValidationError("manifest contains duplicate entries")
 for item in files:_safe_name(item.archive_path);_safe_name(item.logical_path)
 return result
def _safe_name(name:str)->None:
 path=PurePosixPath(name)
 if not name or path.is_absolute() or ".." in path.parts or "\\" in name or name.startswith("/"):raise BackupValidationError("archive path is unsafe")

class BackupArchive:
 def __init__(self,*,maximum_archive_size_bytes:int=2_147_483_648,maximum_file_count:int=100_000,disk_usage=shutil.disk_usage):
  if maximum_archive_size_bytes<=0 or maximum_file_count<=0:raise ValueError("archive limits must be positive")
  self.max_size=maximum_archive_size_bytes;self.max_count=maximum_file_count;self.disk_usage=disk_usage
 def create(self,destination:Path,manifest:BackupManifest,files:dict[str,Path],*,overwrite:bool=False)->None:
  if destination.exists() and not overwrite:raise BackupValidationError("backup destination already exists")
  destination.parent.mkdir(parents=True,exist_ok=True);required=sum(p.stat().st_size for p in files.values())+len(manifest_bytes(manifest))+1_048_576
  if self.disk_usage(destination.parent).free<required:raise BackupSpaceError("insufficient space to create backup")
  descriptor,name=tempfile.mkstemp(prefix=f".{destination.name}.",suffix=".tmp",dir=destination.parent);os.close(descriptor);temporary=Path(name)
  try:
   with zipfile.ZipFile(temporary,"w",compression=zipfile.ZIP_DEFLATED,allowZip64=True) as archive:
    archive.writestr(MANIFEST_NAME,manifest_bytes(manifest))
    for archive_path,path in sorted(files.items()):archive.write(path,archive_path)
   self.verify(temporary)
   os.replace(temporary,destination)
  except Exception:temporary.unlink(missing_ok=True);raise
 def verify(self,archive_path:Path,extract_to:Path|None=None)->tuple[BackupManifest,dict[str,Path]]:
  if archive_path.stat().st_size>self.max_size:raise BackupValidationError("backup archive exceeds configured limit")
  extracted={}
  try:
   with zipfile.ZipFile(archive_path,"r") as archive:
    infos=archive.infolist();names=[i.filename for i in infos]
    if len(infos)>self.max_count or len(names)!=len(set(names)):raise BackupValidationError("archive entry count or duplicates are invalid")
    if names.count(MANIFEST_NAME)!=1:raise BackupValidationError("archive must contain one manifest")
    total=0
    for info in infos:
     _safe_name(info.filename);total+=info.file_size
     if total>self.max_size:raise BackupValidationError("expanded archive exceeds configured limit")
     if (info.external_attr>>16)&0o170000==0o120000:raise BackupValidationError("archive symlinks are forbidden")
    manifest=parse_manifest(archive.read(MANIFEST_NAME))
    expected={i.archive_path:i for i in manifest.files}
    if set(names)!={MANIFEST_NAME,*expected}:raise BackupValidationError("archive contents differ from manifest")
    for name,item in expected.items():
     info=archive.getinfo(name)
     if info.file_size!=item.size:raise BackupIntegrityError("backup file size mismatch")
     digest=hashlib.sha256();target=None;stream=archive.open(info)
     if extract_to is not None:
      target=(extract_to/PurePosixPath(name));target.parent.mkdir(parents=True,exist_ok=True);output=target.open("xb")
     else:output=None
     try:
      for block in iter(lambda:stream.read(1024*1024),b""):digest.update(block);output and output.write(block)
     finally:
      stream.close();output and output.close()
     if digest.hexdigest()!=item.sha256:raise BackupIntegrityError("backup checksum mismatch")
     if target:extracted[name]=target
    return manifest,extracted
  except (zipfile.BadZipFile,OSError) as exc:raise BackupValidationError("backup archive is invalid") from exc
