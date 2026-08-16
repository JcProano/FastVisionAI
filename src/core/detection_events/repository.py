"""SQLite persistence with one connection per operation."""
from __future__ import annotations
import csv
import sqlite3
from datetime import datetime
from pathlib import Path

from .contracts import (
    DetectionEventQuery, DetectionEventRecord, DetectionEventRepositoryError,
    DetectionEventType,
)
from .migrations import initialize_schema


class DetectionEventRepository:
    def __init__(self, database_path: Path, *, timeout: float = 5.0) -> None:
        if timeout <= 0: raise ValueError("timeout must be positive")
        self.database_path = database_path
        self.timeout = timeout

    def initialize(self) -> int:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            version = initialize_schema(connection)
            connection.commit()
            return version
        except DetectionEventRepositoryError:
            connection.rollback(); raise
        except Exception as exc:
            connection.rollback()
            raise DetectionEventRepositoryError("event database initialization failed") from exc
        finally: connection.close()

    def create(self, event: DetectionEventRecord) -> DetectionEventRecord:
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            connection.execute("""INSERT INTO detection_events(
                event_id,person_id,event_type,timestamp,camera_id,display_name_snapshot,
                similarity,quality_score,recognition_state,administrative_status,session_id,created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""", (
                event.event_id, event.person_id, event.event_type.value,
                event.timestamp.isoformat(), event.camera_id, event.display_name_snapshot,
                event.similarity, event.quality_score, event.recognition_state,
                event.administrative_status, event.session_id, event.created_at.isoformat(),
            ))
            connection.commit(); return event
        except Exception as exc:
            connection.rollback()
            raise DetectionEventRepositoryError("detection event could not be persisted") from exc
        finally: connection.close()

    def get_by_event_id(self, event_id: str) -> DetectionEventRecord | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM detection_events WHERE event_id = ?", (event_id,)
            ).fetchone()
            return None if row is None else _record(row)
        except Exception as exc:
            raise DetectionEventRepositoryError("detection event lookup failed") from exc
        finally: connection.close()

    def query(self, query: DetectionEventQuery) -> tuple[DetectionEventRecord, ...]:
        clauses: list[str] = []; parameters: list[object] = []
        if query.date_from:
            clauses.append("timestamp >= ?"); parameters.append(query.date_from.isoformat())
        if query.date_to:
            clauses.append("timestamp <= ?"); parameters.append(query.date_to.isoformat())
        if query.person_id is not None:
            clauses.append("person_id = ?"); parameters.append(query.person_id)
        if query.event_type is not None:
            clauses.append("event_type = ?"); parameters.append(query.event_type.value)
        if query.camera_id is not None:
            clauses.append("camera_id = ?"); parameters.append(query.camera_id)
        if query.administrative_status is not None:
            clauses.append("administrative_status = ?")
            parameters.append(query.administrative_status)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        parameters.extend((query.limit, query.offset))
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM detection_events" + where
                + " ORDER BY timestamp DESC, event_id DESC LIMIT ? OFFSET ?", parameters,
            ).fetchall()
            return tuple(_record(row) for row in rows)
        except Exception as exc:
            raise DetectionEventRepositoryError("detection event query failed") from exc
        finally: connection.close()

    def list(self, *, limit: int = 100) -> tuple[DetectionEventRecord, ...]:
        return self.query(DetectionEventQuery(limit=limit))

    def count(self) -> int:
        connection = self._connect()
        try: return int(connection.execute("SELECT COUNT(*) FROM detection_events").fetchone()[0])
        except Exception as exc:
            raise DetectionEventRepositoryError("detection event count failed") from exc
        finally: connection.close()

    def export_csv(self, destination: Path, query: DetectionEventQuery) -> int:
        rows = self.query(query)
        if destination.exists():
            raise DetectionEventRepositoryError("CSV destination already exists")
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with destination.open("x", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(("timestamp", "event_type", "person_id", "display_name_snapshot",
                                 "similarity", "quality_score", "recognition_state", "camera_id"))
                for item in rows:
                    writer.writerow((item.timestamp.isoformat(), item.event_type.value,
                                     item.person_id or "", item.display_name_snapshot or "",
                                     item.similarity, item.quality_score,
                                     item.recognition_state, item.camera_id or ""))
            return len(rows)
        except Exception as exc:
            raise DetectionEventRepositoryError("CSV export failed") from exc

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=self.timeout)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def _record(row: sqlite3.Row) -> DetectionEventRecord:
    return DetectionEventRecord(
        str(row["event_id"]), row["person_id"], DetectionEventType(str(row["event_type"])),
        datetime.fromisoformat(str(row["timestamp"])), row["camera_id"],
        row["display_name_snapshot"], row["similarity"], row["quality_score"],
        str(row["recognition_state"]), row["administrative_status"], row["session_id"],
        datetime.fromisoformat(str(row["created_at"])),
    )
