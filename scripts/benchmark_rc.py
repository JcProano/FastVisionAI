#!/usr/bin/env python3
"""Non-biometric RC micro-benchmark; results are not face-recognition FPS."""
from __future__ import annotations
import json,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from src.core.audit import AuditAction,AuditEntityType,AuditRepository,AuditService
from src.core.configuration import ConfigurationLoader,ConfigurationProfile,ConfigurationValidator
from src.core.security import PasswordHasher
from src.version import __version__

def elapsed(call):start=time.perf_counter();call();return (time.perf_counter()-start)*1000
def main()->int:
 with tempfile.TemporaryDirectory(prefix="fastvision-benchmark-") as name:
  root=Path(name);loader=ConfigurationLoader(ConfigurationValidator(ROOT));config_ms=elapsed(lambda:loader.load(ROOT/"config/local_face_validation.dev.json",ConfigurationProfile.DEVELOPMENT))
  repository=AuditRepository(root/"audit.db");repository.initialize();service=AuditService(repository);audit_ms=elapsed(lambda:service.record(AuditAction.CONFIG_VALIDATED,AuditEntityType.CONFIGURATION))
  hasher=PasswordHasher();stored=None
  def hash_one():
   nonlocal stored;stored=hasher.hash_password("ReleaseCandidate123")
  scrypt_hash_ms=elapsed(hash_one);scrypt_verify_ms=elapsed(lambda:hasher.verify_password("ReleaseCandidate123",stored))
  query_ms=elapsed(repository.summary)
 print(json.dumps({"application_version":__version__,"warning":"Micro-benchmark de infraestructura; no mide reconocimiento facial.","milliseconds":{"config_load":config_ms,"sqlite_audit_append":audit_ms,"sqlite_summary":query_ms,"scrypt_hash":scrypt_hash_ms,"scrypt_verify":scrypt_verify_ms}},indent=2));return 0
if __name__=="__main__":raise SystemExit(main())

