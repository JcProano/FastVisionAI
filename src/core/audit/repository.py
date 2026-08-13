"""Append-only SQLite repository for administrative audit records."""
from __future__ import annotations
import json, sqlite3
from datetime import datetime, timezone
from pathlib import Path
from .contracts import *
from .migrations import initialize_schema

class AuditRepository:
    def __init__(self, database_path: Path, *, timeout: float = 5.0) -> None:
        if timeout <= 0: raise ValueError("timeout must be positive")
        self.database_path=database_path; self.timeout=timeout

    def initialize(self) -> int:
        self.database_path.parent.mkdir(parents=True,exist_ok=True)
        connection=self._connect()
        try:
            connection.execute("BEGIN"); version=initialize_schema(connection); connection.commit(); return version
        except AuditRepositoryError: connection.rollback(); raise
        except Exception as exc: connection.rollback(); raise AuditRepositoryError("audit database initialization failed") from exc
        finally: connection.close()

    def append(self, record: AuditRecord) -> AuditRecord:
        connection=self._connect()
        try:
            connection.execute("BEGIN")
            connection.execute("""INSERT INTO audit_records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",(
                record.audit_id,record.timestamp_utc.isoformat(),record.actor_user_id,record.actor_role,
                record.action.value,record.entity_type.value,record.entity_id,int(record.success),record.message,
                record.source,record.session_id,json.dumps(dict(record.metadata),sort_keys=True,separators=(",",":")),
                datetime.now(timezone.utc).isoformat(),
            ));connection.commit();return record
        except Exception as exc: connection.rollback();raise AuditRepositoryError("audit record could not be appended") from exc
        finally:connection.close()

    def query(self, query: AuditQuery, *, maximum_limit: int = 1000) -> tuple[AuditRecord,...]:
        clauses=[];parameters=[]
        for clause,value in (("timestamp_utc >= ?",query.date_from.isoformat() if query.date_from else None),("timestamp_utc <= ?",query.date_to.isoformat() if query.date_to else None),("action = ?",query.action.value if query.action else None),("actor_user_id = ?",query.actor_user_id),("actor_role = ?",query.actor_role),("entity_type = ?",query.entity_type.value if query.entity_type else None),("entity_id = ?",query.entity_id)):
            if value is not None:clauses.append(clause);parameters.append(value)
        if query.success is not None:clauses.append("success = ?");parameters.append(int(query.success))
        where=" WHERE "+" AND ".join(clauses) if clauses else ""
        parameters.extend((min(query.limit,maximum_limit),query.offset))
        connection=self._connect()
        try:
            rows=connection.execute("SELECT * FROM audit_records"+where+" ORDER BY timestamp_utc DESC,audit_id DESC LIMIT ? OFFSET ?",parameters).fetchall()
            return tuple(_record(row) for row in rows)
        except Exception as exc:raise AuditRepositoryError("audit query failed") from exc
        finally:connection.close()

    def summary(self) -> AuditSummaryDTO:
        connection=self._connect()
        try:
            row=connection.execute("SELECT COUNT(*),COALESCE(SUM(success),0),MAX(timestamp_utc) FROM audit_records").fetchone()
            total=int(row[0]); successes=int(row[1]); latest=datetime.fromisoformat(row[2]) if row[2] else None
            return AuditSummaryDTO(total,successes,total-successes,latest)
        except Exception as exc:raise AuditRepositoryError("audit summary failed") from exc
        finally:connection.close()

    def _connect(self):
        connection=sqlite3.connect(self.database_path,timeout=self.timeout);connection.row_factory=sqlite3.Row;connection.execute("PRAGMA foreign_keys = ON");return connection

def _record(row:sqlite3.Row)->AuditRecord:
    return AuditRecord(str(row["audit_id"]),datetime.fromisoformat(str(row["timestamp_utc"])),row["actor_user_id"],row["actor_role"],AuditAction(str(row["action"])),AuditEntityType(str(row["entity_type"])),row["entity_id"],bool(row["success"]),str(row["message"]),str(row["source"]),row["session_id"],json.loads(str(row["metadata_json"])))

