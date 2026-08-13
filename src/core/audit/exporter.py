"""Safe deterministic CSV export without audit metadata."""
from __future__ import annotations
import csv
from pathlib import Path
from .contracts import AuditExportError,AuditRecord

COLUMNS=("timestamp_utc","action","success","actor_user_id","actor_role","entity_type","entity_id","message","source","session_id")

class AuditCSVExporter:
    def export(self,records:tuple[AuditRecord,...],destination:Path,*,overwrite:bool=False)->int:
        if destination.exists() and not overwrite:raise AuditExportError("audit CSV destination already exists")
        destination.parent.mkdir(parents=True,exist_ok=True)
        mode="w" if overwrite else "x"
        try:
            with destination.open(mode,encoding="utf-8",newline="") as stream:
                writer=csv.writer(stream);writer.writerow(COLUMNS)
                for item in records:writer.writerow(tuple(_safe(value) for value in (item.timestamp_utc.isoformat(),item.action.value,item.success,item.actor_user_id,item.actor_role,item.entity_type.value,item.entity_id,item.message,item.source,item.session_id)))
            return len(records)
        except AuditExportError:raise
        except Exception as exc:raise AuditExportError("audit CSV export failed") from exc

def _safe(value:object)->str:
    text="" if value is None else str(value)
    return "'"+text if text.startswith(("=","+","-","@")) else text

