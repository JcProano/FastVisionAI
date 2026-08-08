"""Thread-compatible SQLite repository using one connection per operation."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .contracts import (
    PersonCreateRequest, PersonDatabaseStats, PersonRecord, PersonSearchQuery,
    PersonStatus, PersonUpdateRequest,
)
from .migrations import SCHEMA_VERSION, PersonDatabaseMigrationError, initialize_schema
from .validators import EcuadorianCedulaValidator, validate_person_id


class PersonRepositoryError(RuntimeError):
    pass


class DuplicatePersonIdError(PersonRepositoryError):
    pass


class DuplicateCedulaError(PersonRepositoryError):
    pass


class PersonNotFoundError(PersonRepositoryError):
    pass


class PersonRepository:
    """No connection is shared across UI/worker threads; every call closes its own."""

    def __init__(self, database_path: Path, *, timeout: float = 5.0) -> None:
        if timeout <= 0:
            raise ValueError("SQLite timeout must be positive")
        self.database_path = database_path
        self.timeout = timeout

    def initialize(self) -> int:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = self._connect()
        try:
            return initialize_schema(connection)
        except PersonDatabaseMigrationError:
            raise
        except Exception as exc:
            raise PersonRepositoryError("person database initialization failed") from exc
        finally:
            connection.close()

    def create(self, request: PersonCreateRequest) -> PersonRecord:
        now = datetime.now(timezone.utc).isoformat()
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            connection.execute(
                """INSERT INTO people(
                    person_id, cedula, first_name, last_name, address, phone, email,
                    birth_date, sex, notes, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    request.person_id, request.cedula, request.first_name, request.last_name,
                    request.address, request.phone, request.email, request.birth_date,
                    request.sex, request.notes, PersonStatus.PENDING_BIOMETRIC.value, now, now,
                ),
            )
            connection.commit()
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            self._raise_integrity(exc, request.person_id, request.cedula)
        except Exception as exc:
            connection.rollback()
            raise PersonRepositoryError("person creation failed") from exc
        finally:
            connection.close()
        record = self.get_by_person_id(request.person_id)
        assert record is not None
        return record

    def get_by_person_id(self, person_id: str) -> PersonRecord | None:
        normalized = validate_person_id(person_id)
        return self._one("SELECT * FROM people WHERE person_id = ?", (normalized,))

    def get_by_cedula(self, cedula: str) -> PersonRecord | None:
        normalized = EcuadorianCedulaValidator.validate(cedula)
        return self._one("SELECT * FROM people WHERE cedula = ?", (normalized,))

    def update(self, request: PersonUpdateRequest) -> PersonRecord:
        values: dict[str, str | None] = {}
        for field in (
            "first_name", "last_name", "address", "phone", "email", "birth_date",
            "sex", "notes",
        ):
            value = getattr(request, field)
            if value is not None:
                values[field] = value
        for field in request.clear_fields:
            values[field] = None
        if not values:
            existing = self.get_by_person_id(request.person_id)
            if existing is None:
                raise PersonNotFoundError("person does not exist")
            return existing
        values["updated_at"] = datetime.now(timezone.utc).isoformat()
        assignments = ", ".join(f"{field} = ?" for field in values)
        parameters = tuple(values.values()) + (request.person_id,)
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            cursor = connection.execute(
                f"UPDATE people SET {assignments} WHERE person_id = ?", parameters
            )
            if cursor.rowcount != 1:
                raise PersonNotFoundError("person does not exist")
            connection.commit()
        except PersonNotFoundError:
            connection.rollback()
            raise
        except Exception as exc:
            connection.rollback()
            raise PersonRepositoryError("person update failed") from exc
        finally:
            connection.close()
        result = self.get_by_person_id(request.person_id)
        assert result is not None
        return result

    def set_status(self, person_id: str, status: PersonStatus) -> PersonRecord:
        normalized = validate_person_id(person_id)
        if not isinstance(status, PersonStatus):
            raise ValueError("status must be a PersonStatus")
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            cursor = connection.execute(
                "UPDATE people SET status = ?, updated_at = ? WHERE person_id = ?",
                (status.value, datetime.now(timezone.utc).isoformat(), normalized),
            )
            if cursor.rowcount != 1:
                raise PersonNotFoundError("person does not exist")
            connection.commit()
        except PersonNotFoundError:
            connection.rollback()
            raise
        except Exception as exc:
            connection.rollback()
            raise PersonRepositoryError("person status update failed") from exc
        finally:
            connection.close()
        result = self.get_by_person_id(normalized)
        assert result is not None
        return result

    def delete(self, person_id: str) -> bool:
        normalized = validate_person_id(person_id)
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            cursor = connection.execute("DELETE FROM people WHERE person_id = ?", (normalized,))
            connection.commit()
            return cursor.rowcount == 1
        except Exception as exc:
            connection.rollback()
            raise PersonRepositoryError("person deletion failed") from exc
        finally:
            connection.close()

    def delete_pending(self, person_id: str) -> bool:
        normalized = validate_person_id(person_id)
        connection = self._connect()
        try:
            connection.execute("BEGIN")
            cursor = connection.execute(
                "DELETE FROM people WHERE person_id = ? AND status = ?",
                (normalized, PersonStatus.PENDING_BIOMETRIC.value),
            )
            connection.commit()
            return cursor.rowcount == 1
        except Exception as exc:
            connection.rollback()
            raise PersonRepositoryError("pending person deletion failed") from exc
        finally:
            connection.close()

    def list(self, *, limit: int = 100, offset: int = 0) -> tuple[PersonRecord, ...]:
        return self.search(PersonSearchQuery(limit=limit, offset=offset))

    def search(self, query: PersonSearchQuery) -> tuple[PersonRecord, ...]:
        clauses: list[str] = []
        parameters: list[object] = []
        if query.cedula is not None:
            clauses.append("cedula = ?")
            parameters.append(EcuadorianCedulaValidator.validate(query.cedula))
        for field in ("first_name", "last_name", "email"):
            value = getattr(query, field)
            if value is not None:
                clauses.append(f"{field} LIKE ? COLLATE NOCASE")
                parameters.append(f"%{value.strip()}%")
        if query.phone is not None:
            clauses.append("phone LIKE ?")
            parameters.append(f"%{query.phone.strip()}%")
        if query.status is not None:
            clauses.append("status = ?")
            parameters.append(query.status.value)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        parameters.extend((query.limit, query.offset))
        connection = self._connect()
        try:
            rows = connection.execute(
                "SELECT * FROM people" + where
                + " ORDER BY last_name COLLATE NOCASE, first_name COLLATE NOCASE, person_id"
                + " LIMIT ? OFFSET ?",
                tuple(parameters),
            ).fetchall()
            return tuple(_record(row) for row in rows)
        except Exception as exc:
            raise PersonRepositoryError("person search failed") from exc
        finally:
            connection.close()

    def exists_cedula(self, cedula: str) -> bool:
        return self.get_by_cedula(cedula) is not None

    def count(self) -> int:
        connection = self._connect()
        try:
            return int(connection.execute("SELECT COUNT(*) FROM people").fetchone()[0])
        except Exception as exc:
            raise PersonRepositoryError("person count failed") from exc
        finally:
            connection.close()

    def stats(self) -> PersonDatabaseStats:
        connection = self._connect()
        try:
            counts = {status.value: 0 for status in PersonStatus}
            for row in connection.execute(
                "SELECT status, COUNT(*) FROM people GROUP BY status"
            ):
                counts[str(row[0])] = int(row[1])
            return PersonDatabaseStats(
                sum(counts.values()), counts[PersonStatus.PENDING_BIOMETRIC.value],
                counts[PersonStatus.ACTIVE.value], counts[PersonStatus.DISABLED.value],
                SCHEMA_VERSION,
            )
        except Exception as exc:
            raise PersonRepositoryError("person database statistics failed") from exc
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=self.timeout)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _one(self, sql: str, parameters: tuple[object, ...]) -> PersonRecord | None:
        connection = self._connect()
        try:
            row = connection.execute(sql, parameters).fetchone()
            return None if row is None else _record(row)
        except Exception as exc:
            raise PersonRepositoryError("person lookup failed") from exc
        finally:
            connection.close()

    def _raise_integrity(self, error: sqlite3.IntegrityError,
                         person_id: str, cedula: str) -> None:
        if self._one("SELECT * FROM people WHERE person_id = ?", (person_id,)) is not None:
            raise DuplicatePersonIdError("person_id is already registered") from error
        if self._one("SELECT * FROM people WHERE cedula = ?", (cedula,)) is not None:
            raise DuplicateCedulaError("cedula is already registered") from error
        raise PersonRepositoryError("person constraint validation failed") from error


def _record(row: sqlite3.Row) -> PersonRecord:
    return PersonRecord(
        str(row["person_id"]), str(row["cedula"]), str(row["first_name"]),
        str(row["last_name"]), row["address"], row["phone"], row["email"],
        row["birth_date"], row["sex"], row["notes"], PersonStatus(str(row["status"])),
        datetime.fromisoformat(str(row["created_at"])),
        datetime.fromisoformat(str(row["updated_at"])),
    )
