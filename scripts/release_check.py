#!/usr/bin/env python3
"""Read-only release readiness checks (temporary files only)."""
from __future__ import annotations
import argparse,json,subprocess,sys,tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from src.core.configuration import ConfigurationLoader,ConfigurationProfile,ConfigurationValidator
from src.version import __version__
from src.core.backup import BACKUP_FORMAT_VERSION,BackupArchive
from src.core.person_database.migrations import SCHEMA_VERSION as PEOPLE_SCHEMA
from src.core.detection_events.migrations import SCHEMA_VERSION as EVENTS_SCHEMA
from src.core.attendance.migrations import SCHEMA_VERSION as ATTENDANCE_SCHEMA
from src.core.security.migrations import SCHEMA_VERSION as USERS_SCHEMA
from src.core.audit.migrations import SCHEMA_VERSION as AUDIT_SCHEMA

def run(configs:tuple[Path,...],*,require_clean=False,run_tests=False,backup:Path|None=None,require_models=False)->tuple[bool,tuple[str,...]]:
 messages=[];ok=True
 if sys.version_info<(3,12):ok=False;messages.append("FAIL Python 3.12+ requerido")
 else:messages.append(f"OK Python {sys.version_info.major}.{sys.version_info.minor}")
 if __version__!="1.0.0-rc1":ok=False;messages.append("FAIL versión central")
 else:messages.append(f"OK versión {__version__}")
 try:
  __import__("src.ui.main");__import__("src.core.backup");__import__("src.core.audit");messages.append("OK imports esenciales")
 except Exception:ok=False;messages.append("FAIL imports esenciales")
 schemas=(PEOPLE_SCHEMA,EVENTS_SCHEMA,ATTENDANCE_SCHEMA,USERS_SCHEMA,AUDIT_SCHEMA,BACKUP_FORMAT_VERSION)
 if schemas!=(1,1,1,1,1,1):ok=False;messages.append("FAIL schemas incompatibles")
 else:messages.append("OK schemas SQLite/backup versión 1")
 loader=ConfigurationLoader(ConfigurationValidator(ROOT))
 for path in configs:
  try:
   raw=json.loads(path.read_text(encoding="utf-8"));profile=ConfigurationProfile(str(raw["configuration_manager"]["profile"]));snapshot=loader.load(path,profile)
   if snapshot.schema_version!=1:raise ValueError("schema")
   messages.append(f"OK config {path.name} {profile.value}")
  except Exception:ok=False;messages.append(f"FAIL config {path.name}")
 tracked=_git("ls-files","data")
 if tracked.strip():ok=False;messages.append("FAIL data/ contiene archivos versionados")
 else:messages.append("OK data/ no versionado")
 hardcoded=[]
 for base in (ROOT/"src",ROOT/"config",ROOT/"docs",ROOT/"deploy"):
  if not base.exists():continue
  for item in base.rglob("*"):
   if item.is_file() and item.suffix in {".py",".json",".md",".example"}:
    try:text=item.read_text(encoding="utf-8")
    except UnicodeDecodeError:continue
    if "/home/fastcell" in text:hardcoded.append(str(item.relative_to(ROOT)))
 if hardcoded:ok=False;messages.append("FAIL rutas de usuario: "+", ".join(hardcoded))
 else:messages.append("OK sin rutas hardcoded de usuario")
 if require_clean:
  if _git("status","--porcelain").strip():ok=False;messages.append("FAIL working tree no limpio")
  else:messages.append("OK working tree limpio")
 tags=set(_git("tag","--list").splitlines())
 messages.append("WARN tags históricos v0.33/v0.34 inconsistentes; no se modifican" if {"v0.33-audit-log","v0.34-system-health"}<=tags else "OK tags históricos no presentes")
 if backup is not None:
  try:manifest,_=BackupArchive().verify(backup);messages.append(f"OK backup manifest {manifest.format_version} app {manifest.application_version}")
  except Exception:ok=False;messages.append("FAIL backup manifest")
 if require_models:
  required=(ROOT/"models/face/face_detection_yunet_2026may.onnx",ROOT/"models/face_embedding/w600k_mbf.onnx")
  missing=[item.name for item in required if not item.is_file()]
  if missing:ok=False;messages.append("FAIL modelos requeridos ausentes: "+", ".join(missing))
  else:messages.append("OK modelos requeridos presentes")
 if run_tests:
  result=subprocess.run([sys.executable,"-m","unittest"],cwd=ROOT,check=False)
  ok=ok and result.returncode==0;messages.append("OK tests" if result.returncode==0 else "FAIL tests")
 with tempfile.TemporaryDirectory(prefix=".fastvision-rc-",dir=ROOT) as name:
  if not Path(name).is_dir():ok=False
  else:messages.append("OK directorio del proyecto escribible mediante temporal")
 return ok,tuple(messages)

def _git(*args:str)->str:
 result=subprocess.run(("git",*args),cwd=ROOT,text=True,capture_output=True,check=False)
 return result.stdout if result.returncode==0 else ""

def main()->int:
 parser=argparse.ArgumentParser();parser.add_argument("--config",action="append",type=Path);parser.add_argument("--require-clean",action="store_true");parser.add_argument("--run-tests",action="store_true");parser.add_argument("--backup",type=Path);parser.add_argument("--require-models",action="store_true");args=parser.parse_args()
 configs=tuple(args.config or (ROOT/"config/local_face_validation.dev.json",ROOT/"config/local_face_validation.prod.json"));ok,messages=run(configs,require_clean=args.require_clean,run_tests=args.run_tests,backup=args.backup,require_models=args.require_models);print("\n".join(messages));return 0 if ok else 1
if __name__=="__main__":raise SystemExit(main())
