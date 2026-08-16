"""SQLite attendance source of truth using one connection per operation."""

from __future__ import annotations

import csv
import sqlite3
from datetime import date, datetime, time, timezone
from pathlib import Path

from .contracts import (
    AttendanceDailySummary,
    AttendanceEventType,
    AttendanceQuery,
    AttendanceRecord,
    AttendanceRepositoryError,
)
from .migrations import initialize_schema


class AttendanceRepository:
    def __init__(self, database_path: Path, *, timeout: float = 5.0) -> None:
        if timeout <= 0:
            raise ValueError("SQLite timeout must be positive")
        self.database_path = database_path
        self.timeout = timeout

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=self.timeout)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> int:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            version = initialize_schema(connection)
            connection.commit()
            return version
        except AttendanceRepositoryError:
            connection.rollback()
            raise
        except Exception as exc:
            connection.rollback()
            raise AttendanceRepositoryError("attendance initialization failed") from exc
        finally:
            connection.close()

    def create(self, item: AttendanceRecord) -> AttendanceRecord:
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            connection.execute(
                """INSERT INTO attendance_records(
                    attendance_id, person_id, event_type, timestamp,
                    source_event_id, camera_id, session_id, created_at, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item.attendance_id, item.person_id, item.event_type.value,
                    item.timestamp.isoformat(), item.source_event_id, item.camera_id,
                    item.session_id, item.created_at.isoformat(), item.notes,
                ),
            )
            connection.commit()
            return item
        except Exception as exc:
            connection.rollback()
            raise AttendanceRepositoryError("attendance create failed") from exc
        finally:
            connection.close()

    def get_by_id(self, attendance_id: str) -> AttendanceRecord | None:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT * FROM attendance_records WHERE attendance_id = ?", (attendance_id,),
            ).fetchone()
            return _record(row) if row else None
        except Exception as exc:
            raise AttendanceRepositoryError("attendance lookup failed") from exc
        finally:
            connection.close()

    def query(self, query: AttendanceQuery) -> tuple[AttendanceRecord, ...]:
        clauses: list[str] = []
        parameters: list[object] = []
        for sql, value in (
            ("timestamp >= ?", query.date_from),
            ("timestamp <= ?", query.date_to),
            ("person_id = ?", query.person_id),
        ):
            if value is not None:
                clauses.append(sql)
                parameters.append(value.isoformat() if isinstance(value, datetime) else value)
        if query.event_type is not None:
            clauses.append("event_type = ?")
            parameters.append(query.event_type.value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        parameters.extend((query.limit, query.offset))
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM attendance_records" + where
                + " ORDER BY timestamp DESC, attendance_id DESC LIMIT ? OFFSET ?",
                parameters,
            )
            return tuple(_record(row) for row in rows)
        except Exception as exc:
            raise AttendanceRepositoryError("attendance query failed") from exc
        finally:
            connection.close()

    def list(self, *, limit: int = 100) -> tuple[AttendanceRecord, ...]:
        return self.query(AttendanceQuery(limit=limit))

    def count(self) -> int:
        connection = self._connect()
        try:
            return int(connection.execute("SELECT COUNT(*) FROM attendance_records").fetchone()[0])
        except Exception as exc:
            raise AttendanceRepositoryError("attendance count failed") from exc
        finally:
            connection.close()

    def latest_for_person(self, person_id: str) -> AttendanceRecord | None:
        rows = self.query(AttendanceQuery(person_id=person_id, limit=1))
        return rows[0] if rows else None

    def consume_automatic_toggle(
        self, *, person_id: str, source_event_id: str, timestamp: datetime,
        camera_id: str | None, created_at: datetime, day_start: datetime,
        day_end: datetime, duplicate_cooldown_seconds: float,
        minimum_checkout_interval_seconds: float,
    ) -> tuple[str, AttendanceRecord | None]:
        """Atomically consume one persisted recognition and toggle its local day."""
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            consumed = connection.execute(
                "SELECT 1 FROM attendance_consumed_events WHERE source_event_id = ?",
                (source_event_id,),
            ).fetchone()
            if consumed:
                connection.rollback(); return "event_already_consumed", None
            rows = tuple(_record(row) for row in connection.execute(
                """SELECT * FROM attendance_records
                   WHERE person_id = ? AND timestamp >= ? AND timestamp < ?
                   ORDER BY timestamp ASC, attendance_id ASC""",
                (person_id, day_start.isoformat(), day_end.isoformat()),
            ).fetchall())
            check_ins = tuple(row for row in rows if row.event_type in {
                AttendanceEventType.CHECK_IN, AttendanceEventType.MANUAL_CHECK_IN,
            })
            check_outs = tuple(row for row in rows if row.event_type in {
                AttendanceEventType.CHECK_OUT, AttendanceEventType.MANUAL_CHECK_OUT,
            })
            proposed = None; reason = "day_complete"
            if check_outs and not check_ins:
                reason = "manual_checkout_without_checkin"
            elif not check_ins and not check_outs:
                proposed = AttendanceEventType.CHECK_IN; reason = "recorded"
            elif check_ins and not check_outs:
                elapsed = (timestamp - check_ins[0].timestamp).total_seconds()
                latest_elapsed = (timestamp - rows[-1].timestamp).total_seconds()
                if latest_elapsed < duplicate_cooldown_seconds:
                    reason = "duplicate_cooldown"
                elif elapsed < minimum_checkout_interval_seconds:
                    reason = "minimum_interval"
                else:
                    proposed = AttendanceEventType.CHECK_OUT; reason = "recorded"
            record = None
            if proposed is not None:
                import uuid
                record = AttendanceRecord(
                    str(uuid.uuid4()), person_id, proposed, timestamp, source_event_id,
                    camera_id, None, created_at,
                )
                connection.execute(
                    """INSERT INTO attendance_records(
                      attendance_id,person_id,event_type,timestamp,source_event_id,
                      camera_id,session_id,created_at,notes) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (record.attendance_id, record.person_id, record.event_type.value,
                     record.timestamp.isoformat(), record.source_event_id, record.camera_id,
                     record.session_id, record.created_at.isoformat(), record.notes),
                )
            connection.execute(
                "INSERT INTO attendance_consumed_events(source_event_id,attendance_id,consumed_at) VALUES (?,?,?)",
                (source_event_id, None if record is None else record.attendance_id,
                 created_at.isoformat()),
            )
            connection.commit(); return reason, record
        except Exception as exc:
            connection.rollback()
            raise AttendanceRepositoryError("automatic attendance transaction failed") from exc
        finally:
            connection.close()

    def is_source_event_consumed(self, source_event_id: str) -> bool:
        connection = self._connect()
        try:
            return connection.execute(
                "SELECT 1 FROM attendance_consumed_events WHERE source_event_id = ?",
                (source_event_id,),
            ).fetchone() is not None
        except Exception as exc:
            raise AttendanceRepositoryError("attendance consumption lookup failed") from exc
        finally: connection.close()

    def daily_summary(self, day: date) -> AttendanceDailySummary:
        start = datetime.combine(day, time.min, tzinfo=timezone.utc)
        end = datetime.combine(day, time.max, tzinfo=timezone.utc)
        return self.summary_between(day,start,end)

    def summary_between(self,day:date,start:datetime,end:datetime)->AttendanceDailySummary:
        connection = self._connect()
        try:
            row = connection.execute(
                """SELECT
                    SUM(CASE WHEN event_type IN (?, ?) THEN 1 ELSE 0 END) AS entries,
                    SUM(CASE WHEN event_type IN (?, ?) THEN 1 ELSE 0 END) AS exits,
                    COUNT(DISTINCT person_id) AS people,
                    MIN(timestamp) AS first_at,
                    MAX(timestamp) AS last_at
                FROM attendance_records WHERE timestamp >= ? AND timestamp <= ?""",
                (
                    AttendanceEventType.CHECK_IN.value,
                    AttendanceEventType.MANUAL_CHECK_IN.value,
                    AttendanceEventType.CHECK_OUT.value,
                    AttendanceEventType.MANUAL_CHECK_OUT.value,
                    start.isoformat(), end.isoformat(),
                ),
            ).fetchone()
            return AttendanceDailySummary(
                day, int(row["entries"] or 0), int(row["exits"] or 0),
                int(row["people"] or 0),
                datetime.fromisoformat(row["first_at"]) if row["first_at"] else None,
                datetime.fromisoformat(row["last_at"]) if row["last_at"] else None,
            )
        except Exception as exc:
            raise AttendanceRepositoryError("attendance daily summary failed") from exc
        finally:
            connection.close()

    def count_for_person_between(
        self, person_id: str, date_from: datetime, date_to: datetime,
    ) -> int:
        connection = self._connect()
        try:
            row = connection.execute(
                """SELECT COUNT(*) FROM attendance_records
                   WHERE person_id = ? AND timestamp >= ? AND timestamp <= ?""",
                (person_id, date_from.isoformat(), date_to.isoformat()),
            ).fetchone()
            return int(row[0])
        except Exception as exc:
            raise AttendanceRepositoryError("attendance person summary failed") from exc
        finally:
            connection.close()

    def export_csv(self, destination: Path, query: AttendanceQuery) -> int:
        if destination.exists():
            raise AttendanceRepositoryError("CSV destination exists")
        rows = self.query(query)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with destination.open("x", newline="", encoding="utf-8") as stream:
                writer = csv.writer(stream)
                writer.writerow(("timestamp", "person_id", "event_type", "camera_id", "source_event_id"))
                for item in rows:
                    writer.writerow((
                        item.timestamp.isoformat(), item.person_id, item.event_type.value,
                        item.camera_id or "", item.source_event_id or "",
                    ))
            return len(rows)
        except Exception as exc:
            raise AttendanceRepositoryError("attendance CSV export failed") from exc


def _record(row: sqlite3.Row) -> AttendanceRecord:
    return AttendanceRecord(
        str(row["attendance_id"]), str(row["person_id"]),
        AttendanceEventType(str(row["event_type"])), datetime.fromisoformat(row["timestamp"]),
        row["source_event_id"], row["camera_id"], row["session_id"],
        datetime.fromisoformat(row["created_at"]), row["notes"],
    )
